#!/usr/bin/env python3
"""Extract every explicit data-centre tag from one verified OSM Planet PBF.

This stage deliberately emits another OSM PBF.  It does not convert relations
to areas or GeoJSON: ordinary site relations are valid source records and must
survive for a later, relation-aware materialization stage.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from typing import Any, Callable, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(PROJECT_ROOT))

from datacenter_atlas.ohsome import DATA_CENTER_FILTER
from datacenter_atlas.taginfo_targets import explicit_tag_pairs

if __package__ in {None, ""}:
    import fetch_osm_planet as planet_fetch
else:
    from . import fetch_osm_planet as planet_fetch


EXTRACTION_SCHEMA_VERSION = 1
EXTRACTION_PIPELINE = "openstreetmap_planet_data_center_extraction"
EXPECTED_TAG_PAIR_COUNT = 92
OUTPUT_FILENAME = f"planet-{planet_fetch.PLANET_DATE_TOKEN}-data-centers.osm.pbf"
MANIFEST_FILENAME = "extract-manifest.json"
GENERATOR = "DataCenterAtlas/0.1 planet-data-center-filter"
OSMIUM_LICENSE = "GPL-3.0-or-later"


class ExtractionError(ValueError):
    """Raised when source verification or extraction integrity fails."""


@dataclass(frozen=True, slots=True)
class ExtractionPlan:
    source_path: Path
    output_path: Path
    temporary_output_path: Path
    manifest_path: Path
    temporary_manifest_path: Path
    osmium_executable: str
    filter_expressions: tuple[str, ...]
    version_command: tuple[str, ...]
    tags_filter_command: tuple[str, ...]
    fileinfo_command: tuple[str, ...]

    def dry_run_document(self) -> dict[str, Any]:
        return {
            "schema_version": EXTRACTION_SCHEMA_VERSION,
            "pipeline": EXTRACTION_PIPELINE,
            "dry_run": True,
            "source_path": str(self.source_path),
            "output_path": str(self.output_path),
            "temporary_output_path": str(self.temporary_output_path),
            "manifest_path": str(self.manifest_path),
            "temporary_manifest_path": str(self.temporary_manifest_path),
            "filter": filter_manifest_document(self.filter_expressions),
            "commands": {
                "version": list(self.version_command),
                "tags_filter": list(self.tags_filter_command),
                "fileinfo": list(self.fileinfo_command),
            },
        }


@dataclass(frozen=True, slots=True)
class VerifiedSource:
    path: Path
    snapshot_date: str
    source_url: str
    bytes: int
    md5: str
    sha256: str
    fetch_manifest_path: Path | None
    fetch_manifest_sha256: str | None

    @property
    def verification_mode(self) -> str:
        if self.fetch_manifest_path is None:
            return "exact_size_and_md5"
        return "completed_fetch_manifest_plus_exact_size_and_md5"

    def manifest_document(self) -> dict[str, Any]:
        fetch_manifest = None
        if self.fetch_manifest_path is not None:
            fetch_manifest = {
                "path": self.fetch_manifest_path.name,
                "sha256": self.fetch_manifest_sha256,
            }
        return {
            "path": self.path.name,
            "url": self.source_url,
            "snapshot_date": self.snapshot_date,
            "bytes": self.bytes,
            "md5": self.md5,
            "sha256": self.sha256,
            "verification": {
                "mode": self.verification_mode,
                "exact_size": True,
                "official_md5": True,
                "verified_before_extraction": True,
            },
            "fetch_manifest": fetch_manifest,
        }


Runner = Callable[..., subprocess.CompletedProcess[str]]
Clock = Callable[[], str]


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _absolute(path: str | Path) -> Path:
    """Make a path absolute without dereferencing a possibly hostile symlink."""
    return Path(os.path.abspath(os.fspath(path)))


def osmium_filter_expressions(
    tag_filter: str = DATA_CENTER_FILTER,
) -> tuple[str, ...]:
    pairs = explicit_tag_pairs(tag_filter)
    if len(pairs) != EXPECTED_TAG_PAIR_COUNT:
        raise ExtractionError(
            f"shared data-centre filter has {len(pairs)} equality pairs; "
            f"expected exactly {EXPECTED_TAG_PAIR_COUNT}"
        )
    return tuple(f"nwr/{key}={value}" for key, value in pairs)


def _temporary_output_path(output_path: Path) -> Path:
    return output_path.with_name(f".{output_path.name}.extracting.osm.pbf")


def _temporary_manifest_path(manifest_path: Path) -> Path:
    return manifest_path.with_name(f".{manifest_path.name}.extracting.tmp")


def build_command_plan(
    source_path: str | Path,
    output_path: str | Path,
    manifest_path: str | Path,
    *,
    osmium_executable: str = "osmium",
) -> ExtractionPlan:
    source = _absolute(source_path)
    output = _absolute(output_path)
    manifest = _absolute(manifest_path)
    temporary_output = _temporary_output_path(output)
    temporary_manifest = _temporary_manifest_path(manifest)
    all_paths = (source, output, manifest, temporary_output, temporary_manifest)
    if len(set(all_paths)) != len(all_paths):
        raise ExtractionError("source, output, manifest, and temporary paths must be distinct")
    if not output.name.endswith(".osm.pbf"):
        raise ExtractionError("extraction output filename must end with .osm.pbf")
    if output.parent != manifest.parent:
        raise ExtractionError("output PBF and manifest must be in the same directory")
    expressions = osmium_filter_expressions()
    executable = os.fspath(osmium_executable)
    version_command = (executable, "--version")
    tags_filter_command = (
        executable,
        "tags-filter",
        "--no-progress",
        "--fsync",
        f"--generator={GENERATOR}",
        "--output",
        str(temporary_output),
        str(source),
        *expressions,
    )
    fileinfo_command = (
        executable,
        "fileinfo",
        "--extended",
        "--json",
        "--no-progress",
        str(temporary_output),
    )
    return ExtractionPlan(
        source_path=source,
        output_path=output,
        temporary_output_path=temporary_output,
        manifest_path=manifest,
        temporary_manifest_path=temporary_manifest,
        osmium_executable=executable,
        filter_expressions=expressions,
        version_command=version_command,
        tags_filter_command=tags_filter_command,
        fileinfo_command=fileinfo_command,
    )


def resolve_osmium(executable: str = "osmium") -> str:
    candidate = shutil.which(executable)
    if candidate is None:
        raise ExtractionError(f"osmium executable is not installed or not on PATH: {executable}")
    try:
        resolved = Path(candidate).resolve(strict=True)
        mode = resolved.stat().st_mode
    except OSError as error:
        raise ExtractionError(f"cannot inspect osmium executable: {candidate}") from error
    if not stat.S_ISREG(mode) or not os.access(resolved, os.X_OK):
        raise ExtractionError(f"osmium executable is not an executable regular file: {resolved}")
    return str(resolved)


def _require_regular_file(path: Path, *, label: str) -> None:
    if path.is_symlink():
        raise ExtractionError(f"refusing {label} symlink: {path}")
    try:
        mode = path.stat().st_mode
    except FileNotFoundError as error:
        raise ExtractionError(f"{label} is missing: {path}") from error
    if not stat.S_ISREG(mode):
        raise ExtractionError(f"{label} is not a regular file: {path}")


def _hash_file(path: Path) -> dict[str, str]:
    hashers = {name: hashlib.new(name) for name in ("md5", "sha256")}
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            for hasher in hashers.values():
                hasher.update(chunk)
    return {name: hasher.hexdigest() for name, hasher in hashers.items()}


def _read_json_file(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    _require_regular_file(path, label=label)
    raw = path.read_bytes()
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExtractionError(f"{label} is not valid UTF-8 JSON: {path}") from error
    if not isinstance(document, dict):
        raise ExtractionError(f"{label} must be a JSON object: {path}")
    return document, hashlib.sha256(raw).hexdigest()


def _expect_equal(actual: Any, expected: Any, *, field: str, label: str) -> None:
    if actual != expected:
        raise ExtractionError(
            f"{label} {field} is {actual!r}; expected {expected!r}"
        )


def validate_fetch_manifest(
    document: Mapping[str, Any],
    *,
    source_path: Path,
    source_bytes: int,
    source_md5: str,
    source_sha256: str,
    expected_snapshot_date: str,
    expected_filename: str,
    expected_source_url: str,
    expected_size: int,
    expected_md5: str,
) -> None:
    label = "Planet fetch manifest"
    _expect_equal(document.get("schema_version"), 1, field="schema_version", label=label)
    _expect_equal(
        document.get("pipeline"),
        "openstreetmap_planet_fetch",
        field="pipeline",
        label=label,
    )
    _expect_equal(document.get("state"), "completed", field="state", label=label)
    _expect_equal(
        document.get("snapshot_date"),
        expected_snapshot_date,
        field="snapshot_date",
        label=label,
    )

    source = document.get("source")
    if not isinstance(source, Mapping):
        raise ExtractionError(f"{label} source must be an object")
    for field, expected in (
        ("url", expected_source_url),
        ("md5_url", f"{expected_source_url}.md5"),
        ("filename", expected_filename),
        ("expected_bytes", expected_size),
        ("expected_md5", expected_md5.lower()),
    ):
        _expect_equal(source.get(field), expected, field=f"source.{field}", label=label)

    sidecar = document.get("sidecar")
    if not isinstance(sidecar, Mapping):
        raise ExtractionError(f"{label} sidecar must be an object")
    for field, expected in (
        ("url", f"{expected_source_url}.md5"),
        ("path", f"{expected_filename}.md5"),
        ("md5", expected_md5.lower()),
    ):
        _expect_equal(sidecar.get(field), expected, field=f"sidecar.{field}", label=label)
    sidecar_sha256 = sidecar.get("sha256")
    if not (
        isinstance(sidecar_sha256, str)
        and len(sidecar_sha256) == 64
        and all(character in "0123456789abcdef" for character in sidecar_sha256)
    ):
        raise ExtractionError(f"{label} sidecar.sha256 must be a lowercase SHA256")

    source_input = document.get("input")
    if not isinstance(source_input, Mapping):
        raise ExtractionError(f"{label} input must be an object")
    for field, expected in (
        ("path", source_path.name),
        ("bytes", source_bytes),
        ("md5", source_md5),
        ("sha256", source_sha256),
    ):
        _expect_equal(source_input.get(field), expected, field=f"input.{field}", label=label)

    verification = document.get("verification")
    if not isinstance(verification, Mapping):
        raise ExtractionError(f"{label} verification must be an object")
    for field in ("exact_size", "official_md5", "verified_before_extraction"):
        if verification.get(field) is not True:
            raise ExtractionError(f"{label} verification.{field} must be true")

    rights = document.get("rights")
    if not isinstance(rights, Mapping):
        raise ExtractionError(f"{label} rights must be an object")
    for field, expected in (
        ("license", planet_fetch.OSM_LICENSE),
        ("attribution", planet_fetch.OSM_ATTRIBUTION),
        ("copyright_url", planet_fetch.OSM_COPYRIGHT_URL),
    ):
        _expect_equal(rights.get(field), expected, field=f"rights.{field}", label=label)


def verify_source(
    source_path: str | Path,
    *,
    fetch_manifest_path: str | Path | None = None,
    expected_snapshot_date: str = planet_fetch.PLANET_SNAPSHOT_DATE,
    expected_filename: str = planet_fetch.PLANET_FILENAME,
    expected_source_url: str = planet_fetch.PLANET_URL,
    expected_size: int = planet_fetch.PLANET_SIZE_BYTES,
    expected_md5: str = planet_fetch.PLANET_MD5,
) -> VerifiedSource:
    source = _absolute(source_path)
    if source.name != expected_filename:
        raise ExtractionError(
            f"Planet source filename is {source.name!r}; expected {expected_filename!r}"
        )
    _require_regular_file(source, label="Planet source PBF")
    actual_size = source.stat().st_size
    if actual_size != expected_size:
        raise ExtractionError(
            f"Planet source PBF is {actual_size} bytes; expected exactly {expected_size}"
        )
    hashes = _hash_file(source)
    if not hmac.compare_digest(hashes["md5"], expected_md5.lower()):
        raise ExtractionError(
            f"Planet source PBF MD5 is {hashes['md5']}; expected {expected_md5.lower()}"
        )

    manifest: Path | None = None
    manifest_sha256: str | None = None
    if fetch_manifest_path is not None:
        manifest = _absolute(fetch_manifest_path)
        if manifest.parent != source.parent:
            raise ExtractionError(
                "Planet fetch manifest must be adjacent to its source PBF"
            )
        manifest_document, manifest_sha256 = _read_json_file(
            manifest, label="Planet fetch manifest"
        )
        validate_fetch_manifest(
            manifest_document,
            source_path=source,
            source_bytes=actual_size,
            source_md5=hashes["md5"],
            source_sha256=hashes["sha256"],
            expected_snapshot_date=expected_snapshot_date,
            expected_filename=expected_filename,
            expected_source_url=expected_source_url,
            expected_size=expected_size,
            expected_md5=expected_md5,
        )

    return VerifiedSource(
        path=source,
        snapshot_date=expected_snapshot_date,
        source_url=expected_source_url,
        bytes=actual_size,
        md5=hashes["md5"],
        sha256=hashes["sha256"],
        fetch_manifest_path=manifest,
        fetch_manifest_sha256=manifest_sha256,
    )


def filter_manifest_document(expressions: Sequence[str]) -> dict[str, Any]:
    pairs = explicit_tag_pairs(DATA_CENTER_FILTER)
    expected_expressions = tuple(f"nwr/{key}={value}" for key, value in pairs)
    if tuple(expressions) != expected_expressions:
        raise ExtractionError("osmium expressions do not match the shared data-centre filter")
    return {
        "source_filter_expression": DATA_CENTER_FILTER,
        "source_filter_sha256": hashlib.sha256(
            DATA_CENTER_FILTER.encode("utf-8")
        ).hexdigest(),
        "equality_pair_count": len(pairs),
        "exact_tag_pairs": [
            {"key": key, "value": value} for key, value in pairs
        ],
        "osmium_expressions": list(expressions),
        "object_types": ["node", "way", "relation"],
        "match_scope": "all_relations_including_non_area_relations",
        "referenced_nodes_and_members_retained": True,
        "omit_referenced_flag_used": False,
        "output_object_counts_include_references": True,
        "converted_to_geojson": False,
    }


def _run_command(runner: Runner, command: Sequence[str], *, label: str) -> str:
    try:
        result = runner(
            list(command),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as error:
        raise ExtractionError(f"could not execute {label}: {error}") from error
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        detail = f": {stderr}" if stderr else ""
        raise ExtractionError(
            f"{label} failed with exit code {result.returncode}{detail}"
        )
    return (result.stdout or "").strip()


def _osmium_version(runner: Runner, command: Sequence[str]) -> dict[str, Any]:
    output = _run_command(runner, command, label="osmium version check")
    if not output:
        raise ExtractionError("osmium version check returned no version text")
    return {"first_line": output.splitlines()[0], "output": output}


def _nonnegative_integer(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ExtractionError(f"osmium fileinfo {field} must be a non-negative integer")
    return value


def normalize_fileinfo(
    stdout: str,
    *,
    output_name: str,
    output_bytes: int,
) -> dict[str, Any]:
    try:
        document = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise ExtractionError("osmium fileinfo did not return valid JSON") from error
    if not isinstance(document, dict):
        raise ExtractionError("osmium fileinfo JSON must be an object")
    file_section = document.get("file")
    header = document.get("header")
    data = document.get("data")
    if not isinstance(file_section, Mapping):
        raise ExtractionError("osmium fileinfo JSON has no file object")
    if not isinstance(header, Mapping):
        raise ExtractionError("osmium fileinfo JSON has no header object")
    if not isinstance(data, Mapping):
        raise ExtractionError("osmium fileinfo JSON has no extended data object")
    if str(file_section.get("format", "")).upper() != "PBF":
        raise ExtractionError("osmium fileinfo output format is not PBF")
    _expect_equal(
        file_section.get("size"),
        output_bytes,
        field="file.size",
        label="osmium fileinfo",
    )
    count = data.get("count")
    if not isinstance(count, Mapping):
        raise ExtractionError("osmium fileinfo JSON has no data.count object")
    counts = {
        object_type: _nonnegative_integer(
            count.get(object_type), field=f"data.count.{object_type}"
        )
        for object_type in ("nodes", "ways", "relations")
    }
    if "changesets" in count:
        counts["changesets"] = _nonnegative_integer(
            count.get("changesets"), field="data.count.changesets"
        )
    timestamps = data.get("timestamp")
    if not isinstance(timestamps, Mapping):
        raise ExtractionError("osmium fileinfo JSON has no data.timestamp object")
    normalized_timestamps = {
        "first": timestamps.get("first"),
        "last": timestamps.get("last"),
    }
    for field, value in normalized_timestamps.items():
        if value is not None and not isinstance(value, str):
            raise ExtractionError(
                f"osmium fileinfo data.timestamp.{field} must be a string or null"
            )
    return {
        "file": {
            "name": output_name,
            "format": file_section.get("format"),
            "compression": file_section.get("compression"),
            "size": output_bytes,
        },
        "header": dict(header),
        "bounds": {
            "header": header.get("boxes"),
            "data": data.get("bbox"),
        },
        "timestamps": normalized_timestamps,
        "object_counts_including_references": counts,
        "objects_ordered": data.get("objects_ordered"),
        "multiple_versions": data.get("multiple_versions"),
        "crc32": data.get("crc32"),
    }


def _json_bytes(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _prepare_atomic_file(path: Path, payload: bytes, *, label: str) -> None:
    if path.is_symlink():
        raise ExtractionError(f"refusing {label} symlink: {path}")
    try:
        with path.open("xb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError as error:
        raise ExtractionError(f"refusing to overwrite existing {label}: {path}") from error


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _cleanup_owned_temporary(path: Path) -> None:
    if path.is_symlink():
        return
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def _assert_publish_paths_available(plan: ExtractionPlan) -> None:
    for path, label in (
        (plan.temporary_output_path, "temporary extraction output"),
        (plan.temporary_manifest_path, "temporary extraction manifest"),
    ):
        if path.exists() or path.is_symlink():
            raise ExtractionError(f"refusing to overwrite existing {label}: {path}")


def _output_hashes(path: Path) -> dict[str, Any]:
    _require_regular_file(path, label="extracted PBF")
    return {"bytes": path.stat().st_size, **_hash_file(path)}


def _expected_source_manifest(source: VerifiedSource) -> dict[str, Any]:
    return source.manifest_document()


def validate_extraction_manifest(
    document: Mapping[str, Any],
    *,
    plan: ExtractionPlan,
    source: VerifiedSource,
) -> None:
    label = "extraction manifest"
    _expect_equal(
        document.get("schema_version"),
        EXTRACTION_SCHEMA_VERSION,
        field="schema_version",
        label=label,
    )
    _expect_equal(document.get("pipeline"), EXTRACTION_PIPELINE, field="pipeline", label=label)
    _expect_equal(document.get("state"), "completed", field="state", label=label)
    _expect_equal(
        document.get("snapshot_date"),
        source.snapshot_date,
        field="snapshot_date",
        label=label,
    )
    _expect_equal(
        document.get("source"),
        _expected_source_manifest(source),
        field="source",
        label=label,
    )
    _expect_equal(
        document.get("filter"),
        filter_manifest_document(plan.filter_expressions),
        field="filter",
        label=label,
    )
    rights = document.get("rights")
    expected_rights = {
        "license": planet_fetch.OSM_LICENSE,
        "attribution": planet_fetch.OSM_ATTRIBUTION,
        "copyright_url": planet_fetch.OSM_COPYRIGHT_URL,
    }
    _expect_equal(rights, expected_rights, field="rights", label=label)

    output = document.get("output")
    if not isinstance(output, Mapping):
        raise ExtractionError(f"{label} output must be an object")
    _expect_equal(output.get("path"), plan.output_path.name, field="output.path", label=label)
    current = _output_hashes(plan.output_path)
    for field in ("bytes", "md5", "sha256"):
        _expect_equal(
            output.get(field), current[field], field=f"output.{field}", label=label
        )
    fileinfo = document.get("fileinfo")
    if not isinstance(fileinfo, Mapping):
        raise ExtractionError(f"{label} fileinfo must be an object")
    counts = fileinfo.get("object_counts_including_references")
    if not isinstance(counts, Mapping):
        raise ExtractionError(
            f"{label} fileinfo.object_counts_including_references must be an object"
        )
    for object_type in ("nodes", "ways", "relations"):
        _nonnegative_integer(
            counts.get(object_type),
            field=f"manifest.fileinfo.object_counts_including_references.{object_type}",
        )


def _load_existing_extraction(
    plan: ExtractionPlan,
    source: VerifiedSource,
) -> dict[str, Any] | None:
    output_exists = plan.output_path.exists() or plan.output_path.is_symlink()
    manifest_exists = plan.manifest_path.exists() or plan.manifest_path.is_symlink()
    if not output_exists and not manifest_exists:
        return None
    if output_exists != manifest_exists:
        raise ExtractionError(
            "existing extraction is incomplete; output and manifest must either "
            "both exist or both be absent"
        )
    _require_regular_file(plan.output_path, label="existing extracted PBF")
    document, _ = _read_json_file(plan.manifest_path, label="extraction manifest")
    validate_extraction_manifest(document, plan=plan, source=source)
    return document


def extract_planet(
    source_path: str | Path,
    output_path: str | Path,
    manifest_path: str | Path,
    *,
    fetch_manifest_path: str | Path | None = None,
    osmium_executable: str = "osmium",
    expected_snapshot_date: str = planet_fetch.PLANET_SNAPSHOT_DATE,
    expected_filename: str = planet_fetch.PLANET_FILENAME,
    expected_source_url: str = planet_fetch.PLANET_URL,
    expected_size: int = planet_fetch.PLANET_SIZE_BYTES,
    expected_md5: str = planet_fetch.PLANET_MD5,
    runner: Runner = subprocess.run,
    clock: Clock = utc_now,
    invocation: Sequence[str] | None = None,
) -> dict[str, Any]:
    plan = build_command_plan(
        source_path,
        output_path,
        manifest_path,
        osmium_executable=osmium_executable,
    )
    source = verify_source(
        plan.source_path,
        fetch_manifest_path=fetch_manifest_path,
        expected_snapshot_date=expected_snapshot_date,
        expected_filename=expected_filename,
        expected_source_url=expected_source_url,
        expected_size=expected_size,
        expected_md5=expected_md5,
    )
    existing = _load_existing_extraction(plan, source)
    if existing is not None:
        return existing

    plan.output_path.parent.mkdir(parents=True, exist_ok=True)
    plan.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _assert_publish_paths_available(plan)
    started_at = clock()
    output_published = False
    manifest_published = False
    try:
        version = _osmium_version(runner, plan.version_command)
        _run_command(runner, plan.tags_filter_command, label="osmium tags-filter")
        _require_regular_file(plan.temporary_output_path, label="temporary extracted PBF")
        output_hashes = _output_hashes(plan.temporary_output_path)
        if output_hashes["bytes"] <= 0:
            raise ExtractionError("osmium tags-filter produced an empty PBF file")
        fileinfo_stdout = _run_command(
            runner, plan.fileinfo_command, label="osmium fileinfo"
        )
        fileinfo = normalize_fileinfo(
            fileinfo_stdout,
            output_name=plan.output_path.name,
            output_bytes=output_hashes["bytes"],
        )
        manifest: dict[str, Any] = {
            "schema_version": EXTRACTION_SCHEMA_VERSION,
            "pipeline": EXTRACTION_PIPELINE,
            "state": "completed",
            "started_at": started_at,
            "finished_at": clock(),
            "snapshot_date": source.snapshot_date,
            "invocation": list(invocation or ()),
            "source": source.manifest_document(),
            "filter": filter_manifest_document(plan.filter_expressions),
            "tool": {
                "name": "osmium-tool",
                "license": OSMIUM_LICENSE,
                "executable": plan.osmium_executable,
                "version": version,
                "commands": {
                    "version": list(plan.version_command),
                    "tags_filter": list(plan.tags_filter_command),
                    "fileinfo": list(plan.fileinfo_command),
                },
            },
            "output": {"path": plan.output_path.name, **output_hashes},
            "fileinfo": fileinfo,
            "rights": {
                "license": planet_fetch.OSM_LICENSE,
                "attribution": planet_fetch.OSM_ATTRIBUTION,
                "copyright_url": planet_fetch.OSM_COPYRIGHT_URL,
            },
        }
        _prepare_atomic_file(
            plan.temporary_manifest_path,
            _json_bytes(manifest),
            label="temporary extraction manifest",
        )
        if plan.output_path.exists() or plan.output_path.is_symlink():
            raise ExtractionError(f"refusing to overwrite extraction output: {plan.output_path}")
        plan.temporary_output_path.replace(plan.output_path)
        output_published = True
        if plan.manifest_path.exists() or plan.manifest_path.is_symlink():
            raise ExtractionError(
                f"refusing to overwrite extraction manifest: {plan.manifest_path}"
            )
        plan.temporary_manifest_path.replace(plan.manifest_path)
        manifest_published = True
        _fsync_directory(plan.output_path.parent)
        return manifest
    except Exception:
        _cleanup_owned_temporary(plan.temporary_output_path)
        _cleanup_owned_temporary(plan.temporary_manifest_path)
        if output_published and not manifest_published:
            _cleanup_owned_temporary(plan.output_path)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=planet_fetch.DEFAULT_OUTPUT_DIRECTORY / planet_fetch.PLANET_FILENAME,
        help="verified dated Planet PBF",
    )
    parser.add_argument(
        "--fetch-manifest",
        type=Path,
        help="completed fetch-manifest.json to bind to the source",
    )
    parser.add_argument(
        "--exact-source-verification",
        action="store_true",
        help="verify exact pinned size and MD5 without using an adjacent fetch manifest",
    )
    parser.add_argument("--output", type=Path, help=f"filtered PBF (default: {OUTPUT_FILENAME})")
    parser.add_argument(
        "--manifest",
        type=Path,
        help=f"extraction manifest (default: {MANIFEST_FILENAME})",
    )
    parser.add_argument("--osmium", default="osmium", help="osmium executable name or path")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the deterministic command plan without reading or writing data",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.fetch_manifest is not None and arguments.exact_source_verification:
        parser.error("--fetch-manifest and --exact-source-verification are mutually exclusive")
    source = _absolute(arguments.source)
    output = _absolute(arguments.output or source.parent / OUTPUT_FILENAME)
    manifest = _absolute(arguments.manifest or output.parent / MANIFEST_FILENAME)
    try:
        osmium = resolve_osmium(arguments.osmium)
        plan = build_command_plan(source, output, manifest, osmium_executable=osmium)
        if arguments.dry_run:
            print(json.dumps(plan.dry_run_document(), indent=2, sort_keys=True))
            return 0
        fetch_manifest: Path | None
        if arguments.exact_source_verification:
            fetch_manifest = None
        elif arguments.fetch_manifest is not None:
            fetch_manifest = arguments.fetch_manifest
        else:
            adjacent = source.parent / "fetch-manifest.json"
            fetch_manifest = adjacent if adjacent.exists() or adjacent.is_symlink() else None
        document = extract_planet(
            source,
            output,
            manifest,
            fetch_manifest_path=fetch_manifest,
            osmium_executable=osmium,
            invocation=[
                sys.executable,
                str(Path(__file__).resolve()),
                *(argv or sys.argv[1:]),
            ],
        )
    except Exception as error:
        parser.exit(1, f"error: {error}\n")
    print(json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
