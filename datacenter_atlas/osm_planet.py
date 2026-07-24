"""Loss-aware materialization of a filtered OSM planet for the OSM adapter.

The planet extractor deliberately keeps referenced OSM objects.  This module
converts that PBF to OSM XML with ``osmium cat`` and then resolves the XML into
the small Overpass-JSON dialect consumed by :class:`OpenStreetMapAdapter`.
OSM XML is used as the bridge because GeoJSON conversion can silently omit
non-area relations.
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
import shutil
import stat
import subprocess
import tempfile
from typing import Any, Callable, Iterable, Mapping, Sequence
import xml.etree.ElementTree as ElementTree

from .ohsome import DATA_CENTER_FILTER
from .taginfo_targets import explicit_tag_pairs


SCHEMA_VERSION = 1
PIPELINE = "openstreetmap_planet_materialize"
EXTRACTION_PIPELINES = {
    "openstreetmap_planet_extract",
    "openstreetmap_planet_extraction",
    "openstreetmap_planet_data_center_extraction",
}
OSM_ATTRIBUTION = "© OpenStreetMap contributors"
OSM_LICENSE = "ODbL-1.0"
OSM_COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"
DEFAULT_XML_FILENAME = "filtered.osm"
DEFAULT_JSON_FILENAME = "overpass.json"
DEFAULT_MANIFEST_FILENAME = "manifest.json"
TYPE_ORDER = {"node": 0, "way": 1, "relation": 2}
EXACT_TAG_PAIRS = explicit_tag_pairs(DATA_CENTER_FILTER)
EXACT_TAG_PAIR_SET = frozenset(EXACT_TAG_PAIRS)
TAG_FILTER_SHA256 = hashlib.sha256(DATA_CENTER_FILTER.encode("utf-8")).hexdigest()


class PlanetMaterializationError(ValueError):
    """Raised when lineage or materialization integrity cannot be proved."""


class MissingReferenceError(PlanetMaterializationError):
    """Raised when the filtered PBF did not retain geometry references."""

    def __init__(self, missing_references: Sequence[Mapping[str, Any]]) -> None:
        self.missing_references = tuple(dict(item) for item in missing_references)
        preview = ", ".join(
            f"{item['owner_type']}/{item['owner_id']} -> "
            f"{item['member_type']}/{item['member_id']}"
            for item in self.missing_references[:5]
        )
        suffix = "" if len(self.missing_references) <= 5 else ", ..."
        super().__init__(
            f"filtered OSM input is missing {len(self.missing_references)} retained "
            f"reference(s): {preview}{suffix}"
        )


@dataclass(frozen=True, slots=True)
class ExtractionInput:
    manifest_path: Path
    manifest_sha256: str
    manifest_bytes: int
    document: dict[str, Any]
    pbf_path: Path
    pbf_md5: str
    pbf_sha256: str
    pbf_bytes: int
    pbf_record: dict[str, Any]
    source_object_counts: dict[str, int]
    source_retrieved_at: str | None = None


@dataclass(frozen=True, slots=True)
class NodeRecord:
    element_id: int
    latitude: float | None
    longitude: float | None
    tags: dict[str, str]
    attributes: dict[str, Any]


@dataclass(frozen=True, slots=True)
class WayRecord:
    element_id: int
    node_refs: tuple[int, ...]
    tags: dict[str, str]
    attributes: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MemberRecord:
    member_type: str
    ref: int
    role: str


@dataclass(frozen=True, slots=True)
class RelationRecord:
    element_id: int
    members: tuple[MemberRecord, ...]
    tags: dict[str, str]
    attributes: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ParsedOSM:
    nodes: dict[int, NodeRecord]
    ways: dict[int, WayRecord]
    relations: dict[int, RelationRecord]
    source_counts: dict[str, int]


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(document: Any) -> bytes:
    return (
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def pretty_json_bytes(document: Any) -> bytes:
    return (
        json.dumps(
            document,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _absolute(path: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def inspect_file(
    path: Path, algorithms: Sequence[str] = ("sha256",)
) -> dict[str, Any]:
    if path.is_symlink():
        raise PlanetMaterializationError(f"refusing symlink input: {path}")
    try:
        facts = path.stat()
    except FileNotFoundError as error:
        raise PlanetMaterializationError(f"required input is missing: {path}") from error
    if not stat.S_ISREG(facts.st_mode):
        raise PlanetMaterializationError(f"required input is not a regular file: {path}")
    hashers = {name: hashlib.new(name) for name in algorithms}
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            for hasher in hashers.values():
                hasher.update(chunk)
    return {
        "bytes": facts.st_size,
        **{name: hasher.hexdigest() for name, hasher in hashers.items()},
    }


def _load_json_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink():
        raise PlanetMaterializationError(f"refusing symlink {label}: {path}")
    try:
        raw = path.read_bytes()
    except FileNotFoundError as error:
        raise PlanetMaterializationError(f"{label} is missing: {path}") from error
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PlanetMaterializationError(f"{label} is not valid JSON") from error
    if not isinstance(document, dict):
        raise PlanetMaterializationError(f"{label} must be a JSON object")
    return document, raw


def _safe_manifest_path(base: Path, raw_path: Any, label: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise PlanetMaterializationError(f"{label} path must be a non-empty string")
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return _absolute(candidate)
    resolved_base = _absolute(base)
    resolved = _absolute(resolved_base / candidate)
    try:
        resolved.relative_to(resolved_base)
    except ValueError as error:
        raise PlanetMaterializationError(f"{label} path escapes its manifest directory") from error
    return resolved


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_md5(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 32
        and all(character in "0123456789abcdef" for character in value)
    )


def _extract_pbf_record(document: Mapping[str, Any]) -> dict[str, Any]:
    """Accept the extractor's named output while rejecting ambiguous records."""
    candidates: list[dict[str, Any]] = []
    outputs = document.get("outputs")
    if isinstance(outputs, Mapping):
        for key in ("filtered_pbf", "pbf"):
            record = outputs.get(key)
            if isinstance(record, Mapping):
                candidates.append(dict(record))
    for key in ("output", "filtered_pbf"):
        record = document.get(key)
        if isinstance(record, Mapping):
            candidates.append(dict(record))
    unique = {
        (record.get("path"), record.get("sha256"), record.get("bytes")):
        record
        for record in candidates
    }
    if len(unique) != 1:
        raise PlanetMaterializationError(
            "extraction manifest must identify exactly one filtered PBF output"
        )
    return next(iter(unique.values()))


def _manifest_tag_pairs(document: Mapping[str, Any]) -> tuple[tuple[str, str], ...] | None:
    values: Any = None
    filter_document = document.get("filter")
    if isinstance(filter_document, Mapping):
        values = filter_document.get("exact_tag_pairs")
    transform = document.get("transform")
    if values is None and isinstance(transform, Mapping):
        values = transform.get("tag_pairs") or transform.get("filter_pairs")
    if values is None:
        values = document.get("tag_pairs") or document.get("filter_pairs")
    if values is None:
        return None
    pairs: list[tuple[str, str]] = []
    if not isinstance(values, list):
        raise PlanetMaterializationError("extraction manifest tag_pairs must be a list")
    for item in values:
        if isinstance(item, Mapping):
            key, value = item.get("key"), item.get("value")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            key, value = item
        else:
            raise PlanetMaterializationError("extraction manifest has malformed tag_pairs")
        if not isinstance(key, str) or not isinstance(value, str):
            raise PlanetMaterializationError("extraction manifest tag pairs must be strings")
        pairs.append((key, value))
    return tuple(pairs)


def _validate_extraction_filter(document: Mapping[str, Any]) -> None:
    filter_document = document.get("filter")
    if filter_document is not None:
        if not isinstance(filter_document, Mapping):
            raise PlanetMaterializationError("extraction manifest filter must be an object")
        expected_expressions = [
            f"nwr/{key}={value}" for key, value in EXACT_TAG_PAIRS
        ]
        required = {
            "source_filter_expression": DATA_CENTER_FILTER,
            "source_filter_sha256": TAG_FILTER_SHA256,
            "equality_pair_count": len(EXACT_TAG_PAIRS),
            "exact_tag_pairs": [
                {"key": key, "value": value} for key, value in EXACT_TAG_PAIRS
            ],
            "osmium_expressions": expected_expressions,
            "object_types": ["node", "way", "relation"],
            "match_scope": "all_relations_including_non_area_relations",
            "referenced_nodes_and_members_retained": True,
            "omit_referenced_flag_used": False,
            "output_object_counts_include_references": True,
            "converted_to_geojson": False,
        }
        for key, expected in required.items():
            if filter_document.get(key) != expected:
                raise PlanetMaterializationError(
                    f"extraction manifest filter.{key} does not match the canonical contract"
                )
        return

    transform = document.get("transform")
    filter_text = None
    filter_sha = None
    retained_references = None
    if isinstance(transform, Mapping):
        filter_text = transform.get("ohsome_filter") or transform.get("tag_filter")
        filter_sha = transform.get("tag_filter_sha256")
        retained_references = transform.get("retained_references")
    filter_text = filter_text or document.get("ohsome_filter") or document.get("tag_filter")
    filter_sha = filter_sha or document.get("tag_filter_sha256")
    if retained_references is None:
        retained_references = document.get("retained_references")

    pairs = _manifest_tag_pairs(document)
    if pairs is not None and pairs != EXACT_TAG_PAIRS:
        raise PlanetMaterializationError(
            "extraction manifest tag pairs do not match the canonical 92-pair filter"
        )
    if filter_text is not None and filter_text != DATA_CENTER_FILTER:
        raise PlanetMaterializationError(
            "extraction manifest tag filter does not match the canonical filter"
        )
    if filter_sha is not None and filter_sha != TAG_FILTER_SHA256:
        raise PlanetMaterializationError("extraction manifest tag filter SHA256 does not match")
    if pairs is None and filter_text is None and filter_sha is None:
        raise PlanetMaterializationError(
            "extraction manifest does not bind its output to the canonical tag filter"
        )
    if retained_references is not True:
        raise PlanetMaterializationError(
            "extraction manifest must explicitly attest that references were retained"
        )


def _validate_extraction_lineage(
    document: Mapping[str, Any], manifest_directory: Path
) -> dict[str, int]:
    source = document.get("source")
    if not isinstance(source, Mapping):
        raise PlanetMaterializationError("extraction manifest source must be an object")
    if not isinstance(source.get("path"), str) or not source["path"]:
        raise PlanetMaterializationError("extraction manifest source.path is invalid")
    if not isinstance(source.get("bytes"), int) or source["bytes"] <= 0:
        raise PlanetMaterializationError("extraction manifest source.bytes is invalid")
    if not _is_md5(source.get("md5")) or not _is_sha256(source.get("sha256")):
        raise PlanetMaterializationError("extraction manifest source hashes are invalid")
    if source.get("snapshot_date") != document.get("snapshot_date"):
        raise PlanetMaterializationError(
            "extraction manifest source snapshot does not match the extraction snapshot"
        )
    try:
        datetime.strptime(str(source["snapshot_date"]), "%Y-%m-%d")
    except ValueError as error:
        raise PlanetMaterializationError(
            "extraction manifest source snapshot date is invalid"
        ) from error
    expected_url = f"https://planet.openstreetmap.org/pbf/{source['path']}"
    if source.get("url") != expected_url:
        raise PlanetMaterializationError(
            "extraction manifest source URL is not the official dated Planet object"
        )
    source_path = _safe_manifest_path(
        manifest_directory, source["path"], "Planet source PBF"
    )
    if source_path.is_symlink():
        raise PlanetMaterializationError(f"refusing Planet source PBF symlink: {source_path}")
    try:
        source_facts = source_path.stat()
    except FileNotFoundError as error:
        raise PlanetMaterializationError(
            f"Planet source PBF is missing: {source_path}"
        ) from error
    if not stat.S_ISREG(source_facts.st_mode) or source_facts.st_size != source["bytes"]:
        raise PlanetMaterializationError(
            "Planet source PBF type or byte count does not match extraction lineage"
        )
    verification = source.get("verification")
    if not isinstance(verification, Mapping) or any(
        verification.get(key) is not True
        for key in ("exact_size", "official_md5", "verified_before_extraction")
    ):
        raise PlanetMaterializationError(
            "extraction manifest source verification attestation is incomplete"
        )
    if verification.get("mode") not in {
        "exact_size_and_md5",
        "completed_fetch_manifest_plus_exact_size_and_md5",
    }:
        raise PlanetMaterializationError(
            "extraction manifest source verification mode is invalid"
        )
    fetch_manifest = source.get("fetch_manifest")
    if fetch_manifest is not None:
        if not isinstance(fetch_manifest, Mapping) or not _is_sha256(
            fetch_manifest.get("sha256")
        ):
            raise PlanetMaterializationError(
                "extraction manifest fetch-manifest lineage is invalid"
            )
        fetch_path = _safe_manifest_path(
            manifest_directory,
            fetch_manifest.get("path"),
            "Planet fetch manifest",
        )
        fetch_facts = inspect_file(fetch_path)
        if fetch_facts["sha256"] != fetch_manifest["sha256"]:
            raise PlanetMaterializationError(
                "Planet fetch manifest SHA256 does not match extraction lineage"
            )
        if verification.get("mode") != "completed_fetch_manifest_plus_exact_size_and_md5":
            raise PlanetMaterializationError(
                "extraction source verification mode omits its fetch manifest"
            )
    elif verification.get("mode") != "exact_size_and_md5":
        raise PlanetMaterializationError(
            "extraction source verification mode requires a fetch manifest"
        )

    rights = document.get("rights")
    expected_rights = {
        "license": OSM_LICENSE,
        "attribution": OSM_ATTRIBUTION,
        "copyright_url": OSM_COPYRIGHT_URL,
    }
    if rights != expected_rights:
        raise PlanetMaterializationError("extraction manifest ODbL rights are invalid")

    fileinfo = document.get("fileinfo")
    counts = (
        fileinfo.get("object_counts_including_references")
        if isinstance(fileinfo, Mapping)
        else None
    )
    if not isinstance(counts, Mapping):
        raise PlanetMaterializationError(
            "extraction manifest has no fileinfo reference-inclusive counts"
        )
    normalized: dict[str, int] = {}
    for singular, plural in (("node", "nodes"), ("way", "ways"), ("relation", "relations")):
        value = counts.get(plural)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PlanetMaterializationError(
                f"extraction manifest fileinfo count for {plural} is invalid"
            )
        normalized[singular] = value
    return normalized


def _source_retrieved_at(
    document: Mapping[str, Any], manifest_directory: Path
) -> str | None:
    source = document.get("source")
    if not isinstance(source, Mapping):
        return None
    fetch_record = source.get("fetch_manifest")
    if fetch_record is None:
        return None
    if not isinstance(fetch_record, Mapping) or not _is_sha256(
        fetch_record.get("sha256")
    ):
        raise PlanetMaterializationError(
            "extraction fetch-manifest retrieval lineage is invalid"
        )
    fetch_path = _safe_manifest_path(
        manifest_directory,
        fetch_record.get("path"),
        "Planet fetch manifest",
    )
    fetch_manifest, raw = _load_json_object(fetch_path, "Planet fetch manifest")
    if sha256_bytes(raw) != fetch_record["sha256"]:
        raise PlanetMaterializationError(
            "Planet fetch manifest SHA256 does not match retrieval lineage"
        )
    if (
        fetch_manifest.get("pipeline") != "openstreetmap_planet_fetch"
        or fetch_manifest.get("state") != "completed"
    ):
        raise PlanetMaterializationError("Planet fetch manifest is not completed")
    retrieved_at = fetch_manifest.get("finished_at")
    if not isinstance(retrieved_at, str) or not retrieved_at:
        raise PlanetMaterializationError(
            "Planet fetch manifest has no completion timestamp"
        )
    try:
        parsed = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise PlanetMaterializationError(
            "Planet fetch completion timestamp is invalid"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PlanetMaterializationError(
            "Planet fetch completion timestamp has no UTC offset"
        )
    return retrieved_at


def validate_extraction_input(
    extraction_manifest: str | Path,
    *,
    filtered_pbf: str | Path | None = None,
) -> ExtractionInput:
    manifest_path = _absolute(extraction_manifest)
    document, raw = _load_json_object(manifest_path, "OSM extraction manifest")
    if document.get("schema_version") not in {1, 2}:
        raise PlanetMaterializationError("unsupported OSM extraction manifest schema")
    if document.get("pipeline") not in EXTRACTION_PIPELINES:
        raise PlanetMaterializationError("unexpected OSM extraction manifest pipeline")
    if document.get("state") != "completed":
        raise PlanetMaterializationError("OSM extraction manifest is not completed")
    _validate_extraction_filter(document)
    source_counts = _validate_extraction_lineage(document, manifest_path.parent)
    source_retrieved_at = _source_retrieved_at(document, manifest_path.parent)

    record = _extract_pbf_record(document)
    record_path = _safe_manifest_path(manifest_path.parent, record.get("path"), "filtered PBF")
    pbf_path = _absolute(filtered_pbf) if filtered_pbf is not None else record_path
    if pbf_path != record_path:
        raise PlanetMaterializationError(
            "explicit filtered PBF path does not match the extraction manifest"
        )
    if not isinstance(record.get("bytes"), int) or record["bytes"] <= 0:
        raise PlanetMaterializationError("extraction manifest has an invalid PBF byte count")
    if not _is_sha256(record.get("sha256")):
        raise PlanetMaterializationError("extraction manifest has an invalid PBF SHA256")
    if not _is_md5(record.get("md5")):
        raise PlanetMaterializationError("extraction manifest has an invalid PBF MD5")
    actual = inspect_file(pbf_path, ("md5", "sha256"))
    if actual["bytes"] != record["bytes"]:
        raise PlanetMaterializationError(
            "filtered PBF byte count does not match the extraction manifest"
        )
    if actual["sha256"] != record["sha256"]:
        raise PlanetMaterializationError(
            "filtered PBF SHA256 does not match the extraction manifest"
        )
    if actual["md5"] != record["md5"]:
        raise PlanetMaterializationError(
            "filtered PBF MD5 does not match the extraction manifest"
        )
    return ExtractionInput(
        manifest_path=manifest_path,
        manifest_sha256=sha256_bytes(raw),
        manifest_bytes=len(raw),
        document=document,
        pbf_path=pbf_path,
        pbf_md5=actual["md5"],
        pbf_sha256=actual["sha256"],
        pbf_bytes=actual["bytes"],
        pbf_record=record,
        source_object_counts=source_counts,
        source_retrieved_at=source_retrieved_at,
    )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_int(value: Any, label: str) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError) as error:
        raise PlanetMaterializationError(f"invalid integer {label}: {value!r}") from error


def _parse_osm_id(value: Any, label: str) -> int:
    parsed = _parse_int(value, label)
    if parsed <= 0:
        raise PlanetMaterializationError(f"non-positive {label}: {parsed}")
    return parsed


def _parse_coordinate(value: Any, label: str) -> float | None:
    if value is None:
        return None
    try:
        coordinate = float(str(value))
    except ValueError as error:
        raise PlanetMaterializationError(f"invalid {label}: {value!r}") from error
    if not math.isfinite(coordinate):
        raise PlanetMaterializationError(f"non-finite {label}: {value!r}")
    if label == "latitude" and not -90 <= coordinate <= 90:
        raise PlanetMaterializationError(f"out-of-range latitude: {value!r}")
    if label == "longitude" and not -180 <= coordinate <= 180:
        raise PlanetMaterializationError(f"out-of-range longitude: {value!r}")
    return coordinate


def _element_attributes(attributes: Mapping[str, str]) -> dict[str, Any]:
    preserved: dict[str, Any] = {}
    for key in ("version", "changeset", "uid"):
        if key in attributes:
            preserved[key] = _parse_int(attributes[key], key)
    for key in ("timestamp", "user"):
        if key in attributes:
            preserved[key] = attributes[key]
    if "visible" in attributes:
        value = attributes["visible"].strip().lower()
        if value not in {"true", "false"}:
            raise PlanetMaterializationError(
                f"invalid OSM visible attribute: {attributes['visible']!r}"
            )
        preserved["visible"] = value == "true"
    return preserved


def _parse_tags(element: ElementTree.Element) -> dict[str, str]:
    tags: dict[str, str] = {}
    for child in element:
        if _local_name(child.tag) != "tag":
            continue
        key = child.attrib.get("k")
        value = child.attrib.get("v")
        if key is None or value is None:
            raise PlanetMaterializationError("OSM tag is missing k or v")
        if key in tags:
            raise PlanetMaterializationError(f"OSM object contains duplicate tag key {key!r}")
        tags[key] = value
    return dict(sorted(tags.items()))


def parse_osm_xml(path: str | Path) -> ParsedOSM:
    """Stream one osmium-generated OSM XML file into reference tables."""
    xml_path = Path(path)
    if xml_path.is_symlink():
        raise PlanetMaterializationError(f"refusing symlink OSM XML: {xml_path}")
    nodes: dict[int, NodeRecord] = {}
    ways: dict[int, WayRecord] = {}
    relations: dict[int, RelationRecord] = {}
    counts: Counter[str] = Counter()
    try:
        iterator = ElementTree.iterparse(xml_path, events=("end",))
        for _, element in iterator:
            object_type = _local_name(element.tag)
            if object_type not in TYPE_ORDER:
                continue
            element_id = _parse_osm_id(element.attrib.get("id"), f"{object_type} id")
            table: dict[int, Any]
            if object_type == "node":
                table = nodes
                latitude = _parse_coordinate(element.attrib.get("lat"), "latitude")
                longitude = _parse_coordinate(element.attrib.get("lon"), "longitude")
                record: Any = NodeRecord(
                    element_id,
                    latitude,
                    longitude,
                    _parse_tags(element),
                    _element_attributes(element.attrib),
                )
            elif object_type == "way":
                table = ways
                refs = tuple(
                    _parse_osm_id(child.attrib.get("ref"), "way node reference")
                    for child in element
                    if _local_name(child.tag) == "nd"
                )
                record = WayRecord(
                    element_id,
                    refs,
                    _parse_tags(element),
                    _element_attributes(element.attrib),
                )
            else:
                table = relations
                members: list[MemberRecord] = []
                for child in element:
                    if _local_name(child.tag) != "member":
                        continue
                    member_type = child.attrib.get("type")
                    if member_type not in TYPE_ORDER:
                        raise PlanetMaterializationError(
                            f"relation/{element_id} has unsupported member type {member_type!r}"
                        )
                    members.append(
                        MemberRecord(
                            member_type,
                            _parse_osm_id(
                                child.attrib.get("ref"), "relation member reference"
                            ),
                            child.attrib.get("role", ""),
                        )
                    )
                record = RelationRecord(
                    element_id,
                    tuple(members),
                    _parse_tags(element),
                    _element_attributes(element.attrib),
                )
            if element_id in table:
                raise PlanetMaterializationError(
                    f"OSM XML contains duplicate {object_type}/{element_id}"
                )
            table[element_id] = record
            counts[object_type] += 1
            element.clear()
    except ElementTree.ParseError as error:
        raise PlanetMaterializationError(f"OSM XML is malformed: {error}") from error
    return ParsedOSM(nodes, ways, relations, dict(counts))


def is_exact_match(tags: Mapping[str, str]) -> bool:
    return any((key, value) in EXACT_TAG_PAIR_SET for key, value in tags.items())


def _point(node: NodeRecord) -> dict[str, float] | None:
    if node.latitude is None or node.longitude is None:
        return None
    return {"lat": node.latitude, "lon": node.longitude}


def _bounds(points: Iterable[Mapping[str, float]]) -> dict[str, float] | None:
    coordinates = list(points)
    if not coordinates:
        return None
    latitudes = [point["lat"] for point in coordinates]
    longitudes = [point["lon"] for point in coordinates]
    return {
        "minlat": min(latitudes),
        "minlon": min(longitudes),
        "maxlat": max(latitudes),
        "maxlon": max(longitudes),
    }


def _center(bounds: Mapping[str, float]) -> dict[str, float]:
    return {
        "lat": (bounds["minlat"] + bounds["maxlat"]) / 2,
        "lon": (bounds["minlon"] + bounds["maxlon"]) / 2,
    }


@dataclass(frozen=True, slots=True)
class _WayFragment:
    member_index: int
    way_id: int
    node_refs: tuple[int, ...]
    points: tuple[dict[str, float], ...]


@dataclass(frozen=True, slots=True)
class _StitchedRing:
    member_indices: tuple[int, ...]
    way_ids: tuple[int, ...]
    node_refs: tuple[int, ...]
    points: tuple[dict[str, float], ...]

    @property
    def sort_key(self) -> tuple[Any, ...]:
        return (min(self.member_indices), self.way_ids, self.node_refs)


def _unresolved_fragments(
    role: str,
    fragments: Iterable[_WayFragment],
    reason: str,
) -> dict[str, Any]:
    ordered = sorted(fragments, key=lambda item: (item.member_index, item.way_id))
    return {
        "role": role,
        "reason": reason,
        "member_indices": [item.member_index for item in ordered],
        "way_ids": [item.way_id for item in ordered],
    }


def _signed_ring_area(points: Sequence[Mapping[str, float]]) -> float:
    return sum(
        first["lon"] * second["lat"] - second["lon"] * first["lat"]
        for first, second in zip(points, points[1:])
    ) / 2


def _orientation(
    first: tuple[float, float],
    second: tuple[float, float],
    third: tuple[float, float],
) -> float:
    return (second[0] - first[0]) * (third[1] - first[1]) - (
        second[1] - first[1]
    ) * (third[0] - first[0])


def _on_segment(
    first: tuple[float, float],
    point: tuple[float, float],
    second: tuple[float, float],
    *,
    epsilon: float = 1e-12,
) -> bool:
    return (
        min(first[0], second[0]) - epsilon
        <= point[0]
        <= max(first[0], second[0]) + epsilon
        and min(first[1], second[1]) - epsilon
        <= point[1]
        <= max(first[1], second[1]) + epsilon
        and abs(_orientation(first, second, point)) <= epsilon
    )


def _segments_intersect(
    first_start: tuple[float, float],
    first_end: tuple[float, float],
    second_start: tuple[float, float],
    second_end: tuple[float, float],
    *,
    epsilon: float = 1e-12,
) -> bool:
    orientations = (
        _orientation(first_start, first_end, second_start),
        _orientation(first_start, first_end, second_end),
        _orientation(second_start, second_end, first_start),
        _orientation(second_start, second_end, first_end),
    )
    if (
        orientations[0] * orientations[1] < -epsilon
        and orientations[2] * orientations[3] < -epsilon
    ):
        return True
    return any(
        abs(orientation) <= epsilon and _on_segment(start, point, end)
        for orientation, start, point, end in (
            (orientations[0], first_start, second_start, first_end),
            (orientations[1], first_start, second_end, first_end),
            (orientations[2], second_start, first_start, second_end),
            (orientations[3], second_start, first_end, second_end),
        )
    )


def _ring_validation_error(ring: _StitchedRing) -> str | None:
    refs = ring.node_refs
    if len(refs) < 4 or refs[0] != refs[-1]:
        return "not_closed_or_too_short"
    if len(set(refs[:-1])) < 3:
        return "fewer_than_three_distinct_vertices"
    if len(set(refs[:-1])) != len(refs) - 1:
        return "repeated_interior_vertex"
    if len(ring.points) != len(refs):
        return "coordinate_count_mismatch"
    if abs(_signed_ring_area(ring.points)) <= 1e-15:
        return "zero_area_ring"
    segments = [
        (
            (ring.points[index]["lon"], ring.points[index]["lat"]),
            (ring.points[index + 1]["lon"], ring.points[index + 1]["lat"]),
        )
        for index in range(len(ring.points) - 1)
    ]
    last_index = len(segments) - 1
    for first_index, first in enumerate(segments):
        for second_index in range(first_index + 1, len(segments)):
            if second_index == first_index + 1 or (
                first_index == 0 and second_index == last_index
            ):
                continue
            if _segments_intersect(*first, *segments[second_index]):
                return "self_intersecting_ring"
    return None


def _stitch_role_fragments(
    fragments: Sequence[_WayFragment],
    *,
    role: str,
) -> tuple[list[_StitchedRing], list[dict[str, Any]]]:
    rings: list[_StitchedRing] = []
    unresolved: list[dict[str, Any]] = []
    open_fragments: list[_WayFragment] = []
    for fragment in sorted(fragments, key=lambda item: (item.member_index, item.way_id)):
        if len(fragment.node_refs) < 2 or len(fragment.points) != len(fragment.node_refs):
            unresolved.append(
                _unresolved_fragments(role, [fragment], "insufficient_complete_geometry")
            )
        elif fragment.node_refs[0] == fragment.node_refs[-1]:
            ring = _StitchedRing(
                (fragment.member_index,),
                (fragment.way_id,),
                fragment.node_refs,
                fragment.points,
            )
            reason = _ring_validation_error(ring)
            if reason is None:
                rings.append(ring)
            else:
                unresolved.append(_unresolved_fragments(role, [fragment], reason))
        else:
            open_fragments.append(fragment)

    by_index = {fragment.member_index: fragment for fragment in open_fragments}
    incident: dict[int, list[int]] = {}
    for fragment in open_fragments:
        incident.setdefault(fragment.node_refs[0], []).append(fragment.member_index)
        incident.setdefault(fragment.node_refs[-1], []).append(fragment.member_index)

    remaining = set(by_index)
    while remaining:
        seed = min(remaining)
        component_edges: set[int] = set()
        frontier = [seed]
        component_nodes: set[int] = set()
        while frontier:
            edge_index = frontier.pop()
            if edge_index in component_edges:
                continue
            component_edges.add(edge_index)
            fragment = by_index[edge_index]
            for node_id in (fragment.node_refs[0], fragment.node_refs[-1]):
                component_nodes.add(node_id)
                frontier.extend(incident.get(node_id, ()))
        remaining.difference_update(component_edges)
        component = [by_index[index] for index in sorted(component_edges)]
        if any(
            sum(index in component_edges for index in incident.get(node_id, ())) != 2
            for node_id in component_nodes
        ):
            unresolved.append(
                _unresolved_fragments(role, component, "open_or_branched_component")
            )
            continue

        first = min(component, key=lambda item: (item.member_index, item.way_id))
        start_node = min(first.node_refs[0], first.node_refs[-1])
        if first.node_refs[0] == start_node:
            refs = list(first.node_refs)
            points = [dict(point) for point in first.points]
        else:
            refs = list(reversed(first.node_refs))
            points = [dict(point) for point in reversed(first.points)]
        used = {first.member_index}
        ordered_fragments = [first]
        current = refs[-1]
        failed = False
        while current != start_node:
            candidates = [
                index
                for index in incident.get(current, ())
                if index in component_edges and index not in used
            ]
            if len(candidates) != 1:
                failed = True
                break
            fragment = by_index[candidates[0]]
            if fragment.node_refs[0] == current:
                next_refs = fragment.node_refs
                next_points = fragment.points
            elif fragment.node_refs[-1] == current:
                next_refs = tuple(reversed(fragment.node_refs))
                next_points = tuple(reversed(fragment.points))
            else:
                failed = True
                break
            used.add(fragment.member_index)
            ordered_fragments.append(fragment)
            refs.extend(next_refs[1:])
            points.extend(dict(point) for point in next_points[1:])
            current = refs[-1]
        if failed or used != component_edges:
            unresolved.append(
                _unresolved_fragments(role, component, "ambiguous_component_traversal")
            )
            continue
        ring = _StitchedRing(
            tuple(item.member_index for item in ordered_fragments),
            tuple(item.way_id for item in ordered_fragments),
            tuple(refs),
            tuple(points),
        )
        reason = _ring_validation_error(ring)
        if reason is None:
            rings.append(ring)
        else:
            unresolved.append(_unresolved_fragments(role, component, reason))
    return sorted(rings, key=lambda item: item.sort_key), unresolved


def _point_in_ring(
    point: tuple[float, float], ring: _StitchedRing
) -> int:
    """Return 1 inside, 0 outside, and -1 on the boundary."""
    inside = False
    for first, second in zip(ring.points, ring.points[1:]):
        start = (first["lon"], first["lat"])
        end = (second["lon"], second["lat"])
        if _on_segment(start, point, end):
            return -1
        if (start[1] > point[1]) != (end[1] > point[1]):
            crossing = (end[0] - start[0]) * (point[1] - start[1]) / (
                end[1] - start[1]
            ) + start[0]
            if point[0] < crossing:
                inside = not inside
    return 1 if inside else 0


def _rings_intersect(first: _StitchedRing, second: _StitchedRing) -> bool:
    first_segments = [
        (
            (start["lon"], start["lat"]),
            (end["lon"], end["lat"]),
        )
        for start, end in zip(first.points, first.points[1:])
    ]
    second_segments = [
        (
            (start["lon"], start["lat"]),
            (end["lon"], end["lat"]),
        )
        for start, end in zip(second.points, second.points[1:])
    ]
    return any(
        _segments_intersect(*first_segment, *second_segment)
        for first_segment in first_segments
        for second_segment in second_segments
    )


def _canonical_ring_coordinates(
    ring: _StitchedRing, *, counterclockwise: bool
) -> list[list[float]]:
    coordinates = [
        [point["lon"], point["lat"]] for point in ring.points[:-1]
    ]
    is_counterclockwise = _signed_ring_area(ring.points) > 0
    if is_counterclockwise != counterclockwise:
        coordinates.reverse()
    start = min(range(len(coordinates)), key=lambda index: tuple(coordinates[index]))
    coordinates = coordinates[start:] + coordinates[:start]
    return [*coordinates, coordinates[0]]


def _relation_polygon_geometry(
    relation: RelationRecord,
    parsed: ParsedOSM,
    resolver: "_Resolver",
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    outer_fragments: list[_WayFragment] = []
    inner_fragments: list[_WayFragment] = []
    for member_index, member in enumerate(relation.members):
        if member.member_type != "way" or member.role not in {"", "outer", "inner"}:
            continue
        way = parsed.ways.get(member.ref)
        if way is None:
            continue
        points = resolver.way_points(
            way, owner_type="relation", owner_id=relation.element_id
        )
        fragment = _WayFragment(
            member_index,
            way.element_id,
            way.node_refs,
            tuple(dict(point) for point in points),
        )
        (inner_fragments if member.role == "inner" else outer_fragments).append(
            fragment
        )
    if not outer_fragments and not inner_fragments:
        return None, None

    outer_rings, unresolved = _stitch_role_fragments(
        outer_fragments, role="outer_or_empty"
    )
    inner_rings, inner_unresolved = _stitch_role_fragments(
        inner_fragments, role="inner"
    )
    unresolved.extend(inner_unresolved)

    for index, first in enumerate(outer_rings):
        for second in outer_rings[index + 1 :]:
            first_point = (first.points[0]["lon"], first.points[0]["lat"])
            second_point = (second.points[0]["lon"], second.points[0]["lat"])
            if (
                _rings_intersect(first, second)
                or _point_in_ring(first_point, second) != 0
                or _point_in_ring(second_point, first) != 0
            ):
                unresolved.append(
                    {
                        "role": "outer_or_empty",
                        "reason": "overlapping_or_nested_outer_rings",
                        "member_indices": sorted(
                            {*first.member_indices, *second.member_indices}
                        ),
                        "way_ids": sorted({*first.way_ids, *second.way_ids}),
                    }
                )

    holes_by_outer: dict[int, list[_StitchedRing]] = {
        index: [] for index in range(len(outer_rings))
    }
    for inner in inner_rings:
        containers: list[int] = []
        for outer_index, outer in enumerate(outer_rings):
            strictly_inside = all(
                _point_in_ring((point["lon"], point["lat"]), outer) == 1
                for point in inner.points[:-1]
            )
            if strictly_inside and not _rings_intersect(inner, outer):
                containers.append(outer_index)
        if len(containers) == 1:
            holes_by_outer[containers[0]].append(inner)
        else:
            unresolved.append(
                {
                    "role": "inner",
                    "reason": "inner_ring_not_in_exactly_one_outer",
                    "member_indices": list(inner.member_indices),
                    "way_ids": list(inner.way_ids),
                }
            )

    for outer_index, holes in holes_by_outer.items():
        for index, first in enumerate(holes):
            for second in holes[index + 1 :]:
                first_point = (first.points[0]["lon"], first.points[0]["lat"])
                second_point = (second.points[0]["lon"], second.points[0]["lat"])
                if (
                    _rings_intersect(first, second)
                    or _point_in_ring(first_point, second) != 0
                    or _point_in_ring(second_point, first) != 0
                ):
                    unresolved.append(
                        {
                            "role": "inner",
                            "reason": "overlapping_or_nested_inner_rings",
                            "outer_ring_index": outer_index,
                            "member_indices": sorted(
                                {*first.member_indices, *second.member_indices}
                            ),
                            "way_ids": sorted({*first.way_ids, *second.way_ids}),
                        }
                    )

    unresolved = sorted(
        unresolved,
        key=lambda item: (
            str(item["role"]),
            str(item["reason"]),
            tuple(item["member_indices"]),
            tuple(item["way_ids"]),
        ),
    )
    report = {
        "method": "role_aware_endpoint_stitching",
        "outer_or_empty_member_way_count": len(outer_fragments),
        "inner_member_way_count": len(inner_fragments),
        "outer_ring_count": len(outer_rings),
        "inner_ring_count": len(inner_rings),
        "unresolved_fragments": unresolved,
        "status": "unresolved" if unresolved or not outer_rings else "assembled",
    }
    if unresolved or not outer_rings:
        return None, report

    polygons = []
    for outer_index, outer in enumerate(outer_rings):
        coordinates = [_canonical_ring_coordinates(outer, counterclockwise=True)]
        coordinates.extend(
            _canonical_ring_coordinates(inner, counterclockwise=False)
            for inner in sorted(
                holes_by_outer[outer_index], key=lambda item: item.sort_key
            )
        )
        polygons.append(coordinates)
    geometry: dict[str, Any]
    if len(polygons) == 1:
        geometry = {"type": "Polygon", "coordinates": polygons[0]}
    else:
        geometry = {"type": "MultiPolygon", "coordinates": polygons}
    return geometry, report


class _Resolver:
    def __init__(self, parsed: ParsedOSM) -> None:
        self.parsed = parsed
        self.missing: list[dict[str, Any]] = []
        self.geometry_unavailable: list[dict[str, Any]] = []
        self._missing_keys: set[tuple[str, int, str, int]] = set()
        self._relation_points: dict[int, tuple[dict[str, float], ...]] = {}

    def _record_missing(
        self,
        owner_type: str,
        owner_id: int,
        member_type: str,
        member_id: int,
    ) -> None:
        key = (owner_type, owner_id, member_type, member_id)
        if key in self._missing_keys:
            return
        self._missing_keys.add(key)
        self.missing.append(
            {
                "owner_type": owner_type,
                "owner_id": owner_id,
                "member_type": member_type,
                "member_id": member_id,
            }
        )

    def way_points(
        self, way: WayRecord, *, owner_type: str = "way", owner_id: int | None = None
    ) -> list[dict[str, float]]:
        points: list[dict[str, float]] = []
        resolved_owner_id = way.element_id if owner_id is None else owner_id
        for node_id in way.node_refs:
            node = self.parsed.nodes.get(node_id)
            if node is None:
                self._record_missing(owner_type, resolved_owner_id, "node", node_id)
                continue
            point = _point(node)
            if point is None:
                self._record_missing(owner_type, resolved_owner_id, "node", node_id)
                continue
            points.append(point)
        return points

    def relation_points(
        self, relation: RelationRecord, stack: tuple[int, ...] = ()
    ) -> list[dict[str, float]]:
        cached = self._relation_points.get(relation.element_id)
        if cached is not None:
            return [dict(point) for point in cached]
        if relation.element_id in stack:
            self.geometry_unavailable.append(
                {
                    "type": "relation",
                    "id": relation.element_id,
                    "reason": "cyclic_relation_membership",
                }
            )
            return []
        points: list[dict[str, float]] = []
        next_stack = (*stack, relation.element_id)
        for member in relation.members:
            if member.member_type == "node":
                node = self.parsed.nodes.get(member.ref)
                point = _point(node) if node is not None else None
                if point is None:
                    self._record_missing("relation", relation.element_id, "node", member.ref)
                else:
                    points.append(point)
            elif member.member_type == "way":
                way = self.parsed.ways.get(member.ref)
                if way is None:
                    self._record_missing("relation", relation.element_id, "way", member.ref)
                else:
                    points.extend(
                        self.way_points(
                            way, owner_type="relation", owner_id=relation.element_id
                        )
                    )
            else:
                nested = self.parsed.relations.get(member.ref)
                if nested is None:
                    self._record_missing("relation", relation.element_id, "relation", member.ref)
                else:
                    points.extend(self.relation_points(nested, next_stack))
        self._relation_points[relation.element_id] = tuple(dict(point) for point in points)
        return points

    def relation_members(self, relation: RelationRecord) -> list[dict[str, Any]]:
        members: list[dict[str, Any]] = []
        for member in relation.members:
            output: dict[str, Any] = {
                "type": member.member_type,
                "ref": member.ref,
                "role": member.role,
            }
            if member.member_type == "node":
                node = self.parsed.nodes.get(member.ref)
                point = _point(node) if node is not None else None
                if point is None:
                    self._record_missing("relation", relation.element_id, "node", member.ref)
                else:
                    output.update(point)
            elif member.member_type == "way":
                way = self.parsed.ways.get(member.ref)
                if way is None:
                    self._record_missing("relation", relation.element_id, "way", member.ref)
                else:
                    geometry = self.way_points(
                        way, owner_type="relation", owner_id=relation.element_id
                    )
                    if geometry:
                        output["geometry"] = geometry
                        output["bounds"] = _bounds(geometry)
                    else:
                        output["geometry_status"] = "unavailable_no_coordinates"
            else:
                nested = self.parsed.relations.get(member.ref)
                if nested is None:
                    self._record_missing("relation", relation.element_id, "relation", member.ref)
                else:
                    nested_points = self.relation_points(nested, (relation.element_id,))
                    nested_bounds = _bounds(nested_points)
                    if nested_bounds is not None:
                        output["bounds"] = nested_bounds
                    else:
                        output["geometry_status"] = "unavailable_no_coordinates"
            members.append(output)
        return members


def _base_element(
    object_type: str,
    element_id: int,
    attributes: Mapping[str, Any],
    tags: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "type": object_type,
        "id": element_id,
        **attributes,
        "tags": dict(tags),
    }


def build_overpass_document(parsed: ParsedOSM) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve every exact match once and return the document plus integrity facts."""
    resolver = _Resolver(parsed)
    elements: list[dict[str, Any]] = []
    matched: Counter[str] = Counter()
    assembly_reports: list[dict[str, Any]] = []

    for node_id in sorted(parsed.nodes):
        node = parsed.nodes[node_id]
        if not is_exact_match(node.tags):
            continue
        matched["node"] += 1
        output = _base_element("node", node_id, node.attributes, node.tags)
        point = _point(node)
        if point is None:
            resolver._record_missing("node", node_id, "coordinate", node_id)
        else:
            output.update(point)
        elements.append(output)

    for way_id in sorted(parsed.ways):
        way = parsed.ways[way_id]
        if not is_exact_match(way.tags):
            continue
        matched["way"] += 1
        output = _base_element("way", way_id, way.attributes, way.tags)
        output["nodes"] = list(way.node_refs)
        geometry = resolver.way_points(way)
        if geometry:
            bounds = _bounds(geometry)
            if bounds is None:
                raise PlanetMaterializationError(
                    f"way/{way_id} geometry unexpectedly has no bounds"
                )
            output["geometry"] = geometry
            output["bounds"] = bounds
            output["center"] = _center(bounds)
        else:
            output["geometry_status"] = "unavailable_no_coordinates"
            resolver.geometry_unavailable.append(
                {"type": "way", "id": way_id, "reason": "no_coordinate_geometry"}
            )
        elements.append(output)

    for relation_id in sorted(parsed.relations):
        relation = parsed.relations[relation_id]
        if not is_exact_match(relation.tags):
            continue
        matched["relation"] += 1
        output = _base_element(
            "relation", relation_id, relation.attributes, relation.tags
        )
        output["members"] = resolver.relation_members(relation)
        assembled_geometry, assembly_report = _relation_polygon_geometry(
            relation, parsed, resolver
        )
        if assembly_report is not None:
            output["geometry_assembly"] = assembly_report
            assembly_reports.append(
                {"relation_id": relation_id, **assembly_report}
            )
        if assembled_geometry is not None:
            output["geometry"] = assembled_geometry
            output["geometry_source"] = "stitched_relation_member_ways"
        points = resolver.relation_points(relation)
        bounds = _bounds(points)
        if bounds is not None:
            output["bounds"] = bounds
            output["center"] = _center(bounds)
        else:
            output["geometry_status"] = "unavailable_no_coordinate_members"
            resolver.geometry_unavailable.append(
                {
                    "type": "relation",
                    "id": relation_id,
                    "reason": "no_coordinate_members",
                }
            )
        elements.append(output)

    if resolver.missing:
        raise MissingReferenceError(
            sorted(
                resolver.missing,
                key=lambda item: (
                    TYPE_ORDER.get(str(item["owner_type"]), -1),
                    int(item["owner_id"]),
                    TYPE_ORDER.get(str(item["member_type"]), -1),
                    int(item["member_id"]),
                ),
            )
        )

    elements.sort(key=lambda item: (TYPE_ORDER[item["type"]], item["id"]))
    identities = [(element["type"], element["id"]) for element in elements]
    if len(identities) != len(set(identities)):
        raise PlanetMaterializationError("materialized output contains duplicate OSM identities")
    expected_count = sum(matched.values())
    if len(elements) != expected_count:
        raise PlanetMaterializationError(
            "not every exact OSM tag match was emitted exactly once"
        )

    source_counts = {
        object_type: parsed.source_counts.get(object_type, 0)
        for object_type in TYPE_ORDER
    }
    matched_counts = {object_type: matched[object_type] for object_type in TYPE_ORDER}
    emitted_by_type = Counter(element["type"] for element in elements)
    unavailable = {
        (str(item["type"]), int(item["id"]), str(item["reason"]))
        for item in resolver.geometry_unavailable
    }
    geometry_unavailable = [
        {"type": object_type, "id": element_id, "reason": reason}
        for object_type, element_id, reason in sorted(
            unavailable,
            key=lambda item: (TYPE_ORDER.get(item[0], -1), item[1], item[2]),
        )
    ]
    integrity = {
        "source_object_counts": source_counts,
        "exact_match_counts": {
            **matched_counts,
            "total": expected_count,
        },
        "emitted_counts": {
            **{object_type: emitted_by_type[object_type] for object_type in TYPE_ORDER},
            "total": len(elements),
        },
        "reference_objects_excluded_from_elements": sum(source_counts.values())
        - expected_count,
        "missing_references": [],
        "missing_reference_count": 0,
        "geometry_unavailable": geometry_unavailable,
        "geometry_unavailable_count": len(geometry_unavailable),
        "relation_geometry_assembly": assembly_reports,
        "relation_geometry_assembled_count": sum(
            report["status"] == "assembled" for report in assembly_reports
        ),
        "relation_geometry_unresolved_count": sum(
            report["status"] == "unresolved" for report in assembly_reports
        ),
        "all_exact_matches_emitted_once": True,
        "referential_integrity": True,
    }
    document = {
        "version": 0.6,
        "generator": "DataCenterAtlas OSM planet materializer",
        "copyright": "OpenStreetMap and contributors",
        "attribution": OSM_ATTRIBUTION,
        "license": OSM_LICENSE,
        "elements": elements,
        "materialization": {
            "schema_version": SCHEMA_VERSION,
            "selection": "exact_tag_pairs_only",
            "tag_filter_sha256": TAG_FILTER_SHA256,
            "tag_pair_count": len(EXACT_TAG_PAIRS),
            "integrity": integrity,
        },
    }
    return document, integrity


def _run(
    runner: Callable[..., Any],
    command: Sequence[str],
) -> Any:
    try:
        result = runner(
            list(command),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        stderr = getattr(error, "stderr", None)
        detail = f": {str(stderr).strip()}" if stderr else ""
        raise PlanetMaterializationError(
            f"command failed: {' '.join(command)}{detail}"
        ) from error
    return_code = getattr(result, "returncode", 0)
    if return_code != 0:
        stderr = getattr(result, "stderr", None)
        detail = f": {str(stderr).strip()}" if stderr else ""
        raise PlanetMaterializationError(
            f"command failed with exit code {return_code}: {' '.join(command)}{detail}"
        )
    return result


def osmium_version(
    *,
    osmium_binary: str = "osmium",
    runner: Callable[..., Any] = subprocess.run,
) -> str:
    result = _run(runner, [osmium_binary, "--version"])
    stdout = getattr(result, "stdout", "")
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", errors="replace")
    first_line = str(stdout).splitlines()[0].strip() if str(stdout).splitlines() else ""
    if not first_line:
        raise PlanetMaterializationError("osmium --version returned no version text")
    return first_line


def convert_pbf_to_xml(
    pbf_path: str | Path,
    xml_path: str | Path,
    *,
    osmium_binary: str = "osmium",
    runner: Callable[..., Any] = subprocess.run,
) -> list[str]:
    """Convert a PBF to OSM XML and expose the final file only on success."""
    source = _absolute(pbf_path)
    destination = Path(xml_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise PlanetMaterializationError(
            f"refusing to overwrite existing OSM XML output: {destination}"
        )
    temporary = destination.with_name(f".{destination.name}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PlanetMaterializationError(
            f"refusing to overwrite stale XML conversion temporary: {temporary}"
        )
    command = [
        osmium_binary,
        "cat",
        "--no-progress",
        str(source),
        "--output",
        str(temporary),
        "--output-format",
        "osm",
        "--fsync",
    ]
    try:
        _run(runner, command)
        if not temporary.is_file() or temporary.is_symlink():
            raise PlanetMaterializationError("osmium cat did not create its OSM XML output")
        if temporary.stat().st_size == 0:
            raise PlanetMaterializationError("osmium cat created an empty OSM XML output")
        temporary.replace(destination)
    finally:
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()
    return command


def _relative_command(command: Sequence[str], stage: Path) -> list[str]:
    stage_text = str(stage)
    return [str(item).replace(stage_text + os.sep, "") for item in command]


def _upstream_snapshot(document: Mapping[str, Any]) -> Any:
    for key in ("snapshot_date", "source_snapshot_date"):
        if document.get(key) is not None:
            return document[key]
    source = document.get("source")
    if isinstance(source, Mapping):
        return source.get("snapshot_date") or source.get("date")
    return None


def _lineage_manifest(
    extraction: ExtractionInput,
    *,
    lineage_base: Path,
    xml_record: Mapping[str, Any],
    json_record: Mapping[str, Any],
    integrity: Mapping[str, Any],
    command: Sequence[str],
    tool_version: str,
    materialized_at: str,
) -> dict[str, Any]:
    source = extraction.document.get("source")
    inputs: dict[str, Any] = {
        "extraction_manifest": {
            "path": os.path.relpath(extraction.manifest_path, lineage_base),
            "bytes": extraction.manifest_bytes,
            "sha256": extraction.manifest_sha256,
            "pipeline": extraction.document.get("pipeline"),
            "schema_version": extraction.document.get("schema_version"),
        },
        "filtered_pbf": {
            "path": os.path.relpath(extraction.pbf_path, lineage_base),
            "bytes": extraction.pbf_bytes,
            "md5": extraction.pbf_md5,
            "sha256": extraction.pbf_sha256,
        },
    }
    if isinstance(source, Mapping):
        inputs["planet_source"] = dict(source)
    return {
        "schema_version": SCHEMA_VERSION,
        "pipeline": PIPELINE,
        "state": "completed",
        "materialized_at": materialized_at,
        "source_retrieved_at": extraction.source_retrieved_at,
        "snapshot_date": _upstream_snapshot(extraction.document),
        "inputs": inputs,
        "transform": {
            "bridge": "filtered_pbf_to_osm_xml_to_overpass_json",
            "why_xml": "preserves explicitly tagged non-area relations",
            "command": list(command),
            "tool_version": tool_version,
            "tag_filter": DATA_CENTER_FILTER,
            "tag_filter_sha256": TAG_FILTER_SHA256,
            "tag_pairs": [
                {"key": key, "value": value} for key, value in EXACT_TAG_PAIRS
            ],
            "tag_pair_count": len(EXACT_TAG_PAIRS),
            "selection": "exact_tag_pairs_only",
            "references_required": True,
            "status_or_capacity_inference": False,
        },
        "outputs": {
            "osm_xml": dict(xml_record),
            "overpass_json": dict(json_record),
        },
        "counts": dict(integrity),
        "rights": {
            "license": OSM_LICENSE,
            "attribution": OSM_ATTRIBUTION,
            "copyright_url": OSM_COPYRIGHT_URL,
            "database_rights_apply_to_derived_output": True,
        },
    }


def _validate_existing_bundle(
    output_directory: Path,
    extraction: ExtractionInput,
) -> dict[str, Any]:
    manifest_path = output_directory / DEFAULT_MANIFEST_FILENAME
    manifest, _ = _load_json_object(manifest_path, "materialization manifest")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise PlanetMaterializationError("existing materialization schema does not match")
    if manifest.get("pipeline") != PIPELINE or manifest.get("state") != "completed":
        raise PlanetMaterializationError("existing materialization is not completed")
    if manifest.get("source_retrieved_at") != extraction.source_retrieved_at:
        raise PlanetMaterializationError(
            "existing materialization source retrieval time does not match"
        )
    inputs = manifest.get("inputs")
    if not isinstance(inputs, Mapping):
        raise PlanetMaterializationError("existing materialization has no input lineage")
    extraction_record = inputs.get("extraction_manifest")
    pbf_record = inputs.get("filtered_pbf")
    if not isinstance(extraction_record, Mapping) or not isinstance(pbf_record, Mapping):
        raise PlanetMaterializationError("existing materialization input lineage is malformed")
    if extraction_record.get("sha256") != extraction.manifest_sha256:
        raise PlanetMaterializationError(
            "existing materialization used a different extraction manifest"
        )
    if pbf_record.get("sha256") != extraction.pbf_sha256:
        raise PlanetMaterializationError(
            "existing materialization used a different filtered PBF"
        )
    transform = manifest.get("transform")
    if (
        not isinstance(transform, Mapping)
        or transform.get("tag_filter_sha256") != TAG_FILTER_SHA256
    ):
        raise PlanetMaterializationError("existing materialization used a different tag filter")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, Mapping):
        raise PlanetMaterializationError("existing materialization output records are malformed")
    for key, expected_name in (
        ("osm_xml", DEFAULT_XML_FILENAME),
        ("overpass_json", DEFAULT_JSON_FILENAME),
    ):
        record = outputs.get(key)
        if not isinstance(record, Mapping) or record.get("path") != expected_name:
            raise PlanetMaterializationError(
                f"existing materialization has an invalid {key} output record"
            )
        actual = inspect_file(output_directory / expected_name, ("md5", "sha256"))
        if any(actual.get(field) != record.get(field) for field in ("bytes", "md5", "sha256")):
            raise PlanetMaterializationError(
                f"existing materialization {key} hash or byte count does not match"
            )
    overpass, _ = _load_json_object(
        output_directory / DEFAULT_JSON_FILENAME, "materialized Overpass JSON"
    )
    elements = overpass.get("elements")
    if not isinstance(elements, list):
        raise PlanetMaterializationError("materialized Overpass JSON has no elements list")
    if overpass.get("license") != OSM_LICENSE or overpass.get("attribution") != OSM_ATTRIBUTION:
        raise PlanetMaterializationError(
            "materialized Overpass JSON has invalid ODbL attribution"
        )
    output_metadata = overpass.get("materialization")
    if (
        not isinstance(output_metadata, Mapping)
        or output_metadata.get("schema_version") != SCHEMA_VERSION
        or output_metadata.get("tag_filter_sha256") != TAG_FILTER_SHA256
        or output_metadata.get("tag_pair_count") != len(EXACT_TAG_PAIRS)
    ):
        raise PlanetMaterializationError(
            "materialized Overpass JSON has invalid selection metadata"
        )
    identities: set[tuple[str, int]] = set()
    observed_counts: Counter[str] = Counter()
    for element in elements:
        if not isinstance(element, Mapping):
            raise PlanetMaterializationError(
                "materialized Overpass JSON contains a non-object element"
            )
        object_type = element.get("type")
        element_id = element.get("id")
        tags = element.get("tags")
        if (
            object_type not in TYPE_ORDER
            or isinstance(element_id, bool)
            or not isinstance(element_id, int)
            or element_id <= 0
            or not isinstance(tags, Mapping)
            or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in tags.items()
            )
            or not is_exact_match(tags)
        ):
            raise PlanetMaterializationError(
                "materialized Overpass JSON contains an invalid exact-match element"
            )
        identity = (str(object_type), element_id)
        if identity in identities:
            raise PlanetMaterializationError(
                "materialized Overpass JSON contains duplicate OSM identities"
            )
        identities.add(identity)
        observed_counts[str(object_type)] += 1
    counts = manifest.get("counts")
    if not isinstance(counts, Mapping):
        raise PlanetMaterializationError("existing materialization has no integrity counts")
    exact_counts = counts.get("exact_match_counts")
    if not isinstance(exact_counts, Mapping) or exact_counts.get("total") != len(elements):
        raise PlanetMaterializationError("existing materialization element count does not match")
    for object_type in TYPE_ORDER:
        if exact_counts.get(object_type) != observed_counts[object_type]:
            raise PlanetMaterializationError(
                "existing materialization per-type element counts do not match"
            )
    if (
        counts.get("missing_reference_count") != 0
        or counts.get("referential_integrity") is not True
        or counts.get("all_exact_matches_emitted_once") is not True
    ):
        raise PlanetMaterializationError(
            "existing materialization does not attest complete referential integrity"
        )
    return manifest


def materialize_planet_extract(
    extraction_manifest: str | Path,
    output_directory: str | Path,
    *,
    filtered_pbf: str | Path | None = None,
    osmium_binary: str = "osmium",
    runner: Callable[..., Any] = subprocess.run,
    dry_run: bool = False,
    clock: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    """Build an atomic, lineage-bound XML/Overpass materialization bundle."""
    extraction = validate_extraction_input(
        extraction_manifest, filtered_pbf=filtered_pbf
    )
    destination = _absolute(output_directory)
    if destination.is_symlink():
        raise PlanetMaterializationError(f"refusing symlink output directory: {destination}")
    if destination.exists():
        if not destination.is_dir():
            raise PlanetMaterializationError("materialization output exists and is not a directory")
        return _validate_existing_bundle(destination, extraction)

    planned_command = [
        osmium_binary,
        "cat",
        "--no-progress",
        str(extraction.pbf_path),
        "--output",
        DEFAULT_XML_FILENAME,
        "--output-format",
        "osm",
        "--fsync",
    ]
    if dry_run:
        return {
            "schema_version": SCHEMA_VERSION,
            "pipeline": PIPELINE,
            "state": "dry_run",
            "inputs": {
                "extraction_manifest_sha256": extraction.manifest_sha256,
                "filtered_pbf_md5": extraction.pbf_md5,
                "filtered_pbf_sha256": extraction.pbf_sha256,
                "filtered_pbf_bytes": extraction.pbf_bytes,
            },
            "planned_command": planned_command,
            "output_directory": str(destination),
            "writes_performed": False,
        }

    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent)
    )
    try:
        tool_version = osmium_version(osmium_binary=osmium_binary, runner=runner)
        xml_path = stage / DEFAULT_XML_FILENAME
        actual_command = convert_pbf_to_xml(
            extraction.pbf_path,
            xml_path,
            osmium_binary=osmium_binary,
            runner=runner,
        )
        parsed = parse_osm_xml(xml_path)
        parsed_counts = {
            object_type: parsed.source_counts.get(object_type, 0)
            for object_type in TYPE_ORDER
        }
        if parsed_counts != extraction.source_object_counts:
            raise PlanetMaterializationError(
                "OSM XML object counts do not match the extraction manifest: "
                f"parsed {parsed_counts}, expected {extraction.source_object_counts}"
            )
        overpass, integrity = build_overpass_document(parsed)
        overpass_raw = canonical_json_bytes(overpass)
        overpass_path = stage / DEFAULT_JSON_FILENAME
        _write_bytes_atomic(overpass_path, overpass_raw)

        xml_record = {
            "path": DEFAULT_XML_FILENAME,
            **inspect_file(xml_path, ("md5", "sha256")),
        }
        json_record = {
            "path": DEFAULT_JSON_FILENAME,
            "bytes": len(overpass_raw),
            "md5": hashlib.md5(overpass_raw).hexdigest(),
            "sha256": sha256_bytes(overpass_raw),
            "element_count": integrity["exact_match_counts"]["total"],
            "element_counts_by_type": {
                key: integrity["exact_match_counts"][key] for key in TYPE_ORDER
            },
        }
        manifest = _lineage_manifest(
            extraction,
            lineage_base=destination,
            xml_record=xml_record,
            json_record=json_record,
            integrity=integrity,
            command=_relative_command(actual_command, stage),
            tool_version=tool_version,
            materialized_at=clock(),
        )
        _write_bytes_atomic(
            stage / DEFAULT_MANIFEST_FILENAME, pretty_json_bytes(manifest)
        )
        if destination.exists():
            raise PlanetMaterializationError(
                "materialization output appeared while the atomic bundle was being built"
            )
        stage.replace(destination)
        return manifest
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PlanetMaterializationError(f"refusing stale output temporary: {temporary}")
    try:
        with temporary.open("xb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()


__all__ = [
    "DEFAULT_JSON_FILENAME",
    "DEFAULT_MANIFEST_FILENAME",
    "DEFAULT_XML_FILENAME",
    "EXACT_TAG_PAIRS",
    "MissingReferenceError",
    "PlanetMaterializationError",
    "build_overpass_document",
    "canonical_json_bytes",
    "convert_pbf_to_xml",
    "is_exact_match",
    "materialize_planet_extract",
    "parse_osm_xml",
    "validate_extraction_input",
]
