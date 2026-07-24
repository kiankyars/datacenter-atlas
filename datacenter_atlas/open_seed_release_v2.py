"""Strict mixed-schema validator for the frozen open-seed v57 release.

The legacy validator remains byte-pinned and continues to own schema-1.0-only
releases through v56.  This module validates that frozen v56 base first, then
reconstructs v57 twice while preserving each evidence record's own retrieval
timestamp.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
from typing import Any, Mapping

from .curated import CuratedOfficialSourceAdapter
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .epoch import EpochAIAdapter
from .epoch_source_capture import MANIFEST_FILENAME as FETCH_MANIFEST_FILENAME
from .epoch_source_capture import validate_epoch_source_capture
from .open_seed_release import validate_open_seed_release as validate_legacy_release
from .publication_release import build_release_documents
from .service import validate_database


DEFINITION_SCHEMA_VERSION = 1
RELEASE_MANIFEST_FILENAME = "manifest.json"
FROZEN_FILE_MODE = 0o444
FROZEN_DIRECTORY_MODE = 0o555

V56_DEFINITION = "sources/open-seed-2026-07-20-v56.json"
V56_RELEASE = "releases/2026-07-20-open-seed-v56"
V56_DEFINITION_SHA256 = (
    "b41bf23073c51aed7756f1fa5ae7d081c5d349914b9794531fe0c1010396962c"
)
V56_MANIFEST_SHA256 = (
    "f8bc9b4bef238288f72160e7a21533321b452d7b571d707b1de492a2f62f1cdd"
)
V56_TREE_SHA256 = "c75b3b4b2fb066dce2e8549bdfa6fdbf06412c9885b5a9aeaea7eb36fcfe61d2"

REPLACEMENTS = {
    "sources/curated-official-2026-07-19-nextdc-b2-brisbane-1h26-fitout.json": (
        "sources/curated-official-2026-07-19-nextdc-b2-brisbane-1h26-fitout-v2.json"
    ),
    "sources/curated-official-2026-07-19-nextdc-kl1-kuala-lumpur-1h26-fitout.json": (
        "sources/curated-official-2026-07-19-nextdc-kl1-kuala-lumpur-1h26-fitout-v2.json"
    ),
    "sources/curated-official-2026-07-19-nextdc-m2-melbourne-1h26-fitout.json": (
        "sources/curated-official-2026-07-19-nextdc-m2-melbourne-1h26-fitout-v2.json"
    ),
    "sources/curated-official-2026-07-19-nextdc-p1-perth-1h26-fitout.json": (
        "sources/curated-official-2026-07-19-nextdc-p1-perth-1h26-fitout-v2.json"
    ),
    "sources/curated-official-2026-07-19-nextdc-p2-perth-1h26-fitout.json": (
        "sources/curated-official-2026-07-19-nextdc-p2-perth-1h26-fitout-v2.json"
    ),
}
SUCCESSOR_PINS = {
    "sources/curated-official-2026-07-19-nextdc-b2-brisbane-1h26-fitout-v2.json": (
        "0e5c6c9dc979bc0604a8b49541d6c4f9af548d69b6f7864b99b23893e7d8ea3e"
    ),
    "sources/curated-official-2026-07-19-nextdc-kl1-kuala-lumpur-1h26-fitout-v2.json": (
        "748522f0e5cfbc0c24de6929d986fa886f763d03897fdf97346635daf2797bc4"
    ),
    "sources/curated-official-2026-07-19-nextdc-m2-melbourne-1h26-fitout-v2.json": (
        "fb7ba690ad00ea6734a1299167131ac744c4db11f78dd3d27cbc87490d618134"
    ),
    "sources/curated-official-2026-07-19-nextdc-p1-perth-1h26-fitout-v2.json": (
        "ab8f3acc96ec0e94dc3c7ebcaac321f087c9e7c960ab572436b9eb008de002dc"
    ),
    "sources/curated-official-2026-07-19-nextdc-p2-perth-1h26-fitout-v2.json": (
        "4802ae0d901e31536c56521910c061ca503b01602078d494b684d92e24b06bb7"
    ),
}
ADDITION_PINS = {
    "sources/curated-official-2026-07-20-aligned-iad06-frederick-topout.json": (
        "1321b938e409635e883e6e417beb55ac56736bfc9d956bbefcc062df35192103"
    ),
    "sources/curated-official-2026-07-20-google-bermuda-hundred-chesterfield.json": (
        "cf283bdd697427ea54cc282b37078af2ca4e0ba85aee08352b38427bcc8f4724"
    ),
}
ADDITIONS = frozenset(ADDITION_PINS)


class OpenSeedReleaseV2Error(ValueError):
    """Raised when a v57 definition, input, or release differs."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise OpenSeedReleaseV2Error(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _json_object(raw: bytes, label: str, *, canonical: bool) -> dict[str, Any]:
    try:
        document = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise OpenSeedReleaseV2Error(f"{label} is not valid UTF-8 JSON") from error
    if not isinstance(document, dict):
        raise OpenSeedReleaseV2Error(f"{label} must be a JSON object")
    if canonical and raw != _canonical_json(document):
        raise OpenSeedReleaseV2Error(f"{label} is not canonical JSON")
    return document


def _lexical_absolute(path: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _reject_symlink_components(path: Path, label: str) -> None:
    absolute = _lexical_absolute(path)
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError as error:
            raise OpenSeedReleaseV2Error(
                f"{label} does not exist: {current}"
            ) from error
        if stat.S_ISLNK(mode):
            raise OpenSeedReleaseV2Error(
                f"{label} uses a symlink component: {current}"
            )


def _ordinary_file(path: Path, label: str) -> bytes:
    _reject_symlink_components(path, label)
    if not path.is_file():
        raise OpenSeedReleaseV2Error(f"{label} must be an ordinary file")
    return path.read_bytes()


def _repo_path(project_root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise OpenSeedReleaseV2Error(f"{label} must be a non-empty relative path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise OpenSeedReleaseV2Error(
            f"{label} must be a normalized repository-relative path"
        )
    path = project_root.joinpath(*pure.parts)
    _reject_symlink_components(path, label)
    return path


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise OpenSeedReleaseV2Error(f"frozen tree contains symlink: {relative}")
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
        elif path.is_file():
            raw = path.read_bytes()
            digest.update(
                f"F\0{relative}\0{mode:04o}\0{len(raw)}\0{_sha256(raw)}\n".encode()
            )
        else:
            raise OpenSeedReleaseV2Error(
                f"frozen tree contains unsupported entry: {relative}"
            )
    return digest.hexdigest()


def validate_frozen_v56(project_root: Path) -> dict[str, Any]:
    """Validate the sole frozen base with its pinned legacy validator."""

    definition = project_root / V56_DEFINITION
    release = project_root / V56_RELEASE
    if _sha256(_ordinary_file(definition, "v56 definition")) != V56_DEFINITION_SHA256:
        raise OpenSeedReleaseV2Error("frozen v56 definition hash differs")
    if (
        _sha256(_ordinary_file(release / "manifest.json", "v56 manifest"))
        != V56_MANIFEST_SHA256
    ):
        raise OpenSeedReleaseV2Error("frozen v56 manifest hash differs")
    if _tree_digest(release) != V56_TREE_SHA256:
        raise OpenSeedReleaseV2Error("frozen v56 release tree differs")
    try:
        return validate_legacy_release(definition, release)
    except ValueError as error:
        raise OpenSeedReleaseV2Error("frozen v56 legacy validation failed") from error


def _definition(path: str | Path) -> tuple[dict[str, Any], Path, Path]:
    definition_path = _lexical_absolute(path)
    raw = _ordinary_file(definition_path, "definition")
    document = _json_object(raw, "definition", canonical=True)
    expected_keys = {
        "build",
        "curated_inputs",
        "epoch_capture",
        "expected_epoch_result",
        "expected_release",
        "expected_summary",
        "publication_contract_version",
        "release_id",
        "schema_version",
        "scope",
    }
    if set(document) != expected_keys or document["schema_version"] != 1:
        raise OpenSeedReleaseV2Error("definition schema is invalid")
    if document["publication_contract_version"] != 4:
        raise OpenSeedReleaseV2Error("publication contract version must be 4")
    if definition_path.parent.name != "sources":
        raise OpenSeedReleaseV2Error("definition must reside in the sources directory")
    project_root = definition_path.parent.parent
    if document["release_id"] != "2026-07-20-open-seed-v57":
        raise OpenSeedReleaseV2Error("release_id must identify frozen v57")
    if document["scope"] != {
        "commercial_census_parity_claimed": False,
        "epoch_selected_site_count_is_global_census": False,
        "orphan_timeline_imported": False,
        "source_scoped_estimates_only": True,
    }:
        raise OpenSeedReleaseV2Error("definition scope guardrails are invalid")
    build = document["build"]
    if build != {
        "as_of": "2026-07-20",
        "recorded_at": "2026-07-20T23:56:00Z",
    }:
        raise OpenSeedReleaseV2Error("v57 build timestamp contract differs")
    return document, definition_path, project_root


def _instant(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise OpenSeedReleaseV2Error(f"{label} must be a canonical UTC instant")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise OpenSeedReleaseV2Error(f"{label} is invalid") from error
    return result.astimezone(timezone.utc)


def _expected_v57_rows(project_root: Path) -> list[dict[str, str]]:
    raw = _ordinary_file(project_root / V56_DEFINITION, "v56 definition")
    base = _json_object(raw, "v56 definition", canonical=True)
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 318:
        raise OpenSeedReleaseV2Error("v56 curated inventory differs")
    base_by_path = {row["path"]: row["sha256"] for row in rows}
    if len(base_by_path) != 318 or not set(REPLACEMENTS).issubset(base_by_path):
        raise OpenSeedReleaseV2Error("v56 replacement boundary differs")
    selected = [
        {"path": path, "sha256": digest}
        for path, digest in base_by_path.items()
        if path not in REPLACEMENTS
    ]
    expected_pins = {**SUCCESSOR_PINS, **ADDITION_PINS}
    if set(REPLACEMENTS.values()) != set(SUCCESSOR_PINS):
        raise OpenSeedReleaseV2Error("NEXTDC successor pin boundary differs")
    for path, digest in expected_pins.items():
        source = project_root / path
        if _sha256(_ordinary_file(source, path)) != digest:
            raise OpenSeedReleaseV2Error(f"accepted v57 source hash differs: {path}")
        selected.append({"path": path, "sha256": digest})
    return sorted(selected, key=lambda row: row["path"])


def _validate_selection(paths: list[str]) -> None:
    """Reject duplicates, nondeterminism, and predecessor/successor coexistence."""

    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise OpenSeedReleaseV2Error("curated paths must be sorted and unique")
    selected_paths = set(paths)
    for predecessor, successor in REPLACEMENTS.items():
        selected = {predecessor, successor} & selected_paths
        if selected != {successor}:
            raise OpenSeedReleaseV2Error(
                "predecessor and successor must never be selected together"
            )


def _evidence_timestamps(
    source: Mapping[str, Any], *, cutoff: datetime, label: str
) -> tuple[str, ...]:
    """Inventory every first-class retrieval timestamp and enforce the cutoff."""

    evidence = source.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise OpenSeedReleaseV2Error(f"curated evidence is empty: {label}")
    timestamps: list[str] = []
    for index, item in enumerate(evidence):
        if not isinstance(item, dict) or "retrieved_at" not in item:
            raise OpenSeedReleaseV2Error(
                f"curated evidence timestamp is missing: {label}[{index}]"
            )
        value = item["retrieved_at"]
        if _instant(value, f"{label} evidence[{index}].retrieved_at") > cutoff:
            raise OpenSeedReleaseV2Error(
                f"curated evidence post-dates build.recorded_at: {label}"
            )
        timestamps.append(value)
    if source.get("schema_version") == "1.0" and len(set(timestamps)) != 1:
        raise OpenSeedReleaseV2Error(
            f"schema 1.0 input must use one evidence timestamp: {label}"
        )
    return tuple(timestamps)


def _validate_inputs(
    definition: Mapping[str, Any], project_root: Path
) -> tuple[Path, Path, list[tuple[Path, dict[str, Any]]], tuple[str, ...]]:
    epoch = definition["epoch_capture"]
    if not isinstance(epoch, dict) or set(epoch) != {
        "archive",
        "directory",
        "fetch_manifest_sha256",
        "map",
        "retrieved_at",
    }:
        raise OpenSeedReleaseV2Error("epoch_capture definition is invalid")
    capture = _repo_path(project_root, epoch["directory"], "Epoch capture")
    manifest = validate_epoch_source_capture(capture)
    manifest_raw = _ordinary_file(capture / FETCH_MANIFEST_FILENAME, "Epoch manifest")
    if _sha256(manifest_raw) != epoch["fetch_manifest_sha256"]:
        raise OpenSeedReleaseV2Error("Epoch capture manifest hash differs")
    if manifest["retrieved_at"] != epoch["retrieved_at"]:
        raise OpenSeedReleaseV2Error("Epoch retrieval timestamp differs")
    archive = _repo_path(project_root, epoch["archive"], "Epoch archive")
    map_path = _repo_path(project_root, epoch["map"], "Epoch map")
    if archive.parent != capture or map_path.parent != capture:
        raise OpenSeedReleaseV2Error("Epoch inputs must stay inside the pinned capture")

    inputs = definition["curated_inputs"]
    if inputs != _expected_v57_rows(project_root):
        raise OpenSeedReleaseV2Error(
            "curated inputs are not the exact five-replacement/two-addition v56 successor"
        )
    if len(inputs) != 320:
        raise OpenSeedReleaseV2Error("v57 must contain exactly 320 curated inputs")
    paths = [row["path"] for row in inputs]
    _validate_selection(paths)

    cutoff = _instant(definition["build"]["recorded_at"], "build.recorded_at")
    parsed: list[tuple[Path, dict[str, Any]]] = []
    timestamps = [epoch["retrieved_at"]]
    for record in inputs:
        path = _repo_path(project_root, record["path"], "curated input")
        raw = _ordinary_file(path, "curated input")
        if stat.S_IMODE(path.stat().st_mode) != 0o644:
            raise OpenSeedReleaseV2Error(
                f"curated input mode must be 0644: {record['path']}"
            )
        if _sha256(raw) != record["sha256"]:
            raise OpenSeedReleaseV2Error(f"curated input changed: {record['path']}")
        source = _json_object(raw, f"curated input {record['path']}", canonical=False)
        version = source.get("schema_version")
        if version not in {"1.0", "1.1"}:
            raise OpenSeedReleaseV2Error(f"unsupported curated schema: {version!r}")
        source_times = _evidence_timestamps(
            source, cutoff=cutoff, label=record["path"]
        )
        timestamps.extend(source_times)
        parsed.append((path, source))
    return archive, map_path, parsed, tuple(timestamps)


def _rebuild_documents(
    definition: Mapping[str, Any],
    archive: Path,
    map_path: Path,
    curated: list[tuple[Path, dict[str, Any]]],
) -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="open-seed-v57-offline-", dir="/private/tmp") as td:
        connection, _ = initialize(Path(td) / "atlas.sqlite")
        try:
            epoch_result = EpochAIAdapter().import_file(
                connection,
                archive,
                map_html=map_path,
                retrieved_at=definition["epoch_capture"]["retrieved_at"],
                as_of_date=definition["build"]["as_of"],
            )
            normalized = json.loads(json.dumps(asdict(epoch_result)))
            if normalized != definition["expected_epoch_result"]:
                raise OpenSeedReleaseV2Error("Epoch import result or warning set differs")
            for path, source in curated:
                if source["schema_version"] == "1.0":
                    timestamps = {
                        item["retrieved_at"] for item in source["evidence"]
                    }
                    CuratedOfficialSourceAdapter().import_file(
                        connection, path, retrieved_at=next(iter(timestamps))
                    )
                else:
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        path,
                        recorded_at=definition["build"]["recorded_at"],
                    )
            errors = validate_database(connection)
            if errors:
                raise OpenSeedReleaseV2Error(
                    "reconstructed database is invalid: " + "; ".join(errors)
                )
            return build_release_documents(
                connection,
                as_of=definition["build"]["as_of"],
                recorded_at=definition["build"]["recorded_at"],
                publication_contract_version=4,
            )
        finally:
            connection.close()


def validate_open_seed_release_v2(
    definition_path: str | Path,
    release_directory: str | Path,
    *,
    require_frozen: bool = True,
) -> dict[str, Any]:
    """Validate v56 lineage and reconstruct every v57 output byte twice offline."""

    definition, _, project_root = _definition(definition_path)
    validate_frozen_v56(project_root)
    archive, map_path, curated, timestamps = _validate_inputs(definition, project_root)
    if not timestamps:
        raise OpenSeedReleaseV2Error("retrieval inventory must not be empty")

    release = _lexical_absolute(release_directory)
    _reject_symlink_components(release, "release")
    valid_release_names = {
        definition["release_id"],
    }
    is_private_stage = release.name.startswith(f".{definition['release_id']}.")
    if not release.is_dir() or (
        release.name not in valid_release_names and not is_private_stage
    ):
        raise OpenSeedReleaseV2Error("release directory identity differs")
    entries = list(release.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise OpenSeedReleaseV2Error("release may contain only ordinary files")
    manifest_raw = _ordinary_file(release / "manifest.json", "release manifest")
    manifest = _json_object(manifest_raw, "release manifest", canonical=True)
    expected_release = definition["expected_release"]
    if not isinstance(expected_release, dict) or "manifest_sha256" not in expected_release:
        raise OpenSeedReleaseV2Error("expected_release definition is invalid")
    if _sha256(manifest_raw) != expected_release["manifest_sha256"]:
        raise OpenSeedReleaseV2Error("release manifest hash differs")
    for key, value in expected_release.items():
        if key != "manifest_sha256" and manifest.get(key) != value:
            raise OpenSeedReleaseV2Error(f"release manifest fact differs: {key}")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise OpenSeedReleaseV2Error("release manifest file inventory is invalid")
    expected_files = set(files) | {"manifest.json"}
    if {path.name for path in entries} != expected_files:
        raise OpenSeedReleaseV2Error("release file set differs from its manifest")
    for filename, record in files.items():
        path = release / filename
        raw = _ordinary_file(path, f"release file {filename}")
        if not isinstance(record, dict) or record != {
            "bytes": len(raw),
            "sha256": _sha256(raw),
        }:
            raise OpenSeedReleaseV2Error(f"release file changed: {filename}")

    summary_raw = _ordinary_file(release / "summary.json", "release summary")
    summary = _json_object(summary_raw, "release summary", canonical=True)
    expected_summary = definition["expected_summary"]
    if not isinstance(expected_summary, dict) or any(
        summary.get(key) != value for key, value in expected_summary.items()
    ):
        raise OpenSeedReleaseV2Error("release summary facts differ")

    first = _rebuild_documents(definition, archive, map_path, curated)
    second = _rebuild_documents(definition, archive, map_path, curated)
    if first != second:
        raise OpenSeedReleaseV2Error("two offline reconstructions differ")
    if set(first) != expected_files:
        raise OpenSeedReleaseV2Error("offline reconstruction file set differs")
    for filename, text in first.items():
        if (release / filename).read_bytes() != text.encode("utf-8"):
            raise OpenSeedReleaseV2Error(
                f"offline reconstruction differs byte-for-byte: {filename}"
            )

    if require_frozen:
        if stat.S_IMODE(release.stat().st_mode) != FROZEN_DIRECTORY_MODE:
            raise OpenSeedReleaseV2Error("release root must have mode 0555")
        wrong_modes = [
            path.name
            for path in entries
            if stat.S_IMODE(path.stat().st_mode) != FROZEN_FILE_MODE
        ]
        if wrong_modes:
            raise OpenSeedReleaseV2Error(
                "release files must have mode 0444: " + ", ".join(sorted(wrong_modes))
            )
    return manifest
