"""Geometry-complete, candidate-independent industrial/grid OSM auxiliary v3.

The only authoritative source is one pinned full-Planet snapshot and its
adjacent acquisition manifest.  Selection remains tag-only and independent of
Atlas, candidate, construction, and satellite inputs.  Unlike v1, every
industrial selection must reproduce as an osmium polygon before it can enter
the usable PBF.  Missing geometry is preserved in an exact unresolved ledger;
it is never silently treated as negative evidence.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, BinaryIO, Callable, Iterable, Mapping, Sequence, TextIO
import xml.etree.ElementTree as ET

from . import osm_blind_tile_auxiliary as v1


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLANET_PATH = v1.PLANET_PATH
PLANET_FETCH_MANIFEST = v1.PLANET_FETCH_MANIFEST
OUTPUT_DIRECTORY = (
    PROJECT_ROOT / "source_cache" / "osm-blind-tile-auxiliary-260713-v3"
)

OUTPUT_PBF_FILENAME = "stable-industrial-grid-geometry-complete.osm.pbf"
IDS_FILENAME = "selected-feature-ids.txt"
LEDGER_FILENAME = "selection-ledger.jsonl"
UNRESOLVED_FILENAME = "unresolved-geometry-ledger.jsonl"
MANIFEST_FILENAME = "extract-manifest.json"
MANIFEST_SHA_FILENAME = "manifest.sha256"

PIPELINE = "osm_blind_tile_stable_industrial_grid_extraction_v3"
SCHEMA_VERSION = 3
GENERATOR = "DataCenterAtlas/0.1 blind-tile-stable-industrial-grid-v3"
EXPECTED_OSMIUM_FIRST_LINE = "osmium version 1.19.1"
EXPECTED_LIBOSMIUM_LINE = "libosmium version 2.23.1"
FROZEN_DIRECTORY_MODE = 0o555
FROZEN_FILE_MODE = 0o444

PROCESSOR_FILES = (
    "datacenter_atlas/osm_blind_tile_auxiliary.py",
    "datacenter_atlas/osm_blind_tile_auxiliary_v3.py",
    "scripts/extract_osm_blind_tile_auxiliary_v3.py",
)

TYPE_LETTERS = {"node": "n", "way": "w", "relation": "r"}
LETTER_TYPES = {value: key for key, value in TYPE_LETTERS.items()}
TYPE_ORDER = {"node": 0, "way": 1, "relation": 2}

PRESELECTION_REASONS = frozenset(
    {
        "explicit_area_no",
        "relation_empty",
        "relation_no_direct_way_member",
    }
)
POSTEXPORT_REASON = "not_emitted_by_complete_polygon_export"
BOUNDED_DOWNSTREAM_TREATMENT = {
    "applies_to": "every_tile_intersecting_conservative_bounds",
    "industrial_coverage": "incomplete_unknown",
    "may_be_treated_as_false": False,
    "tile_fact_established": True,
    "treatment": "mark_intersecting_tiles_industrial_coverage_incomplete_unknown",
}
UNLOCATED_DOWNSTREAM_TREATMENT = {
    "applies_to": "no_tile_without_locatable_geometry",
    "industrial_coverage": "no_locatable_tile_fact",
    "may_be_treated_as_false": False,
    "tile_fact_established": False,
    "treatment": "object_local_exclusion_without_any_tile_fact",
}
DOWNSTREAM_CONTRACT = {
    "bounded_unresolved": (
        "Every downstream tile whose closed footprint intersects an unresolved "
        "object's conservative referenced-node envelope must be marked industrial "
        "coverage incomplete/unknown; the object may not be treated as false there."
    ),
    "candidate_or_atlas_input_used": False,
    "null_bounds_unresolved": (
        "An unresolved object without referenced-node coordinates provides no "
        "locatable geometry, establishes no tile fact, and is excluded only at the "
        "object level; no geometry or global location is invented."
    ),
    "selection_ledger_defines_signals": True,
}

OUTPUT_NAMES = frozenset(
    {
        OUTPUT_PBF_FILENAME,
        IDS_FILENAME,
        LEDGER_FILENAME,
        UNRESOLVED_FILENAME,
        MANIFEST_FILENAME,
        MANIFEST_SHA_FILENAME,
    }
)
MANIFEST_KEYS = frozenset(
    {
        "candidate_independence",
        "commands",
        "downstream_contract",
        "fileinfo",
        "filter",
        "finished_at",
        "geometry_completeness",
        "integrity",
        "invocation",
        "outputs",
        "pipeline",
        "processor",
        "production_frame_built",
        "rights",
        "schema_version",
        "selection_statistics",
        "source",
        "started_at",
        "state",
        "tool",
    }
)
SELECTION_RECORD_KEYS = frozenset(
    {
        "geometry_status",
        "osm_id",
        "osm_type",
        "parsed_voltages_v",
        "power",
        "signals",
        "voltage_tags",
    }
)
CANDIDATE_RECORD_KEYS = frozenset(
    {
        "accepted_preexport_signals",
        "geometry_preselection_reason",
        "osm_id",
        "osm_type",
        "parsed_voltages_v",
        "power",
        "requested_signals",
        "voltage_tags",
    }
)
UNRESOLVED_RECORD_KEYS = frozenset(
    {
        "accepted_signals",
        "downstream_coverage",
        "location",
        "osm_id",
        "osm_type",
        "reason",
        "rejected_signal",
        "source_reference",
        "stage",
    }
)
SCAN_STATISTIC_KEYS = frozenset(
    {
        "broad_objects",
        "broad_nodes",
        "broad_ways",
        "broad_relations",
        "broad_industrial",
        "broad_grid",
        "broad_both",
        "excluded_any",
        "excluded_data_center_identity",
        "excluded_unstable_lifecycle",
        "grid_without_parsed_110kv",
        "candidate_objects",
        "candidate_nodes",
        "candidate_ways",
        "candidate_relations",
        "candidate_industrial",
        "candidate_grid",
        "preselected_industrial",
        "preselection_industrial_rejected",
        "preselection_explicit_area_no",
        "preselection_relation_empty",
        "preselection_relation_no_direct_way_member",
    }
)
FINAL_STATISTIC_KEYS = frozenset(
    {
        "selected_objects",
        "selected_nodes",
        "selected_ways",
        "selected_relations",
        "selected_industrial",
        "selected_grid",
        "selected_both",
        "unresolved_geometry_objects",
        "unresolved_with_bounds",
        "unresolved_without_bounds",
        "preselection_geometry_rejections",
        "polygon_export_unresolved",
    }
)


class OsmBlindTileAuxiliaryV3Error(ValueError):
    """Raised when v3 selection, geometry, lineage, or publication fails closed."""


Runner = Callable[..., subprocess.CompletedProcess[str]]
PopenFactory = Callable[..., subprocess.Popen[bytes]]
Clock = Callable[[], str]


@dataclass(frozen=True, slots=True)
class ExtractionPlan:
    source_path: Path
    fetch_manifest_path: Path
    output_directory: Path
    osmium_executable: str

    def command_contract(self) -> dict[str, list[str]]:
        executable = self.osmium_executable
        return {
            "candidate_getid": [
                executable,
                "getid",
                "--no-progress",
                "--add-referenced",
                "--remove-tags",
                "--fsync",
                "--id-file",
                "{candidate_ids}",
                "--output",
                "{provisional_pbf}",
                "--output-format=pbf",
                str(self.source_path),
            ],
            "check_refs": [
                executable,
                "check-refs",
                "--no-progress",
                "--check-relations",
                "{pbf}",
            ],
            "fileinfo": [
                executable,
                "fileinfo",
                "--extended",
                "--json",
                "--no-progress",
                "{pbf}",
            ],
            "final_getid": [
                executable,
                "getid",
                "--no-progress",
                "--add-referenced",
                "--remove-tags",
                "--fsync",
                "--id-file",
                "{selected_ids}",
                "--output",
                "{final_pbf}",
                "--output-format=pbf",
                "{provisional_pbf}",
            ],
            "industrial_getid": [
                executable,
                "getid",
                "--no-progress",
                "--add-referenced",
                "--remove-tags",
                "--fsync",
                "--id-file",
                "{industrial_ids}",
                "--output",
                "{industrial_pbf}",
                "--output-format=pbf",
                "{source_pbf}",
            ],
            "polygon_export_initial": [
                executable,
                "export",
                "--no-progress",
                "--show-errors",
                "--geometry-types=polygon",
                "--add-unique-id=type_id",
                "--output-format=geojsonseq",
                "{industrial_pbf}",
            ],
            "polygon_export_final": [
                executable,
                "export",
                "--no-progress",
                "--show-errors",
                "--stop-on-error",
                "--geometry-types=polygon",
                "--add-unique-id=type_id",
                "--output-format=geojsonseq",
                "{industrial_pbf}",
            ],
            "scan": [
                executable,
                "tags-filter",
                "--no-progress",
                "--omit-referenced",
                "--output-format=osm,add_metadata=false",
                str(self.source_path),
                *v1.BROAD_FILTER_EXPRESSIONS,
            ],
            "version": [executable, "--version"],
        }

    def contract_document(self) -> dict[str, Any]:
        return {
            "candidate_independent": True,
            "commands": self.command_contract(),
            "downstream_contract": DOWNSTREAM_CONTRACT,
            "dry_run": True,
            "filter": filter_contract_document(),
            "output_directory": str(self.output_directory),
            "pipeline": PIPELINE,
            "production_frame_built": False,
            "schema_version": SCHEMA_VERSION,
            "source": str(self.source_path),
        }


@dataclass(frozen=True, slots=True)
class WorkPaths:
    root: Path
    work: Path
    candidate_ids: Path
    candidate_ledger: Path
    preselected_industrial_ids: Path
    provisional_pbf: Path
    initial_industrial_pbf: Path
    unresolved_ids: Path
    unresolved_osm: Path
    final_industrial_ids: Path
    final_industrial_pbf: Path
    final_ids: Path
    final_ledger: Path
    unresolved_ledger: Path
    final_pbf: Path
    manifest: Path
    sidecar: Path


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def canonical_json_line(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ) + "\n"


def _decode_json(raw: bytes, label: str) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise OsmBlindTileAuxiliaryV3Error(f"{label} must be UTF-8") from error

    def reject_constant(value: str) -> None:
        raise OsmBlindTileAuxiliaryV3Error(
            f"{label} contains non-finite number {value}"
        )

    try:
        return json.loads(text, parse_constant=reject_constant)
    except json.JSONDecodeError as error:
        raise OsmBlindTileAuxiliaryV3Error(f"{label} is invalid JSON") from error


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise OsmBlindTileAuxiliaryV3Error(f"{label} must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise OsmBlindTileAuxiliaryV3Error(
            f"{label} must be an RFC 3339 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OsmBlindTileAuxiliaryV3Error(f"{label} must include a timezone")
    return parsed.astimezone(UTC)


def _normalize(path: str | Path, label: str) -> Path:
    try:
        return Path(path).expanduser().resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise OsmBlindTileAuxiliaryV3Error(f"{label} path cannot be normalized") from error


def _regular_file(path: Path, label: str) -> os.stat_result:
    if path.is_symlink():
        raise OsmBlindTileAuxiliaryV3Error(f"{label} must not be a symlink")
    try:
        status = path.stat()
    except FileNotFoundError as error:
        raise OsmBlindTileAuxiliaryV3Error(f"{label} is missing") from error
    if not stat.S_ISREG(status.st_mode):
        raise OsmBlindTileAuxiliaryV3Error(f"{label} must be a regular file")
    return status


def _hash_file(path: Path, algorithms: Iterable[str] = ("sha256",)) -> dict[str, str]:
    hashers = {name: hashlib.new(name) for name in algorithms}
    with path.open("rb") as source:
        while chunk := source.read(16 * 1024 * 1024):
            for hasher in hashers.values():
                hasher.update(chunk)
    return {name: hasher.hexdigest() for name, hasher in hashers.items()}


def _checkpoint(path: Path, label: str, *, include_path: bool = True) -> dict[str, Any]:
    status = _regular_file(path, label)
    if status.st_size <= 0:
        raise OsmBlindTileAuxiliaryV3Error(f"{label} is empty")
    record: dict[str, Any] = {
        "bytes": status.st_size,
        "sha256": _hash_file(path)["sha256"],
    }
    if include_path:
        record["path"] = path.name
    return record


def _source_stat(path: Path) -> dict[str, int]:
    status = _regular_file(path, "Planet source")
    return {
        "device": status.st_dev,
        "inode": status.st_ino,
        "mtime_ns": status.st_mtime_ns,
        "size": status.st_size,
    }


def _runtime_lineage() -> dict[str, Any]:
    return {
        "platform": {
            "architecture": platform.architecture()[0],
            "descriptor": platform.platform(),
            "machine": platform.machine(),
            "release": platform.release(),
            "system": platform.system(),
        },
        "python": {
            "cache_tag": sys.implementation.cache_tag,
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
    }


def _processor_files() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for relative in PROCESSOR_FILES:
        path = PROJECT_ROOT / relative
        result[relative] = _checkpoint(path, f"processor {relative}", include_path=False)
    return result


def _processor_lineage() -> dict[str, Any]:
    return {"files": _processor_files(), "runtime": _runtime_lineage()}


def resolve_osmium(executable: str = "osmium") -> str:
    try:
        return v1.resolve_osmium(executable)
    except v1.OsmBlindTileAuxiliaryError as error:
        raise OsmBlindTileAuxiliaryV3Error(str(error)) from error


def _run_text(runner: Runner, command: Sequence[str], label: str) -> tuple[str, str]:
    try:
        result = runner(
            list(command),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as error:
        raise OsmBlindTileAuxiliaryV3Error(f"could not execute {label}: {error}") from error
    if result.returncode != 0:
        raise OsmBlindTileAuxiliaryV3Error(
            f"{label} failed with exit code {result.returncode}: {(result.stderr or '').strip()}"
        )
    return (result.stdout or "").strip(), (result.stderr or "").strip()


def _tool_lineage(executable: str, runner: Runner = subprocess.run) -> dict[str, Any]:
    stdout, stderr = _run_text(runner, [executable, "--version"], "osmium version")
    if stderr:
        raise OsmBlindTileAuxiliaryV3Error("osmium version emitted stderr")
    lines = stdout.splitlines()
    if len(lines) < 2 or lines[0] != EXPECTED_OSMIUM_FIRST_LINE or lines[1] != EXPECTED_LIBOSMIUM_LINE:
        raise OsmBlindTileAuxiliaryV3Error("osmium/libosmium version is not pinned")
    path = Path(executable).resolve(strict=True)
    return {
        "executable": {
            "bytes": _regular_file(path, "osmium executable").st_size,
            "path": str(path),
            "sha256": _hash_file(path)["sha256"],
        },
        "license": v1.OSMIUM_LICENSE,
        "name": "osmium-tool",
        "version_output": stdout,
    }


def _assert_execution_lineage(
    processor: Mapping[str, Any],
    tool: Mapping[str, Any],
    *,
    runner: Runner = subprocess.run,
) -> None:
    if _processor_files() != processor.get("files"):
        raise OsmBlindTileAuxiliaryV3Error("processor files drifted during extraction")
    if _runtime_lineage() != processor.get("runtime"):
        raise OsmBlindTileAuxiliaryV3Error("Python/platform runtime drifted during extraction")
    if _tool_lineage(str(tool["executable"]["path"]), runner) != tool:
        raise OsmBlindTileAuxiliaryV3Error("osmium runtime drifted during extraction")


def build_plan(
    source_path: str | Path = PLANET_PATH,
    fetch_manifest_path: str | Path = PLANET_FETCH_MANIFEST,
    output_directory: str | Path = OUTPUT_DIRECTORY,
    *,
    osmium_executable: str = "osmium",
) -> ExtractionPlan:
    source = _normalize(source_path, "Planet source")
    fetch_manifest = _normalize(fetch_manifest_path, "Planet fetch manifest")
    output = _normalize(output_directory, "output")
    try:
        v1._validate_input_paths(source, fetch_manifest)
    except v1.OsmBlindTileAuxiliaryError as error:
        raise OsmBlindTileAuxiliaryV3Error(str(error)) from error
    return ExtractionPlan(
        source_path=source,
        fetch_manifest_path=fetch_manifest,
        output_directory=output,
        osmium_executable=os.fspath(osmium_executable),
    )


def _work_paths(root: Path) -> WorkPaths:
    work = root / ".work"
    return WorkPaths(
        root=root,
        work=work,
        candidate_ids=work / "candidate-ids.txt",
        candidate_ledger=work / "candidate-ledger.jsonl",
        preselected_industrial_ids=work / "preselected-industrial-ids.txt",
        provisional_pbf=work / "provisional.osm.pbf",
        initial_industrial_pbf=work / "initial-industrial.osm.pbf",
        unresolved_ids=work / "unresolved-ids.txt",
        unresolved_osm=work / "unresolved-with-references.osm",
        final_industrial_ids=work / "final-industrial-ids.txt",
        final_industrial_pbf=work / "final-industrial.osm.pbf",
        final_ids=root / IDS_FILENAME,
        final_ledger=root / LEDGER_FILENAME,
        unresolved_ledger=root / UNRESOLVED_FILENAME,
        final_pbf=root / OUTPUT_PBF_FILENAME,
        manifest=root / MANIFEST_FILENAME,
        sidecar=root / MANIFEST_SHA_FILENAME,
    )


def _element_tags(element: ET.Element) -> dict[str, str]:
    tags: dict[str, str] = {}
    for child in element:
        if child.tag.rsplit("}", 1)[-1] != "tag":
            continue
        key = child.attrib.get("k")
        value = child.attrib.get("v")
        if key is None or value is None or key in tags:
            raise OsmBlindTileAuxiliaryV3Error("OSM XML contains an invalid or duplicate tag")
        tags[key] = value
    return tags


def _industrial_preselection_reason(
    element: ET.Element, object_type: str, tags: Mapping[str, str]
) -> str | None:
    if object_type == "way":
        if tags.get("area", "").strip().casefold() == "no":
            return "explicit_area_no"
        return None
    if object_type != "relation":
        return None
    members = [
        child
        for child in element
        if child.tag.rsplit("}", 1)[-1] == "member"
    ]
    if not members:
        return "relation_empty"
    # Member roles are not a sound structural polygon gate.  Pinned libosmium
    # 2.23.1 reproducibly emits valid polygons from blank-, inner-, and
    # other-role way members.  Only the absence of a direct way member proves
    # that this relation cannot itself assemble an area from the scanned
    # object.  The complete polygon export deterministically decides all
    # role-bearing direct-way cases.
    if not any(member.attrib.get("type") == "way" for member in members):
        return "relation_no_direct_way_member"
    return None


def classify_element(
    element: ET.Element,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    try:
        base, flags = v1.classify_element(element)
    except v1.OsmBlindTileAuxiliaryError as error:
        raise OsmBlindTileAuxiliaryV3Error(str(error)) from error
    result_flags: dict[str, Any] = dict(flags)
    result_flags["geometry_preselection_reason"] = None
    if base is None:
        return None, result_flags
    object_type = str(base["osm_type"])
    requested = list(base["signals"])
    accepted = list(requested)
    reason: str | None = None
    if "industrial" in requested:
        reason = _industrial_preselection_reason(
            element, object_type, _element_tags(element)
        )
        if reason is not None:
            accepted.remove("industrial")
    result_flags["geometry_preselection_reason"] = reason
    return {
        "accepted_preexport_signals": accepted,
        "geometry_preselection_reason": reason,
        "osm_id": base["osm_id"],
        "osm_type": object_type,
        "parsed_voltages_v": base["parsed_voltages_v"],
        "power": base["power"],
        "requested_signals": requested,
        "voltage_tags": base["voltage_tags"],
    }, result_flags


def scan_osm_xml(
    source: BinaryIO,
    candidate_ids_output: TextIO,
    candidate_ledger_output: TextIO,
    industrial_ids_output: TextIO,
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    previous: tuple[int, int] | None = None
    try:
        iterator = ET.iterparse(source, events=("start", "end"))
        try:
            first_event, root = next(iterator)
        except StopIteration as error:
            raise OsmBlindTileAuxiliaryV3Error("osmium broad stream is empty") from error
        if first_event != "start" or root.tag.rsplit("}", 1)[-1] != "osm":
            raise OsmBlindTileAuxiliaryV3Error("osmium broad stream has no OSM root")
        for event, element in iterator:
            if event != "end":
                continue
            object_type = element.tag.rsplit("}", 1)[-1]
            if object_type not in TYPE_LETTERS:
                continue
            try:
                osm_id = int(element.attrib["id"])
            except (KeyError, ValueError) as error:
                raise OsmBlindTileAuxiliaryV3Error("OSM XML object has an invalid ID") from error
            order = (TYPE_ORDER[object_type], osm_id)
            if previous is not None and order <= previous:
                raise OsmBlindTileAuxiliaryV3Error(
                    "broad OSM stream is duplicate or not type/ID ordered"
                )
            previous = order
            record, flags = classify_element(element)
            counts["broad_objects"] += 1
            counts[f"broad_{object_type}s"] += 1
            for flag, count_name in (
                ("industrial_broad", "broad_industrial"),
                ("grid_broad", "broad_grid"),
                ("data_center_excluded", "excluded_data_center_identity"),
                ("lifecycle_excluded", "excluded_unstable_lifecycle"),
            ):
                if flags.get(flag):
                    counts[count_name] += 1
            if flags.get("industrial_broad") and flags.get("grid_broad"):
                counts["broad_both"] += 1
            if flags.get("data_center_excluded") or flags.get("lifecycle_excluded"):
                counts["excluded_any"] += 1
            if flags.get("grid_broad") and not flags.get("grid_high_voltage"):
                counts["grid_without_parsed_110kv"] += 1
            if record is not None:
                reference = f"{TYPE_LETTERS[object_type]}{osm_id}"
                candidate_ids_output.write(reference + "\n")
                candidate_ledger_output.write(canonical_json_line(record))
                counts["candidate_objects"] += 1
                counts[f"candidate_{object_type}s"] += 1
                if "industrial" in record["requested_signals"]:
                    counts["candidate_industrial"] += 1
                if "grid" in record["requested_signals"]:
                    counts["candidate_grid"] += 1
                reason = record["geometry_preselection_reason"]
                if reason is not None:
                    counts["preselection_industrial_rejected"] += 1
                    counts[f"preselection_{reason}"] += 1
                elif "industrial" in record["requested_signals"]:
                    industrial_ids_output.write(reference + "\n")
                    counts["preselected_industrial"] += 1
            element.clear()
            root.clear()
    except ET.ParseError as error:
        raise OsmBlindTileAuxiliaryV3Error("osmium broad stream is invalid XML") from error
    if counts["broad_objects"] <= 0 or counts["candidate_objects"] <= 0:
        raise OsmBlindTileAuxiliaryV3Error("broad scan or stable candidate inventory is empty")
    if counts["preselected_industrial"] <= 0:
        raise OsmBlindTileAuxiliaryV3Error("preselected industrial inventory is empty")
    return {key: counts[key] for key in sorted(SCAN_STATISTIC_KEYS)}


def filter_contract_document() -> dict[str, Any]:
    document = json.loads(json.dumps(v1.filter_contract_document()))
    document["geometry_v3"] = {
        "area_id_bijection_required": True,
        "explicit_area_no_rejected_before_industrial_selection": True,
        "final_industrial_export_stop_on_error": True,
        "grid_point_line_polygon_preserved": True,
        "missing_polygon_ids_recorded_not_silently_dropped": True,
        "polygon_exporter": {
            "geometry_types": ["polygon"],
            "identity": "osmium type_id area IDs decoded to source way/relation IDs",
        },
        "relation_member_roles_deferred_to_pinned_polygon_exporter": True,
        "relation_requires_direct_way_member": True,
        "unresolved_location": "recursive referenced-node envelope only; never invented geometry",
    }
    return document


def _scan_planet(
    plan: ExtractionPlan,
    paths: WorkPaths,
    *,
    popen_factory: PopenFactory = subprocess.Popen,
) -> tuple[dict[str, int], dict[str, Any]]:
    command = plan.command_contract()["scan"]
    stderr_path = paths.work / "scan.stderr"
    with paths.candidate_ids.open("x", encoding="utf-8", newline="\n") as ids_output, \
        paths.candidate_ledger.open("x", encoding="utf-8", newline="\n") as ledger_output, \
        paths.preselected_industrial_ids.open(
            "x", encoding="utf-8", newline="\n"
        ) as industrial_output, stderr_path.open("xb") as stderr_output:
        try:
            process = popen_factory(command, stdout=subprocess.PIPE, stderr=stderr_output)
        except OSError as error:
            raise OsmBlindTileAuxiliaryV3Error(f"could not start osmium scan: {error}") from error
        if process.stdout is None:
            process.terminate()
            process.wait()
            raise OsmBlindTileAuxiliaryV3Error("osmium scan has no stdout stream")
        try:
            statistics = scan_osm_xml(
                process.stdout, ids_output, ledger_output, industrial_output
            )
        except Exception:
            process.terminate()
            process.wait()
            raise
        finally:
            process.stdout.close()
        returncode = process.wait()
        for output in (ids_output, ledger_output, industrial_output, stderr_output):
            output.flush()
            os.fsync(output.fileno())
    raw = stderr_path.read_bytes()
    if returncode != 0:
        raise OsmBlindTileAuxiliaryV3Error(
            "osmium broad scan failed: " + raw.decode("utf-8", errors="replace").strip()
        )
    checkpoint = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    stderr_path.unlink()
    return statistics, checkpoint


def _getid_command(
    executable: str,
    source: Path,
    ids: Path,
    output: Path,
    *,
    output_format: str = "pbf",
) -> list[str]:
    return [
        executable,
        "getid",
        "--no-progress",
        "--add-referenced",
        "--remove-tags",
        "--fsync",
        "--id-file",
        str(ids),
        "--output",
        str(output),
        f"--output-format={output_format}",
        str(source),
    ]


def _run_getid(
    runner: Runner,
    executable: str,
    source: Path,
    ids: Path,
    output: Path,
    *,
    output_format: str = "pbf",
) -> None:
    if output.exists() or output.is_symlink():
        raise OsmBlindTileAuxiliaryV3Error("refusing to overwrite an extraction intermediate")
    stdout, stderr = _run_text(
        runner,
        _getid_command(executable, source, ids, output, output_format=output_format),
        "osmium getid",
    )
    if stdout or stderr:
        raise OsmBlindTileAuxiliaryV3Error("osmium getid emitted unexpected output")
    _regular_file(output, "osmium getid output")


def _check_refs(runner: Runner, executable: str, pbf: Path) -> dict[str, str]:
    stdout, stderr = _run_text(
        runner,
        [
            executable,
            "check-refs",
            "--no-progress",
            "--check-relations",
            str(pbf),
        ],
        "osmium check-refs",
    )
    return {"stderr": stderr, "stdout": stdout}


def _id_key(reference: str) -> tuple[int, int]:
    match = re.fullmatch(r"([nwr])([1-9][0-9]*)", reference)
    if match is None:
        raise OsmBlindTileAuxiliaryV3Error(f"invalid OSM reference {reference!r}")
    object_type = LETTER_TYPES[match.group(1)]
    return TYPE_ORDER[object_type], int(match.group(2))


def _read_ids(path: Path, label: str) -> list[str]:
    result: list[str] = []
    previous: tuple[int, int] | None = None
    with path.open("r", encoding="utf-8", newline="") as source:
        for line in source:
            if not line.endswith("\n"):
                raise OsmBlindTileAuxiliaryV3Error(f"{label} has an unterminated line")
            value = line[:-1]
            order = _id_key(value)
            if previous is not None and order <= previous:
                raise OsmBlindTileAuxiliaryV3Error(f"{label} is duplicate or unordered")
            previous = order
            result.append(value)
    if not result:
        raise OsmBlindTileAuxiliaryV3Error(f"{label} is empty")
    return result


def _decode_area_id(value: Any) -> str:
    if not isinstance(value, str):
        raise OsmBlindTileAuxiliaryV3Error("polygon export feature ID is not a string")
    match = re.fullmatch(r"a([1-9][0-9]*)", value)
    if match is None:
        raise OsmBlindTileAuxiliaryV3Error("polygon export feature ID is not an osmium area ID")
    area_id = int(match.group(1))
    if area_id % 2 == 0:
        osm_id = area_id // 2
        letter = "w"
    else:
        osm_id = (area_id - 1) // 2
        letter = "r"
    if osm_id <= 0:
        raise OsmBlindTileAuxiliaryV3Error("polygon export area ID decodes to an invalid OSM ID")
    return f"{letter}{osm_id}"


def _polygon_export(
    executable: str,
    pbf: Path,
    stderr_path: Path,
    *,
    stop_on_error: bool,
    popen_factory: PopenFactory = subprocess.Popen,
) -> tuple[set[str], dict[str, Any]]:
    command = [
        executable,
        "export",
        "--no-progress",
        "--show-errors",
    ]
    if stop_on_error:
        command.append("--stop-on-error")
    command.extend(
        [
            "--geometry-types=polygon",
            "--add-unique-id=type_id",
            "--output-format=geojsonseq",
            str(pbf),
        ]
    )
    exported: set[str] = set()
    with stderr_path.open("xb") as stderr_output:
        try:
            process = popen_factory(command, stdout=subprocess.PIPE, stderr=stderr_output)
        except OSError as error:
            raise OsmBlindTileAuxiliaryV3Error(
                f"could not start osmium polygon export: {error}"
            ) from error
        if process.stdout is None:
            process.terminate()
            process.wait()
            raise OsmBlindTileAuxiliaryV3Error("polygon export has no stdout stream")
        try:
            for raw_line in process.stdout:
                if not raw_line.startswith(b"\x1e") or not raw_line.endswith(b"\n"):
                    raise OsmBlindTileAuxiliaryV3Error(
                        "polygon export is not canonical GeoJSON text sequence"
                    )
                feature = _decode_json(raw_line[1:-1], "polygon export feature")
                if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
                    raise OsmBlindTileAuxiliaryV3Error("polygon export emitted a non-feature")
                geometry = feature.get("geometry")
                if not isinstance(geometry, Mapping) or geometry.get("type") not in {
                    "Polygon",
                    "MultiPolygon",
                }:
                    raise OsmBlindTileAuxiliaryV3Error(
                        "polygon export emitted non-polygon geometry"
                    )
                reference = _decode_area_id(feature.get("id"))
                if reference in exported:
                    raise OsmBlindTileAuxiliaryV3Error(
                        "polygon export emitted a duplicate source identity"
                    )
                exported.add(reference)
        except Exception:
            process.terminate()
            process.wait()
            raise
        finally:
            process.stdout.close()
        returncode = process.wait()
        stderr_output.flush()
        os.fsync(stderr_output.fileno())
    raw_stderr = stderr_path.read_bytes()
    lines = raw_stderr.decode("utf-8", errors="strict").splitlines()
    if stop_on_error:
        if returncode != 0 or lines:
            raise OsmBlindTileAuxiliaryV3Error(
                "final stop-on-error polygon export did not complete cleanly"
            )
    else:
        if returncode != 0:
            raise OsmBlindTileAuxiliaryV3Error(
                "initial complete polygon export returned nonzero"
            )
        if any(line != "Geometry error: Could not build area geometry" for line in lines):
            raise OsmBlindTileAuxiliaryV3Error(
                "initial polygon export emitted an unknown diagnostic"
            )
    checkpoint = {
        "bytes": len(raw_stderr),
        "diagnostic_lines": len(lines),
        "sha256": hashlib.sha256(raw_stderr).hexdigest(),
    }
    stderr_path.unlink()
    return exported, checkpoint


def _candidate_records(path: Path) -> Iterable[dict[str, Any]]:
    previous: tuple[int, int] | None = None
    with path.open("r", encoding="utf-8", newline="") as source:
        for index, line in enumerate(source, 1):
            if not line.endswith("\n"):
                raise OsmBlindTileAuxiliaryV3Error("candidate ledger line is unterminated")
            value = _decode_json(line.encode("utf-8"), f"candidate ledger line {index}")
            if not isinstance(value, dict) or set(value) != CANDIDATE_RECORD_KEYS:
                raise OsmBlindTileAuxiliaryV3Error("candidate ledger schema is invalid")
            if line != canonical_json_line(value):
                raise OsmBlindTileAuxiliaryV3Error("candidate ledger is not canonical")
            reference = f"{TYPE_LETTERS.get(value.get('osm_type'), '?')}{value.get('osm_id')}"
            order = _id_key(reference)
            if previous is not None and order <= previous:
                raise OsmBlindTileAuxiliaryV3Error("candidate ledger is unordered")
            previous = order
            yield value


def _write_lines(path: Path, values: Iterable[str]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as output:
        for value in values:
            output.write(value + "\n")
        output.flush()
        os.fsync(output.fileno())


def _geometry_index(path: Path) -> tuple[
    dict[int, tuple[float, float]],
    dict[int, list[int]],
    dict[int, list[tuple[str, int]]],
]:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        raise OsmBlindTileAuxiliaryV3Error("unresolved reference XML is invalid") from error
    nodes: dict[int, tuple[float, float]] = {}
    ways: dict[int, list[int]] = {}
    relations: dict[int, list[tuple[str, int]]] = {}
    for element in root:
        kind = element.tag.rsplit("}", 1)[-1]
        if kind not in TYPE_LETTERS:
            continue
        try:
            osm_id = int(element.attrib["id"])
        except (KeyError, ValueError) as error:
            raise OsmBlindTileAuxiliaryV3Error("unresolved XML object ID is invalid") from error
        if kind == "node":
            try:
                longitude = float(element.attrib["lon"])
                latitude = float(element.attrib["lat"])
            except (KeyError, ValueError) as error:
                raise OsmBlindTileAuxiliaryV3Error("unresolved node location is invalid") from error
            if not math.isfinite(longitude) or not math.isfinite(latitude):
                raise OsmBlindTileAuxiliaryV3Error("unresolved node location is non-finite")
            nodes[osm_id] = (longitude, latitude)
        elif kind == "way":
            references: list[int] = []
            for child in element:
                if child.tag.rsplit("}", 1)[-1] == "nd":
                    try:
                        references.append(int(child.attrib["ref"]))
                    except (KeyError, ValueError) as error:
                        raise OsmBlindTileAuxiliaryV3Error("unresolved way reference is invalid") from error
            ways[osm_id] = references
        else:
            members: list[tuple[str, int]] = []
            for child in element:
                if child.tag.rsplit("}", 1)[-1] != "member":
                    continue
                member_type = child.attrib.get("type")
                if member_type not in TYPE_LETTERS:
                    raise OsmBlindTileAuxiliaryV3Error("unresolved relation member type is invalid")
                try:
                    member_id = int(child.attrib["ref"])
                except (KeyError, ValueError) as error:
                    raise OsmBlindTileAuxiliaryV3Error("unresolved relation member ID is invalid") from error
                members.append((member_type, member_id))
            relations[osm_id] = members
    return nodes, ways, relations


def _referenced_positions(
    object_type: str,
    osm_id: int,
    nodes: Mapping[int, tuple[float, float]],
    ways: Mapping[int, Sequence[int]],
    relations: Mapping[int, Sequence[tuple[str, int]]],
    active: set[tuple[str, int]] | None = None,
) -> list[tuple[float, float]]:
    key = (object_type, osm_id)
    active = set() if active is None else active
    if key in active:
        raise OsmBlindTileAuxiliaryV3Error("unresolved relation references contain a cycle")
    if object_type == "node":
        if osm_id not in nodes:
            raise OsmBlindTileAuxiliaryV3Error("unresolved node reference is missing")
        return [nodes[osm_id]]
    if object_type == "way":
        if osm_id not in ways:
            raise OsmBlindTileAuxiliaryV3Error("unresolved way reference is missing")
        result: list[tuple[float, float]] = []
        for node_id in ways[osm_id]:
            if node_id not in nodes:
                raise OsmBlindTileAuxiliaryV3Error("unresolved way node is missing")
            result.append(nodes[node_id])
        return result
    if osm_id not in relations:
        raise OsmBlindTileAuxiliaryV3Error("unresolved relation reference is missing")
    active.add(key)
    result = []
    for member_type, member_id in relations[osm_id]:
        result.extend(
            _referenced_positions(
                member_type, member_id, nodes, ways, relations, active
            )
        )
    active.remove(key)
    return result


def _location_record(
    object_type: str,
    osm_id: int,
    nodes: Mapping[int, tuple[float, float]],
    ways: Mapping[int, Sequence[int]],
    relations: Mapping[int, Sequence[tuple[str, int]]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    positions = _referenced_positions(object_type, osm_id, nodes, ways, relations)
    if not positions:
        return (
            {
                "bounds_wgs84": None,
                "geometry_invented": False,
                "method": "unavailable_no_referenced_nodes",
            },
            dict(UNLOCATED_DOWNSTREAM_TREATMENT),
        )
    longitudes = [position[0] for position in positions]
    latitudes = [position[1] for position in positions]
    bounds = [min(longitudes), min(latitudes), max(longitudes), max(latitudes)]
    return (
        {
            "bounds_wgs84": bounds,
            "geometry_invented": False,
            "method": "recursive_referenced_node_envelope",
        },
        dict(BOUNDED_DOWNSTREAM_TREATMENT),
    )


def _build_ledgers(
    paths: WorkPaths,
    polygon_missing: set[str],
    *,
    runner: Runner,
    executable: str,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    unresolved_candidates: dict[str, dict[str, Any]] = {}
    for record in _candidate_records(paths.candidate_ledger):
        reference = f"{TYPE_LETTERS[record['osm_type']]}{record['osm_id']}"
        if record["geometry_preselection_reason"] is not None or reference in polygon_missing:
            unresolved_candidates[reference] = record
    if set(polygon_missing) - set(unresolved_candidates):
        raise OsmBlindTileAuxiliaryV3Error("polygon-missing ID has no candidate record")
    ordered_unresolved = sorted(unresolved_candidates, key=_id_key)
    _write_lines(paths.unresolved_ids, ordered_unresolved)
    _run_getid(
        runner,
        executable,
        paths.provisional_pbf,
        paths.unresolved_ids,
        paths.unresolved_osm,
        output_format="osm",
    )
    nodes, ways, relations = _geometry_index(paths.unresolved_osm)
    unresolved_records: list[dict[str, Any]] = []
    for reference in ordered_unresolved:
        record = unresolved_candidates[reference]
        reason = record["geometry_preselection_reason"]
        stage = "preselection_structure"
        if reason is None:
            reason = POSTEXPORT_REASON
            stage = "polygon_export_completeness"
        accepted_signals = [
            signal for signal in record["accepted_preexport_signals"] if signal != "industrial"
        ]
        location, downstream = _location_record(
            record["osm_type"], record["osm_id"], nodes, ways, relations
        )
        unresolved_records.append(
            {
                "accepted_signals": accepted_signals,
                "downstream_coverage": downstream,
                "location": location,
                "osm_id": record["osm_id"],
                "osm_type": record["osm_type"],
                "reason": reason,
                "rejected_signal": "industrial",
                "source_reference": reference,
                "stage": stage,
            }
        )
    with paths.unresolved_ledger.open("xb") as output:
        for record in unresolved_records:
            output.write(canonical_json_line(record).encode("utf-8"))
        output.flush()
        os.fsync(output.fileno())

    final_counts: Counter[str] = Counter()
    unresolved_set = set(ordered_unresolved)
    with paths.final_ids.open("x", encoding="utf-8", newline="\n") as ids_output, \
        paths.final_ledger.open("x", encoding="utf-8", newline="\n") as ledger_output, \
        paths.final_industrial_ids.open(
            "x", encoding="utf-8", newline="\n"
        ) as industrial_output:
        for record in _candidate_records(paths.candidate_ledger):
            reference = f"{TYPE_LETTERS[record['osm_type']]}{record['osm_id']}"
            signals = list(record["accepted_preexport_signals"])
            if reference in polygon_missing and "industrial" in signals:
                signals.remove("industrial")
            if not signals:
                continue
            if "industrial" in signals:
                geometry_status = "polygon_export_verified"
                industrial_output.write(reference + "\n")
            elif reference in unresolved_set and "grid" in signals:
                geometry_status = "grid_preserved_industrial_unresolved"
            else:
                geometry_status = "grid_geometry_preserved"
            final_record = {
                "geometry_status": geometry_status,
                "osm_id": record["osm_id"],
                "osm_type": record["osm_type"],
                "parsed_voltages_v": record["parsed_voltages_v"],
                "power": record["power"],
                "signals": signals,
                "voltage_tags": record["voltage_tags"],
            }
            ids_output.write(reference + "\n")
            ledger_output.write(canonical_json_line(final_record))
            final_counts["selected_objects"] += 1
            final_counts[f"selected_{record['osm_type']}s"] += 1
            for signal in signals:
                final_counts[f"selected_{signal}"] += 1
            if signals == ["industrial", "grid"]:
                final_counts["selected_both"] += 1
        for output in (ids_output, ledger_output, industrial_output):
            output.flush()
            os.fsync(output.fileno())
    if final_counts["selected_objects"] <= 0 or final_counts["selected_industrial"] <= 0:
        raise OsmBlindTileAuxiliaryV3Error("final selection inventory is empty")
    final_counts["unresolved_geometry_objects"] = len(unresolved_records)
    final_counts["unresolved_with_bounds"] = sum(
        record["location"]["bounds_wgs84"] is not None for record in unresolved_records
    )
    final_counts["unresolved_without_bounds"] = sum(
        record["location"]["bounds_wgs84"] is None for record in unresolved_records
    )
    final_counts["preselection_geometry_rejections"] = sum(
        record["stage"] == "preselection_structure" for record in unresolved_records
    )
    final_counts["polygon_export_unresolved"] = sum(
        record["stage"] == "polygon_export_completeness"
        for record in unresolved_records
    )
    return {
        key: final_counts[key] for key in sorted(FINAL_STATISTIC_KEYS)
    }, unresolved_records


def _normalize_fileinfo(stdout: str, pbf: Path) -> dict[str, Any]:
    value = _decode_json(stdout.encode("utf-8"), "osmium fileinfo")
    if not isinstance(value, Mapping):
        raise OsmBlindTileAuxiliaryV3Error("osmium fileinfo must be an object")
    file_section = value.get("file")
    data = value.get("data")
    header = value.get("header")
    if not all(isinstance(section, Mapping) for section in (file_section, data, header)):
        raise OsmBlindTileAuxiliaryV3Error("osmium fileinfo sections are missing")
    assert isinstance(file_section, Mapping)
    assert isinstance(data, Mapping)
    assert isinstance(header, Mapping)
    if str(file_section.get("format", "")).upper() != "PBF" or file_section.get(
        "size"
    ) != pbf.stat().st_size:
        raise OsmBlindTileAuxiliaryV3Error("osmium fileinfo does not describe the final PBF")
    count = data.get("count")
    if not isinstance(count, Mapping):
        raise OsmBlindTileAuxiliaryV3Error("osmium fileinfo counts are missing")
    counts: dict[str, int] = {}
    for key in ("nodes", "ways", "relations"):
        number = count.get(key)
        if isinstance(number, bool) or not isinstance(number, int) or number < 0:
            raise OsmBlindTileAuxiliaryV3Error("osmium fileinfo count is invalid")
        counts[key] = number
    return {
        "bounds": {"data": data.get("bbox"), "header": header.get("boxes")},
        "compression": file_section.get("compression"),
        "crc32": data.get("crc32"),
        "format": file_section.get("format"),
        "multiple_versions": data.get("multiple_versions"),
        "object_counts_including_references": counts,
        "objects_ordered": data.get("objects_ordered"),
        "timestamps": data.get("timestamp"),
    }


def _fileinfo(runner: Runner, executable: str, pbf: Path) -> dict[str, Any]:
    stdout, stderr = _run_text(
        runner,
        [
            executable,
            "fileinfo",
            "--extended",
            "--json",
            "--no-progress",
            str(pbf),
        ],
        "osmium fileinfo",
    )
    if stderr:
        raise OsmBlindTileAuxiliaryV3Error("osmium fileinfo emitted stderr")
    return _normalize_fileinfo(stdout, pbf)


def _candidate_independence() -> dict[str, Any]:
    return {
        "atlas_release_input_used": False,
        "candidate_fusion_input_used": False,
        "construction_output_input_used": False,
        "only_input": "full dated OSM Planet plus its adjacent acquisition manifest",
        "satellite_queue_input_used": False,
        "structural_shortlist_input_used": False,
    }


def _expected_source_document(
    source: Path,
    fetch_manifest: Path,
    *,
    expected_bytes: int,
    expected_md5: str,
    expected_sha256: str,
    expected_fetch_manifest_sha256: str,
) -> dict[str, Any]:
    return {
        "bytes": expected_bytes,
        "fetch_manifest": {
            "path": fetch_manifest.name,
            "sha256": expected_fetch_manifest_sha256,
        },
        "md5": expected_md5,
        "path": source.name,
        "sha256": expected_sha256,
        "snapshot_date": v1.PLANET_SNAPSHOT_DATE,
        "url": v1.PLANET_URL,
        "verification": {
            "exact_size": True,
            "official_md5": True,
            "sha256_recomputed_before_extraction": True,
        },
    }


def _rights() -> dict[str, str]:
    return {
        "attribution": v1.OSM_ATTRIBUTION,
        "copyright_url": v1.OSM_COPYRIGHT_URL,
        "license": v1.OSM_LICENSE,
    }


def _output_checkpoints(paths: WorkPaths) -> dict[str, Any]:
    return {
        "ids": _checkpoint(paths.final_ids, "selected IDs"),
        "pbf": _checkpoint(paths.final_pbf, "final selected PBF"),
        "selection_ledger": _checkpoint(paths.final_ledger, "selection ledger"),
        "unresolved_geometry": _checkpoint(
            paths.unresolved_ledger, "unresolved geometry ledger"
        ),
    }


def _fsync_path(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_tree(root: Path) -> None:
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        _fsync_path(path)
    directories = [root, *(item for item in root.rglob("*") if item.is_dir())]
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        _fsync_path(path)


def _freeze_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            path.chmod(FROZEN_FILE_MODE)
    for path in sorted(
        (item for item in root.rglob("*") if item.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        path.chmod(FROZEN_DIRECTORY_MODE)
    root.chmod(FROZEN_DIRECTORY_MODE)


def _cleanup_staging(staging: Path) -> None:
    if not staging.exists():
        return
    for path in staging.rglob("*"):
        try:
            path.chmod(0o755 if path.is_dir() else 0o644)
        except OSError:
            pass
    staging.chmod(0o755)
    shutil.rmtree(staging)


def _validate_closed_tree(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise OsmBlindTileAuxiliaryV3Error("v3 output is not a regular directory")
    if stat.S_IMODE(root.stat().st_mode) != FROZEN_DIRECTORY_MODE:
        raise OsmBlindTileAuxiliaryV3Error("v3 output directory mode must be 0555")
    actual = {path.name for path in root.iterdir()}
    if actual != OUTPUT_NAMES:
        raise OsmBlindTileAuxiliaryV3Error("v3 output inventory is not closed")
    for path in root.iterdir():
        status = _regular_file(path, f"v3 artifact {path.name}")
        if stat.S_IMODE(status.st_mode) != FROZEN_FILE_MODE:
            raise OsmBlindTileAuxiliaryV3Error(
                f"v3 artifact mode must be 0444: {path.name}"
            )


def _validate_selection(
    ids_path: Path, ledger_path: Path
) -> tuple[dict[str, int], dict[str, dict[str, Any]]]:
    ids = _read_ids(ids_path, "selected ID inventory")
    records: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    with ledger_path.open("r", encoding="utf-8", newline="") as source:
        for index, (reference, line) in enumerate(zip(ids, source, strict=True), 1):
            if not line.endswith("\n"):
                raise OsmBlindTileAuxiliaryV3Error("selection ledger line is unterminated")
            record = _decode_json(line.encode("utf-8"), f"selection ledger line {index}")
            if not isinstance(record, dict) or set(record) != SELECTION_RECORD_KEYS:
                raise OsmBlindTileAuxiliaryV3Error("selection ledger schema is invalid")
            if line != canonical_json_line(record):
                raise OsmBlindTileAuxiliaryV3Error("selection ledger is not canonical")
            if reference != f"{TYPE_LETTERS.get(record.get('osm_type'), '?')}{record.get('osm_id')}":
                raise OsmBlindTileAuxiliaryV3Error("selection ID and ledger identity differ")
            signals = record.get("signals")
            if signals not in (["industrial"], ["grid"], ["industrial", "grid"]):
                raise OsmBlindTileAuxiliaryV3Error("selection signals are invalid")
            status = record.get("geometry_status")
            if "industrial" in signals and status != "polygon_export_verified":
                raise OsmBlindTileAuxiliaryV3Error("industrial selection lacks polygon verification")
            if status == "grid_preserved_industrial_unresolved" and signals != ["grid"]:
                raise OsmBlindTileAuxiliaryV3Error("mixed unresolved grid status is invalid")
            if status not in {
                "polygon_export_verified",
                "grid_geometry_preserved",
                "grid_preserved_industrial_unresolved",
            }:
                raise OsmBlindTileAuxiliaryV3Error("selection geometry status is invalid")
            voltages = record.get("parsed_voltages_v")
            if not isinstance(voltages, list) or any(
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
                for value in voltages
            ):
                raise OsmBlindTileAuxiliaryV3Error("selection voltages are invalid")
            if "grid" in signals and not any(
                value >= v1.MINIMUM_GRID_VOLTAGE_V for value in voltages
            ):
                raise OsmBlindTileAuxiliaryV3Error("grid selection is below 110 kV")
            if not isinstance(record.get("voltage_tags"), dict):
                raise OsmBlindTileAuxiliaryV3Error("selection voltage tags are invalid")
            if any(
                key not in v1.VOLTAGE_KEYS
                or not isinstance(value, str)
                or not value
                for key, value in record["voltage_tags"].items()
            ):
                raise OsmBlindTileAuxiliaryV3Error("selection voltage tags are invalid")
            power = record.get("power")
            if power is not None and (not isinstance(power, str) or not power):
                raise OsmBlindTileAuxiliaryV3Error("selection power value is invalid")
            records[reference] = record
            counts["selected_objects"] += 1
            counts[f"selected_{record['osm_type']}s"] += 1
            for signal in signals:
                counts[f"selected_{signal}"] += 1
            if signals == ["industrial", "grid"]:
                counts["selected_both"] += 1
    return dict(counts), records


def _validate_bounds(value: Any) -> list[float] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 4:
        raise OsmBlindTileAuxiliaryV3Error("unresolved bounds are invalid")
    result: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise OsmBlindTileAuxiliaryV3Error("unresolved bounds must be numeric")
        number = float(item)
        if not math.isfinite(number):
            raise OsmBlindTileAuxiliaryV3Error("unresolved bounds must be finite")
        result.append(number)
    if not -180 <= result[0] <= result[2] <= 180 or not -90 <= result[1] <= result[3] <= 90:
        raise OsmBlindTileAuxiliaryV3Error("unresolved bounds are outside WGS84")
    return result


def _validate_unresolved(
    path: Path, selection: Mapping[str, Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    previous: tuple[int, int] | None = None
    with path.open("r", encoding="utf-8", newline="") as source:
        for index, line in enumerate(source, 1):
            if not line.endswith("\n"):
                raise OsmBlindTileAuxiliaryV3Error("unresolved ledger line is unterminated")
            record = _decode_json(line.encode("utf-8"), f"unresolved line {index}")
            if not isinstance(record, dict) or set(record) != UNRESOLVED_RECORD_KEYS:
                raise OsmBlindTileAuxiliaryV3Error("unresolved ledger schema is invalid")
            if line != canonical_json_line(record):
                raise OsmBlindTileAuxiliaryV3Error("unresolved ledger is not canonical")
            reference = record.get("source_reference")
            if reference != f"{TYPE_LETTERS.get(record.get('osm_type'), '?')}{record.get('osm_id')}":
                raise OsmBlindTileAuxiliaryV3Error("unresolved source identity is invalid")
            order = _id_key(reference)
            if previous is not None and order <= previous:
                raise OsmBlindTileAuxiliaryV3Error("unresolved ledger is unordered")
            previous = order
            reason = record.get("reason")
            stage = record.get("stage")
            if stage == "preselection_structure":
                if reason not in PRESELECTION_REASONS:
                    raise OsmBlindTileAuxiliaryV3Error("preselection unresolved reason is invalid")
                counts["preselection_geometry_rejections"] += 1
            elif stage == "polygon_export_completeness":
                if reason != POSTEXPORT_REASON:
                    raise OsmBlindTileAuxiliaryV3Error("polygon unresolved reason is invalid")
                counts["polygon_export_unresolved"] += 1
            else:
                raise OsmBlindTileAuxiliaryV3Error("unresolved stage is invalid")
            if record.get("rejected_signal") != "industrial":
                raise OsmBlindTileAuxiliaryV3Error("unresolved rejected signal is invalid")
            accepted = record.get("accepted_signals")
            if accepted not in ([], ["grid"]):
                raise OsmBlindTileAuxiliaryV3Error("unresolved accepted signals are invalid")
            location = record.get("location")
            if not isinstance(location, Mapping) or set(location) != {
                "bounds_wgs84",
                "geometry_invented",
                "method",
            } or location.get("geometry_invented") is not False:
                raise OsmBlindTileAuxiliaryV3Error("unresolved location schema is invalid")
            bounds = _validate_bounds(location.get("bounds_wgs84"))
            if bounds is None:
                if location.get("method") != "unavailable_no_referenced_nodes" or record.get(
                    "downstream_coverage"
                ) != UNLOCATED_DOWNSTREAM_TREATMENT:
                    raise OsmBlindTileAuxiliaryV3Error(
                        "unlocated unresolved downstream contract is invalid"
                    )
                counts["unresolved_without_bounds"] += 1
            else:
                if location.get("method") != "recursive_referenced_node_envelope" or record.get(
                    "downstream_coverage"
                ) != BOUNDED_DOWNSTREAM_TREATMENT:
                    raise OsmBlindTileAuxiliaryV3Error(
                        "bounded unresolved downstream contract is invalid"
                    )
                counts["unresolved_with_bounds"] += 1
            selected = selection.get(reference)
            if accepted == ["grid"]:
                if selected is None or selected.get("signals") != ["grid"] or selected.get(
                    "geometry_status"
                ) != "grid_preserved_industrial_unresolved":
                    raise OsmBlindTileAuxiliaryV3Error(
                        "mixed unresolved object did not preserve exact grid semantics"
                    )
            elif selected is not None:
                raise OsmBlindTileAuxiliaryV3Error(
                    "industrial-only unresolved object leaked into final selection"
                )
            counts["unresolved_geometry_objects"] += 1
            records.append(record)
    if not records:
        raise OsmBlindTileAuxiliaryV3Error("unresolved ledger is empty")
    return records, dict(counts)


def _semantic_polygon_validation(
    output: Path,
    selection: Mapping[str, Mapping[str, Any]],
    *,
    executable: str,
    runner: Runner,
    popen_factory: PopenFactory,
) -> dict[str, int]:
    expected = sorted(
        (reference for reference, record in selection.items() if "industrial" in record["signals"]),
        key=_id_key,
    )
    if not expected:
        raise OsmBlindTileAuxiliaryV3Error("final industrial inventory is empty")
    with tempfile.TemporaryDirectory(prefix="osm-blind-v3-validate-") as temporary:
        root = Path(temporary)
        ids = root / "industrial-ids.txt"
        pbf = root / "industrial.osm.pbf"
        stderr = root / "polygon.stderr"
        _write_lines(ids, expected)
        _run_getid(
            runner,
            executable,
            output / OUTPUT_PBF_FILENAME,
            ids,
            pbf,
        )
        _check_refs(runner, executable, pbf)
        exported, diagnostics = _polygon_export(
            executable,
            pbf,
            stderr,
            stop_on_error=True,
            popen_factory=popen_factory,
        )
    if exported != set(expected):
        raise OsmBlindTileAuxiliaryV3Error(
            "final stop-on-error polygon export identity set is incomplete"
        )
    if diagnostics != {
        "bytes": 0,
        "diagnostic_lines": 0,
        "sha256": hashlib.sha256(b"").hexdigest(),
    }:
        raise OsmBlindTileAuxiliaryV3Error("final polygon export emitted diagnostics")
    return {"expected": len(expected), "exported": len(exported)}


def _validate_statistics(
    value: Any,
    selection_counts: Mapping[str, int],
    unresolved_counts: Mapping[str, int],
) -> None:
    if not isinstance(value, Mapping) or set(value) != {"final", "scan"}:
        raise OsmBlindTileAuxiliaryV3Error("selection statistics schema is invalid")
    scan = value.get("scan")
    if not isinstance(scan, Mapping) or set(scan) != SCAN_STATISTIC_KEYS or any(
        isinstance(number, bool) or not isinstance(number, int) or number < 0
        for number in scan.values()
    ):
        raise OsmBlindTileAuxiliaryV3Error("scan statistics are invalid")
    if (
        scan["broad_objects"]
        != scan["broad_nodes"] + scan["broad_ways"] + scan["broad_relations"]
        or scan["candidate_objects"]
        != scan["candidate_nodes"]
        + scan["candidate_ways"]
        + scan["candidate_relations"]
        or scan["candidate_industrial"]
        != scan["preselected_industrial"]
        + scan["preselection_industrial_rejected"]
        or scan["preselection_industrial_rejected"]
        != scan["preselection_explicit_area_no"]
        + scan["preselection_relation_empty"]
        + scan["preselection_relation_no_direct_way_member"]
    ):
        raise OsmBlindTileAuxiliaryV3Error("scan statistics do not reconcile")
    expected_final = {
        key: selection_counts.get(key, 0)
        for key in FINAL_STATISTIC_KEYS
        if key.startswith("selected_")
    }
    expected_final.update(
        {
            key: unresolved_counts.get(key, 0)
            for key in FINAL_STATISTIC_KEYS
            if not key.startswith("selected_")
        }
    )
    if set(expected_final) != FINAL_STATISTIC_KEYS or value.get("final") != expected_final:
        raise OsmBlindTileAuxiliaryV3Error("final statistics do not reproduce ledgers")
    if (
        expected_final["selected_objects"]
        != expected_final["selected_nodes"]
        + expected_final["selected_ways"]
        + expected_final["selected_relations"]
        or expected_final["unresolved_geometry_objects"]
        != expected_final["unresolved_with_bounds"]
        + expected_final["unresolved_without_bounds"]
        or expected_final["unresolved_geometry_objects"]
        != expected_final["preselection_geometry_rejections"]
        + expected_final["polygon_export_unresolved"]
    ):
        raise OsmBlindTileAuxiliaryV3Error("final statistics do not reconcile")


def validate_bundle(
    output_directory: str | Path = OUTPUT_DIRECTORY,
    *,
    source_path: str | Path = PLANET_PATH,
    fetch_manifest_path: str | Path = PLANET_FETCH_MANIFEST,
    osmium_executable: str = "osmium",
    deep_source_hash: bool = True,
    runner: Runner = subprocess.run,
    popen_factory: PopenFactory = subprocess.Popen,
    expected_filename: str = v1.PLANET_FILENAME,
    expected_bytes: int = v1.PLANET_BYTES,
    expected_md5: str = v1.PLANET_MD5,
    expected_sha256: str = v1.PLANET_SHA256,
    expected_fetch_manifest_sha256: str = v1.PLANET_FETCH_MANIFEST_SHA256,
) -> dict[str, Any]:
    executable = resolve_osmium(osmium_executable)
    plan = build_plan(
        source_path,
        fetch_manifest_path,
        output_directory,
        osmium_executable=executable,
    )
    _validate_closed_tree(plan.output_directory)
    manifest_path = plan.output_directory / MANIFEST_FILENAME
    sidecar_path = plan.output_directory / MANIFEST_SHA_FILENAME
    raw = manifest_path.read_bytes()
    document = _decode_json(raw, "v3 extraction manifest")
    if not isinstance(document, dict) or set(document) != MANIFEST_KEYS:
        raise OsmBlindTileAuxiliaryV3Error("v3 manifest top-level schema is invalid")
    if raw != canonical_json(document):
        raise OsmBlindTileAuxiliaryV3Error("v3 extraction manifest is not canonical")
    digest = hashlib.sha256(raw).hexdigest()
    if sidecar_path.read_bytes() != f"{digest}  {MANIFEST_FILENAME}\n".encode("ascii"):
        raise OsmBlindTileAuxiliaryV3Error("v3 manifest sidecar mismatch")
    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("pipeline") != PIPELINE
        or document.get("state") != "completed"
        or document.get("production_frame_built") is not False
    ):
        raise OsmBlindTileAuxiliaryV3Error("v3 manifest identity is invalid")
    if document.get("candidate_independence") != _candidate_independence():
        raise OsmBlindTileAuxiliaryV3Error("candidate-independence contract changed")
    if document.get("downstream_contract") != DOWNSTREAM_CONTRACT:
        raise OsmBlindTileAuxiliaryV3Error("downstream unresolved contract changed")
    if document.get("filter") != filter_contract_document():
        raise OsmBlindTileAuxiliaryV3Error("v3 filter contract changed")
    if document.get("commands") != plan.command_contract():
        raise OsmBlindTileAuxiliaryV3Error("v3 command contract changed")
    if document.get("rights") != _rights():
        raise OsmBlindTileAuxiliaryV3Error("v3 rights changed")
    started_at = _timestamp(document.get("started_at"), "v3 started_at")
    finished_at = _timestamp(document.get("finished_at"), "v3 finished_at")
    if finished_at < started_at:
        raise OsmBlindTileAuxiliaryV3Error("v3 extraction finished before it started")
    invocation = document.get("invocation")
    if not isinstance(invocation, list) or any(
        not isinstance(value, str) or not value for value in invocation
    ):
        raise OsmBlindTileAuxiliaryV3Error("v3 invocation schema is invalid")
    processor = document.get("processor")
    if processor != _processor_lineage():
        raise OsmBlindTileAuxiliaryV3Error("v3 processor/runtime lineage changed")
    tool = document.get("tool")
    if tool != _tool_lineage(executable, runner):
        raise OsmBlindTileAuxiliaryV3Error("v3 osmium lineage changed")
    source_document = document.get("source")
    expected_source_document = _expected_source_document(
        plan.source_path,
        plan.fetch_manifest_path,
        expected_bytes=expected_bytes,
        expected_md5=expected_md5,
        expected_sha256=expected_sha256,
        expected_fetch_manifest_sha256=expected_fetch_manifest_sha256,
    )
    if deep_source_hash:
        try:
            verified = v1.verify_planet(
                plan.source_path,
                plan.fetch_manifest_path,
                expected_filename=expected_filename,
                expected_bytes=expected_bytes,
                expected_md5=expected_md5,
                expected_sha256=expected_sha256,
                expected_fetch_manifest_sha256=expected_fetch_manifest_sha256,
            )
        except v1.OsmBlindTileAuxiliaryError as error:
            raise OsmBlindTileAuxiliaryV3Error(str(error)) from error
        if source_document != verified.manifest_document() or source_document != expected_source_document:
            raise OsmBlindTileAuxiliaryV3Error("v3 source checkpoint changed")
    elif source_document != expected_source_document:
        raise OsmBlindTileAuxiliaryV3Error("v3 source checkpoint changed")
    outputs = document.get("outputs")
    paths = _work_paths(plan.output_directory)
    if outputs != _output_checkpoints(paths):
        raise OsmBlindTileAuxiliaryV3Error("v3 output checkpoints changed")
    selection_counts, selection = _validate_selection(paths.final_ids, paths.final_ledger)
    _, unresolved_counts = _validate_unresolved(paths.unresolved_ledger, selection)
    _validate_statistics(document.get("selection_statistics"), selection_counts, unresolved_counts)
    completeness = document.get("geometry_completeness")
    if not isinstance(completeness, Mapping) or set(completeness) != {
        "final_exported_industrial",
        "final_expected_industrial",
        "final_stop_on_error_passed",
        "initial_diagnostics",
        "initial_exported_industrial",
        "initial_expected_industrial",
        "initial_missing_industrial",
    }:
        raise OsmBlindTileAuxiliaryV3Error("geometry completeness schema is invalid")
    scan = document["selection_statistics"]["scan"]
    if (
        completeness.get("initial_expected_industrial")
        != scan.get("preselected_industrial")
        or completeness.get("initial_missing_industrial")
        != unresolved_counts.get("polygon_export_unresolved", 0)
        or completeness.get("initial_exported_industrial")
        + completeness.get("initial_missing_industrial")
        != completeness.get("initial_expected_industrial")
        or completeness.get("final_expected_industrial")
        != selection_counts.get("selected_industrial", 0)
        or completeness.get("final_exported_industrial")
        != completeness.get("final_expected_industrial")
        or completeness.get("final_stop_on_error_passed") is not True
    ):
        raise OsmBlindTileAuxiliaryV3Error("geometry completeness counts do not reconcile")
    diagnostics = completeness.get("initial_diagnostics")
    if not isinstance(diagnostics, Mapping) or set(diagnostics) != {
        "bytes",
        "diagnostic_lines",
        "sha256",
    }:
        raise OsmBlindTileAuxiliaryV3Error("initial polygon diagnostics are invalid")
    if (
        isinstance(diagnostics.get("bytes"), bool)
        or not isinstance(diagnostics.get("bytes"), int)
        or diagnostics["bytes"] < 0
        or isinstance(diagnostics.get("diagnostic_lines"), bool)
        or not isinstance(diagnostics.get("diagnostic_lines"), int)
        or diagnostics["diagnostic_lines"] < 0
        or not isinstance(diagnostics.get("sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", diagnostics["sha256"]) is None
    ):
        raise OsmBlindTileAuxiliaryV3Error("initial polygon diagnostics are invalid")
    check_refs = _check_refs(runner, executable, paths.final_pbf)
    if document.get("integrity") != {
        "check_refs_passed": True,
        "check_refs_output": check_refs,
        "polygon_export_identity_bijection": True,
        "polygon_export_stop_on_error": True,
        "scan_stderr": document.get("integrity", {}).get("scan_stderr"),
    }:
        raise OsmBlindTileAuxiliaryV3Error("v3 integrity schema is invalid")
    scan_stderr = document["integrity"]["scan_stderr"]
    if (
        not isinstance(scan_stderr, Mapping)
        or set(scan_stderr) != {"bytes", "sha256"}
        or isinstance(scan_stderr.get("bytes"), bool)
        or not isinstance(scan_stderr.get("bytes"), int)
        or scan_stderr["bytes"] < 0
        or not isinstance(scan_stderr.get("sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", scan_stderr["sha256"]) is None
    ):
        raise OsmBlindTileAuxiliaryV3Error("scan stderr checkpoint is invalid")
    semantic = _semantic_polygon_validation(
        plan.output_directory,
        selection,
        executable=executable,
        runner=runner,
        popen_factory=popen_factory,
    )
    if semantic != {
        "expected": completeness["final_expected_industrial"],
        "exported": completeness["final_exported_industrial"],
    }:
        raise OsmBlindTileAuxiliaryV3Error("offline polygon validation counts changed")
    if document.get("fileinfo") != _fileinfo(runner, executable, paths.final_pbf):
        raise OsmBlindTileAuxiliaryV3Error("v3 final PBF fileinfo changed")
    return dict(document)


def extract_auxiliary(
    source_path: str | Path = PLANET_PATH,
    fetch_manifest_path: str | Path = PLANET_FETCH_MANIFEST,
    output_directory: str | Path = OUTPUT_DIRECTORY,
    *,
    osmium_executable: str = "osmium",
    runner: Runner = subprocess.run,
    popen_factory: PopenFactory = subprocess.Popen,
    clock: Clock = utc_now,
    invocation: Sequence[str] = (),
    recheck_source_hash_after: bool = True,
    expected_filename: str = v1.PLANET_FILENAME,
    expected_bytes: int = v1.PLANET_BYTES,
    expected_md5: str = v1.PLANET_MD5,
    expected_sha256: str = v1.PLANET_SHA256,
    expected_fetch_manifest_sha256: str = v1.PLANET_FETCH_MANIFEST_SHA256,
) -> dict[str, Any]:
    executable = resolve_osmium(osmium_executable)
    plan = build_plan(
        source_path,
        fetch_manifest_path,
        output_directory,
        osmium_executable=executable,
    )
    if plan.output_directory.exists() or plan.output_directory.is_symlink():
        return validate_bundle(
            plan.output_directory,
            source_path=plan.source_path,
            fetch_manifest_path=plan.fetch_manifest_path,
            osmium_executable=executable,
            deep_source_hash=True,
            runner=runner,
            popen_factory=popen_factory,
            expected_filename=expected_filename,
            expected_bytes=expected_bytes,
            expected_md5=expected_md5,
            expected_sha256=expected_sha256,
            expected_fetch_manifest_sha256=expected_fetch_manifest_sha256,
        )
    plan.output_directory.parent.mkdir(parents=True, exist_ok=True)
    if plan.output_directory.parent.is_symlink():
        raise OsmBlindTileAuxiliaryV3Error("output parent must not be a symlink")
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{plan.output_directory.name}.", dir=plan.output_directory.parent
        )
    )
    paths = _work_paths(staging)
    paths.work.mkdir()
    try:
        processor = _processor_lineage()
        tool = _tool_lineage(executable, runner)
        source_stat_before = _source_stat(plan.source_path)
        try:
            verified = v1.verify_planet(
                plan.source_path,
                plan.fetch_manifest_path,
                expected_filename=expected_filename,
                expected_bytes=expected_bytes,
                expected_md5=expected_md5,
                expected_sha256=expected_sha256,
                expected_fetch_manifest_sha256=expected_fetch_manifest_sha256,
            )
        except v1.OsmBlindTileAuxiliaryError as error:
            raise OsmBlindTileAuxiliaryV3Error(str(error)) from error
        started_at = clock()
        _assert_execution_lineage(processor, tool, runner=runner)
        scan_statistics, scan_stderr = _scan_planet(
            plan, paths, popen_factory=popen_factory
        )
        _assert_execution_lineage(processor, tool, runner=runner)
        _run_getid(
            runner,
            executable,
            plan.source_path,
            paths.candidate_ids,
            paths.provisional_pbf,
        )
        _check_refs(runner, executable, paths.provisional_pbf)
        _run_getid(
            runner,
            executable,
            paths.provisional_pbf,
            paths.preselected_industrial_ids,
            paths.initial_industrial_pbf,
        )
        _check_refs(runner, executable, paths.initial_industrial_pbf)
        expected_initial = _read_ids(
            paths.preselected_industrial_ids, "preselected industrial IDs"
        )
        exported_initial, initial_diagnostics = _polygon_export(
            executable,
            paths.initial_industrial_pbf,
            paths.work / "initial-polygon.stderr",
            stop_on_error=False,
            popen_factory=popen_factory,
        )
        unexpected = exported_initial - set(expected_initial)
        if unexpected:
            raise OsmBlindTileAuxiliaryV3Error(
                "initial polygon export emitted an unselected industrial identity"
            )
        polygon_missing = set(expected_initial) - exported_initial
        final_statistics, _ = _build_ledgers(
            paths,
            polygon_missing,
            runner=runner,
            executable=executable,
        )
        _assert_execution_lineage(processor, tool, runner=runner)
        _run_getid(
            runner,
            executable,
            paths.provisional_pbf,
            paths.final_ids,
            paths.final_pbf,
        )
        check_refs_output = _check_refs(runner, executable, paths.final_pbf)
        _run_getid(
            runner,
            executable,
            paths.final_pbf,
            paths.final_industrial_ids,
            paths.final_industrial_pbf,
        )
        _check_refs(runner, executable, paths.final_industrial_pbf)
        expected_final = _read_ids(paths.final_industrial_ids, "final industrial IDs")
        exported_final, final_diagnostics = _polygon_export(
            executable,
            paths.final_industrial_pbf,
            paths.work / "final-polygon.stderr",
            stop_on_error=True,
            popen_factory=popen_factory,
        )
        if exported_final != set(expected_final) or final_diagnostics["diagnostic_lines"] != 0:
            raise OsmBlindTileAuxiliaryV3Error(
                "final stop-on-error polygon export is not an exact identity bijection"
            )
        if _source_stat(plan.source_path) != source_stat_before:
            raise OsmBlindTileAuxiliaryV3Error("Planet source metadata drifted during extraction")
        if recheck_source_hash_after:
            try:
                verified_after = v1.verify_planet(
                    plan.source_path,
                    plan.fetch_manifest_path,
                    expected_filename=expected_filename,
                    expected_bytes=expected_bytes,
                    expected_md5=expected_md5,
                    expected_sha256=expected_sha256,
                    expected_fetch_manifest_sha256=expected_fetch_manifest_sha256,
                )
            except v1.OsmBlindTileAuxiliaryError as error:
                raise OsmBlindTileAuxiliaryV3Error(str(error)) from error
            if verified_after != verified:
                raise OsmBlindTileAuxiliaryV3Error("Planet source hash drifted during extraction")
        _assert_execution_lineage(processor, tool, runner=runner)
        fileinfo = _fileinfo(runner, executable, paths.final_pbf)
        outputs = _output_checkpoints(paths)
        manifest = {
            "candidate_independence": _candidate_independence(),
            "commands": plan.command_contract(),
            "downstream_contract": DOWNSTREAM_CONTRACT,
            "fileinfo": fileinfo,
            "filter": filter_contract_document(),
            "finished_at": clock(),
            "geometry_completeness": {
                "final_exported_industrial": len(exported_final),
                "final_expected_industrial": len(expected_final),
                "final_stop_on_error_passed": True,
                "initial_diagnostics": initial_diagnostics,
                "initial_exported_industrial": len(exported_initial),
                "initial_expected_industrial": len(expected_initial),
                "initial_missing_industrial": len(polygon_missing),
            },
            "integrity": {
                "check_refs_passed": True,
                "check_refs_output": check_refs_output,
                "polygon_export_identity_bijection": True,
                "polygon_export_stop_on_error": True,
                "scan_stderr": scan_stderr,
            },
            "invocation": list(invocation),
            "outputs": outputs,
            "pipeline": PIPELINE,
            "processor": processor,
            "production_frame_built": False,
            "rights": _rights(),
            "schema_version": SCHEMA_VERSION,
            "selection_statistics": {"final": final_statistics, "scan": scan_statistics},
            "source": verified.manifest_document(),
            "started_at": started_at,
            "state": "completed",
            "tool": tool,
        }
        manifest_raw = canonical_json(manifest)
        with paths.manifest.open("xb") as output:
            output.write(manifest_raw)
            output.flush()
            os.fsync(output.fileno())
        with paths.sidecar.open("xb") as output:
            output.write(
                f"{hashlib.sha256(manifest_raw).hexdigest()}  {MANIFEST_FILENAME}\n".encode(
                    "ascii"
                )
            )
            output.flush()
            os.fsync(output.fileno())
        shutil.rmtree(paths.work)
        _fsync_tree(staging)
        _freeze_tree(staging)
        _fsync_tree(staging)
        validated = validate_bundle(
            staging,
            source_path=plan.source_path,
            fetch_manifest_path=plan.fetch_manifest_path,
            osmium_executable=executable,
            deep_source_hash=False,
            runner=runner,
            popen_factory=popen_factory,
            expected_filename=expected_filename,
            expected_bytes=expected_bytes,
            expected_md5=expected_md5,
            expected_sha256=expected_sha256,
            expected_fetch_manifest_sha256=expected_fetch_manifest_sha256,
        )
        if plan.output_directory.exists() or plan.output_directory.is_symlink():
            raise OsmBlindTileAuxiliaryV3Error("output appeared before atomic publication")
        os.replace(staging, plan.output_directory)
        _fsync_path(plan.output_directory.parent)
        return validated
    except Exception:
        _cleanup_staging(staging)
        raise


__all__ = [
    "DOWNSTREAM_CONTRACT",
    "IDS_FILENAME",
    "LEDGER_FILENAME",
    "MANIFEST_FILENAME",
    "MANIFEST_SHA_FILENAME",
    "OUTPUT_DIRECTORY",
    "OUTPUT_PBF_FILENAME",
    "OsmBlindTileAuxiliaryV3Error",
    "PLANET_FETCH_MANIFEST",
    "PLANET_PATH",
    "UNRESOLVED_FILENAME",
    "build_plan",
    "classify_element",
    "extract_auxiliary",
    "filter_contract_document",
    "resolve_osmium",
    "scan_osm_xml",
    "validate_bundle",
]
