"""Build a candidate-independent stable industrial/grid auxiliary from OSM Planet.

The selector streams a broad, reference-free XML projection directly from the
full dated Planet. It applies only predeclared OSM-tag rules, writes selected
object IDs and a compact decision ledger, then asks osmium to recover complete
geometry from the same Planet. No Atlas or candidate-derived input is accepted.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
from typing import Any, BinaryIO, Callable, Iterable, Mapping, Sequence, TextIO
import unicodedata
import xml.etree.ElementTree as ET


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLANET_DIRECTORY = PROJECT_ROOT / "source_cache" / "osm-planet-260713"
PLANET_FILENAME = "planet-260713.osm.pbf"
PLANET_PATH = PLANET_DIRECTORY / PLANET_FILENAME
PLANET_FETCH_MANIFEST = PLANET_DIRECTORY / "fetch-manifest.json"
PLANET_SNAPSHOT_DATE = "2026-07-13"
PLANET_BYTES = 93_874_282_582
PLANET_MD5 = "f6b3e7b85e291713f1413442017e24a4"
PLANET_SHA256 = "14774547661414e1b5df31558aa402d2e489b97e16966f319b0e6e059bd31eb4"
PLANET_FETCH_MANIFEST_SHA256 = (
    "10e9e3da4e544920a79912154f3a07e36c6e31e9c88a4f082508ef11b92da15c"
)
PLANET_URL = "https://planet.openstreetmap.org/pbf/planet-260713.osm.pbf"

OUTPUT_DIRECTORY = (
    PROJECT_ROOT / "source_cache" / "osm-blind-tile-auxiliary-260713-v1"
)
OUTPUT_PBF_FILENAME = "stable-industrial-grid.osm.pbf"
IDS_FILENAME = "selected-feature-ids.txt"
LEDGER_FILENAME = "selection-ledger.jsonl"
MANIFEST_FILENAME = "extract-manifest.json"
MANIFEST_SHA_FILENAME = "manifest.sha256"
PIPELINE = "osm_blind_tile_stable_industrial_grid_extraction"
SCHEMA_VERSION = 1
GENERATOR = "DataCenterAtlas/0.1 blind-tile-stable-industrial-grid-v1"
OSMIUM_LICENSE = "GPL-3.0-or-later"
PROCESSOR_FILES = (
    "datacenter_atlas/osm_blind_tile_auxiliary.py",
    "scripts/extract_osm_blind_tile_auxiliary.py",
)
FROZEN_DIRECTORY_MODE = 0o555
FROZEN_FILE_MODE = 0o444

OSM_ATTRIBUTION = "© OpenStreetMap contributors"
OSM_LICENSE = "ODbL-1.0"
OSM_COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"

BROAD_FILTER_EXPRESSIONS = (
    "a/landuse=industrial",
    "nwr/power=substation,line,cable",
    "a/industrial",
)
GRID_POWER_VALUES = frozenset({"substation", "line", "cable"})
VOLTAGE_KEYS = (
    "voltage",
    "voltage:primary",
    "voltage:secondary",
    "voltage:tertiary",
)
MINIMUM_GRID_VOLTAGE_V = 110_000
MAXIMUM_PARSED_VOLTAGE_V = 10_000_000
SMOD_OR_GHSL_INPUT_USED = False

LIFECYCLE_ROOT_KEYS = frozenset(
    {
        "abandoned",
        "construction",
        "demolished",
        "destroyed",
        "disused",
        "proposed",
        "razed",
        "removed",
    }
)
INACTIVE_STATUS_VALUES = frozenset(
    {
        "abandoned",
        "closed",
        "construction",
        "decommissioned",
        "demolished",
        "destroyed",
        "disused",
        "inactive",
        "planned",
        "proposed",
        "razed",
        "removed",
    }
)
STATUS_KEYS = frozenset({"lifecycle", "operational_status", "state", "status"})
FALSE_VALUES = frozenset({"0", "false", "no", "none", "off"})

DATA_CENTER_KEY_PATTERN = re.compile(r"data[ _:-]*cent(?:er|re)")
DATA_CENTER_VALUE_PATTERN = re.compile(
    r"(?<![a-z0-9])data\s*cent(?:er|re)s?(?![a-z0-9])|"
    r"(?<![a-z0-9])datacent(?:er|re)s?(?![a-z0-9])|"
    r"(?<![a-z0-9])server\s*farms?(?![a-z0-9])"
)
DATA_CENTER_EXACT_VALUES = frozenset(
    {
        "data_center",
        "data_centers",
        "data_centre",
        "data_centres",
        "datacenter",
        "datacenters",
        "datacentre",
        "datacentres",
        "server_farm",
        "server_farms",
    }
)
DATA_CENTER_PHRASE_LEXICON = {
    "arabic": ("مركز بيانات", "مركز للبيانات"),
    "bengali": ("ডেটা সেন্টার",),
    "chinese_simplified": ("数据中心",),
    "chinese_traditional": ("數據中心", "資料中心"),
    "czech_slovak": ("datové centrum", "dátové centrum"),
    "dutch": ("datacentrum",),
    "english": ("data center", "data centre", "datacenter", "datacentre", "server farm"),
    "finnish": ("datakeskus",),
    "french": ("centre de données", "centre informatique"),
    "german": ("rechenzentrum",),
    "greek": ("κέντρο δεδομένων",),
    "hebrew": ("מרכז נתונים",),
    "hindi": ("डेटा सेंटर", "डाटा सेंटर"),
    "hungarian": ("adatközpont",),
    "indonesian_malay": ("pusat data",),
    "italian": ("centro dati",),
    "japanese": ("データセンター",),
    "korean": ("데이터 센터", "데이터센터"),
    "persian": ("مرکز داده",),
    "polish": ("centrum danych",),
    "portuguese": ("centro de dados",),
    "romanian": ("centru de date",),
    "russian": ("центр обработки данных", "дата-центр", "дата центр"),
    "scandinavian": ("datacenter", "datasenter", "datorhall"),
    "spanish": ("centro de datos",),
    "thai": ("ศูนย์ข้อมูล",),
    "turkish": ("veri merkezi",),
    "ukrainian": ("центр обробки даних",),
    "vietnamese": ("trung tâm dữ liệu",),
}

FORBIDDEN_INPUT_SEGMENTS = frozenset(
    {
        "candidate-fusion",
        "candidate_fusion",
        "construction-map",
        "construction-maps",
        "construction-master",
        "construction_map",
        "construction_maps",
        "construction_master",
        "osm-structural-shortlist",
        "osm_structural_shortlist",
        "satellite-review-queue",
        "satellite-review-queues",
        "satellite_review_queue",
        "satellite_review_queues",
    }
)

TYPE_LETTERS = {"node": "n", "way": "w", "relation": "r"}
TYPE_ORDER = {"node": 0, "way": 1, "relation": 2}


class OsmBlindTileAuxiliaryError(ValueError):
    """Raised when source, selection, or bundle validation fails closed."""


@dataclass(frozen=True, slots=True)
class VerifiedPlanet:
    path: Path
    fetch_manifest_path: Path
    bytes: int
    md5: str
    sha256: str
    fetch_manifest_sha256: str

    def manifest_document(self) -> dict[str, Any]:
        return {
            "bytes": self.bytes,
            "fetch_manifest": {
                "path": self.fetch_manifest_path.name,
                "sha256": self.fetch_manifest_sha256,
            },
            "md5": self.md5,
            "path": self.path.name,
            "sha256": self.sha256,
            "snapshot_date": PLANET_SNAPSHOT_DATE,
            "url": PLANET_URL,
            "verification": {
                "exact_size": True,
                "official_md5": True,
                "sha256_recomputed_before_extraction": True,
            },
        }


@dataclass(frozen=True, slots=True)
class ExtractionPlan:
    source_path: Path
    fetch_manifest_path: Path
    output_directory: Path
    output_pbf_path: Path
    ids_path: Path
    ledger_path: Path
    manifest_path: Path
    manifest_sha_path: Path
    temporary_pbf_path: Path
    temporary_ids_path: Path
    temporary_ledger_path: Path
    temporary_manifest_path: Path
    temporary_manifest_sha_path: Path
    temporary_scan_stderr_path: Path
    osmium_executable: str
    version_command: tuple[str, ...]
    scan_command: tuple[str, ...]
    getid_command: tuple[str, ...]
    check_refs_command: tuple[str, ...]
    fileinfo_command: tuple[str, ...]

    def contract_document(self) -> dict[str, Any]:
        return {
            "candidate_independent": True,
            "commands": {
                "check_refs": list(self.check_refs_command),
                "fileinfo": list(self.fileinfo_command),
                "getid": list(self.getid_command),
                "scan": list(self.scan_command),
                "version": list(self.version_command),
            },
            "dry_run": True,
            "filter": filter_contract_document(),
            "output_directory": str(self.output_directory),
            "pipeline": PIPELINE,
            "production_frame_built": False,
            "schema_version": SCHEMA_VERSION,
            "source": str(self.source_path),
        }


Clock = Callable[[], str]
Runner = Callable[..., subprocess.CompletedProcess[str]]
PopenFactory = Callable[..., subprocess.Popen[bytes]]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_json(document: Any) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def canonical_json_line(document: Any) -> str:
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ) + "\n"


def _absolute(path: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _regular_file(path: Path, label: str) -> os.stat_result:
    if path.is_symlink():
        raise OsmBlindTileAuxiliaryError(f"{label} must not be a symlink: {path}")
    try:
        status = path.stat()
    except FileNotFoundError as error:
        raise OsmBlindTileAuxiliaryError(f"{label} is missing: {path}") from error
    if not stat.S_ISREG(status.st_mode):
        raise OsmBlindTileAuxiliaryError(f"{label} must be a regular file: {path}")
    return status


def _hash_file(path: Path, algorithms: Iterable[str] = ("sha256",)) -> dict[str, str]:
    hashers = {name: hashlib.new(name) for name in algorithms}
    with path.open("rb") as source:
        while chunk := source.read(16 * 1024 * 1024):
            for hasher in hashers.values():
                hasher.update(chunk)
    return {name: hasher.hexdigest() for name, hasher in hashers.items()}


def _processor_file_lineage() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for relative in PROCESSOR_FILES:
        path = PROJECT_ROOT / relative
        status = _regular_file(path, f"processor file {relative}")
        records[relative] = {
            "bytes": status.st_size,
            "sha256": _hash_file(path)["sha256"],
        }
    return records


def _processor_lineage() -> dict[str, Any]:
    return {
        "files": _processor_file_lineage(),
        "runtime": {
            "platform": {
                "machine": platform.machine(),
                "release": platform.release(),
                "system": platform.system(),
            },
            "python": {
                "cache_tag": sys.implementation.cache_tag,
                "implementation": platform.python_implementation(),
                "version": platform.python_version(),
            },
        },
    }


def _forbidden_input_reference(path: Path) -> str | None:
    for part in path.parts:
        normalized = part.casefold()
        if normalized in FORBIDDEN_INPUT_SEGMENTS:
            return part
    return None


def _validate_input_paths(source: Path, fetch_manifest: Path) -> None:
    for path, label in ((source, "Planet source"), (fetch_manifest, "Planet manifest")):
        forbidden = _forbidden_input_reference(path)
        if forbidden is not None:
            raise OsmBlindTileAuxiliaryError(
                f"{label} references forbidden candidate-derived segment {forbidden!r}"
            )
    if fetch_manifest.parent != source.parent:
        raise OsmBlindTileAuxiliaryError("Planet fetch manifest must be adjacent to Planet")


def verify_planet(
    source_path: str | Path = PLANET_PATH,
    fetch_manifest_path: str | Path = PLANET_FETCH_MANIFEST,
    *,
    expected_filename: str = PLANET_FILENAME,
    expected_bytes: int = PLANET_BYTES,
    expected_md5: str = PLANET_MD5,
    expected_sha256: str = PLANET_SHA256,
    expected_fetch_manifest_sha256: str = PLANET_FETCH_MANIFEST_SHA256,
) -> VerifiedPlanet:
    source = _absolute(source_path)
    fetch_manifest = _absolute(fetch_manifest_path)
    _validate_input_paths(source, fetch_manifest)
    if source.name != expected_filename:
        raise OsmBlindTileAuxiliaryError("Planet filename does not match the pinned snapshot")
    status = _regular_file(source, "Planet source")
    if status.st_size != expected_bytes:
        raise OsmBlindTileAuxiliaryError("Planet byte count does not match the pinned snapshot")
    hashes = _hash_file(source, ("md5", "sha256"))
    if not hmac.compare_digest(hashes["md5"], expected_md5):
        raise OsmBlindTileAuxiliaryError("Planet MD5 does not match the official sidecar")
    if not hmac.compare_digest(hashes["sha256"], expected_sha256):
        raise OsmBlindTileAuxiliaryError("Planet SHA-256 does not match the local acquisition pin")

    manifest_status = _regular_file(fetch_manifest, "Planet fetch manifest")
    raw = fetch_manifest.read_bytes()
    manifest_sha256 = hashlib.sha256(raw).hexdigest()
    if manifest_sha256 != expected_fetch_manifest_sha256:
        raise OsmBlindTileAuxiliaryError("Planet fetch-manifest SHA-256 changed")
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OsmBlindTileAuxiliaryError("Planet fetch manifest is invalid JSON") from error
    if raw != canonical_json(document):
        raise OsmBlindTileAuxiliaryError("Planet fetch manifest must be canonical JSON")
    if (
        document.get("schema_version") != 1
        or document.get("pipeline") != "openstreetmap_planet_fetch"
        or document.get("state") != "completed"
        or document.get("snapshot_date") != PLANET_SNAPSHOT_DATE
    ):
        raise OsmBlindTileAuxiliaryError("Planet fetch manifest identity changed")
    if document.get("input") != {
        "bytes": expected_bytes,
        "md5": expected_md5,
        "path": expected_filename,
        "sha256": expected_sha256,
    }:
        raise OsmBlindTileAuxiliaryError("Planet fetch manifest input checkpoint changed")
    if document.get("verification") != {
        "exact_size": True,
        "official_md5": True,
        "verified_before_extraction": True,
    }:
        raise OsmBlindTileAuxiliaryError("Planet fetch verification flags changed")
    if document.get("rights") != {
        "attribution": OSM_ATTRIBUTION,
        "copyright_url": OSM_COPYRIGHT_URL,
        "license": OSM_LICENSE,
    }:
        raise OsmBlindTileAuxiliaryError("Planet rights checkpoint changed")
    if manifest_status.st_size <= 0:
        raise OsmBlindTileAuxiliaryError("Planet fetch manifest is empty")
    return VerifiedPlanet(
        path=source,
        fetch_manifest_path=fetch_manifest,
        bytes=expected_bytes,
        md5=hashes["md5"],
        sha256=hashes["sha256"],
        fetch_manifest_sha256=manifest_sha256,
    )


def resolve_osmium(executable: str = "osmium") -> str:
    found = shutil.which(executable)
    if found is None:
        raise OsmBlindTileAuxiliaryError(f"osmium is not installed: {executable}")
    resolved = Path(found).resolve(strict=True)
    status = resolved.stat()
    if not stat.S_ISREG(status.st_mode) or not os.access(resolved, os.X_OK):
        raise OsmBlindTileAuxiliaryError("osmium must be an executable regular file")
    return str(resolved)


def build_plan(
    source_path: str | Path = PLANET_PATH,
    fetch_manifest_path: str | Path = PLANET_FETCH_MANIFEST,
    output_directory: str | Path = OUTPUT_DIRECTORY,
    *,
    osmium_executable: str = "osmium",
) -> ExtractionPlan:
    source = _absolute(source_path)
    fetch_manifest = _absolute(fetch_manifest_path)
    output = _absolute(output_directory)
    _validate_input_paths(source, fetch_manifest)
    executable = os.fspath(osmium_executable)
    pbf = output / OUTPUT_PBF_FILENAME
    ids = output / IDS_FILENAME
    ledger = output / LEDGER_FILENAME
    manifest = output / MANIFEST_FILENAME
    manifest_sha = output / MANIFEST_SHA_FILENAME
    temporary_pbf = output / ".stable-industrial-grid.extracting.osm.pbf"
    temporary_ids = output / f".{IDS_FILENAME}.extracting"
    temporary_ledger = output / f".{LEDGER_FILENAME}.extracting"
    temporary_manifest = output / f".{MANIFEST_FILENAME}.extracting"
    temporary_manifest_sha = output / f".{MANIFEST_SHA_FILENAME}.extracting"
    scan_stderr = output / ".scan-stderr.extracting"
    scan_command = (
        executable,
        "tags-filter",
        "--no-progress",
        "--omit-referenced",
        "--output-format=osm,add_metadata=false",
        str(source),
        *BROAD_FILTER_EXPRESSIONS,
    )
    getid_command = (
        executable,
        "getid",
        "--no-progress",
        "--add-referenced",
        "--remove-tags",
        f"--generator={GENERATOR}",
        "--fsync",
        "--id-file",
        str(temporary_ids),
        "--output",
        str(temporary_pbf),
        "--output-format=pbf",
        str(source),
    )
    check_refs_command = (
        executable,
        "check-refs",
        "--no-progress",
        "--check-relations",
        str(temporary_pbf),
    )
    fileinfo_command = (
        executable,
        "fileinfo",
        "--extended",
        "--json",
        "--no-progress",
        str(temporary_pbf),
    )
    return ExtractionPlan(
        source_path=source,
        fetch_manifest_path=fetch_manifest,
        output_directory=output,
        output_pbf_path=pbf,
        ids_path=ids,
        ledger_path=ledger,
        manifest_path=manifest,
        manifest_sha_path=manifest_sha,
        temporary_pbf_path=temporary_pbf,
        temporary_ids_path=temporary_ids,
        temporary_ledger_path=temporary_ledger,
        temporary_manifest_path=temporary_manifest,
        temporary_manifest_sha_path=temporary_manifest_sha,
        temporary_scan_stderr_path=scan_stderr,
        osmium_executable=executable,
        version_command=(executable, "--version"),
        scan_command=scan_command,
        getid_command=getid_command,
        check_refs_command=check_refs_command,
        fileinfo_command=fileinfo_command,
    )


def _normalized_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _normalized_token(value: str) -> str:
    normalized = _normalized_text(value).strip()
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")


def _normalized_phrase_text(value: str) -> str:
    normalized = _normalized_text(value).replace("_", " ").replace("-", " ")
    return " ".join(normalized.split())


def has_data_center_identity(tags: Mapping[str, str]) -> bool:
    for key, value in tags.items():
        normalized_key = _normalized_text(key)
        if DATA_CENTER_KEY_PATTERN.search(normalized_key):
            return True
        normalized_value = _normalized_phrase_text(value)
        if DATA_CENTER_VALUE_PATTERN.search(normalized_value):
            return True
        if _normalized_token(value) in DATA_CENTER_EXACT_VALUES:
            return True
        if any(
            _normalized_phrase_text(phrase) in normalized_value
            for phrases in DATA_CENTER_PHRASE_LEXICON.values()
            for phrase in phrases
        ):
            return True
    return False


def has_unstable_lifecycle(tags: Mapping[str, str]) -> bool:
    for key, value in tags.items():
        normalized_key = _normalized_text(key).strip()
        normalized_value = _normalized_token(value)
        root = normalized_key.split(":", 1)[0]
        if root in LIFECYCLE_ROOT_KEYS and normalized_value not in FALSE_VALUES:
            return True
        if normalized_key in STATUS_KEYS and normalized_value in INACTIVE_STATUS_VALUES:
            return True
    return False


_VOLTAGE_PATTERN = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(kv|v)?", re.IGNORECASE)


def parse_voltage_token(token: str) -> int | None:
    match = _VOLTAGE_PATTERN.fullmatch(token.strip())
    if match is None:
        return None
    try:
        value = Decimal(match.group(1))
    except InvalidOperation:
        return None
    if match.group(2) and match.group(2).casefold() == "kv":
        value *= 1000
    if value != value.to_integral_value():
        return None
    integer = int(value)
    if not 0 < integer <= MAXIMUM_PARSED_VOLTAGE_V:
        return None
    return integer


def parsed_voltages(tags: Mapping[str, str]) -> tuple[int, ...]:
    values: set[int] = set()
    for key in VOLTAGE_KEYS:
        raw = tags.get(key)
        if raw is None:
            continue
        for token in re.split(r"[;,/|]", raw):
            parsed = parse_voltage_token(token)
            if parsed is not None:
                values.add(parsed)
    return tuple(sorted(values))


def _element_tags(element: ET.Element) -> dict[str, str]:
    tags: dict[str, str] = {}
    for child in element:
        if child.tag.rsplit("}", 1)[-1] != "tag":
            continue
        key = child.attrib.get("k")
        value = child.attrib.get("v")
        if key is None or value is None or key in tags:
            raise OsmBlindTileAuxiliaryError("OSM XML contains an invalid or duplicate tag")
        tags[key] = value
    return tags


def _is_area(element: ET.Element, object_type: str, tags: Mapping[str, str]) -> bool:
    if object_type == "way":
        refs = [
            child.attrib.get("ref")
            for child in element
            if child.tag.rsplit("}", 1)[-1] == "nd"
        ]
        return len(refs) >= 4 and refs[0] is not None and refs[0] == refs[-1]
    return object_type == "relation" and tags.get("type") in {
        "boundary",
        "multipolygon",
    }


def classify_element(element: ET.Element) -> tuple[dict[str, Any] | None, dict[str, bool]]:
    object_type = element.tag.rsplit("}", 1)[-1]
    if object_type not in TYPE_LETTERS:
        raise OsmBlindTileAuxiliaryError(f"unexpected OSM object type: {object_type}")
    try:
        osm_id = int(element.attrib["id"])
    except (KeyError, ValueError) as error:
        raise OsmBlindTileAuxiliaryError("OSM XML object has an invalid ID") from error
    if osm_id <= 0:
        raise OsmBlindTileAuxiliaryError("OSM object IDs must be positive")
    tags = _element_tags(element)
    power = _normalized_text(tags.get("power", "")).strip()
    industrial_broad = _is_area(element, object_type, tags) and (
        tags.get("landuse") == "industrial" or "industrial" in tags
    )
    grid_broad = power in GRID_POWER_VALUES
    if not industrial_broad and not grid_broad:
        raise OsmBlindTileAuxiliaryError("broad osmium stream contains a non-matching object")
    dc_excluded = has_data_center_identity(tags)
    lifecycle_excluded = has_unstable_lifecycle(tags)
    voltages = parsed_voltages(tags)
    high_voltage = any(value >= MINIMUM_GRID_VOLTAGE_V for value in voltages)
    flags = {
        "data_center_excluded": dc_excluded,
        "grid_broad": grid_broad,
        "grid_high_voltage": high_voltage,
        "industrial_broad": industrial_broad,
        "lifecycle_excluded": lifecycle_excluded,
    }
    if dc_excluded or lifecycle_excluded:
        return None, flags
    signals: list[str] = []
    if industrial_broad:
        signals.append("industrial")
    if grid_broad and high_voltage:
        signals.append("grid")
    if not signals:
        return None, flags
    voltage_tags = {key: tags[key] for key in VOLTAGE_KEYS if key in tags}
    return {
        "osm_id": osm_id,
        "osm_type": object_type,
        "parsed_voltages_v": list(voltages),
        "power": power or None,
        "signals": signals,
        "voltage_tags": voltage_tags,
    }, flags


def scan_osm_xml(
    source: BinaryIO,
    ids_output: TextIO,
    ledger_output: TextIO,
) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    previous: tuple[int, int] | None = None
    try:
        iterator = ET.iterparse(source, events=("start", "end"))
        try:
            first_event, root = next(iterator)
        except StopIteration as error:
            raise OsmBlindTileAuxiliaryError("osmium broad stream is empty") from error
        if first_event != "start" or root.tag.rsplit("}", 1)[-1] != "osm":
            raise OsmBlindTileAuxiliaryError("osmium broad stream has no OSM root")
        for event, element in iterator:
            if event != "end":
                continue
            object_type = element.tag.rsplit("}", 1)[-1]
            if object_type not in TYPE_LETTERS:
                continue
            try:
                osm_id = int(element.attrib["id"])
            except (KeyError, ValueError) as error:
                raise OsmBlindTileAuxiliaryError("OSM XML object has an invalid ID") from error
            order_key = (TYPE_ORDER[object_type], osm_id)
            if previous is not None and order_key <= previous:
                raise OsmBlindTileAuxiliaryError("broad OSM stream is duplicate or not type/ID ordered")
            previous = order_key
            record, flags = classify_element(element)
            counts["broad_objects"] += 1
            counts[f"broad_{object_type}s"] += 1
            if flags["industrial_broad"]:
                counts["broad_industrial"] += 1
            if flags["grid_broad"]:
                counts["broad_grid"] += 1
            if flags["industrial_broad"] and flags["grid_broad"]:
                counts["broad_both"] += 1
            if flags["data_center_excluded"]:
                counts["excluded_data_center_identity"] += 1
            if flags["lifecycle_excluded"]:
                counts["excluded_unstable_lifecycle"] += 1
            if flags["data_center_excluded"] or flags["lifecycle_excluded"]:
                counts["excluded_any"] += 1
            if flags["grid_broad"] and not flags["grid_high_voltage"]:
                counts["grid_without_parsed_110kv"] += 1
            if record is not None:
                ids_output.write(f"{TYPE_LETTERS[object_type]}{osm_id}\n")
                ledger_output.write(canonical_json_line(record))
                counts["selected_objects"] += 1
                counts[f"selected_{object_type}s"] += 1
                for signal in record["signals"]:
                    counts[f"selected_{signal}"] += 1
                if record["signals"] == ["industrial", "grid"]:
                    counts["selected_both"] += 1
            element.clear()
            root.clear()
    except ET.ParseError as error:
        raise OsmBlindTileAuxiliaryError("osmium broad stream is invalid XML") from error
    if counts["broad_objects"] <= 0:
        raise OsmBlindTileAuxiliaryError("broad OSM scan returned no objects")
    if counts["selected_objects"] <= 0:
        raise OsmBlindTileAuxiliaryError("stable industrial/grid selection is empty")
    keys = (
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
        "selected_objects",
        "selected_nodes",
        "selected_ways",
        "selected_relations",
        "selected_industrial",
        "selected_grid",
        "selected_both",
    )
    return {key: counts[key] for key in keys}


def filter_contract_document() -> dict[str, Any]:
    return {
        "broad_osmium_expressions": list(BROAD_FILTER_EXPRESSIONS),
        "candidate_or_atlas_input_used": False,
        "data_center_exclusion": {
            "all_tag_keys_scanned_for_structured_identity": True,
            "all_tag_values_scanned_against_pinned_phrase_lexicon": True,
            "exact_normalized_values": sorted(DATA_CENTER_EXACT_VALUES),
            "key_pattern": DATA_CENTER_KEY_PATTERN.pattern,
            "localized_name_exclusion_complete": False,
            "multilingual_phrase_lexicon": {
                key: list(values) for key, values in DATA_CENTER_PHRASE_LEXICON.items()
            },
            "multilingual_phrase_lexicon_sha256": hashlib.sha256(
                canonical_json(DATA_CENTER_PHRASE_LEXICON)
            ).hexdigest(),
            "residual_unlisted_language_or_synonym_leakage_is_blocker": True,
            "value_pattern": DATA_CENTER_VALUE_PATTERN.pattern,
        },
        "geometry": {
            "final_references_recursively_recovered_from_same_planet": True,
            "industrial_requires_area_capable_object": True,
            "referenced_only_tags_removed": True,
            "scan_omits_references": True,
        },
        "grid": {
            "minimum_parsed_voltage_v": MINIMUM_GRID_VOLTAGE_V,
            "power_values": sorted(GRID_POWER_VALUES),
            "voltage_keys": list(VOLTAGE_KEYS),
            "voltage_unitless_values_interpreted_as_volts": True,
        },
        "industrial": {
            "positive_tags": ["landuse=industrial", "industrial=*"],
        },
        "lifecycle_exclusion": {
            "false_values_do_not_exclude": sorted(FALSE_VALUES),
            "root_keys": sorted(LIFECYCLE_ROOT_KEYS),
            "status_keys": sorted(STATUS_KEYS),
            "status_values": sorted(INACTIVE_STATUS_VALUES),
        },
        "stable_semantics": (
            "not explicitly construction, proposed, inactive, disused, abandoned, "
            "demolished, destroyed, razed, or removed in selected object tags"
        ),
    }


def _run_text(runner: Runner, command: Sequence[str], label: str) -> str:
    try:
        result = runner(
            list(command),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as error:
        raise OsmBlindTileAuxiliaryError(f"could not execute {label}: {error}") from error
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        raise OsmBlindTileAuxiliaryError(
            f"{label} failed with exit code {result.returncode}: {detail}"
        )
    return (result.stdout or "").strip()


def _osmium_version(runner: Runner, command: Sequence[str]) -> dict[str, str]:
    output = _run_text(runner, command, "osmium version")
    if not output:
        raise OsmBlindTileAuxiliaryError("osmium version output is empty")
    return {"first_line": output.splitlines()[0], "output": output}


def _scan_planet(
    plan: ExtractionPlan,
    *,
    popen_factory: PopenFactory = subprocess.Popen,
) -> tuple[dict[str, Any], dict[str, Any]]:
    with plan.temporary_ids_path.open("x", encoding="utf-8", newline="\n") as ids_output, \
        plan.temporary_ledger_path.open("x", encoding="utf-8", newline="\n") as ledger_output, \
        plan.temporary_scan_stderr_path.open("xb") as stderr_output:
        try:
            process = popen_factory(
                list(plan.scan_command),
                stdout=subprocess.PIPE,
                stderr=stderr_output,
            )
        except OSError as error:
            raise OsmBlindTileAuxiliaryError(f"could not start osmium scan: {error}") from error
        if process.stdout is None:
            process.terminate()
            process.wait()
            raise OsmBlindTileAuxiliaryError("osmium scan has no stdout stream")
        try:
            stats = scan_osm_xml(process.stdout, ids_output, ledger_output)
        except Exception:
            process.terminate()
            process.wait()
            raise
        finally:
            process.stdout.close()
        return_code = process.wait()
        ids_output.flush()
        ledger_output.flush()
        os.fsync(ids_output.fileno())
        os.fsync(ledger_output.fileno())
        os.fsync(stderr_output.fileno())
    stderr_raw = plan.temporary_scan_stderr_path.read_bytes()
    if return_code != 0:
        detail = stderr_raw.decode("utf-8", errors="replace").strip()
        raise OsmBlindTileAuxiliaryError(
            f"osmium tags-filter scan failed with exit code {return_code}: {detail}"
        )
    stderr_checkpoint = {
        "bytes": len(stderr_raw),
        "sha256": hashlib.sha256(stderr_raw).hexdigest(),
    }
    plan.temporary_scan_stderr_path.unlink()
    return stats, stderr_checkpoint


def _normalize_fileinfo(stdout: str, path: Path) -> dict[str, Any]:
    try:
        document = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise OsmBlindTileAuxiliaryError("osmium fileinfo returned invalid JSON") from error
    if not isinstance(document, dict):
        raise OsmBlindTileAuxiliaryError("osmium fileinfo must return an object")
    file_section = document.get("file")
    data = document.get("data")
    header = document.get("header")
    if not all(isinstance(item, Mapping) for item in (file_section, data, header)):
        raise OsmBlindTileAuxiliaryError("osmium fileinfo sections are missing")
    assert isinstance(file_section, Mapping)
    assert isinstance(data, Mapping)
    assert isinstance(header, Mapping)
    if str(file_section.get("format", "")).upper() != "PBF":
        raise OsmBlindTileAuxiliaryError("osmium output is not PBF")
    if file_section.get("size") != path.stat().st_size:
        raise OsmBlindTileAuxiliaryError("osmium fileinfo size does not match output")
    count = data.get("count")
    if not isinstance(count, Mapping):
        raise OsmBlindTileAuxiliaryError("osmium fileinfo counts are missing")
    counts: dict[str, int] = {}
    for key in ("nodes", "ways", "relations"):
        value = count.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise OsmBlindTileAuxiliaryError("osmium fileinfo count is invalid")
        counts[key] = value
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


def _checkpoint(path: Path, label: str) -> dict[str, Any]:
    status = _regular_file(path, label)
    if status.st_size <= 0:
        raise OsmBlindTileAuxiliaryError(f"{label} is empty")
    return {"bytes": status.st_size, "path": path.name, **_hash_file(path)}


def _prepare_output_directory(plan: ExtractionPlan) -> None:
    if plan.output_directory.exists() and not plan.output_directory.is_dir():
        raise OsmBlindTileAuxiliaryError("output path must be a directory")
    plan.output_directory.mkdir(parents=True, exist_ok=True)
    publish_paths = (
        plan.output_pbf_path,
        plan.ids_path,
        plan.ledger_path,
        plan.manifest_path,
        plan.manifest_sha_path,
    )
    existing = [path for path in publish_paths if path.exists() or path.is_symlink()]
    if existing and len(existing) != len(publish_paths):
        raise OsmBlindTileAuxiliaryError("existing auxiliary bundle is incomplete")
    for path in (
        plan.temporary_pbf_path,
        plan.temporary_ids_path,
        plan.temporary_ledger_path,
        plan.temporary_manifest_path,
        plan.temporary_manifest_sha_path,
        plan.temporary_scan_stderr_path,
    ):
        if path.exists() or path.is_symlink():
            raise OsmBlindTileAuxiliaryError(f"stale temporary extraction path: {path}")


def _atomic_create(path: Path, payload: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise OsmBlindTileAuxiliaryError(f"refusing to overwrite {path}")
    with path.open("xb") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _published_paths(plan: ExtractionPlan) -> tuple[Path, ...]:
    return (
        plan.output_pbf_path,
        plan.ids_path,
        plan.ledger_path,
        plan.manifest_path,
        plan.manifest_sha_path,
    )


def _freeze_bundle(plan: ExtractionPlan) -> None:
    for path in _published_paths(plan):
        _regular_file(path, f"published auxiliary artifact {path.name}")
        path.chmod(FROZEN_FILE_MODE)
    plan.output_directory.chmod(FROZEN_DIRECTORY_MODE)


def _validate_frozen_closed_tree(plan: ExtractionPlan) -> None:
    root = plan.output_directory
    if root.is_symlink() or not root.is_dir():
        raise OsmBlindTileAuxiliaryError("auxiliary output must be a regular directory")
    if stat.S_IMODE(root.stat().st_mode) != FROZEN_DIRECTORY_MODE:
        raise OsmBlindTileAuxiliaryError("auxiliary output directory mode must be 0555")
    expected = set(_published_paths(plan))
    actual = set(root.iterdir())
    if actual != expected:
        missing = sorted(path.name for path in expected - actual)
        extra = sorted(path.name for path in actual - expected)
        raise OsmBlindTileAuxiliaryError(
            f"auxiliary output inventory changed; missing={missing}, extra={extra}"
        )
    for path in expected:
        status = _regular_file(path, f"frozen auxiliary artifact {path.name}")
        if stat.S_IMODE(status.st_mode) != FROZEN_FILE_MODE:
            raise OsmBlindTileAuxiliaryError(
                f"auxiliary artifact mode must be 0444: {path.name}"
            )


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
    expected_filename: str = PLANET_FILENAME,
    expected_bytes: int = PLANET_BYTES,
    expected_md5: str = PLANET_MD5,
    expected_sha256: str = PLANET_SHA256,
    expected_fetch_manifest_sha256: str = PLANET_FETCH_MANIFEST_SHA256,
) -> dict[str, Any]:
    plan = build_plan(
        source_path,
        fetch_manifest_path,
        output_directory,
        osmium_executable=osmium_executable,
    )
    _prepare_output_directory(plan)
    if plan.manifest_path.exists():
        return validate_bundle(
            plan.output_directory,
            source_path=plan.source_path,
            fetch_manifest_path=plan.fetch_manifest_path,
            deep_source_hash=True,
            expected_filename=expected_filename,
            expected_bytes=expected_bytes,
            expected_md5=expected_md5,
            expected_sha256=expected_sha256,
            expected_fetch_manifest_sha256=expected_fetch_manifest_sha256,
        )
    processor = _processor_lineage()
    source = verify_planet(
        plan.source_path,
        plan.fetch_manifest_path,
        expected_filename=expected_filename,
        expected_bytes=expected_bytes,
        expected_md5=expected_md5,
        expected_sha256=expected_sha256,
        expected_fetch_manifest_sha256=expected_fetch_manifest_sha256,
    )
    started_at = clock()
    version = _osmium_version(runner, plan.version_command)
    stats, scan_stderr = _scan_planet(plan, popen_factory=popen_factory)
    _run_text(runner, plan.getid_command, "osmium getid")
    _regular_file(plan.temporary_pbf_path, "temporary selected PBF")
    check_refs_stdout = _run_text(runner, plan.check_refs_command, "osmium check-refs")
    fileinfo = _normalize_fileinfo(
        _run_text(runner, plan.fileinfo_command, "osmium fileinfo"),
        plan.temporary_pbf_path,
    )
    outputs = {
        "ids": _checkpoint(plan.temporary_ids_path, "selected IDs"),
        "pbf": _checkpoint(plan.temporary_pbf_path, "selected PBF"),
        "selection_ledger": _checkpoint(plan.temporary_ledger_path, "selection ledger"),
    }
    outputs["ids"]["path"] = plan.ids_path.name
    outputs["pbf"]["path"] = plan.output_pbf_path.name
    outputs["selection_ledger"]["path"] = plan.ledger_path.name
    if _processor_file_lineage() != processor["files"]:
        raise OsmBlindTileAuxiliaryError(
            "selector or CLI changed during the Planet extraction"
        )
    manifest = {
        "candidate_independence": {
            "atlas_release_input_used": False,
            "candidate_fusion_input_used": False,
            "construction_output_input_used": False,
            "only_input": "full dated OSM Planet plus its adjacent acquisition manifest",
            "satellite_queue_input_used": False,
            "structural_shortlist_input_used": False,
        },
        "commands": {
            "check_refs": list(plan.check_refs_command),
            "fileinfo": list(plan.fileinfo_command),
            "getid": list(plan.getid_command),
            "scan": list(plan.scan_command),
            "version": list(plan.version_command),
        },
        "fileinfo": fileinfo,
        "filter": filter_contract_document(),
        "finished_at": clock(),
        "integrity": {
            "check_refs_passed": True,
            "check_refs_stdout": check_refs_stdout,
            "scan_stderr": scan_stderr,
        },
        "invocation": list(invocation),
        "outputs": outputs,
        "pipeline": PIPELINE,
        "processor": processor,
        "production_frame_built": False,
        "rights": {
            "attribution": OSM_ATTRIBUTION,
            "copyright_url": OSM_COPYRIGHT_URL,
            "license": OSM_LICENSE,
        },
        "schema_version": SCHEMA_VERSION,
        "selection_statistics": stats,
        "source": source.manifest_document(),
        "started_at": started_at,
        "state": "completed",
        "tool": {
            "executable": plan.osmium_executable,
            "license": OSMIUM_LICENSE,
            "name": "osmium-tool",
            "version": version,
        },
    }
    _atomic_create(plan.temporary_manifest_path, canonical_json(manifest))
    manifest_sha256 = hashlib.sha256(plan.temporary_manifest_path.read_bytes()).hexdigest()
    _atomic_create(
        plan.temporary_manifest_sha_path,
        f"{manifest_sha256}  {MANIFEST_FILENAME}\n".encode("ascii"),
    )
    for temporary, final in (
        (plan.temporary_pbf_path, plan.output_pbf_path),
        (plan.temporary_ids_path, plan.ids_path),
        (plan.temporary_ledger_path, plan.ledger_path),
        (plan.temporary_manifest_path, plan.manifest_path),
        (plan.temporary_manifest_sha_path, plan.manifest_sha_path),
    ):
        if final.exists() or final.is_symlink():
            raise OsmBlindTileAuxiliaryError(f"refusing to overwrite {final}")
        temporary.replace(final)
    _fsync_directory(plan.output_directory)
    _freeze_bundle(plan)
    _fsync_directory(plan.output_directory)
    return validate_bundle(
        plan.output_directory,
        source_path=plan.source_path,
        fetch_manifest_path=plan.fetch_manifest_path,
        deep_source_hash=False,
        expected_filename=expected_filename,
        expected_bytes=expected_bytes,
        expected_md5=expected_md5,
        expected_sha256=expected_sha256,
        expected_fetch_manifest_sha256=expected_fetch_manifest_sha256,
    )


def _validate_ids_and_ledger(ids_path: Path, ledger_path: Path) -> int:
    count = 0
    previous: tuple[int, int] | None = None
    with ids_path.open("r", encoding="utf-8", newline="") as ids_file, ledger_path.open(
        "r", encoding="utf-8", newline=""
    ) as ledger_file:
        for ids_line, ledger_line in zip(ids_file, ledger_file, strict=True):
            match = re.fullmatch(r"([nwr])([1-9][0-9]*)\n", ids_line)
            if match is None:
                raise OsmBlindTileAuxiliaryError("selected ID file has an invalid line")
            try:
                record = json.loads(ledger_line)
            except json.JSONDecodeError as error:
                raise OsmBlindTileAuxiliaryError("selection ledger has invalid JSON") from error
            if ledger_line != canonical_json_line(record):
                raise OsmBlindTileAuxiliaryError("selection ledger line is not canonical")
            reverse_types = {value: key for key, value in TYPE_LETTERS.items()}
            object_type = reverse_types[match.group(1)]
            osm_id = int(match.group(2))
            if record.get("osm_type") != object_type or record.get("osm_id") != osm_id:
                raise OsmBlindTileAuxiliaryError("selection ID and ledger record differ")
            signals = record.get("signals")
            if signals not in (["industrial"], ["grid"], ["industrial", "grid"]):
                raise OsmBlindTileAuxiliaryError("selection ledger signals are invalid")
            voltages = record.get("parsed_voltages_v")
            if not isinstance(voltages, list) or any(
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
                for value in voltages
            ):
                raise OsmBlindTileAuxiliaryError("selection ledger voltage list is invalid")
            if "grid" in signals and not any(
                value >= MINIMUM_GRID_VOLTAGE_V for value in voltages
            ):
                raise OsmBlindTileAuxiliaryError("grid selection is below 110 kV")
            order = (TYPE_ORDER[object_type], osm_id)
            if previous is not None and order <= previous:
                raise OsmBlindTileAuxiliaryError("selection ledger is not type/ID ordered")
            previous = order
            count += 1
    if count <= 0:
        raise OsmBlindTileAuxiliaryError("selection ledger is empty")
    return count


def validate_bundle(
    output_directory: str | Path = OUTPUT_DIRECTORY,
    *,
    source_path: str | Path = PLANET_PATH,
    fetch_manifest_path: str | Path = PLANET_FETCH_MANIFEST,
    deep_source_hash: bool = True,
    expected_filename: str = PLANET_FILENAME,
    expected_bytes: int = PLANET_BYTES,
    expected_md5: str = PLANET_MD5,
    expected_sha256: str = PLANET_SHA256,
    expected_fetch_manifest_sha256: str = PLANET_FETCH_MANIFEST_SHA256,
) -> dict[str, Any]:
    plan = build_plan(source_path, fetch_manifest_path, output_directory)
    _validate_frozen_closed_tree(plan)
    for path, label in (
        (plan.output_pbf_path, "selected PBF"),
        (plan.ids_path, "selected IDs"),
        (plan.ledger_path, "selection ledger"),
        (plan.manifest_path, "extraction manifest"),
        (plan.manifest_sha_path, "manifest SHA-256"),
    ):
        _regular_file(path, label)
    raw = plan.manifest_path.read_bytes()
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OsmBlindTileAuxiliaryError("extraction manifest is invalid JSON") from error
    if raw != canonical_json(document):
        raise OsmBlindTileAuxiliaryError("extraction manifest must be canonical JSON")
    digest = hashlib.sha256(raw).hexdigest()
    if plan.manifest_sha_path.read_bytes() != f"{digest}  {MANIFEST_FILENAME}\n".encode(
        "ascii"
    ):
        raise OsmBlindTileAuxiliaryError("manifest SHA-256 sidecar changed")
    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("pipeline") != PIPELINE
        or document.get("state") != "completed"
        or document.get("production_frame_built") is not False
        or document.get("filter") != filter_contract_document()
    ):
        raise OsmBlindTileAuxiliaryError("extraction manifest identity or filter changed")
    if document.get("rights") != {
        "attribution": OSM_ATTRIBUTION,
        "copyright_url": OSM_COPYRIGHT_URL,
        "license": OSM_LICENSE,
    }:
        raise OsmBlindTileAuxiliaryError("extraction rights changed")
    processor = document.get("processor")
    if not isinstance(processor, Mapping) or processor.get(
        "files"
    ) != _processor_file_lineage():
        raise OsmBlindTileAuxiliaryError("selector or CLI lineage changed")
    runtime = processor.get("runtime")
    if not isinstance(runtime, Mapping) or set(runtime) != {"platform", "python"}:
        raise OsmBlindTileAuxiliaryError("processor runtime lineage is invalid")
    for section, keys in (
        (runtime.get("platform"), {"machine", "release", "system"}),
        (runtime.get("python"), {"cache_tag", "implementation", "version"}),
    ):
        if (
            not isinstance(section, Mapping)
            or set(section) != keys
            or any(not isinstance(value, str) or not value for value in section.values())
        ):
            raise OsmBlindTileAuxiliaryError("processor runtime lineage is invalid")
    source_document = document.get("source")
    if not isinstance(source_document, Mapping):
        raise OsmBlindTileAuxiliaryError("extraction source checkpoint is missing")
    if deep_source_hash:
        verified = verify_planet(
            plan.source_path,
            plan.fetch_manifest_path,
            expected_filename=expected_filename,
            expected_bytes=expected_bytes,
            expected_md5=expected_md5,
            expected_sha256=expected_sha256,
            expected_fetch_manifest_sha256=expected_fetch_manifest_sha256,
        )
        if source_document != verified.manifest_document():
            raise OsmBlindTileAuxiliaryError("extraction source checkpoint changed")
    else:
        if (
            source_document.get("bytes") != expected_bytes
            or source_document.get("md5") != expected_md5
            or source_document.get("sha256") != expected_sha256
            or source_document.get("snapshot_date") != PLANET_SNAPSHOT_DATE
        ):
            raise OsmBlindTileAuxiliaryError("extraction source checkpoint changed")
    outputs = document.get("outputs")
    if not isinstance(outputs, Mapping):
        raise OsmBlindTileAuxiliaryError("extraction output checkpoints are missing")
    current = {
        "ids": _checkpoint(plan.ids_path, "selected IDs"),
        "pbf": _checkpoint(plan.output_pbf_path, "selected PBF"),
        "selection_ledger": _checkpoint(plan.ledger_path, "selection ledger"),
    }
    for key, path in (
        ("ids", plan.ids_path),
        ("pbf", plan.output_pbf_path),
        ("selection_ledger", plan.ledger_path),
    ):
        current[key]["path"] = path.name
    if outputs != current:
        raise OsmBlindTileAuxiliaryError("extraction output hash changed")
    selected_count = _validate_ids_and_ledger(plan.ids_path, plan.ledger_path)
    statistics = document.get("selection_statistics")
    if not isinstance(statistics, Mapping) or statistics.get("selected_objects") != selected_count:
        raise OsmBlindTileAuxiliaryError("selection statistics do not match ledger")
    independence = document.get("candidate_independence")
    if not isinstance(independence, Mapping) or any(
        independence.get(key) is not False
        for key in (
            "atlas_release_input_used",
            "candidate_fusion_input_used",
            "construction_output_input_used",
            "satellite_queue_input_used",
            "structural_shortlist_input_used",
        )
    ):
        raise OsmBlindTileAuxiliaryError("candidate-independence checkpoint changed")
    integrity = document.get("integrity")
    if not isinstance(integrity, Mapping) or integrity.get("check_refs_passed") is not True:
        raise OsmBlindTileAuxiliaryError("referential-integrity checkpoint changed")
    return dict(document)


__all__ = [
    "BROAD_FILTER_EXPRESSIONS",
    "MINIMUM_GRID_VOLTAGE_V",
    "OsmBlindTileAuxiliaryError",
    "OUTPUT_DIRECTORY",
    "PLANET_FETCH_MANIFEST",
    "PLANET_PATH",
    "build_plan",
    "classify_element",
    "extract_auxiliary",
    "filter_contract_document",
    "has_data_center_identity",
    "has_unstable_lifecycle",
    "parse_voltage_token",
    "parsed_voltages",
    "resolve_osmium",
    "scan_osm_xml",
    "validate_bundle",
    "verify_planet",
]
