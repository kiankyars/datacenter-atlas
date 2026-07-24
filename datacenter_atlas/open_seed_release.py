"""Deterministic offline validator for a frozen open-seed release."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import stat
import tempfile
from typing import Any, Mapping

from .curated import CuratedOfficialSourceAdapter
from .database import initialize
from .epoch import EpochAIAdapter
from .epoch_source_capture import MANIFEST_FILENAME as FETCH_MANIFEST_FILENAME
from .epoch_source_capture import validate_epoch_source_capture
from .publication_release import build_release_documents
from .service import validate_database


DEFINITION_SCHEMA_VERSION = 1
RELEASE_MANIFEST_FILENAME = "manifest.json"
FROZEN_FILE_MODE = 0o444
FROZEN_DIRECTORY_MODE = 0o555


class OpenSeedReleaseError(ValueError):
    """Raised when an input, definition, release, or reconstruction differs."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


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
            raise OpenSeedReleaseError(f"{label} does not exist: {current}") from error
        if stat.S_ISLNK(mode):
            raise OpenSeedReleaseError(f"{label} uses a symlink component: {current}")


def _read_canonical_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    _reject_symlink_components(path, label)
    if not path.is_file():
        raise OpenSeedReleaseError(f"{label} must be an ordinary file")
    raw = path.read_bytes()
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise OpenSeedReleaseError(f"{label} is not valid JSON") from error
    if not isinstance(document, dict) or raw != _canonical_json(document):
        raise OpenSeedReleaseError(f"{label} is not a canonical JSON object")
    return document, raw


def _repo_path(project_root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise OpenSeedReleaseError(f"{label} must be a non-empty relative path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise OpenSeedReleaseError(f"{label} must be a normalized repository-relative path")
    path = project_root.joinpath(*pure.parts)
    _reject_symlink_components(path, label)
    return path


def _definition(path: str | Path) -> tuple[dict[str, Any], Path, Path]:
    definition_path = _lexical_absolute(path)
    document, _ = _read_canonical_object(definition_path, "definition")
    expected_keys = {
        "build",
        "curated_inputs",
        "epoch_capture",
        "expected_epoch_result",
        "expected_release",
        "expected_summary",
        "release_id",
        "schema_version",
        "scope",
    }
    keys = frozenset(document)
    valid_key_sets = {
        frozenset(expected_keys),
        frozenset(expected_keys | {"publication_contract_version"}),
    }
    if (
        keys not in valid_key_sets
        or document["schema_version"] != DEFINITION_SCHEMA_VERSION
    ):
        raise OpenSeedReleaseError("definition schema is invalid")
    publication_contract_version = document.get("publication_contract_version", 1)
    if type(publication_contract_version) is not int or publication_contract_version not in {
        1,
        2,
        3,
        4,
    }:
        raise OpenSeedReleaseError("publication contract version is invalid")
    if definition_path.parent.name != "sources":
        raise OpenSeedReleaseError("definition must reside in the sources directory")
    project_root = definition_path.parent.parent
    _reject_symlink_components(project_root, "project root")
    scope = document["scope"]
    if scope != {
        "commercial_census_parity_claimed": False,
        "epoch_selected_site_count_is_global_census": False,
        "orphan_timeline_imported": False,
        "source_scoped_estimates_only": True,
    }:
        raise OpenSeedReleaseError("definition scope guardrails are invalid")
    return document, definition_path, project_root


def _validate_inputs(
    definition: Mapping[str, Any], project_root: Path
) -> tuple[Path, Path, list[Path]]:
    epoch = definition["epoch_capture"]
    if not isinstance(epoch, dict) or set(epoch) != {
        "archive",
        "directory",
        "fetch_manifest_sha256",
        "map",
        "retrieved_at",
    }:
        raise OpenSeedReleaseError("epoch_capture definition is invalid")
    capture = _repo_path(project_root, epoch["directory"], "Epoch capture")
    manifest = validate_epoch_source_capture(capture)
    manifest_raw = (capture / FETCH_MANIFEST_FILENAME).read_bytes()
    if _sha256(manifest_raw) != epoch["fetch_manifest_sha256"]:
        raise OpenSeedReleaseError("Epoch capture manifest hash differs")
    if manifest["retrieved_at"] != epoch["retrieved_at"]:
        raise OpenSeedReleaseError("Epoch retrieval timestamp differs")
    archive = _repo_path(project_root, epoch["archive"], "Epoch archive")
    map_path = _repo_path(project_root, epoch["map"], "Epoch map")
    if archive.parent != capture or map_path.parent != capture:
        raise OpenSeedReleaseError("Epoch inputs must stay inside the pinned capture")

    inputs = definition["curated_inputs"]
    if not isinstance(inputs, list) or not inputs:
        raise OpenSeedReleaseError("curated_inputs must be a non-empty list")
    curated: list[Path] = []
    seen: set[str] = set()
    for record in inputs:
        if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
            raise OpenSeedReleaseError("curated input record is invalid")
        path = _repo_path(project_root, record["path"], "curated input")
        if record["path"] in seen or not path.is_file():
            raise OpenSeedReleaseError("curated input paths must be unique ordinary files")
        seen.add(record["path"])
        if _sha256(path.read_bytes()) != record["sha256"]:
            raise OpenSeedReleaseError(f"curated input changed: {record['path']}")
        curated.append(path)
    if curated != sorted(curated):
        raise OpenSeedReleaseError("curated inputs must use deterministic path order")
    return archive, map_path, curated


def _rebuild_documents(
    definition: Mapping[str, Any], archive: Path, map_path: Path, curated: list[Path]
) -> dict[str, str]:
    build = definition["build"]
    if not isinstance(build, dict) or set(build) != {"as_of", "recorded_at"}:
        raise OpenSeedReleaseError("build definition is invalid")
    temporary = tempfile.TemporaryDirectory(prefix="open-seed-offline-", dir="/private/tmp")
    connection: sqlite3.Connection | None = None
    try:
        connection, _ = initialize(Path(temporary.name) / "atlas.sqlite")
        epoch_result = EpochAIAdapter().import_file(
            connection,
            archive,
            map_html=map_path,
            retrieved_at=definition["epoch_capture"]["retrieved_at"],
            as_of_date=build["as_of"],
        )
        normalized_epoch_result = json.loads(json.dumps(asdict(epoch_result)))
        if normalized_epoch_result != definition["expected_epoch_result"]:
            raise OpenSeedReleaseError("Epoch import result or warning set differs")
        for path in curated:
            document = json.loads(path.read_text(encoding="utf-8"))
            timestamps = {
                evidence["retrieved_at"] for evidence in document.get("evidence", [])
            }
            if len(timestamps) != 1:
                raise OpenSeedReleaseError(
                    f"curated input lacks one retrieval timestamp: {path.name}"
                )
            CuratedOfficialSourceAdapter().import_file(
                connection, path, retrieved_at=next(iter(timestamps))
            )
        errors = validate_database(connection)
        if errors:
            raise OpenSeedReleaseError(
                "reconstructed database is invalid: " + "; ".join(errors)
            )
        return build_release_documents(
            connection,
            as_of=build["as_of"],
            recorded_at=build["recorded_at"],
            publication_contract_version=definition.get(
                "publication_contract_version", 1
            ),
        )
    finally:
        if connection is not None:
            connection.close()
        temporary.cleanup()


def validate_open_seed_release(
    definition_path: str | Path,
    release_directory: str | Path,
    *,
    require_frozen: bool = True,
) -> dict[str, Any]:
    """Rebuild the release offline and compare every distributed byte."""
    definition, _, project_root = _definition(definition_path)
    archive, map_path, curated = _validate_inputs(definition, project_root)

    release = _lexical_absolute(release_directory)
    _reject_symlink_components(release, "release")
    if not release.is_dir():
        raise OpenSeedReleaseError("release must be an ordinary directory")
    entries = list(release.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise OpenSeedReleaseError("release may contain only ordinary files")
    manifest, manifest_raw = _read_canonical_object(
        release / RELEASE_MANIFEST_FILENAME, "release manifest"
    )
    expected_release = definition["expected_release"]
    if not isinstance(expected_release, dict) or "manifest_sha256" not in expected_release:
        raise OpenSeedReleaseError("expected_release definition is invalid")
    if _sha256(manifest_raw) != expected_release["manifest_sha256"]:
        raise OpenSeedReleaseError("release manifest hash differs")
    for key, value in expected_release.items():
        if key != "manifest_sha256" and manifest.get(key) != value:
            raise OpenSeedReleaseError(f"release manifest fact differs: {key}")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise OpenSeedReleaseError("release manifest file inventory is invalid")
    expected_files = set(files) | {RELEASE_MANIFEST_FILENAME}
    if {path.name for path in entries} != expected_files:
        raise OpenSeedReleaseError("release file set differs from its manifest")
    for filename, record in files.items():
        if not isinstance(record, dict) or set(record) != {"bytes", "sha256"}:
            raise OpenSeedReleaseError(f"release file record is invalid: {filename}")
        raw = (release / filename).read_bytes()
        if {"bytes": len(raw), "sha256": _sha256(raw)} != record:
            raise OpenSeedReleaseError(f"release file changed: {filename}")

    summary, _ = _read_canonical_object(release / "summary.json", "release summary")
    expected_summary = definition["expected_summary"]
    if not isinstance(expected_summary, dict) or any(
        summary.get(key) != value for key, value in expected_summary.items()
    ):
        raise OpenSeedReleaseError("release summary facts differ")

    rebuilt = _rebuild_documents(definition, archive, map_path, curated)
    if set(rebuilt) != expected_files:
        raise OpenSeedReleaseError("offline reconstruction file set differs")
    for filename, text in rebuilt.items():
        if (release / filename).read_bytes() != text.encode("utf-8"):
            raise OpenSeedReleaseError(
                f"offline reconstruction differs byte-for-byte: {filename}"
            )

    if require_frozen:
        if release.stat().st_mode & 0o777 != FROZEN_DIRECTORY_MODE:
            raise OpenSeedReleaseError("release root must have mode 0555")
        wrong_modes = [
            path.name
            for path in entries
            if path.stat().st_mode & 0o777 != FROZEN_FILE_MODE
        ]
        if wrong_modes:
            raise OpenSeedReleaseError(
                "release files must have mode 0444: " + ", ".join(sorted(wrong_modes))
            )
    return manifest
