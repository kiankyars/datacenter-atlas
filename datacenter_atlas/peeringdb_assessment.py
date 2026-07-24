"""Fail-closed validation for the PeeringDB source-rights assessment.

This module deliberately does not fetch PeeringDB facility rows.  The current
PeeringDB Acceptable Use Policy does not provide a clear bulk-redistribution or
commercial-use grant for Data Center Atlas.  It validates a metadata-only
assessment bundle and can audit an immutable Scrutica release for rows whose
declared upstream source is PeeringDB.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping
from urllib.parse import quote, urlsplit

from .global_snapshot import GlobalSnapshotError, validate_release_files


ASSESSMENT_FILENAME = "assessment.json"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
SCHEMA_VERSION = 1
ASSESSMENT_FORMAT = "datacenter-atlas-source-rights-assessment-v1"
PEERINGDB_SOURCE = "peeringdb"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_FILES = {
    ASSESSMENT_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
}
_PEERINGDB_HOSTS = {"www.peeringdb.com", "docs.peeringdb.com"}
_QUARANTINED_DEPENDENT_TABLES = (
    "entity_snapshots",
    "capacity_estimates",
    "lifecycle_observations",
    "operating_model_observations",
    "workload_observations",
)


class PeeringDBAssessmentError(ValueError):
    """Raised when the PeeringDB rights assessment fails closed."""


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PeeringDBAssessmentError(f"{field} must be a non-empty timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PeeringDBAssessmentError(f"{field} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PeeringDBAssessmentError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PeeringDBAssessmentError(f"{field} must be an object")
    return value


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise PeeringDBAssessmentError(f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PeeringDBAssessmentError(f"invalid {label}") from error
    if not isinstance(value, dict):
        raise PeeringDBAssessmentError(f"{label} must contain an object")
    if path.read_bytes() != _canonical_json(value):
        raise PeeringDBAssessmentError(f"{label} is not canonical JSON")
    return value


def _validate_retrievals(retrievals: Any) -> None:
    if not isinstance(retrievals, list) or not retrievals:
        raise PeeringDBAssessmentError("official_retrievals must be a non-empty list")
    source_ids: set[str] = set()
    for index, raw in enumerate(retrievals):
        record = _object(raw, f"official_retrievals[{index}]")
        source_id = record.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise PeeringDBAssessmentError("retrieval source_id must be non-empty")
        if source_id in source_ids:
            raise PeeringDBAssessmentError("retrieval source_id values must be unique")
        source_ids.add(source_id)
        url = record.get("url")
        if not isinstance(url, str):
            raise PeeringDBAssessmentError("retrieval URL must be text")
        parsed = urlsplit(url)
        if parsed.scheme != "https":
            raise PeeringDBAssessmentError("retrieval URL must use HTTPS")
        publisher = record.get("publisher")
        if publisher == "PeeringDB" and parsed.hostname not in _PEERINGDB_HOSTS:
            raise PeeringDBAssessmentError(
                "PeeringDB evidence must use an official PeeringDB host"
            )
        _timestamp(record.get("retrieved_at"), "retrieval retrieved_at")
        if record.get("http_status") != 200:
            raise PeeringDBAssessmentError("retrieval HTTP status must be 200")
        byte_count = record.get("bytes")
        digest = record.get("sha256")
        if (
            isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count <= 0
        ):
            raise PeeringDBAssessmentError("retrieval bytes must be positive")
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            raise PeeringDBAssessmentError("retrieval SHA-256 is invalid")
        if record.get("raw_artifact_retained") is not False:
            raise PeeringDBAssessmentError(
                "rights assessment must not retain fetched source documents"
            )
    required = {
        "peeringdb_acceptable_use_policy",
        "peeringdb_live_openapi_schema",
        "peeringdb_anonymous_facility_probe",
        "peeringdb_facility_operator_howto",
        "peeringdb_facility_approval_guidelines",
    }
    if not required.issubset(source_ids):
        raise PeeringDBAssessmentError("required official evidence is missing")


def validate_assessment_document(document: Mapping[str, Any]) -> None:
    """Validate the fail-closed semantics of one assessment document."""

    if document.get("schema_version") != SCHEMA_VERSION:
        raise PeeringDBAssessmentError("unsupported assessment schema version")
    if document.get("format") != ASSESSMENT_FORMAT:
        raise PeeringDBAssessmentError("unsupported assessment format")
    if document.get("assessment_id") != "peeringdb-2026-07-18-v1":
        raise PeeringDBAssessmentError("unexpected assessment ID")
    _timestamp(document.get("assessed_at"), "assessed_at")
    _validate_retrievals(document.get("official_retrievals"))

    probe = _object(document.get("api_probe"), "api_probe")
    if (
        probe.get("authentication") != "anonymous"
        or probe.get("http_status") != 200
        or probe.get("records_requested") != 1
        or probe.get("records_returned") != 1
        or probe.get("records_released") != 0
        or probe.get("raw_response_retained") is not False
    ):
        raise PeeringDBAssessmentError("API probe must remain metadata-only")
    if probe.get("facility_count_at_probe") != 5857:
        raise PeeringDBAssessmentError("facility count differs from pinned probe")

    fields = _object(document.get("field_assessment"), "field_assessment")
    missing = fields.get("structured_fields_not_available")
    required_missing = {
        "annual_energy_mwh",
        "construction_lifecycle_status",
        "gross_power_capacity_mw",
        "it_load_mw",
        "pue",
        "workload_type",
    }
    if not isinstance(missing, list) or not required_missing.issubset(missing):
        raise PeeringDBAssessmentError("required PeeringDB field gaps are missing")
    if fields.get("status_is_construction_lifecycle") is not False:
        raise PeeringDBAssessmentError(
            "PeeringDB status must not be treated as lifecycle"
        )
    if fields.get("voltage_is_power_capacity_or_consumption") is not False:
        raise PeeringDBAssessmentError("voltage categories must not become power metrics")

    rights = _object(document.get("rights_assessment"), "rights_assessment")
    required_false = (
        "bulk_redistribution_approval_evidenced",
        "commercial_use_permission_clear",
        "direct_release_permitted",
        "permission_from_peeringdb_evidenced",
    )
    if any(rights.get(field) is not False for field in required_false):
        raise PeeringDBAssessmentError("PeeringDB rights must fail closed")

    decision = _object(document.get("atlas_decision"), "atlas_decision")
    if (
        decision.get("status") != "blocked_pending_written_permission"
        or decision.get("bulk_fetch_permitted") is not False
        or decision.get("build_release_permitted") is not False
        or decision.get("publication_eligible") is not False
    ):
        raise PeeringDBAssessmentError("Atlas PeeringDB decision must fail closed")

    dependency = _object(
        document.get("dependency_constraints"), "dependency_constraints"
    )
    if (
        dependency.get("scrutica_peeringdb_is_independent_corroboration") is not False
        or dependency.get("direct_peeringdb_plus_scrutica_peeringdb_counts_as_two_sources")
        is not False
    ):
        raise PeeringDBAssessmentError("PeeringDB dependency must not be double counted")

    conflict = _object(
        document.get("scrutica_upstream_rights_conflict"),
        "scrutica_upstream_rights_conflict",
    )
    exact_counts = {
        "peeringdb_evidence_rows": 1548,
        "peeringdb_entity_rows": 1548,
        "cc_by_sa_labeled_peeringdb_evidence_rows": 1548,
        "permission_evidence_recorded_rows": 0,
    }
    if any(conflict.get(key) != value for key, value in exact_counts.items()):
        raise PeeringDBAssessmentError("Scrutica PeeringDB conflict counts changed")
    if (
        conflict.get("conflict_detected") is not True
        or conflict.get("relabel_alone_is_sufficient") is not False
        or conflict.get("publication_eligible") is not False
        or conflict.get("required_action")
        != "quarantine_or_exclude_until_rights_are_evidenced"
    ):
        raise PeeringDBAssessmentError("Scrutica publication rule must fail closed")


def validate_assessment_bundle(path: str | Path) -> dict[str, Any]:
    """Validate the exact, immutable metadata-only assessment bundle."""

    directory = Path(path)
    if directory.is_symlink() or not directory.is_dir():
        raise PeeringDBAssessmentError("assessment bundle must be a directory")
    entries = list(directory.iterdir())
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise PeeringDBAssessmentError("assessment bundle entries must be regular files")
    actual = {entry.name for entry in entries}
    if actual != _EXPECTED_FILES:
        raise PeeringDBAssessmentError(
            f"assessment bundle file set differs: {sorted(actual)}"
        )

    assessment = _load_json(directory / ASSESSMENT_FILENAME, "assessment")
    validate_assessment_document(assessment)
    manifest = _load_json(directory / MANIFEST_FILENAME, "assessment manifest")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != ASSESSMENT_FORMAT
        or manifest.get("assessment_id") != assessment.get("assessment_id")
        or manifest.get("generated_at") != assessment.get("assessed_at")
    ):
        raise PeeringDBAssessmentError("assessment manifest identity is invalid")
    files = _object(manifest.get("files"), "manifest files")
    if set(files) != {ASSESSMENT_FILENAME}:
        raise PeeringDBAssessmentError("assessment manifest must pin assessment.json")
    record = _object(files[ASSESSMENT_FILENAME], "assessment file record")
    assessment_path = directory / ASSESSMENT_FILENAME
    if (
        record.get("bytes") != assessment_path.stat().st_size
        or record.get("sha256") != _sha256(assessment_path)
    ):
        raise PeeringDBAssessmentError("assessment file hash mismatch")
    expected_sidecar = f"{_sha256(directory / MANIFEST_FILENAME)}  manifest.json\n"
    if (directory / MANIFEST_HASH_FILENAME).read_text(encoding="utf-8") != expected_sidecar:
        raise PeeringDBAssessmentError("assessment manifest sidecar mismatch")
    return assessment


def _read_only_connection(database: Path) -> sqlite3.Connection:
    if database.is_symlink() or not database.is_file():
        raise PeeringDBAssessmentError("Scrutica atlas.sqlite must be a regular file")
    uri = f"file:{quote(str(database.resolve()))}?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.execute("PRAGMA query_only = ON")
    except sqlite3.Error as error:
        raise PeeringDBAssessmentError("cannot open Scrutica SQLite read-only") from error
    return connection


def _permission_evidenced(metadata: Mapping[str, Any]) -> bool:
    permission = metadata.get("peeringdb_permission")
    if not isinstance(permission, Mapping):
        return False
    digest = permission.get("document_sha256")
    reference = permission.get("permission_reference")
    return bool(
        permission.get("approval_status") == "approved"
        and permission.get("granted_by") == "PeeringDB"
        and permission.get("bulk_redistribution") is True
        and isinstance(digest, str)
        and _SHA256_RE.fullmatch(digest)
        and isinstance(reference, str)
        and reference.strip()
    )


def audit_scrutica_peeringdb_rights(release_directory: str | Path) -> dict[str, Any]:
    """Audit PeeringDB-derived rows without modifying the immutable release."""

    directory = Path(release_directory)
    try:
        validate_release_files(directory)
    except (GlobalSnapshotError, OSError) as error:
        raise PeeringDBAssessmentError("Scrutica release files are invalid") from error
    manifest_path = directory / "manifest.json"
    attribution_path = directory / "ATTRIBUTION.txt"
    if attribution_path.is_symlink() or not attribution_path.is_file():
        raise PeeringDBAssessmentError("Scrutica ATTRIBUTION.txt is missing")

    connection = _read_only_connection(directory / "atlas.sqlite")
    try:
        evidence_rows = connection.execute(
            "SELECT id, license, attribution, metadata_json "
            "FROM evidence WHERE source_family = 'scrutica' ORDER BY id"
        ).fetchall()
        matched: list[tuple[str, str, str, Mapping[str, Any]]] = []
        for evidence_id, license_name, attribution, raw_metadata in evidence_rows:
            try:
                metadata = json.loads(raw_metadata)
            except (TypeError, json.JSONDecodeError) as error:
                raise PeeringDBAssessmentError(
                    f"invalid Scrutica metadata JSON: {evidence_id}"
                ) from error
            if not isinstance(metadata, Mapping):
                raise PeeringDBAssessmentError(
                    f"Scrutica metadata must be an object: {evidence_id}"
                )
            if (
                str(metadata.get("data_source", "")).strip().casefold()
                == PEERINGDB_SOURCE
            ):
                matched.append((evidence_id, license_name, attribution, metadata))

        evidence_ids = {row[0] for row in matched}
        entity_rows = connection.execute(
            "SELECT id, created_from_evidence_id FROM entities ORDER BY id"
        ).fetchall()
        entity_ids = {
            entity_id
            for entity_id, evidence_id in entity_rows
            if evidence_id in evidence_ids
        }
        dependent_counts: dict[str, int] = {}
        for table in _QUARANTINED_DEPENDENT_TABLES:
            rows = connection.execute(
                f"SELECT entity_id, evidence_id FROM {table}"  # noqa: S608
            ).fetchall()
            dependent_counts[table] = sum(
                entity_id in entity_ids or evidence_id in evidence_ids
                for entity_id, evidence_id in rows
            )
        facility_rows = connection.execute("SELECT entity_id FROM facilities").fetchall()
        dependent_counts["facilities"] = sum(
            entity_id in entity_ids for (entity_id,) in facility_rows
        )
    except sqlite3.Error as error:
        raise PeeringDBAssessmentError("cannot audit Scrutica SQLite") from error
    finally:
        connection.close()

    license_counts = Counter(str(row[1]) for row in matched)
    attribution_counts = Counter(str(row[2]) for row in matched)
    permission_rows = sum(_permission_evidenced(row[3]) for row in matched)
    cc_rows = sum(
        row[1] == "CC-BY-SA-4.0"
        and row[2] == "Scrutica data, licensed under CC BY-SA 4.0"
        for row in matched
    )
    return {
        "release_manifest_sha256": _sha256(manifest_path),
        "attribution_file_sha256": _sha256(attribution_path),
        "attribution_file_text": attribution_path.read_text(encoding="utf-8").strip(),
        "scrutica_evidence_rows": len(evidence_rows),
        "peeringdb_evidence_rows": len(matched),
        "peeringdb_entity_rows": len(entity_ids),
        "cc_by_sa_labeled_peeringdb_evidence_rows": cc_rows,
        "permission_evidence_recorded_rows": permission_rows,
        "license_counts": dict(sorted(license_counts.items())),
        "attribution_counts": dict(sorted(attribution_counts.items())),
        "dependent_rows": dependent_counts,
        "conflict_detected": bool(matched and cc_rows and permission_rows == 0),
        "publication_eligible": False,
        "required_action": "quarantine_or_exclude_until_rights_are_evidenced",
        "relabel_alone_is_sufficient": False,
    }


__all__ = [
    "ASSESSMENT_FILENAME",
    "MANIFEST_FILENAME",
    "MANIFEST_HASH_FILENAME",
    "PeeringDBAssessmentError",
    "audit_scrutica_peeringdb_rights",
    "validate_assessment_bundle",
    "validate_assessment_document",
]
