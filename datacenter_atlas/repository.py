"""Evidence-first persistence helpers."""

from __future__ import annotations

import json
import sqlite3
import unicodedata
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal

from .models import (
    AdministrativeAssignment,
    Building,
    Campus,
    CapacityEstimate,
    Evidence,
    Facility,
    LifecycleObservation,
    OperatingModel,
    Project,
    Workload,
)
from .timestamps import canonical_persistence_write, canonical_storage_timestamp


ATLAS_NAMESPACE = uuid.UUID("aa3d9079-c7f8-4a77-84d9-75ae2097549f")
IDENTITY_V2_NAMESPACE = uuid.UUID("2dff6f74-05d0-5527-8004-5bad15859a7f")


def utc_now() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _canonical_utc_timestamp(value: str, field: str) -> str:
    return canonical_storage_timestamp(value, field)


def stable_id(*parts: object) -> str:
    return str(uuid.uuid5(ATLAS_NAMESPACE, "|".join(str(part) for part in parts)))


def _identity_v2_json(value: object, field: str) -> object:
    """Return a canonical, JSON-safe identity value without lossy coercion."""

    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [
            _identity_v2_json(item, f"{field}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"{field} keys must be non-empty strings")
            canonical_key = unicodedata.normalize("NFC", key)
            if canonical_key in normalized:
                raise ValueError(
                    f"{field} has duplicate keys after Unicode normalization: "
                    f"{canonical_key!r}"
                )
            normalized[canonical_key] = _identity_v2_json(
                item, f"{field}.{canonical_key}"
            )
        return normalized
    raise TypeError(
        f"{field} must contain only JSON strings, integers, booleans, nulls, "
        "lists, or string-keyed objects"
    )


def stable_id_v2(
    record_kind: str,
    *,
    identity_fields: Mapping[str, object],
    temporal_semantics: Literal["content_revision", "captured_observation"],
    content_revision: str,
    captured_at: str | None = None,
) -> str:
    """Build an opt-in, structured identifier for new source adapters.

    Both modes bind a required content revision. ``content_revision`` identities
    deliberately exclude retrieval time, so the same source bytes keep the same ID
    when downloaded again. A ``captured_observation`` additionally includes a
    canonical UTC observation instant. Legacy ``stable_id`` remains unchanged so
    existing releases retain their IDs.
    """

    if not isinstance(record_kind, str) or not record_kind.strip():
        raise ValueError("record_kind must be a non-empty string")
    if not isinstance(identity_fields, Mapping) or not identity_fields:
        raise ValueError("identity_fields must be a non-empty mapping")
    if temporal_semantics not in {"content_revision", "captured_observation"}:
        raise ValueError(
            "temporal_semantics must be 'content_revision' or "
            "'captured_observation'"
        )
    if not isinstance(content_revision, str) or not content_revision.strip():
        raise ValueError("content_revision must be a non-empty string")

    canonical_identity = _identity_v2_json(identity_fields, "identity_fields")
    payload: dict[str, object] = {
        "identity_fields": canonical_identity,
        "record_kind": unicodedata.normalize("NFC", record_kind),
        "temporal_semantics": temporal_semantics,
        "version": 2,
    }
    payload["content_revision"] = unicodedata.normalize("NFC", content_revision)

    if temporal_semantics == "content_revision":
        if captured_at is not None:
            raise ValueError(
                "captured_at is excluded from content_revision identity; use "
                "captured_observation semantics when capture time is identity-bearing"
            )
    else:
        if captured_at is None:
            raise ValueError(
                "captured_at is required for captured_observation identity"
            )
        payload["captured_at"] = canonical_storage_timestamp(
            captured_at, "stable_id_v2.captured_at"
        )

    canonical_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return str(uuid.uuid5(IDENTITY_V2_NAMESPACE, canonical_payload))


@canonical_persistence_write
def add_evidence(
    connection: sqlite3.Connection,
    evidence: Evidence,
    *,
    content_hash: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    retrieved_at = _canonical_utc_timestamp(
        evidence.retrieved_at, "evidence.retrieved_at"
    )
    columns = (
        "id",
        "kind",
        "title",
        "source_url",
        "publisher",
        "source_family",
        "license",
        "attribution",
        "published_at",
        "retrieved_at",
        "excerpt",
        "content_hash",
        "metadata_json",
    )
    values = (
        evidence.id,
        evidence.kind.value,
        evidence.title,
        evidence.source_url,
        evidence.publisher,
        evidence.source_family,
        evidence.license,
        evidence.attribution,
        evidence.published_at,
        retrieved_at,
        evidence.excerpt,
        content_hash,
        json.dumps(metadata or {}, sort_keys=True, separators=(",", ":")),
    )
    return _insert_exact_row(
        connection,
        table="evidence",
        columns=columns,
        values=values,
    )


def _add_entity(
    connection: sqlite3.Connection,
    *,
    entity_id: str,
    kind: str,
    stable_key: str,
    evidence_id: str,
    created_at: str,
) -> bool:
    created_at = _canonical_utc_timestamp(created_at, "entity.created_at")
    existing = connection.execute(
        """
        SELECT id, kind, stable_key, created_from_evidence_id, created_at
        FROM entities
        WHERE id = ?
        """,
        (entity_id,),
    ).fetchone()
    if existing is not None:
        if existing["kind"] != kind or existing["stable_key"] != stable_key:
            raise ValueError(f"entity identity conflicts with existing row: {entity_id}")

        incoming_provenance = (created_at, evidence_id)
        existing_provenance = (
            _canonical_utc_timestamp(
                existing["created_at"], "entities.created_at"
            ),
            existing["created_from_evidence_id"],
        )
        if incoming_provenance < existing_provenance:
            connection.execute(
                """
                UPDATE entities
                SET created_from_evidence_id = ?, created_at = ?
                WHERE id = ?
                """,
                (evidence_id, created_at, entity_id),
            )
        return False

    stable_key_owner = connection.execute(
        "SELECT id FROM entities WHERE stable_key = ?",
        (stable_key,),
    ).fetchone()
    if stable_key_owner is not None:
        raise ValueError(f"entity stable key is already assigned: {stable_key}")
    connection.execute(
        """
        INSERT INTO entities(id, kind, stable_key, created_from_evidence_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (entity_id, kind, stable_key, evidence_id, created_at),
    )
    return True


def _validate_existing_detail(
    connection: sqlite3.Connection,
    *,
    table: str,
    entity_id: str,
    relation_column: str | None = None,
    relation_value: str | None = None,
) -> None:
    allowed = {
        "campuses": None,
        "facilities": "campus_id",
        "buildings": "facility_id",
        "projects": "target_entity_id",
    }
    if table not in allowed or allowed[table] != relation_column:
        raise ValueError(f"unsupported entity detail table: {table}")
    if connection.execute(
        "SELECT 1 FROM entities WHERE id = ?", (entity_id,)
    ).fetchone() is None:
        return
    selected = "entity_id" if relation_column is None else relation_column
    detail = connection.execute(
        f"SELECT {selected} FROM {table} WHERE entity_id = ?",
        (entity_id,),
    ).fetchone()
    if detail is None:
        raise ValueError(f"existing entity lacks a {table} detail row: {entity_id}")
    if relation_column is not None and detail[relation_column] != relation_value:
        raise ValueError(f"{table} relation conflicts with existing row: {entity_id}")


@canonical_persistence_write
def add_campus(connection: sqlite3.Connection, campus: Campus, *, created_at: str) -> bool:
    _validate_existing_detail(
        connection,
        table="campuses",
        entity_id=campus.id,
    )
    created = _add_entity(
        connection,
        entity_id=campus.id,
        kind="campus",
        stable_key=campus.stable_key,
        evidence_id=campus.created_from_evidence_id,
        created_at=created_at,
    )
    connection.execute("INSERT OR IGNORE INTO campuses(entity_id) VALUES (?)", (campus.id,))
    return created


@canonical_persistence_write
def add_facility(connection: sqlite3.Connection, facility: Facility, *, created_at: str) -> bool:
    _validate_existing_detail(
        connection,
        table="facilities",
        entity_id=facility.id,
        relation_column="campus_id",
        relation_value=facility.campus_id,
    )
    created = _add_entity(
        connection,
        entity_id=facility.id,
        kind="facility",
        stable_key=facility.stable_key,
        evidence_id=facility.created_from_evidence_id,
        created_at=created_at,
    )
    connection.execute(
        "INSERT OR IGNORE INTO facilities(entity_id, campus_id) VALUES (?, ?)",
        (facility.id, facility.campus_id),
    )
    return created


@canonical_persistence_write
def add_building(connection: sqlite3.Connection, building: Building, *, created_at: str) -> bool:
    _validate_existing_detail(
        connection,
        table="buildings",
        entity_id=building.id,
        relation_column="facility_id",
        relation_value=building.facility_id,
    )
    created = _add_entity(
        connection,
        entity_id=building.id,
        kind="building",
        stable_key=building.stable_key,
        evidence_id=building.created_from_evidence_id,
        created_at=created_at,
    )
    connection.execute(
        "INSERT OR IGNORE INTO buildings(entity_id, facility_id) VALUES (?, ?)",
        (building.id, building.facility_id),
    )
    return created


@canonical_persistence_write
def add_project(connection: sqlite3.Connection, project: Project, *, created_at: str) -> bool:
    _validate_existing_detail(
        connection,
        table="projects",
        entity_id=project.id,
        relation_column="target_entity_id",
        relation_value=project.target_entity_id,
    )
    created = _add_entity(
        connection,
        entity_id=project.id,
        kind="project",
        stable_key=project.stable_key,
        evidence_id=project.created_from_evidence_id,
        created_at=created_at,
    )
    connection.execute(
        "INSERT OR IGNORE INTO projects(entity_id, target_entity_id) VALUES (?, ?)",
        (project.id, project.target_entity_id),
    )
    return created


def _insert_exact_row(
    connection: sqlite3.Connection,
    *,
    table: str,
    columns: tuple[str, ...],
    values: tuple[object, ...],
) -> bool:
    allowed_columns = {
        "evidence": (
            "id",
            "kind",
            "title",
            "source_url",
            "publisher",
            "source_family",
            "license",
            "attribution",
            "published_at",
            "retrieved_at",
            "excerpt",
            "content_hash",
            "metadata_json",
        ),
        "entity_snapshots": (
            "id",
            "entity_id",
            "name",
            "latitude",
            "longitude",
            "geometry_json",
            "tags_json",
            "evidence_id",
            "as_of_date",
            "recorded_at",
            "method",
            "confidence",
        ),
        "lifecycle_observations": (
            "id",
            "entity_id",
            "status",
            "evidence_id",
            "as_of_date",
            "recorded_at",
            "method",
            "confidence",
        ),
        "operating_model_observations": (
            "id",
            "entity_id",
            "operating_model",
            "evidence_id",
            "as_of_date",
            "recorded_at",
            "method",
            "confidence",
        ),
        "workload_observations": (
            "id",
            "entity_id",
            "workload",
            "evidence_id",
            "as_of_date",
            "recorded_at",
            "method",
            "confidence",
        ),
        "capacity_estimates": (
            "id",
            "entity_id",
            "metric",
            "stage",
            "unit",
            "low",
            "base",
            "high",
            "method",
            "confidence",
            "evidence_id",
            "as_of_date",
            "target_date",
            "recorded_at",
            "notes",
        ),
        "administrative_assignments": (
            "id",
            "entity_id",
            "resolution_status",
            "country_name",
            "iso_a2",
            "iso_a3",
            "source_admin",
            "source_sovereignt",
            "source_type",
            "source_note_adm0",
            "source_note_brk",
            "source_feature_id",
            "match_feature_ids_json",
            "source_country_tag",
            "coordinate_snapshot_id",
            "boundary_evidence_id",
            "as_of_date",
            "recorded_at",
            "method",
            "confidence",
            "notes",
        ),
    }
    if allowed_columns.get(table) != columns or len(columns) != len(values):
        raise ValueError(f"unsupported exact insert shape: {table}")
    placeholders = ", ".join("?" for _ in columns)
    cursor = connection.execute(
        f"INSERT INTO {table}({', '.join(columns)}) "
        f"VALUES ({placeholders}) ON CONFLICT(id) DO NOTHING",
        values,
    )
    if cursor.rowcount == 1:
        return True

    existing = connection.execute(
        f"SELECT {', '.join(columns)} FROM {table} WHERE id = ?",
        (values[0],),
    ).fetchone()
    if existing is None:
        raise RuntimeError(f"{table} insert conflict did not preserve an ID row")
    conflicting_fields = [
        column
        for column, value in zip(columns, values)
        if existing[column] != value
    ]
    if conflicting_fields:
        raise ValueError(
            f"{table}.{values[0]} conflicts on persisted fields: "
            + ", ".join(conflicting_fields)
        )
    return False


def _supersede_previous(
    connection: sqlite3.Connection,
    table: str,
    entity_id: str,
    new_id: str,
    as_of_date: str,
    recorded_at: str,
    *,
    dimension_column: str | None = None,
    dimension_value: str | None = None,
) -> None:
    allowed = {
        "entity_snapshots",
        "lifecycle_observations",
        "operating_model_observations",
        "workload_observations",
        "capacity_estimates",
        "administrative_assignments",
    }
    if table not in allowed:
        raise ValueError(f"unsupported temporal table: {table}")
    dimension_sql = ""
    params: list[object] = [entity_id, as_of_date]
    if dimension_column:
        if dimension_column not in {"metric", "metric_stage", "workload"}:
            raise ValueError(f"unsupported temporal dimension: {dimension_column}")
        if dimension_column == "metric_stage":
            dimension_sql = " AND metric || '|' || stage = ?"
        else:
            dimension_sql = f" AND {dimension_column} = ?"
        params.append(dimension_value)

    rows = connection.execute(
        f"""
        SELECT id, recorded_at, superseded_at
        FROM {table}
        WHERE entity_id = ?
          AND as_of_date = ?
          {dimension_sql}
        ORDER BY recorded_at, id
        """,
        params,
    ).fetchall()

    recorded_at_counts: dict[str, int] = {}
    for row in rows:
        recorded_at_counts[row["recorded_at"]] = (
            recorded_at_counts.get(row["recorded_at"], 0) + 1
        )
    if any(count > 1 for count in recorded_at_counts.values()):
        connection.execute(f"DELETE FROM {table} WHERE id = ?", (new_id,))
        raise ValueError(
            f"{table} already has a claim for the same logical key, "
            "as_of_date, and recorded_at"
        )

    updates = []
    for index, row in enumerate(rows):
        superseded_at = (
            rows[index + 1]["recorded_at"] if index + 1 < len(rows) else None
        )
        if row["superseded_at"] != superseded_at:
            updates.append((superseded_at, row["id"]))
    connection.executemany(
        f"UPDATE {table} SET superseded_at = ? WHERE id = ?",
        updates,
    )


@canonical_persistence_write
def add_snapshot(
    connection: sqlite3.Connection,
    *,
    snapshot_id: str,
    entity_id: str,
    name: str | None,
    latitude: float | None,
    longitude: float | None,
    geometry: dict[str, Any] | None,
    tags: dict[str, str],
    evidence_id: str,
    as_of_date: str,
    recorded_at: str,
    method: str,
    confidence: float,
) -> bool:
    recorded_at = _canonical_utc_timestamp(
        recorded_at, "entity_snapshots.recorded_at"
    )
    columns = (
        "id",
        "entity_id",
        "name",
        "latitude",
        "longitude",
        "geometry_json",
        "tags_json",
        "evidence_id",
        "as_of_date",
        "recorded_at",
        "method",
        "confidence",
    )
    values = (
        snapshot_id,
        entity_id,
        name,
        latitude,
        longitude,
        (
            json.dumps(geometry, sort_keys=True, separators=(",", ":"))
            if geometry
            else None
        ),
        json.dumps(tags, sort_keys=True, separators=(",", ":")),
        evidence_id,
        as_of_date,
        recorded_at,
        method,
        confidence,
    )
    created = _insert_exact_row(
        connection,
        table="entity_snapshots",
        columns=columns,
        values=values,
    )
    if created:
        _supersede_previous(
            connection, "entity_snapshots", entity_id, snapshot_id, as_of_date, recorded_at
        )
    return created


@canonical_persistence_write
def add_lifecycle(connection: sqlite3.Connection, observation: LifecycleObservation) -> bool:
    recorded_at = _canonical_utc_timestamp(
        observation.recorded_at, "lifecycle_observations.recorded_at"
    )
    columns = (
        "id",
        "entity_id",
        "status",
        "evidence_id",
        "as_of_date",
        "recorded_at",
        "method",
        "confidence",
    )
    values = (
        observation.id,
        observation.entity_id,
        observation.status.value,
        observation.evidence_id,
        observation.as_of_date,
        recorded_at,
        observation.method,
        observation.confidence,
    )
    created = _insert_exact_row(
        connection,
        table="lifecycle_observations",
        columns=columns,
        values=values,
    )
    if created:
        _supersede_previous(
            connection,
            "lifecycle_observations",
            observation.entity_id,
            observation.id,
            observation.as_of_date,
            recorded_at,
        )
    return created


@canonical_persistence_write
def add_operating_model(
    connection: sqlite3.Connection,
    *,
    observation_id: str,
    entity_id: str,
    operating_model: OperatingModel,
    evidence_id: str,
    as_of_date: str,
    recorded_at: str,
    method: str,
    confidence: float,
) -> bool:
    recorded_at = _canonical_utc_timestamp(
        recorded_at, "operating_model_observations.recorded_at"
    )
    columns = (
        "id",
        "entity_id",
        "operating_model",
        "evidence_id",
        "as_of_date",
        "recorded_at",
        "method",
        "confidence",
    )
    values = (
        observation_id,
        entity_id,
        operating_model.value,
        evidence_id,
        as_of_date,
        recorded_at,
        method,
        confidence,
    )
    created = _insert_exact_row(
        connection,
        table="operating_model_observations",
        columns=columns,
        values=values,
    )
    if created:
        _supersede_previous(
            connection,
            "operating_model_observations",
            entity_id,
            observation_id,
            as_of_date,
            recorded_at,
        )
    return created


@canonical_persistence_write
def add_workload(
    connection: sqlite3.Connection,
    *,
    observation_id: str,
    entity_id: str,
    workload: Workload,
    evidence_id: str,
    as_of_date: str,
    recorded_at: str,
    method: str,
    confidence: float,
) -> bool:
    recorded_at = _canonical_utc_timestamp(
        recorded_at, "workload_observations.recorded_at"
    )
    columns = (
        "id",
        "entity_id",
        "workload",
        "evidence_id",
        "as_of_date",
        "recorded_at",
        "method",
        "confidence",
    )
    values = (
        observation_id,
        entity_id,
        workload.value,
        evidence_id,
        as_of_date,
        recorded_at,
        method,
        confidence,
    )
    created = _insert_exact_row(
        connection,
        table="workload_observations",
        columns=columns,
        values=values,
    )
    if created:
        _supersede_previous(
            connection,
            "workload_observations",
            entity_id,
            observation_id,
            as_of_date,
            recorded_at,
            dimension_column="workload",
            dimension_value=workload.value,
        )
    return created


@canonical_persistence_write
def add_capacity(connection: sqlite3.Connection, estimate: CapacityEstimate) -> bool:
    recorded_at = _canonical_utc_timestamp(
        estimate.recorded_at, "capacity_estimates.recorded_at"
    )
    columns = (
        "id",
        "entity_id",
        "metric",
        "stage",
        "unit",
        "low",
        "base",
        "high",
        "method",
        "confidence",
        "evidence_id",
        "as_of_date",
        "target_date",
        "recorded_at",
        "notes",
    )
    values = (
        estimate.id,
        estimate.entity_id,
        estimate.metric.value,
        estimate.stage.value,
        estimate.metric.unit,
        estimate.low,
        estimate.base,
        estimate.high,
        estimate.method.value,
        estimate.confidence,
        estimate.evidence_id,
        estimate.as_of_date,
        estimate.target_date,
        recorded_at,
        estimate.notes,
    )
    created = _insert_exact_row(
        connection,
        table="capacity_estimates",
        columns=columns,
        values=values,
    )
    if created:
        _supersede_previous(
            connection,
            "capacity_estimates",
            estimate.entity_id,
            estimate.id,
            estimate.as_of_date,
            recorded_at,
            dimension_column="metric_stage",
            dimension_value=f"{estimate.metric.value}|{estimate.stage.value}",
        )
    return created


@canonical_persistence_write
def add_administrative_assignment(
    connection: sqlite3.Connection,
    assignment: AdministrativeAssignment,
) -> bool:
    recorded_at = _canonical_utc_timestamp(
        assignment.recorded_at, "administrative_assignments.recorded_at"
    )
    columns = (
        "id",
        "entity_id",
        "resolution_status",
        "country_name",
        "iso_a2",
        "iso_a3",
        "source_admin",
        "source_sovereignt",
        "source_type",
        "source_note_adm0",
        "source_note_brk",
        "source_feature_id",
        "match_feature_ids_json",
        "source_country_tag",
        "coordinate_snapshot_id",
        "boundary_evidence_id",
        "as_of_date",
        "recorded_at",
        "method",
        "confidence",
        "notes",
    )
    values = (
        assignment.id,
        assignment.entity_id,
        assignment.resolution_status.value,
        assignment.country_name,
        assignment.iso_a2,
        assignment.iso_a3,
        assignment.source_admin,
        assignment.source_sovereignt,
        assignment.source_type,
        assignment.source_note_adm0,
        assignment.source_note_brk,
        assignment.source_feature_id,
        assignment.match_feature_ids_json,
        assignment.source_country_tag,
        assignment.coordinate_snapshot_id,
        assignment.boundary_evidence_id,
        assignment.as_of_date,
        recorded_at,
        assignment.method,
        assignment.confidence,
        assignment.notes,
    )
    created = _insert_exact_row(
        connection,
        table="administrative_assignments",
        columns=columns,
        values=values,
    )
    if created:
        _supersede_previous(
            connection,
            "administrative_assignments",
            assignment.entity_id,
            assignment.id,
            assignment.as_of_date,
            recorded_at,
        )
    return created
