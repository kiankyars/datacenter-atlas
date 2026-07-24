"""Immutable exact-identity decisions over a hash-pinned federation.

This lane publishes only deterministic source-record equivalence and explicit
typed topology.  Spatial proximity, names, addresses, coordinates, geometry,
and candidate scores remain manual-review signals and never create components.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import tempfile
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote

from .federated_release import (
    FederatedReleaseError,
    validate_federated_release_index,
)
from .global_snapshot import GlobalSnapshotError, validate_release_files


SCHEMA_VERSION = 1
DEFINITION_FORMAT = "datacenter-atlas-exact-identity-decision-definition-v1"
BUNDLE_FORMAT = "datacenter-atlas-exact-identity-decision-bundle-v1"
FEDERATED_INDEX_FORMAT = "datacenter-atlas-federated-release-index-v1"

MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
COMPONENTS_FILENAME = "component-members.csv"
RELATIONSHIPS_FILENAME = "relationships.csv"
UNRESOLVED_FILENAME = "unresolved-candidate-references.csv"
LINEAGE_FILENAME = "source-lineage.csv"
ACCOUNTING_FILENAME = "accounting.json"
README_FILENAME = "README.md"
ATTRIBUTION_FILENAME = "ATTRIBUTION.txt"

BUNDLE_FILES = frozenset(
    {
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
        COMPONENTS_FILENAME,
        RELATIONSHIPS_FILENAME,
        UNRESOLVED_FILENAME,
        LINEAGE_FILENAME,
        ACCOUNTING_FILENAME,
        README_FILENAME,
        ATTRIBUTION_FILENAME,
    }
)

POLICY = {
    "automatic_physical_site_merges": False,
    "cross_kind_identity_union": False,
    "exact_same_kind_source_record_components": True,
    "explicit_topology_only": True,
    "manual_candidate_signals": [
        "address",
        "coordinate",
        "distance",
        "geometry",
        "name",
        "owner_operator",
        "score",
    ],
    "physical_site_lower_bound": None,
    "physical_site_upper_bound": None,
    "review_only_rows_in_public_accounting": False,
    "source_family_difference_proves_independence": False,
    "unique_physical_sites": None,
}

ENTITY_KINDS = frozenset({"campus", "facility", "building", "project"})
RIGHTS_INELIGIBLE_SOURCE_ROOTS = frozenset({"peeringdb", "scrutica"})

COMPONENT_FIELDS = (
    "component_id",
    "occurrence_id",
    "release_id",
    "entity_id",
    "entity_kind",
    "stable_key",
    "source_family",
    "source_root",
    "snapshot_evidence_id",
    "component_member_count",
    "identity_proof_parent_occurrence_id",
    "identity_proof_token",
    "typed_identity_tokens_json",
    "ambiguous_identity_tokens_json",
)

RELATIONSHIP_FIELDS = (
    "relationship_id",
    "relationship_type",
    "subject_component_id",
    "subject_kind",
    "object_component_id",
    "object_kind",
    "decision_basis",
    "typed_identity_tokens_json",
    "source_release_ids_json",
    "raw_relationship_count",
)

UNRESOLVED_FIELDS = (
    "candidate_reference_id",
    "origin",
    "release_id",
    "left_occurrence_id",
    "right_occurrence_id",
    "relationship_suggestion",
    "disposition",
    "reason",
    "typed_identity_token",
    "source_artifact",
    "source_sha256",
)

LINEAGE_FIELDS = (
    "release_id",
    "source_family",
    "source_root",
    "publisher_roots_json",
    "occurrence_count",
    "exact_component_count",
    "derivation_status",
    "independence_claim_allowed",
)

RELATIONSHIP_KIND_PAIRS = {
    "campus_contains_facility": ("campus", "facility"),
    "facility_contains_building": ("facility", "building"),
}

_OSM_STABLE_RE = re.compile(r"^osm:(node|way|relation)/(\d+)(?::|$)", re.I)
_WIKIDATA_STABLE_RE = re.compile(r"^wikidata:(Q\d+)(?::|$)", re.I)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PUBLISHER_RE = re.compile(r"[^a-z0-9]+")


class ExactIdentityDecisionError(ValueError):
    """Raised when an exact-identity input or output fails closed."""


@dataclass(frozen=True, slots=True)
class _Definition:
    path: Path
    raw: bytes
    bundle_id: str
    recorded_at: str
    federation: Mapping[str, Any]
    children: tuple[Mapping[str, Any], ...]
    expected: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class _Identity:
    token: str
    basis: str
    ambiguous: bool = False


@dataclass(frozen=True, slots=True)
class _Occurrence:
    occurrence_id: str
    release_id: str
    entity_id: str
    kind: str
    stable_key: str
    source_family: str
    source_root: str
    publisher_root: str
    snapshot_evidence_id: str
    tags: Mapping[str, Any]
    identities: tuple[_Identity, ...]


@dataclass(frozen=True, slots=True)
class _RawRelationship:
    release_id: str
    relationship_type: str
    subject_occurrence_id: str
    object_occurrence_id: str


@dataclass(frozen=True, slots=True)
class _Child:
    release_id: str
    directory: Path
    manifest: Mapping[str, Any]
    manifest_checkpoint: Mapping[str, Any]
    review_only: bool
    disposition: str
    federation_descriptor: Mapping[str, Any]


class _UnionFind:
    def __init__(self, values: Iterable[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> tuple[bool, str, str]:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return False, left_root, right_root
        parent, child = sorted((left_root, right_root))
        self.parent[child] = parent
        return True, parent, child


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _compact_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _checkpoint(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def _require_checkpoint(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"bytes", "sha256"}:
        raise ExactIdentityDecisionError(f"{label} checkpoint is invalid")
    size = value.get("bytes")
    digest = value.get("sha256")
    if (
        isinstance(size, bool)
        or not isinstance(size, int)
        or size < 0
        or not isinstance(digest, str)
        or not _SHA256_RE.fullmatch(digest)
    ):
        raise ExactIdentityDecisionError(f"{label} checkpoint is invalid")
    return {"bytes": size, "sha256": digest}


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ExactIdentityDecisionError(f"{label} must be non-empty canonical text")
    return value


def _timestamp(value: Any, label: str) -> str:
    text = _text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ExactIdentityDecisionError(f"{label} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExactIdentityDecisionError(f"{label} must include a timezone")
    canonical = (
        parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    if canonical != text:
        raise ExactIdentityDecisionError(
            f"{label} must use canonical UTC whole seconds"
        )
    return text


def _json_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise ExactIdentityDecisionError(f"{label} must be a regular file")
    raw = path.read_bytes()
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExactIdentityDecisionError(f"{label} must be valid JSON") from error
    if not isinstance(document, dict):
        raise ExactIdentityDecisionError(f"{label} must contain an object")
    return document, raw


def _resolve(definition_path: Path, value: Any, label: str) -> Path:
    text = _text(value, label)
    path = Path(text)
    if path.is_absolute():
        raise ExactIdentityDecisionError(f"{label} must be relative")
    return (definition_path.parent / path).resolve()


def _load_definition(path_value: str | Path) -> _Definition:
    path = Path(path_value)
    document, raw = _json_object(path, "decision definition")
    if raw != _canonical_json(document):
        raise ExactIdentityDecisionError("decision definition is not canonical JSON")
    if set(document) != {
        "schema_version",
        "format",
        "bundle_id",
        "recorded_at",
        "federation",
        "children",
        "expected",
    }:
        raise ExactIdentityDecisionError("decision definition schema is invalid")
    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("format") != DEFINITION_FORMAT
    ):
        raise ExactIdentityDecisionError("decision definition format is unsupported")
    bundle_id = _text(document.get("bundle_id"), "decision bundle_id")
    recorded_at = _timestamp(document.get("recorded_at"), "decision recorded_at")
    parsed_recorded_at = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
    if parsed_recorded_at > datetime.now(UTC):
        raise ExactIdentityDecisionError("decision recorded_at must be in the past")

    federation = document.get("federation")
    if not isinstance(federation, Mapping) or set(federation) != {
        "index_path",
        "expected_manifest_sha256",
        "expected_index_sha256",
    }:
        raise ExactIdentityDecisionError("decision federation schema is invalid")
    _resolve(path, federation.get("index_path"), "federation index_path")
    for key in ("expected_manifest_sha256", "expected_index_sha256"):
        value = federation.get(key)
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise ExactIdentityDecisionError(f"federation {key} is invalid")

    children_value = document.get("children")
    if not isinstance(children_value, list) or not children_value:
        raise ExactIdentityDecisionError("decision children must be non-empty")
    children: list[dict[str, Any]] = []
    release_ids: set[str] = set()
    resolved_paths: set[Path] = set()
    for index, raw_child in enumerate(children_value):
        label = f"decision child {index}"
        if not isinstance(raw_child, Mapping) or set(raw_child) != {
            "release_id",
            "release_path",
            "expected_manifest_sha256",
            "expected_review_only",
        }:
            raise ExactIdentityDecisionError(f"{label} schema is invalid")
        release_id = _text(raw_child.get("release_id"), f"{label} release_id")
        release_path = _resolve(path, raw_child.get("release_path"), f"{label} path")
        digest = raw_child.get("expected_manifest_sha256")
        review_only = raw_child.get("expected_review_only")
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            raise ExactIdentityDecisionError(f"{label} manifest digest is invalid")
        if not isinstance(review_only, bool):
            raise ExactIdentityDecisionError(f"{label} review scope is invalid")
        if release_id in release_ids or release_path in resolved_paths:
            raise ExactIdentityDecisionError("decision children must be unique")
        release_ids.add(release_id)
        resolved_paths.add(release_path)
        children.append(
            {
                "release_id": release_id,
                "release_path": release_path,
                "expected_manifest_sha256": digest,
                "expected_review_only": review_only,
            }
        )

    expected = document.get("expected")
    expected_keys = {
        "source_scoped_entity_records",
        "non_review_source_scoped_entity_records",
        "review_only_source_scoped_entity_records",
        "exact_source_record_components",
        "exact_component_reductions",
        "raw_topology_links",
        "canonical_topology_links",
        "release_candidate_references",
        "ambiguous_identity_candidate_references",
        "unresolved_candidate_references",
    }
    if not isinstance(expected, Mapping) or set(expected) != expected_keys:
        raise ExactIdentityDecisionError("decision expected counts schema is invalid")
    for key in expected_keys:
        value = expected.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ExactIdentityDecisionError(f"expected {key} is invalid")

    return _Definition(
        path=path.resolve(),
        raw=raw,
        bundle_id=bundle_id,
        recorded_at=recorded_at,
        federation=dict(federation),
        children=tuple(sorted(children, key=lambda item: item["release_id"])),
        expected=dict(expected),
    )


def _source_root(source_family: str) -> str:
    normalized = source_family.casefold()
    if normalized == "openstreetmap" or normalized.startswith(
        ("openstreetmap:", "openstreetmap_")
    ):
        return "openstreetmap"
    aliases = {
        "ada_infrastructure_location_pages": "ada_infrastructure",
        "ada_infrastructure_press_releases": "ada_infrastructure",
        "crusoe_newsroom": "crusoe",
        "edgeconnex_press_releases": "edgeconnex",
    }
    return aliases.get(normalized, normalized)


def _publisher_root(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "unknown"
    return _PUBLISHER_RE.sub("_", value.casefold()).strip("_") or "unknown"


def _identity_tokens(
    *, stable_key: str, source_family: str, tags: Mapping[str, Any]
) -> tuple[_Identity, ...]:
    identities: dict[tuple[str, bool], str] = {}
    osm = _OSM_STABLE_RE.match(stable_key)
    if osm:
        identities[
            (f"openstreetmap:{osm.group(1).casefold()}/{osm.group(2)}", False)
        ] = "osm_stable_key"
    wikidata = _WIKIDATA_STABLE_RE.match(stable_key)
    if wikidata:
        identities[(f"wikidata:{wikidata.group(1).upper()}", False)] = (
            "wikidata_stable_key"
        )
    source_record_id = tags.get("source_record_id")
    if isinstance(source_record_id, str) and source_record_id.strip():
        identities[(f"{source_family}:record/{source_record_id.strip()}", False)] = (
            "typed_source_record_id"
        )

    if source_family == "openstreetmap:pnnl_im3":
        version = tags.get("pnnl_im3:dataset_version")
        source_type = tags.get("pnnl_im3:source_type")
        source_id = tags.get("pnnl_im3:source_id")
        if all(
            isinstance(value, str) and value.strip()
            for value in (version, source_type, source_id)
        ):
            version_text = str(version).strip()
            type_text = str(source_type).strip().casefold()
            id_text = str(source_id).strip()
            identities[
                (
                    f"openstreetmap:pnnl_im3:{version_text}:{type_text}/{id_text}",
                    False,
                )
            ] = "pnnl_im3_typed_dataset_record"
            if id_text.isdigit():
                normalized_id = str(int(id_text))
                if type_text == "point":
                    identities[(f"openstreetmap:node/{normalized_id}", False)] = (
                        "pnnl_im3_osm_numeric_source_id"
                    )
                elif type_text == "building":
                    identities[(f"openstreetmap:way/{normalized_id}", False)] = (
                        "pnnl_im3_osm_numeric_source_id"
                    )
                elif type_text == "campus":
                    for osm_type in ("relation", "way"):
                        identities[
                            (f"openstreetmap:{osm_type}/{normalized_id}", True)
                        ] = "pnnl_im3_ambiguous_osm_numeric_source_id"
    return tuple(
        _Identity(token=token, basis=basis, ambiguous=ambiguous)
        for (token, ambiguous), basis in sorted(identities.items())
    )


def _federation_input(definition: _Definition) -> tuple[dict[str, Any], dict[str, Any]]:
    directory = _resolve(
        definition.path,
        definition.federation["index_path"],
        "federation index_path",
    )
    try:
        index = validate_federated_release_index(directory)
    except (FederatedReleaseError, OSError) as error:
        raise ExactIdentityDecisionError(
            f"federated index validation failed: {error}"
        ) from error
    manifest_checkpoint = _checkpoint(directory / MANIFEST_FILENAME)
    index_checkpoint = _checkpoint(directory / "federated-index.json")
    if (
        manifest_checkpoint["sha256"]
        != definition.federation["expected_manifest_sha256"]
        or index_checkpoint["sha256"] != definition.federation["expected_index_sha256"]
    ):
        raise ExactIdentityDecisionError("federated index hash drifted")
    if index.get("format") != FEDERATED_INDEX_FORMAT:
        raise ExactIdentityDecisionError("federated index format is unsupported")
    return index, {
        "directory_name": directory.name,
        "manifest": manifest_checkpoint,
        "federated_index": index_checkpoint,
    }


def _inspect_children(
    definition: _Definition, index: Mapping[str, Any]
) -> list[_Child]:
    descriptors = index.get("releases")
    if not isinstance(descriptors, list):
        raise ExactIdentityDecisionError("federated release descriptors are invalid")
    by_id = {
        str(item.get("release_id")): item
        for item in descriptors
        if isinstance(item, Mapping)
    }
    definition_ids = {str(item["release_id"]) for item in definition.children}
    if set(by_id) != definition_ids:
        raise ExactIdentityDecisionError(
            "decision children do not exactly match the federation"
        )

    children: list[_Child] = []
    for value in definition.children:
        release_id = str(value["release_id"])
        directory = Path(value["release_path"])
        try:
            manifest = validate_release_files(directory)
        except (GlobalSnapshotError, OSError) as error:
            raise ExactIdentityDecisionError(
                f"child release validation failed for {release_id}: {error}"
            ) from error
        manifest_checkpoint = _checkpoint(directory / MANIFEST_FILENAME)
        if manifest_checkpoint["sha256"] != value["expected_manifest_sha256"]:
            raise ExactIdentityDecisionError(
                f"child manifest hash drifted: {release_id}"
            )
        descriptor = by_id[release_id]
        descriptor_manifest = descriptor.get("manifest")
        if (
            not isinstance(descriptor_manifest, Mapping)
            or descriptor_manifest.get("sha256") != manifest_checkpoint["sha256"]
            or descriptor.get("files") != manifest.get("files")
        ):
            raise ExactIdentityDecisionError(
                f"child hashes do not match federation descriptor: {release_id}"
            )
        scope = descriptor.get("scope")
        review_only = manifest.get("review_only", False)
        if (
            not isinstance(scope, Mapping)
            or not isinstance(review_only, bool)
            or scope.get("review_only") is not review_only
            or value["expected_review_only"] is not review_only
        ):
            raise ExactIdentityDecisionError(
                f"child review scope does not reconcile: {release_id}"
            )
        child_recorded_at = _timestamp(
            manifest.get("recorded_at"), f"{release_id} recorded_at"
        )
        if child_recorded_at >= definition.recorded_at:
            raise ExactIdentityDecisionError(
                f"decision recorded_at must follow child release: {release_id}"
            )
        children.append(
            _Child(
                release_id=release_id,
                directory=directory,
                manifest=manifest,
                manifest_checkpoint=manifest_checkpoint,
                review_only=review_only,
                disposition="excluded_review_only" if review_only else "processed",
                federation_descriptor=descriptor,
            )
        )
    return sorted(children, key=lambda item: item.release_id)


def _load_occurrences(child: _Child) -> list[_Occurrence]:
    path = child.directory / "atlas.geojson"
    document, _ = _json_object(path, f"{child.release_id} atlas.geojson")
    if document.get("type") != "FeatureCollection":
        raise ExactIdentityDecisionError("child atlas must be a FeatureCollection")
    features = document.get("features")
    expected_count = child.manifest.get("entities")
    if not isinstance(features, list) or len(features) != expected_count:
        raise ExactIdentityDecisionError(
            f"child atlas entity count does not reconcile: {child.release_id}"
        )
    occurrences: list[_Occurrence] = []
    seen: set[str] = set()
    for position, feature in enumerate(features):
        if not isinstance(feature, Mapping) or not isinstance(
            feature.get("properties"), Mapping
        ):
            raise ExactIdentityDecisionError(
                f"child atlas feature is invalid: {child.release_id} #{position}"
            )
        properties = feature["properties"]
        entity_id = _text(properties.get("entity_id"), "feature entity_id")
        if feature.get("id") != entity_id or entity_id in seen:
            raise ExactIdentityDecisionError("child atlas entity IDs are invalid")
        seen.add(entity_id)
        kind = _text(properties.get("entity_kind"), "feature entity_kind")
        if kind not in ENTITY_KINDS:
            raise ExactIdentityDecisionError("child atlas entity kind is unsupported")
        stable_key = _text(properties.get("stable_key"), "feature stable_key")
        source_family = _text(properties.get("source_family"), "feature source_family")
        source_root = _source_root(source_family)
        if source_root in RIGHTS_INELIGIBLE_SOURCE_ROOTS:
            raise ExactIdentityDecisionError(
                f"rights-ineligible source root in processed child: {source_root}"
            )
        tags = properties.get("tags") or {}
        if not isinstance(tags, Mapping):
            raise ExactIdentityDecisionError("feature tags must be an object")
        evidence_id = _text(
            properties.get("snapshot_evidence_id"), "feature snapshot evidence_id"
        )
        occurrence_id = f"{child.release_id}:{entity_id}"
        occurrences.append(
            _Occurrence(
                occurrence_id=occurrence_id,
                release_id=child.release_id,
                entity_id=entity_id,
                kind=kind,
                stable_key=stable_key,
                source_family=source_family,
                source_root=source_root,
                publisher_root=_publisher_root(properties.get("source_publisher")),
                snapshot_evidence_id=evidence_id,
                tags=dict(tags),
                identities=_identity_tokens(
                    stable_key=stable_key,
                    source_family=source_family,
                    tags=tags,
                ),
            )
        )
    return sorted(occurrences, key=lambda item: item.occurrence_id)


def _read_only_connection(path: Path) -> sqlite3.Connection:
    if path.is_symlink() or not path.is_file():
        raise ExactIdentityDecisionError("atlas.sqlite must be a regular file")
    uri = f"file:{quote(str(path.resolve()), safe='/')}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _raw_relationships(
    child: _Child, occurrences: Sequence[_Occurrence]
) -> list[_RawRelationship]:
    by_entity = {item.entity_id: item for item in occurrences}
    relationships: list[_RawRelationship] = []
    sqlite_path = child.directory / "atlas.sqlite"
    has_sqlite = "atlas.sqlite" in child.manifest.get("files", {})
    if has_sqlite:
        connection = _read_only_connection(sqlite_path)
        try:
            for row in connection.execute(
                "SELECT entity_id, campus_id FROM facilities "
                "WHERE campus_id IS NOT NULL ORDER BY entity_id"
            ):
                facility = str(row["entity_id"])
                campus = str(row["campus_id"])
                relationships.append(
                    _RawRelationship(
                        child.release_id,
                        "campus_contains_facility",
                        f"{child.release_id}:{campus}",
                        f"{child.release_id}:{facility}",
                    )
                )
            for row in connection.execute(
                "SELECT entity_id, facility_id FROM buildings ORDER BY entity_id"
            ):
                building = str(row["entity_id"])
                facility = str(row["facility_id"])
                relationships.append(
                    _RawRelationship(
                        child.release_id,
                        "facility_contains_building",
                        f"{child.release_id}:{facility}",
                        f"{child.release_id}:{building}",
                    )
                )
        finally:
            connection.close()
    elif any(item.kind in {"facility", "building"} for item in occurrences):
        raise ExactIdentityDecisionError(
            f"child with facility/building rows lacks atlas.sqlite: {child.release_id}"
        )

    geojson, _ = _json_object(
        child.directory / "atlas.geojson", f"{child.release_id} atlas.geojson"
    )
    for feature in geojson["features"]:
        properties = feature["properties"]
        if properties["entity_kind"] != "project":
            continue
        project = str(properties["entity_id"])
        target = properties.get("target_entity_id")
        if not isinstance(target, str) or target not in by_entity:
            raise ExactIdentityDecisionError(
                f"project target is absent from child: {child.release_id}:{project}"
            )
        relationships.append(
            _RawRelationship(
                child.release_id,
                "project_targets",
                f"{child.release_id}:{project}",
                f"{child.release_id}:{target}",
            )
        )
    keys = [
        (
            item.release_id,
            item.relationship_type,
            item.subject_occurrence_id,
            item.object_occurrence_id,
        )
        for item in relationships
    ]
    if len(keys) != len(set(keys)):
        raise ExactIdentityDecisionError("raw child relationships are duplicated")
    return sorted(
        relationships,
        key=lambda item: (
            item.release_id,
            item.relationship_type,
            item.subject_occurrence_id,
            item.object_occurrence_id,
        ),
    )


def _component_id(kind: str, members: Sequence[str]) -> str:
    payload = "\x1f".join(("exact-component-v1", kind, *sorted(members))).encode()
    return f"exact:{hashlib.sha256(payload).hexdigest()}"


def _candidate_id(*parts: str) -> str:
    return f"candidate:{hashlib.sha256(chr(31).join(parts).encode()).hexdigest()}"


def _relationship_id(
    relationship_type: str, subject_component_id: str, object_component_id: str
) -> str:
    payload = "\x1f".join(
        (
            "exact-relationship-v1",
            relationship_type,
            subject_component_id,
            object_component_id,
        )
    ).encode()
    return f"relationship:{hashlib.sha256(payload).hexdigest()}"


def _build_components(
    occurrences: Sequence[_Occurrence],
) -> tuple[
    list[dict[str, Any]],
    dict[str, str],
    list[dict[str, Any]],
    dict[str, set[str]],
]:
    by_id = {item.occurrence_id: item for item in occurrences}
    union = _UnionFind(by_id)
    token_members: dict[str, list[_Occurrence]] = defaultdict(list)
    ambiguous_members: dict[str, list[_Occurrence]] = defaultdict(list)
    for occurrence in occurrences:
        for identity in occurrence.identities:
            target = ambiguous_members if identity.ambiguous else token_members
            target[identity.token].append(occurrence)

    proof_parent: dict[str, tuple[str, str]] = {}
    for token, members in sorted(token_members.items()):
        by_kind: dict[str, list[_Occurrence]] = defaultdict(list)
        for member in members:
            by_kind[member.kind].append(member)
        for kind, kind_members in sorted(by_kind.items()):
            roots = {item.source_root for item in kind_members}
            if len(kind_members) > 1 and len(roots) != 1:
                raise ExactIdentityDecisionError(
                    f"exact identity crosses source roots: {token} {kind}"
                )
            ordered = sorted(kind_members, key=lambda item: item.occurrence_id)
            for left, right in zip(ordered, ordered[1:], strict=False):
                changed, parent, child = union.union(
                    left.occurrence_id, right.occurrence_id
                )
                if changed:
                    proof_parent[child] = (parent, token)

    root_members: dict[str, list[str]] = defaultdict(list)
    for occurrence_id in sorted(by_id):
        root_members[union.find(occurrence_id)].append(occurrence_id)
    component_for: dict[str, str] = {}
    component_tokens: dict[str, set[str]] = defaultdict(set)
    for members in root_members.values():
        kinds = {by_id[item].kind for item in members}
        if len(kinds) != 1:
            raise ExactIdentityDecisionError("exact component crosses entity kinds")
        kind = next(iter(kinds))
        component = _component_id(kind, members)
        for member in members:
            component_for[member] = component
            component_tokens[component].update(
                identity.token
                for identity in by_id[member].identities
                if not identity.ambiguous
            )

    rows: list[dict[str, Any]] = []
    member_counts = Counter(component_for.values())
    for occurrence in sorted(occurrences, key=lambda item: item.occurrence_id):
        proof = proof_parent.get(occurrence.occurrence_id)
        rows.append(
            {
                "component_id": component_for[occurrence.occurrence_id],
                "occurrence_id": occurrence.occurrence_id,
                "release_id": occurrence.release_id,
                "entity_id": occurrence.entity_id,
                "entity_kind": occurrence.kind,
                "stable_key": occurrence.stable_key,
                "source_family": occurrence.source_family,
                "source_root": occurrence.source_root,
                "snapshot_evidence_id": occurrence.snapshot_evidence_id,
                "component_member_count": member_counts[
                    component_for[occurrence.occurrence_id]
                ],
                "identity_proof_parent_occurrence_id": proof[0] if proof else "",
                "identity_proof_token": proof[1] if proof else "",
                "typed_identity_tokens_json": _compact_json(
                    sorted(
                        identity.token
                        for identity in occurrence.identities
                        if not identity.ambiguous
                    )
                ),
                "ambiguous_identity_tokens_json": _compact_json(
                    sorted(
                        identity.token
                        for identity in occurrence.identities
                        if identity.ambiguous
                    )
                ),
            }
        )

    ambiguous_candidates: list[dict[str, Any]] = []
    for token, ambiguous in sorted(ambiguous_members.items()):
        exact = token_members.get(token, [])
        for left in sorted(ambiguous, key=lambda item: item.occurrence_id):
            for right in sorted(exact, key=lambda item: item.occurrence_id):
                if left.occurrence_id == right.occurrence_id:
                    continue
                left_id, right_id = sorted((left.occurrence_id, right.occurrence_id))
                ambiguous_candidates.append(
                    {
                        "candidate_reference_id": _candidate_id(
                            "ambiguous-identity", token, left_id, right_id
                        ),
                        "origin": "ambiguous_typed_identity",
                        "release_id": left.release_id,
                        "left_occurrence_id": left_id,
                        "right_occurrence_id": right_id,
                        "relationship_suggestion": (
                            "same_upstream_record_cross_kind_candidate"
                            if by_id[left_id].kind != by_id[right_id].kind
                            else "same_upstream_record_candidate"
                        ),
                        "disposition": "manual_only",
                        "reason": "ambiguous_pnnl_campus_osm_object_type",
                        "typed_identity_token": token,
                        "source_artifact": "atlas.geojson",
                        "source_sha256": "",
                    }
                )
    keys = [item["candidate_reference_id"] for item in ambiguous_candidates]
    if len(keys) != len(set(keys)):
        raise ExactIdentityDecisionError("ambiguous identity candidates collide")
    return rows, component_for, ambiguous_candidates, component_tokens


def _component_cross_kind_tokens(
    component_tokens: Mapping[str, set[str]], left: str, right: str
) -> list[str]:
    return sorted(
        component_tokens.get(left, set()) & component_tokens.get(right, set())
    )


def _build_relationships(
    occurrences: Sequence[_Occurrence],
    component_for: Mapping[str, str],
    raw_relationships: Sequence[_RawRelationship],
    component_tokens: Mapping[str, set[str]],
) -> list[dict[str, Any]]:
    by_id = {item.occurrence_id: item for item in occurrences}
    grouped: dict[tuple[str, str, str], list[_RawRelationship]] = defaultdict(list)
    for relationship in raw_relationships:
        if (
            relationship.subject_occurrence_id not in by_id
            or relationship.object_occurrence_id not in by_id
        ):
            raise ExactIdentityDecisionError(
                "relationship references unknown occurrence"
            )
        subject = by_id[relationship.subject_occurrence_id]
        object_ = by_id[relationship.object_occurrence_id]
        if relationship.relationship_type in RELATIONSHIP_KIND_PAIRS:
            if (
                subject.kind,
                object_.kind,
            ) != RELATIONSHIP_KIND_PAIRS[relationship.relationship_type]:
                raise ExactIdentityDecisionError(
                    "containment relationship kinds are invalid"
                )
        elif relationship.relationship_type == "project_targets":
            if subject.kind != "project" or object_.kind == "project":
                raise ExactIdentityDecisionError(
                    "project target relationship is invalid"
                )
        else:
            raise ExactIdentityDecisionError("relationship type is unsupported")
        subject_component = component_for[subject.occurrence_id]
        object_component = component_for[object_.occurrence_id]
        if subject_component == object_component:
            raise ExactIdentityDecisionError("topology relationship became a self-loop")
        grouped[
            (
                relationship.relationship_type,
                subject_component,
                object_component,
            )
        ].append(relationship)

    rows: list[dict[str, Any]] = []
    for (relationship_type, subject, object_), members in sorted(grouped.items()):
        subject_kind = by_id[members[0].subject_occurrence_id].kind
        object_kind = by_id[members[0].object_occurrence_id].kind
        tokens = _component_cross_kind_tokens(component_tokens, subject, object_)
        rows.append(
            {
                "relationship_id": _relationship_id(
                    relationship_type, subject, object_
                ),
                "relationship_type": relationship_type,
                "subject_component_id": subject,
                "subject_kind": subject_kind,
                "object_component_id": object_,
                "object_kind": object_kind,
                "decision_basis": (
                    "explicit_parent_and_exact_typed_identity"
                    if tokens
                    else "explicit_parent"
                ),
                "typed_identity_tokens_json": _compact_json(tokens),
                "source_release_ids_json": _compact_json(
                    sorted({item.release_id for item in members})
                ),
                "raw_relationship_count": len(members),
            }
        )

    # Cross-kind representations stay as distinct components. For each exact
    # token, the explicit typed parent/target edges must connect every involved
    # component; redundant transitive edges are neither inferred nor emitted.
    token_components: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for occurrence in occurrences:
        component = component_for[occurrence.occurrence_id]
        for identity in occurrence.identities:
            if not identity.ambiguous:
                token_components[identity.token][occurrence.kind].add(component)
    explicit_edges: dict[str, set[frozenset[str]]] = defaultdict(set)
    for row in rows:
        edge = frozenset((row["subject_component_id"], row["object_component_id"]))
        for token in json.loads(row["typed_identity_tokens_json"]):
            explicit_edges[token].add(edge)
    for token, kinds in token_components.items():
        if len(kinds) < 2:
            continue
        nodes = set().union(*kinds.values())
        seen = {min(nodes)}
        while True:
            reached = {
                member
                for edge in explicit_edges.get(token, set())
                if edge & seen
                for member in edge
            }
            expanded = seen | reached
            if expanded == seen:
                break
            seen = expanded
        if seen != nodes:
            raise ExactIdentityDecisionError(
                f"cross-kind exact identity lacks connected explicit topology: {token}"
            )
    return sorted(rows, key=lambda item: item["relationship_id"])


def _load_release_candidates(
    child: _Child, occurrences: Mapping[str, _Occurrence]
) -> list[dict[str, Any]]:
    path = child.directory / "resolution_candidates.json"
    checkpoint = _checkpoint(path)
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ExactIdentityDecisionError("resolution candidates are invalid") from error
    if not isinstance(rows, list):
        raise ExactIdentityDecisionError("resolution candidates must be an array")
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ExactIdentityDecisionError("resolution candidate row is invalid")
        left_entity = _text(row.get("left_entity_id"), "candidate left entity")
        right_entity = _text(row.get("right_entity_id"), "candidate right entity")
        left = f"{child.release_id}:{left_entity}"
        right = f"{child.release_id}:{right_entity}"
        if left not in occurrences or right not in occurrences or left == right:
            raise ExactIdentityDecisionError(
                "resolution candidate references unknown occurrences"
            )
        left, right = sorted((left, right))
        relationship = _text(
            row.get("relationship_suggestion"), "candidate relationship"
        )
        canonical = _compact_json(row)
        result.append(
            {
                "candidate_reference_id": _candidate_id(
                    "release-candidate", child.release_id, canonical
                ),
                "origin": "release_resolution_candidate",
                "release_id": child.release_id,
                "left_occurrence_id": left,
                "right_occurrence_id": right,
                "relationship_suggestion": relationship,
                "disposition": "manual_only",
                "reason": "spatial_semantic_signals_are_not_identity",
                "typed_identity_token": "",
                "source_artifact": "resolution_candidates.json",
                "source_sha256": checkpoint["sha256"],
            }
        )
    keys = [item["candidate_reference_id"] for item in result]
    if len(keys) != len(set(keys)):
        raise ExactIdentityDecisionError("release candidate references collide")
    return result


def _fill_ambiguous_source_hashes(
    rows: Sequence[dict[str, Any]], children: Mapping[str, _Child]
) -> None:
    for row in rows:
        if row["origin"] != "ambiguous_typed_identity":
            continue
        child = children[row["release_id"]]
        row["source_sha256"] = child.manifest["files"]["atlas.geojson"]["sha256"]


def _build_lineage(
    occurrences: Sequence[_Occurrence], component_for: Mapping[str, str]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[_Occurrence]] = defaultdict(list)
    for occurrence in occurrences:
        grouped[
            (
                occurrence.release_id,
                occurrence.source_family,
                occurrence.source_root,
            )
        ].append(occurrence)
    rows: list[dict[str, Any]] = []
    for (release_id, family, root), members in sorted(grouped.items()):
        rows.append(
            {
                "release_id": release_id,
                "source_family": family,
                "source_root": root,
                "publisher_roots_json": _compact_json(
                    sorted({item.publisher_root for item in members})
                ),
                "occurrence_count": len(members),
                "exact_component_count": len(
                    {component_for[item.occurrence_id] for item in members}
                ),
                "derivation_status": (
                    "shared_upstream_root"
                    if family.casefold() != root
                    else "direct_or_unclassified"
                ),
                "independence_claim_allowed": False,
            }
        )
    return rows


def _csv_bytes(fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        if set(row) != set(fields):
            raise ExactIdentityDecisionError("CSV row schema is invalid")
        writer.writerow({field: row[field] for field in fields})
    return stream.getvalue().encode("utf-8")


def _accounting(
    children: Sequence[_Child],
    occurrences: Sequence[_Occurrence],
    component_rows: Sequence[Mapping[str, Any]],
    relationships: Sequence[Mapping[str, Any]],
    raw_relationships: Sequence[_RawRelationship],
    unresolved: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    components = {str(row["component_id"]) for row in component_rows}
    component_kind = {
        str(row["component_id"]): str(row["entity_kind"]) for row in component_rows
    }
    raw_kind = Counter(item.kind for item in occurrences)
    exact_kind = Counter(component_kind.values())
    relationship_kind = Counter(
        str(item["relationship_type"]) for item in relationships
    )
    unresolved_origin = Counter(str(item["origin"]) for item in unresolved)
    source_rows = sum(int(child.manifest["entities"]) for child in children)
    excluded_rows = sum(
        int(child.manifest["entities"]) for child in children if child.review_only
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "unit": "source_scoped_release_occurrence",
        "source_scoped_entity_records": source_rows,
        "non_review_source_scoped_entity_records": len(occurrences),
        "review_only_source_scoped_entity_records": excluded_rows,
        "raw_non_review_occurrences_by_kind": dict(sorted(raw_kind.items())),
        "exact_source_record_components": len(components),
        "exact_source_record_components_by_kind": dict(sorted(exact_kind.items())),
        "exact_component_reductions": len(occurrences) - len(components),
        "raw_topology_links": len(raw_relationships),
        "canonical_topology_links": len(relationships),
        "canonical_topology_links_by_type": dict(sorted(relationship_kind.items())),
        "release_candidate_references": unresolved_origin.get(
            "release_resolution_candidate", 0
        ),
        "ambiguous_identity_candidate_references": unresolved_origin.get(
            "ambiguous_typed_identity", 0
        ),
        "unresolved_candidate_references": len(unresolved),
        "unique_physical_sites": None,
        "physical_site_lower_bound": None,
        "physical_site_upper_bound": None,
    }


def _readme(accounting: Mapping[str, Any]) -> bytes:
    text = (
        "# Exact identity decisions v1\n\n"
        "This immutable bundle deduplicates only unambiguous, same-kind typed "
        "upstream source records and publishes only explicit typed parent/target "
        "relationships. Cross-kind records remain separate components. Names, "
        "coordinates, distance, geometry, owner/operator similarity, and scores "
        "remain manual-only signals.\n\n"
        f"The {accounting['non_review_source_scoped_entity_records']:,} eligible "
        f"source-scoped rows form {accounting['exact_source_record_components']:,} "
        "exact source-record components. The bundle contains "
        f"{accounting['canonical_topology_links']:,} canonical explicit topology "
        "links and "
        f"{accounting['unresolved_candidate_references']:,} unresolved candidate "
        "references. These are not physical-site counts. Unique physical sites "
        "and both physical-site bounds remain null.\n"
    )
    return text.encode("utf-8")


def _attribution(children: Sequence[_Child]) -> bytes:
    parts = []
    for child in children:
        text = (child.directory / ATTRIBUTION_FILENAME).read_text(encoding="utf-8")
        rights = child.federation_descriptor.get("rights", {})
        parts.append(
            f"[{child.release_id}; {child.disposition}]\n"
            f"{text.rstrip()}\n"
            f"Rights: {rights.get('license_expression', 'see child release')}\n"
        )
    return ("\n".join(parts).rstrip() + "\n").encode("utf-8")


def _input_child_record(child: _Child) -> dict[str, Any]:
    files = child.manifest.get("files")
    if not isinstance(files, Mapping):
        raise ExactIdentityDecisionError("child files manifest is invalid")
    return {
        "release_id": child.release_id,
        "release_directory_name": child.directory.name,
        "review_only": child.review_only,
        "disposition": child.disposition,
        "source_scoped_entity_records": child.manifest["entities"],
        "recorded_at": child.manifest["recorded_at"],
        "manifest": dict(child.manifest_checkpoint),
        "files": {name: dict(record) for name, record in sorted(files.items())},
    }


def _prepare_bundle(
    definition: _Definition,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    index, federation_record = _federation_input(definition)
    children = _inspect_children(definition, index)
    processed = [child for child in children if not child.review_only]
    occurrences = [
        occurrence for child in processed for occurrence in _load_occurrences(child)
    ]
    occurrence_map = {item.occurrence_id: item for item in occurrences}
    if len(occurrence_map) != len(occurrences):
        raise ExactIdentityDecisionError("occurrence IDs collide across children")
    raw_relationships = [
        relationship
        for child in processed
        for relationship in _raw_relationships(
            child,
            [
                occurrence
                for occurrence in occurrences
                if occurrence.release_id == child.release_id
            ],
        )
    ]
    (
        component_rows,
        component_for,
        ambiguous_candidates,
        component_tokens,
    ) = _build_components(occurrences)
    relationships = _build_relationships(
        occurrences,
        component_for,
        raw_relationships,
        component_tokens,
    )
    release_candidates = [
        candidate
        for child in processed
        for candidate in _load_release_candidates(child, occurrence_map)
    ]
    by_child = {child.release_id: child for child in children}
    _fill_ambiguous_source_hashes(ambiguous_candidates, by_child)
    unresolved = sorted(
        [*release_candidates, *ambiguous_candidates],
        key=lambda item: item["candidate_reference_id"],
    )
    if len(unresolved) != len({item["candidate_reference_id"] for item in unresolved}):
        raise ExactIdentityDecisionError("unresolved candidate references collide")
    lineage = _build_lineage(occurrences, component_for)
    accounting = _accounting(
        children,
        occurrences,
        component_rows,
        relationships,
        raw_relationships,
        unresolved,
    )

    compared = {key: accounting[key] for key in definition.expected}
    expected = dict(definition.expected)
    if compared != expected:
        raise ExactIdentityDecisionError(
            f"decision counts diverged: expected {expected}, found {compared}"
        )
    if any(
        accounting[field] is not None
        for field in (
            "unique_physical_sites",
            "physical_site_lower_bound",
            "physical_site_upper_bound",
        )
    ):
        raise ExactIdentityDecisionError("physical-site accounting must remain null")

    payloads = {
        COMPONENTS_FILENAME: _csv_bytes(COMPONENT_FIELDS, component_rows),
        RELATIONSHIPS_FILENAME: _csv_bytes(RELATIONSHIP_FIELDS, relationships),
        UNRESOLVED_FILENAME: _csv_bytes(UNRESOLVED_FIELDS, unresolved),
        LINEAGE_FILENAME: _csv_bytes(LINEAGE_FIELDS, lineage),
        ACCOUNTING_FILENAME: _canonical_json(accounting),
        README_FILENAME: _readme(accounting),
        ATTRIBUTION_FILENAME: _attribution(children),
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "format": BUNDLE_FORMAT,
        "bundle_id": definition.bundle_id,
        "recorded_at": definition.recorded_at,
        "scope": POLICY,
        "definition": {
            "file": definition.path.name,
            "bytes": len(definition.raw),
            "sha256": _sha256_bytes(definition.raw),
        },
        "federation_input": federation_record,
        "input_children": [_input_child_record(child) for child in children],
        "counts": accounting,
        "files": {
            name: {"bytes": len(raw), "sha256": _sha256_bytes(raw)}
            for name, raw in sorted(payloads.items())
        },
    }
    manifest_raw = _canonical_json(manifest)
    payloads[MANIFEST_FILENAME] = manifest_raw
    payloads[MANIFEST_HASH_FILENAME] = (
        f"{_sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    return payloads, manifest


def _csv_rows(path: Path, fields: Sequence[str]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != list(fields):
            raise ExactIdentityDecisionError(f"CSV schema is invalid: {path.name}")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ExactIdentityDecisionError(f"CSV row width is invalid: {path.name}")
    return rows


def _validate_output_semantics(directory: Path, manifest: Mapping[str, Any]) -> None:
    accounting, raw = _json_object(
        directory / ACCOUNTING_FILENAME, "decision accounting"
    )
    if raw != _canonical_json(accounting):
        raise ExactIdentityDecisionError("decision accounting is not canonical JSON")
    if manifest.get("counts") != accounting:
        raise ExactIdentityDecisionError("manifest counts differ from accounting")
    if accounting.get("schema_version") != SCHEMA_VERSION:
        raise ExactIdentityDecisionError("accounting schema version is invalid")
    for field in (
        "unique_physical_sites",
        "physical_site_lower_bound",
        "physical_site_upper_bound",
    ):
        if accounting.get(field) is not None:
            raise ExactIdentityDecisionError("physical-site fields must remain null")

    input_children = manifest.get("input_children")
    if not isinstance(input_children, list) or not input_children:
        raise ExactIdentityDecisionError("input child lineage is invalid")
    child_ids = [
        child.get("release_id")
        for child in input_children
        if isinstance(child, Mapping)
    ]
    if len(child_ids) != len(input_children) or child_ids != sorted(set(child_ids)):
        raise ExactIdentityDecisionError("input child lineage is not sorted and unique")
    decision_time = datetime.fromisoformat(
        str(manifest["recorded_at"]).replace("Z", "+00:00")
    )
    total_child_rows = 0
    review_child_rows = 0
    for child in input_children:
        if set(child) != {
            "release_id",
            "release_directory_name",
            "review_only",
            "disposition",
            "source_scoped_entity_records",
            "recorded_at",
            "manifest",
            "files",
        }:
            raise ExactIdentityDecisionError("input child lineage schema is invalid")
        review_only = child["review_only"]
        child_rows = child["source_scoped_entity_records"]
        child_recorded_at = _timestamp(
            child["recorded_at"], f"{child['release_id']} input recorded_at"
        )
        if (
            not isinstance(review_only, bool)
            or isinstance(child_rows, bool)
            or not isinstance(child_rows, int)
            or child_rows < 0
            or child["disposition"]
            != ("excluded_review_only" if review_only else "processed")
            or datetime.fromisoformat(child_recorded_at.replace("Z", "+00:00"))
            >= decision_time
        ):
            raise ExactIdentityDecisionError("input child temporal scope is invalid")
        _text(child["release_id"], "input child release_id")
        _text(child["release_directory_name"], "input child directory")
        _require_checkpoint(child["manifest"], "input child manifest")
        child_files = child["files"]
        if not isinstance(child_files, Mapping) or not child_files:
            raise ExactIdentityDecisionError("input child files are invalid")
        for name, checkpoint in child_files.items():
            if not isinstance(name, str) or Path(name).name != name:
                raise ExactIdentityDecisionError("input child filename is invalid")
            _require_checkpoint(checkpoint, f"input child file {name}")
        total_child_rows += child_rows
        if review_only:
            review_child_rows += child_rows
    if (
        total_child_rows != accounting["source_scoped_entity_records"]
        or review_child_rows != accounting["review_only_source_scoped_entity_records"]
    ):
        raise ExactIdentityDecisionError("input child accounting does not reconcile")

    components = _csv_rows(directory / COMPONENTS_FILENAME, COMPONENT_FIELDS)
    occurrences = [row["occurrence_id"] for row in components]
    if occurrences != sorted(set(occurrences)):
        raise ExactIdentityDecisionError("component members are not sorted and unique")
    by_occurrence = {row["occurrence_id"]: row for row in components}
    component_members = Counter(row["component_id"] for row in components)
    if len(components) != accounting["non_review_source_scoped_entity_records"]:
        raise ExactIdentityDecisionError("component member count does not reconcile")
    if len(component_members) != accounting["exact_source_record_components"]:
        raise ExactIdentityDecisionError("component count does not reconcile")
    components_by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    component_tokens: dict[str, set[str]] = defaultdict(set)
    for row in components:
        if row["entity_kind"] not in ENTITY_KINDS:
            raise ExactIdentityDecisionError("component entity kind is invalid")
        if int(row["component_member_count"]) != component_members[row["component_id"]]:
            raise ExactIdentityDecisionError("component member cardinality is invalid")
        typed_tokens = json.loads(row["typed_identity_tokens_json"])
        ambiguous_tokens = json.loads(row["ambiguous_identity_tokens_json"])
        if (
            not isinstance(typed_tokens, list)
            or typed_tokens != sorted(set(typed_tokens))
            or not isinstance(ambiguous_tokens, list)
            or ambiguous_tokens != sorted(set(ambiguous_tokens))
            or set(typed_tokens) & set(ambiguous_tokens)
        ):
            raise ExactIdentityDecisionError("component identity tokens are invalid")
        components_by_id[row["component_id"]].append(row)
        component_tokens[row["component_id"]].update(typed_tokens)
    for component_id, members in components_by_id.items():
        kinds = {row["entity_kind"] for row in members}
        if len(kinds) != 1:
            raise ExactIdentityDecisionError("component crosses entity kinds")
        expected_component_id = _component_id(
            next(iter(kinds)), [row["occurrence_id"] for row in members]
        )
        if component_id != expected_component_id:
            raise ExactIdentityDecisionError("component identifier is invalid")
        parent_count = 0
        for row in members:
            parent_id = row["identity_proof_parent_occurrence_id"]
            proof_token = row["identity_proof_token"]
            if bool(parent_id) != bool(proof_token):
                raise ExactIdentityDecisionError("identity proof fields are incomplete")
            if not parent_id:
                continue
            parent_count += 1
            parent = by_occurrence.get(parent_id)
            if (
                parent is None
                or parent_id == row["occurrence_id"]
                or parent["component_id"] != component_id
                or proof_token not in json.loads(parent["typed_identity_tokens_json"])
                or proof_token not in json.loads(row["typed_identity_tokens_json"])
            ):
                raise ExactIdentityDecisionError("identity proof edge is invalid")
        if parent_count != len(members) - 1:
            raise ExactIdentityDecisionError("component proof tree is not closed")
        for row in members:
            cursor = row
            visited: set[str] = set()
            while cursor["identity_proof_parent_occurrence_id"]:
                if cursor["occurrence_id"] in visited:
                    raise ExactIdentityDecisionError("component proof tree has a cycle")
                visited.add(cursor["occurrence_id"])
                cursor = by_occurrence[cursor["identity_proof_parent_occurrence_id"]]
    proof_edges = sum(
        bool(row["identity_proof_parent_occurrence_id"]) for row in components
    )
    if proof_edges != accounting["exact_component_reductions"]:
        raise ExactIdentityDecisionError("identity proof edge count does not reconcile")

    relationships = _csv_rows(directory / RELATIONSHIPS_FILENAME, RELATIONSHIP_FIELDS)
    relationship_ids = [row["relationship_id"] for row in relationships]
    if relationship_ids != sorted(set(relationship_ids)):
        raise ExactIdentityDecisionError("relationships are not sorted and unique")
    if len(relationships) != accounting["canonical_topology_links"]:
        raise ExactIdentityDecisionError("relationship count does not reconcile")
    if (
        sum(int(row["raw_relationship_count"]) for row in relationships)
        != accounting["raw_topology_links"]
    ):
        raise ExactIdentityDecisionError("raw topology count does not reconcile")
    for row in relationships:
        if row["subject_component_id"] == row["object_component_id"]:
            raise ExactIdentityDecisionError("relationship self-loop is invalid")
        if row["relationship_type"] in RELATIONSHIP_KIND_PAIRS:
            if (
                row["subject_kind"],
                row["object_kind"],
            ) != RELATIONSHIP_KIND_PAIRS[row["relationship_type"]]:
                raise ExactIdentityDecisionError("relationship kinds are invalid")
        elif row["relationship_type"] == "project_targets":
            if row["subject_kind"] != "project" or row["object_kind"] == "project":
                raise ExactIdentityDecisionError("project target kinds are invalid")
        else:
            raise ExactIdentityDecisionError("relationship type is invalid")
        if (
            row["subject_component_id"] not in components_by_id
            or row["object_component_id"] not in components_by_id
            or row["relationship_id"]
            != _relationship_id(
                row["relationship_type"],
                row["subject_component_id"],
                row["object_component_id"],
            )
            or int(row["raw_relationship_count"]) < 1
        ):
            raise ExactIdentityDecisionError("relationship identity is invalid")
        typed_tokens = json.loads(row["typed_identity_tokens_json"])
        source_releases = json.loads(row["source_release_ids_json"])
        expected_tokens = sorted(
            component_tokens[row["subject_component_id"]]
            & component_tokens[row["object_component_id"]]
        )
        if (
            typed_tokens != expected_tokens
            or not isinstance(source_releases, list)
            or source_releases != sorted(set(source_releases))
            or not source_releases
            or row["decision_basis"]
            != (
                "explicit_parent_and_exact_typed_identity"
                if typed_tokens
                else "explicit_parent"
            )
        ):
            raise ExactIdentityDecisionError("relationship evidence is invalid")

    unresolved = _csv_rows(directory / UNRESOLVED_FILENAME, UNRESOLVED_FIELDS)
    candidate_ids = [row["candidate_reference_id"] for row in unresolved]
    if candidate_ids != sorted(set(candidate_ids)):
        raise ExactIdentityDecisionError(
            "unresolved candidate references are not sorted and unique"
        )
    if len(unresolved) != accounting["unresolved_candidate_references"]:
        raise ExactIdentityDecisionError("unresolved candidates do not reconcile")
    unresolved_origins = Counter(row["origin"] for row in unresolved)
    if (
        unresolved_origins.get("release_resolution_candidate", 0)
        != accounting["release_candidate_references"]
        or unresolved_origins.get("ambiguous_typed_identity", 0)
        != accounting["ambiguous_identity_candidate_references"]
        or set(unresolved_origins)
        - {"release_resolution_candidate", "ambiguous_typed_identity"}
    ):
        raise ExactIdentityDecisionError("unresolved origin counts do not reconcile")
    if any(
        row["disposition"] != "manual_only"
        or row["reason"]
        not in {
            "ambiguous_pnnl_campus_osm_object_type",
            "spatial_semantic_signals_are_not_identity",
        }
        for row in unresolved
    ):
        raise ExactIdentityDecisionError("unresolved disposition is invalid")
    for row in unresolved:
        left = by_occurrence.get(row["left_occurrence_id"])
        right = by_occurrence.get(row["right_occurrence_id"])
        if (
            left is None
            or right is None
            or row["left_occurrence_id"] >= row["right_occurrence_id"]
            or row["release_id"] not in {left["release_id"], right["release_id"]}
            or not _SHA256_RE.fullmatch(row["source_sha256"])
        ):
            raise ExactIdentityDecisionError("unresolved candidate identity is invalid")
        if row["origin"] == "release_resolution_candidate":
            if (
                row["typed_identity_token"]
                or row["source_artifact"] != "resolution_candidates.json"
            ):
                raise ExactIdentityDecisionError(
                    "release candidate provenance is invalid"
                )
        else:
            token = row["typed_identity_token"]
            left_typed = json.loads(left["typed_identity_tokens_json"])
            right_typed = json.loads(right["typed_identity_tokens_json"])
            left_ambiguous = json.loads(left["ambiguous_identity_tokens_json"])
            right_ambiguous = json.loads(right["ambiguous_identity_tokens_json"])
            if (
                row["source_artifact"] != "atlas.geojson"
                or not token
                or not (
                    (token in left_ambiguous and token in right_typed)
                    or (token in right_ambiguous and token in left_typed)
                )
            ):
                raise ExactIdentityDecisionError(
                    "ambiguous candidate provenance is invalid"
                )

    lineage = _csv_rows(directory / LINEAGE_FILENAME, LINEAGE_FIELDS)
    lineage_keys = [
        (row["release_id"], row["source_family"], row["source_root"]) for row in lineage
    ]
    if lineage_keys != sorted(set(lineage_keys)):
        raise ExactIdentityDecisionError("source lineage is not sorted and unique")
    expected_lineage: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(
        list
    )
    for row in components:
        expected_lineage[
            (row["release_id"], row["source_family"], row["source_root"])
        ].append(row)
    if set(lineage_keys) != set(expected_lineage):
        raise ExactIdentityDecisionError("source lineage groups do not reconcile")
    for row in lineage:
        key = (row["release_id"], row["source_family"], row["source_root"])
        members = expected_lineage[key]
        publishers = json.loads(row["publisher_roots_json"])
        expected_derivation = (
            "shared_upstream_root"
            if row["source_family"].casefold() != row["source_root"]
            else "direct_or_unclassified"
        )
        if (
            row["source_root"] != _source_root(row["source_family"])
            or int(row["occurrence_count"]) != len(members)
            or int(row["exact_component_count"])
            != len({member["component_id"] for member in members})
            or not isinstance(publishers, list)
            or publishers != sorted(set(publishers))
            or not publishers
            or row["derivation_status"] != expected_derivation
            or row["independence_claim_allowed"] != "False"
        ):
            raise ExactIdentityDecisionError("source lineage evidence is invalid")

    raw_kind = dict(sorted(Counter(row["entity_kind"] for row in components).items()))
    exact_kind = dict(
        sorted(
            Counter(
                members[0]["entity_kind"] for members in components_by_id.values()
            ).items()
        )
    )
    relationship_kind = dict(
        sorted(Counter(row["relationship_type"] for row in relationships).items())
    )
    if (
        accounting["source_scoped_entity_records"]
        != accounting["non_review_source_scoped_entity_records"]
        + accounting["review_only_source_scoped_entity_records"]
        or accounting["exact_component_reductions"]
        != len(components) - len(components_by_id)
        or accounting["raw_non_review_occurrences_by_kind"] != raw_kind
        or accounting["exact_source_record_components_by_kind"] != exact_kind
        or accounting["canonical_topology_links_by_type"] != relationship_kind
    ):
        raise ExactIdentityDecisionError("decision accounting does not reconcile")


def validate_exact_identity_decision_bundle(
    path_value: str | Path,
    *,
    definition_path: str | Path | None = None,
    verify_inputs: bool = False,
    require_frozen: bool = True,
) -> dict[str, Any]:
    """Validate a closed decision bundle, optionally rebuilding all inputs."""

    directory = Path(path_value)
    if directory.is_symlink() or not directory.is_dir():
        raise ExactIdentityDecisionError("decision bundle must be a regular directory")
    entries = list(directory.iterdir())
    if any(item.is_symlink() or not item.is_file() for item in entries):
        raise ExactIdentityDecisionError(
            "decision bundle entries must be regular files"
        )
    if {item.name for item in entries} != BUNDLE_FILES:
        raise ExactIdentityDecisionError("decision bundle file inventory is invalid")
    if require_frozen:
        if stat.S_IMODE(directory.stat().st_mode) != 0o555 or any(
            stat.S_IMODE(item.stat().st_mode) != 0o444 for item in entries
        ):
            raise ExactIdentityDecisionError("decision bundle is not frozen")

    manifest, manifest_raw = _json_object(
        directory / MANIFEST_FILENAME, "decision manifest"
    )
    if manifest_raw != _canonical_json(manifest):
        raise ExactIdentityDecisionError("decision manifest is not canonical JSON")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != BUNDLE_FORMAT
        or manifest.get("scope") != POLICY
    ):
        raise ExactIdentityDecisionError("decision manifest identity is invalid")
    _text(manifest.get("bundle_id"), "decision manifest bundle_id")
    recorded_at = _timestamp(
        manifest.get("recorded_at"), "decision manifest recorded_at"
    )
    if datetime.fromisoformat(recorded_at.replace("Z", "+00:00")) > datetime.now(UTC):
        raise ExactIdentityDecisionError(
            "decision manifest recorded_at is in the future"
        )
    files = manifest.get("files")
    payload_names = BUNDLE_FILES - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    if not isinstance(files, Mapping) or set(files) != payload_names:
        raise ExactIdentityDecisionError("decision manifest file set is invalid")
    for name in sorted(payload_names):
        expected = _require_checkpoint(files[name], f"decision file {name}")
        if _checkpoint(directory / name) != expected:
            raise ExactIdentityDecisionError(f"decision file hash mismatch: {name}")
    expected_sidecar = (f"{_sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n").encode(
        "ascii"
    )
    if (directory / MANIFEST_HASH_FILENAME).read_bytes() != expected_sidecar:
        raise ExactIdentityDecisionError("decision manifest sidecar is invalid")
    _validate_output_semantics(directory, manifest)

    if definition_path is not None:
        definition = _load_definition(definition_path)
        expected_definition = {
            "file": definition.path.name,
            "bytes": len(definition.raw),
            "sha256": _sha256_bytes(definition.raw),
        }
        if manifest.get("definition") != expected_definition:
            raise ExactIdentityDecisionError("definition checkpoint differs")
        if verify_inputs:
            expected_payloads, expected_manifest = _prepare_bundle(definition)
            actual_payloads = {
                item.name: item.read_bytes() for item in directory.iterdir()
            }
            if actual_payloads != expected_payloads or manifest != expected_manifest:
                raise ExactIdentityDecisionError(
                    "exact-input rebuild differs from decision bundle"
                )
    elif verify_inputs:
        raise ExactIdentityDecisionError(
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


def _freeze_tree(directory: Path) -> None:
    for path in directory.iterdir():
        path.chmod(0o444)
    directory.chmod(0o555)


def _thaw_tree(directory: Path) -> None:
    directory.chmod(0o755)
    for path in directory.iterdir():
        path.chmod(0o644)


def write_exact_identity_decision_bundle(
    definition_path: str | Path, output_directory: str | Path
) -> dict[str, Any]:
    """Atomically publish one frozen exact-identity decision bundle."""

    definition = _load_definition(definition_path)
    payloads, manifest = _prepare_bundle(definition)
    output = Path(os.path.abspath(os.fspath(output_directory)))
    if output.is_symlink():
        raise ExactIdentityDecisionError("decision output may not be a symlink")
    if output.exists():
        validated = validate_exact_identity_decision_bundle(
            output, definition_path=definition.path, verify_inputs=True
        )
        if any((output / name).read_bytes() != raw for name, raw in payloads.items()):
            raise ExactIdentityDecisionError(
                "existing decision bundle is valid but not byte-identical"
            )
        return validated

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.parent.is_symlink() or not output.parent.is_dir() or not output.name:
        raise ExactIdentityDecisionError("decision output parent is invalid")
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    try:
        for name, raw in payloads.items():
            _write_bytes(stage / name, raw)
        validate_exact_identity_decision_bundle(stage, require_frozen=False)

        # A complete second preparation catches mid-build input drift and also
        # establishes deterministic, order-independent output before publication.
        rechecked_payloads, rechecked_manifest = _prepare_bundle(definition)
        if rechecked_payloads != payloads or rechecked_manifest != manifest:
            raise ExactIdentityDecisionError(
                "decision inputs changed or rebuild was not deterministic"
            )
        if output.exists() or output.is_symlink():
            raise ExactIdentityDecisionError(
                "decision output appeared during publication"
            )
        _freeze_tree(stage)
        validate_exact_identity_decision_bundle(stage)
        os.rename(stage, output)
        _fsync_directory(output.parent)
    except Exception:
        if stage.exists() and stage.is_dir() and not stage.is_symlink():
            _thaw_tree(stage)
            shutil.rmtree(stage)
        raise
    return manifest


build_exact_identity_decision_bundle = write_exact_identity_decision_bundle


__all__ = [
    "ACCOUNTING_FILENAME",
    "BUNDLE_FILES",
    "BUNDLE_FORMAT",
    "COMPONENTS_FILENAME",
    "DEFINITION_FORMAT",
    "ExactIdentityDecisionError",
    "LINEAGE_FILENAME",
    "POLICY",
    "RELATIONSHIPS_FILENAME",
    "UNRESOLVED_FILENAME",
    "build_exact_identity_decision_bundle",
    "validate_exact_identity_decision_bundle",
    "write_exact_identity_decision_bundle",
]
