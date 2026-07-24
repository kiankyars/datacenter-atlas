"""Atomic, read-only resolution reports between separately licensed releases.

The crosswalk is deliberately not a merged database.  It validates both child
release manifests, opens their SQLite files read-only, and emits advisory
candidate links plus exact input checkpoints.  Source rights and upstream
independence remain visible on every link and in the bundle-level summary.
"""

from __future__ import annotations

from collections import Counter
import csv
from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import io
import json
from math import isfinite
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import Any, Mapping
from urllib.parse import quote

from .global_snapshot import GlobalSnapshotError, validate_release_files
from .resolution import (
    CSV_FIELDS,
    ResolutionThresholds,
    _current_records,
    candidate_links_to_csv,
    candidate_links_to_json,
    generate_candidate_links_between,
)


BUNDLE_FORMAT = "datacenter-atlas-cross-release-resolution-v1"
RELEASE_FORMAT = "datacenter-atlas-release-v1"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
CANDIDATES_JSON_FILENAME = "resolution_candidates.json"
CANDIDATES_CSV_FILENAME = "resolution_candidates.csv"
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
LEGACY_CROSSWALK_SCOPE = {
    "review_only": True,
    "child_payloads_copied": False,
    "child_entities_merged": False,
    "automatic_resolution_allowed": False,
    "candidate_links_are_identity_claims": False,
    "candidate_links_are_independent_corroboration": False,
    "unique_physical_site_count_computed": False,
    "source_rights_collapsed": False,
}
CROSSWALK_SCOPE = {
    "review_only": True,
    "child_databases_copied": False,
    "selected_child_fields_reproduced_in_candidate_rows": True,
    "candidate_evidence_ids_reference_child_records": True,
    "candidate_fields_remain_subject_to_child_rights": True,
    "child_entities_merged": False,
    "automatic_resolution_allowed": False,
    "candidate_links_are_identity_claims": False,
    "candidate_links_are_independent_corroboration": False,
    "unique_physical_site_count_computed": False,
    "source_rights_collapsed": False,
}
SIGNAL_FIELDS = frozenset(
    {
        "address_similarity",
        "country_left",
        "country_match",
        "country_right",
        "distance_score",
        "geometry_bounds_overlap",
        "geometry_left_bounds_contain_right",
        "geometry_left_contains_right",
        "geometry_right_bounds_contain_left",
        "geometry_right_contains_left",
        "geometry_score",
        "name_similarity",
        "exact_upstream_identity_match",
        "matching_upstream_identities",
        "owner_operator_similarity",
        "left_source_root",
        "right_source_root",
        "source_independent",
    }
)


class CrossReleaseResolutionError(ValueError):
    """Raised when a release or crosswalk fails its immutable contract."""


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


def _timestamp(value: str, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CrossReleaseResolutionError(f"{label} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CrossReleaseResolutionError(f"{label} must be ISO 8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CrossReleaseResolutionError(f"{label} must include a timezone")
    canonical = parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    if canonical != value:
        raise CrossReleaseResolutionError(
            f"{label} must use canonical UTC whole seconds"
        )
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CrossReleaseResolutionError(f"{label} must be non-empty text")
    return value.strip()


def _json_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise CrossReleaseResolutionError(f"{label} must be a regular file: {path}")
    raw = path.read_bytes()
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CrossReleaseResolutionError(f"{label} must be valid UTF-8 JSON") from error
    if not isinstance(document, dict):
        raise CrossReleaseResolutionError(f"{label} must be a JSON object")
    return document, raw


def _release_input(path: str | Path, label: str) -> dict[str, Any]:
    supplied = Path(path)
    if supplied.is_symlink() or not supplied.is_dir():
        raise CrossReleaseResolutionError(
            f"{label} release must be a regular directory"
        )
    directory = supplied.resolve()
    try:
        manifest = validate_release_files(directory)
    except GlobalSnapshotError as error:
        raise CrossReleaseResolutionError(
            f"{label} release validation failed: {error}"
        ) from error
    if manifest.get("format") != RELEASE_FORMAT:
        raise CrossReleaseResolutionError(f"{label} release format is unsupported")
    manifest_path = directory / MANIFEST_FILENAME
    manifest_raw = manifest_path.read_bytes()
    files = manifest.get("files")
    if not isinstance(files, Mapping) or "atlas.sqlite" not in files:
        raise CrossReleaseResolutionError(
            f"{label} release does not bind atlas.sqlite"
        )
    database_path = directory / "atlas.sqlite"
    if database_path.is_symlink() or not database_path.is_file():
        raise CrossReleaseResolutionError(
            f"{label} atlas.sqlite must be a regular file"
        )
    as_of = _text(manifest.get("as_of"), f"{label} as_of")
    recorded_at = _timestamp(manifest.get("recorded_at"), f"{label} recorded_at")
    source_families = manifest.get("source_families")
    if not isinstance(source_families, list) or not all(
        isinstance(item, str) and item for item in source_families
    ):
        raise CrossReleaseResolutionError(
            f"{label} source_families must be a text array"
        )
    attribution_path = directory / ATTRIBUTION_FILENAME
    if attribution_path.is_symlink() or not attribution_path.is_file():
        raise CrossReleaseResolutionError(
            f"{label} release attribution must be a regular file"
        )
    return {
        "directory": directory,
        "database_path": database_path,
        "manifest": manifest,
        "manifest_checkpoint": {
            "bytes": len(manifest_raw),
            "sha256": _sha256(manifest_raw),
        },
        "database_checkpoint": _file_checkpoint(database_path),
        "as_of": as_of,
        "recorded_at": recorded_at,
        "source_families": sorted(set(source_families)),
        "attribution": attribution_path.read_text(encoding="utf-8"),
    }


def _assert_release_unchanged(release: Mapping[str, Any], label: str) -> None:
    current = _release_input(release["directory"], label)
    compared_fields = (
        "manifest",
        "manifest_checkpoint",
        "database_checkpoint",
        "as_of",
        "recorded_at",
        "source_families",
        "attribution",
    )
    if any(current[field] != release[field] for field in compared_fields):
        raise CrossReleaseResolutionError(
            f"{label} release changed while the crosswalk was being built"
        )


def _read_only_connection(path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(str(path), safe='/')}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _input_manifest_record(release: Mapping[str, Any], label: str) -> dict[str, Any]:
    manifest = release["manifest"]
    return {
        "label": label,
        "release_directory_name": release["directory"].name,
        "release_manifest": release["manifest_checkpoint"],
        "atlas_sqlite": release["database_checkpoint"],
        "as_of": release["as_of"],
        "recorded_at": release["recorded_at"],
        "source_families": release["source_families"],
        "source_scoped_entity_records": manifest.get("entities"),
        "review_only": manifest.get("review_only", False),
    }


def _summary(candidates: list[Any], left_records: int, right_records: int) -> dict[str, Any]:
    relationships = Counter(
        candidate.relationship_suggestion for candidate in candidates
    )
    independence = Counter(
        "independent" if candidate.signals.get("source_independent") else "shared_root"
        for candidate in candidates
    )
    source_root_pairs = Counter(
        " | ".join(
            (
                str(candidate.signals.get("left_source_root") or "unknown"),
                str(candidate.signals.get("right_source_root") or "unknown"),
            )
        )
        for candidate in candidates
    )
    relationship_independence = Counter(
        " | ".join(
            (
                candidate.relationship_suggestion,
                "independent"
                if candidate.signals.get("source_independent")
                else "shared_root",
            )
        )
        for candidate in candidates
    )
    exact_identity_candidates = [
        candidate
        for candidate in candidates
        if candidate.signals.get("exact_upstream_identity_match")
    ]
    exact_identity_independence = Counter(
        "independent"
        if candidate.signals.get("source_independent")
        else "shared_root"
        for candidate in exact_identity_candidates
    )
    return {
        "left_current_campus_facility_records_with_coordinates": left_records,
        "right_current_campus_facility_records_with_coordinates": right_records,
        "candidate_links": len(candidates),
        "candidate_links_by_relationship_suggestion": dict(sorted(relationships.items())),
        "candidate_links_by_source_independence": dict(sorted(independence.items())),
        "candidate_links_by_source_root_pair": dict(sorted(source_root_pairs.items())),
        "candidate_links_by_relationship_and_source_independence": dict(
            sorted(relationship_independence.items())
        ),
        "exact_upstream_identity_candidate_links": len(exact_identity_candidates),
        "exact_upstream_identity_links_by_source_independence": dict(
            sorted(exact_identity_independence.items())
        ),
        "same_site_or_part_of_candidate_links": sum(
            relationships[relationship]
            for relationship in ("same_site_candidate", "part_of_candidate")
        ),
        "unique_physical_sites": None,
    }


def _readme(left_label: str, right_label: str, summary: Mapping[str, Any]) -> bytes:
    relationships = summary["candidate_links_by_relationship_suggestion"]
    return (
        "# Data Center Atlas cross-release resolution candidates\n\n"
        f"This immutable review bundle compares `{left_label}` with `{right_label}` and emits "
        f"{summary['candidate_links']:,} spatial or exact-upstream-identity candidate links. "
        "Spatial links use the published resolution threshold; a typed upstream identity is "
        "retained even when conflicting coordinates fall outside it. The bundle does not copy "
        "either child database, merge any entity, or "
        "compute a unique-site total.\n\n"
        f"The bundle contains {summary.get('exact_upstream_identity_candidate_links', 0):,} "
        "typed upstream-identity links and "
        f"{summary.get('same_site_or_part_of_candidate_links', 0):,} same-site or part-of "
        "suggestions. These subsets are still advisory.\n\n"
        f"Relationship suggestions are {json.dumps(relationships, sort_keys=True)}. "
        "They are ranking hints, not adjudicated identity claims. Every row retains both entity "
        "and evidence IDs, distance, the explainable scoring signals, and whether the two records "
        "share an upstream provenance root. A shared root is not independent corroboration.\n\n"
        "`manifest.json` binds the exact child manifests and SQLite databases used for the "
        "comparison. The child attributions and license obligations remain applicable to their "
        "respective referenced fields; this crosswalk does not replace or collapse them.\n"
    ).encode("utf-8")


def _canonical_candidate_csv(rows: list[dict[str, Any]]) -> str:
    json_fields = (set(CSV_FIELDS) - {"signals_json"}) | {"signals"}
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        if set(row) != json_fields or not isinstance(row.get("signals"), dict):
            raise CrossReleaseResolutionError("crosswalk candidate schema is invalid")
        csv_row = dict(row)
        csv_row["signals_json"] = json.dumps(
            csv_row.pop("signals"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        writer.writerow(csv_row)
    return stream.getvalue()


def _candidate_number(
    value: Any, label: str, *, minimum: float, maximum: float | None = None
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CrossReleaseResolutionError(f"{label} must be numeric")
    result = float(value)
    if not isfinite(result) or result < minimum or (
        maximum is not None and result > maximum
    ):
        raise CrossReleaseResolutionError(f"{label} is outside its valid range")
    return result


def _candidate_text(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    result = _text(value, label)
    if result != value:
        raise CrossReleaseResolutionError(f"{label} has surrounding whitespace")
    return result


def _validate_candidate_row(
    row: Any, thresholds: ResolutionThresholds
) -> tuple[str, str]:
    json_fields = (set(CSV_FIELDS) - {"signals_json"}) | {"signals"}
    if not isinstance(row, dict) or set(row) != json_fields:
        raise CrossReleaseResolutionError("crosswalk candidate schema is invalid")

    relationship = row["relationship_suggestion"]
    if relationship not in {
        "same_site_candidate",
        "part_of_candidate",
        "nearby_only",
    }:
        raise CrossReleaseResolutionError(
            "crosswalk candidate relationship is invalid"
        )
    score = _candidate_number(row["score"], "candidate score", minimum=0, maximum=1)
    distance = _candidate_number(
        row["distance_m"], "candidate distance_m", minimum=0
    )
    left_id = _candidate_text(row["left_entity_id"], "left entity ID")
    right_id = _candidate_text(row["right_entity_id"], "right entity ID")
    left_kind = _candidate_text(row["left_entity_kind"], "left entity kind")
    right_kind = _candidate_text(row["right_entity_kind"], "right entity kind")
    if left_kind not in {"campus", "facility"} or right_kind not in {
        "campus",
        "facility",
    }:
        raise CrossReleaseResolutionError(
            "crosswalk candidate entity kind is unsupported"
        )
    for side in ("left", "right"):
        _candidate_text(row[f"{side}_name"], f"{side} name", nullable=True)
        _candidate_text(row[f"{side}_source_family"], f"{side} source family")
        _candidate_text(row[f"{side}_evidence_id"], f"{side} evidence ID")
    parent_id = _candidate_text(
        row["suggested_parent_entity_id"], "suggested parent entity ID", nullable=True
    )
    child_id = _candidate_text(
        row["suggested_child_entity_id"], "suggested child entity ID", nullable=True
    )

    signals = row["signals"]
    if not isinstance(signals, dict) or set(signals) != SIGNAL_FIELDS:
        raise CrossReleaseResolutionError("crosswalk candidate signals are invalid")
    similarities = {
        field: _candidate_number(
            signals[field], f"candidate signal {field}", minimum=0, maximum=1
        )
        for field in (
            "address_similarity",
            "distance_score",
            "geometry_score",
            "name_similarity",
            "owner_operator_similarity",
        )
    }
    boolean_fields = (
        "geometry_bounds_overlap",
        "geometry_left_bounds_contain_right",
        "geometry_left_contains_right",
        "geometry_right_bounds_contain_left",
        "geometry_right_contains_left",
        "exact_upstream_identity_match",
        "source_independent",
    )
    if any(not isinstance(signals[field], bool) for field in boolean_fields):
        raise CrossReleaseResolutionError(
            "crosswalk candidate boolean signal is invalid"
        )
    for field in ("country_left", "country_right"):
        _candidate_text(signals[field], f"candidate signal {field}", nullable=True)
    country_match = signals["country_match"]
    if country_match is not None and not isinstance(country_match, bool):
        raise CrossReleaseResolutionError(
            "crosswalk candidate country_match signal is invalid"
        )
    left_country = signals["country_left"]
    right_country = signals["country_right"]
    expected_country_match = (
        left_country == right_country
        if left_country is not None and right_country is not None
        else None
    )
    if country_match != expected_country_match or country_match is False:
        raise CrossReleaseResolutionError(
            "crosswalk candidate country signals do not reconcile"
        )
    left_root = _candidate_text(
        signals["left_source_root"], "candidate left source root"
    )
    right_root = _candidate_text(
        signals["right_source_root"], "candidate right source root"
    )
    if signals["source_independent"] != (left_root != right_root):
        raise CrossReleaseResolutionError(
            "crosswalk candidate source independence does not reconcile"
        )
    identities = signals["matching_upstream_identities"]
    if (
        not isinstance(identities, list)
        or identities != sorted(set(identities))
        or any(not isinstance(identity, str) or not identity for identity in identities)
        or signals["exact_upstream_identity_match"] != bool(identities)
    ):
        raise CrossReleaseResolutionError(
            "crosswalk candidate upstream identities do not reconcile"
        )
    exact_identity = signals["exact_upstream_identity_match"]
    expected_score = (
        0.35 * similarities["distance_score"]
        + 0.30 * similarities["name_similarity"]
        + 0.15 * similarities["address_similarity"]
        + 0.12 * similarities["owner_operator_similarity"]
        + 0.08 * similarities["geometry_score"]
    )
    if exact_identity:
        expected_score = max(expected_score, 0.99)
    expected_score = round(min(1.0, max(0.0, expected_score)), 6)
    if abs(score - expected_score) > 0.0000005:
        raise CrossReleaseResolutionError(
            "crosswalk candidate score does not reconcile with signals"
        )
    if distance > thresholds.nearby_max_distance_m + 0.001 and not exact_identity:
        raise CrossReleaseResolutionError(
            "crosswalk candidate exceeds the nearby gate without exact identity"
        )

    if left_kind != right_kind:
        expected_relationship = (
            "part_of_candidate"
            if distance <= thresholds.part_of_max_distance_m + 0.001
            and score >= thresholds.part_of_min_score
            else "nearby_only"
        )
    else:
        expected_relationship = (
            "same_site_candidate"
            if distance <= thresholds.same_site_max_distance_m + 0.001
            and score >= thresholds.same_site_min_score
            else "nearby_only"
        )
    if relationship != expected_relationship:
        raise CrossReleaseResolutionError(
            "crosswalk candidate relationship does not satisfy thresholds"
        )
    if relationship == "part_of_candidate":
        expected_parent = left_id if left_kind == "campus" else right_id
        expected_child = right_id if left_kind == "campus" else left_id
        if parent_id != expected_parent or child_id != expected_child:
            raise CrossReleaseResolutionError(
                "crosswalk candidate part-of orientation is invalid"
            )
    elif parent_id is not None or child_id is not None:
        raise CrossReleaseResolutionError(
            "crosswalk non-part-of candidate contains topology pointers"
        )
    return left_id, right_id


def build_cross_release_resolution(
    left_release: str | Path,
    right_release: str | Path,
    output_directory: str | Path,
    *,
    left_label: str,
    right_label: str,
    generated_at: str,
    thresholds: ResolutionThresholds | None = None,
) -> dict[str, Any]:
    """Build an atomic candidate crosswalk between two immutable releases."""

    left_label = _text(left_label, "left_label")
    right_label = _text(right_label, "right_label")
    if left_label == right_label:
        raise CrossReleaseResolutionError("left and right labels must differ")
    generated_at = _timestamp(generated_at, "generated_at")
    thresholds = thresholds or ResolutionThresholds()
    left = _release_input(left_release, "left")
    right = _release_input(right_release, "right")
    if left["manifest_checkpoint"] == right["manifest_checkpoint"]:
        raise CrossReleaseResolutionError("left and right releases must differ")

    destination = Path(os.path.abspath(os.fspath(output_directory)))
    if destination.exists() or destination.is_symlink():
        raise CrossReleaseResolutionError(
            f"refusing existing output directory: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent)
    )
    left_connection: sqlite3.Connection | None = None
    right_connection: sqlite3.Connection | None = None
    try:
        left_connection = _read_only_connection(left["database_path"])
        right_connection = _read_only_connection(right["database_path"])
        left_records = _current_records(
            left_connection,
            as_of=left["as_of"],
            recorded_at=left["recorded_at"],
        )
        right_records = _current_records(
            right_connection,
            as_of=right["as_of"],
            recorded_at=right["recorded_at"],
        )
        candidates = generate_candidate_links_between(
            left_connection,
            right_connection,
            left_as_of=left["as_of"],
            left_recorded_at=left["recorded_at"],
            right_as_of=right["as_of"],
            right_recorded_at=right["recorded_at"],
            thresholds=thresholds,
        )
        summary = _summary(candidates, len(left_records), len(right_records))
        documents = {
            CANDIDATES_JSON_FILENAME: candidate_links_to_json(candidates).encode("utf-8"),
            CANDIDATES_CSV_FILENAME: candidate_links_to_csv(candidates).encode("utf-8"),
            SUMMARY_FILENAME: _canonical_json(summary),
            README_FILENAME: _readme(left_label, right_label, summary),
            ATTRIBUTION_FILENAME: (
                f"[{left_label}]\n{left['attribution'].rstrip()}\n\n"
                f"[{right_label}]\n{right['attribution'].rstrip()}\n"
            ).encode("utf-8"),
        }
        for filename, raw in documents.items():
            (stage / filename).write_bytes(raw)
        manifest = {
            "format": BUNDLE_FORMAT,
            "generated_at": generated_at,
            "left_input": _input_manifest_record(left, left_label),
            "right_input": _input_manifest_record(right, right_label),
            "thresholds": asdict(thresholds),
            "scope": CROSSWALK_SCOPE,
            "counts": summary,
            "files": {
                filename: {
                    "bytes": len(raw),
                    "sha256": _sha256(raw),
                }
                for filename, raw in sorted(documents.items())
            },
        }
        manifest_raw = _canonical_json(manifest)
        (stage / MANIFEST_FILENAME).write_bytes(manifest_raw)
        (stage / MANIFEST_HASH_FILENAME).write_text(
            f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n", encoding="ascii"
        )
        validate_cross_release_resolution(stage)
        if left_connection is not None:
            left_connection.close()
            left_connection = None
        if right_connection is not None:
            right_connection.close()
            right_connection = None
        _assert_release_unchanged(left, "left")
        _assert_release_unchanged(right, "right")
        stage.replace(destination)
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise
    finally:
        if left_connection is not None:
            left_connection.close()
        if right_connection is not None:
            right_connection.close()

    return manifest


def validate_cross_release_resolution(path: str | Path) -> dict[str, Any]:
    """Validate a completed crosswalk entirely offline."""

    directory = Path(path)
    if directory.is_symlink() or not directory.is_dir():
        raise CrossReleaseResolutionError("crosswalk must be a regular directory")
    entries = list(directory.iterdir())
    if any(not item.is_file() or item.is_symlink() for item in entries):
        raise CrossReleaseResolutionError("crosswalk entries must be regular files")
    if {item.name for item in entries} != BUNDLE_FILES:
        raise CrossReleaseResolutionError("crosswalk file inventory is invalid")
    manifest, manifest_raw = _json_object(
        directory / MANIFEST_FILENAME, "crosswalk manifest"
    )
    if manifest.get("format") != BUNDLE_FORMAT:
        raise CrossReleaseResolutionError("crosswalk format is unsupported")
    _timestamp(manifest.get("generated_at"), "crosswalk generated_at")
    if manifest.get("scope") not in (CROSSWALK_SCOPE, LEGACY_CROSSWALK_SCOPE):
        raise CrossReleaseResolutionError("crosswalk scope contract is invalid")
    threshold_document = manifest.get("thresholds")
    if not isinstance(threshold_document, dict):
        raise CrossReleaseResolutionError("crosswalk thresholds are invalid")
    try:
        validated_thresholds = ResolutionThresholds(**threshold_document)
    except (TypeError, ValueError) as error:
        raise CrossReleaseResolutionError("crosswalk thresholds are invalid") from error
    if asdict(validated_thresholds) != threshold_document:
        raise CrossReleaseResolutionError("crosswalk thresholds are non-canonical")
    for side in ("left_input", "right_input"):
        child = manifest.get(side)
        if not isinstance(child, dict):
            raise CrossReleaseResolutionError(f"crosswalk {side} is invalid")
        for checkpoint_name in ("release_manifest", "atlas_sqlite"):
            checkpoint = child.get(checkpoint_name)
            if (
                not isinstance(checkpoint, dict)
                or set(checkpoint) != {"bytes", "sha256"}
                or isinstance(checkpoint.get("bytes"), bool)
                or not isinstance(checkpoint.get("bytes"), int)
                or checkpoint["bytes"] < 0
                or not isinstance(checkpoint.get("sha256"), str)
                or len(checkpoint["sha256"]) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in checkpoint["sha256"]
                )
            ):
                raise CrossReleaseResolutionError(
                    f"crosswalk {side} {checkpoint_name} checkpoint is invalid"
                )
        _text(child.get("label"), f"crosswalk {side} label")
        _text(
            child.get("release_directory_name"),
            f"crosswalk {side} release directory name",
        )
        _text(child.get("as_of"), f"crosswalk {side} as_of")
        _timestamp(child.get("recorded_at"), f"crosswalk {side} recorded_at")
        source_families = child.get("source_families")
        if (
            not isinstance(source_families, list)
            or not all(isinstance(item, str) and item for item in source_families)
            or source_families != sorted(set(source_families))
        ):
            raise CrossReleaseResolutionError(
                f"crosswalk {side} source families are invalid"
            )
    if manifest["left_input"]["label"] == manifest["right_input"]["label"]:
        raise CrossReleaseResolutionError("crosswalk input labels must differ")
    files = manifest.get("files")
    expected_payloads = BUNDLE_FILES - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    if not isinstance(files, Mapping) or set(files) != expected_payloads:
        raise CrossReleaseResolutionError("crosswalk manifest file inventory is invalid")
    for filename in sorted(expected_payloads):
        record = files[filename]
        if not isinstance(record, Mapping) or set(record) != {"bytes", "sha256"}:
            raise CrossReleaseResolutionError(
                f"crosswalk checkpoint is invalid: {filename}"
            )
        if _file_checkpoint(directory / filename) != dict(record):
            raise CrossReleaseResolutionError(
                f"crosswalk file checkpoint does not match: {filename}"
            )
    expected_sidecar = f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    if (directory / MANIFEST_HASH_FILENAME).read_bytes() != expected_sidecar:
        raise CrossReleaseResolutionError("crosswalk manifest sidecar does not match")

    try:
        candidates = json.loads(
            (directory / CANDIDATES_JSON_FILENAME).read_text(encoding="utf-8")
        )
        summary = json.loads((directory / SUMMARY_FILENAME).read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CrossReleaseResolutionError("crosswalk JSON payload is invalid") from error
    if not isinstance(candidates, list) or not isinstance(summary, dict):
        raise CrossReleaseResolutionError("crosswalk JSON payload schema is invalid")
    if summary != manifest.get("counts") or summary.get("candidate_links") != len(candidates):
        raise CrossReleaseResolutionError("crosswalk counts do not reconcile")
    if summary.get("unique_physical_sites", object()) is not None:
        raise CrossReleaseResolutionError(
            "crosswalk must not report a unique physical site count"
        )
    relationship_counts: Counter[str] = Counter()
    independence_counts: Counter[str] = Counter()
    source_root_counts: Counter[str] = Counter()
    relationship_independence_counts: Counter[str] = Counter()
    exact_identity_independence_counts: Counter[str] = Counter()
    exact_identity_count = 0
    for row in candidates:
        _validate_candidate_row(row, validated_thresholds)
        relationship = row.get("relationship_suggestion")
        if relationship not in {
            "same_site_candidate",
            "part_of_candidate",
            "nearby_only",
        }:
            raise CrossReleaseResolutionError(
                "crosswalk candidate relationship is invalid"
            )
        relationship_counts[relationship] += 1
        signals = row["signals"]
        independent = signals.get("source_independent")
        if not isinstance(independent, bool):
            raise CrossReleaseResolutionError(
                "crosswalk candidate independence signal is invalid"
            )
        independence_counts["independent" if independent else "shared_root"] += 1
        relationship_independence_counts[
            " | ".join(
                (
                    relationship,
                    "independent" if independent else "shared_root",
                )
            )
        ] += 1
        if signals.get("exact_upstream_identity_match"):
            exact_identity_count += 1
            exact_identity_independence_counts[
                "independent" if independent else "shared_root"
            ] += 1
        source_root_counts[
            " | ".join(
                (
                    str(signals.get("left_source_root") or "unknown"),
                    str(signals.get("right_source_root") or "unknown"),
                )
            )
        ] += 1
    if summary.get("candidate_links_by_relationship_suggestion") != dict(
        sorted(relationship_counts.items())
    ):
        raise CrossReleaseResolutionError(
            "crosswalk relationship counts do not reconcile"
        )
    if summary.get("candidate_links_by_source_independence") != dict(
        sorted(independence_counts.items())
    ):
        raise CrossReleaseResolutionError(
            "crosswalk independence counts do not reconcile"
        )
    if summary.get("candidate_links_by_source_root_pair") != dict(
        sorted(source_root_counts.items())
    ):
        raise CrossReleaseResolutionError(
            "crosswalk source-root counts do not reconcile"
        )
    if "candidate_links_by_relationship_and_source_independence" in summary:
        if summary["candidate_links_by_relationship_and_source_independence"] != dict(
            sorted(relationship_independence_counts.items())
        ):
            raise CrossReleaseResolutionError(
                "crosswalk relationship-independence counts do not reconcile"
            )
        if summary.get("exact_upstream_identity_candidate_links") != exact_identity_count:
            raise CrossReleaseResolutionError(
                "crosswalk exact-identity count does not reconcile"
            )
        if summary.get("exact_upstream_identity_links_by_source_independence") != dict(
            sorted(exact_identity_independence_counts.items())
        ):
            raise CrossReleaseResolutionError(
                "crosswalk exact-identity independence counts do not reconcile"
            )
        if summary.get("same_site_or_part_of_candidate_links") != sum(
            relationship_counts[relationship]
            for relationship in ("same_site_candidate", "part_of_candidate")
        ):
            raise CrossReleaseResolutionError(
                "crosswalk topology-suggestion counts do not reconcile"
            )
    try:
        csv_text = (directory / CANDIDATES_CSV_FILENAME).read_text(encoding="utf-8")
        canonical_csv = _canonical_candidate_csv(candidates)
    except (UnicodeDecodeError, csv.Error) as error:
        raise CrossReleaseResolutionError("crosswalk CSV is invalid") from error
    if csv_text != canonical_csv:
        raise CrossReleaseResolutionError("crosswalk CSV and JSON rows differ")
    json_pairs = [
        (row.get("left_entity_id"), row.get("right_entity_id"))
        for row in candidates
        if isinstance(row, dict)
    ]
    if len(json_pairs) != len(candidates):
        raise CrossReleaseResolutionError("crosswalk candidate schema is invalid")
    if len(set(json_pairs)) != len(json_pairs):
        raise CrossReleaseResolutionError("crosswalk contains duplicate entity pairs")
    if json_pairs != sorted(json_pairs):
        raise CrossReleaseResolutionError("crosswalk candidate rows are not sorted")
    return manifest


__all__ = [
    "BUNDLE_FORMAT",
    "CROSSWALK_SCOPE",
    "LEGACY_CROSSWALK_SCOPE",
    "CrossReleaseResolutionError",
    "build_cross_release_resolution",
    "validate_cross_release_resolution",
]
