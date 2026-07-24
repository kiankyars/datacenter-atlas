"""Publish exact-identity v11 over accepted v10 and fresh federation v35.

The only semantic input change is federation v35 replacing federation v34 and
open seed v86 replacing open seed v83. Rejected artifacts remain outside the
lineage, and all superseded federation/open-seed generations are absent.
Identity remains source-scoped: there are no implicit physical-site merges and
all physical-site count fields remain null.
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

from . import exact_identity_decisions_carrier_v4 as identity_carrier_v4
from . import exact_identity_decisions_v10 as accepted_v10
from . import federated_release_v4 as federation
from . import federation_v35
from .open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]

BUNDLE_ID = "2026-07-21-public-open-v11"
DEFINITION = ROOT / "sources/exact-identity-decisions-2026-07-21-public-open-v11.json"
BUNDLE = ROOT / "exact_identity_decisions/2026-07-21-public-open-v11"
PUBLICATION_LOCK = ROOT / ".exact-identity-v11.lock"

PREDECESSOR_DEFINITION = (
    ROOT / "sources/exact-identity-decisions-2026-07-21-public-open-v10.json"
)
PREDECESSOR_BUNDLE = ROOT / "exact_identity_decisions/2026-07-21-public-open-v10"
PREDECESSOR_DEFINITION_SHA256 = (
    "b68c6cd6f84405844b518dcf1aa421f86202c7d2f86c1325905333e5f281d78b"
)
PREDECESSOR_ACCOUNTING_SHA256 = (
    "fc9c2b08983b785b3f5792068dd9b80262f2fa1bbf6dd1496dd7a6cb73b45794"
)
PREDECESSOR_MANIFEST_SHA256 = (
    "5806448df1316aa56e4ba82a63961f5dd0b6337ee455de29929c369288a940fe"
)
PREDECESSOR_TREE_SHA256 = (
    "22363d1472487077386510c51ee373b15b2c1ee9f6343d80267f98ca4cd4a5fa"
)

FEDERATION_DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v35.json"
FEDERATION_BUNDLE = ROOT / "federated_indexes/2026-07-21-public-open-v35"
FEDERATION_DEFINITION_SHA256 = (
    "7c6f9c3d7892d86974b20ba694c24695c0a0d9a4fd91d830e9824ad2db49903f"
)
FEDERATION_INDEX_SHA256 = (
    "f7cf31d905bf497a6bc7ba3db7f22fb8e281e7b1452e1f2853ea79af1d9ea802"
)
FEDERATION_MANIFEST_SHA256 = (
    "7396e2854abd73f0209a02f13ab5b31fa79af6250059b92dff484442d61fe388"
)
FEDERATION_TREE_SHA256 = (
    "37bb03f650d2d57823fbc226c471866a4997711ef201440d10dbc4ef6c14f5ba"
)

V86_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v86.json"
V86_RELEASE = ROOT / "releases/2026-07-21-open-seed-v86"
V86_DEFINITION_SHA256 = (
    "2a2f0cded9e95efd2ab90cbde1d8ad11306b14f019f42cb14086fb80a63fb25d"
)
V86_MANIFEST_SHA256 = (
    "5bc24a692e2d4fc793192f03bd23fa921e434661a0675e6612370d354cf11488"
)
V86_TREE_SHA256 = (
    "593fe37f16cc81bd6e2011c9b893251be4041dc54376ffec2f743a510fb4d4de"
)

OLD_RELEASE_ID = "epoch-official-open-seed-v83"
NEW_RELEASE_ID = "epoch-official-open-seed-v86"

EXPECTED_COUNTS = {
    "ambiguous_identity_candidate_references": 127,
    "canonical_topology_links": 2451,
    "exact_component_reductions": 1732,
    "exact_source_record_components": 8490,
    "non_review_source_scoped_entity_records": 10222,
    "raw_topology_links": 2856,
    "release_candidate_references": 100414,
    "review_only_source_scoped_entity_records": 6130,
    "source_scoped_entity_records": 16352,
    "unresolved_candidate_references": 100541,
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
    b"2026-07-21-public-open-v33",
    b"2026-07-21-public-open-v34",
    b"epoch-official-open-seed-v71",
    b"epoch-official-open-seed-v73",
    b"epoch-official-open-seed-v83",
    b"2026-07-21-open-seed-v83",
)

legacy = accepted_v10.legacy
carrier = identity_carrier_v4

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
            "federation v35 is not final-green; missing exact pins: "
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
        "v86_definition": _sha256(V86_DEFINITION),
        "v86_manifest": _sha256(V86_RELEASE / MANIFEST_FILENAME),
        "v86_tree": tree_digest(V86_RELEASE),
    }


def _require_guard_state() -> dict[str, str]:
    _require_configured_federation()
    try:
        federation_v35.validate_federation_v35()
    except (OSError, federation_v35.FederationV35Error) as error:
        raise ExactIdentityDecisionError(
            f"accepted federation v35 validation failed: {error}"
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
        "v86_definition": V86_DEFINITION_SHA256,
        "v86_manifest": V86_MANIFEST_SHA256,
        "v86_tree": V86_TREE_SHA256,
    }
    actual = _guard_state()
    if actual != expected:
        differing = sorted(key for key in expected if actual.get(key) != expected[key])
        raise ExactIdentityDecisionError(
            "accepted identity-v11 input pin drift: " + ", ".join(differing)
        )
    return actual


def _v11_document(recorded_at: str) -> dict[str, Any]:
    predecessor, _ = _regular_document(
        PREDECESSOR_DEFINITION, "accepted identity v10 definition"
    )
    result = deepcopy(predecessor)
    result["bundle_id"] = BUNDLE_ID
    result["recorded_at"] = recorded_at
    result["federation"] = {
        "expected_index_sha256": FEDERATION_INDEX_SHA256,
        "expected_manifest_sha256": FEDERATION_MANIFEST_SHA256,
        "index_path": "../federated_indexes/2026-07-21-public-open-v35",
    }
    old_children = [
        child for child in result["children"] if child["release_id"] == OLD_RELEASE_ID
    ]
    if len(old_children) != 1:
        raise ExactIdentityDecisionError(
            "accepted identity v10 seed child contract changed"
        )
    old_children[0].update(
        {
            "expected_manifest_sha256": V86_MANIFEST_SHA256,
            "release_id": NEW_RELEASE_ID,
            "release_path": "../releases/2026-07-21-open-seed-v86",
        }
    )
    result["expected"] = dict(EXPECTED_COUNTS)
    return result


def _assert_forbidden_lineage_absent(payloads: Mapping[str, bytes]) -> None:
    for name, raw in payloads.items():
        for token in (*REJECTED_LINEAGE_TOKENS, *SUPERSEDED_LINEAGE_TOKENS):
            if token in raw:
                raise ExactIdentityDecisionError(
                    f"forbidden lineage token in identity v11 {name}: "
                    f"{token.decode('ascii')}"
                )


def _definition_object(
    document: Mapping[str, Any], raw: bytes, *, logical_path: Path = DEFINITION
) -> legacy._Definition:
    recorded_at = legacy._timestamp(
        document.get("recorded_at"), "identity v11 recorded_at"
    )
    expected_document = _v11_document(recorded_at)
    if document != expected_document or raw != _canonical_json(expected_document):
        raise ExactIdentityDecisionError(
            "identity v11 definition is not the exact accepted-v10 structural successor"
        )
    _assert_forbidden_lineage_absent({logical_path.name: raw})
    children = []
    for child in document["children"]:
        relative = Path(child["release_path"])
        if relative.is_absolute():
            raise ExactIdentityDecisionError("identity v11 child path must be relative")
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
    recorded = _parsed_timestamp(definition.recorded_at, "identity v11 recorded_at")
    if recorded > validation_wall_clock:
        raise ExactIdentityDecisionError(
            "identity v11 recorded_at exceeds validation wall clock"
        )
    for path in (definition_path, bundle_path, *bundle_path.rglob("*")):
        _path_timestamp_bounds(path, recorded, f"identity v11 artifact {path.name}")

    predecessor, _ = _regular_document(
        PREDECESSOR_DEFINITION, "accepted identity v10 definition"
    )
    predecessor_recorded = _parsed_timestamp(
        predecessor.get("recorded_at"), "identity v10 recorded_at"
    )
    if predecessor_recorded >= recorded:
        raise ExactIdentityDecisionError(
            "identity v11 must follow accepted identity v10"
        )
    for path in (
        PREDECESSOR_DEFINITION,
        PREDECESSOR_BUNDLE,
        *PREDECESSOR_BUNDLE.rglob("*"),
    ):
        _path_timestamp_bounds(
            path, predecessor_recorded, f"identity v10 artifact {path.name}"
        )

    federation_definition, _ = _regular_document(
        FEDERATION_DEFINITION, "accepted federation v35 definition"
    )
    federation_index, _ = _regular_document(
        FEDERATION_BUNDLE / "federated-index.json", "accepted federation v35 index"
    )
    generated = _parsed_timestamp(
        federation_definition.get("generated_at"), "federation v35 generated_at"
    )
    if federation_index.get("generated_at") != federation_definition.get(
        "generated_at"
    ):
        raise ExactIdentityDecisionError(
            "federation v35 definition and index generated_at differ"
        )
    if generated >= recorded or generated > validation_wall_clock:
        raise ExactIdentityDecisionError(
            "identity v11 must follow a non-future federation v35"
        )
    for path in (
        FEDERATION_DEFINITION,
        FEDERATION_BUNDLE,
        *FEDERATION_BUNDLE.rglob("*"),
    ):
        _path_timestamp_bounds(path, generated, f"federation v35 artifact {path.name}")
    _final_root_ctime(
        FEDERATION_DEFINITION,
        generated,
        validation_wall_clock,
        "federation v35 definition",
    )
    _final_root_ctime(
        FEDERATION_BUNDLE,
        generated,
        validation_wall_clock,
        "federation v35 bundle",
    )

    v86_manifest, _ = _regular_document(
        V86_RELEASE / MANIFEST_FILENAME, "accepted open-seed v86 manifest"
    )
    v86_recorded = _parsed_timestamp(
        v86_manifest.get("recorded_at"), "open-seed v86 recorded_at"
    )
    if v86_recorded >= generated:
        raise ExactIdentityDecisionError(
            "federation v35 must follow accepted open-seed v86"
        )
    for path in (V86_DEFINITION, V86_RELEASE, *V86_RELEASE.rglob("*")):
        _path_timestamp_bounds(path, v86_recorded, f"open-seed v86 artifact {path.name}")
    _final_root_ctime(
        V86_DEFINITION,
        v86_recorded,
        validation_wall_clock,
        "open-seed v86 definition",
    )
    _final_root_ctime(
        V86_RELEASE,
        v86_recorded,
        validation_wall_clock,
        "open-seed v86 release",
    )

    if (
        definition_path.absolute() == DEFINITION.absolute()
        and bundle_path.absolute() == BUNDLE.absolute()
    ):
        _final_root_ctime(
            definition_path, recorded, validation_wall_clock, "identity v11 definition"
        )
        _final_root_ctime(
            bundle_path, recorded, validation_wall_clock, "identity v11 bundle"
        )


def validate_exact_identity_decision_bundle(
    path_value: str | Path = BUNDLE,
    *,
    definition_path: str | Path = DEFINITION,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
) -> dict[str, Any]:
    """Validate v11 with two exact offline reconstructions and temporal closure."""

    if replay_count != 2:
        raise ExactIdentityDecisionError(
            "identity v11 requires exactly two offline reconstructions"
        )
    wall_clock = _wall_clock(validation_wall_clock)
    guard = _require_guard_state()
    definition_file = Path(definition_path)
    document, raw = _regular_document(definition_file, "identity v11 definition")
    definition = _definition_object(document, raw)
    bundle = Path(path_value)
    if bundle.is_symlink() or not bundle.is_dir():
        raise ExactIdentityDecisionError(
            "identity v11 bundle must be a regular directory"
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
            "identity v11 inputs changed or two offline reconstructions differ"
        )
    if manifest != first_manifest:
        raise ExactIdentityDecisionError("identity v11 manifest differs from replay")
    actual_payloads = {entry.name: entry.read_bytes() for entry in bundle.iterdir()}
    if actual_payloads != first_payloads:
        raise ExactIdentityDecisionError("identity v11 bundle differs from replay")
    counts = manifest.get("counts")
    if (
        manifest.get("bundle_id") != BUNDLE_ID
        or not isinstance(counts, Mapping)
        or any(counts.get(key) != value for key, value in EXPECTED_COUNTS.items())
    ):
        raise ExactIdentityDecisionError("identity v11 identity or counts differ")
    if manifest.get("scope") != POLICY or any(
        counts.get(field) is not None
        for field in (
            "unique_physical_sites",
            "physical_site_lower_bound",
            "physical_site_upper_bound",
        )
    ):
        raise ExactIdentityDecisionError(
            "identity v11 conservative identity policy differs"
        )
    _assert_forbidden_lineage_absent(
        {definition_file.name: raw, **actual_payloads}
    )
    if _guard_state() != guard:
        raise ExactIdentityDecisionError("identity v11 validation mutated inputs")
    return manifest


def _planned_publication_time(lead_seconds: int = 45) -> str:
    target = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(
        seconds=lead_seconds
    )
    return target.isoformat().replace("+00:00", "Z")


def _wait_until(recorded_at: str) -> None:
    target = _parsed_timestamp(recorded_at, "identity v11 recorded_at").timestamp()
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
                "refusing contaminated identity-v11 stage cleanup"
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
            f"active identity-v11 publication lock exists: {PUBLICATION_LOCK}"
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
                f"identity v11 final path already exists; refusing replacement: {path}"
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
                f"identity v11 output parent is invalid: {parent}"
            )


def _rollback_bundle(staged_bundle: Path) -> None:
    if staged_bundle.exists() or staged_bundle.is_symlink():
        raise ExactIdentityDecisionError(
            "identity v11 rollback destination is occupied"
        )
    BUNDLE.chmod(0o755)
    try:
        federation._promote_noreplace(BUNDLE, staged_bundle)
    except federation.FederatedReleaseError as error:
        raise ExactIdentityDecisionError(
            f"identity v11 bundle rollback failed: {error}"
        ) from error
    staged_bundle.chmod(0o555)


def write_exact_identity_decision_bundle() -> dict[str, Any]:
    """Stage, double-replay, freeze, and no-replace publish identity v11."""

    with publication_lock():
        guard = _require_guard_state()
        _require_unpublished()
        _require_output_parents()
        stage_root = Path(
            tempfile.mkdtemp(prefix=".identity-v11-private-stage-", dir=ROOT)
        )
        stage_root.chmod(0o700)
        definition_stage = stage_root / DEFINITION.name
        bundle_stage = stage_root / BUNDLE.name
        bundle_stage.mkdir(mode=0o700)
        try:
            recorded_at = _planned_publication_time()
            document = _v11_document(recorded_at)
            raw = _canonical_json(document)
            definition = _definition_object(document, raw)
            first_payloads, first_manifest = carrier._prepare_bundle(definition)
            second_payloads, second_manifest = carrier._prepare_bundle(definition)
            if first_payloads != second_payloads or first_manifest != second_manifest:
                raise ExactIdentityDecisionError(
                    "identity v11 inputs changed or two offline reconstructions differ"
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
                recorded_at, "identity v11 recorded_at"
            ).timestamp()
            if _max_stage_time((definition_stage, bundle_stage)) > target + 0.000_001:
                raise ExactIdentityDecisionError(
                    "identity v11 staging exceeded planned publication timestamp"
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
                    "identity v11 private stage changed while waiting"
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
            raise ExactIdentityDecisionError("identity v11 publication mutated inputs")
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
