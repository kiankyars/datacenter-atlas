"""Hardened exact-identity v8 publisher over accepted identity v6.

Identity v8 replaces only the accepted federation-v28/open-seed-v67 inputs
with accepted federation v31/open-seed v71. Rejected identity v7 and
federations v29/v30 are never lineage. The definition and bundle remain in
hidden sibling stages until the claimed publication instant is live.
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

from . import exact_identity_decisions as legacy
from . import exact_identity_decisions_v3 as carrier
from .open_seed_v56 import promote_noreplace, tree_digest


ROOT = Path(__file__).resolve().parents[1]

BUNDLE_ID = "2026-07-21-public-open-v8"
DEFINITION = ROOT / "sources/exact-identity-decisions-2026-07-21-public-open-v8.json"
BUNDLE = ROOT / "exact_identity_decisions/2026-07-21-public-open-v8"
PUBLICATION_LOCK = ROOT / ".exact-identity-v8.lock"

PREDECESSOR_DEFINITION = (
    ROOT / "sources/exact-identity-decisions-2026-07-21-public-open-v6.json"
)
PREDECESSOR_BUNDLE = ROOT / "exact_identity_decisions/2026-07-21-public-open-v6"
PREDECESSOR_DEFINITION_SHA256 = (
    "2b9b26f452ebfc3d36f4bb36d9cc7198a29b8be8806657750f440a928671d759"
)
PREDECESSOR_MANIFEST_SHA256 = (
    "0af1e65f5b772b87e7dfe5b5c195513e79f31d4b5648fdcae5fd343f86f82ee9"
)
PREDECESSOR_TREE_SHA256 = (
    "44057ef4e03b3ce4412fb4d89b7e673cf9da8a289eb13ecbca6e11dcb9a4505d"
)

FEDERATION_DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v31.json"
FEDERATION_BUNDLE = ROOT / "federated_indexes/2026-07-21-public-open-v31"
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

V71_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v71.json"
V71_RELEASE = ROOT / "releases/2026-07-21-open-seed-v71"
V71_DEFINITION_SHA256 = (
    "f5115fa57f32c8d9451609a662f6b524a15283b8e4fa1d9b65af59430d9e3b38"
)
V71_MANIFEST_SHA256 = (
    "0f8acbce360f763707cb4c51276a0873ee60ec96d9258b1915fa8c76fcf9fa22"
)
V71_TREE_SHA256 = (
    "7636964f1d640268ed8627d5f18d800a43a35a4d7dbc1f62b8386e60bd1fa720"
)

OLD_RELEASE_ID = "epoch-official-open-seed-v67"
NEW_RELEASE_ID = "epoch-official-open-seed-v71"

EXPECTED_COUNTS = {
    "ambiguous_identity_candidate_references": 127,
    "canonical_topology_links": 2392,
    "exact_component_reductions": 1732,
    "exact_source_record_components": 8373,
    "non_review_source_scoped_entity_records": 10105,
    "raw_topology_links": 2797,
    "release_candidate_references": 100411,
    "review_only_source_scoped_entity_records": 6130,
    "source_scoped_entity_records": 16235,
    "unresolved_candidate_references": 100538,
}

REJECTED_LINEAGE_TOKENS = (
    b"2026-07-21-public-open-v7",
    b"2026-07-21-public-open-v29",
    b"2026-07-21-public-open-v30",
    b"epoch-official-open-seed-v68",
    b"2026-07-21-open-seed-v68",
)

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
            "federation v31 is not final-green; missing exact pins: "
            + ", ".join(invalid)
        )


def _guard_state() -> dict[str, str]:
    return {
        "predecessor_definition": _sha256(PREDECESSOR_DEFINITION),
        "predecessor_manifest": _sha256(PREDECESSOR_BUNDLE / MANIFEST_FILENAME),
        "predecessor_tree": tree_digest(PREDECESSOR_BUNDLE),
        "federation_definition": _sha256(FEDERATION_DEFINITION),
        "federation_index": _sha256(FEDERATION_BUNDLE / "federated-index.json"),
        "federation_manifest": _sha256(FEDERATION_BUNDLE / MANIFEST_FILENAME),
        "federation_tree": tree_digest(FEDERATION_BUNDLE),
        "v71_definition": _sha256(V71_DEFINITION),
        "v71_manifest": _sha256(V71_RELEASE / MANIFEST_FILENAME),
        "v71_tree": tree_digest(V71_RELEASE),
    }


def _require_guard_state() -> dict[str, str]:
    _require_configured_federation()
    expected = {
        "predecessor_definition": PREDECESSOR_DEFINITION_SHA256,
        "predecessor_manifest": PREDECESSOR_MANIFEST_SHA256,
        "predecessor_tree": PREDECESSOR_TREE_SHA256,
        "federation_definition": FEDERATION_DEFINITION_SHA256,
        "federation_index": FEDERATION_INDEX_SHA256,
        "federation_manifest": FEDERATION_MANIFEST_SHA256,
        "federation_tree": FEDERATION_TREE_SHA256,
        "v71_definition": V71_DEFINITION_SHA256,
        "v71_manifest": V71_MANIFEST_SHA256,
        "v71_tree": V71_TREE_SHA256,
    }
    actual = _guard_state()
    if actual != expected:
        differing = sorted(key for key in expected if actual.get(key) != expected[key])
        raise ExactIdentityDecisionError(
            "accepted identity-v8 input pin drift: " + ", ".join(differing)
        )
    return actual


def _v8_document(recorded_at: str) -> dict[str, Any]:
    predecessor, _ = _regular_document(
        PREDECESSOR_DEFINITION, "accepted identity v6 definition"
    )
    result = deepcopy(predecessor)
    result["bundle_id"] = BUNDLE_ID
    result["recorded_at"] = recorded_at
    result["federation"] = {
        "expected_index_sha256": FEDERATION_INDEX_SHA256,
        "expected_manifest_sha256": FEDERATION_MANIFEST_SHA256,
        "index_path": "../federated_indexes/2026-07-21-public-open-v31",
    }
    old_children = [
        child for child in result["children"] if child["release_id"] == OLD_RELEASE_ID
    ]
    if len(old_children) != 1:
        raise ExactIdentityDecisionError(
            "accepted identity v6 seed child contract changed"
        )
    old_children[0].update(
        {
            "expected_manifest_sha256": V71_MANIFEST_SHA256,
            "release_id": NEW_RELEASE_ID,
            "release_path": "../releases/2026-07-21-open-seed-v71",
        }
    )
    result["expected"] = dict(EXPECTED_COUNTS)
    return result


def _assert_rejected_lineage_absent(payloads: Mapping[str, bytes]) -> None:
    for name, raw in payloads.items():
        for token in REJECTED_LINEAGE_TOKENS:
            if token in raw:
                raise ExactIdentityDecisionError(
                    f"rejected lineage token in identity v8 {name}: "
                    f"{token.decode('ascii')}"
                )


def _definition_object(
    document: Mapping[str, Any], raw: bytes, *, logical_path: Path = DEFINITION
) -> legacy._Definition:
    recorded_at = legacy._timestamp(
        document.get("recorded_at"), "identity v8 recorded_at"
    )
    expected_document = _v8_document(recorded_at)
    if document != expected_document or raw != _canonical_json(expected_document):
        raise ExactIdentityDecisionError(
            "identity v8 definition is not the exact accepted-v6 structural successor"
        )
    _assert_rejected_lineage_absent({logical_path.name: raw})
    children = []
    for child in document["children"]:
        relative = Path(child["release_path"])
        if relative.is_absolute():
            raise ExactIdentityDecisionError("identity v8 child path must be relative")
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


def _validate_temporal_closure(
    definition_path: Path,
    bundle_path: Path,
    definition: legacy._Definition,
    *,
    validation_wall_clock: datetime,
) -> None:
    recorded = _parsed_timestamp(definition.recorded_at, "identity v8 recorded_at")
    if recorded > validation_wall_clock:
        raise ExactIdentityDecisionError(
            "identity v8 recorded_at exceeds validation wall clock"
        )
    for path in (definition_path, bundle_path, *bundle_path.iterdir()):
        _path_timestamp_bounds(path, recorded, f"identity v8 artifact {path.name}")

    federation_definition, _ = _regular_document(
        FEDERATION_DEFINITION, "accepted federation v31 definition"
    )
    federation_index, _ = _regular_document(
        FEDERATION_BUNDLE / "federated-index.json", "accepted federation v31 index"
    )
    generated = _parsed_timestamp(
        federation_definition.get("generated_at"), "federation v31 generated_at"
    )
    if federation_index.get("generated_at") != federation_definition.get(
        "generated_at"
    ):
        raise ExactIdentityDecisionError(
            "federation v31 definition and index generated_at differ"
        )
    if generated >= recorded or generated > validation_wall_clock:
        raise ExactIdentityDecisionError(
            "identity v8 must follow a non-future federation v31"
        )
    for path in (
        FEDERATION_DEFINITION,
        FEDERATION_BUNDLE,
        *FEDERATION_BUNDLE.iterdir(),
    ):
        _path_timestamp_bounds(path, generated, f"federation v31 artifact {path.name}")

    v71_manifest, _ = _regular_document(
        V71_RELEASE / MANIFEST_FILENAME, "accepted open-seed v71 manifest"
    )
    v71_recorded = _parsed_timestamp(
        v71_manifest.get("recorded_at"), "open-seed v71 recorded_at"
    )
    if v71_recorded >= generated:
        raise ExactIdentityDecisionError(
            "federation v31 must follow accepted open-seed v71"
        )
    for path in (V71_DEFINITION, V71_RELEASE, *V71_RELEASE.iterdir()):
        _path_timestamp_bounds(
            path, v71_recorded, f"open-seed v71 artifact {path.name}"
        )


def validate_exact_identity_decision_bundle(
    path_value: str | Path = BUNDLE,
    *,
    definition_path: str | Path = DEFINITION,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
) -> dict[str, Any]:
    """Validate v8 with two exact offline reconstructions and temporal closure."""

    if replay_count != 2:
        raise ExactIdentityDecisionError(
            "identity v8 requires exactly two offline reconstructions"
        )
    wall_clock = _wall_clock(validation_wall_clock)
    guard = _require_guard_state()
    definition_file = Path(definition_path)
    document, raw = _regular_document(definition_file, "identity v8 definition")
    definition = _definition_object(document, raw)
    bundle = Path(path_value)
    if bundle.is_symlink() or not bundle.is_dir():
        raise ExactIdentityDecisionError(
            "identity v8 bundle must be a regular directory"
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
            "identity v8 inputs changed or two offline reconstructions differ"
        )
    if manifest != first_manifest:
        raise ExactIdentityDecisionError("identity v8 manifest differs from replay")
    actual_payloads = {entry.name: entry.read_bytes() for entry in bundle.iterdir()}
    if actual_payloads != first_payloads:
        raise ExactIdentityDecisionError("identity v8 bundle differs from replay")
    counts = manifest.get("counts")
    if (
        manifest.get("bundle_id") != BUNDLE_ID
        or not isinstance(counts, Mapping)
        or any(counts.get(key) != value for key, value in EXPECTED_COUNTS.items())
    ):
        raise ExactIdentityDecisionError("identity v8 identity or counts differ")
    if manifest.get("scope") != POLICY or any(
        counts.get(field) is not None
        for field in (
            "unique_physical_sites",
            "physical_site_lower_bound",
            "physical_site_upper_bound",
        )
    ):
        raise ExactIdentityDecisionError(
            "identity v8 conservative identity policy differs"
        )
    _assert_rejected_lineage_absent(
        {definition_file.name: raw, **actual_payloads}
    )
    if _guard_state() != guard:
        raise ExactIdentityDecisionError("identity v8 validation mutated inputs")
    return manifest


def _planned_publication_time(lead_seconds: int = 45) -> str:
    target = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(
        seconds=lead_seconds
    )
    return target.isoformat().replace("+00:00", "Z")


def _wait_until(recorded_at: str) -> None:
    target = _parsed_timestamp(recorded_at, "identity v8 recorded_at").timestamp()
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


def _discard_bundle_stage(stage: Path) -> None:
    if not stage.exists() or stage.is_symlink() or not stage.is_dir():
        return
    stage.chmod(0o700)
    for entry in stage.iterdir():
        if entry.is_symlink() or not entry.is_file():
            raise ExactIdentityDecisionError(
                "refusing contaminated identity-v8 stage cleanup"
            )
        entry.chmod(0o600)
    shutil.rmtree(stage)


@contextmanager
def publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise ExactIdentityDecisionError(
            f"active identity-v8 publication lock exists: {PUBLICATION_LOCK}"
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
                f"identity v8 final path already exists; refusing replacement: {path}"
            )


def write_exact_identity_decision_bundle() -> dict[str, Any]:
    """Stage, double-replay, freeze, and no-replace publish identity v8."""

    with publication_lock():
        guard = _require_guard_state()
        _require_unpublished()
        for parent in (DEFINITION.parent, BUNDLE.parent):
            parent.mkdir(parents=True, exist_ok=True)
            if parent.is_symlink() or not parent.is_dir():
                raise ExactIdentityDecisionError(
                    f"identity v8 output parent is invalid: {parent}"
                )

        bundle_stage = Path(
            tempfile.mkdtemp(prefix=f".{BUNDLE.name}.stage-", dir=BUNDLE.parent)
        )
        stage_name = (
            f".{DEFINITION.name}.stage-{os.getpid()}-{time.time_ns()}"
        )
        definition_stage = DEFINITION.parent / stage_name
        try:
            descriptor = os.open(
                definition_stage, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
        except FileExistsError as error:
            _discard_bundle_stage(bundle_stage)
            raise ExactIdentityDecisionError(
                f"identity v8 definition-stage collision: {definition_stage}"
            ) from error
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

        published_bundle = False
        try:
            recorded_at = _planned_publication_time()
            document = _v8_document(recorded_at)
            raw = _canonical_json(document)
            definition = _definition_object(document, raw)
            first_payloads, first_manifest = carrier._prepare_bundle(definition)
            second_payloads, second_manifest = carrier._prepare_bundle(definition)
            if first_payloads != second_payloads or first_manifest != second_manifest:
                raise ExactIdentityDecisionError(
                    "identity v8 inputs changed or two offline reconstructions differ"
                )
            _assert_rejected_lineage_absent(
                {DEFINITION.name: raw, **first_payloads}
            )

            with definition_stage.open("r+b") as stream:
                stream.write(raw)
                stream.truncate()
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
                recorded_at, "identity v8 recorded_at"
            ).timestamp()
            if _max_stage_time((definition_stage, bundle_stage)) > target + 0.000_001:
                raise ExactIdentityDecisionError(
                    "identity v8 staging exceeded planned publication timestamp"
                )
            _wait_until(recorded_at)
            validate_exact_identity_decision_bundle(
                bundle_stage,
                definition_path=definition_stage,
                validation_wall_clock=datetime.now(timezone.utc),
            )
            _require_unpublished()
            try:
                promote_noreplace(bundle_stage, BUNDLE)
            except SystemExit as error:
                raise ExactIdentityDecisionError(str(error)) from error
            published_bundle = True
            try:
                promote_noreplace(definition_stage, DEFINITION)
            except SystemExit as error:
                raise ExactIdentityDecisionError(str(error)) from error
            result = validate_exact_identity_decision_bundle()
        finally:
            if not published_bundle:
                _discard_bundle_stage(bundle_stage)
            try:
                definition_stage.unlink()
            except FileNotFoundError:
                pass
        if _guard_state() != guard:
            raise ExactIdentityDecisionError("identity v8 publication mutated inputs")
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
    "UNRESOLVED_FILENAME",
    "build_exact_identity_decision_bundle",
    "validate_exact_identity_decision_bundle",
    "write_exact_identity_decision_bundle",
]
