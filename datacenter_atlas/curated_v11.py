"""Versioned curated importer with per-evidence retrieval timestamps.

Schema 1.0 remains owned by :mod:`datacenter_atlas.curated`. Schema 1.1 keeps
the same document shape but allows each evidence record to retain its actual
retrieval timestamp, provided no evidence post-dates the import transaction.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import curated as legacy
from .adapters import ImportResult


SCHEMA_VERSION = "1.1"
LEGACY_CURATED_SHA256 = (
    "638d39c4199d4479106c365672ff9efb327f145ccf494bc92942ac6788c6cc12"
)


def _verify_legacy_adapter() -> None:
    source_path = Path(legacy.__file__).resolve()
    actual = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if actual != LEGACY_CURATED_SHA256:
        raise RuntimeError(
            "curated_v11 requires the pinned schema-1.0 adapter "
            f"{LEGACY_CURATED_SHA256}, found {actual}"
        )


_verify_legacy_adapter()


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _entity_record(value: Any, path: str, ref: str) -> legacy._EntityRecord:
    """Preserve an explicitly absent representative point for geometry-only rows."""

    record = legacy._entity_record(value, path, ref)
    if isinstance(value, dict) and value.get("coordinates") is None and value.get(
        "geometry"
    ) is not None:
        return replace(record, latitude=None, longitude=None)
    return record


def _parse_document(path: Path, recorded_at: str) -> legacy._Document:
    import_recorded_at = legacy._timestamp(recorded_at, "recorded_at")
    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=legacy._reject_duplicate_keys,
        )
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid curated JSON: {error}") from error
    root = legacy._object(raw, "root")
    legacy._fields(
        root,
        "root",
        required={
            "schema_version",
            "evidence",
            "campus",
            "project",
            "lifecycle",
            "operating_models",
            "workloads",
            "capacities",
        },
    )
    if root["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION!r}")

    evidence_records = legacy._list(root["evidence"], "evidence")
    evidence: list[legacy._EvidenceRecord] = []
    for index, item in enumerate(evidence_records):
        record = legacy._object(item, f"evidence[{index}]")
        evidence_retrieved_at = legacy._timestamp(
            record.get("retrieved_at"), f"evidence[{index}].retrieved_at"
        )
        if _instant(evidence_retrieved_at) > _instant(import_recorded_at):
            raise ValueError(
                f"evidence[{index}].retrieved_at must not be later than the import "
                "recorded_at"
            )
        evidence.append(legacy._evidence_record(item, index, evidence_retrieved_at))
    if not evidence:
        raise ValueError("evidence must contain at least one record")
    evidence_tuple = tuple(evidence)
    evidence_by_key = {item.key: item for item in evidence_tuple}
    if len(evidence_by_key) != len(evidence_tuple):
        raise ValueError("evidence keys must be unique")

    campus = _entity_record(root["campus"], "campus", "campus")
    project = (
        _entity_record(root["project"], "project", "project")
        if root["project"] is not None
        else None
    )
    lifecycle = tuple(
        legacy._observation(
            item,
            f"lifecycle[{index}]",
            enum_type=legacy.LifecycleStatus,
            allowed_methods=legacy.LIFECYCLE_METHODS,
        )
        for index, item in enumerate(legacy._list(root["lifecycle"], "lifecycle"))
    )
    operating_models = tuple(
        legacy._observation(
            item,
            f"operating_models[{index}]",
            enum_type=legacy.OperatingModel,
            allowed_methods=legacy.CLASSIFICATION_METHODS,
        )
        for index, item in enumerate(
            legacy._list(root["operating_models"], "operating_models")
        )
    )
    workloads = tuple(
        legacy._observation(
            item,
            f"workloads[{index}]",
            enum_type=legacy.Workload,
            allowed_methods=legacy.CLASSIFICATION_METHODS,
        )
        for index, item in enumerate(legacy._list(root["workloads"], "workloads"))
    )
    capacities = tuple(
        legacy._capacity(item, index)
        for index, item in enumerate(legacy._list(root["capacities"], "capacities"))
    )
    legacy._reject_duplicate_claim_keys(
        "lifecycle", lifecycle, lambda item: (item.entity_ref, item.as_of_date)
    )
    legacy._reject_duplicate_claim_keys(
        "operating_models",
        operating_models,
        lambda item: (item.entity_ref, item.as_of_date),
    )
    legacy._reject_duplicate_claim_keys(
        "workloads",
        workloads,
        lambda item: (item.entity_ref, item.value.value, item.as_of_date),
    )
    legacy._reject_duplicate_claim_keys(
        "capacities",
        capacities,
        lambda item: (
            item.entity_ref,
            item.metric.value,
            item.stage.value,
            item.as_of_date,
        ),
    )

    entity_refs = {"campus"} | ({"project"} if project else set())
    for entity in (campus, project):
        if entity is not None and entity.evidence_key not in evidence_by_key:
            raise ValueError(
                f"{entity.ref}.evidence_key references missing evidence: "
                f"{entity.evidence_key}"
            )
    for collection_name, collection in (
        ("lifecycle", lifecycle),
        ("operating_models", operating_models),
        ("workloads", workloads),
        ("capacities", capacities),
    ):
        for index, observation in enumerate(collection):
            if observation.entity_ref not in entity_refs:
                raise ValueError(
                    f"{collection_name}[{index}].entity references a missing entity"
                )
            if observation.evidence_key not in evidence_by_key:
                raise ValueError(
                    f"{collection_name}[{index}].evidence_key references missing "
                    f"evidence: {observation.evidence_key}"
                )

    for index, observation in enumerate(lifecycle):
        if (
            observation.value in legacy.CONSTRUCTION_STATUSES
            and observation.method not in legacy.CONSTRUCTION_METHODS
        ):
            raise ValueError(
                f"lifecycle[{index}] construction status requires "
                "authoritative_construction_start, "
                "authoritative_physical_status_update, or physical_observation"
            )
    for index, estimate in enumerate(capacities):
        if not (0 <= estimate.low <= estimate.base <= estimate.high):
            raise ValueError(
                f"capacities[{index}] must satisfy 0 <= low <= base <= high"
            )
        if estimate.metric is legacy.CapacityMetric.PUE and estimate.low <= 0:
            raise ValueError(f"capacities[{index}] PUE must be greater than zero")
        evidence_kind = evidence_by_key[estimate.evidence_key].model.kind
        if (
            estimate.metric is legacy.CapacityMetric.ANNUAL_ENERGY_MWH
            and estimate.stage is legacy.CapacityStage.MEASURED
            and evidence_kind not in legacy.MEASURED_ENERGY_EVIDENCE_KINDS
        ):
            raise ValueError(
                f"capacities[{index}] measured annual energy requires "
                "utility_record or government_record evidence"
            )
    return legacy._Document(
        evidence=evidence_tuple,
        campus=campus,
        project=project,
        lifecycle=lifecycle,
        operating_models=operating_models,
        workloads=workloads,
        capacities=capacities,
    )


def _schema_version(path: Path) -> Any:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid curated JSON: {error}") from error
    if not isinstance(document, dict):
        return None
    return document.get("schema_version")


class CuratedOfficialSourceAdapterV11:
    """Import schema 1.1 sources while delegating schema 1.0 unchanged."""

    source_name = legacy.CuratedOfficialSourceAdapter.source_name

    def import_file(
        self,
        connection: sqlite3.Connection,
        path: str | Path,
        *,
        recorded_at: str,
    ) -> ImportResult:
        source_path = Path(path)
        if _schema_version(source_path) == legacy.SCHEMA_VERSION:
            return legacy.CuratedOfficialSourceAdapter().import_file(
                connection, source_path, retrieved_at=recorded_at
            )

        document = _parse_document(source_path, recorded_at)
        evidence_by_key = {item.key: item for item in document.evidence}
        evidence_created = 0
        entities_created = 0
        entity_ids: dict[str, str] = {}

        with connection:
            for item in document.evidence:
                evidence_created += int(
                    legacy.add_evidence(
                        connection,
                        item.model,
                        content_hash=item.content_hash,
                        metadata={
                            "curated_record_key": item.key,
                            "content_hash_scope": item.content_hash_scope,
                            "content_hash_verification": (
                                item.content_hash_verification
                            ),
                            "record": item.metadata,
                        },
                    )
                )

            campus_evidence = evidence_by_key[document.campus.evidence_key].model
            campus_id = legacy.stable_id("entity", document.campus.stable_key, "campus")
            entity_ids["campus"] = campus_id
            entities_created += int(
                legacy.add_campus(
                    connection,
                    legacy.Campus(
                        campus_id,
                        document.campus.stable_key,
                        campus_evidence.id,
                    ),
                    created_at=recorded_at,
                )
            )
            entities: list[tuple[legacy._EntityRecord, str]] = [
                (document.campus, campus_id)
            ]
            if document.project:
                project_evidence = evidence_by_key[document.project.evidence_key].model
                project_id = legacy.stable_id(
                    "entity", document.project.stable_key, "project"
                )
                entity_ids["project"] = project_id
                entities_created += int(
                    legacy.add_project(
                        connection,
                        legacy.Project(
                            project_id,
                            document.project.stable_key,
                            project_evidence.id,
                            campus_id,
                        ),
                        created_at=recorded_at,
                    )
                )
                entities.append((document.project, project_id))

            for entity, entity_id in entities:
                evidence_id = evidence_by_key[entity.evidence_key].model.id
                legacy.add_snapshot(
                    connection,
                    snapshot_id=legacy.stable_id(
                        "snapshot",
                        entity_id,
                        evidence_id,
                        entity.as_of_date,
                        entity.method,
                    ),
                    entity_id=entity_id,
                    name=entity.name,
                    latitude=entity.latitude,
                    longitude=entity.longitude,
                    geometry=entity.geometry,
                    tags=legacy._entity_tags(entity),
                    evidence_id=evidence_id,
                    as_of_date=entity.as_of_date,
                    recorded_at=recorded_at,
                    method=entity.method,
                    confidence=entity.confidence,
                )

            for observation in document.lifecycle:
                entity_id = entity_ids[observation.entity_ref]
                evidence_id = evidence_by_key[observation.evidence_key].model.id
                observation_id = legacy.stable_id(
                    "lifecycle",
                    entity_id,
                    evidence_id,
                    observation.as_of_date,
                    observation.value.value,
                    observation.method,
                )
                legacy._reject_existing_claim_key(
                    connection,
                    table="lifecycle_observations",
                    claim_id=observation_id,
                    entity_id=entity_id,
                    as_of_date=observation.as_of_date,
                    recorded_at=recorded_at,
                )
                legacy.add_lifecycle(
                    connection,
                    legacy.LifecycleObservation(
                        id=observation_id,
                        entity_id=entity_id,
                        status=observation.value,
                        evidence_id=evidence_id,
                        as_of_date=observation.as_of_date,
                        recorded_at=recorded_at,
                        method=observation.method,
                        confidence=observation.confidence,
                    ),
                )
            for observation in document.operating_models:
                entity_id = entity_ids[observation.entity_ref]
                evidence_id = evidence_by_key[observation.evidence_key].model.id
                observation_id = legacy.stable_id(
                    "operating-model",
                    entity_id,
                    evidence_id,
                    observation.as_of_date,
                    observation.value.value,
                    observation.method,
                )
                legacy._reject_existing_claim_key(
                    connection,
                    table="operating_model_observations",
                    claim_id=observation_id,
                    entity_id=entity_id,
                    as_of_date=observation.as_of_date,
                    recorded_at=recorded_at,
                )
                legacy.add_operating_model(
                    connection,
                    observation_id=observation_id,
                    entity_id=entity_id,
                    operating_model=observation.value,
                    evidence_id=evidence_id,
                    as_of_date=observation.as_of_date,
                    recorded_at=recorded_at,
                    method=observation.method,
                    confidence=observation.confidence,
                )
            for observation in document.workloads:
                entity_id = entity_ids[observation.entity_ref]
                evidence_id = evidence_by_key[observation.evidence_key].model.id
                observation_id = legacy.stable_id(
                    "workload",
                    entity_id,
                    evidence_id,
                    observation.as_of_date,
                    observation.value.value,
                    observation.method,
                )
                legacy._reject_existing_claim_key(
                    connection,
                    table="workload_observations",
                    claim_id=observation_id,
                    entity_id=entity_id,
                    as_of_date=observation.as_of_date,
                    recorded_at=recorded_at,
                    dimensions={"workload": observation.value.value},
                )
                legacy.add_workload(
                    connection,
                    observation_id=observation_id,
                    entity_id=entity_id,
                    workload=observation.value,
                    evidence_id=evidence_id,
                    as_of_date=observation.as_of_date,
                    recorded_at=recorded_at,
                    method=observation.method,
                    confidence=observation.confidence,
                )
            for estimate in document.capacities:
                entity_id = entity_ids[estimate.entity_ref]
                evidence_id = evidence_by_key[estimate.evidence_key].model.id
                estimate_id = legacy.stable_id(
                    "capacity",
                    entity_id,
                    evidence_id,
                    estimate.metric.value,
                    estimate.stage.value,
                    estimate.as_of_date,
                    estimate.target_date,
                    estimate.low,
                    estimate.base,
                    estimate.high,
                    estimate.method.value,
                )
                legacy._reject_existing_claim_key(
                    connection,
                    table="capacity_estimates",
                    claim_id=estimate_id,
                    entity_id=entity_id,
                    as_of_date=estimate.as_of_date,
                    recorded_at=recorded_at,
                    dimensions={
                        "metric": estimate.metric.value,
                        "stage": estimate.stage.value,
                    },
                )
                legacy.add_capacity(
                    connection,
                    legacy.CapacityEstimate(
                        id=estimate_id,
                        entity_id=entity_id,
                        metric=estimate.metric,
                        stage=estimate.stage,
                        low=estimate.low,
                        base=estimate.base,
                        high=estimate.high,
                        method=estimate.method,
                        confidence=estimate.confidence,
                        evidence_id=evidence_id,
                        as_of_date=estimate.as_of_date,
                        target_date=estimate.target_date,
                        recorded_at=recorded_at,
                        notes=estimate.notes,
                    ),
                )

        return ImportResult(
            source=self.source_name,
            examined_elements=1,
            imported_elements=1,
            entities_created=entities_created,
            evidence_created=evidence_created,
        )
