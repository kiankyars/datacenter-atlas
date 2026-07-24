"""Deterministic advisory entity-resolution candidates inside immutable releases.

This lane is intentionally narrower than the legacy release-level nearby report.
It emits only typed shared-source identities, tightly gated same-site candidates,
and explicit hierarchy candidates.  It never merges entities, accepts a link, or
computes a unique physical-site count.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import io
import json
from math import isfinite
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from .federated_release import (
    FederatedReleaseError,
    validate_federated_release_index,
)
from .global_snapshot import GlobalSnapshotError, validate_release_files
from .resolution import (
    _Record as ResolutionRecord,
    _bounds,
    _bounds_contains,
    _bounds_overlap,
    _country,
    _geometry_contains,
    _normalized_text,
    _similarity,
    _source_root,
    _spatial_candidate_pairs,
    haversine_distance_m,
)


DEFINITION_FORMAT = "datacenter-atlas-within-release-resolution-definition-v1"
BUNDLE_FORMAT = "datacenter-atlas-within-release-resolution-bundle-v1"
RELEASE_FORMAT = "datacenter-atlas-release-v1"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
CANDIDATES_JSON_FILENAME = "resolution-candidates.json"
CANDIDATES_CSV_FILENAME = "resolution-candidates.csv"
SUMMARY_FILENAME = "summary.json"
README_FILENAME = "README.md"
ATTRIBUTION_FILENAME = "ATTRIBUTION.txt"
BUNDLE_FILES = frozenset(
    {
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
        CANDIDATES_JSON_FILENAME,
        CANDIDATES_CSV_FILENAME,
        SUMMARY_FILENAME,
        README_FILENAME,
        ATTRIBUTION_FILENAME,
    }
)

POLICY = {
    "advisory_review_required": True,
    "automatic_merges_allowed": False,
    "accepted_relationships_created": False,
    "candidate_links_are_identity_claims": False,
    "child_release_payloads_copied": False,
    "cross_release_comparisons_allowed": False,
    "nearby_only_candidates_emitted": False,
    "review_only_release_rows_excluded": True,
    "source_provenance_roots_retained": True,
    "unique_physical_site_count": None,
}

CANDIDATE_CLASSES = frozenset(
    {"shared_source_identity", "tight_same_site", "part_of"}
)
RELATIONSHIPS = frozenset(
    {
        "same_site_candidate",
        "part_of_candidate",
        "source_record_structure_candidate",
    }
)
ENTITY_KINDS = frozenset({"campus", "facility", "building", "project"})
HIERARCHY_PAIRS = frozenset(
    {
        ("campus", "facility"),
        ("campus", "building"),
        ("campus", "project"),
        ("facility", "building"),
        ("facility", "project"),
        ("building", "project"),
    }
)
KIND_RANK = {"campus": 0, "facility": 1, "building": 2, "project": 3}

CANDIDATE_FIELDS = (
    "candidate_id",
    "release_id",
    "candidate_class",
    "relationship_suggestion",
    "score",
    "distance_m",
    "left_entity_id",
    "left_entity_kind",
    "left_name",
    "left_source_family",
    "left_source_root",
    "left_stable_key",
    "left_evidence_id",
    "right_entity_id",
    "right_entity_kind",
    "right_name",
    "right_source_family",
    "right_source_root",
    "right_stable_key",
    "right_evidence_id",
    "suggested_parent_entity_id",
    "suggested_child_entity_id",
    "input_review_only",
    "advisory_only",
    "automatic_merge_allowed",
    "signals_json",
)
JSON_CANDIDATE_FIELDS = (set(CANDIDATE_FIELDS) - {"signals_json"}) | {"signals"}
SIGNAL_FIELDS = frozenset(
    {
        "address_similarity",
        "country_left",
        "country_match",
        "country_right",
        "cross_source_family",
        "distance_score",
        "exact_source_identity_match",
        "geometry_bounds_overlap",
        "geometry_left_bounds_contain_right",
        "geometry_left_contains_right",
        "geometry_right_bounds_contain_left",
        "geometry_right_contains_left",
        "geometry_score",
        "identity_bases",
        "left_source_generated_structure",
        "matching_typed_source_identities",
        "name_similarity",
        "owner_operator_similarity",
        "right_source_generated_structure",
        "source_generated_structure",
        "source_independent",
    }
)

_OSM_STABLE_RE = re.compile(r"^osm:(node|way|relation)/(\d+)(?::|$)", re.I)
_WIKIDATA_STABLE_RE = re.compile(r"^wikidata:(Q\d+)(?::|$)", re.I)
_STRUCTURAL_STABLE_SUFFIXES = (
    ":facility-container",
    ":structural-facility-container",
    ":development-project",
)
_ORG_SPLIT_RE = re.compile(r"\s*(?:[;,|]|\band\b)\s*", re.I)
_ORG_QUALIFIER_RE = re.compile(r"\s*#(?:speculative|confident)\b", re.I)


class WithinReleaseResolutionError(ValueError):
    """Raised when a definition, input, or output violates this lane's contract."""


@dataclass(frozen=True, slots=True)
class WithinReleaseThresholds:
    """Published conservative gates for non-identity candidate links."""

    spatial_max_distance_m: float = 1_000.0
    same_site_max_distance_m: float = 250.0
    part_of_max_distance_m: float = 750.0
    same_site_min_score: float = 0.62
    part_of_min_score: float = 0.55
    semantic_min_similarity: float = 0.82

    def __post_init__(self) -> None:
        distances = (
            self.spatial_max_distance_m,
            self.same_site_max_distance_m,
            self.part_of_max_distance_m,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
            or value <= 0
            for value in distances
        ):
            raise ValueError("resolution distances must be finite and positive")
        if self.same_site_max_distance_m > self.spatial_max_distance_m:
            raise ValueError("same-site distance exceeds the spatial distance")
        if self.part_of_max_distance_m > self.spatial_max_distance_m:
            raise ValueError("part-of distance exceeds the spatial distance")
        for value in (
            self.same_site_min_score,
            self.part_of_min_score,
            self.semantic_min_similarity,
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(float(value))
                or not 0 <= value <= 1
            ):
                raise ValueError("resolution scores must be between zero and one")


@dataclass(frozen=True, slots=True)
class _Entity:
    release_id: str
    entity_id: str
    kind: str
    name: str | None
    latitude: float | None
    longitude: float | None
    geometry: Mapping[str, Any] | None
    tags: Mapping[str, Any]
    evidence_id: str
    source_family: str
    source_root: str
    stable_key: str
    source_url: str | None
    source_generated_structure: bool

    def resolution_record(self) -> ResolutionRecord | None:
        if self.latitude is None or self.longitude is None:
            return None
        return ResolutionRecord(
            entity_id=self.entity_id,
            kind=self.kind,
            name=self.name,
            latitude=self.latitude,
            longitude=self.longitude,
            geometry=self.geometry,
            tags=self.tags,
            evidence_id=self.evidence_id,
            source_family=self.source_family,
            stable_key=self.stable_key,
            source_url=self.source_url,
            source_root=self.source_root,
        )


@dataclass(frozen=True, slots=True)
class _Definition:
    path: Path
    raw: bytes
    bundle_id: str
    generated_at: str
    thresholds: WithinReleaseThresholds
    releases: tuple[Mapping[str, Any], ...]
    federation: Mapping[str, Any] | None


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _file_checkpoint(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def _checkpoint(raw: bytes) -> dict[str, Any]:
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise WithinReleaseResolutionError(f"{label} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise WithinReleaseResolutionError(f"{label} must be ISO 8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise WithinReleaseResolutionError(f"{label} must include a timezone")
    canonical = parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    if value != canonical:
        raise WithinReleaseResolutionError(
            f"{label} must use canonical UTC whole seconds"
        )
    return value


def _text(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise WithinReleaseResolutionError(f"{label} must be canonical non-empty text")
    return value


def _json_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise WithinReleaseResolutionError(f"{label} must be a regular file: {path}")
    raw = path.read_bytes()
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WithinReleaseResolutionError(f"{label} must be valid UTF-8 JSON") from error
    if not isinstance(document, dict):
        raise WithinReleaseResolutionError(f"{label} must be a JSON object")
    return document, raw


def _resolve_relative(definition: Path, value: Any, label: str) -> Path:
    relative = _text(value, label)
    assert relative is not None
    path = Path(relative)
    if path.is_absolute():
        raise WithinReleaseResolutionError(f"{label} must be relative to the definition")
    return (definition.parent / path).resolve()


def _load_definition(path: str | Path) -> _Definition:
    supplied = Path(path)
    document, raw = _json_object(supplied, "resolution definition")
    expected_keys = {
        "schema_version",
        "format",
        "bundle_id",
        "generated_at",
        "review_only_policy",
        "thresholds",
        "releases",
        "federation",
    }
    if set(document) != expected_keys:
        raise WithinReleaseResolutionError("resolution definition schema is invalid")
    if document.get("schema_version") != 1 or document.get("format") != DEFINITION_FORMAT:
        raise WithinReleaseResolutionError("resolution definition format is unsupported")
    if document.get("review_only_policy") != "exclude":
        raise WithinReleaseResolutionError("review-only inputs must be excluded")
    bundle_id = _text(document.get("bundle_id"), "bundle_id")
    generated_at = _timestamp(document.get("generated_at"), "generated_at")
    threshold_document = document.get("thresholds")
    if not isinstance(threshold_document, dict):
        raise WithinReleaseResolutionError("definition thresholds are invalid")
    try:
        thresholds = WithinReleaseThresholds(**threshold_document)
    except (TypeError, ValueError) as error:
        raise WithinReleaseResolutionError("definition thresholds are invalid") from error
    if asdict(thresholds) != threshold_document:
        raise WithinReleaseResolutionError("definition thresholds are non-canonical")

    release_values = document.get("releases")
    if not isinstance(release_values, list) or not release_values:
        raise WithinReleaseResolutionError("definition releases must be non-empty")
    releases: list[dict[str, Any]] = []
    for position, value in enumerate(release_values):
        if not isinstance(value, dict) or set(value) != {
            "release_id",
            "release_path",
            "expected_manifest_sha256",
            "expected_review_only",
        }:
            raise WithinReleaseResolutionError(
                f"definition release {position} schema is invalid"
            )
        release_id = _text(value.get("release_id"), f"release {position} ID")
        release_path = _resolve_relative(
            supplied.resolve(), value.get("release_path"), f"release {position} path"
        )
        expected_hash = value.get("expected_manifest_sha256")
        if not _is_sha256(expected_hash):
            raise WithinReleaseResolutionError(
                f"release {position} manifest hash is invalid"
            )
        expected_review_only = value.get("expected_review_only")
        if not isinstance(expected_review_only, bool):
            raise WithinReleaseResolutionError(
                f"release {position} review-only expectation is invalid"
            )
        releases.append(
            {
                "release_id": release_id,
                "release_path": release_path,
                "expected_manifest_sha256": expected_hash,
                "expected_review_only": expected_review_only,
            }
        )
    release_ids = [str(item["release_id"]) for item in releases]
    if release_ids != sorted(set(release_ids)):
        raise WithinReleaseResolutionError(
            "definition releases must be sorted by unique release ID"
        )

    federation_value = document.get("federation")
    federation: dict[str, Any] | None = None
    if federation_value is not None:
        if not isinstance(federation_value, dict) or set(federation_value) != {
            "index_path",
            "expected_manifest_sha256",
        }:
            raise WithinReleaseResolutionError("definition federation schema is invalid")
        expected_hash = federation_value.get("expected_manifest_sha256")
        if not _is_sha256(expected_hash):
            raise WithinReleaseResolutionError(
                "definition federation manifest hash is invalid"
            )
        federation = {
            "index_path": _resolve_relative(
                supplied.resolve(), federation_value.get("index_path"), "federation path"
            ),
            "expected_manifest_sha256": expected_hash,
        }
    return _Definition(
        path=supplied.resolve(),
        raw=raw,
        bundle_id=str(bundle_id),
        generated_at=generated_at,
        thresholds=thresholds,
        releases=tuple(releases),
        federation=federation,
    )


def _inspect_release(definition: Mapping[str, Any]) -> dict[str, Any]:
    release_id = str(definition["release_id"])
    directory = Path(definition["release_path"])
    if directory.is_symlink() or not directory.is_dir():
        raise WithinReleaseResolutionError(
            f"release must be a regular directory: {release_id}"
        )
    try:
        manifest = validate_release_files(directory)
    except (GlobalSnapshotError, OSError) as error:
        raise WithinReleaseResolutionError(
            f"release validation failed for {release_id}: {error}"
        ) from error
    if manifest.get("format") != RELEASE_FORMAT:
        raise WithinReleaseResolutionError(f"release format is unsupported: {release_id}")
    manifest_path = directory / MANIFEST_FILENAME
    manifest_checkpoint = _file_checkpoint(manifest_path)
    if manifest_checkpoint["sha256"] != definition["expected_manifest_sha256"]:
        raise WithinReleaseResolutionError(
            f"release manifest hash drifted: {release_id}"
        )
    review_only = manifest.get("review_only", False)
    if not isinstance(review_only, bool) or review_only != definition["expected_review_only"]:
        raise WithinReleaseResolutionError(
            f"release review-only scope drifted: {release_id}"
        )
    files = manifest.get("files")
    if not isinstance(files, dict) or "atlas.geojson" not in files:
        raise WithinReleaseResolutionError(
            f"release does not bind atlas.geojson: {release_id}"
        )
    geojson_path = directory / "atlas.geojson"
    attribution_path = directory / ATTRIBUTION_FILENAME
    if attribution_path.is_symlink() or not attribution_path.is_file():
        raise WithinReleaseResolutionError(
            f"release attribution is missing: {release_id}"
        )
    entities = manifest.get("entities")
    if isinstance(entities, bool) or not isinstance(entities, int) or entities < 0:
        raise WithinReleaseResolutionError(f"release entity count is invalid: {release_id}")
    source_families = manifest.get("source_families")
    if (
        not isinstance(source_families, list)
        or source_families != sorted(set(source_families))
        or any(not isinstance(item, str) or not item for item in source_families)
    ):
        raise WithinReleaseResolutionError(
            f"release source families are invalid: {release_id}"
        )
    return {
        "release_id": release_id,
        "directory": directory.resolve(),
        "manifest": manifest,
        "manifest_checkpoint": manifest_checkpoint,
        "atlas_geojson_path": geojson_path,
        "atlas_geojson_checkpoint": _file_checkpoint(geojson_path),
        "attribution": attribution_path.read_text(encoding="utf-8"),
        "entities": entities,
        "review_only": review_only,
        "source_families": source_families,
        "as_of": _text(manifest.get("as_of"), f"{release_id} as_of"),
        "recorded_at": _timestamp(
            manifest.get("recorded_at"), f"{release_id} recorded_at"
        ),
    }


def _federation_input(
    definition: _Definition, releases: Sequence[Mapping[str, Any]]
) -> dict[str, Any] | None:
    if definition.federation is None:
        return None
    directory = Path(definition.federation["index_path"])
    try:
        index = validate_federated_release_index(directory)
    except (FederatedReleaseError, OSError) as error:
        raise WithinReleaseResolutionError(
            f"federated index validation failed: {error}"
        ) from error
    manifest_checkpoint = _file_checkpoint(directory / MANIFEST_FILENAME)
    if manifest_checkpoint["sha256"] != definition.federation["expected_manifest_sha256"]:
        raise WithinReleaseResolutionError("federated index manifest hash drifted")
    expected = {
        str(item["release_id"]): str(item["manifest_checkpoint"]["sha256"])
        for item in releases
    }
    actual = {
        str(item["release_id"]): str(item["manifest"]["sha256"])
        for item in index["releases"]
    }
    if actual != expected:
        raise WithinReleaseResolutionError(
            "definition releases do not exactly match the federated index"
        )
    return {
        "directory_name": directory.name,
        "manifest": manifest_checkpoint,
        "federated_index": _file_checkpoint(directory / "federated-index.json"),
        "release_ids": sorted(actual),
    }


def _root_for_source_family(source_family: str) -> str:
    aliases = {
        "ada_infrastructure_location_pages": "ada_infrastructure",
        "ada_infrastructure_press_releases": "ada_infrastructure",
        "crusoe_newsroom": "crusoe",
        "edgeconnex_press_releases": "edgeconnex",
    }
    return aliases.get(source_family.casefold(), _source_root(source_family))


def _load_entities(release: Mapping[str, Any]) -> list[_Entity]:
    release_id = str(release["release_id"])
    document, _ = _json_object(
        Path(release["atlas_geojson_path"]), f"{release_id} atlas.geojson"
    )
    if document.get("type") != "FeatureCollection":
        raise WithinReleaseResolutionError(
            f"release atlas is not a FeatureCollection: {release_id}"
        )
    features = document.get("features")
    if not isinstance(features, list) or len(features) != release["entities"]:
        raise WithinReleaseResolutionError(
            f"release atlas feature count does not reconcile: {release_id}"
        )
    entities: list[_Entity] = []
    seen: set[str] = set()
    for position, feature in enumerate(features):
        if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
            raise WithinReleaseResolutionError(
                f"release atlas feature is invalid: {release_id} #{position}"
            )
        properties = feature["properties"]
        entity_id = _text(properties.get("entity_id"), "feature entity ID")
        if feature.get("id") != entity_id or entity_id in seen:
            raise WithinReleaseResolutionError(
                f"release atlas entity IDs are invalid: {release_id}"
            )
        seen.add(str(entity_id))
        kind = _text(properties.get("entity_kind"), "feature entity kind")
        if kind not in ENTITY_KINDS:
            raise WithinReleaseResolutionError(
                f"release atlas entity kind is unsupported: {release_id}"
            )
        source_family = _text(
            properties.get("source_family"), "feature source family"
        )
        stable_key = _text(properties.get("stable_key"), "feature stable key")
        evidence_id = _text(
            properties.get("snapshot_evidence_id"), "feature evidence ID"
        )
        name = properties.get("name")
        if name is not None:
            name = _text(name, "feature name")
        tags = properties.get("tags") or {}
        if not isinstance(tags, dict):
            raise WithinReleaseResolutionError("feature tags must be an object")
        tags = dict(tags)
        country = properties.get("country") or properties.get("country_iso_a2")
        if country and not any(
            key in tags
            for key in ("country", "country_name", "addr:country", "iso_country_code")
        ):
            tags["country"] = country
        geometry = feature.get("geometry")
        if geometry is not None and not isinstance(geometry, dict):
            raise WithinReleaseResolutionError("feature geometry must be an object or null")
        latitude = properties.get("latitude")
        longitude = properties.get("longitude")
        if latitude is None or longitude is None:
            latitude = longitude = None
        else:
            if (
                isinstance(latitude, bool)
                or isinstance(longitude, bool)
                or not isinstance(latitude, (int, float))
                or not isinstance(longitude, (int, float))
                or not isfinite(float(latitude))
                or not isfinite(float(longitude))
                or not -90 <= float(latitude) <= 90
                or not -180 <= float(longitude) <= 180
            ):
                raise WithinReleaseResolutionError("feature coordinates are invalid")
            latitude = float(latitude)
            longitude = float(longitude)
        source_url = properties.get("source_url")
        if source_url is not None:
            source_url = _text(source_url, "feature source URL")
        structure = bool(tags.get("pnnl_im3:structural_role")) or any(
            str(stable_key).endswith(suffix)
            for suffix in _STRUCTURAL_STABLE_SUFFIXES
        )
        entities.append(
            _Entity(
                release_id=release_id,
                entity_id=str(entity_id),
                kind=str(kind),
                name=str(name) if name is not None else None,
                latitude=latitude,
                longitude=longitude,
                geometry=geometry,
                tags=tags,
                evidence_id=str(evidence_id),
                source_family=str(source_family),
                source_root=_root_for_source_family(str(source_family)),
                stable_key=str(stable_key),
                source_url=str(source_url) if source_url is not None else None,
                source_generated_structure=structure,
            )
        )
    return sorted(entities, key=lambda item: item.entity_id)


def _identity_tokens(entity: _Entity) -> dict[str, str]:
    """Return typed record identities and a transparent extraction basis."""

    result: dict[str, str] = {}
    osm = _OSM_STABLE_RE.match(entity.stable_key)
    if osm:
        result[f"openstreetmap:{osm.group(1).casefold()}/{osm.group(2)}"] = (
            "osm_stable_key"
        )
    wikidata = _WIKIDATA_STABLE_RE.match(entity.stable_key)
    if wikidata:
        result[f"wikidata:{wikidata.group(1).upper()}"] = "wikidata_stable_key"

    tags = entity.tags
    source_record_id = tags.get("source_record_id")
    if isinstance(source_record_id, str) and source_record_id.strip():
        result[
            f"{entity.source_family}:record/{source_record_id.strip()}"
        ] = "typed_source_record_id"

    if entity.source_family == "openstreetmap:pnnl_im3":
        version = tags.get("pnnl_im3:dataset_version")
        source_type = tags.get("pnnl_im3:source_type")
        source_id = tags.get("pnnl_im3:source_id")
        if all(isinstance(value, str) and value.strip() for value in (version, source_type, source_id)):
            version_text = str(version).strip()
            type_text = str(source_type).strip().casefold()
            id_text = str(source_id).strip()
            result[
                f"openstreetmap:pnnl_im3:{version_text}:{type_text}/{id_text}"
            ] = "pnnl_im3_typed_dataset_record"
            if id_text.isdigit():
                normalized_id = str(int(id_text))
                osm_types: tuple[str, ...] = {
                    "point": ("node",),
                    "building": ("way",),
                    # IM3 campus polygons preserve OSM numeric source IDs but can
                    # originate from either a way or a multipolygon relation.
                    "campus": ("way", "relation"),
                }.get(type_text, ())
                for osm_type in osm_types:
                    result[f"openstreetmap:{osm_type}/{normalized_id}"] = (
                        "pnnl_im3_osm_numeric_source_id"
                    )
    return result


def _address(tags: Mapping[str, Any]) -> str:
    direct = tags.get("address") or tags.get("addr:full")
    if direct:
        return str(direct)
    if not (
        tags.get("addr:street")
        or tags.get("addr:postcode")
        or (tags.get("addr:housenumber") and tags.get("addr:city"))
    ):
        return ""
    return " ".join(
        str(tags[key])
        for key in ("addr:housenumber", "addr:street", "addr:city", "addr:postcode")
        if tags.get(key)
    )


def _organizations(tags: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in (
        "owner",
        "owners",
        "operator",
        "operators",
        "role:owner",
        "role:operator",
        "users",
        "pnnl_im3:operator",
    ):
        value = tags.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif value:
            values.extend(_ORG_SPLIT_RE.split(str(value)))
    normalized = {
        _normalized_text(_ORG_QUALIFIER_RE.sub("", value))
        for value in values
        if _normalized_text(_ORG_QUALIFIER_RE.sub("", value))
    }
    return sorted(normalized)


def _organization_similarity(left: _Entity, right: _Entity) -> float:
    left_values = _organizations(left.tags)
    right_values = _organizations(right.tags)
    return max(
        (_similarity(left_value, right_value) for left_value in left_values for right_value in right_values),
        default=0.0,
    )


def _distance(left: _Entity, right: _Entity) -> float | None:
    if (
        left.latitude is None
        or left.longitude is None
        or right.latitude is None
        or right.longitude is None
    ):
        return None
    return haversine_distance_m(
        left.latitude, left.longitude, right.latitude, right.longitude
    )


def _signals(
    left: _Entity,
    right: _Entity,
    distance_m: float | None,
    thresholds: WithinReleaseThresholds,
    matching_identities: Sequence[str],
    identity_bases: Sequence[str],
) -> dict[str, Any]:
    left_country = _country(left.tags)
    right_country = _country(right.tags)
    left_bounds = _bounds(left.geometry)
    right_bounds = _bounds(right.geometry)
    left_contains_right = bool(
        right.longitude is not None
        and right.latitude is not None
        and _geometry_contains(left.geometry, right.longitude, right.latitude)
    )
    right_contains_left = bool(
        left.longitude is not None
        and left.latitude is not None
        and _geometry_contains(right.geometry, left.longitude, left.latitude)
    )
    left_bounds_contain_right = bool(
        right.longitude is not None
        and right.latitude is not None
        and _bounds_contains(left_bounds, right.longitude, right.latitude)
    )
    right_bounds_contain_left = bool(
        left.longitude is not None
        and left.latitude is not None
        and _bounds_contains(right_bounds, left.longitude, left.latitude)
    )
    bounds_overlap = _bounds_overlap(left_bounds, right_bounds)
    geometry_score = (
        1.0
        if left_contains_right or right_contains_left
        else 0.5
        if left_bounds_contain_right or right_bounds_contain_left or bounds_overlap
        else 0.0
    )
    distance_score = (
        max(0.0, 1.0 - distance_m / thresholds.spatial_max_distance_m)
        if distance_m is not None
        else 0.0
    )
    return {
        "address_similarity": round(
            _similarity(_address(left.tags), _address(right.tags)), 6
        ),
        "country_left": left_country,
        "country_match": (
            left_country == right_country
            if left_country is not None and right_country is not None
            else None
        ),
        "country_right": right_country,
        "cross_source_family": left.source_family != right.source_family,
        "distance_score": round(distance_score, 6),
        "exact_source_identity_match": bool(matching_identities),
        "geometry_bounds_overlap": bounds_overlap,
        "geometry_left_bounds_contain_right": left_bounds_contain_right,
        "geometry_left_contains_right": left_contains_right,
        "geometry_right_bounds_contain_left": right_bounds_contain_left,
        "geometry_right_contains_left": right_contains_left,
        "geometry_score": geometry_score,
        "identity_bases": sorted(set(identity_bases)),
        "left_source_generated_structure": left.source_generated_structure,
        "matching_typed_source_identities": sorted(set(matching_identities)),
        "name_similarity": round(_similarity(left.name, right.name, names=True), 6),
        "owner_operator_similarity": round(_organization_similarity(left, right), 6),
        "right_source_generated_structure": right.source_generated_structure,
        "source_generated_structure": (
            left.source_generated_structure or right.source_generated_structure
        ),
        "source_independent": left.source_root != right.source_root,
    }


def _score(signals: Mapping[str, Any]) -> float:
    score = (
        0.35 * signals["distance_score"]
        + 0.30 * signals["name_similarity"]
        + 0.15 * signals["address_similarity"]
        + 0.12 * signals["owner_operator_similarity"]
        + 0.08 * signals["geometry_score"]
    )
    if signals["exact_source_identity_match"]:
        score = max(score, 0.99)
    return round(min(1.0, max(0.0, score)), 6)


def _parent_child(left: _Entity, right: _Entity) -> tuple[str | None, str | None]:
    if left.kind == right.kind:
        return None, None
    ordered = sorted((left, right), key=lambda item: KIND_RANK[item.kind])
    if (ordered[0].kind, ordered[1].kind) not in HIERARCHY_PAIRS:
        return None, None
    return ordered[0].entity_id, ordered[1].entity_id


def _candidate_id(
    release_id: str, candidate_class: str, left_id: str, right_id: str
) -> str:
    payload = "\x1f".join(
        ("within-release-resolution-v1", release_id, candidate_class, left_id, right_id)
    ).encode("utf-8")
    return f"within:{hashlib.sha256(payload).hexdigest()}"


def _candidate(
    left: _Entity,
    right: _Entity,
    candidate_class: str,
    thresholds: WithinReleaseThresholds,
    *,
    matching_identities: Sequence[str] = (),
    identity_bases: Sequence[str] = (),
) -> dict[str, Any]:
    if right.entity_id < left.entity_id:
        left, right = right, left
    distance_m = _distance(left, right)
    signals = _signals(
        left,
        right,
        distance_m,
        thresholds,
        matching_identities,
        identity_bases,
    )
    parent_id, child_id = _parent_child(left, right)
    if candidate_class == "shared_source_identity":
        relationship = (
            "source_record_structure_candidate"
            if parent_id is not None or signals["source_generated_structure"]
            else "same_site_candidate"
        )
    elif candidate_class == "tight_same_site":
        relationship = "same_site_candidate"
    else:
        relationship = "part_of_candidate"
    return {
        "candidate_id": _candidate_id(
            left.release_id, candidate_class, left.entity_id, right.entity_id
        ),
        "release_id": left.release_id,
        "candidate_class": candidate_class,
        "relationship_suggestion": relationship,
        "score": _score(signals),
        "distance_m": round(distance_m, 3) if distance_m is not None else None,
        "left_entity_id": left.entity_id,
        "left_entity_kind": left.kind,
        "left_name": left.name,
        "left_source_family": left.source_family,
        "left_source_root": left.source_root,
        "left_stable_key": left.stable_key,
        "left_evidence_id": left.evidence_id,
        "right_entity_id": right.entity_id,
        "right_entity_kind": right.kind,
        "right_name": right.name,
        "right_source_family": right.source_family,
        "right_source_root": right.source_root,
        "right_stable_key": right.stable_key,
        "right_evidence_id": right.evidence_id,
        "suggested_parent_entity_id": parent_id,
        "suggested_child_entity_id": child_id,
        "input_review_only": False,
        "advisory_only": True,
        "automatic_merge_allowed": False,
        "signals": signals,
    }


def _part_of_semantic_gate(signals: Mapping[str, Any]) -> bool:
    semantic = max(
        signals["name_similarity"],
        signals["address_similarity"],
        signals["owner_operator_similarity"],
    )
    contains = (
        signals["geometry_left_contains_right"]
        or signals["geometry_right_contains_left"]
    )
    return bool(
        (contains and semantic >= 0.4)
        or signals["name_similarity"] >= 0.82
        or signals["address_similarity"] >= 0.9
        or (
            signals["owner_operator_similarity"] >= 0.85
            and signals["name_similarity"] >= 0.35
        )
    )


def generate_within_release_candidates(
    release_id: str,
    entities: Sequence[_Entity],
    *,
    thresholds: WithinReleaseThresholds | None = None,
) -> list[dict[str, Any]]:
    """Generate a stable, advisory candidate set inside one release."""

    thresholds = thresholds or WithinReleaseThresholds()
    by_id = {entity.entity_id: entity for entity in entities}
    identities: dict[str, list[tuple[_Entity, str]]] = defaultdict(list)
    for entity in entities:
        for token, basis in _identity_tokens(entity).items():
            identities[token].append((entity, basis))

    exact_pairs: dict[tuple[str, str], dict[str, set[str]]] = {}
    for token, members in identities.items():
        if len(members) < 2:
            continue
        for left_index, (left, left_basis) in enumerate(members):
            for right, right_basis in members[left_index + 1 :]:
                if left.entity_id == right.entity_id:
                    continue
                pair = tuple(sorted((left.entity_id, right.entity_id)))
                record = exact_pairs.setdefault(
                    pair, {"identities": set(), "bases": set()}
                )
                record["identities"].add(token)
                record["bases"].update((left_basis, right_basis))

    candidates = [
        _candidate(
            by_id[left_id],
            by_id[right_id],
            "shared_source_identity",
            thresholds,
            matching_identities=sorted(record["identities"]),
            identity_bases=sorted(record["bases"]),
        )
        for (left_id, right_id), record in sorted(exact_pairs.items())
    ]

    resolution_records = [
        record
        for entity in entities
        if (record := entity.resolution_record()) is not None
    ]
    for left_record, right_record in _spatial_candidate_pairs(
        resolution_records, thresholds.spatial_max_distance_m
    ):
        pair = tuple(sorted((left_record.entity_id, right_record.entity_id)))
        if pair in exact_pairs:
            continue
        left = by_id[left_record.entity_id]
        right = by_id[right_record.entity_id]
        if left.source_family == right.source_family:
            continue
        distance_m = _distance(left, right)
        assert distance_m is not None
        if distance_m > thresholds.spatial_max_distance_m:
            continue
        left_country = _country(left.tags)
        right_country = _country(right.tags)
        if left_country and right_country and left_country != right_country:
            continue
        signals = _signals(left, right, distance_m, thresholds, (), ())
        score = _score(signals)
        semantic = max(
            signals["name_similarity"],
            signals["address_similarity"],
            signals["owner_operator_similarity"],
        )
        if (
            left.kind == right.kind
            and distance_m <= thresholds.same_site_max_distance_m
            and score >= thresholds.same_site_min_score
            and semantic >= thresholds.semantic_min_similarity
        ):
            candidates.append(
                _candidate(left, right, "tight_same_site", thresholds)
            )
            continue
        kind_pair = tuple(
            item.kind for item in sorted((left, right), key=lambda item: KIND_RANK[item.kind])
        )
        if (
            kind_pair in HIERARCHY_PAIRS
            and distance_m <= thresholds.part_of_max_distance_m
            and score >= thresholds.part_of_min_score
            and _part_of_semantic_gate(signals)
        ):
            candidates.append(_candidate(left, right, "part_of", thresholds))

    return sorted(
        candidates,
        key=lambda row: (
            row["release_id"],
            row["left_entity_id"],
            row["right_entity_id"],
            row["candidate_class"],
        ),
    )


def _input_descriptor(
    release: Mapping[str, Any], coordinate_entities: int | None
) -> dict[str, Any]:
    return {
        "release_id": release["release_id"],
        "release_directory_name": Path(release["directory"]).name,
        "release_manifest": release["manifest_checkpoint"],
        "atlas_geojson": release["atlas_geojson_checkpoint"],
        "as_of": release["as_of"],
        "recorded_at": release["recorded_at"],
        "source_families": release["source_families"],
        "source_scoped_entity_records": release["entities"],
        "coordinate_entity_records": coordinate_entities,
        "review_only": release["review_only"],
        "disposition": "excluded_review_only" if release["review_only"] else "processed",
    }


def _summary(
    candidates: Sequence[Mapping[str, Any]],
    inputs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    candidate_class = Counter(str(row["candidate_class"]) for row in candidates)
    relationship = Counter(str(row["relationship_suggestion"]) for row in candidates)
    releases = Counter(str(row["release_id"]) for row in candidates)
    independence = Counter(
        "independent" if row["signals"]["source_independent"] else "shared_root"
        for row in candidates
    )
    roots = Counter(
        " | ".join((str(row["left_source_root"]), str(row["right_source_root"])))
        for row in candidates
    )
    identities = {
        identity
        for row in candidates
        for identity in row["signals"]["matching_typed_source_identities"]
    }
    excluded = [item for item in inputs if item["review_only"]]
    processed = [item for item in inputs if not item["review_only"]]
    return {
        "input_release_bundles": len(inputs),
        "processed_release_bundles": len(processed),
        "excluded_review_only_release_bundles": len(excluded),
        "excluded_review_only_release_ids": sorted(
            str(item["release_id"]) for item in excluded
        ),
        "source_scoped_entity_records": sum(
            int(item["source_scoped_entity_records"]) for item in inputs
        ),
        "processed_source_scoped_entity_records": sum(
            int(item["source_scoped_entity_records"]) for item in processed
        ),
        "review_only_source_scoped_entity_records_excluded": sum(
            int(item["source_scoped_entity_records"]) for item in excluded
        ),
        "processed_coordinate_entity_records": sum(
            int(item["coordinate_entity_records"] or 0) for item in processed
        ),
        "candidate_links": len(candidates),
        "candidate_links_by_class": dict(sorted(candidate_class.items())),
        "candidate_links_by_relationship_suggestion": dict(
            sorted(relationship.items())
        ),
        "candidate_links_by_release": dict(sorted(releases.items())),
        "candidate_links_by_source_independence": dict(
            sorted(independence.items())
        ),
        "candidate_links_by_source_root_pair": dict(sorted(roots.items())),
        "distinct_matching_typed_source_identities": len(identities),
        "source_generated_structure_candidate_links": sum(
            bool(row["signals"]["source_generated_structure"])
            for row in candidates
        ),
        "advisory_review_only_candidate_links": len(candidates),
        "accepted_relationships": 0,
        "automatic_merges": 0,
        "unique_physical_sites": None,
    }


def _candidate_json(candidates: Sequence[Mapping[str, Any]]) -> bytes:
    return _canonical_json(list(candidates))


def _candidate_csv(candidates: Sequence[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CANDIDATE_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in candidates:
        if set(row) != JSON_CANDIDATE_FIELDS:
            raise WithinReleaseResolutionError("candidate schema is invalid")
        csv_row = dict(row)
        csv_row["signals_json"] = json.dumps(
            csv_row.pop("signals"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        writer.writerow(csv_row)
    return stream.getvalue().encode("utf-8")


def _readme(summary: Mapping[str, Any]) -> bytes:
    return (
        "# Within-release entity-resolution candidates\n\n"
        f"This immutable advisory bundle contains {summary['candidate_links']:,} "
        "candidate links generated independently inside each processed release. It emits only "
        "typed shared-source identities, tightly gated same-site links, and hierarchy/part-of "
        "links. It emits no broad nearby-only rows.\n\n"
        f"The build processed {summary['processed_source_scoped_entity_records']:,} source-scoped "
        f"records and excluded {summary['review_only_source_scoped_entity_records_excluded']:,} "
        "review-only records before matching. Structural container or project pairs retained "
        "from a canonical release are explicitly marked in candidate signals.\n\n"
        "Every row is a manual-review lead, not a merge or identity claim. Source-family and "
        "upstream-root labels remain visible; records derived from the same root are not "
        "independent corroboration. The bundle reports zero accepted relationships, zero "
        "automatic merges, and no unique physical-site count.\n"
    ).encode("utf-8")


def _attribution(releases: Sequence[Mapping[str, Any]]) -> bytes:
    sections = []
    for release in releases:
        disposition = "excluded review-only input" if release["review_only"] else "processed input"
        sections.append(
            f"[{release['release_id']}; {disposition}]\n"
            f"{str(release['attribution']).rstrip()}"
        )
    return ("\n\n".join(sections) + "\n").encode("utf-8")


def _prepare_bundle(definition: _Definition) -> tuple[dict[str, bytes], dict[str, Any], list[dict[str, Any]]]:
    releases = [_inspect_release(item) for item in definition.releases]
    federation = _federation_input(definition, releases)
    candidates: list[dict[str, Any]] = []
    input_descriptors: list[dict[str, Any]] = []
    for release in releases:
        if release["review_only"]:
            input_descriptors.append(_input_descriptor(release, None))
            continue
        entities = _load_entities(release)
        candidates.extend(
            generate_within_release_candidates(
                str(release["release_id"]),
                entities,
                thresholds=definition.thresholds,
            )
        )
        input_descriptors.append(
            _input_descriptor(
                release,
                sum(entity.latitude is not None for entity in entities),
            )
        )
    candidates.sort(
        key=lambda row: (
            row["release_id"],
            row["left_entity_id"],
            row["right_entity_id"],
            row["candidate_class"],
        )
    )
    summary = _summary(candidates, input_descriptors)
    documents = {
        CANDIDATES_JSON_FILENAME: _candidate_json(candidates),
        CANDIDATES_CSV_FILENAME: _candidate_csv(candidates),
        SUMMARY_FILENAME: _canonical_json(summary),
        README_FILENAME: _readme(summary),
        ATTRIBUTION_FILENAME: _attribution(releases),
    }
    manifest = {
        "format": BUNDLE_FORMAT,
        "schema_version": 1,
        "bundle_id": definition.bundle_id,
        "generated_at": definition.generated_at,
        "definition": {
            "file": definition.path.name,
            **_checkpoint(definition.raw),
        },
        "federated_input": federation,
        "thresholds": asdict(definition.thresholds),
        "policy": POLICY,
        "inputs": input_descriptors,
        "counts": summary,
        "files": {
            name: _checkpoint(raw) for name, raw in sorted(documents.items())
        },
    }
    manifest_raw = _canonical_json(manifest)
    payloads = dict(documents)
    payloads[MANIFEST_FILENAME] = manifest_raw
    payloads[MANIFEST_HASH_FILENAME] = (
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    return payloads, manifest, releases


def _number(
    value: Any,
    label: str,
    *,
    minimum: float,
    maximum: float | None = None,
    nullable: bool = False,
) -> float | None:
    if nullable and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WithinReleaseResolutionError(f"{label} must be numeric")
    result = float(value)
    if not isfinite(result) or result < minimum or (
        maximum is not None and result > maximum
    ):
        raise WithinReleaseResolutionError(f"{label} is outside its valid range")
    return result


def _validate_checkpoint(value: Any, label: str) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {"bytes", "sha256"}
        or isinstance(value.get("bytes"), bool)
        or not isinstance(value.get("bytes"), int)
        or value["bytes"] < 0
        or not _is_sha256(value.get("sha256"))
    ):
        raise WithinReleaseResolutionError(f"{label} checkpoint is invalid")


def _validate_candidate(
    row: Any, thresholds: WithinReleaseThresholds
) -> tuple[str, str, str, str]:
    if not isinstance(row, dict) or set(row) != JSON_CANDIDATE_FIELDS:
        raise WithinReleaseResolutionError("candidate schema is invalid")
    for field in (
        "candidate_id",
        "release_id",
        "candidate_class",
        "relationship_suggestion",
        "left_entity_id",
        "left_entity_kind",
        "left_source_family",
        "left_source_root",
        "left_stable_key",
        "left_evidence_id",
        "right_entity_id",
        "right_entity_kind",
        "right_source_family",
        "right_source_root",
        "right_stable_key",
        "right_evidence_id",
    ):
        _text(row[field], f"candidate {field}")
    for field in ("left_name", "right_name", "suggested_parent_entity_id", "suggested_child_entity_id"):
        _text(row[field], f"candidate {field}", nullable=True)
    if row["candidate_class"] not in CANDIDATE_CLASSES:
        raise WithinReleaseResolutionError("candidate class is invalid")
    if row["relationship_suggestion"] not in RELATIONSHIPS:
        raise WithinReleaseResolutionError("candidate relationship is invalid")
    if row["left_entity_kind"] not in ENTITY_KINDS or row["right_entity_kind"] not in ENTITY_KINDS:
        raise WithinReleaseResolutionError("candidate entity kind is invalid")
    if row["left_entity_id"] >= row["right_entity_id"]:
        raise WithinReleaseResolutionError("candidate entity orientation is non-canonical")
    expected_id = _candidate_id(
        row["release_id"],
        row["candidate_class"],
        row["left_entity_id"],
        row["right_entity_id"],
    )
    if row["candidate_id"] != expected_id:
        raise WithinReleaseResolutionError("candidate ID does not reconcile")
    if (
        row["input_review_only"] is not False
        or row["advisory_only"] is not True
        or row["automatic_merge_allowed"] is not False
    ):
        raise WithinReleaseResolutionError("candidate review scope is invalid")
    score = _number(row["score"], "candidate score", minimum=0, maximum=1)
    distance = _number(
        row["distance_m"], "candidate distance", minimum=0, nullable=True
    )
    signals = row["signals"]
    if not isinstance(signals, dict) or set(signals) != SIGNAL_FIELDS:
        raise WithinReleaseResolutionError("candidate signals are invalid")
    similarities = {
        field: _number(signals[field], f"candidate signal {field}", minimum=0, maximum=1)
        for field in (
            "address_similarity",
            "distance_score",
            "geometry_score",
            "name_similarity",
            "owner_operator_similarity",
        )
    }
    boolean_fields = (
        "cross_source_family",
        "exact_source_identity_match",
        "geometry_bounds_overlap",
        "geometry_left_bounds_contain_right",
        "geometry_left_contains_right",
        "geometry_right_bounds_contain_left",
        "geometry_right_contains_left",
        "left_source_generated_structure",
        "right_source_generated_structure",
        "source_generated_structure",
        "source_independent",
    )
    if any(not isinstance(signals[field], bool) for field in boolean_fields):
        raise WithinReleaseResolutionError("candidate boolean signal is invalid")
    for field in ("country_left", "country_right"):
        _text(signals[field], f"candidate signal {field}", nullable=True)
    country_match = signals["country_match"]
    if country_match is not None and not isinstance(country_match, bool):
        raise WithinReleaseResolutionError("candidate country match is invalid")
    expected_country = (
        signals["country_left"] == signals["country_right"]
        if signals["country_left"] is not None and signals["country_right"] is not None
        else None
    )
    if country_match != expected_country or (
        country_match is False and row["candidate_class"] != "shared_source_identity"
    ):
        raise WithinReleaseResolutionError("candidate country signals do not reconcile")
    identities = signals["matching_typed_source_identities"]
    bases = signals["identity_bases"]
    for values, label in ((identities, "identities"), (bases, "identity bases")):
        if (
            not isinstance(values, list)
            or values != sorted(set(values))
            or any(not isinstance(value, str) or not value for value in values)
        ):
            raise WithinReleaseResolutionError(f"candidate {label} are invalid")
    if signals["exact_source_identity_match"] != bool(identities):
        raise WithinReleaseResolutionError("candidate exact identity signal is invalid")
    if bool(identities) != bool(bases):
        raise WithinReleaseResolutionError("candidate identity bases do not reconcile")
    if signals["cross_source_family"] != (
        row["left_source_family"] != row["right_source_family"]
    ):
        raise WithinReleaseResolutionError("candidate source-family signal is invalid")
    if signals["source_independent"] != (
        row["left_source_root"] != row["right_source_root"]
    ):
        raise WithinReleaseResolutionError("candidate source-root signal is invalid")
    if signals["source_generated_structure"] != (
        signals["left_source_generated_structure"]
        or signals["right_source_generated_structure"]
    ):
        raise WithinReleaseResolutionError("candidate structural signal is invalid")
    expected_distance_score = (
        max(0.0, 1.0 - float(distance) / thresholds.spatial_max_distance_m)
        if distance is not None
        else 0.0
    )
    if similarities["distance_score"] != round(expected_distance_score, 6):
        raise WithinReleaseResolutionError("candidate distance score does not reconcile")
    expected_score = (
        0.35 * float(similarities["distance_score"])
        + 0.30 * float(similarities["name_similarity"])
        + 0.15 * float(similarities["address_similarity"])
        + 0.12 * float(similarities["owner_operator_similarity"])
        + 0.08 * float(similarities["geometry_score"])
    )
    if signals["exact_source_identity_match"]:
        expected_score = max(expected_score, 0.99)
    if score != round(min(1.0, max(0.0, expected_score)), 6):
        raise WithinReleaseResolutionError("candidate score does not reconcile")

    candidate_class = row["candidate_class"]
    if candidate_class == "shared_source_identity":
        if not identities:
            raise WithinReleaseResolutionError("identity candidate has no typed identity")
        expected_relationship = (
            "source_record_structure_candidate"
            if row["suggested_parent_entity_id"] is not None
            or signals["source_generated_structure"]
            else "same_site_candidate"
        )
    elif candidate_class == "tight_same_site":
        if identities or distance is None or distance > thresholds.same_site_max_distance_m:
            raise WithinReleaseResolutionError("same-site candidate gate is invalid")
        if row["left_entity_kind"] != row["right_entity_kind"]:
            raise WithinReleaseResolutionError("same-site candidate kinds differ")
        if score < thresholds.same_site_min_score or max(
            float(similarities["name_similarity"]),
            float(similarities["address_similarity"]),
            float(similarities["owner_operator_similarity"]),
        ) < thresholds.semantic_min_similarity:
            raise WithinReleaseResolutionError("same-site semantic gate is invalid")
        expected_relationship = "same_site_candidate"
    else:
        if identities or distance is None or distance > thresholds.part_of_max_distance_m:
            raise WithinReleaseResolutionError("part-of candidate distance gate is invalid")
        if score < thresholds.part_of_min_score or not _part_of_semantic_gate(signals):
            raise WithinReleaseResolutionError("part-of semantic gate is invalid")
        expected_relationship = "part_of_candidate"
    if row["relationship_suggestion"] != expected_relationship:
        raise WithinReleaseResolutionError("candidate relationship does not reconcile")

    left_stub = _Entity(
        row["release_id"], row["left_entity_id"], row["left_entity_kind"], None,
        None, None, None, {}, row["left_evidence_id"], row["left_source_family"],
        row["left_source_root"], row["left_stable_key"], None,
        signals["left_source_generated_structure"],
    )
    right_stub = _Entity(
        row["release_id"], row["right_entity_id"], row["right_entity_kind"], None,
        None, None, None, {}, row["right_evidence_id"], row["right_source_family"],
        row["right_source_root"], row["right_stable_key"], None,
        signals["right_source_generated_structure"],
    )
    expected_parent, expected_child = _parent_child(left_stub, right_stub)
    if (
        row["suggested_parent_entity_id"],
        row["suggested_child_entity_id"],
    ) != (expected_parent, expected_child):
        raise WithinReleaseResolutionError("candidate hierarchy hint does not reconcile")
    if candidate_class == "part_of" and expected_parent is None:
        raise WithinReleaseResolutionError("part-of candidate lacks a hierarchy hint")
    return (
        row["release_id"],
        row["left_entity_id"],
        row["right_entity_id"],
        candidate_class,
    )


def validate_within_release_resolution(
    path: str | Path,
    *,
    definition_path: str | Path | None = None,
    verify_inputs: bool = False,
) -> dict[str, Any]:
    """Validate a completed bundle offline, optionally rebuilding exact inputs."""

    directory = Path(path)
    if directory.is_symlink() or not directory.is_dir():
        raise WithinReleaseResolutionError("resolution bundle must be a regular directory")
    entries = list(directory.iterdir())
    if any(item.is_symlink() or not item.is_file() for item in entries):
        raise WithinReleaseResolutionError("resolution bundle entries must be regular files")
    if {item.name for item in entries} != BUNDLE_FILES:
        raise WithinReleaseResolutionError("resolution bundle file inventory is invalid")
    manifest, manifest_raw = _json_object(
        directory / MANIFEST_FILENAME, "resolution manifest"
    )
    if manifest.get("format") != BUNDLE_FORMAT or manifest.get("schema_version") != 1:
        raise WithinReleaseResolutionError("resolution bundle format is unsupported")
    _text(manifest.get("bundle_id"), "resolution bundle ID")
    _timestamp(manifest.get("generated_at"), "resolution generated_at")
    if manifest.get("policy") != POLICY:
        raise WithinReleaseResolutionError("resolution policy is invalid")
    definition_record = manifest.get("definition")
    if not isinstance(definition_record, dict) or set(definition_record) != {
        "file", "bytes", "sha256"
    }:
        raise WithinReleaseResolutionError("resolution definition checkpoint is invalid")
    _text(definition_record.get("file"), "resolution definition filename")
    _validate_checkpoint(
        {key: definition_record[key] for key in ("bytes", "sha256")},
        "resolution definition",
    )
    threshold_document = manifest.get("thresholds")
    if not isinstance(threshold_document, dict):
        raise WithinReleaseResolutionError("resolution thresholds are invalid")
    try:
        thresholds = WithinReleaseThresholds(**threshold_document)
    except (TypeError, ValueError) as error:
        raise WithinReleaseResolutionError("resolution thresholds are invalid") from error
    if asdict(thresholds) != threshold_document:
        raise WithinReleaseResolutionError("resolution thresholds are non-canonical")
    inputs = manifest.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise WithinReleaseResolutionError("resolution inputs are invalid")
    expected_input_keys = {
        "release_id",
        "release_directory_name",
        "release_manifest",
        "atlas_geojson",
        "as_of",
        "recorded_at",
        "source_families",
        "source_scoped_entity_records",
        "coordinate_entity_records",
        "review_only",
        "disposition",
    }
    release_ids: list[str] = []
    for value in inputs:
        if not isinstance(value, dict) or set(value) != expected_input_keys:
            raise WithinReleaseResolutionError("resolution input schema is invalid")
        release_id = _text(value["release_id"], "resolution input release ID")
        release_ids.append(str(release_id))
        _text(value["release_directory_name"], "resolution input directory")
        _text(value["as_of"], "resolution input as_of")
        _timestamp(value["recorded_at"], "resolution input recorded_at")
        _validate_checkpoint(value["release_manifest"], "release manifest")
        _validate_checkpoint(value["atlas_geojson"], "release atlas GeoJSON")
        source_families = value["source_families"]
        if (
            not isinstance(source_families, list)
            or source_families != sorted(set(source_families))
            or any(not isinstance(item, str) or not item for item in source_families)
        ):
            raise WithinReleaseResolutionError("resolution input sources are invalid")
        count = value["source_scoped_entity_records"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise WithinReleaseResolutionError("resolution input entity count is invalid")
        if not isinstance(value["review_only"], bool):
            raise WithinReleaseResolutionError("resolution input review scope is invalid")
        expected_disposition = (
            "excluded_review_only" if value["review_only"] else "processed"
        )
        if value["disposition"] != expected_disposition:
            raise WithinReleaseResolutionError("resolution input disposition is invalid")
        coordinate_count = value["coordinate_entity_records"]
        if value["review_only"]:
            if coordinate_count is not None:
                raise WithinReleaseResolutionError(
                    "excluded review-only input must not be scanned"
                )
        elif (
            isinstance(coordinate_count, bool)
            or not isinstance(coordinate_count, int)
            or not 0 <= coordinate_count <= count
        ):
            raise WithinReleaseResolutionError(
                "resolution input coordinate count is invalid"
            )
    if release_ids != sorted(set(release_ids)):
        raise WithinReleaseResolutionError("resolution inputs are not sorted and unique")

    federation = manifest.get("federated_input")
    if federation is not None:
        if not isinstance(federation, dict) or set(federation) != {
            "directory_name", "manifest", "federated_index", "release_ids"
        }:
            raise WithinReleaseResolutionError("federated input schema is invalid")
        _text(federation["directory_name"], "federated input directory")
        _validate_checkpoint(federation["manifest"], "federated manifest")
        _validate_checkpoint(federation["federated_index"], "federated index")
        if federation["release_ids"] != release_ids:
            raise WithinReleaseResolutionError(
                "federated input release IDs do not reconcile"
            )

    files = manifest.get("files")
    payload_names = BUNDLE_FILES - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    if not isinstance(files, dict) or set(files) != payload_names:
        raise WithinReleaseResolutionError("resolution payload inventory is invalid")
    for name in sorted(payload_names):
        _validate_checkpoint(files[name], f"resolution payload {name}")
        if _file_checkpoint(directory / name) != files[name]:
            raise WithinReleaseResolutionError(
                f"resolution payload checkpoint does not match: {name}"
            )
    expected_sidecar = f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode(
        "ascii"
    )
    if (directory / MANIFEST_HASH_FILENAME).read_bytes() != expected_sidecar:
        raise WithinReleaseResolutionError("resolution manifest sidecar does not match")
    try:
        candidates = json.loads(
            (directory / CANDIDATES_JSON_FILENAME).read_text(encoding="utf-8")
        )
        summary = json.loads(
            (directory / SUMMARY_FILENAME).read_text(encoding="utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WithinReleaseResolutionError("resolution JSON payload is invalid") from error
    if not isinstance(candidates, list) or not isinstance(summary, dict):
        raise WithinReleaseResolutionError("resolution JSON schema is invalid")
    keys = [_validate_candidate(row, thresholds) for row in candidates]
    if keys != sorted(set(keys)):
        raise WithinReleaseResolutionError("resolution candidates are not sorted and unique")
    input_ids = {value["release_id"] for value in inputs if not value["review_only"]}
    if any(row["release_id"] not in input_ids for row in candidates):
        raise WithinReleaseResolutionError(
            "resolution candidate references an excluded or unknown release"
        )
    expected_summary = _summary(candidates, inputs)
    if summary != expected_summary or manifest.get("counts") != expected_summary:
        raise WithinReleaseResolutionError("resolution counts do not reconcile")
    if summary["unique_physical_sites"] is not None:
        raise WithinReleaseResolutionError(
            "resolution bundle must not count unique physical sites"
        )
    expected_csv = _candidate_csv(candidates)
    if (directory / CANDIDATES_CSV_FILENAME).read_bytes() != expected_csv:
        raise WithinReleaseResolutionError("resolution CSV and JSON rows differ")

    if definition_path is not None:
        definition = _load_definition(definition_path)
        if definition_record != {
            "file": definition.path.name,
            **_checkpoint(definition.raw),
        }:
            raise WithinReleaseResolutionError(
                "resolution definition checkpoint does not match"
            )
        if verify_inputs:
            expected_payloads, expected_manifest, _ = _prepare_bundle(definition)
            actual_payloads = {
                item.name: item.read_bytes() for item in directory.iterdir()
            }
            if actual_payloads != expected_payloads or manifest != expected_manifest:
                raise WithinReleaseResolutionError(
                    "resolution exact-input rebuild differs from the bundle"
                )
    elif verify_inputs:
        raise WithinReleaseResolutionError(
            "verify_inputs requires the original definition"
        )
    return manifest


def _write_bytes(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_within_release_resolution(
    definition_path: str | Path, output_directory: str | Path
) -> dict[str, Any]:
    """Build and atomically publish one immutable resolution-candidate bundle."""

    definition = _load_definition(definition_path)
    payloads, manifest, inspected_releases = _prepare_bundle(definition)
    output = Path(os.path.abspath(os.fspath(output_directory)))
    if output.is_symlink():
        raise WithinReleaseResolutionError("resolution output may not be a symlink")
    if output.exists():
        if not output.is_dir():
            raise WithinReleaseResolutionError("resolution output is not a directory")
        validate_within_release_resolution(output)
        differing = [
            name
            for name, raw in payloads.items()
            if (output / name).read_bytes() != raw
        ]
        if differing:
            raise WithinReleaseResolutionError(
                "existing resolution bundle is valid but not byte-identical; "
                f"refusing to replace: {sorted(differing)}"
            )
        return manifest

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.parent.is_symlink() or not output.parent.is_dir() or not output.name:
        raise WithinReleaseResolutionError("resolution output parent is invalid")
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    try:
        for name, raw in payloads.items():
            _write_bytes(stage / name, raw)
        validate_within_release_resolution(stage)
        # Re-run complete release and federation validation after candidate generation
        # so publication fails closed if any input changed mid-build.
        rechecked = [_inspect_release(item) for item in definition.releases]
        if [item["manifest_checkpoint"] for item in rechecked] != [
            item["manifest_checkpoint"] for item in inspected_releases
        ] or [item["atlas_geojson_checkpoint"] for item in rechecked] != [
            item["atlas_geojson_checkpoint"] for item in inspected_releases
        ]:
            raise WithinReleaseResolutionError(
                "release input changed while resolution candidates were built"
            )
        if _federation_input(definition, rechecked) != manifest["federated_input"]:
            raise WithinReleaseResolutionError(
                "federated input changed while resolution candidates were built"
            )
        if output.exists() or output.is_symlink():
            raise WithinReleaseResolutionError(
                "resolution output appeared during publication"
            )
        os.rename(stage, output)
        _fsync_directory(output.parent)
    except Exception:
        if stage.exists() and stage.is_dir() and not stage.is_symlink():
            shutil.rmtree(stage)
        raise
    return manifest


build_within_release_resolution = write_within_release_resolution


__all__ = [
    "BUNDLE_FORMAT",
    "DEFINITION_FORMAT",
    "POLICY",
    "WithinReleaseResolutionError",
    "WithinReleaseThresholds",
    "build_within_release_resolution",
    "generate_within_release_candidates",
    "validate_within_release_resolution",
    "write_within_release_resolution",
]
