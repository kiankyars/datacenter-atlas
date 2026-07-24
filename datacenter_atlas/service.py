"""Read models, GeoJSON export, summaries, and database validation."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from typing import Any

from .database import schema_version
from .models import ACTIVE_PIPELINE_STATUSES
from .natural_earth import canonicalize_source_country
from .timestamps import (
    canonical_read_cutoff,
    persistence_timestamp_errors,
    require_canonical_persistence_state,
)
from .wikidata import (
    WIKIDATA_COUNTRY_FALLBACK_LABEL_TAG,
    WIKIDATA_COUNTRY_FALLBACK_METHOD,
    WIKIDATA_COUNTRY_FALLBACK_METHOD_TAG,
    WIKIDATA_COUNTRY_FALLBACK_QID_TAG,
)


SOURCE_COUNTRY_TAG_METHOD = "source_explicit_country_tag"


def default_as_of() -> str:
    return date.today().isoformat()


def default_recorded_at() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _source_country_claim(
    tags: dict[str, Any],
    *,
    source_family: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    for key in ("country", "country_name", "addr:country"):
        value = tags.get(key)
        if value is not None and str(value).strip():
            return str(value).strip(), SOURCE_COUNTRY_TAG_METHOD, None

    label = tags.get(WIKIDATA_COUNTRY_FALLBACK_LABEL_TAG)
    qid = tags.get(WIKIDATA_COUNTRY_FALLBACK_QID_TAG)
    method = tags.get(WIKIDATA_COUNTRY_FALLBACK_METHOD_TAG)
    if (
        source_family == "wikidata"
        and isinstance(label, str)
        and label.strip()
        and isinstance(qid, str)
        and qid.startswith("Q")
        and qid[1:].isdigit()
        and method == WIKIDATA_COUNTRY_FALLBACK_METHOD
    ):
        return label.strip(), WIKIDATA_COUNTRY_FALLBACK_METHOD, qid
    return None, None, None


def _effective_country(
    assignment: sqlite3.Row | None,
    source_country_tag: str | None,
) -> tuple[str | None, str | None, str | None]:
    if assignment is not None and assignment["country_name"]:
        return assignment["country_name"], assignment["iso_a2"], assignment["iso_a3"]
    canonical_source = canonicalize_source_country(source_country_tag)
    if canonical_source is not None:
        return canonical_source.name, canonical_source.iso_a2, canonical_source.iso_a3
    return source_country_tag, None, None


def _current_rows(
    connection: sqlite3.Connection,
    table: str,
    *,
    as_of: str,
    recorded_at: str,
    partition: str = "entity_id",
) -> list[sqlite3.Row]:
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
    if partition not in {
        "entity_id",
        "entity_id, workload",
        "entity_id, metric, stage",
    }:
        raise ValueError(f"unsupported partition: {partition}")
    recorded_at = canonical_read_cutoff(recorded_at)
    require_canonical_persistence_state(connection)
    return connection.execute(
        f"""
        WITH eligible AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY {partition}
                       ORDER BY as_of_date DESC, recorded_at DESC, id DESC
                   ) AS temporal_rank
            FROM {table}
            WHERE as_of_date <= ?
              AND (valid_to_date IS NULL OR ? < valid_to_date)
              AND recorded_at <= ?
              AND (superseded_at IS NULL OR ? < superseded_at)
        )
        SELECT * FROM eligible WHERE temporal_rank = 1
        """,
        (as_of, as_of, recorded_at, recorded_at),
    ).fetchall()


def export_geojson(
    connection: sqlite3.Connection,
    *,
    as_of: str | None = None,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    as_of = as_of or default_as_of()
    recorded_at = canonical_read_cutoff(recorded_at or default_recorded_at())
    snapshots = _current_rows(
        connection, "entity_snapshots", as_of=as_of, recorded_at=recorded_at
    )
    lifecycle = {
        row["entity_id"]: row
        for row in _current_rows(
            connection, "lifecycle_observations", as_of=as_of, recorded_at=recorded_at
        )
    }
    operating_models = {
        row["entity_id"]: row
        for row in _current_rows(
            connection,
            "operating_model_observations",
            as_of=as_of,
            recorded_at=recorded_at,
        )
    }
    workloads: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _current_rows(
        connection,
        "workload_observations",
        as_of=as_of,
        recorded_at=recorded_at,
        partition="entity_id, workload",
    ):
        workloads[row["entity_id"]].append(
            {
                "workload": row["workload"],
                "confidence": row["confidence"],
                "method": row["method"],
                "as_of_date": row["as_of_date"],
                "evidence_id": row["evidence_id"],
            }
        )
    capacities: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _current_rows(
        connection,
        "capacity_estimates",
        as_of=as_of,
        recorded_at=recorded_at,
        partition="entity_id, metric, stage",
    ):
        capacities[row["entity_id"]].append(
            {
                "metric": row["metric"],
                "stage": row["stage"],
                "unit": row["unit"],
                "low": row["low"],
                "base": row["base"],
                "high": row["high"],
                "method": row["method"],
                "confidence": row["confidence"],
                "as_of_date": row["as_of_date"],
                "target_date": row["target_date"],
                "evidence_id": row["evidence_id"],
                "notes": row["notes"],
            }
        )
    administrative_assignments = {
        row["entity_id"]: row
        for row in _current_rows(
            connection,
            "administrative_assignments",
            as_of=as_of,
            recorded_at=recorded_at,
        )
    }

    entity_rows = {
        row["id"]: row
        for row in connection.execute("SELECT id, kind, stable_key FROM entities")
    }
    project_targets = {
        row["entity_id"]: row["target_entity_id"]
        for row in connection.execute("SELECT entity_id, target_entity_id FROM projects")
    }
    evidence_rows = {
        row["id"]: row
        for row in connection.execute(
            """
            SELECT id, source_url, publisher, source_family, license, attribution,
                   published_at, retrieved_at
            FROM evidence
            """
        )
    }

    features = []
    for snapshot in snapshots:
        entity = entity_rows[snapshot["entity_id"]]
        evidence = evidence_rows[snapshot["evidence_id"]]
        geometry = json.loads(snapshot["geometry_json"]) if snapshot["geometry_json"] else None
        if geometry is None and snapshot["latitude"] is not None:
            geometry = {
                "type": "Point",
                "coordinates": [snapshot["longitude"], snapshot["latitude"]],
            }
        lifecycle_row = lifecycle.get(entity["id"])
        model_row = operating_models.get(entity["id"])
        assignment_row = administrative_assignments.get(entity["id"])
        if (
            assignment_row is not None
            and assignment_row["coordinate_snapshot_id"] != snapshot["id"]
        ):
            assignment_row = None
        tags = json.loads(snapshot["tags_json"])
        source_country_tag, source_country_method, source_country_qid = (
            _source_country_claim(tags, source_family=evidence["source_family"])
        )
        if assignment_row is not None and assignment_row["source_country_tag"]:
            source_country_tag = assignment_row["source_country_tag"]
            if source_country_method is None:
                source_country_method = SOURCE_COUNTRY_TAG_METHOD
        assignment_evidence = (
            evidence_rows[assignment_row["boundary_evidence_id"]]
            if assignment_row is not None
            else None
        )
        country, country_iso_a2, country_iso_a3 = _effective_country(
            assignment_row, source_country_tag
        )
        properties: dict[str, Any] = {
            "entity_id": entity["id"],
            "entity_kind": entity["kind"],
            "stable_key": entity["stable_key"],
            "name": snapshot["name"],
            "latitude": snapshot["latitude"],
            "longitude": snapshot["longitude"],
            "tags": tags,
            "status": lifecycle_row["status"] if lifecycle_row else None,
            "status_as_of": lifecycle_row["as_of_date"] if lifecycle_row else None,
            "status_method": lifecycle_row["method"] if lifecycle_row else None,
            "status_confidence": lifecycle_row["confidence"] if lifecycle_row else None,
            "status_evidence_id": lifecycle_row["evidence_id"] if lifecycle_row else None,
            "operating_model": model_row["operating_model"] if model_row else None,
            "operating_model_as_of": model_row["as_of_date"] if model_row else None,
            "operating_model_method": model_row["method"] if model_row else None,
            "operating_model_confidence": model_row["confidence"] if model_row else None,
            "operating_model_evidence_id": model_row["evidence_id"] if model_row else None,
            "workloads": sorted(
                (item["workload"] for item in workloads.get(entity["id"], []))
            ),
            "workload_observations": sorted(
                workloads.get(entity["id"], []), key=lambda item: item["workload"]
            ),
            "capacity_estimates": sorted(
                capacities.get(entity["id"], []), key=lambda item: item["metric"]
            ),
            "country": country,
            "country_iso_a2": country_iso_a2,
            "country_iso_a3": country_iso_a3,
            "source_country_tag": source_country_tag,
            "source_country_method": source_country_method,
            "source_country_qid": source_country_qid,
            "administrative_assignment_status": (
                assignment_row["resolution_status"] if assignment_row else None
            ),
            "administrative_country_name": (
                assignment_row["country_name"] if assignment_row else None
            ),
            "administrative_country_iso_a2": (
                assignment_row["iso_a2"] if assignment_row else None
            ),
            "administrative_country_iso_a3": (
                assignment_row["iso_a3"] if assignment_row else None
            ),
            "administrative_country_source_admin": (
                assignment_row["source_admin"] if assignment_row else None
            ),
            "administrative_country_source_sovereignt": (
                assignment_row["source_sovereignt"] if assignment_row else None
            ),
            "administrative_country_source_type": (
                assignment_row["source_type"] if assignment_row else None
            ),
            "administrative_country_source_note_adm0": (
                assignment_row["source_note_adm0"] if assignment_row else None
            ),
            "administrative_country_source_note_brk": (
                assignment_row["source_note_brk"] if assignment_row else None
            ),
            "administrative_country_feature_id": (
                assignment_row["source_feature_id"] if assignment_row else None
            ),
            "administrative_country_match_feature_ids": (
                json.loads(assignment_row["match_feature_ids_json"])
                if assignment_row
                else []
            ),
            "administrative_assignment_as_of": (
                assignment_row["as_of_date"] if assignment_row else None
            ),
            "administrative_assignment_method": (
                assignment_row["method"] if assignment_row else None
            ),
            "administrative_assignment_confidence": (
                assignment_row["confidence"] if assignment_row else None
            ),
            "administrative_assignment_evidence_id": (
                assignment_row["boundary_evidence_id"] if assignment_row else None
            ),
            "administrative_assignment_source_url": (
                assignment_evidence["source_url"] if assignment_evidence else None
            ),
            "administrative_assignment_source_license": (
                assignment_evidence["license"] if assignment_evidence else None
            ),
            "administrative_assignment_source_attribution": (
                assignment_evidence["attribution"] if assignment_evidence else None
            ),
            "source_url": evidence["source_url"],
            "source_publisher": evidence["publisher"],
            "source_family": evidence["source_family"],
            "source_published_at": evidence["published_at"],
            "source_retrieved_at": evidence["retrieved_at"],
            "source_license": evidence["license"],
            "source_attribution": evidence["attribution"],
            "snapshot_evidence_id": evidence["id"],
            "snapshot_as_of": snapshot["as_of_date"],
            "snapshot_confidence": snapshot["confidence"],
        }
        if entity["kind"] == "project":
            properties["target_entity_id"] = project_targets[entity["id"]]
        features.append(
            {
                "type": "Feature",
                "id": entity["id"],
                "geometry": geometry,
                "properties": properties,
            }
        )

    features.sort(key=lambda feature: (feature["properties"]["entity_kind"], feature["id"]))
    attributions = sorted(
        {
            attribution
            for feature in features
            for attribution in (
                feature["properties"]["source_attribution"],
                feature["properties"]["administrative_assignment_source_attribution"],
            )
            if attribution
        }
    )
    return {
        "type": "FeatureCollection",
        "atlas_as_of": as_of,
        "atlas_recorded_at": recorded_at,
        "attribution": attributions,
        "features": features,
    }


def summarize(
    connection: sqlite3.Connection,
    *,
    as_of: str | None = None,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    as_of = as_of or default_as_of()
    recorded_at = canonical_read_cutoff(recorded_at or default_recorded_at())
    entity_counts = dict(
        connection.execute("SELECT kind, COUNT(*) FROM entities GROUP BY kind ORDER BY kind")
    )
    lifecycle_rows = _current_rows(
        connection, "lifecycle_observations", as_of=as_of, recorded_at=recorded_at
    )
    status_counts = dict(sorted(Counter(row["status"] for row in lifecycle_rows).items()))
    construction_rows = [
        row for row in lifecycle_rows if row["status"] in ACTIVE_PIPELINE_STATUSES
    ]
    snapshot_rows = _current_rows(
        connection, "entity_snapshots", as_of=as_of, recorded_at=recorded_at
    )
    evidence_source_families = {
        row["id"]: row["source_family"]
        for row in connection.execute("SELECT id, source_family FROM evidence")
    }
    assignment_rows = {
        row["entity_id"]: row
        for row in _current_rows(
            connection,
            "administrative_assignments",
            as_of=as_of,
            recorded_at=recorded_at,
        )
    }
    campus_entity_ids = {
        row["id"]
        for row in connection.execute("SELECT id FROM entities WHERE kind = 'campus'")
    }
    countries = Counter()
    assignment_statuses = Counter()
    source_country_fallbacks = 0
    source_country_conflicts = 0
    source_country_methods = Counter()
    evaluated_assignments = 0
    for row in snapshot_rows:
        tags = json.loads(row["tags_json"])
        source_country, source_country_method, _source_country_qid = (
            _source_country_claim(
                tags,
                source_family=evidence_source_families.get(row["evidence_id"]),
            )
        )
        if source_country_method is not None:
            source_country_methods[source_country_method] += 1
        assignment = assignment_rows.get(row["entity_id"])
        if assignment is not None and assignment["coordinate_snapshot_id"] != row["id"]:
            assignment = None
        if assignment is not None and assignment["source_country_tag"]:
            source_country = assignment["source_country_tag"]
            if source_country_method is None:
                source_country_method = SOURCE_COUNTRY_TAG_METHOD
        if assignment is not None:
            evaluated_assignments += 1
            assignment_statuses[assignment["resolution_status"]] += 1
            if assignment["resolution_status"] == "assigned":
                canonical_source = canonicalize_source_country(source_country)
                if (
                    assignment["iso_a3"]
                    and canonical_source is not None
                    and canonical_source.iso_a3 != assignment["iso_a3"]
                ):
                    source_country_conflicts += 1
        country, _country_iso_a2, _country_iso_a3 = _effective_country(
            assignment, source_country
        )
        if (assignment is None or assignment["resolution_status"] != "assigned") and source_country:
            source_country_fallbacks += 1
        if country:
            countries[str(country)] += 1
    evidence_counts = dict(
        connection.execute("SELECT kind, COUNT(*) FROM evidence GROUP BY kind ORDER BY kind")
    )
    capacity_rows = _current_rows(
        connection,
        "capacity_estimates",
        as_of=as_of,
        recorded_at=recorded_at,
        partition="entity_id, metric, stage",
    )
    capacity_counts = dict(sorted(Counter(row["metric"] for row in capacity_rows).items()))
    capacity_stages = dict(sorted(Counter(row["stage"] for row in capacity_rows).items()))
    capacity_totals: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in capacity_rows:
        bucket = capacity_totals[row["metric"]].setdefault(
            row["stage"], {"base": 0.0, "count": 0, "unit": row["unit"]}
        )
        bucket["base"] += row["base"]
        bucket["count"] += 1
    for stages in capacity_totals.values():
        for bucket in stages.values():
            bucket["base"] = round(bucket["base"], 6)
    return {
        "schema_version": schema_version(connection),
        "as_of": as_of,
        "recorded_at": recorded_at,
        "entities_total": sum(entity_counts.values()),
        "entities_by_kind": entity_counts,
        "campuses_total": entity_counts.get("campus", 0),
        "projects_total": entity_counts.get("project", 0),
        "lifecycle_observations_current": len(lifecycle_rows),
        "entities_by_status": status_counts,
        "construction_pipeline_records": len(construction_rows),
        "construction_source_signals": len(
            {row["evidence_id"] for row in construction_rows}
        ),
        "entities_by_country": dict(sorted(countries.items())),
        "country_assignment_counts": {
            "assigned": assignment_statuses.get("assigned", 0),
            "unmatched": assignment_statuses.get("unmatched", 0),
            "conflict": assignment_statuses.get("ambiguous", 0)
            + assignment_statuses.get("boundary", 0),
            "ambiguous": assignment_statuses.get("ambiguous", 0),
            "boundary": assignment_statuses.get("boundary", 0),
            "not_evaluated": len(snapshot_rows) - evaluated_assignments,
        },
        "country_source_tag_fallbacks": source_country_fallbacks,
        "country_source_tag_conflicts": source_country_conflicts,
        "country_source_claims_by_method": dict(sorted(source_country_methods.items())),
        "entities_with_coordinates": sum(
            row["latitude"] is not None and row["longitude"] is not None
            for row in snapshot_rows
        ),
        "campuses_with_coordinates": sum(
            row["entity_id"] in campus_entity_ids
            and row["latitude"] is not None
            and row["longitude"] is not None
            for row in snapshot_rows
        ),
        "evidence_total": sum(evidence_counts.values()),
        "evidence_by_kind": evidence_counts,
        "capacity_estimates_current": len(capacity_rows),
        "capacity_estimates_by_metric": capacity_counts,
        "capacity_estimates_by_stage": capacity_stages,
        "capacity_base_totals": {
            metric: dict(sorted(stages.items()))
            for metric, stages in sorted(capacity_totals.items())
        },
    }


def _parse_iso(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            date.fromisoformat(value)
        except ValueError:
            return False
    return True


def validate_database(connection: sqlite3.Connection) -> list[str]:
    errors: list[str] = []
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        errors.append(f"integrity_check: {integrity}")
    for row in connection.execute("PRAGMA foreign_key_check"):
        errors.append(f"foreign_key_check: table={row[0]} rowid={row[1]} parent={row[2]}")
    errors.extend(persistence_timestamp_errors(connection))

    detail_tables = {
        "campus": "campuses",
        "facility": "facilities",
        "building": "buildings",
        "project": "projects",
    }
    for kind, table in detail_tables.items():
        missing = connection.execute(
            f"""
            SELECT COUNT(*) FROM entities e
            LEFT JOIN {table} d ON d.entity_id = e.id
            WHERE e.kind = ? AND d.entity_id IS NULL
            """,
            (kind,),
        ).fetchone()[0]
        if missing:
            errors.append(f"{missing} {kind} entities lack a {table} detail row")

    targets = connection.execute(
        """
        SELECT COUNT(*) FROM projects p
        JOIN entities e ON e.id = p.target_entity_id
        WHERE e.kind = 'project'
        """
    ).fetchone()[0]
    if targets:
        errors.append(f"{targets} projects target another project")

    missing_snapshots = connection.execute(
        """
        SELECT COUNT(*) FROM entities e
        LEFT JOIN entity_snapshots s ON s.entity_id = e.id
        WHERE s.id IS NULL
        """
    ).fetchone()[0]
    if missing_snapshots:
        errors.append(f"{missing_snapshots} entities have no evidence-backed snapshot")

    claim_tables = {
        "entity_snapshots": "evidence_id",
        "lifecycle_observations": "evidence_id",
        "operating_model_observations": "evidence_id",
        "workload_observations": "evidence_id",
        "capacity_estimates": "evidence_id",
        "administrative_assignments": "boundary_evidence_id",
    }
    for table, evidence_column in claim_tables.items():
        orphans = connection.execute(
            f"""
            SELECT COUNT(*) FROM {table} c
            LEFT JOIN evidence e ON e.id = c.{evidence_column}
            WHERE e.id IS NULL
            """
        ).fetchone()[0]
        if orphans:
            errors.append(f"{table} contains {orphans} claims without evidence")
        for row in connection.execute(
            f"SELECT id, as_of_date, recorded_at, valid_to_date, superseded_at FROM {table}"
        ):
            if not _parse_iso(row["as_of_date"]):
                errors.append(
                    f"{table}.{row['id']} has invalid as_of_date: {row['as_of_date']}"
                )
            if row["valid_to_date"] and not _parse_iso(row["valid_to_date"]):
                errors.append(
                    f"{table}.{row['id']} has invalid valid_to_date: "
                    f"{row['valid_to_date']}"
                )

    for row in connection.execute(
        "SELECT id, source_url, retrieved_at, kind, license, attribution FROM evidence"
    ):
        if not row["source_url"].strip():
            errors.append(f"evidence.{row['id']} has no source URL")
        if row["kind"] == "openstreetmap":
            if row["license"] != "ODbL-1.0":
                errors.append(f"OSM evidence.{row['id']} lacks ODbL-1.0 license")
            if row["attribution"] != "© OpenStreetMap contributors":
                errors.append(f"OSM evidence.{row['id']} lacks required attribution")

    for row in connection.execute(
        "SELECT id, geometry_json, latitude, longitude FROM entity_snapshots"
    ):
        if row["geometry_json"]:
            try:
                geometry = json.loads(row["geometry_json"])
            except json.JSONDecodeError:
                errors.append(f"snapshot.{row['id']} has invalid geometry JSON")
                continue
            if geometry.get("type") not in {
                "Point",
                "LineString",
                "Polygon",
                "MultiLineString",
                "MultiPolygon",
            }:
                errors.append(f"snapshot.{row['id']} has unsupported GeoJSON geometry type")
        if (row["latitude"] is None) != (row["longitude"] is None):
            errors.append(f"snapshot.{row['id']} has an incomplete center coordinate")

    temporal_dimensions = {
        "entity_snapshots": "entity_id",
        "lifecycle_observations": "entity_id",
        "operating_model_observations": "entity_id",
        "workload_observations": "entity_id, workload",
        "capacity_estimates": "entity_id, metric, stage",
        "administrative_assignments": "entity_id",
    }
    for table, dimensions in temporal_dimensions.items():
        overlaps = connection.execute(
            f"""
            SELECT COUNT(*) FROM (
                SELECT {dimensions}, as_of_date, COUNT(*) AS versions
                FROM {table}
                WHERE superseded_at IS NULL
                GROUP BY {dimensions}, as_of_date
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
        if overlaps:
            errors.append(
                f"{table} has {overlaps} as-of dates with overlapping transaction-time claims"
            )
    assignment_snapshot_mismatches = connection.execute(
        """
        SELECT COUNT(*)
        FROM administrative_assignments a
        JOIN entity_snapshots s ON s.id = a.coordinate_snapshot_id
        WHERE s.entity_id != a.entity_id
        """
    ).fetchone()[0]
    if assignment_snapshot_mismatches:
        errors.append(
            f"administrative_assignments has {assignment_snapshot_mismatches} "
            "coordinate snapshots belonging to another entity"
        )
    for row in connection.execute(
        "SELECT id, resolution_status, match_feature_ids_json FROM administrative_assignments"
    ):
        try:
            match_ids = json.loads(row["match_feature_ids_json"])
        except json.JSONDecodeError:
            errors.append(
                f"administrative_assignments.{row['id']} has invalid match feature JSON"
            )
            continue
        if (
            not isinstance(match_ids, list)
            or any(not isinstance(value, str) for value in match_ids)
            or len(match_ids) != len(set(match_ids))
        ):
            errors.append(
                f"administrative_assignments.{row['id']} has invalid match feature IDs"
            )
        if row["resolution_status"] == "unmatched" and match_ids:
            errors.append(
                f"administrative_assignments.{row['id']} unmatched row has feature matches"
            )
    return errors
