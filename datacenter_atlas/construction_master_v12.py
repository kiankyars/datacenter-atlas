"""Frozen v28 successor carrier for the role-preserving construction master.

The schema remains v2. This carrier byte-pins the accepted v27 carrier and
applies only the closed v67-to-v71 replacement-release/count transition. The
v14 base master and accepted Unknown033 recovery control plane remain exact.
No identity decision, satellite payload, or physical-site count is added.
"""

from __future__ import annotations

from contextlib import contextmanager as _v28_contextmanager
from copy import deepcopy as _v28_deepcopy
from datetime import datetime as _V28DateTime, timezone as _v28_timezone
import hashlib as _carrier_hashlib
import json as _v28_json
import os as _v28_os
from pathlib import Path as _CarrierPath
import shutil as _v28_shutil
import tempfile as _v28_tempfile
import time as _v28_time
from typing import Any as _V28Any, Iterator as _V28Iterator

from .open_seed_v56 import (
    promote_noreplace as _v28_promote_noreplace,
    tree_digest as _v28_tree_digest,
)


_BASE_SOURCE_SHA256 = "1ac853a00cd0279c56d14b767cadbe8a6e4e6df256d3ec6b73b4bcf3ff5b88af"
_BASE_SOURCE = _CarrierPath(__file__).with_name("construction_master_v11.py")


def _successor_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_master_v12 accepted-v27 boundary changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if _carrier_hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_master_v11 changed; refusing v28 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("construction_master_v11", "construction_master_v12", 2),
    ("ConstructionMasterV11Error", "ConstructionMasterV12Error", 1),
    ("is_frozen_master_v11", "is_frozen_master_v12", 1),
    ("v27", "v28", 4),
    ("V27", "V28", 1),
    ("v67", "v71", 3),
    ("V67", "V71", 1),
    ("2026-07-21T08:05:00Z", "2026-07-21T10:56:30Z", 1),
    ('added_replacement_rows": 202', 'added_replacement_rows": 217', 1),
    ('replacement_rows": 401', 'replacement_rows": 416', 1),
    (
        'replacement_rows_with_any_role": 142',
        'replacement_rows_with_any_role": 145',
        1,
    ),
    (
        'replacement_rows_with_source_role_tags' + ("\\" * 16) + '": 103',
        'replacement_rows_with_source_role_tags' + ("\\" * 16) + '": 106',
        1,
    ),
    ('rows_with_contract_marker": 401', 'rows_with_contract_marker": 416', 1),
    ('tier_a_rows": 521', 'tier_a_rows": 536', 1),
    ('total_rows": 109_313', 'total_rows": 109_328', 1),
    (
        'construction_pipeline_records") != 401',
        'construction_pipeline_records") != 416',
        1,
    ),
    ('added_rows": 202', 'added_rows": 217', 1),
    ("109,313", "109,328", 1),
    ("521 Tier A", "536 Tier A", 1),
    ("401-row", "416-row", 1),
):
    _source = _successor_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())

globals()["MASTER_ID"] = "2026-07-21-public-open-v28"
globals()["REPLACEMENT_DEFINITION_RELEASE_ID"] = "2026-07-21-open-seed-v71"
globals()["EXPECTED_FIXED"].update(
    {
        "replacement_rows_with_operator": 59,
        "replacement_rows_with_owner": 48,
        "replacement_rows_with_tenants": 7,
    }
)


# The accepted v27 implementation remains the executable carrier. Federation,
# exact-identity, and timeline artifacts are checkpoint gates only: they do not
# add, merge, reclassify, or appear as provenance for master rows.
ROOT = _CarrierPath(__file__).resolve().parents[1]
DEFINITION_RELATIVE_PATH = "sources/construction-master-2026-07-21-public-open-v28.json"
BUNDLE_RELATIVE_PATH = "construction_master/2026-07-21-public-open-v28"
DEFINITION_PATH = ROOT / DEFINITION_RELATIVE_PATH
BUNDLE_PATH = ROOT / BUNDLE_RELATIVE_PATH
PUBLICATION_LOCK = ROOT / ".construction-master-v28.lock"
PREPARATION_GENERATED_AT = "2099-01-01T00:00:00Z"

EXPECTED_DIGESTS = {
    "added_source_record_ids_sha256": (
        "3095a75223675a90e1c654b107bef1f8e29bce43505dc66572e72f93233869ea"
    ),
    "base_replaced_source_record_ids_sha256": (
        "f9801441dab6df464741d53f7bfc4e9c664b860e66a5de6797eeef8c82ca1950"
    ),
    "inherited_rows_without_roles_sha256": (
        "d6580ceaad528c3a6a489eb568368e7109a0488dfa4425bbe100dc0f1f13ac3f"
    ),
    "replacement_role_projection_sha256": (
        "9c566f52b2b9ca3c895b6669454924717424df17d09c03a637ab0e79794eaf08"
    ),
    "replacement_rows_without_roles_sha256": (
        "6adb69e298ec760b996d34d801e53e406fb04de23bdfea6062c660630e89a9c0"
    ),
    "replacement_source_record_ids_sha256": (
        "6ab7fd97029c5fa613f037608cc238186ec0198156efd2227132a0234d332b67"
    ),
    "tier_a_arithmetic_projection_sha256": (
        "51398b146ebb1cb6f8f68e3a1804639a47609aec198a8e4ecf40faac18d31b06"
    ),
}

PREDECESSOR_DEFINITION = {
    "bytes": 5659,
    "path": "sources/construction-master-2026-07-21-public-open-v27.json",
    "sha256": "c0f2a5c89e44838da876d7629dc39f49bdaa497d882a2826fff92e6e7080198b",
}
PREDECESSOR_MANIFEST = {
    "bytes": 9720,
    "path": "construction_master/2026-07-21-public-open-v27/manifest.json",
    "sha256": "6a5f48a0c86220c66d13fc1bd0ec7a9716e624d3d952599e3b6660e07717f5e7",
}
REPLACEMENT_INPUTS = {
    "artifact_id": "epoch-official-open-seed-v71",
    "data": {
        "bytes": 531171,
        "path": "releases/2026-07-21-open-seed-v71/construction_pipeline.csv",
        "sha256": "2973f164b2e19b3f816fef7c5d6dddfb41922978bd1b28f1bab54c162907db32",
    },
    "definition": {
        "bytes": 86839,
        "path": "sources/open-seed-2026-07-21-v71.json",
        "sha256": "f5115fa57f32c8d9451609a662f6b524a15283b8e4fa1d9b65af59430d9e3b38",
    },
    "evidence": {
        "bytes": 201471,
        "path": "releases/2026-07-21-open-seed-v71/evidence.csv",
        "sha256": "62bae2503599cc65fad1945dee28985b202c2c4bab60751af6bfd4a8a7b626dd",
    },
    "manifest": {
        "bytes": 12577,
        "path": "releases/2026-07-21-open-seed-v71/manifest.json",
        "sha256": "0f8acbce360f763707cb4c51276a0873ee60ec96d9258b1915fa8c76fcf9fa22",
    },
    "publication_contract_version": 4,
    "release_id": "epoch-official-open-seed-v71",
}

ACCEPTED_DEPENDENCY_CLOSURE = {
    "federation_v31": {
        "artifact_id": "2026-07-21-public-open-v31",
        "definition": {
            "bytes": 1788,
            "path": "sources/federation-2026-07-21-public-open-v31.json",
            "sha256": "83a878ee72563e6572a53cf09236c0af469e629bc04482401d6891b54d108ee1",
        },
        "manifest": {
            "bytes": 986,
            "path": "federated_indexes/2026-07-21-public-open-v31/manifest.json",
            "sha256": "7adc941dd73fa33315322ce19ff9c9887cdc2fb80cbd0aca3385a1c005781101",
        },
        "tree": {
            "path": "federated_indexes/2026-07-21-public-open-v31",
            "sha256": "978b1a574071f0128538aafee4503436fd0ae95284a60e236b0ee9065834f55c",
        },
    },
    "identity_v8": {
        "artifact_id": "2026-07-21-public-open-v8",
        "definition": {
            "bytes": 1735,
            "path": "sources/exact-identity-decisions-2026-07-21-public-open-v8.json",
            "sha256": "304144a09b1ec4773b662823501ac4a01505e2550d4a0270123fb20391980704",
        },
        "manifest": {
            "bytes": 11438,
            "path": "exact_identity_decisions/2026-07-21-public-open-v8/manifest.json",
            "sha256": "63492e7fe633591577cdbb3f8c05c5097a52ac4f85190bdc532c869d5fe93401",
        },
        "tree": {
            "path": "exact_identity_decisions/2026-07-21-public-open-v8",
            "sha256": "607485d7106a06dd32f31f56fd2b5ca395f76e300b3a12b3c55ab533c1fa2b0f",
        },
    },
    "open_seed_v71": {
        "artifact_id": "2026-07-21-open-seed-v71",
        "definition": _v28_deepcopy(REPLACEMENT_INPUTS["definition"]),
        "manifest": _v28_deepcopy(REPLACEMENT_INPUTS["manifest"]),
        "tree": {
            "path": "releases/2026-07-21-open-seed-v71",
            "sha256": "7636964f1d640268ed8627d5f18d800a43a35a4d7dbc1f62b8386e60bd1fa720",
        },
    },
    "predecessor_master_v27": {
        "artifact_id": "2026-07-21-public-open-v27",
        "definition": _v28_deepcopy(PREDECESSOR_DEFINITION),
        "manifest": _v28_deepcopy(PREDECESSOR_MANIFEST),
        "tree": {
            "path": "construction_master/2026-07-21-public-open-v27",
            "sha256": "15f5a8c5630faa28c45c7aaa4cb4cd212b472441db4c9e3a9daf80fb23bc25a9",
        },
    },
    "timeline_v5": {
        "artifact_id": "2026-07-21-public-open-v5",
        "definition": {
            "bytes": 2676,
            "path": "sources/construction-timeline-2026-07-21-public-open-v5.json",
            "sha256": "f70f520e3ab887f0efea717c6850cb05dc26ce9b6b0697f96e0e6a9b8670a739",
        },
        "manifest": {
            "bytes": 3632,
            "path": "construction_timelines/2026-07-21-public-open-v5/manifest.json",
            "sha256": "aa378cde74d50b6016c5cd040a32a24e044489c0eb0fe9b412450d8abb038dba",
        },
        "tree": {
            "path": "construction_timelines/2026-07-21-public-open-v5",
            "sha256": "06ea50e5675c9931459fff09fd8bcfab92ebc3c0d9346fd5f5564fa65fa9641d",
        },
    },
}

_v28_carrier_validate_definition = globals()["validate_definition"]
_v28_carrier_write = globals()["write_construction_master_v12"]


def _v28_error(message: str) -> Exception:
    return globals()["ConstructionMasterV12Error"](message)


def _v28_resolve(relative: str, label: str) -> _CarrierPath:
    if not relative or "\\" in relative:
        raise _v28_error(f"{label} path is invalid")
    candidate = _CarrierPath(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise _v28_error(f"{label} path escapes the package")
    resolved = (ROOT / candidate).resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as error:
        raise _v28_error(f"{label} path escapes the package") from error
    return resolved


def _v28_validate_checkpoint(checkpoint: dict[str, _V28Any], label: str) -> None:
    if set(checkpoint) != {"bytes", "path", "sha256"}:
        raise _v28_error(f"{label} checkpoint schema changed")
    path = _v28_resolve(str(checkpoint["path"]), label)
    if path.is_symlink() or not path.is_file():
        raise _v28_error(f"{label} must be a regular file")
    if globals()["_checkpoint"](path) != {
        "bytes": checkpoint["bytes"],
        "sha256": checkpoint["sha256"],
    }:
        raise _v28_error(f"accepted dependency changed: {checkpoint['path']}")


def validate_dependency_closure_v28() -> None:
    """Fail closed unless every accepted definition, manifest, and tree is exact."""

    expected_lanes = {
        "federation_v31",
        "identity_v8",
        "open_seed_v71",
        "predecessor_master_v27",
        "timeline_v5",
    }
    if set(ACCEPTED_DEPENDENCY_CLOSURE) != expected_lanes:
        raise _v28_error("accepted dependency lane set changed")
    for lane_name in sorted(expected_lanes):
        lane = ACCEPTED_DEPENDENCY_CLOSURE[lane_name]
        if set(lane) != {"artifact_id", "definition", "manifest", "tree"}:
            raise _v28_error(f"{lane_name} dependency schema changed")
        _v28_validate_checkpoint(lane["definition"], f"{lane_name} definition")
        _v28_validate_checkpoint(lane["manifest"], f"{lane_name} manifest")
        tree = lane["tree"]
        if set(tree) != {"path", "sha256"}:
            raise _v28_error(f"{lane_name} tree checkpoint schema changed")
        directory = _v28_resolve(str(tree["path"]), f"{lane_name} tree")
        if directory.is_symlink() or not directory.is_dir():
            raise _v28_error(f"{lane_name} tree must be a regular directory")
        try:
            observed = _v28_tree_digest(directory)
        except SystemExit as error:
            raise _v28_error(f"{lane_name} tree is unsafe: {error}") from error
        if observed != tree["sha256"]:
            raise _v28_error(f"accepted dependency tree changed: {tree['path']}")


def construction_master_v28_definition() -> dict[str, _V28Any]:
    """Derive the v28 definition from the byte-pinned accepted v27 definition."""

    validate_dependency_closure_v28()
    predecessor_path = _v28_resolve(
        PREDECESSOR_DEFINITION["path"], "predecessor definition"
    )
    predecessor_raw = predecessor_path.read_bytes()
    if globals()["_checkpoint"](predecessor_path) != {
        "bytes": PREDECESSOR_DEFINITION["bytes"],
        "sha256": PREDECESSOR_DEFINITION["sha256"],
    }:
        raise _v28_error("accepted v27 definition changed")
    try:
        document = _v28_json.loads(predecessor_raw)
    except (UnicodeDecodeError, _v28_json.JSONDecodeError) as error:
        raise _v28_error("accepted v27 definition is invalid JSON") from error
    if predecessor_raw != globals()["_canonical_json"](document):
        raise _v28_error("accepted v27 definition is not canonical")
    document["expected"] = {
        **globals()["EXPECTED_FIXED"],
        **EXPECTED_DIGESTS,
    }
    document["generated_at"] = globals()["GENERATED_AT"]
    document["inputs"]["replacement_release"] = _v28_deepcopy(REPLACEMENT_INPUTS)
    document["master_id"] = globals()["MASTER_ID"]
    document["scope"] = _v28_deepcopy(globals()["SCOPE_POLICY"])
    return document


def construction_master_v28_definition_bytes() -> bytes:
    return globals()["_canonical_json"](construction_master_v28_definition())


def validate_definition(
    definition_path: str | _CarrierPath,
) -> tuple[
    dict[str, _V28Any],
    bytes,
    _CarrierPath,
    dict[str, _CarrierPath],
    dict[str, _V28Any],
]:
    """Validate the exact derived v28 definition and its accepted closure."""

    result = _v28_carrier_validate_definition(definition_path)
    document, raw, _package_root, _resolved, _context = result
    if raw != construction_master_v28_definition_bytes():
        raise _v28_error("v28 definition differs from its accepted v27 derivation")
    return result


def _v28_rebind_manifest(bundle: _CarrierPath, definition_raw: bytes) -> dict[str, _V28Any]:
    manifest_path = bundle / globals()["MANIFEST_FILENAME"]
    sidecar_path = bundle / globals()["MANIFEST_HASH_FILENAME"]
    manifest = _v28_json.loads(manifest_path.read_bytes())
    manifest["definition"] = {
        "bytes": len(definition_raw),
        "path": DEFINITION_RELATIVE_PATH,
        "sha256": globals()["_sha256"](definition_raw),
    }
    manifest_raw = globals()["_canonical_json"](manifest)
    manifest_path.write_bytes(manifest_raw)
    sidecar_path.write_bytes(
        (
            f"{globals()['_sha256'](manifest_raw)}  "
            f"{globals()['MANIFEST_FILENAME']}\n"
        ).encode("ascii")
    )
    for path in (manifest_path, sidecar_path):
        with path.open("rb") as source:
            _v28_os.fsync(source.fileno())
    return manifest


def _v28_freeze_bundle(bundle: _CarrierPath) -> None:
    for entry in bundle.iterdir():
        entry.chmod(0o444)
    bundle.chmod(0o555)


def _v28_unfreeze_private_tree(root: _CarrierPath) -> None:
    if root.is_symlink() or not root.exists():
        return
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_symlink():
            continue
        path.chmod(0o755 if path.is_dir() else 0o644)
    root.chmod(0o755)


def _v28_discard_private_transaction(transaction: _CarrierPath) -> None:
    if (
        transaction.parent != ROOT
        or not transaction.name.startswith(".construction-master-v28.transaction-")
    ):
        raise _v28_error(f"refusing unsafe private-stage cleanup: {transaction}")
    if transaction.exists() and not transaction.is_symlink():
        _v28_unfreeze_private_tree(transaction)
        _v28_shutil.rmtree(transaction)


def _v28_build_candidate(
    definition_path: _CarrierPath,
    candidate: _CarrierPath,
    *,
    freeze: bool,
) -> dict[str, _V28Any]:
    definition_raw = definition_path.read_bytes()
    manifest = _v28_carrier_write(definition_path, candidate, freeze=False)
    manifest = _v28_rebind_manifest(candidate, definition_raw)
    globals()["_validate_static"](candidate, frozen=False)
    if freeze:
        _v28_freeze_bundle(candidate)
        globals()["_validate_static"](candidate, frozen=True)
    return manifest


def _v28_destination_absent(path: _CarrierPath, label: str) -> None:
    if path.exists() or path.is_symlink():
        raise _v28_error(f"refusing existing {label}: {path}")


def write_construction_master_v12(
    definition_path: str | _CarrierPath,
    output_directory: str | _CarrierPath,
    *,
    freeze: bool = False,
) -> dict[str, _V28Any]:
    """Build v28 through a hidden stage and publish with atomic no-replace."""

    definition = _CarrierPath(definition_path)
    destination = _CarrierPath(
        _v28_os.path.abspath(_v28_os.fspath(output_directory))
    )
    _v28_destination_absent(destination, "output")
    destination.parent.mkdir(parents=True, exist_ok=True)
    transaction = _CarrierPath(
        _v28_tempfile.mkdtemp(
            prefix=f".{destination.name}.v28-transaction-", dir=destination.parent
        )
    )
    promoted = False
    try:
        candidate = transaction / "bundle"
        manifest = _v28_build_candidate(definition, candidate, freeze=freeze)
        _v28_destination_absent(destination, "late output")
        if freeze:
            # Darwin renamex_np(RENAME_EXCL) rejects a 0555 source directory.
            # Keep every payload file 0444, open only the directory mode for
            # the atomic namespace move, then close it immediately at final.
            candidate.chmod(0o755)
        _v28_promote_noreplace(candidate, destination)
        promoted = True
        if freeze:
            destination.chmod(0o555)
        transaction.rmdir()
        return manifest
    finally:
        if transaction.exists() and not promoted:
            _v28_unfreeze_private_tree(transaction)
            _v28_shutil.rmtree(transaction)


def validate_construction_master_v12(
    directory: str | _CarrierPath,
    *,
    definition_path: str | _CarrierPath,
    reproduce: bool = True,
) -> dict[str, _V28Any]:
    """Validate the v28 bundle, closure, final-path binding, and offline replay."""

    root = _CarrierPath(directory)
    manifest = globals()["_validate_static"](root, frozen=True)
    _document, raw, _package_root, _resolved, _context = validate_definition(
        definition_path
    )
    if manifest.get("definition") != {
        "bytes": len(raw),
        "path": DEFINITION_RELATIVE_PATH,
        "sha256": globals()["_sha256"](raw),
    }:
        raise _v28_error("v28 manifest definition binding changed")
    if reproduce:
        with _v28_tempfile.TemporaryDirectory(
            prefix="construction-master-v28-reproduce-"
        ) as temporary:
            rebuilt = _CarrierPath(temporary) / "bundle"
            write_construction_master_v12(definition_path, rebuilt, freeze=True)
            for name in sorted(globals()["BUNDLE_FILES"]):
                if globals()["_checkpoint"](root / name) != globals()["_checkpoint"](
                    rebuilt / name
                ):
                    raise _v28_error(
                        f"v28 output differs from offline reproduction: {name}"
                    )
    return manifest


def prepare_construction_master_v28() -> tuple[_CarrierPath, _CarrierPath, _CarrierPath]:
    """Build a frozen private candidate while leaving both public paths absent."""

    _v28_destination_absent(DEFINITION_PATH, "v28 definition")
    _v28_destination_absent(BUNDLE_PATH, "v28 bundle")
    transaction = _CarrierPath(
        _v28_tempfile.mkdtemp(
            prefix=".construction-master-v28.transaction-", dir=ROOT
        )
    )
    definition_stage = transaction / DEFINITION_PATH.name
    bundle_stage = transaction / "bundle"
    try:
        definition_raw = construction_master_v28_definition_bytes()
        with definition_stage.open("xb") as output:
            output.write(definition_raw)
            output.flush()
            _v28_os.fsync(output.fileno())
        _v28_build_candidate(definition_stage, bundle_stage, freeze=True)
        definition_stage.chmod(0o444)
        validate_construction_master_v12(
            bundle_stage, definition_path=definition_stage, reproduce=False
        )
        _v28_destination_absent(DEFINITION_PATH, "late v28 definition")
        _v28_destination_absent(BUNDLE_PATH, "late v28 bundle")
        return transaction, definition_stage, bundle_stage
    except BaseException:
        _v28_discard_private_transaction(transaction)
        raise


def discard_construction_master_v28_stage(transaction: str | _CarrierPath) -> None:
    """Discard only a private v28 transaction that has not been published."""

    path = _CarrierPath(transaction).resolve()
    if DEFINITION_PATH.exists() or BUNDLE_PATH.exists():
        raise _v28_error("refusing stage cleanup after a v28 final path appeared")
    _v28_discard_private_transaction(path)


def _v28_generated_epoch() -> float:
    value = globals()["GENERATED_AT"]
    try:
        parsed = _V28DateTime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise _v28_error("v28 generated_at is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() != _v28_timezone.utc.utcoffset(parsed):
        raise _v28_error("v28 generated_at must be UTC")
    return parsed.timestamp()


def _v28_configured_publication_epoch() -> float:
    if globals()["GENERATED_AT"] == PREPARATION_GENERATED_AT:
        raise _v28_error("v28 remains preparation-only; publication timestamp unset")
    return _v28_generated_epoch()


def _v28_assert_live_publication_time(generated_epoch: float) -> None:
    if _v28_time.time() < generated_epoch:
        raise _v28_error("live clock is earlier than v28 generated_at")


def _v28_stage_paths(
    transaction: _CarrierPath,
    definition_stage: _CarrierPath,
    bundle_stage: _CarrierPath,
) -> tuple[_CarrierPath, ...]:
    return (
        transaction,
        definition_stage,
        bundle_stage,
        *sorted(bundle_stage.iterdir()),
    )


def _v28_assert_stage_precedes_target(
    paths: tuple[_CarrierPath, ...], generated_epoch: float
) -> None:
    for path in paths:
        metadata = path.stat()
        birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if max(birth, metadata.st_mtime) > generated_epoch + 0.000_001:
            raise _v28_error(
                f"v28 private stage exceeds generated_at: {path.name}"
            )


def _v28_wait_until(generated_epoch: float) -> None:
    while True:
        remaining = generated_epoch - _v28_time.time()
        if remaining <= 0:
            return
        _v28_time.sleep(min(remaining, 0.25))


@_v28_contextmanager
def _v28_publication_lock() -> _V28Iterator[None]:
    try:
        descriptor = _v28_os.open(
            PUBLICATION_LOCK,
            _v28_os.O_CREAT | _v28_os.O_EXCL | _v28_os.O_WRONLY,
            0o600,
        )
    except FileExistsError as error:
        raise _v28_error(f"active v28 publication lock exists: {PUBLICATION_LOCK}") from error
    try:
        _v28_os.write(descriptor, f"pid={_v28_os.getpid()}\n".encode("ascii"))
        _v28_os.fsync(descriptor)
        yield
    finally:
        _v28_os.close(descriptor)
        try:
            PUBLICATION_LOCK.unlink()
        except FileNotFoundError:
            pass


def publish_construction_master_v28() -> dict[str, _V28Any]:
    """Publish bundle then definition-as-commit-marker with true no-replace."""

    with _v28_publication_lock():
        _v28_destination_absent(DEFINITION_PATH, "v28 definition")
        _v28_destination_absent(BUNDLE_PATH, "v28 bundle")
        generated_epoch = _v28_configured_publication_epoch()
        transaction, definition_stage, bundle_stage = prepare_construction_master_v28()
        promoted = False
        try:
            validate_construction_master_v12(
                bundle_stage, definition_path=definition_stage, reproduce=True
            )
            stage_paths = _v28_stage_paths(
                transaction, definition_stage, bundle_stage
            )
            _v28_assert_stage_precedes_target(stage_paths, generated_epoch)
            staged_definition_checkpoint = globals()["_checkpoint"](definition_stage)
            staged_tree = _v28_tree_digest(bundle_stage)
            _v28_destination_absent(DEFINITION_PATH, "pre-wait v28 definition")
            _v28_destination_absent(BUNDLE_PATH, "pre-wait v28 bundle")
            _v28_wait_until(generated_epoch)
            _v28_assert_live_publication_time(generated_epoch)
            validate_construction_master_v12(
                bundle_stage, definition_path=definition_stage, reproduce=False
            )
            if (
                globals()["_checkpoint"](definition_stage)
                != staged_definition_checkpoint
                or _v28_tree_digest(bundle_stage) != staged_tree
            ):
                raise _v28_error("v28 private stage changed while awaiting publication")
            _v28_destination_absent(DEFINITION_PATH, "late v28 definition")
            _v28_destination_absent(BUNDLE_PATH, "late v28 bundle")
            # See write_construction_master_v12: Darwin needs owner-write on
            # the directory inode for RENAME_EXCL, while files remain 0444.
            bundle_stage.chmod(0o755)
            _v28_promote_noreplace(bundle_stage, BUNDLE_PATH)
            BUNDLE_PATH.chmod(0o555)
            _v28_promote_noreplace(definition_stage, DEFINITION_PATH)
            for final in (BUNDLE_PATH, DEFINITION_PATH):
                if final.stat().st_ctime < generated_epoch:
                    raise _v28_error(
                        f"v28 final rename predates generated_at: {final.name}"
                    )
            promoted = True
            transaction.rmdir()
        except BaseException:
            # Once either final appears, retain every remaining stage byte as
            # incident evidence. Before that point, remove only our private tx.
            if not DEFINITION_PATH.exists() and not BUNDLE_PATH.exists():
                _v28_discard_private_transaction(transaction)
            raise
        if not promoted:  # pragma: no cover - defensive, all failures raise
            raise _v28_error("v28 publication did not complete")
    return validate_construction_master_v12(
        BUNDLE_PATH, definition_path=DEFINITION_PATH, reproduce=False
    )


__all__ = [  # noqa: F822 - names are created by the byte-pinned carrier exec
    "ACCEPTED_DEPENDENCY_CLOSURE",
    "BUNDLE_PATH",
    "ConstructionMasterV12Error",
    "DEFINITION_PATH",
    "EXPECTED_DIGESTS",
    "MASTER_ID",
    "PREPARATION_GENERATED_AT",
    "SCOPE_POLICY",
    "construction_master_v28_definition",
    "construction_master_v28_definition_bytes",
    "discard_construction_master_v28_stage",
    "is_frozen_master_v12",
    "prepare_construction_master_v28",
    "publish_construction_master_v28",
    "validate_construction_master_v12",
    "validate_definition",
    "validate_dependency_closure_v28",
    "write_construction_master_v12",
]
