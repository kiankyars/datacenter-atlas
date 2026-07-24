"""Deterministic index of separately licensed Data Center Atlas releases.

The federation contains references and exact checkpoints only. It never copies
child data files, merges child entities, combines licenses, or claims a count of
unique physical sites.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit


INDEX_FILENAME = "federated-index.json"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
FEDERATED_BUNDLE_FILES = frozenset(
    {INDEX_FILENAME, MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
)
DEFINITION_SCHEMA_VERSION = 1
INDEX_SCHEMA_VERSION = 1
INDEX_FORMAT = "datacenter-atlas-federated-release-index-v1"
BUNDLE_FORMAT = "datacenter-atlas-federated-index-bundle-v1"
CHILD_RELEASE_FORMAT = "datacenter-atlas-release-v1"
MAX_CHILD_CSV_FIELD_SIZE = 1024 * 1024
FEDERATION_POLICY = {
    "federation_only": True,
    "child_payloads_copied": False,
    "child_entities_merged": False,
    "cross_source_deduplication": False,
    "source_family_labels_collapsed_across_releases": False,
    "licenses_or_attributions_combined": False,
    "totals_are_arithmetic_sums_of_child_release_counts": True,
    "review_only_rows_are_separately_counted": True,
    "unique_physical_site_count": None,
}
REQUIRED_CHILD_FILES = frozenset(
    {
        "ATTRIBUTION.txt",
        "entities.csv",
        "evidence.csv",
        "source_inputs.json",
    }
)
RELEASE_REQUIRED_MANIFEST_KEYS = frozenset(
    {
        "format",
        "as_of",
        "recorded_at",
        "entities",
        "entities_by_kind",
        "capacity_estimates",
        "construction_pipeline_records",
        "evidence_records",
        "source_families",
        "resolution_candidates",
        "files",
    }
)
RELEASE_OPTIONAL_MANIFEST_KEYS = frozenset(
    {
        "construction_source_signals",
        "fuzzy_review_excluded_candidates",
        "fuzzy_review_shortlist_records",
        "publication_contract_version",
        "review_only",
    }
)
CHILD_COUNT_FIELDS = (
    "source_scoped_entity_records",
    "evidence_records",
    "source_family_entries",
    "capacity_estimates",
    "construction_pipeline_records",
    "resolution_candidates",
)
TOTAL_COUNT_FIELDS = (
    "source_scoped_entity_records",
    "evidence_records",
    "source_family_entries",
    "capacity_estimates",
    "construction_pipeline_records",
    "resolution_candidates",
)
SCOPE_SPLIT_TOTAL_FIELDS = ("construction_pipeline_records",)


class FederatedReleaseError(ValueError):
    """Raised when a child release or federated index fails closed."""


@dataclass(frozen=True, slots=True)
class FederatedIndexBundle:
    index_bytes: bytes
    manifest_bytes: bytes
    manifest_hash_bytes: bytes
    index: Mapping[str, Any]
    manifest: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class _ChildDefinition:
    release_id: str
    release_path: Path
    reference: str
    expected_manifest_sha256: str
    license_expression: str
    rights_notice: str


def _aggregate_counts(
    releases: list[dict[str, Any]], *, include_scope_splits: bool
) -> dict[str, Any]:
    totals: dict[str, Any] = {
        "release_bundles": len(releases),
        "review_only_release_bundles": sum(
            release["scope"]["review_only"] for release in releases
        ),
        "review_only_source_scoped_entity_records": sum(
            release["counts"]["source_scoped_entity_records"]
            for release in releases
            if release["scope"]["review_only"]
        ),
        "non_review_source_scoped_entity_records": sum(
            release["counts"]["source_scoped_entity_records"]
            for release in releases
            if not release["scope"]["review_only"]
        ),
        "unique_physical_sites": None,
    }
    for field in TOTAL_COUNT_FIELDS:
        totals[field] = sum(release["counts"][field] for release in releases)
    if include_scope_splits:
        for field in SCOPE_SPLIT_TOTAL_FIELDS:
            totals[f"review_only_{field}"] = sum(
                release["counts"][field]
                for release in releases
                if release["scope"]["review_only"]
            )
            totals[f"non_review_{field}"] = sum(
                release["counts"][field]
                for release in releases
                if not release["scope"]["review_only"]
            )
    return totals


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FederatedReleaseError(f"{label} must be non-empty text")
    result = value.strip()
    if result != value:
        raise FederatedReleaseError(f"{label} must not have surrounding whitespace")
    return result


def _nonempty_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FederatedReleaseError(f"{label} must be non-empty text")
    return value


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise FederatedReleaseError(
            f"{label} must be lowercase SHA-256 hexadecimal"
        )
    return value


def _nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FederatedReleaseError(f"{label} must be a non-negative integer")
    return value


def _positive_integer(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise FederatedReleaseError(f"{label} must be a positive integer")
    return value


def _calendar_date(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise FederatedReleaseError(f"{label} must use YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise FederatedReleaseError(f"{label} must be a valid YYYY-MM-DD date") from error
    if parsed.isoformat() != value:
        raise FederatedReleaseError(f"{label} must use canonical YYYY-MM-DD")
    return value


def _timestamp(value: Any, label: str, *, require_canonical_utc: bool) -> str:
    if not isinstance(value, str) or not value:
        raise FederatedReleaseError(f"{label} must be a timezone-aware timestamp")
    if not value.endswith("Z") and not (
        len(value) >= 6 and value[-6] in {"+", "-"} and value[-3] == ":"
    ):
        raise FederatedReleaseError(f"{label} must include a timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise FederatedReleaseError(f"{label} is not a valid timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FederatedReleaseError(f"{label} must include a timezone")
    if require_canonical_utc:
        canonical = (
            parsed.astimezone(UTC)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        if value != canonical:
            raise FederatedReleaseError(f"{label} must be canonical UTC seconds")
    return value


def _regular_bytes(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise FederatedReleaseError(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FederatedReleaseError(f"{label} must be UTF-8") from error

    def reject_constant(value: str) -> None:
        raise FederatedReleaseError(f"{label} contains non-finite number {value}")

    try:
        document = json.loads(text, parse_constant=reject_constant)
    except json.JSONDecodeError as error:
        raise FederatedReleaseError(f"{label} is not valid JSON") from error
    if not isinstance(document, dict):
        raise FederatedReleaseError(f"{label} must be a JSON object")
    return document


def _checkpoint(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"bytes", "sha256"}:
        raise FederatedReleaseError(f"{label} checkpoint schema is invalid")
    return {
        "bytes": _nonnegative_integer(value.get("bytes"), f"{label} bytes"),
        "sha256": _sha256(value.get("sha256"), f"{label} sha256"),
    }


def _release_id(value: Any, label: str) -> str:
    result = _required_text(value, label)
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789-"
    if (
        len(result) > 96
        or any(character not in allowed for character in result)
        or not result[0].isalnum()
        or not result[-1].isalnum()
    ):
        raise FederatedReleaseError(
            f"{label} must be a lowercase alphanumeric-hyphen identifier"
        )
    return result


def _reference(value: Any, label: str) -> str:
    result = _required_text(value, label)
    parsed = urlsplit(result)
    if parsed.scheme:
        if parsed.scheme != "https" or not parsed.netloc:
            raise FederatedReleaseError(
                f"{label} must be an HTTPS URL or relative published path"
            )
    elif result.startswith("/") or "\\" in result:
        raise FederatedReleaseError(
            f"{label} must be an HTTPS URL or relative published path"
        )
    return result


def _sorted_unique_texts(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise FederatedReleaseError(f"{label} must be an array")
    result = [_required_text(item, f"{label} item") for item in value]
    if result != sorted(set(result)):
        raise FederatedReleaseError(f"{label} must be sorted and unique")
    return result


def _csv_facts_under_limit(
    release: Path,
) -> tuple[dict[str, int], int, list[str], list[str]]:
    entity_kind_counts: dict[str, int] = {}
    entity_count = 0
    entities_path = release / "entities.csv"
    try:
        with entities_path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None or "entity_kind" not in reader.fieldnames:
                raise FederatedReleaseError(
                    "child entities.csv must contain entity_kind"
                )
            for row in reader:
                kind = _required_text(row.get("entity_kind"), "child entity_kind")
                entity_kind_counts[kind] = entity_kind_counts.get(kind, 0) + 1
                entity_count += 1
    except UnicodeDecodeError as error:
        raise FederatedReleaseError("child entities.csv must be UTF-8") from error

    evidence_count = 0
    source_families: set[str] = set()
    source_licenses: set[str] = set()
    evidence_path = release / "evidence.csv"
    try:
        with evidence_path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"source_family", "license"}
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise FederatedReleaseError(
                    "child evidence.csv must contain source_family and license"
                )
            for row in reader:
                source_families.add(
                    _required_text(row.get("source_family"), "child source_family")
                )
                source_licenses.add(
                    _required_text(row.get("license"), "child evidence license")
                )
                evidence_count += 1
    except UnicodeDecodeError as error:
        raise FederatedReleaseError("child evidence.csv must be UTF-8") from error
    return (
        dict(sorted(entity_kind_counts.items())),
        evidence_count,
        sorted(source_families),
        sorted(source_licenses),
    )


def _csv_facts(release: Path) -> tuple[dict[str, int], int, list[str], list[str]]:
    previous_limit = csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_CHILD_CSV_FIELD_SIZE)
        return _csv_facts_under_limit(release)
    except csv.Error as error:
        raise FederatedReleaseError(
            "child release CSV exceeds the supported field size or is malformed"
        ) from error
    finally:
        csv.field_size_limit(previous_limit)


def _inspect_child(definition: _ChildDefinition) -> dict[str, Any]:
    release = definition.release_path
    if release.is_symlink() or not release.is_dir():
        raise FederatedReleaseError(
            f"child release must be a regular directory: {release}"
        )
    manifest_path = release / MANIFEST_FILENAME
    manifest_raw = _regular_bytes(manifest_path, "child release manifest")
    manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()
    if manifest_sha256 != definition.expected_manifest_sha256:
        raise FederatedReleaseError(
            f"child {definition.release_id} manifest SHA-256 does not match definition"
        )
    manifest = _json_object(manifest_raw, "child release manifest")
    if manifest_raw != _canonical_json(manifest):
        raise FederatedReleaseError("child release manifest is not canonical JSON")
    manifest_keys = set(manifest)
    if (
        not RELEASE_REQUIRED_MANIFEST_KEYS.issubset(manifest_keys)
        or not manifest_keys.issubset(
            RELEASE_REQUIRED_MANIFEST_KEYS | RELEASE_OPTIONAL_MANIFEST_KEYS
        )
    ):
        raise FederatedReleaseError("child release manifest schema is invalid")
    if manifest.get("format") != CHILD_RELEASE_FORMAT:
        raise FederatedReleaseError("child release format is unsupported")
    as_of = _calendar_date(manifest.get("as_of"), "child release as_of")
    recorded_at = _timestamp(
        manifest.get("recorded_at"),
        "child release recorded_at",
        require_canonical_utc=True,
    )
    publication_contract_version: int | None = None
    if "publication_contract_version" in manifest_keys:
        publication_contract_version = _positive_integer(
            manifest.get("publication_contract_version"),
            "child release publication_contract_version",
        )
    files_value = manifest.get("files")
    if not isinstance(files_value, Mapping) or not files_value:
        raise FederatedReleaseError("child release files inventory is invalid")
    files: dict[str, dict[str, Any]] = {}
    for filename, value in files_value.items():
        if (
            not isinstance(filename, str)
            or not filename
            or Path(filename).name != filename
            or filename == MANIFEST_FILENAME
        ):
            raise FederatedReleaseError("child release contains an unsafe filename")
        files[filename] = _checkpoint(value, f"child file {filename}")
    if not REQUIRED_CHILD_FILES.issubset(files):
        missing = sorted(REQUIRED_CHILD_FILES - set(files))
        raise FederatedReleaseError(
            f"child release is missing required provenance files: {missing}"
        )
    entries = list(release.iterdir())
    names = {entry.name for entry in entries}
    expected_names = set(files) | {MANIFEST_FILENAME}
    if names != expected_names or len(entries) != len(expected_names):
        raise FederatedReleaseError(
            "child release file set differs from its manifest"
        )
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            raise FederatedReleaseError(
                f"child release entry must be a regular file: {entry.name}"
            )
        if entry.name == MANIFEST_FILENAME:
            continue
        raw = entry.read_bytes()
        checkpoint = files[entry.name]
        if (
            len(raw) != checkpoint["bytes"]
            or hashlib.sha256(raw).hexdigest() != checkpoint["sha256"]
        ):
            raise FederatedReleaseError(
                f"child release file hash mismatch: {entry.name}"
            )

    manifest_entities = _nonnegative_integer(
        manifest.get("entities"), "child release entities"
    )
    if manifest_entities == 0:
        raise FederatedReleaseError("child release must contain entity records")
    review_only_value = manifest.get("review_only")
    if review_only_value is not None and review_only_value is not True:
        raise FederatedReleaseError(
            "child release review_only must be true when present"
        )
    review_only = review_only_value is True
    fuzzy_review_fields = {
        "fuzzy_review_excluded_candidates",
        "fuzzy_review_shortlist_records",
    }
    present_fuzzy_review_fields = fuzzy_review_fields & manifest_keys
    if present_fuzzy_review_fields and present_fuzzy_review_fields != fuzzy_review_fields:
        raise FederatedReleaseError(
            "child fuzzy-review counts must be present together"
        )
    fuzzy_review_excluded: int | None = None
    fuzzy_review_shortlist: int | None = None
    if present_fuzzy_review_fields:
        if not review_only:
            raise FederatedReleaseError(
                "child fuzzy-review counts require review_only true"
            )
        fuzzy_review_excluded = _nonnegative_integer(
            manifest.get("fuzzy_review_excluded_candidates"),
            "child fuzzy_review_excluded_candidates",
        )
        fuzzy_review_shortlist = _nonnegative_integer(
            manifest.get("fuzzy_review_shortlist_records"),
            "child fuzzy_review_shortlist_records",
        )
        if fuzzy_review_excluded + fuzzy_review_shortlist != manifest_entities:
            raise FederatedReleaseError(
                "child fuzzy-review counts do not reconcile with entities"
            )
    entities_by_kind_value = manifest.get("entities_by_kind")
    if not isinstance(entities_by_kind_value, Mapping):
        raise FederatedReleaseError("child release entities_by_kind is invalid")
    entities_by_kind: dict[str, int] = {}
    for kind, count in entities_by_kind_value.items():
        normalized_kind = _required_text(kind, "child entity kind")
        normalized_count = _nonnegative_integer(
            count, f"child entity kind {normalized_kind} count"
        )
        if normalized_count == 0:
            raise FederatedReleaseError("child entities_by_kind contains a zero count")
        entities_by_kind[normalized_kind] = normalized_count
    entities_by_kind = dict(sorted(entities_by_kind.items()))
    if entities_by_kind_value != entities_by_kind:
        raise FederatedReleaseError("child entities_by_kind is not canonical")
    source_families = _sorted_unique_texts(
        manifest.get("source_families"), "child source_families"
    )
    if not source_families:
        raise FederatedReleaseError("child release must identify source families")

    csv_entity_kinds, evidence_count, evidence_families, source_licenses = (
        _csv_facts(release)
    )
    if manifest_entities != sum(entities_by_kind.values()):
        raise FederatedReleaseError("child manifest entity counts do not reconcile")
    if manifest_entities != sum(csv_entity_kinds.values()):
        raise FederatedReleaseError("child entities.csv count does not match manifest")
    if csv_entity_kinds != entities_by_kind:
        raise FederatedReleaseError(
            "child entities.csv kind counts do not match manifest"
        )
    manifest_evidence = _nonnegative_integer(
        manifest.get("evidence_records"), "child release evidence_records"
    )
    if manifest_evidence != evidence_count:
        raise FederatedReleaseError("child evidence.csv count does not match manifest")
    if source_families != evidence_families:
        raise FederatedReleaseError(
            "child evidence.csv source families do not match manifest"
        )

    attribution_raw = _regular_bytes(
        release / "ATTRIBUTION.txt", "child ATTRIBUTION.txt"
    )
    try:
        attribution_text = attribution_raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FederatedReleaseError("child ATTRIBUTION.txt must be UTF-8") from error
    if not attribution_text.strip():
        raise FederatedReleaseError("child ATTRIBUTION.txt must not be empty")
    attribution_checkpoint = files["ATTRIBUTION.txt"]
    if (
        len(attribution_raw) != attribution_checkpoint["bytes"]
        or hashlib.sha256(attribution_raw).hexdigest()
        != attribution_checkpoint["sha256"]
    ):
        raise FederatedReleaseError("child attribution checkpoint does not match")

    counts = {
        "source_scoped_entity_records": manifest_entities,
        "entities_by_kind": entities_by_kind,
        "evidence_records": manifest_evidence,
        "source_family_entries": len(source_families),
        "capacity_estimates": _nonnegative_integer(
            manifest.get("capacity_estimates"), "child capacity_estimates"
        ),
        "construction_pipeline_records": _nonnegative_integer(
            manifest.get("construction_pipeline_records"),
            "child construction_pipeline_records",
        ),
        "resolution_candidates": _nonnegative_integer(
            manifest.get("resolution_candidates"), "child resolution_candidates"
        ),
    }
    manifest_descriptor = {
        "file": MANIFEST_FILENAME,
        "bytes": len(manifest_raw),
        "sha256": manifest_sha256,
        "format": CHILD_RELEASE_FORMAT,
        "as_of": as_of,
        "recorded_at": recorded_at,
    }
    if publication_contract_version is not None:
        manifest_descriptor["publication_contract_version"] = (
            publication_contract_version
        )
    return {
        "release_id": definition.release_id,
        "reference": definition.reference,
        "manifest": manifest_descriptor,
        "rights": {
            "license_expression": definition.license_expression,
            "rights_notice": definition.rights_notice,
            "source_licenses": source_licenses,
            "attribution": {
                "file": "ATTRIBUTION.txt",
                "bytes": len(attribution_raw),
                "sha256": hashlib.sha256(attribution_raw).hexdigest(),
                "text": attribution_text,
            },
        },
        "scope": {
            "review_only": review_only,
            "fuzzy_review_excluded_candidates": fuzzy_review_excluded,
            "fuzzy_review_shortlist_records": fuzzy_review_shortlist,
        },
        "counts": counts,
        "source_families": source_families,
        "files": dict(sorted(files.items())),
    }


def _definition(path: Path) -> tuple[bytes, str, list[_ChildDefinition]]:
    raw = _regular_bytes(path, "federation definition")
    document = _json_object(raw, "federation definition")
    if set(document) != {"schema_version", "generated_at", "children"}:
        raise FederatedReleaseError("federation definition schema is invalid")
    if document.get("schema_version") != DEFINITION_SCHEMA_VERSION:
        raise FederatedReleaseError("federation definition schema version is invalid")
    generated_at = _timestamp(
        document.get("generated_at"),
        "federation generated_at",
        require_canonical_utc=True,
    )
    children_value = document.get("children")
    if not isinstance(children_value, list) or len(children_value) < 2:
        raise FederatedReleaseError(
            "federation definition must contain at least two child releases"
        )
    children: list[_ChildDefinition] = []
    release_ids: set[str] = set()
    references: set[str] = set()
    resolved_paths: set[Path] = set()
    for index, value in enumerate(children_value):
        label = f"federation child {index}"
        if not isinstance(value, Mapping) or set(value) != {
            "release_id",
            "release_path",
            "reference",
            "expected_manifest_sha256",
            "license_expression",
            "rights_notice",
        }:
            raise FederatedReleaseError(f"{label} schema is invalid")
        release_id = _release_id(value.get("release_id"), f"{label} release_id")
        reference = _reference(value.get("reference"), f"{label} reference")
        release_path_value = _required_text(
            value.get("release_path"), f"{label} release_path"
        )
        release_path = Path(release_path_value)
        if not release_path.is_absolute():
            release_path = path.parent / release_path
        resolved_path = release_path.resolve()
        if release_id in release_ids:
            raise FederatedReleaseError(f"duplicate federation release_id: {release_id}")
        if reference in references:
            raise FederatedReleaseError(f"duplicate federation reference: {reference}")
        if resolved_path in resolved_paths:
            raise FederatedReleaseError("federation repeats a child release path")
        release_ids.add(release_id)
        references.add(reference)
        resolved_paths.add(resolved_path)
        children.append(
            _ChildDefinition(
                release_id=release_id,
                release_path=release_path,
                reference=reference,
                expected_manifest_sha256=_sha256(
                    value.get("expected_manifest_sha256"),
                    f"{label} expected_manifest_sha256",
                ),
                license_expression=_required_text(
                    value.get("license_expression"),
                    f"{label} license_expression",
                ),
                rights_notice=_required_text(
                    value.get("rights_notice"), f"{label} rights_notice"
                ),
            )
        )
    return raw, generated_at, sorted(children, key=lambda child: child.release_id)


def build_federated_release_index(
    definition_path: str | Path,
) -> FederatedIndexBundle:
    """Validate referenced releases and build an in-memory federation bundle."""
    path = Path(definition_path)
    definition_raw, generated_at, definitions = _definition(path)
    releases = [_inspect_child(definition) for definition in definitions]
    totals = _aggregate_counts(releases, include_scope_splits=True)
    index = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "format": INDEX_FORMAT,
        "generated_at": generated_at,
        "policy": dict(FEDERATION_POLICY),
        "counts": totals,
        "releases": releases,
    }
    index_bytes = _canonical_json(index)
    manifest = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "format": BUNDLE_FORMAT,
        "generated_at": generated_at,
        "scope": dict(FEDERATION_POLICY),
        "definition": {
            "file": path.name,
            "bytes": len(definition_raw),
            "sha256": hashlib.sha256(definition_raw).hexdigest(),
        },
        "artifacts": {
            INDEX_FILENAME: {
                "format": INDEX_FORMAT,
                "release_bundles": len(releases),
                "bytes": len(index_bytes),
                "sha256": hashlib.sha256(index_bytes).hexdigest(),
            }
        },
    }
    manifest_bytes = _canonical_json(manifest)
    manifest_hash_bytes = (
        f"{hashlib.sha256(manifest_bytes).hexdigest()}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    return FederatedIndexBundle(
        index_bytes=index_bytes,
        manifest_bytes=manifest_bytes,
        manifest_hash_bytes=manifest_hash_bytes,
        index=index,
        manifest=manifest,
    )


def _validate_descriptor(value: Any, index: int) -> dict[str, Any]:
    label = f"federated release descriptor {index}"
    if not isinstance(value, Mapping) or set(value) != {
        "release_id",
        "reference",
        "manifest",
        "rights",
        "scope",
        "counts",
        "source_families",
        "files",
    }:
        raise FederatedReleaseError(f"{label} schema is invalid")
    release_id = _release_id(value.get("release_id"), f"{label} release_id")
    reference = _reference(value.get("reference"), f"{label} reference")
    child_manifest = value.get("manifest")
    legacy_manifest_keys = {
        "file",
        "bytes",
        "sha256",
        "format",
        "as_of",
        "recorded_at",
    }
    if not isinstance(child_manifest, Mapping) or set(child_manifest) not in (
        legacy_manifest_keys,
        legacy_manifest_keys | {"publication_contract_version"},
    ):
        raise FederatedReleaseError(f"{label} manifest schema is invalid")
    if (
        child_manifest.get("file") != MANIFEST_FILENAME
        or child_manifest.get("format") != CHILD_RELEASE_FORMAT
    ):
        raise FederatedReleaseError(f"{label} manifest identity is invalid")
    normalized_manifest = {
        "file": MANIFEST_FILENAME,
        "bytes": _nonnegative_integer(
            child_manifest.get("bytes"), f"{label} manifest bytes"
        ),
        "sha256": _sha256(
            child_manifest.get("sha256"), f"{label} manifest sha256"
        ),
        "format": CHILD_RELEASE_FORMAT,
        "as_of": _calendar_date(child_manifest.get("as_of"), f"{label} as_of"),
        "recorded_at": _timestamp(
            child_manifest.get("recorded_at"),
            f"{label} recorded_at",
            require_canonical_utc=True,
        ),
    }
    if "publication_contract_version" in child_manifest:
        normalized_manifest["publication_contract_version"] = _positive_integer(
            child_manifest.get("publication_contract_version"),
            f"{label} publication_contract_version",
        )
    files_value = value.get("files")
    if not isinstance(files_value, Mapping) or not files_value:
        raise FederatedReleaseError(f"{label} files inventory is invalid")
    files: dict[str, dict[str, Any]] = {}
    for filename, checkpoint in files_value.items():
        if (
            not isinstance(filename, str)
            or not filename
            or Path(filename).name != filename
            or filename == MANIFEST_FILENAME
        ):
            raise FederatedReleaseError(f"{label} contains an unsafe filename")
        files[filename] = _checkpoint(checkpoint, f"{label} file {filename}")
    files = dict(sorted(files.items()))
    if files_value != files or not REQUIRED_CHILD_FILES.issubset(files):
        raise FederatedReleaseError(f"{label} file inventory is not canonical")

    source_families = _sorted_unique_texts(
        value.get("source_families"), f"{label} source_families"
    )
    if not source_families:
        raise FederatedReleaseError(f"{label} has no source families")
    scope = value.get("scope")
    if not isinstance(scope, Mapping) or set(scope) != {
        "review_only",
        "fuzzy_review_excluded_candidates",
        "fuzzy_review_shortlist_records",
    }:
        raise FederatedReleaseError(f"{label} scope schema is invalid")
    review_only = scope.get("review_only")
    if not isinstance(review_only, bool):
        raise FederatedReleaseError(f"{label} review_only must be boolean")
    fuzzy_review_excluded = scope.get("fuzzy_review_excluded_candidates")
    fuzzy_review_shortlist = scope.get("fuzzy_review_shortlist_records")
    if (fuzzy_review_excluded is None) != (fuzzy_review_shortlist is None):
        raise FederatedReleaseError(
            f"{label} fuzzy-review counts must both be null or integers"
        )
    if fuzzy_review_excluded is not None:
        if not review_only:
            raise FederatedReleaseError(
                f"{label} fuzzy-review counts require review_only true"
            )
        fuzzy_review_excluded = _nonnegative_integer(
            fuzzy_review_excluded, f"{label} fuzzy_review_excluded_candidates"
        )
        fuzzy_review_shortlist = _nonnegative_integer(
            fuzzy_review_shortlist, f"{label} fuzzy_review_shortlist_records"
        )
    rights = value.get("rights")
    if not isinstance(rights, Mapping) or set(rights) != {
        "license_expression",
        "rights_notice",
        "source_licenses",
        "attribution",
    }:
        raise FederatedReleaseError(f"{label} rights schema is invalid")
    source_licenses = _sorted_unique_texts(
        rights.get("source_licenses"), f"{label} source_licenses"
    )
    if not source_licenses:
        raise FederatedReleaseError(f"{label} has no source licenses")
    attribution = rights.get("attribution")
    if not isinstance(attribution, Mapping) or set(attribution) != {
        "file",
        "bytes",
        "sha256",
        "text",
    }:
        raise FederatedReleaseError(f"{label} attribution schema is invalid")
    attribution_text = _nonempty_text(
        attribution.get("text"), f"{label} attribution text"
    )
    attribution_raw = attribution_text.encode("utf-8")
    if attribution.get("file") != "ATTRIBUTION.txt":
        raise FederatedReleaseError(f"{label} attribution file is invalid")
    attribution_bytes = _nonnegative_integer(
        attribution.get("bytes"), f"{label} attribution bytes"
    )
    attribution_sha256 = _sha256(
        attribution.get("sha256"), f"{label} attribution sha256"
    )
    if (
        len(attribution_raw) != attribution_bytes
        or hashlib.sha256(attribution_raw).hexdigest() != attribution_sha256
        or files["ATTRIBUTION.txt"]
        != {"bytes": attribution_bytes, "sha256": attribution_sha256}
    ):
        raise FederatedReleaseError(f"{label} attribution does not match file inventory")

    counts = value.get("counts")
    if not isinstance(counts, Mapping) or set(counts) != set(CHILD_COUNT_FIELDS) | {
        "entities_by_kind"
    }:
        raise FederatedReleaseError(f"{label} count schema is invalid")
    normalized_counts: dict[str, Any] = {}
    for field in CHILD_COUNT_FIELDS:
        normalized_counts[field] = _nonnegative_integer(
            counts.get(field), f"{label} {field}"
        )
    entities_by_kind_value = counts.get("entities_by_kind")
    if not isinstance(entities_by_kind_value, Mapping):
        raise FederatedReleaseError(f"{label} entities_by_kind is invalid")
    entities_by_kind: dict[str, int] = {}
    for kind, count in entities_by_kind_value.items():
        normalized_count = _nonnegative_integer(
            count, f"{label} entity kind {kind}"
        )
        if normalized_count == 0:
            raise FederatedReleaseError(f"{label} has a zero entity-kind count")
        entities_by_kind[_required_text(kind, f"{label} entity kind")] = normalized_count
    entities_by_kind = dict(sorted(entities_by_kind.items()))
    if entities_by_kind_value != entities_by_kind:
        raise FederatedReleaseError(f"{label} entities_by_kind is not canonical")
    normalized_counts["entities_by_kind"] = entities_by_kind
    if (
        normalized_counts["source_scoped_entity_records"]
        != sum(entities_by_kind.values())
        or normalized_counts["source_family_entries"] != len(source_families)
    ):
        raise FederatedReleaseError(f"{label} counts do not reconcile")
    if (
        fuzzy_review_excluded is not None
        and fuzzy_review_excluded + fuzzy_review_shortlist
        != normalized_counts["source_scoped_entity_records"]
    ):
        raise FederatedReleaseError(f"{label} fuzzy-review counts do not reconcile")
    return {
        "release_id": release_id,
        "reference": reference,
        "manifest": normalized_manifest,
        "rights": {
            "license_expression": _required_text(
                rights.get("license_expression"), f"{label} license_expression"
            ),
            "rights_notice": _required_text(
                rights.get("rights_notice"), f"{label} rights_notice"
            ),
            "source_licenses": source_licenses,
            "attribution": {
                "file": "ATTRIBUTION.txt",
                "bytes": attribution_bytes,
                "sha256": attribution_sha256,
                "text": attribution_text,
            },
        },
        "scope": {
            "review_only": review_only,
            "fuzzy_review_excluded_candidates": fuzzy_review_excluded,
            "fuzzy_review_shortlist_records": fuzzy_review_shortlist,
        },
        "counts": normalized_counts,
        "source_families": source_families,
        "files": files,
    }


def validate_federated_release_index(
    directory_path: str | Path,
    *,
    child_release_paths: Mapping[str, str | Path] | None = None,
) -> Mapping[str, Any]:
    """Validate an index bundle, optionally rechecking every referenced child."""
    directory = Path(directory_path)
    if directory.is_symlink() or not directory.is_dir():
        raise FederatedReleaseError(
            f"federated index must be a regular directory: {directory}"
        )
    entries = list(directory.iterdir())
    names = {entry.name for entry in entries}
    if names != FEDERATED_BUNDLE_FILES or len(entries) != len(FEDERATED_BUNDLE_FILES):
        raise FederatedReleaseError("federated index bundle file set is invalid")
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            raise FederatedReleaseError(
                f"federated index entry must be a regular file: {entry.name}"
            )
    index_raw = (directory / INDEX_FILENAME).read_bytes()
    manifest_raw = (directory / MANIFEST_FILENAME).read_bytes()
    sidecar_raw = (directory / MANIFEST_HASH_FILENAME).read_bytes()
    expected_sidecar = (
        f"{hashlib.sha256(manifest_raw).hexdigest()}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    if sidecar_raw != expected_sidecar:
        raise FederatedReleaseError("federated manifest sidecar does not match")
    manifest = _json_object(manifest_raw, "federated bundle manifest")
    index = _json_object(index_raw, "federated release index")
    if manifest_raw != _canonical_json(manifest) or index_raw != _canonical_json(index):
        raise FederatedReleaseError("federated bundle JSON is not canonical")
    if set(manifest) != {
        "schema_version",
        "format",
        "generated_at",
        "scope",
        "definition",
        "artifacts",
    }:
        raise FederatedReleaseError("federated bundle manifest schema is invalid")
    if (
        manifest.get("schema_version") != INDEX_SCHEMA_VERSION
        or manifest.get("format") != BUNDLE_FORMAT
        or manifest.get("scope") != FEDERATION_POLICY
    ):
        raise FederatedReleaseError("federated bundle manifest identity is invalid")
    generated_at = _timestamp(
        manifest.get("generated_at"),
        "federated manifest generated_at",
        require_canonical_utc=True,
    )
    definition = manifest.get("definition")
    if not isinstance(definition, Mapping) or set(definition) != {
        "file",
        "bytes",
        "sha256",
    }:
        raise FederatedReleaseError("federated definition lineage is invalid")
    definition_file = _required_text(
        definition.get("file"), "federated definition file"
    )
    if Path(definition_file).name != definition_file:
        raise FederatedReleaseError("federated definition file must be a basename")
    _nonnegative_integer(definition.get("bytes"), "federated definition bytes")
    _sha256(definition.get("sha256"), "federated definition sha256")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {INDEX_FILENAME}:
        raise FederatedReleaseError("federated artifact inventory is invalid")
    artifact = artifacts[INDEX_FILENAME]
    if not isinstance(artifact, Mapping) or set(artifact) != {
        "format",
        "release_bundles",
        "bytes",
        "sha256",
    }:
        raise FederatedReleaseError("federated index checkpoint is invalid")
    if artifact.get("format") != INDEX_FORMAT:
        raise FederatedReleaseError("federated index artifact format is invalid")
    release_count = _nonnegative_integer(
        artifact.get("release_bundles"), "federated release count"
    )
    if (
        _nonnegative_integer(artifact.get("bytes"), "federated index bytes")
        != len(index_raw)
        or _sha256(artifact.get("sha256"), "federated index sha256")
        != hashlib.sha256(index_raw).hexdigest()
    ):
        raise FederatedReleaseError("federated index checkpoint does not match bytes")
    if set(index) != {
        "schema_version",
        "format",
        "generated_at",
        "policy",
        "counts",
        "releases",
    }:
        raise FederatedReleaseError("federated release index schema is invalid")
    if (
        index.get("schema_version") != INDEX_SCHEMA_VERSION
        or index.get("format") != INDEX_FORMAT
        or index.get("generated_at") != generated_at
        or index.get("policy") != FEDERATION_POLICY
    ):
        raise FederatedReleaseError("federated release index identity is invalid")
    releases_value = index.get("releases")
    if not isinstance(releases_value, list) or len(releases_value) < 2:
        raise FederatedReleaseError("federated index must contain at least two releases")
    releases = [
        _validate_descriptor(value, position)
        for position, value in enumerate(releases_value)
    ]
    release_ids = [release["release_id"] for release in releases]
    references = [release["reference"] for release in releases]
    if release_ids != sorted(set(release_ids)):
        raise FederatedReleaseError("federated releases are not sorted and unique")
    if len(references) != len(set(references)):
        raise FederatedReleaseError("federated release references are not unique")
    if releases_value != releases or release_count != len(releases):
        raise FederatedReleaseError("federated release descriptors are not canonical")
    expected_counts = _aggregate_counts(releases, include_scope_splits=True)
    legacy_counts = _aggregate_counts(releases, include_scope_splits=False)
    if index.get("counts") not in (expected_counts, legacy_counts):
        raise FederatedReleaseError("federated arithmetic counts do not reconcile")

    if child_release_paths is not None:
        if set(child_release_paths) != set(release_ids):
            raise FederatedReleaseError(
                "child path mapping must exactly match federated release IDs"
            )
        for release in releases:
            release_id = release["release_id"]
            definition = _ChildDefinition(
                release_id=release_id,
                release_path=Path(child_release_paths[release_id]),
                reference=release["reference"],
                expected_manifest_sha256=release["manifest"]["sha256"],
                license_expression=release["rights"]["license_expression"],
                rights_notice=release["rights"]["rights_notice"],
            )
            if _inspect_child(definition) != release:
                raise FederatedReleaseError(
                    f"federated child descriptor drifted: {release_id}"
                )
    return index


def _bundle_payloads(bundle: FederatedIndexBundle) -> dict[str, bytes]:
    return {
        INDEX_FILENAME: bundle.index_bytes,
        MANIFEST_FILENAME: bundle.manifest_bytes,
        MANIFEST_HASH_FILENAME: bundle.manifest_hash_bytes,
    }


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


def write_federated_release_index(
    definition_path: str | Path, output_directory: str | Path
) -> Mapping[str, Any]:
    """Atomically publish one immutable, validated federation index."""
    bundle = build_federated_release_index(definition_path)
    expected = _bundle_payloads(bundle)
    output = Path(output_directory)
    if output.is_symlink():
        raise FederatedReleaseError(f"federated output may not be a symlink: {output}")
    if output.exists():
        if not output.is_dir():
            raise FederatedReleaseError(
                f"federated output is not a directory: {output}"
            )
        validate_federated_release_index(output)
        differing = [
            name
            for name, raw in expected.items()
            if (output / name).read_bytes() != raw
        ]
        if differing:
            raise FederatedReleaseError(
                "existing federated index is valid but not byte-identical; "
                f"refusing to replace: {sorted(differing)}"
            )
        return bundle.index

    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or not parent.is_dir():
        raise FederatedReleaseError(
            f"federated output parent is not a regular directory: {parent}"
        )
    if not output.name:
        raise FederatedReleaseError("federated output must have a directory basename")
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=parent)
    )
    try:
        for name, raw in expected.items():
            _write_bytes(staging / name, raw)
        validate_federated_release_index(staging)
        if output.exists() or output.is_symlink():
            raise FederatedReleaseError(
                f"federated output appeared during publication: {output}"
            )
        os.rename(staging, output)
        _fsync_directory(parent)
    except Exception:
        if staging.exists() and staging.is_dir() and not staging.is_symlink():
            shutil.rmtree(staging)
        raise
    return bundle.index


__all__ = [
    "BUNDLE_FORMAT",
    "FEDERATION_POLICY",
    "FederatedIndexBundle",
    "FederatedReleaseError",
    "INDEX_FILENAME",
    "INDEX_FORMAT",
    "MANIFEST_FILENAME",
    "MANIFEST_HASH_FILENAME",
    "build_federated_release_index",
    "validate_federated_release_index",
    "write_federated_release_index",
]
