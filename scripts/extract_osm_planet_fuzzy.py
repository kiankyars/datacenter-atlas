#!/usr/bin/env python3
"""Extract a review-only fuzzy data-centre layer from one verified OSM Planet."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datacenter_atlas.osm_fuzzy import (  # noqa: E402
    EXTRACTION_PIPELINE,
    filter_manifest_document,
    osmium_filter_expressions,
)

if __package__ in {None, ""}:
    import extract_osm_planet as exact
    import fetch_osm_planet as planet_fetch
else:
    from . import extract_osm_planet as exact
    from . import fetch_osm_planet as planet_fetch


SCHEMA_VERSION = 1
OUTPUT_FILENAME = f"planet-{planet_fetch.PLANET_DATE_TOKEN}-data-center-fuzzy-review.osm.pbf"
MANIFEST_FILENAME = "fuzzy-extract-manifest.json"
GENERATOR = "DataCenterAtlas/0.1 planet-data-center-fuzzy-review"


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
            "schema_version": SCHEMA_VERSION,
            "pipeline": EXTRACTION_PIPELINE,
            "state": "dry_run",
            "dry_run": True,
            "review_only": True,
            "source_path": str(self.source_path),
            "output_path": str(self.output_path),
            "temporary_output_path": str(self.temporary_output_path),
            "manifest_path": str(self.manifest_path),
            "temporary_manifest_path": str(self.temporary_manifest_path),
            "filter": filter_manifest_document(),
            "commands": {
                "version": list(self.version_command),
                "tags_filter": list(self.tags_filter_command),
                "fileinfo": list(self.fileinfo_command),
            },
            "writes_performed": False,
        }


def build_command_plan(
    source_path: str | Path,
    output_path: str | Path,
    manifest_path: str | Path,
    *,
    osmium_executable: str = "osmium",
) -> ExtractionPlan:
    source = exact._absolute(source_path)
    output = exact._absolute(output_path)
    manifest = exact._absolute(manifest_path)
    temporary_output = output.with_name(f".{output.name}.extracting.osm.pbf")
    temporary_manifest = manifest.with_name(f".{manifest.name}.extracting.tmp")
    paths = (source, output, manifest, temporary_output, temporary_manifest)
    if len(set(paths)) != len(paths):
        raise exact.ExtractionError("source, output, manifest, and temporary paths must differ")
    if not output.name.endswith(".osm.pbf"):
        raise exact.ExtractionError("fuzzy extraction output must end with .osm.pbf")
    if output.parent != manifest.parent:
        raise exact.ExtractionError("fuzzy output and manifest must share one directory")
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
        source,
        output,
        temporary_output,
        manifest,
        temporary_manifest,
        executable,
        expressions,
        version_command,
        tags_filter_command,
        fileinfo_command,
    )


def _validate_manifest(
    document: Mapping[str, Any],
    *,
    plan: ExtractionPlan,
    source: exact.VerifiedSource,
) -> None:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "pipeline": EXTRACTION_PIPELINE,
        "state": "completed",
        "review_only": True,
        "candidate_recall_expansion_not_census": True,
        "snapshot_date": source.snapshot_date,
        "source": source.manifest_document(),
        "filter": filter_manifest_document(),
        "rights": {
            "license": planet_fetch.OSM_LICENSE,
            "attribution": planet_fetch.OSM_ATTRIBUTION,
            "copyright_url": planet_fetch.OSM_COPYRIGHT_URL,
        },
    }
    for field, value in expected.items():
        if document.get(field) != value:
            raise exact.ExtractionError(f"fuzzy extraction manifest {field} does not match")
    output = document.get("output")
    if not isinstance(output, Mapping) or output.get("path") != plan.output_path.name:
        raise exact.ExtractionError("fuzzy extraction manifest output is invalid")
    actual = exact._output_hashes(plan.output_path)
    for field in ("bytes", "md5", "sha256"):
        if output.get(field) != actual[field]:
            raise exact.ExtractionError(f"fuzzy extraction manifest output.{field} does not match")
    tool = document.get("tool")
    expected_commands = {
        "version": list(plan.version_command),
        "tags_filter": list(plan.tags_filter_command),
        "fileinfo": list(plan.fileinfo_command),
    }
    if (
        not isinstance(tool, Mapping)
        or tool.get("name") != "osmium-tool"
        or tool.get("license") != exact.OSMIUM_LICENSE
        or tool.get("executable") != plan.osmium_executable
        or tool.get("commands") != expected_commands
        or not isinstance(tool.get("version"), Mapping)
        or not tool["version"].get("first_line")
    ):
        raise exact.ExtractionError("fuzzy extraction manifest tool contract does not match")
    fileinfo = document.get("fileinfo")
    if not isinstance(fileinfo, Mapping):
        raise exact.ExtractionError("fuzzy extraction manifest fileinfo is missing")
    if fileinfo.get("file", {}).get("name") != plan.output_path.name:
        raise exact.ExtractionError("fuzzy extraction manifest fileinfo filename does not match")
    if fileinfo.get("file", {}).get("size") != actual["bytes"]:
        raise exact.ExtractionError("fuzzy extraction manifest fileinfo size does not match")
    counts = fileinfo.get("object_counts_including_references", {})
    for object_type in ("nodes", "ways", "relations"):
        exact._nonnegative_integer(counts.get(object_type), field=f"fuzzy.{object_type}")


def _existing(
    plan: ExtractionPlan,
    source: exact.VerifiedSource,
) -> dict[str, Any] | None:
    output_exists = plan.output_path.exists() or plan.output_path.is_symlink()
    manifest_exists = plan.manifest_path.exists() or plan.manifest_path.is_symlink()
    if not output_exists and not manifest_exists:
        return None
    if output_exists != manifest_exists:
        raise exact.ExtractionError(
            "existing fuzzy extraction is incomplete; output and manifest must coexist"
        )
    exact._require_regular_file(plan.output_path, label="existing fuzzy PBF")
    document, _ = exact._read_json_file(plan.manifest_path, label="fuzzy manifest")
    _validate_manifest(document, plan=plan, source=source)
    return document


def extract_fuzzy_planet(
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
    runner: Any = subprocess.run,
    clock: Any = exact.utc_now,
    invocation: Sequence[str] | None = None,
) -> dict[str, Any]:
    plan = build_command_plan(
        source_path, output_path, manifest_path, osmium_executable=osmium_executable
    )
    source = exact.verify_source(
        plan.source_path,
        fetch_manifest_path=fetch_manifest_path,
        expected_snapshot_date=expected_snapshot_date,
        expected_filename=expected_filename,
        expected_source_url=expected_source_url,
        expected_size=expected_size,
        expected_md5=expected_md5,
    )
    existing = _existing(plan, source)
    if existing is not None:
        return existing

    plan.output_path.parent.mkdir(parents=True, exist_ok=True)
    plan.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    exact._assert_publish_paths_available(plan)
    started_at = clock()
    output_published = manifest_published = False
    try:
        version = exact._osmium_version(runner, plan.version_command)
        exact._run_command(runner, plan.tags_filter_command, label="osmium fuzzy tags-filter")
        exact._require_regular_file(plan.temporary_output_path, label="temporary fuzzy PBF")
        hashes = exact._output_hashes(plan.temporary_output_path)
        if hashes["bytes"] <= 0:
            raise exact.ExtractionError("osmium fuzzy tags-filter produced an empty PBF")
        fileinfo = exact.normalize_fileinfo(
            exact._run_command(runner, plan.fileinfo_command, label="osmium fuzzy fileinfo"),
            output_name=plan.output_path.name,
            output_bytes=hashes["bytes"],
        )
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "pipeline": EXTRACTION_PIPELINE,
            "state": "completed",
            "review_only": True,
            "candidate_recall_expansion_not_census": True,
            "started_at": started_at,
            "finished_at": clock(),
            "snapshot_date": source.snapshot_date,
            "invocation": list(invocation or ()),
            "source": source.manifest_document(),
            "filter": filter_manifest_document(),
            "tool": {
                "name": "osmium-tool",
                "license": exact.OSMIUM_LICENSE,
                "executable": plan.osmium_executable,
                "version": version,
                "commands": {
                    "version": list(plan.version_command),
                    "tags_filter": list(plan.tags_filter_command),
                    "fileinfo": list(plan.fileinfo_command),
                },
            },
            "output": {"path": plan.output_path.name, **hashes},
            "fileinfo": fileinfo,
            "rights": {
                "license": planet_fetch.OSM_LICENSE,
                "attribution": planet_fetch.OSM_ATTRIBUTION,
                "copyright_url": planet_fetch.OSM_COPYRIGHT_URL,
            },
        }
        exact._prepare_atomic_file(
            plan.temporary_manifest_path,
            exact._json_bytes(manifest),
            label="temporary fuzzy extraction manifest",
        )
        if plan.output_path.exists() or plan.output_path.is_symlink():
            raise exact.ExtractionError(f"refusing to overwrite fuzzy output: {plan.output_path}")
        plan.temporary_output_path.replace(plan.output_path)
        output_published = True
        if plan.manifest_path.exists() or plan.manifest_path.is_symlink():
            raise exact.ExtractionError(f"refusing to overwrite fuzzy manifest: {plan.manifest_path}")
        plan.temporary_manifest_path.replace(plan.manifest_path)
        manifest_published = True
        exact._fsync_directory(plan.output_path.parent)
        return manifest
    except Exception:
        exact._cleanup_owned_temporary(plan.temporary_output_path)
        exact._cleanup_owned_temporary(plan.temporary_manifest_path)
        if output_published and not manifest_published:
            exact._cleanup_owned_temporary(plan.output_path)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=planet_fetch.DEFAULT_OUTPUT_DIRECTORY / planet_fetch.PLANET_FILENAME,
    )
    parser.add_argument("--fetch-manifest", type=Path)
    parser.add_argument("--exact-source-verification", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--osmium", default="osmium")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.fetch_manifest is not None and arguments.exact_source_verification:
        parser.error("--fetch-manifest and --exact-source-verification are mutually exclusive")
    source = exact._absolute(arguments.source)
    output = exact._absolute(arguments.output or source.parent / OUTPUT_FILENAME)
    manifest = exact._absolute(arguments.manifest or output.parent / MANIFEST_FILENAME)
    try:
        osmium = exact.resolve_osmium(arguments.osmium)
        plan = build_command_plan(source, output, manifest, osmium_executable=osmium)
        if arguments.dry_run:
            print(json.dumps(plan.dry_run_document(), indent=2, sort_keys=True))
            return 0
        if arguments.fetch_manifest is None and not arguments.exact_source_verification:
            parser.error("choose --fetch-manifest or --exact-source-verification")
        result = extract_fuzzy_planet(
            source,
            output,
            manifest,
            fetch_manifest_path=arguments.fetch_manifest,
            osmium_executable=osmium,
            invocation=[sys.executable, *sys.argv],
        )
    except exact.ExtractionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
