"""Deterministic, auditable snapshot release bundles."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .resolution import (
    candidate_links_to_csv,
    candidate_links_to_json,
    generate_candidate_links,
)
from .models import ACTIVE_PIPELINE_STATUSES
from .service import export_geojson, summarize


SUPPORTED_PUBLICATION_CONTRACT_VERSIONS = frozenset({1, 2, 3})


ENTITY_FIELDS = (
    "entity_id",
    "entity_kind",
    "stable_key",
    "name",
    "latitude",
    "longitude",
    "country",
    "country_iso_a2",
    "country_iso_a3",
    "country_assignment_status",
    "country_assignment_method",
    "country_assignment_confidence",
    "country_assignment_evidence_id",
    "country_boundary_feature_id",
    "source_country_tag",
    "source_country_method",
    "source_country_qid",
    "address",
    "owner",
    "operator",
    "users",
    "status",
    "status_as_of",
    "status_confidence",
    "status_method",
    "status_evidence_id",
    "operating_model",
    "operating_model_confidence",
    "operating_model_evidence_id",
    "workloads_json",
    "capacity_estimates_json",
    "geometry_json",
    "tags_json",
    "snapshot_as_of",
    "snapshot_confidence",
    "snapshot_evidence_id",
    "source_url",
    "source_publisher",
    "source_license",
    "source_retrieved_at",
)

ENTITY_FIELDS_V3 = (
    *ENTITY_FIELDS[: ENTITY_FIELDS.index("users") + 1],
    "tenants",
    "customers",
    *ENTITY_FIELDS[ENTITY_FIELDS.index("users") + 1 :],
)

CAPACITY_FIELDS = (
    "entity_id",
    "entity_kind",
    "name",
    "metric",
    "stage",
    "unit",
    "low",
    "base",
    "high",
    "method",
    "confidence",
    "as_of_date",
    "target_date",
    "evidence_id",
    "notes",
    "source_url",
    "source_publisher",
    "source_license",
    "source_retrieved_at",
)

EVIDENCE_FIELDS = (
    "evidence_id",
    "kind",
    "title",
    "source_url",
    "publisher",
    "source_family",
    "license",
    "attribution",
    "published_at",
    "retrieved_at",
    "content_hash",
)

CONSTRUCTION_SOURCE_SIGNAL_FIELDS = (
    "source_observation_evidence_id",
    "affected_entity_count",
    "affected_entities_json",
    "representative_entity_id",
    "representative_entity_kind",
    "representative_stable_key",
    "representative_name",
    "representative_latitude",
    "representative_longitude",
    "representative_country",
    "representative_country_iso_a2",
    "representative_country_iso_a3",
    "representative_status",
    "representative_status_as_of",
    "representative_status_confidence",
    "representative_status_method",
    "source_kind",
    "source_family",
    "source_title",
    "source_url",
    "source_publisher",
    "source_license",
    "source_attribution",
    "source_published_at",
    "source_retrieved_at",
    "source_content_hash",
)

def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _coordinates(value: Any) -> Iterable[tuple[float, float]]:
    if (
        isinstance(value, list)
        and len(value) >= 2
        and isinstance(value[0], (int, float))
        and isinstance(value[1], (int, float))
    ):
        yield float(value[0]), float(value[1])
        return
    if isinstance(value, list):
        for item in value:
            yield from _coordinates(item)


def _center(geometry: dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not geometry:
        return None, None
    points = list(_coordinates(geometry.get("coordinates")))
    if not points:
        return None, None
    longitudes, latitudes = zip(*points)
    return (min(latitudes) + max(latitudes)) / 2, (min(longitudes) + max(longitudes)) / 2


def _csv_document(fields: tuple[str, ...], rows: Iterable[dict[str, Any]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _validated_publication_contract_version(value: int) -> int:
    if type(value) is not int or value not in SUPPORTED_PUBLICATION_CONTRACT_VERSIONS:
        supported = ", ".join(
            str(version) for version in sorted(SUPPORTED_PUBLICATION_CONTRACT_VERSIONS)
        )
        raise ValueError(
            f"publication_contract_version must be one of: {supported}"
        )
    return value


def _exported_role_columns(
    tags: dict[str, Any], publication_contract_version: int
) -> dict[str, Any]:
    if publication_contract_version < 3:
        return {
            "users": tags.get("users")
            or tags.get("tenants")
            or tags.get("role:user")
            or tags.get("role:tenant")
            or tags.get("role:customer")
        }
    return {
        "users": tags.get("users") or tags.get("role:user"),
        "tenants": tags.get("tenants") or tags.get("role:tenant"),
        "customers": tags.get("customers") or tags.get("role:customer"),
    }


def _evidence_lookup(
    connection: sqlite3.Connection, evidence_ids: set[str]
) -> dict[str, sqlite3.Row]:
    if not evidence_ids:
        return {}
    placeholders = ",".join("?" for _ in evidence_ids)
    rows = connection.execute(
        f"""
        SELECT id, kind, title, source_url, publisher, source_family, license, attribution,
               published_at, retrieved_at, content_hash, metadata_json
        FROM evidence
        WHERE id IN ({placeholders})
        ORDER BY id
        """,
        sorted(evidence_ids),
    )
    return {row["id"]: row for row in rows}


def _construction_source_signal_rows(
    construction_rows: Iterable[dict[str, Any]],
    evidence: dict[str, sqlite3.Row],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in construction_rows:
        evidence_id = row.get("status_evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id:
            raise ValueError(
                "active/pre-construction entity row has no lifecycle evidence ID"
            )
        grouped.setdefault(evidence_id, []).append(row)

    signals: list[dict[str, Any]] = []
    for evidence_id, rows in sorted(grouped.items()):
        source = evidence.get(evidence_id)
        if source is None:
            raise ValueError(
                f"construction lifecycle evidence is absent from release: {evidence_id}"
            )
        ordered = sorted(
            rows,
            key=lambda row: (
                row.get("entity_kind") == "project",
                str(row.get("entity_kind") or ""),
                str(row.get("entity_id") or ""),
            ),
        )
        representative = ordered[0]
        affected_entities = [
            {
                "entity_id": row["entity_id"],
                "entity_kind": row["entity_kind"],
                "stable_key": row["stable_key"],
                "name": row["name"],
                "status": row["status"],
                "status_as_of": row["status_as_of"],
                "status_method": row["status_method"],
            }
            for row in ordered
        ]
        signals.append(
            {
                "source_observation_evidence_id": evidence_id,
                "affected_entity_count": len(ordered),
                "affected_entities_json": _json(affected_entities),
                "representative_entity_id": representative["entity_id"],
                "representative_entity_kind": representative["entity_kind"],
                "representative_stable_key": representative["stable_key"],
                "representative_name": representative["name"],
                "representative_latitude": representative["latitude"],
                "representative_longitude": representative["longitude"],
                "representative_country": representative["country"],
                "representative_country_iso_a2": representative["country_iso_a2"],
                "representative_country_iso_a3": representative["country_iso_a3"],
                "representative_status": representative["status"],
                "representative_status_as_of": representative["status_as_of"],
                "representative_status_confidence": representative[
                    "status_confidence"
                ],
                "representative_status_method": representative["status_method"],
                "source_kind": source["kind"],
                "source_family": source["source_family"],
                "source_title": source["title"],
                "source_url": source["source_url"],
                "source_publisher": source["publisher"],
                "source_license": source["license"],
                "source_attribution": source["attribution"],
                "source_published_at": source["published_at"],
                "source_retrieved_at": source["retrieved_at"],
                "source_content_hash": source["content_hash"],
            }
        )
    return signals


def _assert_release_rights_isolation(connection: sqlite3.Connection) -> None:
    """Keep the CC-BY-SA Scrutica discovery layer out of combined releases."""
    families = {
        str(row["source_family"] or "")
        for row in connection.execute(
            "SELECT DISTINCT source_family FROM evidence ORDER BY source_family"
        )
    }
    if "scrutica" in families and families != {"scrutica"}:
        other = ", ".join(repr(value) for value in sorted(families - {"scrutica"}))
        raise ValueError(
            "Scrutica CC-BY-SA evidence requires a separate release; combined "
            f"source families found: {other}"
        )


def build_release_documents(
    connection: sqlite3.Connection,
    *,
    as_of: str,
    recorded_at: str,
    readme: str | None = None,
    publication_contract_version: int = 1,
) -> dict[str, str]:
    publication_contract_version = _validated_publication_contract_version(
        publication_contract_version
    )
    _assert_release_rights_isolation(connection)
    geojson = export_geojson(connection, as_of=as_of, recorded_at=recorded_at)
    entity_rows: list[dict[str, Any]] = []
    capacity_rows: list[dict[str, Any]] = []
    evidence_ids: set[str] = set()

    for feature in geojson["features"]:
        properties = feature["properties"]
        tags = properties.get("tags") or {}
        latitude, longitude = _center(feature.get("geometry"))
        claim_ids = {
            properties.get("snapshot_evidence_id"),
            properties.get("status_evidence_id"),
            properties.get("operating_model_evidence_id"),
            properties.get("administrative_assignment_evidence_id"),
        }
        claim_ids.update(
            item.get("evidence_id") for item in properties.get("workload_observations", [])
        )
        claim_ids.update(
            item.get("evidence_id") for item in properties.get("capacity_estimates", [])
        )
        evidence_ids.update(item for item in claim_ids if item)

        entity_rows.append(
            {
                "entity_id": properties["entity_id"],
                "entity_kind": properties["entity_kind"],
                "stable_key": properties["stable_key"],
                "name": properties.get("name"),
                "latitude": latitude,
                "longitude": longitude,
                "country": properties.get("country"),
                "country_iso_a2": properties.get("country_iso_a2"),
                "country_iso_a3": properties.get("country_iso_a3"),
                "country_assignment_status": properties.get(
                    "administrative_assignment_status"
                ),
                "country_assignment_method": properties.get(
                    "administrative_assignment_method"
                ),
                "country_assignment_confidence": properties.get(
                    "administrative_assignment_confidence"
                ),
                "country_assignment_evidence_id": properties.get(
                    "administrative_assignment_evidence_id"
                ),
                "country_boundary_feature_id": properties.get(
                    "administrative_country_feature_id"
                ),
                "source_country_tag": properties.get("source_country_tag"),
                "source_country_method": properties.get("source_country_method"),
                "source_country_qid": properties.get("source_country_qid"),
                "address": tags.get("address") or tags.get("addr:full"),
                "owner": tags.get("owner")
                or tags.get("owners")
                or tags.get("role:owner"),
                "operator": tags.get("operator") or tags.get("role:operator"),
                **_exported_role_columns(tags, publication_contract_version),
                "status": properties.get("status"),
                "status_as_of": properties.get("status_as_of"),
                "status_confidence": properties.get("status_confidence"),
                "status_method": properties.get("status_method"),
                "status_evidence_id": properties.get("status_evidence_id"),
                "operating_model": properties.get("operating_model"),
                "operating_model_confidence": properties.get("operating_model_confidence"),
                "operating_model_evidence_id": properties.get(
                    "operating_model_evidence_id"
                ),
                "workloads_json": _json(properties.get("workload_observations", [])),
                "capacity_estimates_json": _json(properties.get("capacity_estimates", [])),
                "geometry_json": _json(feature.get("geometry")),
                "tags_json": _json(tags),
                "snapshot_as_of": properties.get("snapshot_as_of"),
                "snapshot_confidence": properties.get("snapshot_confidence"),
                "snapshot_evidence_id": properties.get("snapshot_evidence_id"),
                "source_url": properties.get("source_url"),
                "source_publisher": properties.get("source_publisher"),
                "source_license": properties.get("source_license"),
                "source_retrieved_at": properties.get("source_retrieved_at"),
            }
        )

        for estimate in properties.get("capacity_estimates", []):
            capacity_rows.append(
                {
                    "entity_id": properties["entity_id"],
                    "entity_kind": properties["entity_kind"],
                    "name": properties.get("name"),
                    **estimate,
                }
            )

    evidence = _evidence_lookup(connection, evidence_ids)
    for row in capacity_rows:
        source = evidence[row["evidence_id"]]
        row.update(
            {
                "source_url": source["source_url"],
                "source_publisher": source["publisher"],
                "source_license": source["license"],
                "source_retrieved_at": source["retrieved_at"],
            }
        )

    evidence_rows = [
        {
            "evidence_id": row["id"],
            "kind": row["kind"],
            "title": row["title"],
            "source_url": row["source_url"],
            "publisher": row["publisher"],
            "source_family": row["source_family"],
            "license": row["license"],
            "attribution": row["attribution"],
            "published_at": row["published_at"],
            "retrieved_at": row["retrieved_at"],
            "content_hash": row["content_hash"],
        }
        for row in evidence.values()
    ]
    if publication_contract_version >= 2:
        geojson["attribution"] = sorted(
            {
                str(row["attribution"])
                for row in evidence.values()
                if row["attribution"] and str(row["attribution"]).strip()
            }
        )
    source_inputs: dict[str, dict[str, Any]] = {}
    for row in evidence.values():
        metadata = json.loads(row["metadata_json"] or "{}")
        provenance = metadata.get("provenance")
        if provenance is None and metadata.get("input_sha256"):
            provenance = {"input_sha256": metadata["input_sha256"]}
        if provenance is None and metadata.get("content_hash_scope"):
            provenance = {
                "content_hash": row["content_hash"],
                "content_hash_scope": metadata["content_hash_scope"],
                "content_hash_verification": metadata.get(
                    "content_hash_verification", "unverified_assertion"
                ),
                "curated_record_key": metadata.get("curated_record_key"),
            }
        source = {
            "source_family": row["source_family"],
            "source_url": row["source_url"],
            "publisher": row["publisher"],
            "license": row["license"],
            "retrieved_at": row["retrieved_at"],
            "provenance": provenance or {},
        }
        source_inputs[_json(source)] = source
    entity_rows.sort(key=lambda row: (row["entity_kind"], row["entity_id"]))
    capacity_rows.sort(
        key=lambda row: (row["entity_id"], row["metric"], row["stage"], row["as_of_date"])
    )

    entity_kind_counts: dict[str, int] = {}
    for row in entity_rows:
        kind = str(row["entity_kind"])
        entity_kind_counts[kind] = entity_kind_counts.get(kind, 0) + 1
    source_families = sorted(
        {str(row["source_family"]) for row in evidence.values() if row["source_family"]}
    )
    resolution_candidates = generate_candidate_links(
        connection, as_of=as_of, recorded_at=recorded_at
    )
    construction_rows = [
        row for row in entity_rows if row.get("status") in ACTIVE_PIPELINE_STATUSES
    ]
    construction_signal_rows = _construction_source_signal_rows(
        construction_rows, evidence
    )
    release_summary = summarize(connection, as_of=as_of, recorded_at=recorded_at)
    if publication_contract_version >= 3:
        release_summary.pop("capacity_base_totals", None)
        release_summary["capacity_aggregation"] = {
            "base_totals_published": False,
            "cross_entity_sum_valid": False,
            "reason": (
                "Capacity rows can be nested, component-scoped, superseding, or "
                "metric-distinct. Arithmetic sums are not valid facility, site, load, "
                "energy, or unique-physical-site totals."
            ),
            "scope": "typed_source_observation_rows",
        }
    release_summary["construction_pipeline_records"] = len(construction_rows)
    release_summary["construction_source_signals"] = len(construction_signal_rows)
    if publication_contract_version == 1:
        default_readme = (
            f"# Data Center Atlas open seed — {as_of}\n\n"
            "This is the first reproducible open-data seed, not a global census and not a "
            "claim of parity with SemiAnalysis. It contains "
            f"{entity_kind_counts.get('campus', 0)} campus records and "
            f"{entity_kind_counts.get('project', 0)} project records in the current release view.\n\n"
            "The seed combines Epoch AI's CC BY 4.0 AI Data Centers dataset with selected "
            "official-source records imported under source-specific terms. "
            "Campus status is conservatively inferred from the latest non-future power row "
            "and future capacity growth for Epoch records; official-source lifecycle claims retain "
            "their own methods and evidence. Operational and forecast capacity are separate; "
            "forecast rows carry target dates and a zero downside bound because projects can "
            "be delayed or cancelled. Annual energy is modeled from gross facility power with "
            "50%/80%/100% low/base/high load factors; it is not metered consumption. Inspect "
            "`evidence.csv`, `source_inputs.json`, and the "
            "per-claim evidence IDs before relying on a field.\n\n"
            "`resolution_candidates.*` contains advisory cross-source links only. It never merges "
            "entities automatically.\n\n"
            "`construction_pipeline.csv` is an entity-level active/pre-construction view with "
            f"{len(construction_rows)} rows derived from {len(construction_signal_rows)} distinct "
            "lifecycle evidence/source observations. `construction_source_signals.csv` groups "
            "those rows by `status_evidence_id` and retains every affected entity. This is not "
            "cross-source deduplication and is not a count of unique physical sites.\n\n"
            "Files: `atlas.html` is the interactive map; `entities.csv` is the flat entity list; "
            "`capacity_estimates.csv` is long-form power data; `atlas.geojson` is the spatial "
            "view; `manifest.json` records hashes.\n"
        )
    else:
        default_readme = (
            f"# Data Center Atlas open seed — {as_of}\n\n"
            "This is a reproducible open-data seed, not a global census and not a claim of "
            "parity with SemiAnalysis. It contains "
            f"{entity_kind_counts.get('campus', 0)} campus records and "
            f"{entity_kind_counts.get('project', 0)} project records in the current release view.\n\n"
            "The seed combines Epoch AI's CC BY 4.0 AI Data Centers dataset with selected "
            "official-source records imported under source-specific terms. Campus status is "
            "conservatively inferred from the latest non-future power row and future capacity "
            "growth for Epoch records; official-source lifecycle claims retain their own methods "
            "and evidence. Operational and forecast capacity are separate, and projects can be "
            "delayed or cancelled.\n\n"
            "Capacity and energy semantics are row-specific. Each row in "
            "`capacity_estimates.csv` retains its metric, stage, low/base/high interval, method, "
            "evidence ID, and notes. Annual-energy estimates are modeled, not metered. "
            "Epoch-derived rows can model gross facility power with 50%/80%/100% load factors; "
            "official-source rows can instead model contracted grid load with source-specific "
            "utilization and downside assumptions. Power generation, contracted grid service, "
            "gross facility load, and critical IT load are not interchangeable. Inspect "
            "`evidence.csv`, `source_inputs.json`, and the per-claim evidence IDs before relying "
            "on a field.\n\n"
            "`resolution_candidates.*` contains advisory cross-source links only. It never merges "
            "entities automatically.\n\n"
            "`construction_pipeline.csv` is an entity-level active/pre-construction view with "
            f"{len(construction_rows)} rows derived from {len(construction_signal_rows)} distinct "
            "lifecycle evidence/source observations. `construction_source_signals.csv` groups "
            "those rows by `status_evidence_id` and retains every affected entity. This is not "
            "cross-source deduplication and is not a count of unique physical sites.\n\n"
            "Files: `entities.csv` is the flat entity list; `capacity_estimates.csv` is long-form "
            "power and energy data; `atlas.geojson` is the spatial view; `manifest.json` records "
            "hashes.\n"
        )

    if publication_contract_version >= 3 and readme is None:
        default_readme = default_readme.replace(
            "Files: `entities.csv`",
            "Role columns are dimensioned in publication contract v3: `users` contains only "
            "explicit user roles, `tenants` only explicit tenant roles, and `customers` only "
            "explicit customer roles. A name in one role is not transferred to another.\n\n"
            "Publication contract v3 does not publish aggregate capacity totals. Capacity rows "
            "can be nested, component-scoped, superseding, or metric-distinct, so arithmetic "
            "sums are not facility, site, load, energy, or unique-site totals.\n\n"
            "Files: `entities.csv`",
        )

    entity_fields = (
        ENTITY_FIELDS_V3 if publication_contract_version >= 3 else ENTITY_FIELDS
    )
    documents = {
        "atlas.geojson": json.dumps(
            geojson, indent=2, sort_keys=True, ensure_ascii=False
        )
        + "\n",
        "entities.csv": _csv_document(entity_fields, entity_rows),
        "construction_pipeline.csv": _csv_document(entity_fields, construction_rows),
        "construction_source_signals.csv": _csv_document(
            CONSTRUCTION_SOURCE_SIGNAL_FIELDS, construction_signal_rows
        ),
        "capacity_estimates.csv": _csv_document(CAPACITY_FIELDS, capacity_rows),
        "evidence.csv": _csv_document(EVIDENCE_FIELDS, evidence_rows),
        "summary.json": json.dumps(
            release_summary,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        "ATTRIBUTION.txt": "\n".join(geojson.get("attribution", [])) + "\n",
        "source_inputs.json": json.dumps(
            {"sources": [source_inputs[key] for key in sorted(source_inputs)]},
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        "resolution_candidates.json": candidate_links_to_json(resolution_candidates),
        "resolution_candidates.csv": candidate_links_to_csv(resolution_candidates),
        "README.md": readme or default_readme,
    }
    manifest = {
        "format": "datacenter-atlas-release-v1",
        "as_of": as_of,
        "recorded_at": recorded_at,
        "entities": len(entity_rows),
        "entities_by_kind": dict(sorted(entity_kind_counts.items())),
        "capacity_estimates": len(capacity_rows),
        "construction_pipeline_records": len(construction_rows),
        "construction_source_signals": len(construction_signal_rows),
        "evidence_records": len(evidence_rows),
        "source_families": source_families,
        "resolution_candidates": len(resolution_candidates),
        "files": {
            name: {"bytes": len(text.encode("utf-8")), "sha256": _sha256(text)}
            for name, text in sorted(documents.items())
        },
    }
    documents["manifest.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    return documents


def write_release(
    connection: sqlite3.Connection,
    output_dir: str | Path,
    *,
    as_of: str,
    recorded_at: str,
    readme: str | None = None,
    publication_contract_version: int = 1,
) -> dict[str, Any]:
    publication_contract_version = _validated_publication_contract_version(
        publication_contract_version
    )
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    documents = build_release_documents(
        connection,
        as_of=as_of,
        recorded_at=recorded_at,
        readme=readme,
        publication_contract_version=publication_contract_version,
    )
    for name, text in documents.items():
        (destination / name).write_text(text, encoding="utf-8")
    manifest = json.loads(documents["manifest.json"])
    return {"output_dir": str(destination.resolve()), **manifest}
