"""Collision-isolated current-coverage ledger v15.

V15 is a strict successor to frozen v14. It replaces only the official
open-seed v44 entry with accepted v46 and preserves the other 43 entries,
including historical satellite-review lineage, byte-semantically unchanged.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import ctypes
from dataclasses import dataclass
from datetime import UTC, datetime
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any, Iterator, Mapping, Sequence

from . import current_coverage as _legacy
from . import current_coverage_v14 as _v14


V15_LEDGER_ID = "current-coverage-2026-07-20-v15"
V15_GENERATED_AT = "2026-07-20T10:16:13Z"
V15_DEFINITION_PATH = "sources/current-coverage-2026-07-20-v15.json"
V15_BUNDLE_PATH = "current_coverage_ledgers/2026-07-20-v15"
V15_DEFINITION_SHA256 = (
    "ec5ad556c422a5f184c818d8aaca858a8c6ec75ec77318461802301bd4ff54bd"
)
V46_RECORDED_AT = "2026-07-20T09:41:21Z"

LEDGER_FILENAME = _legacy.LEDGER_FILENAME
MANIFEST_FILENAME = _legacy.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = _legacy.MANIFEST_HASH_FILENAME
BUNDLE_FILES = _legacy.BUNDLE_FILES
SCOPE_POLICY = _legacy.SCOPE_POLICY_V2

V14_BASE_LINEAGE = {
    "definition": {
        "bytes": 129_254,
        "path": "sources/current-coverage-2026-07-20-v14.json",
        "sha256": "907942b43861845703900dfb57e518ed56611bb932b2ec0f16f1ab656b0beab0",
    },
    "ledger": {
        "bytes": 89_210,
        "path": (
            "current_coverage_ledgers/2026-07-20-v14/"
            "current-coverage-ledger.json"
        ),
        "sha256": "ede89a5b75ca30dae4c96f3ae876e02abf53eff00497a8edc85fc9fcde69b2bd",
    },
    "ledger_id": "current-coverage-2026-07-20-v14",
    "manifest": {
        "bytes": 24_814,
        "path": "current_coverage_ledgers/2026-07-20-v14/manifest.json",
        "sha256": "5f318e610653a4579fb9d995133fd3ea388de5c7a2a3b66c2e250fced69d150c",
    },
}

ARTIFACT_REPLACEMENTS = {
    "seed-epoch-official-v44": "seed-epoch-official-v46",
}
REMOVED_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS)
REPLACEMENT_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS.values())

_BASE_BUNDLE_TREE = {
    "directories": 1,
    "files": 3,
    "path": "current_coverage_ledgers/2026-07-20-v14",
    "sha256": "f59daffd971b54d9a462cc620d6d812dd1650b194675d6bcafa6d8559282ba50",
}
_V46_TREE = {
    "directories": 1,
    "files": 13,
    "path": "releases/2026-07-20-open-seed-v46",
    "sha256": "5e3001aaa1857bb54626c08f5bfe87136ea187632a983b553d64cb8e4d742fe5",
}

_PINNED_FILES = {
    "v14 implementation": (
        "datacenter_atlas/current_coverage_v14.py",
        52_478,
        "8ad89d1aa0e6dc4071f95d18134a01b4ef2685a51a27c8de697244bd6a9863d9",
    ),
    "v14 definition": (
        V14_BASE_LINEAGE["definition"]["path"],
        V14_BASE_LINEAGE["definition"]["bytes"],
        V14_BASE_LINEAGE["definition"]["sha256"],
    ),
    "v14 ledger": (
        V14_BASE_LINEAGE["ledger"]["path"],
        V14_BASE_LINEAGE["ledger"]["bytes"],
        V14_BASE_LINEAGE["ledger"]["sha256"],
    ),
    "v14 manifest": (
        V14_BASE_LINEAGE["manifest"]["path"],
        V14_BASE_LINEAGE["manifest"]["bytes"],
        V14_BASE_LINEAGE["manifest"]["sha256"],
    ),
    "v14 sidecar": (
        "current_coverage_ledgers/2026-07-20-v14/manifest.sha256",
        80,
        "a9ad99f6a82b749ec69ef9f38a1b2f1c010848b0e7db33b878c232b64d4ce536",
    ),
    "v46 definition": (
        "sources/open-seed-2026-07-20-v46.json",
        60_096,
        "b6021710df7211611975dd946ef0a14c974b29a782161af821512a3a167a2293",
    ),
    "v46 manifest": (
        "releases/2026-07-20-open-seed-v46/manifest.json",
        7_747,
        "85ebc71e3751d722da2b24ae36abd62de8733ff331883d686ea74f5c3987418d",
    ),
}

UNCHANGED_43_SHA256 = "03775eeb2327c1764d5ec88874710bee74925dd5e1ddd506e8edc2815e54e4d5"
NEW_ENTRY_SHA256 = "152c7f7ce322dd3790f1c095b0dfd26c7d1cf4f86928f1b60c642bf66256acd2"
ALL_ENTRIES_SHA256 = "636b4953b71d6995002e7e660f3362eb2df77443a94740744051a0ea566330a4"
PARITY_GAPS_SHA256 = "e81c7a6ee803028c4bffcd94daa9c4c37bb8c9c4a540fb0541ba005311614a77"


class CurrentCoverageV15Error(_legacy.CurrentCoverageError):
    """Raised when the v15 definition, inputs, or bundle fail closed."""


@dataclass(frozen=True, slots=True)
class CurrentCoverageV15Bundle:
    ledger_bytes: bytes
    manifest_bytes: bytes
    manifest_hash_bytes: bytes
    ledger: Mapping[str, Any]
    manifest: Mapping[str, Any]


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_line(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _lexical_absolute(path: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _read_regular(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise CurrentCoverageV15Error(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CurrentCoverageV15Error(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise CurrentCoverageV15Error(f"{label} must be a JSON object")
    return value


def _pinned_json(
    package_root: Path,
    spec: Mapping[str, Any],
    label: str,
) -> tuple[bytes, dict[str, Any]]:
    path = (package_root / str(spec["path"])).resolve()
    try:
        path.relative_to(package_root)
    except ValueError as error:
        raise CurrentCoverageV15Error(f"{label} escapes package root") from error
    raw = _read_regular(path, label)
    if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
        raise CurrentCoverageV15Error(f"{label} changed")
    document = _json_object(raw, label)
    if raw != _canonical_json(document):
        raise CurrentCoverageV15Error(f"{label} is not canonical JSON")
    return raw, document


def _tree_digest(root: Path, label: str) -> tuple[int, int, str]:
    if root.is_symlink() or not root.is_dir():
        raise CurrentCoverageV15Error(f"{label} must be a regular directory")
    digest = hashlib.sha256()
    file_count = 0
    directory_count = 0
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise CurrentCoverageV15Error(f"{label} contains symlink: {relative}")
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            if mode != 0o555:
                raise CurrentCoverageV15Error(
                    f"{label} directory mode changed: {relative} is {mode:04o}"
                )
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode("utf-8"))
            directory_count += 1
        elif path.is_file():
            if mode != 0o444:
                raise CurrentCoverageV15Error(
                    f"{label} file mode changed: {relative} is {mode:04o}"
                )
            raw = path.read_bytes()
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{_sha256(raw)}\n"
                ).encode("utf-8")
            )
            file_count += 1
        else:
            raise CurrentCoverageV15Error(
                f"{label} contains unsupported entry: {relative}"
            )
    return file_count, directory_count, digest.hexdigest()


def _validate_tree(package_root: Path, spec: Mapping[str, Any], label: str) -> None:
    path = (package_root / str(spec["path"])).resolve()
    try:
        path.relative_to(package_root)
    except ValueError as error:
        raise CurrentCoverageV15Error(f"{label} tree escapes package root") from error
    files, directories, digest = _tree_digest(path, label)
    if (
        files != spec["files"]
        or directories != spec["directories"]
        or digest != spec["sha256"]
    ):
        raise CurrentCoverageV15Error(f"{label} closed tree changed")


def _load_v14_base(
    package_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    definition_raw, definition = _pinned_json(
        package_root, V14_BASE_LINEAGE["definition"], "v15 base definition"
    )
    ledger_raw, ledger = _pinned_json(
        package_root, V14_BASE_LINEAGE["ledger"], "v15 base ledger"
    )
    manifest_raw, manifest = _pinned_json(
        package_root, V14_BASE_LINEAGE["manifest"], "v15 base manifest"
    )
    if (
        definition.get("ledger_id") != V14_BASE_LINEAGE["ledger_id"]
        or ledger.get("ledger_id") != V14_BASE_LINEAGE["ledger_id"]
        or manifest.get("ledger_id") != V14_BASE_LINEAGE["ledger_id"]
        or manifest.get("definition") != V14_BASE_LINEAGE["definition"]
        or manifest.get("artifacts", {}).get(LEDGER_FILENAME)
        != {"bytes": len(ledger_raw), "sha256": _sha256(ledger_raw)}
        or len(definition_raw) != V14_BASE_LINEAGE["definition"]["bytes"]
        or len(manifest_raw) != V14_BASE_LINEAGE["manifest"]["bytes"]
    ):
        raise CurrentCoverageV15Error("accepted v14 base lineage changed")
    _validate_tree(package_root, _BASE_BUNDLE_TREE, "v15 base bundle")
    return definition, ledger, manifest


def _seed_v46_entry(base_entry: Mapping[str, Any]) -> dict[str, Any]:
    entry = deepcopy(dict(base_entry))
    if entry.get("artifact_id") != "seed-epoch-official-v44":
        raise CurrentCoverageV15Error("v14 official seed entry changed")
    entry["artifact_id"] = "seed-epoch-official-v46"
    checkpoints = entry.get("checkpoints")
    if not isinstance(checkpoints, list) or len(checkpoints) != 1:
        raise CurrentCoverageV15Error("v14 official seed checkpoint changed")
    checkpoint = checkpoints[0]
    if checkpoint.get("checkpoint_id") != "manifest":
        raise CurrentCoverageV15Error("v14 official seed manifest checkpoint changed")
    checkpoint.update(
        {
            "bytes": 7_747,
            "path": "releases/2026-07-20-open-seed-v46/manifest.json",
            "sha256": "85ebc71e3751d722da2b24ae36abd62de8733ff331883d686ea74f5c3987418d",
        }
    )
    old_limitation = (
        "The 573 source-scoped entity rows comprise 312 campus observations and "
        "261 project observations, not deduplicated physical sites."
    )
    new_limitation = (
        "The 603 source-scoped entity rows comprise 324 campus observations and "
        "279 project observations, not deduplicated physical sites."
    )
    limitations = list(entry.get("limitations", []))
    if limitations.count(old_limitation) != 1:
        raise CurrentCoverageV15Error("v14 official seed limitation changed")
    entry["limitations"] = sorted(
        new_limitation if value == old_limitation else value for value in limitations
    )
    expected_metrics = {
        "capacity_observations": 451,
        "construction_pipeline_records": 317,
        "construction_source_signals": 223,
        "evidence_records": 329,
        "resolution_candidates": 4,
        "source_scoped_entity_rows": 603,
    }
    metrics = entry.get("metrics")
    if not isinstance(metrics, list):
        raise CurrentCoverageV15Error("v14 official seed metrics changed")
    by_label = {row.get("label"): row for row in metrics}
    if set(by_label) != set(expected_metrics) or len(by_label) != len(metrics):
        raise CurrentCoverageV15Error("v14 official seed metric inventory changed")
    for label, value in expected_metrics.items():
        by_label[label]["value"] = value
    entry["metrics"] = sorted(by_label.values(), key=lambda row: row["label"])
    return entry


def _v15_parity_gaps(base_gaps: Any) -> list[dict[str, Any]]:
    if not isinstance(base_gaps, list):
        raise CurrentCoverageV15Error("v14 parity gaps are invalid")
    result: list[dict[str, Any]] = []
    replacements = 0
    for raw_gap in base_gaps:
        if not isinstance(raw_gap, Mapping):
            raise CurrentCoverageV15Error("v14 parity gap is invalid")
        gap = deepcopy(dict(raw_gap))
        affected: list[str] = []
        for artifact_id in gap["affected_artifact_ids"]:
            if artifact_id == "seed-epoch-official-v44":
                artifact_id = "seed-epoch-official-v46"
                replacements += 1
            affected.append(artifact_id)
        gap["affected_artifact_ids"] = sorted(affected)
        result.append(gap)
    if replacements != 1:
        raise CurrentCoverageV15Error("v14 parity-gap seed reference changed")
    return result


def _component_digest(entries: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(_canonical_line(entry))
    return digest.hexdigest()


def make_v15_definition(package_root: str | Path) -> bytes:
    """Create canonical v15 definition bytes from the pinned v14 baseline."""

    root = Path(package_root).resolve()
    base_definition, _base_ledger, _base_manifest = _load_v14_base(root)
    base_entries = {
        entry["artifact_id"]: deepcopy(entry) for entry in base_definition["entries"]
    }
    if set(ARTIFACT_REPLACEMENTS.values()) & set(base_entries):
        raise CurrentCoverageV15Error("v14 unexpectedly contains v15 seed ID")
    old_entry = base_entries.pop("seed-epoch-official-v44", None)
    if old_entry is None:
        raise CurrentCoverageV15Error("v14 official seed entry is absent")
    new_entry = _seed_v46_entry(old_entry)
    base_entries[new_entry["artifact_id"]] = new_entry
    if len(base_entries) != 44:
        raise CurrentCoverageV15Error("v15 definition must contain exactly 44 entries")
    ordered = [base_entries[key] for key in sorted(base_entries)]
    unchanged = [
        entry for entry in ordered if entry["artifact_id"] != "seed-epoch-official-v46"
    ]
    parity_gaps = _v15_parity_gaps(base_definition["parity_gaps"])
    if _component_digest(unchanged) != UNCHANGED_43_SHA256:
        raise CurrentCoverageV15Error("v15 inherited-entry digest changed")
    if _component_digest([new_entry]) != NEW_ENTRY_SHA256:
        raise CurrentCoverageV15Error("v15 seed-entry digest changed")
    if _component_digest(ordered) != ALL_ENTRIES_SHA256:
        raise CurrentCoverageV15Error("v15 full-entry digest changed")
    if _sha256(_canonical_line(parity_gaps)) != PARITY_GAPS_SHA256:
        raise CurrentCoverageV15Error("v15 parity-gap digest changed")
    document = {
        "base_ledger": V14_BASE_LINEAGE,
        "entries": ordered,
        "generated_at": V15_GENERATED_AT,
        "ledger_id": V15_LEDGER_ID,
        "parity_gaps": parity_gaps,
        "schema_version": _legacy.DEFINITION_SCHEMA_VERSION_V3,
        "scope": SCOPE_POLICY,
    }
    return _canonical_json(document)


def _validate_accepted_inputs(package_root: Path) -> None:
    for label, (relative, expected_bytes, expected_sha256) in sorted(
        _PINNED_FILES.items()
    ):
        raw = _read_regular(package_root / relative, f"v15 {label}")
        if len(raw) != expected_bytes or _sha256(raw) != expected_sha256:
            raise CurrentCoverageV15Error(f"v15 {label} changed")
    _validate_tree(package_root, _BASE_BUNDLE_TREE, "v15 base bundle")
    _validate_tree(package_root, _V46_TREE, "v15 official seed v46")


def _validate_definition(
    definition_path: str | Path,
) -> tuple[dict[str, Any], bytes, Path]:
    path = Path(definition_path).resolve()
    package_root = path.parent.parent.resolve()
    if path != package_root / V15_DEFINITION_PATH:
        raise CurrentCoverageV15Error("v15 definition publication path changed")
    raw = _read_regular(path, "v15 definition")
    document = _json_object(raw, "v15 definition")
    if raw != _canonical_json(document):
        raise CurrentCoverageV15Error("v15 definition is not canonical JSON")
    if _sha256(raw) != V15_DEFINITION_SHA256:
        raise CurrentCoverageV15Error("v15 definition content changed")
    if set(document) != {
        "base_ledger",
        "entries",
        "generated_at",
        "ledger_id",
        "parity_gaps",
        "schema_version",
        "scope",
    }:
        raise CurrentCoverageV15Error("v15 definition keys changed")
    if (
        document.get("ledger_id") != V15_LEDGER_ID
        or document.get("generated_at") != V15_GENERATED_AT
        or document.get("schema_version") != _legacy.DEFINITION_SCHEMA_VERSION_V3
        or document.get("scope") != SCOPE_POLICY
        or document.get("base_ledger") != V14_BASE_LINEAGE
    ):
        raise CurrentCoverageV15Error("v15 identity, base, schema, or scope changed")
    try:
        generated_at = datetime.fromisoformat(V15_GENERATED_AT.replace("Z", "+00:00"))
        v46_recorded_at = datetime.fromisoformat(V46_RECORDED_AT.replace("Z", "+00:00"))
    except ValueError as error:
        raise CurrentCoverageV15Error("v15 timestamp is invalid") from error
    if generated_at > datetime.now(UTC) or generated_at <= v46_recorded_at:
        raise CurrentCoverageV15Error("v15 chronology is invalid")
    expected_raw = make_v15_definition(package_root)
    if raw != expected_raw:
        raise CurrentCoverageV15Error("v15 definition differs from pinned transformation")
    entries = document.get("entries")
    if not isinstance(entries, list) or len(entries) != 44:
        raise CurrentCoverageV15Error("v15 must contain exactly 44 entries")
    entry_map = {entry.get("artifact_id"): entry for entry in entries}
    if len(entry_map) != 44 or None in entry_map:
        raise CurrentCoverageV15Error("v15 entry inventory is invalid")
    if "seed-epoch-official-v44" in entry_map or "seed-epoch-official-v47" in entry_map:
        raise CurrentCoverageV15Error("v15 contains a stale or unaccepted seed entry")
    _validate_accepted_inputs(package_root)
    return document, raw, package_root


def build_current_coverage_ledger_v15(
    definition_path: str | Path,
) -> CurrentCoverageV15Bundle:
    """Reproduce the v15 ledger entirely from pinned local inputs."""

    definition, definition_raw, package_root = _validate_definition(definition_path)
    artifacts: list[dict[str, Any]] = []
    previous_id: str | None = None
    try:
        for spec in definition["entries"]:
            artifact = _legacy._entry(
                package_root,
                spec,
                previous_id,
                _legacy.DEFINITION_SCHEMA_VERSION_V3,
            )
            artifacts.append(artifact)
            previous_id = artifact["artifact_id"]
        parity_gaps = _legacy._parity_gaps(
            definition["parity_gaps"],
            {artifact["artifact_id"] for artifact in artifacts},
        )
    except _legacy.CurrentCoverageError as error:
        raise CurrentCoverageV15Error(str(error)) from error
    inventory_counts = _v14._inventory_counts(artifacts, parity_gaps)
    if inventory_counts != _v14._EXPECTED_INVENTORY_COUNTS:
        raise CurrentCoverageV15Error("v15 artifact inventory arithmetic changed")
    ledger = {
        "artifact_inventory_counts": inventory_counts,
        "artifacts": artifacts,
        "base_ledger": V14_BASE_LINEAGE,
        "format": _legacy.LEDGER_FORMAT_V3,
        "generated_at": V15_GENERATED_AT,
        "ledger_id": V15_LEDGER_ID,
        "parity_gaps": parity_gaps,
        "schema_version": _legacy.LEDGER_SCHEMA_VERSION_V3,
        "scope": SCOPE_POLICY,
    }
    ledger_bytes = _canonical_json(ledger)
    manifest = {
        "artifacts": {
            LEDGER_FILENAME: {
                "bytes": len(ledger_bytes),
                "sha256": _sha256(ledger_bytes),
            }
        },
        "base_ledger": V14_BASE_LINEAGE,
        "definition": {
            "bytes": len(definition_raw),
            "path": V15_DEFINITION_PATH,
            "sha256": _sha256(definition_raw),
        },
        "format": _legacy.BUNDLE_FORMAT_V3,
        "generated_at": V15_GENERATED_AT,
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
        "ledger_id": V15_LEDGER_ID,
        "schema_version": _legacy.LEDGER_SCHEMA_VERSION_V3,
        "scope": SCOPE_POLICY,
    }
    manifest_bytes = _canonical_json(manifest)
    manifest_hash_bytes = (
        f"{_sha256(manifest_bytes)}  {MANIFEST_FILENAME}\n".encode("ascii")
    )
    return CurrentCoverageV15Bundle(
        ledger_bytes=ledger_bytes,
        manifest_bytes=manifest_bytes,
        manifest_hash_bytes=manifest_hash_bytes,
        ledger=ledger,
        manifest=manifest,
    )


def _write_file(path: Path, raw: bytes) -> None:
    with path.open("xb") as destination:
        destination.write(raw)
        destination.flush()
        os.fsync(destination.fileno())


@contextmanager
def _exclusive_output_lock(destination: Path) -> Iterator[None]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / f".{destination.name}.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise CurrentCoverageV15Error(f"refusing active output lock: {lock}") from error
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _fsync_regular(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _path_identity(path: Path) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    return metadata.st_dev, metadata.st_ino


def _cleanup_owned_file_stage(stage: Path, identity: tuple[int, int]) -> None:
    try:
        metadata = stage.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISREG(metadata.st_mode)
        or (metadata.st_dev, metadata.st_ino) != identity
    ):
        raise CurrentCoverageV15Error(
            "refusing cleanup of substituted v15 definition stage"
        )
    stage.unlink()


def _cleanup_owned_bundle_stage(stage: Path, identity: tuple[int, int]) -> None:
    try:
        metadata = stage.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or (metadata.st_dev, metadata.st_ino) != identity
    ):
        raise CurrentCoverageV15Error(
            "refusing cleanup of substituted v15 bundle stage"
        )
    entries = list(stage.iterdir())
    if not {entry.name for entry in entries}.issubset(BUNDLE_FILES) or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise CurrentCoverageV15Error(
            "refusing cleanup of contaminated v15 bundle stage"
        )
    stage.chmod(0o700)
    for entry in entries:
        entry.chmod(0o600)
        entry.unlink()
    stage.rmdir()


def _promote_noreplace(stage: Path, destination: Path) -> None:
    """Atomically publish one sibling path without replacing a late arrival."""

    if stage.parent != destination.parent:
        raise CurrentCoverageV15Error("v15 stage and destination must be siblings")
    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(stage)
    target = os.fsencode(destination)
    if sys.platform == "darwin":
        function = getattr(library, "renamex_np", None)
        if function is None:  # pragma: no cover - required on publication hosts
            raise CurrentCoverageV15Error(
                "atomic no-clobber publication is unavailable"
            )
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(source, target, 0x00000004)
    elif sys.platform.startswith("linux"):
        function = getattr(library, "renameat2", None)
        if function is None:  # pragma: no cover - required on publication hosts
            raise CurrentCoverageV15Error(
                "atomic no-clobber publication is unavailable"
            )
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(-100, source, -100, target, 0x00000001)
    else:  # pragma: no cover - supported publication hosts are Darwin/Linux
        raise CurrentCoverageV15Error(
            "atomic no-clobber publication is unavailable"
        )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise CurrentCoverageV15Error(
            f"refusing late output collision: {destination}"
        )
    raise CurrentCoverageV15Error(
        "atomic no-clobber publication failed: "
        f"{os.strerror(error_number)}"
    )


def write_v15_definition(
    package_root: str | Path,
    output_path: str | Path,
) -> str:
    """Atomically create, but never replace, the canonical v15 definition."""

    destination = _lexical_absolute(output_path)
    raw = make_v15_definition(package_root)
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise CurrentCoverageV15Error(f"refusing existing output: {destination}")
        stage = destination.parent / f".{destination.name}.{os.getpid()}.tmp"
        stage_identity: tuple[int, int] | None = None
        try:
            _write_file(stage, raw)
            stage_identity = _path_identity(stage)
            stage.chmod(0o644)
            _fsync_regular(stage)
            if destination.exists() or destination.is_symlink():
                raise CurrentCoverageV15Error(
                    f"refusing late output collision: {destination}"
                )
            _promote_noreplace(stage, destination)
            _fsync_directory(destination.parent)
            if (
                destination.is_symlink()
                or not destination.is_file()
                or stat.S_IMODE(destination.stat().st_mode) != 0o644
                or destination.read_bytes() != raw
            ):
                raise CurrentCoverageV15Error(
                    "v15 definition changed during publication"
                )
        except BaseException as primary_error:
            try:
                if stage_identity is not None:
                    _cleanup_owned_file_stage(stage, stage_identity)
            except Exception as cleanup_error:
                primary_error.add_note(f"v15 stage cleanup failed: {cleanup_error}")
            raise
    return _sha256(raw)


def write_current_coverage_ledger_v15(
    definition_path: str | Path,
    output_path: str | Path,
    *,
    freeze: bool = True,
) -> dict[str, Any]:
    """Atomically publish v15 under a collision-refusing sibling lock."""

    if freeze is not True:
        raise CurrentCoverageV15Error("v15 publication requires freeze=True")
    bundle = build_current_coverage_ledger_v15(definition_path)
    destination = _lexical_absolute(output_path)
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise CurrentCoverageV15Error(f"refusing existing output: {destination}")
        stage = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        stage_identity = _path_identity(stage)
        try:
            _write_file(stage / LEDGER_FILENAME, bundle.ledger_bytes)
            _write_file(stage / MANIFEST_FILENAME, bundle.manifest_bytes)
            _write_file(stage / MANIFEST_HASH_FILENAME, bundle.manifest_hash_bytes)
            for filename in BUNDLE_FILES:
                (stage / filename).chmod(0o444)
                _fsync_regular(stage / filename)
            stage.chmod(0o555)
            _fsync_directory(stage)
            validate_current_coverage_ledger_v15(
                stage, definition_path=definition_path
            )
            if destination.exists() or destination.is_symlink():
                raise CurrentCoverageV15Error(
                    f"refusing late output collision: {destination}"
                )
            _promote_noreplace(stage, destination)
            _fsync_directory(destination.parent)
            validate_current_coverage_ledger_v15(
                destination, definition_path=definition_path
            )
        except BaseException as primary_error:
            try:
                _cleanup_owned_bundle_stage(stage, stage_identity)
            except Exception as cleanup_error:
                primary_error.add_note(f"v15 stage cleanup failed: {cleanup_error}")
            raise
    return dict(bundle.manifest)


def validate_current_coverage_ledger_v15(
    output_path: str | Path,
    *,
    definition_path: str | Path,
) -> dict[str, Any]:
    """Validate frozen output and reproduce it byte-for-byte offline."""

    directory = Path(output_path)
    if directory.is_symlink() or not directory.is_dir():
        raise CurrentCoverageV15Error("v15 bundle must be a regular directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES:
        raise CurrentCoverageV15Error("v15 bundle file set differs")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555 or any(
        entry.is_symlink()
        or not entry.is_file()
        or stat.S_IMODE(entry.stat().st_mode) != 0o444
        for entry in entries
    ):
        raise CurrentCoverageV15Error("v15 bundle must be frozen 0555/0444")
    actual_ledger = _read_regular(directory / LEDGER_FILENAME, "v15 ledger")
    actual_manifest = _read_regular(directory / MANIFEST_FILENAME, "v15 manifest")
    actual_sidecar = _read_regular(directory / MANIFEST_HASH_FILENAME, "v15 sidecar")
    _json_object(actual_ledger, "v15 ledger")
    _json_object(actual_manifest, "v15 manifest")
    expected_sidecar = f"{_sha256(actual_manifest)}  {MANIFEST_FILENAME}\n".encode(
        "ascii"
    )
    if actual_sidecar != expected_sidecar:
        raise CurrentCoverageV15Error("v15 manifest sidecar differs")
    expected = build_current_coverage_ledger_v15(definition_path)
    if actual_ledger != expected.ledger_bytes:
        raise CurrentCoverageV15Error("v15 ledger differs from offline reconstruction")
    if actual_manifest != expected.manifest_bytes:
        raise CurrentCoverageV15Error("v15 manifest differs from offline reconstruction")
    if actual_sidecar != expected.manifest_hash_bytes:
        raise CurrentCoverageV15Error("v15 sidecar differs from offline reconstruction")
    return dict(expected.manifest)


__all__ = [
    "ARTIFACT_REPLACEMENTS",
    "BUNDLE_FILES",
    "CurrentCoverageV15Bundle",
    "CurrentCoverageV15Error",
    "REMOVED_ARTIFACT_IDS",
    "REPLACEMENT_ARTIFACT_IDS",
    "V14_BASE_LINEAGE",
    "V15_BUNDLE_PATH",
    "V15_DEFINITION_PATH",
    "V15_DEFINITION_SHA256",
    "V15_GENERATED_AT",
    "V15_LEDGER_ID",
    "build_current_coverage_ledger_v15",
    "make_v15_definition",
    "validate_current_coverage_ledger_v15",
    "write_current_coverage_ledger_v15",
    "write_v15_definition",
]
