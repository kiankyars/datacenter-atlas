"""Hardened v28 construction-map publisher over accepted map v27.

The wire schema remains construction-map v2.  V28 changes only the bound
construction master and its deterministic coordinate projection.  Publication
is deliberately unavailable until the accepted master-v28 hashes below are
configured.  Candidate masters may be inspected read-only with
``derive_candidate_projection`` without creating either final map path.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import gzip
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

from . import construction_master_v12 as master_v12
from .open_seed_v56 import promote_noreplace, tree_digest


# Execute the accepted carrier in this module's namespace so its projection
# functions retain the established schema while binding master v28 and v71.
_BASE_SOURCE = Path(__file__).with_name("construction_map_v11.py")
_BASE_SOURCE_SHA256 = (
    "20ba327d39af80ba7eb14f5b2d52197285e7372a0821ecb3a19817a49c336041"
)


def _successor_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_map_v12 accepted-v27 boundary changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_base_raw = _BASE_SOURCE.read_bytes()
if hashlib.sha256(_base_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_map_v11 changed; refusing v28 carrier load")
_source = _base_raw.decode("utf-8")
for _old, _new, _count in (
    ("construction_map_v11", "construction_map_v12", 2),
    ("ConstructionMapV11Error", "ConstructionMapV12Error", 1),
    ("build_index_v11", "build_index_v12", 1),
    ("is_frozen_map_v11", "is_frozen_map_v12", 1),
    ("validate_map_definition_v11", "validate_map_definition_v12", 1),
    ("construction_master_v11", "construction_master_v12", 1),
    ("ConstructionMasterV11Error", "ConstructionMasterV12Error", 1),
    ("v27", "v28", 6),
    ("v67", "v71", 2),
    ("2026-07-21T08:05:01Z", "2099-01-01T00:00:01Z", 1),
    ("109_313", "109_328", 1),
    ("len(replacement_ids) != 401", "len(replacement_ids) != 416", 1),
    ("len(added) != 202", "len(added) != 217", 1),
    ("108,993", "108,996", 1),
    ("109,313", "109,328", 1),
):
    _source = _successor_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())

# Bind the dynamically loaded carrier names explicitly for static analysis.
ConstructionMapV12Error = globals()["ConstructionMapV12Error"]
BUNDLE_FILES = globals()["BUNDLE_FILES"]
EXPECTED_DIGEST_KEYS = globals()["EXPECTED_DIGEST_KEYS"]
EXPECTED_FIXED = globals()["EXPECTED_FIXED"]
FIELDS = globals()["FIELDS"]
INDEX_FILENAME = globals()["INDEX_FILENAME"]
MANIFEST_FILENAME = globals()["MANIFEST_FILENAME"]
MAP_SCOPE = globals()["MAP_SCOPE"]


ROOT = Path(__file__).resolve().parents[1]
MAP_ID = "2026-07-21-public-open-v28-construction-map-v2"
MASTER_ID = "2026-07-21-public-open-v28"
DEFINITION = ROOT / "sources/construction-map-2026-07-21-public-open-v28.json"
BUNDLE = ROOT / "construction_maps/2026-07-21-public-open-v28"
MASTER_DEFINITION = (
    ROOT / "sources/construction-master-2026-07-21-public-open-v28.json"
)
MASTER = ROOT / "construction_master/2026-07-21-public-open-v28"
PUBLICATION_LOCK = ROOT / ".construction-map-v28.lock"

CANDIDATE_MASTER_TRANSACTION = (
    ROOT / ".construction-master-v28.transaction-op08mj7x"
)
CANDIDATE_MASTER_DEFINITION = (
    CANDIDATE_MASTER_TRANSACTION
    / "construction-master-2026-07-21-public-open-v28.json"
)
CANDIDATE_MASTER = CANDIDATE_MASTER_TRANSACTION / "bundle"
CANDIDATE_MASTER_GENERATED_AT = "2026-07-21T10:56:30Z"
CANDIDATE_MASTER_DEFINITION_SHA256 = (
    "e93b0f3e7750c90a03cca5afe349ea04ae9790b607fa0b09de9ce394a1ad4533"
)
CANDIDATE_MASTER_JSONL_SHA256 = (
    "bab576bd07cdf6d1d0c120834fb8bb1ab764de09051ddf71b58f5626c2f9621b"
)
CANDIDATE_MASTER_MANIFEST_SHA256 = (
    "fbdd682a74cf762573fd607632c1f6b44a2ef2792db1fddb577e99ab8c2ba24c"
)
CANDIDATE_MASTER_TREE_SHA256 = (
    "ab0cd348fd72700e012902f5130a3cbb3045e897d9609f32583fc4fa0a25209f"
)

PREDECESSOR_DEFINITION = (
    ROOT / "sources/construction-map-2026-07-21-public-open-v27.json"
)
PREDECESSOR_BUNDLE = ROOT / "construction_maps/2026-07-21-public-open-v27"
PREDECESSOR_DEFINITION_SHA256 = (
    "a7d62e22778ce4c70e5fbe015e67b5cf2702f19862dc63d93896d669bf4638f4"
)
PREDECESSOR_MANIFEST_SHA256 = (
    "7115033102529e7dcca992960948463ead7f7d74a717510fdddbcfa2e89c6c38"
)
PREDECESSOR_TREE_SHA256 = (
    "55a9811b96d5d644f325c4b82082c8c96c60c21011302fd43ed0e07b76fb665d"
)

# Accepted final master-v28 pins. Candidate inspection never populated these;
# they were installed only after the final no-replace promotion and ctime gate.
MASTER_DEFINITION_SHA256 = (
    "e93b0f3e7750c90a03cca5afe349ea04ae9790b607fa0b09de9ce394a1ad4533"
)
MASTER_JSONL_SHA256 = (
    "bab576bd07cdf6d1d0c120834fb8bb1ab764de09051ddf71b58f5626c2f9621b"
)
MASTER_MANIFEST_SHA256 = (
    "fbdd682a74cf762573fd607632c1f6b44a2ef2792db1fddb577e99ab8c2ba24c"
)
MASTER_TREE_SHA256 = (
    "ab0cd348fd72700e012902f5130a3cbb3045e897d9609f32583fc4fa0a25209f"
)

EXPECTED_PROJECTION = {
    "added_replacement_rows_unmapped": 201,
    "added_replacement_unmapped_source_record_ids_sha256": (
        "dea88eaaca405835e2b79a9312b95a6d518ef8b3f091e7cd06569fcb62ccc1bf"
    ),
    "default_visible_rows": 6502,
    "default_visible_tiers": ["A", "B"],
    "mapped_by_tier": {"A": 222, "B": 6280, "C": 102494},
    "mapped_replacement_rows": 103,
    "mapped_rows": 108996,
    "mapped_rows_with_any_role": 75,
    "master_rows": 109328,
    "unmapped_rows": 332,
    "unmapped_source_record_ids_sha256": (
        "aef8c6128f5051d6d727f012d7e4c2af78dd2564aeb1f3e3503ca124bf6f0c27"
    ),
}

NEW_COORDINATE_MAPPING_IDS = frozenset(
    {
        "3170da28-25e1-5859-b606-f86c78ba5c0f",
        "54c278ca-4dff-5f57-b5a6-911f8a615f5e",
        "b5625b8f-5e00-5fbe-b313-ba7adb980583",
    }
)

REJECTED_LINEAGE_TOKENS = (
    b"2026-07-21-public-open-v29",
    b"2026-07-21-public-open-v30",
    b"2026-07-21-open-seed-v68",
    b"epoch-official-open-seed-v68",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UTC_SECOND_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# Replace the projection constants created by the carrier before any inherited
# function is called.  Digest values remain definition-bound as in schema v2.
EXPECTED_FIXED.clear()
EXPECTED_FIXED.update(
    {
        key: value
        for key, value in EXPECTED_PROJECTION.items()
        if key not in EXPECTED_DIGEST_KEYS and key != "default_visible_tiers"
    }
)

_core_build_index = globals()["build_index_v12"]
_core_validate_map_definition = globals()["validate_map_definition_v12"]
_core_is_frozen_map = globals()["is_frozen_map_v12"]
_core_build_into = globals()["_build_into"]
_core_validate_static = globals()["_validate_static"]
_core_added_source_record_ids = globals()["_added_source_record_ids"]
_core_master_rows = globals()["_master_rows"]


def _sha256(value: Path | bytes) -> str:
    if isinstance(value, bytes):
        return hashlib.sha256(value).hexdigest()
    path = value
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise ConstructionMapV12Error(f"required input must be a regular file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checkpoint(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _parse_utc(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not _UTC_SECOND_RE.fullmatch(value):
        raise ConstructionMapV12Error(f"{label} must be canonical UTC-second text")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ConstructionMapV12Error(f"{label} is invalid") from error
    return result.astimezone(timezone.utc)


def _wall_clock(value: datetime | None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ConstructionMapV12Error("validation wall clock must include a timezone")
    return result.astimezone(timezone.utc)


def _regular_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise ConstructionMapV12Error(f"{label} must be a regular file")
    raw = path.read_bytes()
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConstructionMapV12Error(f"{label} must be valid JSON") from error
    if not isinstance(document, dict) or raw != _canonical_json(document):
        raise ConstructionMapV12Error(f"{label} must be canonical object JSON")
    return document, raw


def _path_from_sources(path: Path) -> str:
    try:
        return path.resolve().relative_to(DEFINITION.parent.resolve()).as_posix()
    except ValueError:
        return os.path.relpath(path.resolve(), DEFINITION.parent.resolve())


def _require_predecessor() -> None:
    actual = {
        "definition": _sha256(PREDECESSOR_DEFINITION),
        "manifest": _sha256(PREDECESSOR_BUNDLE / MANIFEST_FILENAME),
        "tree": tree_digest(PREDECESSOR_BUNDLE),
    }
    expected = {
        "definition": PREDECESSOR_DEFINITION_SHA256,
        "manifest": PREDECESSOR_MANIFEST_SHA256,
        "tree": PREDECESSOR_TREE_SHA256,
    }
    if actual != expected:
        changed = sorted(key for key in expected if actual[key] != expected[key])
        raise ConstructionMapV12Error(
            "accepted construction-map v27 changed: " + ", ".join(changed)
        )


def _accepted_master_pins() -> dict[str, str]:
    pins = {
        "definition": MASTER_DEFINITION_SHA256,
        "jsonl": MASTER_JSONL_SHA256,
        "manifest": MASTER_MANIFEST_SHA256,
        "tree": MASTER_TREE_SHA256,
    }
    missing = [name for name, value in pins.items() if not _SHA256_RE.fullmatch(value)]
    if missing:
        raise ConstructionMapV12Error(
            "master v28 is not accepted; publication pins are unset: "
            + ", ".join(missing)
        )
    return pins


def _require_accepted_master() -> dict[str, str]:
    pins = _accepted_master_pins()
    actual = {
        "definition": _sha256(MASTER_DEFINITION),
        "jsonl": _sha256(MASTER / "construction-master.jsonl"),
        "manifest": _sha256(MASTER / MANIFEST_FILENAME),
        "tree": tree_digest(MASTER),
    }
    if actual != pins:
        changed = sorted(key for key in pins if actual[key] != pins[key])
        raise ConstructionMapV12Error(
            "accepted construction-master v28 changed: " + ", ".join(changed)
        )
    if not master_v12.is_frozen_master_v12(MASTER):
        raise ConstructionMapV12Error("accepted construction-master v28 is not frozen")
    return pins


def require_candidate_master() -> dict[str, str]:
    """Verify the exact frozen live-target stage without accepting it."""

    expected = {
        "definition": CANDIDATE_MASTER_DEFINITION_SHA256,
        "jsonl": CANDIDATE_MASTER_JSONL_SHA256,
        "manifest": CANDIDATE_MASTER_MANIFEST_SHA256,
        "tree": CANDIDATE_MASTER_TREE_SHA256,
    }
    actual = {
        "definition": _sha256(CANDIDATE_MASTER_DEFINITION),
        "jsonl": _sha256(CANDIDATE_MASTER / "construction-master.jsonl"),
        "manifest": _sha256(CANDIDATE_MASTER / MANIFEST_FILENAME),
        "tree": tree_digest(CANDIDATE_MASTER),
    }
    if actual != expected:
        changed = sorted(key for key in expected if actual[key] != expected[key])
        raise ConstructionMapV12Error(
            "construction-master v28 candidate changed: " + ", ".join(changed)
        )
    if not master_v12.is_frozen_master_v12(CANDIDATE_MASTER):
        raise ConstructionMapV12Error(
            "construction-master v28 candidate is not frozen"
        )
    document, _ = _regular_json(
        CANDIDATE_MASTER_DEFINITION, "master v28 candidate definition"
    )
    if document.get("generated_at") != CANDIDATE_MASTER_GENERATED_AT:
        raise ConstructionMapV12Error(
            "construction-master v28 candidate generated_at changed"
        )
    return actual


@contextmanager
def _runtime_timestamps(map_generated_at: str, master_generated_at: str) -> Iterator[None]:
    previous_map = globals()["GENERATED_AT"]
    previous_master = master_v12.GENERATED_AT
    globals()["GENERATED_AT"] = map_generated_at
    master_v12.GENERATED_AT = master_generated_at
    try:
        yield
    finally:
        globals()["GENERATED_AT"] = previous_map
        master_v12.GENERATED_AT = previous_master


def _master_generated_at(master_definition_path: Path) -> str:
    document, _ = _regular_json(master_definition_path, "master v28 definition")
    if document.get("master_id") != MASTER_ID:
        raise ConstructionMapV12Error("candidate master identity is not v28")
    value = document.get("generated_at")
    _parse_utc(value, label="master v28 generated_at")
    return value


def _map_rows(path: Path) -> dict[str, dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise ConstructionMapV12Error(f"map index must be a regular file: {path}")
    try:
        index = json.loads(gzip.decompress(path.read_bytes()))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConstructionMapV12Error(f"map index is invalid: {path}") from error
    fields = index.get("fields")
    rows = index.get("rows")
    if fields != list(FIELDS) or not isinstance(rows, list):
        raise ConstructionMapV12Error("accepted map v27 row schema changed")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, list) or len(row) != len(fields):
            raise ConstructionMapV12Error("accepted map v27 row shape changed")
        record = dict(zip(fields, row, strict=True))
        record_id = record.get("source_record_id")
        if not isinstance(record_id, str) or record_id in result:
            raise ConstructionMapV12Error("accepted map v27 record ID changed")
        result[record_id] = record
    return result


def _master_record_ids(path: Path) -> set[str]:
    result: set[str] = set()
    for line_number, row in enumerate(_core_master_rows(path), start=1):
        source = row.get("source")
        record_id = source.get("record_id") if isinstance(source, Mapping) else None
        if not isinstance(record_id, str) or record_id in result:
            raise ConstructionMapV12Error(
                f"master row {line_number} source record ID changed"
            )
        result.add(record_id)
    return result


def _projection_from_master(
    master_directory: Path,
    master_definition_path: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], set[str]]:
    master_generated_at = _master_generated_at(master_definition_path)
    manifest, manifest_raw = _regular_json(
        master_directory / MANIFEST_FILENAME, "master v28 manifest"
    )
    with _runtime_timestamps("2099-01-01T00:00:01Z", master_generated_at):
        try:
            master_v12.validate_construction_master_v12(
                master_directory,
                definition_path=master_definition_path,
                reproduce=False,
            )
        except master_v12.ConstructionMasterV12Error as error:
            raise ConstructionMapV12Error(str(error)) from error
        added = _core_added_source_record_ids(master_definition_path)
        all_ids: set[str] = set()

        def rows() -> Iterator[Mapping[str, Any]]:
            for row in _core_master_rows(
                master_directory / "construction-master.jsonl"
            ):
                source = row.get("source")
                record_id = (
                    source.get("record_id") if isinstance(source, Mapping) else None
                )
                if not isinstance(record_id, str) or record_id in all_ids:
                    raise ConstructionMapV12Error(
                        "candidate master source record ID is absent or repeated"
                    )
                all_ids.add(record_id)
                yield row

        index, coverage = _core_build_index(
            rows(),
            master_manifest=manifest,
            master_manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),
            added_source_record_ids=added,
            expected_projection=None,
        )
    projected: dict[str, dict[str, Any]] = {}
    for values in index["rows"]:
        row = dict(zip(FIELDS, values, strict=True))
        record_id = row["source_record_id"]
        if record_id in projected:
            raise ConstructionMapV12Error("candidate map record ID repeats")
        projected[record_id] = row
    return dict(coverage["projection"]), projected, all_ids


def _assert_exact_v27_delta(
    projected: Mapping[str, Mapping[str, Any]], all_ids: set[str]
) -> None:
    old_projected = _map_rows(PREDECESSOR_BUNDLE / INDEX_FILENAME)
    old_all_ids = _master_record_ids(
        ROOT
        / "construction_master/2026-07-21-public-open-v27/construction-master.jsonl"
    )
    if not old_all_ids.issubset(all_ids) or len(all_ids - old_all_ids) != 15:
        raise ConstructionMapV12Error(
            "master v28 source-record delta is not exactly fifteen additive rows"
        )
    old_ids = set(old_projected)
    new_ids = set(projected)
    if old_ids - new_ids or new_ids - old_ids != NEW_COORDINATE_MAPPING_IDS:
        raise ConstructionMapV12Error(
            "map v28 coordinate delta is not exactly the three accepted v70 rows"
        )
    if (all_ids - old_all_ids) - NEW_COORDINATE_MAPPING_IDS != (
        all_ids - old_all_ids - new_ids
    ):
        raise ConstructionMapV12Error(
            "the twelve other master-v28 additions are not coordinate-null"
        )
    for record_id, old in old_projected.items():
        current = dict(projected[record_id])
        if old["source_artifact_id"] == "epoch-official-open-seed-v67":
            current.update(
                {
                    "row_id": old["row_id"],
                    "source_artifact_id": old["source_artifact_id"],
                    "source_release_id": old["source_release_id"],
                }
            )
        if current != old:
            raise ConstructionMapV12Error(
                f"map v28 changed an inherited mapped row: {record_id}"
            )


def derive_candidate_projection(
    master_directory: str | Path,
    master_definition_path: str | Path,
) -> dict[str, Any]:
    """Derive and verify v28 projection counts from an actual master candidate."""

    _require_predecessor()
    master_path = Path(master_directory).resolve()
    definition_path = Path(master_definition_path).resolve()
    projection, projected, all_ids = _projection_from_master(
        master_path, definition_path
    )
    _assert_exact_v27_delta(projected, all_ids)
    if projection != EXPECTED_PROJECTION:
        raise ConstructionMapV12Error(
            f"candidate master projection differs from v28 contract: {projection!r}"
        )
    return projection


def definition_document(
    generated_at: str,
    *,
    master_directory: str | Path = MASTER,
    master_definition_path: str | Path = MASTER_DEFINITION,
) -> dict[str, Any]:
    """Return the exact map-v27 structural successor for an actual master v28."""

    generated = _parse_utc(generated_at, label="map v28 generated_at")
    master_path = Path(master_directory).resolve()
    master_definition = Path(master_definition_path).resolve()
    master_generated_at = _parse_utc(
        _master_generated_at(master_definition), label="master v28 generated_at"
    )
    if generated <= master_generated_at:
        raise ConstructionMapV12Error("map v28 must follow construction-master v28")
    projection = derive_candidate_projection(master_path, master_definition)
    predecessor, _ = _regular_json(
        PREDECESSOR_DEFINITION, "accepted map v27 definition"
    )
    result = deepcopy(predecessor)
    result["map_id"] = MAP_ID
    result["generated_at"] = generated_at
    result["expected_projection"] = projection
    result["master"] = {
        "definition": {
            **_checkpoint(master_definition),
            "path": _path_from_sources(master_definition),
        },
        "directory": _path_from_sources(master_path),
        "jsonl": {
            **_checkpoint(master_path / "construction-master.jsonl"),
            "path": _path_from_sources(
                master_path / "construction-master.jsonl"
            ),
        },
        "manifest": {
            **_checkpoint(master_path / MANIFEST_FILENAME),
            "path": _path_from_sources(master_path / MANIFEST_FILENAME),
        },
        "master_id": MASTER_ID,
    }
    payload = _canonical_json(result)
    for token in REJECTED_LINEAGE_TOKENS:
        if token in payload:
            raise ConstructionMapV12Error(
                f"rejected lineage token in map v28: {token.decode('ascii')}"
            )
    return result


def _definition_generated_at(path: Path) -> str:
    document, _ = _regular_json(path, "map v28 definition")
    value = document.get("generated_at")
    _parse_utc(value, label="map v28 generated_at")
    return value


def validate_map_definition_v12(
    definition_path: str | Path,
    *,
    master_directory: str | Path,
    master_definition_path: str | Path,
) -> dict[str, Any]:
    path = Path(definition_path)
    generated_at = _definition_generated_at(path)
    master_generated_at = _master_generated_at(Path(master_definition_path))
    with _runtime_timestamps(generated_at, master_generated_at):
        return _core_validate_map_definition(
            path,
            master_directory=master_directory,
            master_definition_path=master_definition_path,
        )


def _write_definition_stage(path: Path, raw: bytes) -> None:
    with path.open("r+b") as destination:
        destination.write(raw)
        destination.truncate()
        destination.flush()
        os.fsync(destination.fileno())


def _build_bundle_stage(
    destination: Path,
    *,
    definition_path: Path,
    master_directory: Path,
    master_definition_path: Path,
) -> dict[str, Any]:
    generated_at = _definition_generated_at(definition_path)
    master_generated_at = _master_generated_at(master_definition_path)
    with _runtime_timestamps(generated_at, master_generated_at):
        try:
            master_v12.validate_construction_master_v12(
                master_directory,
                definition_path=master_definition_path,
                reproduce=False,
            )
        except master_v12.ConstructionMasterV12Error as error:
            raise ConstructionMapV12Error(str(error)) from error
        definition = _core_validate_map_definition(
            definition_path,
            master_directory=master_directory,
            master_definition_path=master_definition_path,
        )
        added = _core_added_source_record_ids(master_definition_path)
        return _core_build_into(
            master_directory,
            destination,
            definition=definition,
            added_source_record_ids=added,
        )


def _bundle_payloads(directory: Path) -> dict[str, bytes]:
    if directory.is_symlink() or not directory.is_dir():
        raise ConstructionMapV12Error("map v28 stage must be a regular directory")
    return {entry.name: entry.read_bytes() for entry in directory.iterdir()}


def _assert_two_replays(
    first: Path,
    *,
    definition_path: Path,
    master_directory: Path,
    master_definition_path: Path,
) -> None:
    with tempfile.TemporaryDirectory(prefix="construction-map-v28-replay-") as temporary:
        second = Path(temporary) / "bundle"
        second.mkdir()
        first_manifest = _regular_json(first / MANIFEST_FILENAME, "map manifest")[0]
        second_manifest = _build_bundle_stage(
            second,
            definition_path=definition_path,
            master_directory=master_directory,
            master_definition_path=master_definition_path,
        )
        if first_manifest != second_manifest or _bundle_payloads(first) != _bundle_payloads(
            second
        ):
            raise ConstructionMapV12Error(
                "two offline construction-map v28 reconstructions differ"
            )


def _path_timestamp_bounds(path: Path, cutoff: datetime, label: str) -> None:
    if path.is_symlink() or not (path.is_file() or path.is_dir()):
        raise ConstructionMapV12Error(f"{label} must be a regular artifact")
    metadata = path.stat()
    timestamps = [metadata.st_mtime]
    birth = getattr(metadata, "st_birthtime", None)
    if birth is not None:
        timestamps.append(birth)
    if max(timestamps) > cutoff.timestamp() + 0.000_001:
        raise ConstructionMapV12Error(f"{label} post-dates its claimed timestamp")


def _validate_temporal_closure(
    definition_path: Path,
    bundle_path: Path,
    master_definition_path: Path,
    master_directory: Path,
    *,
    validation_wall_clock: datetime,
) -> None:
    generated = _parse_utc(
        _definition_generated_at(definition_path), label="map v28 generated_at"
    )
    master_generated = _parse_utc(
        _master_generated_at(master_definition_path),
        label="master v28 generated_at",
    )
    if generated > validation_wall_clock:
        raise ConstructionMapV12Error("map v28 generated_at exceeds wall clock")
    if master_generated >= generated:
        raise ConstructionMapV12Error("map v28 does not follow master v28")
    for path in (definition_path, bundle_path, *bundle_path.iterdir()):
        _path_timestamp_bounds(path, generated, f"map v28 artifact {path.name}")
    for path in (
        master_definition_path,
        master_directory,
        *master_directory.iterdir(),
    ):
        _path_timestamp_bounds(path, master_generated, f"master v28 artifact {path.name}")


def validate_construction_map_v12(
    directory: str | Path = BUNDLE,
    *,
    master_directory: str | Path = MASTER,
    master_definition_path: str | Path = MASTER_DEFINITION,
    map_definition_path: str | Path = DEFINITION,
    replay_count: int = 2,
    require_accepted_master: bool = True,
    require_frozen: bool = True,
    validation_wall_clock: datetime | None = None,
) -> dict[str, Any]:
    """Validate v28, including two byte-exact offline reconstructions."""

    if replay_count != 2:
        raise ConstructionMapV12Error("map v28 requires exactly two replays")
    _require_predecessor()
    if require_accepted_master:
        _require_accepted_master()
    bundle = Path(directory)
    definition_path = Path(map_definition_path)
    master_path = Path(master_directory)
    master_definition = Path(master_definition_path)
    document, raw = _regular_json(definition_path, "map v28 definition")
    expected = definition_document(
        document["generated_at"],
        master_directory=master_path,
        master_definition_path=master_definition,
    )
    if document != expected or raw != _canonical_json(expected):
        raise ConstructionMapV12Error(
            "map v28 definition is not the exact v27 structural successor"
        )
    generated_at = document["generated_at"]
    master_generated_at = _master_generated_at(master_definition)
    with _runtime_timestamps(generated_at, master_generated_at):
        manifest = _core_validate_static(bundle, frozen=require_frozen)
    _assert_two_replays(
        bundle,
        definition_path=definition_path,
        master_directory=master_path,
        master_definition_path=master_definition,
    )
    _validate_temporal_closure(
        definition_path,
        bundle,
        master_definition,
        master_path,
        validation_wall_clock=_wall_clock(validation_wall_clock),
    )
    payloads = {definition_path.name: raw, **_bundle_payloads(bundle)}
    for name, payload in payloads.items():
        for token in REJECTED_LINEAGE_TOKENS:
            if token in payload:
                raise ConstructionMapV12Error(
                    f"rejected lineage token in map v28 {name}: {token.decode('ascii')}"
                )
    if manifest.get("map_id") != MAP_ID or manifest.get("master", {}).get(
        "rows"
    ) != EXPECTED_PROJECTION["master_rows"]:
        raise ConstructionMapV12Error("map v28 manifest identity or count changed")
    return manifest


def _latest_stage_time(definition_stage: Path, bundle_stage: Path) -> float:
    values: list[float] = []
    for path in (definition_stage, bundle_stage, *bundle_stage.iterdir()):
        metadata = path.stat()
        values.append(metadata.st_mtime)
        birth = getattr(metadata, "st_birthtime", None)
        if birth is not None:
            values.append(birth)
    return max(values)


def _discard_bundle_stage(stage: Path) -> None:
    if not stage.exists() or stage.is_symlink() or not stage.is_dir():
        return
    stage.chmod(0o700)
    for entry in stage.iterdir():
        if entry.is_symlink() or not entry.is_file():
            raise ConstructionMapV12Error(
                "refusing contaminated construction-map v28 stage cleanup"
            )
        entry.chmod(0o600)
    shutil.rmtree(stage)


def _discard_candidate_definition_stage(stage: Path) -> None:
    if not stage.exists() or stage.is_symlink():
        return
    if (
        stage.parent.resolve() != DEFINITION.parent.resolve()
        or not stage.name.startswith(f".{DEFINITION.name}.candidate-")
        or not stage.is_file()
    ):
        raise ConstructionMapV12Error(
            f"refusing unsafe map-v28 candidate cleanup: {stage}"
        )
    stage.chmod(0o600)
    stage.unlink()


def prepare_candidate_construction_map_v12(
    generated_at: str,
) -> tuple[Path, Path]:
    """Build a frozen map from the pinned master stage without publishing it."""

    target = _parse_utc(generated_at, label="candidate map v28 generated_at")
    require_candidate_master()
    _require_predecessor()
    _require_unpublished()
    if target <= _parse_utc(
        CANDIDATE_MASTER_GENERATED_AT,
        label="candidate master v28 generated_at",
    ):
        raise ConstructionMapV12Error(
            "candidate map v28 must follow candidate construction-master v28"
        )
    descriptor, definition_name = tempfile.mkstemp(
        prefix=f".{DEFINITION.name}.candidate-", dir=DEFINITION.parent
    )
    os.close(descriptor)
    definition_stage = Path(definition_name)
    bundle_stage = Path(
        tempfile.mkdtemp(
            prefix=f".{BUNDLE.name}.candidate-", dir=BUNDLE.parent
        )
    )
    complete = False
    try:
        document = definition_document(
            generated_at,
            master_directory=CANDIDATE_MASTER,
            master_definition_path=CANDIDATE_MASTER_DEFINITION,
        )
        _write_definition_stage(definition_stage, _canonical_json(document))
        _build_bundle_stage(
            bundle_stage,
            definition_path=definition_stage,
            master_directory=CANDIDATE_MASTER,
            master_definition_path=CANDIDATE_MASTER_DEFINITION,
        )
        _assert_two_replays(
            bundle_stage,
            definition_path=definition_stage,
            master_directory=CANDIDATE_MASTER,
            master_definition_path=CANDIDATE_MASTER_DEFINITION,
        )
        with _runtime_timestamps(
            generated_at, CANDIDATE_MASTER_GENERATED_AT
        ):
            _core_validate_static(bundle_stage, frozen=False)
        for entry in bundle_stage.iterdir():
            entry.chmod(0o444)
        bundle_stage.chmod(0o555)
        definition_stage.chmod(0o444)
        if _latest_stage_time(definition_stage, bundle_stage) > (
            target.timestamp() + 0.000_001
        ):
            raise ConstructionMapV12Error(
                "candidate map v28 staging exceeded generated_at"
            )
        _require_unpublished()
        complete = True
        return definition_stage, bundle_stage
    finally:
        if not complete:
            _discard_bundle_stage(bundle_stage)
            _discard_candidate_definition_stage(definition_stage)


def validate_candidate_construction_map_v12(
    definition_stage: str | Path,
    bundle_stage: str | Path,
    *,
    validation_wall_clock: datetime | None = None,
) -> dict[str, Any]:
    """Validate a frozen candidate map against the exact pinned master stage."""

    require_candidate_master()
    _require_unpublished()
    return validate_construction_map_v12(
        bundle_stage,
        master_directory=CANDIDATE_MASTER,
        master_definition_path=CANDIDATE_MASTER_DEFINITION,
        map_definition_path=definition_stage,
        require_accepted_master=False,
        validation_wall_clock=validation_wall_clock,
    )


def discard_candidate_construction_map_v12(
    definition_stage: str | Path, bundle_stage: str | Path
) -> None:
    """Discard only hidden map-v28 candidate paths while finals are absent."""

    _require_unpublished()
    definition_path = Path(definition_stage).resolve()
    bundle_path = Path(bundle_stage).resolve()
    if (
        bundle_path.parent != BUNDLE.parent.resolve()
        or not bundle_path.name.startswith(f".{BUNDLE.name}.candidate-")
    ):
        raise ConstructionMapV12Error(
            f"refusing unsafe map-v28 candidate cleanup: {bundle_path}"
        )
    _discard_bundle_stage(bundle_path)
    _discard_candidate_definition_stage(definition_path)


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise ConstructionMapV12Error(
            f"active construction-map v28 publication lock exists: {PUBLICATION_LOCK}"
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
            raise ConstructionMapV12Error(
                f"refusing replacement of construction-map v28: {path}"
            )


def _wait_until(target: datetime) -> None:
    remaining = target.timestamp() - time.time()
    if remaining > 900:
        raise ConstructionMapV12Error("map v28 publication is over 15 minutes ahead")
    while time.time() < target.timestamp():
        time.sleep(min(0.05, target.timestamp() - time.time()))


def publish_construction_map_v12(generated_at: str) -> dict[str, Any]:
    """Double-build privately, freeze, and no-replace publish map v28."""

    target = _parse_utc(generated_at, label="map v28 generated_at")
    _require_predecessor()
    _require_accepted_master()
    for parent in (DEFINITION.parent, BUNDLE.parent):
        if parent.is_symlink() or not parent.is_dir():
            raise ConstructionMapV12Error(f"map output parent is invalid: {parent}")
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
            raw = _canonical_json(definition_document(generated_at))
            _write_definition_stage(definition_stage, raw)
            _build_bundle_stage(
                bundle_stage,
                definition_path=definition_stage,
                master_directory=MASTER,
                master_definition_path=MASTER_DEFINITION,
            )
            _assert_two_replays(
                bundle_stage,
                definition_path=definition_stage,
                master_directory=MASTER,
                master_definition_path=MASTER_DEFINITION,
            )
            generated_text = _definition_generated_at(definition_stage)
            master_generated_at = _master_generated_at(MASTER_DEFINITION)
            with _runtime_timestamps(generated_text, master_generated_at):
                _core_validate_static(bundle_stage, frozen=False)
            for entry in bundle_stage.iterdir():
                entry.chmod(0o444)
            bundle_stage.chmod(0o555)
            definition_stage.chmod(0o444)
            if _latest_stage_time(definition_stage, bundle_stage) > (
                target.timestamp() + 0.000_001
            ):
                raise ConstructionMapV12Error(
                    "map v28 staging exceeded generated_at; refusing publication"
                )
            _wait_until(target)
            validate_construction_map_v12(
                bundle_stage,
                map_definition_path=definition_stage,
                validation_wall_clock=datetime.now(timezone.utc),
            )
            _require_unpublished()
            try:
                # Darwin's atomic RENAME_EXCL path may reject a 0555 source
                # directory. Payload files remain 0444; reopen only the
                # directory inode for the namespace move, then refreeze it.
                bundle_stage.chmod(0o755)
                promote_noreplace(bundle_stage, BUNDLE)
                bundle_published = True
                BUNDLE.chmod(0o555)
                promote_noreplace(definition_stage, DEFINITION)
                definition_published = True
            except SystemExit as error:
                raise ConstructionMapV12Error(str(error)) from error
            return validate_construction_map_v12(
                validation_wall_clock=datetime.now(timezone.utc)
            )
        finally:
            if not bundle_published:
                _discard_bundle_stage(bundle_stage)
            if (
                not bundle_published
                and not definition_published
                and definition_stage.exists()
            ):
                definition_stage.chmod(0o600)
                definition_stage.unlink()


def write_construction_map_v12(
    master_directory: str | Path = MASTER,
    output_directory: str | Path = BUNDLE,
    *,
    master_definition_path: str | Path = MASTER_DEFINITION,
    map_definition_path: str | Path = DEFINITION,
    generated_at: str,
    freeze: bool = True,
) -> dict[str, Any]:
    """Publish only the reserved frozen v28 definition and bundle paths."""

    if (
        Path(master_directory).resolve() != MASTER.resolve()
        or Path(output_directory).resolve() != BUNDLE.resolve()
        or Path(master_definition_path).resolve() != MASTER_DEFINITION.resolve()
        or Path(map_definition_path).resolve() != DEFINITION.resolve()
        or freeze is not True
    ):
        raise ConstructionMapV12Error(
            "construction-map v28 publication paths and frozen mode are reserved"
        )
    return publish_construction_map_v12(generated_at)


build_construction_map_v12 = write_construction_map_v12
is_frozen_map_v12 = _core_is_frozen_map


__all__ = [
    "BUNDLE",
    "BUNDLE_FILES",
    "CANDIDATE_MASTER",
    "CANDIDATE_MASTER_DEFINITION",
    "CANDIDATE_MASTER_GENERATED_AT",
    "CANDIDATE_MASTER_TRANSACTION",
    "ConstructionMapV12Error",
    "DEFINITION",
    "EXPECTED_PROJECTION",
    "FIELDS",
    "MAP_ID",
    "MAP_SCOPE",
    "MASTER",
    "MASTER_DEFINITION",
    "NEW_COORDINATE_MAPPING_IDS",
    "build_construction_map_v12",
    "definition_document",
    "derive_candidate_projection",
    "discard_candidate_construction_map_v12",
    "is_frozen_map_v12",
    "prepare_candidate_construction_map_v12",
    "publish_construction_map_v12",
    "require_candidate_master",
    "validate_candidate_construction_map_v12",
    "validate_construction_map_v12",
    "validate_map_definition_v12",
    "write_construction_map_v12",
]
