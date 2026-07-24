"""Review-only OpenStreetMap discovery for data-centre spelling variants.

This layer deliberately has a wider recall surface than the canonical 92-pair
OSM filter.  It retains every broad match for review, marks canonical matches
as duplicates, and imports only low-confidence, source-scoped leads.  Textual
matches never become confirmed facilities or construction claims.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
from typing import Any, Callable, Iterable, Mapping, Sequence

from .adapters import ImportResult
from .models import Evidence, EvidenceKind, Facility, LifecycleObservation, LifecycleStatus
from .osm import extract_center, extract_geometry
from .osm_planet import (
    ExtractionInput,
    MissingReferenceError,
    OSM_ATTRIBUTION,
    OSM_COPYRIGHT_URL,
    OSM_LICENSE,
    PlanetMaterializationError,
    TYPE_ORDER,
    _Resolver,
    _absolute,
    _base_element,
    _bounds,
    _center,
    _extract_pbf_record,
    _is_md5,
    _is_sha256,
    _load_json_object,
    _point,
    _relation_polygon_geometry,
    _safe_manifest_path,
    _validate_extraction_lineage,
    _write_bytes_atomic,
    canonical_json_bytes,
    convert_pbf_to_xml,
    inspect_file,
    is_exact_match,
    osmium_version,
    parse_osm_xml,
    pretty_json_bytes,
    sha256_bytes,
    utc_now,
)
from .repository import add_evidence, add_facility, add_lifecycle, add_snapshot, stable_id


SCHEMA_VERSION = 1
EXTRACTION_PIPELINE = "openstreetmap_planet_fuzzy_discovery_extraction"
MATERIALIZATION_PIPELINE = "openstreetmap_planet_fuzzy_discovery_materialize"
SOURCE_FAMILY = "openstreetmap:fuzzy_discovery"
UPSTREAM_SOURCE_ROOT = "openstreetmap"
FILTER_VERSION = "osm-fuzzy-review-v1"
CLASSIFIER_VERSION = "osm-fuzzy-classifier-v1"
DEFAULT_XML_FILENAME = "fuzzy-filtered.osm"
DEFAULT_JSON_FILENAME = "fuzzy-review.json"
DEFAULT_MANIFEST_FILENAME = "manifest.json"

# These are deliberately case-sensitive.  All-uppercase spellings are not
# included because no observed evidence currently justifies that extra noise.
VARIANTS = (
    "data_center",
    "data_centre",
    "datacenter",
    "datacentre",
    "data center",
    "data centre",
    "Data Center",
    "Data Centre",
)


def osmium_filter_expressions() -> tuple[str, ...]:
    """Return the versioned any-key/any-value Osmium 1.19 filter surface."""
    expressions: list[str] = []
    for variant in VARIANTS:
        expressions.extend((f"nwr/*{variant}*", f"nwr/*=*{variant}*"))
    return tuple(expressions)


def filter_manifest_document() -> dict[str, Any]:
    expressions = osmium_filter_expressions()
    contract = {
        "version": FILTER_VERSION,
        "variants": list(VARIANTS),
        "osmium_expressions": list(expressions),
        "wildcard_semantics": {
            "key": "case-sensitive substring under any OSM tag key",
            "value": "case-sensitive substring under any OSM tag value",
            "osmium_minimum_version": "1.19",
        },
        "object_types": ["node", "way", "relation"],
        "match_scope": "review_only_candidate_recall_expansion",
        "referenced_nodes_and_members_retained": True,
        "omit_referenced_flag_used": False,
        "output_object_counts_include_references": True,
        "converted_to_geojson": False,
        "all_uppercase_variants_included": False,
    }
    contract["contract_sha256"] = hashlib.sha256(
        canonical_json_bytes(contract)
    ).hexdigest()
    return contract


FILTER_SHA256 = filter_manifest_document()["contract_sha256"]


STRUCTURAL_KEYS = frozenset(
    {
        "amenity",
        "building",
        "building:use",
        "construction",
        "construction:building",
        "industrial",
        "landuse",
        "man_made",
        "proposed",
        "proposed:building",
        "site",
        "telecom",
        "disused:telecom",
        "abandoned:telecom",
        "disused:building",
        "abandoned:building",
    }
)
TEXTUAL_KEYS = frozenset(
    {
        "name",
        "official_name",
        "short_name",
        "alt_name",
        "old_name",
        "description",
        "note",
        "operator",
        "brand",
        "website",
        "url",
        "source",
        "ref",
        "wikipedia",
        "wikidata",
    }
)
NORMALIZED_VALUES = frozenset({"data_center", "data_centre", "datacenter", "datacentre"})
CLASSIFICATIONS = frozenset(
    {
        "exact_92_pair",
        "explicit_marker_variant",
        "unknown_key_explicit_value",
        "textual_only",
        "ambiguous",
    }
)


@dataclass(frozen=True, slots=True)
class FuzzyClassification:
    classification: str
    trigger_tags: tuple[dict[str, Any], ...]
    supplemental_eligible: bool
    lifecycle_hint: str
    reason: str

    def document(self) -> dict[str, Any]:
        return {
            "classifier_version": CLASSIFIER_VERSION,
            "classification": self.classification,
            "supplemental_eligible": self.supplemental_eligible,
            "lifecycle_hint": self.lifecycle_hint,
            "reason": self.reason,
            "trigger_tags": [dict(item) for item in self.trigger_tags],
            "review_only": True,
        }


def _normalized_token(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _explicit_tokens(value: str) -> tuple[str, ...]:
    return tuple(
        token
        for part in value.split(";")
        if (token := _normalized_token(part)) in NORMALIZED_VALUES
    )


def _structural_key(key: str) -> bool:
    return key in STRUCTURAL_KEYS or key.startswith(("construction:", "proposed:"))


def _textual_key(key: str) -> bool:
    return key in TEXTUAL_KEYS or any(
        key.startswith(f"{prefix}:")
        for prefix in ("name", "description", "note", "operator", "brand", "contact")
    )


def trigger_tags(tags: Mapping[str, str]) -> tuple[dict[str, Any], ...]:
    triggers: list[dict[str, Any]] = []
    for key, value in sorted(tags.items()):
        key_variants = [variant for variant in VARIANTS if variant in key]
        value_variants = [variant for variant in VARIANTS if variant in value]
        if not key_variants and not value_variants:
            continue
        sources = []
        if key_variants:
            sources.append("key")
        if value_variants:
            sources.append("value")
        triggers.append(
            {
                "key": key,
                "value": value,
                "trigger_sources": sources,
                "key_variants": key_variants,
                "value_variants": value_variants,
                "explicit_value_tokens": list(_explicit_tokens(value)),
            }
        )
    return tuple(triggers)


def classify_tags(tags: Mapping[str, str]) -> FuzzyClassification | None:
    """Classify a broad match without promoting text into a facility assertion."""
    triggers = trigger_tags(tags)
    if not triggers:
        return None
    if is_exact_match(tags):
        return FuzzyClassification(
            "exact_92_pair",
            triggers,
            False,
            "excluded_exact_layer_duplicate",
            "matches the canonical 92-pair OSM layer",
        )

    explicit_structural = [
        item
        for item in triggers
        if _structural_key(str(item["key"])) and item["explicit_value_tokens"]
    ]
    if explicit_structural:
        lifecycle_hint = "lead"
        keys = {str(item["key"]) for item in explicit_structural}
        if any(key == "construction" or key.startswith("construction:") for key in keys):
            lifecycle_hint = "under_construction"
        elif any(key == "proposed" or key.startswith("proposed:") for key in keys):
            lifecycle_hint = "proposed"
        return FuzzyClassification(
            "explicit_marker_variant",
            triggers,
            True,
            lifecycle_hint,
            "recognized structural or lifecycle key with an exact normalized/list value",
        )

    nontext_explicit = [
        item
        for item in triggers
        if not _textual_key(str(item["key"]))
        and not _structural_key(str(item["key"]))
        and item["explicit_value_tokens"]
    ]
    if nontext_explicit:
        return FuzzyClassification(
            "unknown_key_explicit_value",
            triggers,
            True,
            "lead",
            "unknown key with an exact normalized/list data-centre value",
        )

    if all(_textual_key(str(item["key"])) for item in triggers):
        return FuzzyClassification(
            "textual_only",
            triggers,
            True,
            "lead",
            "match occurs only in free-text identity or description tags",
        )

    return FuzzyClassification(
        "ambiguous",
        triggers,
        True,
        "lead",
        "substring match is not an exact value on a recognized structural key",
    )


def _decorate(element: dict[str, Any], classification: FuzzyClassification) -> None:
    element["fuzzy_discovery"] = {
        **classification.document(),
        "canonical_osm_url": (
            f"https://www.openstreetmap.org/{element['type']}/{element['id']}"
        ),
    }


def build_fuzzy_overpass_document(parsed: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve broad matches while retaining exact-layer duplicates as flags."""
    resolver = _Resolver(parsed)
    elements: list[dict[str, Any]] = []
    matched: Counter[str] = Counter()
    classified: Counter[str] = Counter()
    assembly_reports: list[dict[str, Any]] = []

    for node_id in sorted(parsed.nodes):
        node = parsed.nodes[node_id]
        classification = classify_tags(node.tags)
        if classification is None:
            continue
        matched["node"] += 1
        classified[classification.classification] += 1
        output = _base_element("node", node_id, node.attributes, node.tags)
        point = _point(node)
        if point is None:
            resolver._record_missing("node", node_id, "coordinate", node_id)
        else:
            output.update(point)
        _decorate(output, classification)
        elements.append(output)

    for way_id in sorted(parsed.ways):
        way = parsed.ways[way_id]
        classification = classify_tags(way.tags)
        if classification is None:
            continue
        matched["way"] += 1
        classified[classification.classification] += 1
        output = _base_element("way", way_id, way.attributes, way.tags)
        output["nodes"] = list(way.node_refs)
        geometry = resolver.way_points(way)
        if geometry:
            bounds = _bounds(geometry)
            if bounds is None:
                raise PlanetMaterializationError(f"way/{way_id} has no geometry bounds")
            output["geometry"] = geometry
            output["bounds"] = bounds
            output["center"] = _center(bounds)
        else:
            output["geometry_status"] = "unavailable_no_coordinates"
            resolver.geometry_unavailable.append(
                {"type": "way", "id": way_id, "reason": "no_coordinate_geometry"}
            )
        _decorate(output, classification)
        elements.append(output)

    for relation_id in sorted(parsed.relations):
        relation = parsed.relations[relation_id]
        classification = classify_tags(relation.tags)
        if classification is None:
            continue
        matched["relation"] += 1
        classified[classification.classification] += 1
        output = _base_element("relation", relation_id, relation.attributes, relation.tags)
        output["members"] = resolver.relation_members(relation)
        assembled, report = _relation_polygon_geometry(relation, parsed, resolver)
        if report is not None:
            output["geometry_assembly"] = report
            assembly_reports.append({"relation_id": relation_id, **report})
        if assembled is not None:
            output["geometry"] = assembled
            output["geometry_source"] = "stitched_relation_member_ways"
        points = resolver.relation_points(relation)
        bounds = _bounds(points)
        if bounds is not None:
            output["bounds"] = bounds
            output["center"] = _center(bounds)
        else:
            output["geometry_status"] = "unavailable_no_coordinate_members"
            resolver.geometry_unavailable.append(
                {"type": "relation", "id": relation_id, "reason": "no_coordinate_members"}
            )
        _decorate(output, classification)
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
    identities = [(item["type"], item["id"]) for item in elements]
    if len(identities) != len(set(identities)):
        raise PlanetMaterializationError("fuzzy output contains duplicate OSM identities")
    total = sum(matched.values())
    if len(elements) != total:
        raise PlanetMaterializationError("not every fuzzy OSM match was emitted exactly once")

    source_counts = {
        object_type: parsed.source_counts.get(object_type, 0) for object_type in TYPE_ORDER
    }
    unavailable = {
        (str(item["type"]), int(item["id"]), str(item["reason"]))
        for item in resolver.geometry_unavailable
    }
    geometry_unavailable = [
        {"type": kind, "id": element_id, "reason": reason}
        for kind, element_id, reason in sorted(
            unavailable, key=lambda item: (TYPE_ORDER.get(item[0], -1), item[1], item[2])
        )
    ]
    exact_count = classified["exact_92_pair"]
    integrity = {
        "source_object_counts": source_counts,
        "broad_match_counts": {
            **{object_type: matched[object_type] for object_type in TYPE_ORDER},
            "total": total,
        },
        "classification_counts": {
            name: classified[name] for name in sorted(CLASSIFICATIONS)
        },
        "supplemental_eligible_count": total - exact_count,
        "exact_layer_duplicate_count": exact_count,
        "reference_objects_excluded_from_elements": sum(source_counts.values()) - total,
        "missing_references": [],
        "missing_reference_count": 0,
        "geometry_unavailable": geometry_unavailable,
        "geometry_unavailable_count": len(geometry_unavailable),
        "relation_geometry_assembly": assembly_reports,
        "all_broad_matches_emitted_once": True,
        "exact_layer_duplicates_excluded_from_supplemental_import": True,
        "referential_integrity": True,
    }
    document = {
        "version": 0.6,
        "generator": "DataCenterAtlas OSM fuzzy discovery materializer",
        "copyright": "OpenStreetMap and contributors",
        "attribution": OSM_ATTRIBUTION,
        "license": OSM_LICENSE,
        "elements": elements,
        "materialization": {
            "schema_version": SCHEMA_VERSION,
            "selection": "fuzzy_review_matches_including_flagged_exact_duplicates",
            "filter_version": FILTER_VERSION,
            "filter_sha256": FILTER_SHA256,
            "classifier_version": CLASSIFIER_VERSION,
            "review_only": True,
            "candidate_recall_expansion_not_census": True,
            "integrity": integrity,
        },
    }
    return document, integrity


def validate_extraction_input(
    extraction_manifest: str | Path,
    *,
    filtered_pbf: str | Path | None = None,
) -> ExtractionInput:
    manifest_path = _absolute(extraction_manifest)
    document, raw = _load_json_object(manifest_path, "OSM fuzzy extraction manifest")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise PlanetMaterializationError("unsupported OSM fuzzy extraction schema")
    if document.get("pipeline") != EXTRACTION_PIPELINE or document.get("state") != "completed":
        raise PlanetMaterializationError("OSM fuzzy extraction manifest is not completed")
    if document.get("review_only") is not True:
        raise PlanetMaterializationError("OSM fuzzy extraction is not marked review-only")
    if document.get("filter") != filter_manifest_document():
        raise PlanetMaterializationError("OSM fuzzy extraction filter contract does not match")
    source_counts = _validate_extraction_lineage(document, manifest_path.parent)
    record = _extract_pbf_record(document)
    record_path = _safe_manifest_path(manifest_path.parent, record.get("path"), "fuzzy PBF")
    pbf_path = _absolute(filtered_pbf) if filtered_pbf is not None else record_path
    if pbf_path != record_path:
        raise PlanetMaterializationError("explicit fuzzy PBF does not match its manifest")
    if not isinstance(record.get("bytes"), int) or record["bytes"] <= 0:
        raise PlanetMaterializationError("fuzzy extraction PBF byte count is invalid")
    if not _is_md5(record.get("md5")) or not _is_sha256(record.get("sha256")):
        raise PlanetMaterializationError("fuzzy extraction PBF hashes are invalid")
    actual = inspect_file(pbf_path, ("md5", "sha256"))
    for field in ("bytes", "md5", "sha256"):
        if actual[field] != record[field]:
            raise PlanetMaterializationError(f"fuzzy extraction PBF {field} does not match")
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
    )


def _validate_review_document(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    if document.get("license") != OSM_LICENSE or document.get("attribution") != OSM_ATTRIBUTION:
        raise ValueError("OSM fuzzy review document has invalid ODbL attribution")
    metadata = document.get("materialization")
    if not isinstance(metadata, Mapping) or any(
        (
            metadata.get("schema_version") != SCHEMA_VERSION,
            metadata.get("filter_version") != FILTER_VERSION,
            metadata.get("filter_sha256") != FILTER_SHA256,
            metadata.get("classifier_version") != CLASSIFIER_VERSION,
            metadata.get("review_only") is not True,
        )
    ):
        raise ValueError("OSM fuzzy review document has invalid materialization metadata")
    elements = document.get("elements")
    if not isinstance(elements, list):
        raise ValueError("OSM fuzzy review document has no elements list")
    identities: set[tuple[str, int]] = set()
    validated: list[dict[str, Any]] = []
    for element in elements:
        if not isinstance(element, dict):
            raise ValueError("OSM fuzzy review contains a non-object element")
        object_type, element_id, tags = element.get("type"), element.get("id"), element.get("tags")
        if (
            object_type not in TYPE_ORDER
            or isinstance(element_id, bool)
            or not isinstance(element_id, int)
            or element_id <= 0
            or not isinstance(tags, dict)
            or not all(isinstance(key, str) and isinstance(value, str) for key, value in tags.items())
        ):
            raise ValueError("OSM fuzzy review contains an invalid OSM element")
        identity = (object_type, element_id)
        if identity in identities:
            raise ValueError("OSM fuzzy review contains duplicate OSM identities")
        identities.add(identity)
        expected = classify_tags(tags)
        discovery = element.get("fuzzy_discovery")
        if expected is None or not isinstance(discovery, dict):
            raise ValueError("OSM fuzzy review contains an unclassified element")
        expected_document = expected.document()
        if any(discovery.get(key) != value for key, value in expected_document.items()):
            raise ValueError("OSM fuzzy review classification does not match source tags")
        expected_url = f"https://www.openstreetmap.org/{object_type}/{element_id}"
        if discovery.get("canonical_osm_url") != expected_url:
            raise ValueError("OSM fuzzy review canonical OSM URL is invalid")
        validated.append(element)
    return validated


def _validate_existing_bundle(directory: Path, extraction: ExtractionInput) -> dict[str, Any]:
    manifest, _ = _load_json_object(directory / DEFAULT_MANIFEST_FILENAME, "fuzzy materialization manifest")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("pipeline") != MATERIALIZATION_PIPELINE
        or manifest.get("state") != "completed"
        or manifest.get("review_only") is not True
    ):
        raise PlanetMaterializationError("existing fuzzy materialization is not completed")
    inputs = manifest.get("inputs")
    if not isinstance(inputs, Mapping):
        raise PlanetMaterializationError("existing fuzzy materialization has no input lineage")
    if inputs.get("extraction_manifest", {}).get("sha256") != extraction.manifest_sha256:
        raise PlanetMaterializationError("existing fuzzy materialization used another manifest")
    if inputs.get("filtered_pbf") != {
        "path": os.path.relpath(extraction.pbf_path, directory),
        "bytes": extraction.pbf_bytes,
        "md5": extraction.pbf_md5,
        "sha256": extraction.pbf_sha256,
    }:
        raise PlanetMaterializationError("existing fuzzy materialization used another PBF")
    transform = manifest.get("transform")
    if not isinstance(transform, Mapping) or any(
        (
            transform.get("filter") != filter_manifest_document(),
            transform.get("classifier_version") != CLASSIFIER_VERSION,
            transform.get("selection") != "broad_matches_with_exact_duplicates_flagged",
            transform.get("references_required") is not True,
            transform.get("textual_match_promotion") is not False,
            transform.get("status_capacity_type_or_workload_inference") is not False,
        )
    ):
        raise PlanetMaterializationError("existing fuzzy transform contract does not match")
    if manifest.get("rights") != {
        "license": OSM_LICENSE,
        "attribution": OSM_ATTRIBUTION,
        "copyright_url": OSM_COPYRIGHT_URL,
        "database_rights_apply_to_derived_output": True,
    }:
        raise PlanetMaterializationError("existing fuzzy materialization rights are invalid")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, Mapping):
        raise PlanetMaterializationError("existing fuzzy output records are malformed")
    for key, name in (("osm_xml", DEFAULT_XML_FILENAME), ("review_json", DEFAULT_JSON_FILENAME)):
        record = outputs.get(key)
        if not isinstance(record, Mapping) or record.get("path") != name:
            raise PlanetMaterializationError(f"existing fuzzy {key} record is invalid")
        actual = inspect_file(directory / name, ("md5", "sha256"))
        if any(actual[field] != record.get(field) for field in ("bytes", "md5", "sha256")):
            raise PlanetMaterializationError(f"existing fuzzy {key} hash does not match")
    document, _ = _load_json_object(directory / DEFAULT_JSON_FILENAME, "fuzzy review JSON")
    try:
        elements = _validate_review_document(document)
    except ValueError as error:
        raise PlanetMaterializationError(str(error)) from error
    counts = manifest.get("counts", {}).get("broad_match_counts", {})
    if counts.get("total") != len(elements):
        raise PlanetMaterializationError("existing fuzzy materialization count does not match")
    if manifest.get("counts") != document.get("materialization", {}).get("integrity"):
        raise PlanetMaterializationError("existing fuzzy manifest and review integrity differ")
    return manifest


def _load_review_artifact(path: Path) -> tuple[bytes, dict[str, Any] | None]:
    if not path.is_dir():
        inspect_file(path, ("sha256",))
        return path.read_bytes(), None
    manifest_path = path / DEFAULT_MANIFEST_FILENAME
    manifest, manifest_raw = _load_json_object(
        manifest_path, "fuzzy materialization manifest"
    )
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("pipeline") != MATERIALIZATION_PIPELINE
        or manifest.get("state") != "completed"
        or manifest.get("review_only") is not True
    ):
        raise ValueError("OSM fuzzy input bundle is not a completed review materialization")
    transform = manifest.get("transform")
    if not isinstance(transform, Mapping) or any(
        (
            transform.get("filter") != filter_manifest_document(),
            transform.get("classifier_version") != CLASSIFIER_VERSION,
            transform.get("references_required") is not True,
            transform.get("textual_match_promotion") is not False,
        )
    ):
        raise ValueError("OSM fuzzy input bundle has an invalid transform contract")
    if manifest.get("rights") != {
        "license": OSM_LICENSE,
        "attribution": OSM_ATTRIBUTION,
        "copyright_url": OSM_COPYRIGHT_URL,
        "database_rights_apply_to_derived_output": True,
    }:
        raise ValueError("OSM fuzzy input bundle has invalid ODbL rights")
    record = manifest.get("outputs", {}).get("review_json")
    if not isinstance(record, Mapping) or record.get("path") != DEFAULT_JSON_FILENAME:
        raise ValueError("OSM fuzzy input bundle has no canonical review JSON record")
    review_path = path / DEFAULT_JSON_FILENAME
    facts = inspect_file(review_path, ("md5", "sha256"))
    if any(facts[field] != record.get(field) for field in ("bytes", "md5", "sha256")):
        raise ValueError("OSM fuzzy input bundle review JSON hash does not match")
    raw = review_path.read_bytes()
    inputs = manifest.get("inputs")
    if not isinstance(inputs, Mapping):
        raise ValueError("OSM fuzzy input bundle has no source lineage")
    extraction = inputs.get("extraction_manifest")
    filtered = inputs.get("filtered_pbf")
    planet = inputs.get("planet_source")
    if (
        not isinstance(extraction, Mapping)
        or not _is_sha256(extraction.get("sha256"))
        or not isinstance(filtered, Mapping)
        or not _is_sha256(filtered.get("sha256"))
        or not _is_md5(filtered.get("md5"))
        or not isinstance(planet, Mapping)
        or not _is_sha256(planet.get("sha256"))
        or not _is_md5(planet.get("md5"))
        or planet.get("url")
        != f"https://planet.openstreetmap.org/pbf/{planet.get('path')}"
    ):
        raise ValueError("OSM fuzzy input bundle source lineage is malformed")
    provenance = {
        "materialization_manifest": {
            "path": DEFAULT_MANIFEST_FILENAME,
            "bytes": len(manifest_raw),
            "sha256": sha256_bytes(manifest_raw),
            "pipeline": MATERIALIZATION_PIPELINE,
        },
        "extraction_manifest": dict(extraction),
        "filtered_pbf": dict(filtered),
        "planet_source": dict(planet),
    }
    return raw, provenance


def materialize_fuzzy_extract(
    extraction_manifest: str | Path,
    output_directory: str | Path,
    *,
    filtered_pbf: str | Path | None = None,
    osmium_binary: str = "osmium",
    runner: Callable[..., Any] = subprocess.run,
    dry_run: bool = False,
    clock: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    extraction = validate_extraction_input(extraction_manifest, filtered_pbf=filtered_pbf)
    destination = _absolute(output_directory)
    if destination.is_symlink():
        raise PlanetMaterializationError(f"refusing symlink output directory: {destination}")
    if destination.exists():
        if not destination.is_dir():
            raise PlanetMaterializationError("fuzzy output exists and is not a directory")
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
            "pipeline": MATERIALIZATION_PIPELINE,
            "state": "dry_run",
            "review_only": True,
            "inputs": {
                "extraction_manifest_sha256": extraction.manifest_sha256,
                "filtered_pbf_sha256": extraction.pbf_sha256,
            },
            "planned_command": planned_command,
            "output_directory": str(destination),
            "writes_performed": False,
        }

    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent))
    try:
        version = osmium_version(osmium_binary=osmium_binary, runner=runner)
        xml_path = stage / DEFAULT_XML_FILENAME
        command = convert_pbf_to_xml(
            extraction.pbf_path, xml_path, osmium_binary=osmium_binary, runner=runner
        )
        parsed = parse_osm_xml(xml_path)
        parsed_counts = {
            object_type: parsed.source_counts.get(object_type, 0) for object_type in TYPE_ORDER
        }
        if parsed_counts != extraction.source_object_counts:
            raise PlanetMaterializationError(
                f"fuzzy XML counts {parsed_counts} do not match {extraction.source_object_counts}"
            )
        review, integrity = build_fuzzy_overpass_document(parsed)
        review["materialization"]["snapshot_date"] = extraction.document.get("snapshot_date")
        review_raw = canonical_json_bytes(review)
        _write_bytes_atomic(stage / DEFAULT_JSON_FILENAME, review_raw)
        xml_record = {"path": DEFAULT_XML_FILENAME, **inspect_file(xml_path, ("md5", "sha256"))}
        json_record = {
            "path": DEFAULT_JSON_FILENAME,
            "bytes": len(review_raw),
            "md5": hashlib.md5(review_raw).hexdigest(),
            "sha256": sha256_bytes(review_raw),
            "element_count": integrity["broad_match_counts"]["total"],
        }
        relative_command = [
            str(item).replace(str(stage) + os.sep, "") for item in command
        ]
        source = extraction.document.get("source")
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "pipeline": MATERIALIZATION_PIPELINE,
            "state": "completed",
            "review_only": True,
            "materialized_at": clock(),
            "snapshot_date": extraction.document.get("snapshot_date"),
            "inputs": {
                "extraction_manifest": {
                    "path": os.path.relpath(extraction.manifest_path, destination),
                    "bytes": extraction.manifest_bytes,
                    "sha256": extraction.manifest_sha256,
                    "pipeline": extraction.document.get("pipeline"),
                },
                "filtered_pbf": {
                    "path": os.path.relpath(extraction.pbf_path, destination),
                    "bytes": extraction.pbf_bytes,
                    "md5": extraction.pbf_md5,
                    "sha256": extraction.pbf_sha256,
                },
                "planet_source": dict(source) if isinstance(source, Mapping) else source,
            },
            "transform": {
                "bridge": "fuzzy_filtered_pbf_to_osm_xml_to_review_json",
                "command": relative_command,
                "tool_version": version,
                "filter": filter_manifest_document(),
                "classifier_version": CLASSIFIER_VERSION,
                "selection": "broad_matches_with_exact_duplicates_flagged",
                "references_required": True,
                "textual_match_promotion": False,
                "status_capacity_type_or_workload_inference": False,
            },
            "outputs": {"osm_xml": xml_record, "review_json": json_record},
            "counts": integrity,
            "rights": {
                "license": OSM_LICENSE,
                "attribution": OSM_ATTRIBUTION,
                "copyright_url": OSM_COPYRIGHT_URL,
                "database_rights_apply_to_derived_output": True,
            },
        }
        _write_bytes_atomic(stage / DEFAULT_MANIFEST_FILENAME, pretty_json_bytes(manifest))
        if destination.exists():
            raise PlanetMaterializationError("fuzzy output appeared during atomic build")
        stage.replace(destination)
        return manifest
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def _lifecycle(classification: Mapping[str, Any]) -> tuple[LifecycleStatus, float, str]:
    if classification.get("classification") == "explicit_marker_variant":
        if classification.get("lifecycle_hint") == "under_construction":
            return (
                LifecycleStatus.UNDER_CONSTRUCTION,
                0.45,
                "osm_fuzzy_exact_normalized_construction_marker",
            )
        if classification.get("lifecycle_hint") == "proposed":
            return LifecycleStatus.PROPOSED, 0.40, "osm_fuzzy_exact_normalized_proposed_marker"
        return LifecycleStatus.LEAD, 0.30, "osm_fuzzy_explicit_variant_lead"
    confidence = {
        "unknown_key_explicit_value": 0.22,
        "ambiguous": 0.15,
        "textual_only": 0.10,
    }.get(str(classification.get("classification")), 0.10)
    return LifecycleStatus.LEAD, confidence, "osm_fuzzy_review_lead_only"


class OpenStreetMapFuzzyDiscoveryAdapter:
    """Import supplemental fuzzy matches as low-confidence facility leads only."""

    source_name = SOURCE_FAMILY

    def import_file(
        self,
        connection: sqlite3.Connection,
        path: str | Path,
        *,
        retrieved_at: str,
    ) -> ImportResult:
        input_path = Path(path)
        raw, bundle_provenance = _load_review_artifact(input_path)
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("OSM fuzzy review input must be a JSON object")
        elements = _validate_review_document(payload)
        input_sha256 = hashlib.sha256(raw).hexdigest()
        imported = skipped = entities_created = evidence_created = 0

        with connection:
            for element in elements:
                discovery = element["fuzzy_discovery"]
                if not discovery["supplemental_eligible"]:
                    skipped += 1
                    continue
                element_type = element["type"]
                element_id = element["id"]
                tags = dict(element["tags"])
                source_url = discovery["canonical_osm_url"]
                element_raw = canonical_json_bytes(element)
                element_hash = hashlib.sha256(element_raw).hexdigest()
                evidence_id = stable_id(
                    "evidence", SOURCE_FAMILY, element_type, element_id, retrieved_at, element_hash
                )
                name = tags.get("name") or f"OSM fuzzy review {element_type} {element_id}"
                published_at = element.get("timestamp")
                as_of_date = str(
                    published_at
                    or payload.get("materialization", {}).get("snapshot_date")
                    or retrieved_at
                )[:10]
                evidence = Evidence(
                    id=evidence_id,
                    kind=EvidenceKind.OPENSTREETMAP,
                    title=f"OpenStreetMap fuzzy lead {element_type} {element_id}: {name}",
                    source_url=source_url,
                    publisher="OpenStreetMap contributors",
                    source_family=SOURCE_FAMILY,
                    license=OSM_LICENSE,
                    attribution=OSM_ATTRIBUTION,
                    published_at=str(published_at) if published_at else None,
                    retrieved_at=retrieved_at,
                    excerpt=json.dumps(tags, sort_keys=True),
                )
                evidence_metadata: dict[str, Any] = {
                    "element_type": element_type,
                    "element_id": element_id,
                    "canonical_osm_identity": f"{element_type}/{element_id}",
                    "input_sha256": input_sha256,
                    "source_scope": "osm_element",
                    "upstream_source_family": UPSTREAM_SOURCE_ROOT,
                    "upstream_source_root": UPSTREAM_SOURCE_ROOT,
                    "independent_from_direct_osm": False,
                    "review_only": True,
                    "candidate_recall_expansion_not_census": True,
                    "classification": discovery,
                }
                if bundle_provenance is not None:
                    evidence_metadata["provenance"] = bundle_provenance
                evidence_created += int(
                    add_evidence(
                        connection,
                        evidence,
                        content_hash=element_hash,
                        metadata=evidence_metadata,
                    )
                )
                stable_key = f"osm-fuzzy:{element_type}/{element_id}"
                entity_id = stable_id("entity", stable_key, "facility")
                entities_created += int(
                    add_facility(
                        connection,
                        Facility(entity_id, stable_key, evidence_id),
                        created_at=retrieved_at,
                    )
                )
                geometry = extract_geometry(element)
                latitude, longitude = extract_center(element, geometry)
                status, confidence, method = _lifecycle(discovery)
                add_snapshot(
                    connection,
                    snapshot_id=stable_id("snapshot", entity_id, evidence_id),
                    entity_id=entity_id,
                    name=name,
                    latitude=latitude,
                    longitude=longitude,
                    geometry=geometry,
                    tags=tags,
                    evidence_id=evidence_id,
                    as_of_date=as_of_date,
                    recorded_at=retrieved_at,
                    method="osm_fuzzy_review_candidate",
                    confidence=confidence,
                )
                add_lifecycle(
                    connection,
                    LifecycleObservation(
                        id=stable_id("lifecycle", entity_id, evidence_id, status.value),
                        entity_id=entity_id,
                        status=status,
                        evidence_id=evidence_id,
                        as_of_date=as_of_date,
                        recorded_at=retrieved_at,
                        method=method,
                        confidence=confidence,
                    ),
                )
                imported += 1

        return ImportResult(
            source=self.source_name,
            examined_elements=len(elements),
            imported_elements=imported,
            skipped_elements=skipped,
            entities_created=entities_created,
            evidence_created=evidence_created,
        )


__all__ = [
    "CLASSIFIER_VERSION",
    "DEFAULT_JSON_FILENAME",
    "DEFAULT_MANIFEST_FILENAME",
    "DEFAULT_XML_FILENAME",
    "EXTRACTION_PIPELINE",
    "FILTER_SHA256",
    "FILTER_VERSION",
    "MATERIALIZATION_PIPELINE",
    "OpenStreetMapFuzzyDiscoveryAdapter",
    "SOURCE_FAMILY",
    "VARIANTS",
    "build_fuzzy_overpass_document",
    "classify_tags",
    "filter_manifest_document",
    "materialize_fuzzy_extract",
    "osmium_filter_expressions",
    "trigger_tags",
    "validate_extraction_input",
]
