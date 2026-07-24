"""Publish exact-identity v9 over accepted v8 and fresh federation v33.

The only semantic input change is federation v33 replacing federation v31 and
open seed v73 replacing open seed v71. Rejected identity v7, federations
v29/v30, the definition-only federation v32 incident, and open seed v68 are
never lineage. Identity remains source-scoped: there are no implicit physical
site merges and all physical-site count fields remain null.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping

from . import exact_identity_decisions_v4 as accepted_v8
from . import federated_release_v3 as federation
from . import federation_v33
from .open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]

BUNDLE_ID = "2026-07-21-public-open-v9"
DEFINITION = ROOT / "sources/exact-identity-decisions-2026-07-21-public-open-v9.json"
BUNDLE = ROOT / "exact_identity_decisions/2026-07-21-public-open-v9"
PUBLICATION_LOCK = ROOT / ".exact-identity-v9.lock"

PREDECESSOR_DEFINITION = (
    ROOT / "sources/exact-identity-decisions-2026-07-21-public-open-v8.json"
)
PREDECESSOR_BUNDLE = ROOT / "exact_identity_decisions/2026-07-21-public-open-v8"
PREDECESSOR_DEFINITION_SHA256 = (
    "304144a09b1ec4773b662823501ac4a01505e2550d4a0270123fb20391980704"
)
PREDECESSOR_ACCOUNTING_SHA256 = (
    "f0102c137cf17a76994f94ac43c23c4f9b98963f956e295aaea16935a5d457fb"
)
PREDECESSOR_MANIFEST_SHA256 = (
    "63492e7fe633591577cdbb3f8c05c5097a52ac4f85190bdc532c869d5fe93401"
)
PREDECESSOR_TREE_SHA256 = (
    "607485d7106a06dd32f31f56fd2b5ca395f76e300b3a12b3c55ab533c1fa2b0f"
)

FEDERATION_DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v33.json"
FEDERATION_BUNDLE = ROOT / "federated_indexes/2026-07-21-public-open-v33"
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

V73_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v73.json"
V73_RELEASE = ROOT / "releases/2026-07-21-open-seed-v73"
V73_DEFINITION_SHA256 = (
    "cf8a4cfb8861ab732cdb9e72a01cbdd01d0e435102c47fd6d92bc30ebf11f97d"
)
V73_MANIFEST_SHA256 = (
    "229c572759ab493448b788946a0c8a61ff6995d0ab505bea2af08860a19e204d"
)
V73_TREE_SHA256 = (
    "692583b86324b746fd6edf0ec2dc5101efa86ce0f08e04831e0d471e767a6394"
)

OLD_RELEASE_ID = "epoch-official-open-seed-v71"
NEW_RELEASE_ID = "epoch-official-open-seed-v73"

EXPECTED_COUNTS = {
    "ambiguous_identity_candidate_references": 127,
    "canonical_topology_links": 2396,
    "exact_component_reductions": 1732,
    "exact_source_record_components": 8381,
    "non_review_source_scoped_entity_records": 10113,
    "raw_topology_links": 2801,
    "release_candidate_references": 100412,
    "review_only_source_scoped_entity_records": 6130,
    "source_scoped_entity_records": 16243,
    "unresolved_candidate_references": 100539,
}

REJECTED_LINEAGE_TOKENS = (
    b"2026-07-21-public-open-v7",
    b"2026-07-21-public-open-v29",
    b"2026-07-21-public-open-v30",
    b"2026-07-21-public-open-v32",
    b"epoch-official-open-seed-v68",
    b"2026-07-21-open-seed-v68",
)
SUPERSEDED_LINEAGE_TOKENS = (
    b"2026-07-21-public-open-v31",
    b"epoch-official-open-seed-v71",
)

legacy = accepted_v8.legacy
carrier = accepted_v8.carrier

ACCOUNTING_FILENAME = carrier.ACCOUNTING_FILENAME
ATTRIBUTION_FILENAME = carrier.ATTRIBUTION_FILENAME
BUNDLE_FILES = carrier.BUNDLE_FILES
BUNDLE_FORMAT = carrier.BUNDLE_FORMAT
COMPONENTS_FILENAME = carrier.COMPONENTS_FILENAME
DEFINITION_FORMAT = carrier.DEFINITION_FORMAT
LINEAGE_FILENAME = carrier.LINEAGE_FILENAME
MANIFEST_FILENAME = carrier.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = carrier.MANIFEST_HASH_FILENAME
POLICY = carrier.POLICY
README_FILENAME = carrier.README_FILENAME
RELATIONSHIPS_FILENAME = carrier.RELATIONSHIPS_FILENAME
UNRESOLVED_FILENAME = carrier.UNRESOLVED_FILENAME

ExactIdentityDecisionError = carrier.ExactIdentityDecisionError

_SHA256 = re.compile(r"[0-9a-f]{64}")


def _sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ExactIdentityDecisionError(f"pinned input must be a regular file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _wall_clock(value: datetime | None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ExactIdentityDecisionError(
            "identity validation wall clock must include a timezone"
        )
    return result.astimezone(timezone.utc)


def _parsed_timestamp(value: Any, label: str) -> datetime:
    text = legacy._timestamp(value, label)
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def _regular_document(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise ExactIdentityDecisionError(f"{label} must be a regular file")
    raw = path.read_bytes()
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExactIdentityDecisionError(f"{label} must be valid JSON") from error
    if not isinstance(document, dict) or raw != _canonical_json(document):
        raise ExactIdentityDecisionError(f"{label} must be canonical object JSON")
    return document, raw


def _require_configured_federation() -> None:
    pins = {
        "definition": FEDERATION_DEFINITION_SHA256,
        "index": FEDERATION_INDEX_SHA256,
        "manifest": FEDERATION_MANIFEST_SHA256,
        "tree": FEDERATION_TREE_SHA256,
    }
    invalid = [name for name, value in pins.items() if not _SHA256.fullmatch(value)]
    if invalid:
        raise ExactIdentityDecisionError(
            "federation v33 is not final-green; missing exact pins: "
            + ", ".join(invalid)
        )


def _guard_state() -> dict[str, str]:
    return {
        "predecessor_definition": _sha256(PREDECESSOR_DEFINITION),
        "predecessor_accounting": _sha256(
            PREDECESSOR_BUNDLE / ACCOUNTING_FILENAME
        ),
        "predecessor_manifest": _sha256(PREDECESSOR_BUNDLE / MANIFEST_FILENAME),
        "predecessor_tree": tree_digest(PREDECESSOR_BUNDLE),
        "federation_definition": _sha256(FEDERATION_DEFINITION),
        "federation_index": _sha256(FEDERATION_BUNDLE / "federated-index.json"),
        "federation_manifest": _sha256(FEDERATION_BUNDLE / MANIFEST_FILENAME),
        "federation_tree": tree_digest(FEDERATION_BUNDLE),
        "v73_definition": _sha256(V73_DEFINITION),
        "v73_manifest": _sha256(V73_RELEASE / MANIFEST_FILENAME),
        "v73_tree": tree_digest(V73_RELEASE),
    }


def _require_guard_state() -> dict[str, str]:
    _require_configured_federation()
    try:
        federation_v33.validate_federation_v33()
    except (OSError, federation_v33.FederationV33Error) as error:
        raise ExactIdentityDecisionError(
            f"accepted federation v33 validation failed: {error}"
        ) from error
    expected = {
        "predecessor_definition": PREDECESSOR_DEFINITION_SHA256,
        "predecessor_accounting": PREDECESSOR_ACCOUNTING_SHA256,
        "predecessor_manifest": PREDECESSOR_MANIFEST_SHA256,
        "predecessor_tree": PREDECESSOR_TREE_SHA256,
        "federation_definition": FEDERATION_DEFINITION_SHA256,
        "federation_index": FEDERATION_INDEX_SHA256,
        "federation_manifest": FEDERATION_MANIFEST_SHA256,
        "federation_tree": FEDERATION_TREE_SHA256,
        "v73_definition": V73_DEFINITION_SHA256,
        "v73_manifest": V73_MANIFEST_SHA256,
        "v73_tree": V73_TREE_SHA256,
    }
    actual = _guard_state()
    if actual != expected:
        differing = sorted(key for key in expected if actual.get(key) != expected[key])
        raise ExactIdentityDecisionError(
            "accepted identity-v9 input pin drift: " + ", ".join(differing)
        )
    return actual


def _v9_document(recorded_at: str) -> dict[str, Any]:
    predecessor, _ = _regular_document(
        PREDECESSOR_DEFINITION, "accepted identity v8 definition"
    )
    result = deepcopy(predecessor)
    result["bundle_id"] = BUNDLE_ID
    result["recorded_at"] = recorded_at
    result["federation"] = {
        "expected_index_sha256": FEDERATION_INDEX_SHA256,
        "expected_manifest_sha256": FEDERATION_MANIFEST_SHA256,
        "index_path": "../federated_indexes/2026-07-21-public-open-v33",
    }
    old_children = [
        child for child in result["children"] if child["release_id"] == OLD_RELEASE_ID
    ]
    if len(old_children) != 1:
        raise ExactIdentityDecisionError(
            "accepted identity v8 seed child contract changed"
        )
    old_children[0].update(
        {
            "expected_manifest_sha256": V73_MANIFEST_SHA256,
            "release_id": NEW_RELEASE_ID,
            "release_path": "../releases/2026-07-21-open-seed-v73",
        }
    )
    result["expected"] = dict(EXPECTED_COUNTS)
    return result


def _assert_forbidden_lineage_absent(payloads: Mapping[str, bytes]) -> None:
    for name, raw in payloads.items():
        for token in (*REJECTED_LINEAGE_TOKENS, *SUPERSEDED_LINEAGE_TOKENS):
            if token in raw:
                raise ExactIdentityDecisionError(
                    f"forbidden lineage token in identity v9 {name}: "
                    f"{token.decode('ascii')}"
                )


def _definition_object(
    document: Mapping[str, Any], raw: bytes, *, logical_path: Path = DEFINITION
) -> legacy._Definition:
    recorded_at = legacy._timestamp(
        document.get("recorded_at"), "identity v9 recorded_at"
    )
    expected_document = _v9_document(recorded_at)
    if document != expected_document or raw != _canonical_json(expected_document):
        raise ExactIdentityDecisionError(
            "identity v9 definition is not the exact accepted-v8 structural successor"
        )
    _assert_forbidden_lineage_absent({logical_path.name: raw})
    children = []
    for child in document["children"]:
        relative = Path(child["release_path"])
        if relative.is_absolute():
            raise ExactIdentityDecisionError("identity v9 child path must be relative")
        children.append(
            {
                **child,
                "release_path": (logical_path.parent / relative).resolve(),
            }
        )
    return legacy._Definition(
        path=logical_path.resolve(),
        raw=raw,
        bundle_id=BUNDLE_ID,
        recorded_at=recorded_at,
        federation=dict(document["federation"]),
        children=tuple(sorted(children, key=lambda item: item["release_id"])),
        expected=dict(EXPECTED_COUNTS),
    )


def _path_timestamp_bounds(path: Path, cutoff: datetime, label: str) -> None:
    if path.is_symlink() or not (path.is_file() or path.is_dir()):
        raise ExactIdentityDecisionError(f"{label} must be a regular artifact")
    status = path.stat()
    timestamps = [("mtime", status.st_mtime)]
    birth = getattr(status, "st_birthtime", None)
    if birth is not None:
        timestamps.append(("birth", birth))
    for kind, value in timestamps:
        observed = datetime.fromtimestamp(value, timezone.utc)
        if observed > cutoff + timedelta(microseconds=1):
            raise ExactIdentityDecisionError(
                f"{label} {kind} is after its recorded/generated timestamp"
            )


def _final_root_ctime(
    path: Path, cutoff: datetime, wall_clock: datetime, label: str
) -> None:
    changed = datetime.fromtimestamp(path.stat().st_ctime, timezone.utc)
    if changed < cutoff or changed > wall_clock + timedelta(microseconds=1):
        raise ExactIdentityDecisionError(
            f"{label} final root ctime is outside its publication boundary"
        )


def _validate_temporal_closure(
    definition_path: Path,
    bundle_path: Path,
    definition: legacy._Definition,
    *,
    validation_wall_clock: datetime,
) -> None:
    recorded = _parsed_timestamp(definition.recorded_at, "identity v9 recorded_at")
    if recorded > validation_wall_clock:
        raise ExactIdentityDecisionError(
            "identity v9 recorded_at exceeds validation wall clock"
        )
    for path in (definition_path, bundle_path, *bundle_path.rglob("*")):
        _path_timestamp_bounds(path, recorded, f"identity v9 artifact {path.name}")

    predecessor, _ = _regular_document(
        PREDECESSOR_DEFINITION, "accepted identity v8 definition"
    )
    predecessor_recorded = _parsed_timestamp(
        predecessor.get("recorded_at"), "identity v8 recorded_at"
    )
    if predecessor_recorded >= recorded:
        raise ExactIdentityDecisionError("identity v9 must follow accepted identity v8")
    for path in (
        PREDECESSOR_DEFINITION,
        PREDECESSOR_BUNDLE,
        *PREDECESSOR_BUNDLE.rglob("*"),
    ):
        _path_timestamp_bounds(
            path, predecessor_recorded, f"identity v8 artifact {path.name}"
        )

    federation_definition, _ = _regular_document(
        FEDERATION_DEFINITION, "accepted federation v33 definition"
    )
    federation_index, _ = _regular_document(
        FEDERATION_BUNDLE / "federated-index.json", "accepted federation v33 index"
    )
    generated = _parsed_timestamp(
        federation_definition.get("generated_at"), "federation v33 generated_at"
    )
    if federation_index.get("generated_at") != federation_definition.get(
        "generated_at"
    ):
        raise ExactIdentityDecisionError(
            "federation v33 definition and index generated_at differ"
        )
    if generated >= recorded or generated > validation_wall_clock:
        raise ExactIdentityDecisionError(
            "identity v9 must follow a non-future federation v33"
        )
    for path in (
        FEDERATION_DEFINITION,
        FEDERATION_BUNDLE,
        *FEDERATION_BUNDLE.rglob("*"),
    ):
        _path_timestamp_bounds(path, generated, f"federation v33 artifact {path.name}")
    _final_root_ctime(
        FEDERATION_DEFINITION,
        generated,
        validation_wall_clock,
        "federation v33 definition",
    )
    _final_root_ctime(
        FEDERATION_BUNDLE,
        generated,
        validation_wall_clock,
        "federation v33 bundle",
    )

    v73_manifest, _ = _regular_document(
        V73_RELEASE / MANIFEST_FILENAME, "accepted open-seed v73 manifest"
    )
    v73_recorded = _parsed_timestamp(
        v73_manifest.get("recorded_at"), "open-seed v73 recorded_at"
    )
    if v73_recorded >= generated:
        raise ExactIdentityDecisionError(
            "federation v33 must follow accepted open-seed v73"
        )
    for path in (V73_DEFINITION, V73_RELEASE, *V73_RELEASE.rglob("*")):
        _path_timestamp_bounds(path, v73_recorded, f"open-seed v73 artifact {path.name}")
    _final_root_ctime(
        V73_DEFINITION,
        v73_recorded,
        validation_wall_clock,
        "open-seed v73 definition",
    )
    _final_root_ctime(
        V73_RELEASE,
        v73_recorded,
        validation_wall_clock,
        "open-seed v73 release",
    )

    if (
        definition_path.absolute() == DEFINITION.absolute()
        and bundle_path.absolute() == BUNDLE.absolute()
    ):
        _final_root_ctime(
            definition_path, recorded, validation_wall_clock, "identity v9 definition"
        )
        _final_root_ctime(
            bundle_path, recorded, validation_wall_clock, "identity v9 bundle"
        )


def validate_exact_identity_decision_bundle(
    path_value: str | Path = BUNDLE,
    *,
    definition_path: str | Path = DEFINITION,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
) -> dict[str, Any]:
    """Validate v9 with two exact offline reconstructions and temporal closure."""

    if replay_count != 2:
        raise ExactIdentityDecisionError(
            "identity v9 requires exactly two offline reconstructions"
        )
    wall_clock = _wall_clock(validation_wall_clock)
    guard = _require_guard_state()
    definition_file = Path(definition_path)
    document, raw = _regular_document(definition_file, "identity v9 definition")
    definition = _definition_object(document, raw)
    bundle = Path(path_value)
    if bundle.is_symlink() or not bundle.is_dir():
        raise ExactIdentityDecisionError(
            "identity v9 bundle must be a regular directory"
        )
    _validate_temporal_closure(
        definition_file,
        bundle,
        definition,
        validation_wall_clock=wall_clock,
    )

    manifest = carrier.validate_exact_identity_decision_bundle(
        bundle, require_frozen=require_frozen
    )
    first_payloads, first_manifest = carrier._prepare_bundle(definition)
    second_payloads, second_manifest = carrier._prepare_bundle(definition)
    if first_payloads != second_payloads or first_manifest != second_manifest:
        raise ExactIdentityDecisionError(
            "identity v9 inputs changed or two offline reconstructions differ"
        )
    if manifest != first_manifest:
        raise ExactIdentityDecisionError("identity v9 manifest differs from replay")
    actual_payloads = {entry.name: entry.read_bytes() for entry in bundle.iterdir()}
    if actual_payloads != first_payloads:
        raise ExactIdentityDecisionError("identity v9 bundle differs from replay")
    counts = manifest.get("counts")
    if (
        manifest.get("bundle_id") != BUNDLE_ID
        or not isinstance(counts, Mapping)
        or any(counts.get(key) != value for key, value in EXPECTED_COUNTS.items())
    ):
        raise ExactIdentityDecisionError("identity v9 identity or counts differ")
    if manifest.get("scope") != POLICY or any(
        counts.get(field) is not None
        for field in (
            "unique_physical_sites",
            "physical_site_lower_bound",
            "physical_site_upper_bound",
        )
    ):
        raise ExactIdentityDecisionError(
            "identity v9 conservative identity policy differs"
        )
    _assert_forbidden_lineage_absent(
        {definition_file.name: raw, **actual_payloads}
    )
    if _guard_state() != guard:
        raise ExactIdentityDecisionError("identity v9 validation mutated inputs")
    return manifest


def _planned_publication_time(lead_seconds: int = 45) -> str:
    target = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(
        seconds=lead_seconds
    )
    return target.isoformat().replace("+00:00", "Z")


def _wait_until(recorded_at: str) -> None:
    target = _parsed_timestamp(recorded_at, "identity v9 recorded_at").timestamp()
    while time.time() < target:
        time.sleep(min(0.05, target - time.time()))


def _max_stage_time(paths: tuple[Path, ...]) -> float:
    values = []
    for root in paths:
        members = (root, *root.rglob("*")) if root.is_dir() else (root,)
        for path in members:
            status = path.stat()
            values.append(status.st_mtime)
            birth = getattr(status, "st_birthtime", None)
            if birth is not None:
                values.append(birth)
    return max(values)


def _discard_private_stage(stage: Path) -> None:
    if not stage.exists() or stage.is_symlink() or not stage.is_dir():
        return
    for entry in sorted(stage.rglob("*"), reverse=True):
        if entry.is_symlink():
            raise ExactIdentityDecisionError(
                "refusing contaminated identity-v9 stage cleanup"
            )
        entry.chmod(0o700 if entry.is_dir() else 0o600)
    stage.chmod(0o700)
    shutil.rmtree(stage)


@contextmanager
def publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise ExactIdentityDecisionError(
            f"active identity-v9 publication lock exists: {PUBLICATION_LOCK}"
        ) from error
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            PUBLICATION_LOCK.unlink()
        except FileNotFoundError:
            pass


def _require_unpublished() -> None:
    for path in (DEFINITION, BUNDLE):
        if path.exists() or path.is_symlink():
            raise ExactIdentityDecisionError(
                f"identity v9 final path already exists; refusing replacement: {path}"
            )


def _require_output_parents() -> None:
    for parent in (DEFINITION.parent, BUNDLE.parent):
        parent.mkdir(parents=True, exist_ok=True)
        if (
            parent.is_symlink()
            or not parent.is_dir()
            or not os.access(parent, os.W_OK | os.X_OK)
        ):
            raise ExactIdentityDecisionError(
                f"identity v9 output parent is invalid: {parent}"
            )


def _rollback_bundle(staged_bundle: Path) -> None:
    if staged_bundle.exists() or staged_bundle.is_symlink():
        raise ExactIdentityDecisionError(
            "identity v9 rollback destination is occupied"
        )
    BUNDLE.chmod(0o755)
    try:
        federation._promote_noreplace(BUNDLE, staged_bundle)
    except federation.FederatedReleaseError as error:
        raise ExactIdentityDecisionError(
            f"identity v9 bundle rollback failed: {error}"
        ) from error
    staged_bundle.chmod(0o555)


def write_exact_identity_decision_bundle() -> dict[str, Any]:
    """Stage, double-replay, freeze, and no-replace publish identity v9."""

    with publication_lock():
        guard = _require_guard_state()
        _require_unpublished()
        _require_output_parents()
        stage_root = Path(
            tempfile.mkdtemp(prefix=".identity-v9-private-stage-", dir=ROOT)
        )
        stage_root.chmod(0o700)
        definition_stage = stage_root / DEFINITION.name
        bundle_stage = stage_root / BUNDLE.name
        bundle_stage.mkdir(mode=0o700)
        try:
            recorded_at = _planned_publication_time()
            document = _v9_document(recorded_at)
            raw = _canonical_json(document)
            definition = _definition_object(document, raw)
            first_payloads, first_manifest = carrier._prepare_bundle(definition)
            second_payloads, second_manifest = carrier._prepare_bundle(definition)
            if first_payloads != second_payloads or first_manifest != second_manifest:
                raise ExactIdentityDecisionError(
                    "identity v9 inputs changed or two offline reconstructions differ"
                )
            _assert_forbidden_lineage_absent(
                {DEFINITION.name: raw, **first_payloads}
            )

            with definition_stage.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            for name, payload in first_payloads.items():
                with (bundle_stage / name).open("xb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
            legacy._fsync_directory(bundle_stage)
            definition_stage.chmod(0o444)
            for entry in bundle_stage.iterdir():
                entry.chmod(0o444)
            bundle_stage.chmod(0o555)
            legacy._fsync_directory(bundle_stage)

            target = _parsed_timestamp(
                recorded_at, "identity v9 recorded_at"
            ).timestamp()
            if _max_stage_time((definition_stage, bundle_stage)) > target + 0.000_001:
                raise ExactIdentityDecisionError(
                    "identity v9 staging exceeded planned publication timestamp"
                )
            staged_definition_sha = _sha256(definition_stage)
            staged_tree = tree_digest(bundle_stage)
            _wait_until(recorded_at)
            validate_exact_identity_decision_bundle(
                bundle_stage,
                definition_path=definition_stage,
                validation_wall_clock=datetime.now(timezone.utc),
            )
            if (
                _sha256(definition_stage) != staged_definition_sha
                or tree_digest(bundle_stage) != staged_tree
            ):
                raise ExactIdentityDecisionError(
                    "identity v9 private stage changed while waiting"
                )
            _require_unpublished()
            _require_output_parents()

            # macOS renamex_np(RENAME_EXCL) returns EACCES for a 0555 source
            # directory. The complete frozen tree was validated above; only
            # its root mode is opened for the atomic rename and immediately
            # restored at the final path. Every member remains mode 0444.
            bundle_stage.chmod(0o755)
            try:
                federation._promote_noreplace(bundle_stage, BUNDLE)
            except federation.FederatedReleaseError as error:
                raise ExactIdentityDecisionError(str(error)) from error
            try:
                BUNDLE.chmod(0o555)
                federation._promote_noreplace(definition_stage, DEFINITION)
            except federation.FederatedReleaseError as error:
                _rollback_bundle(bundle_stage)
                raise ExactIdentityDecisionError(str(error)) from error
            except Exception:
                _rollback_bundle(bundle_stage)
                raise
            result = validate_exact_identity_decision_bundle()
        finally:
            _discard_private_stage(stage_root)
        if _guard_state() != guard:
            raise ExactIdentityDecisionError("identity v9 publication mutated inputs")
        return result


build_exact_identity_decision_bundle = write_exact_identity_decision_bundle


__all__ = [
    "ACCOUNTING_FILENAME",
    "BUNDLE",
    "BUNDLE_FILES",
    "BUNDLE_FORMAT",
    "BUNDLE_ID",
    "COMPONENTS_FILENAME",
    "DEFINITION",
    "DEFINITION_FORMAT",
    "EXPECTED_COUNTS",
    "ExactIdentityDecisionError",
    "FEDERATION_BUNDLE",
    "FEDERATION_DEFINITION",
    "LINEAGE_FILENAME",
    "POLICY",
    "REJECTED_LINEAGE_TOKENS",
    "RELATIONSHIPS_FILENAME",
    "SUPERSEDED_LINEAGE_TOKENS",
    "UNRESOLVED_FILENAME",
    "build_exact_identity_decision_bundle",
    "validate_exact_identity_decision_bundle",
    "write_exact_identity_decision_bundle",
]
