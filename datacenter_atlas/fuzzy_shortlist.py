"""Deterministic triage for the high-recall fuzzy OpenStreetMap review layer."""

from __future__ import annotations

from collections import Counter
import csv
import io
import json
import sqlite3
from typing import Any, Mapping

from .service import export_geojson


SHORTLIST_FIELDS = (
    "priority_rank",
    "priority_tier",
    "entity_id",
    "stable_key",
    "name",
    "latitude",
    "longitude",
    "country",
    "country_iso_a2",
    "country_iso_a3",
    "status",
    "status_as_of",
    "status_confidence",
    "classification",
    "classification_reason",
    "lifecycle_hint",
    "trigger_keys_json",
    "trigger_tags_json",
    "tags_json",
    "source_url",
    "source_published_at",
    "source_retrieved_at",
    "review_only",
    "data_center_identity_inferred",
    "capacity_inferred",
)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _key_matches(key: str, roots: tuple[str, ...]) -> bool:
    return any(key == root or key.startswith(root + ":") for root in roots)


def shortlist_priority(classification: Mapping[str, Any]) -> tuple[int, str] | None:
    """Return a transparent review tier; ``None`` means source/reference-only noise."""
    name = classification.get("classification")
    hint = classification.get("lifecycle_hint")
    triggers = classification.get("trigger_tags")
    if not isinstance(triggers, list):
        raise ValueError("fuzzy classification has no trigger-tag list")
    keys = [str(item.get("key")) for item in triggers if isinstance(item, Mapping)]

    if name == "explicit_marker_variant":
        if hint in {"under_construction", "proposed"}:
            return 1, "explicit_lifecycle_marker"
        return 2, "explicit_structural_marker"
    if name == "unknown_key_explicit_value":
        return 3, "nonstandard_exact_marker"

    identity_roots = (
        "name",
        "official_name",
        "short_name",
        "alt_name",
        "old_name",
        "operator",
        "brand",
        "website",
        "url",
        "contact:website",
    )
    context_roots = ("description", "note", "addr:housename")
    has_identity = any(_key_matches(key, identity_roots) for key in keys)
    has_context = any(_key_matches(key, context_roots) for key in keys)
    if name == "textual_only" and has_identity:
        return 4, "identity_text"
    if name == "textual_only" and has_context:
        return 5, "context_text"
    if name == "ambiguous" and (has_identity or has_context):
        return 6, "ambiguous_identity_or_context"
    return None


def build_fuzzy_shortlist(
    connection: sqlite3.Connection,
    *,
    as_of: str,
    recorded_at: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build shortlist rows and an audit report without promoting any candidate."""
    evidence = {
        row["id"]: json.loads(row["metadata_json"])
        for row in connection.execute(
            "SELECT id, metadata_json FROM evidence WHERE source_family = ? ORDER BY id",
            ("openstreetmap:fuzzy_discovery",),
        )
    }
    document = export_geojson(connection, as_of=as_of, recorded_at=recorded_at)
    recorded_at = document["atlas_recorded_at"]
    rows: list[dict[str, Any]] = []
    excluded = 0
    excluded_patterns: Counter[tuple[str, str, str]] = Counter()
    classifications: Counter[str] = Counter()
    tiers: Counter[str] = Counter()

    for feature in document["features"]:
        properties = feature["properties"]
        if properties.get("source_family") != "openstreetmap:fuzzy_discovery":
            continue
        metadata = evidence.get(properties.get("snapshot_evidence_id"))
        if not isinstance(metadata, Mapping):
            raise ValueError("fuzzy feature is missing its evidence metadata")
        classification = metadata.get("classification")
        if not isinstance(classification, Mapping):
            raise ValueError("fuzzy evidence has no classification object")
        class_name = classification.get("classification")
        if not isinstance(class_name, str):
            raise ValueError("fuzzy evidence classification name is invalid")
        classifications[class_name] += 1
        priority = shortlist_priority(classification)
        triggers = classification.get("trigger_tags")
        if not isinstance(triggers, list):
            raise ValueError("fuzzy evidence trigger tags are invalid")
        if priority is None:
            excluded += 1
            for trigger in triggers:
                if isinstance(trigger, Mapping):
                    excluded_patterns[
                        (
                            class_name,
                            str(trigger.get("key") or ""),
                            str(trigger.get("value") or ""),
                        )
                    ] += 1
            continue

        rank, tier = priority
        tiers[tier] += 1
        trigger_keys = sorted(
            {str(trigger.get("key")) for trigger in triggers if isinstance(trigger, Mapping)}
        )
        rows.append(
            {
                "priority_rank": rank,
                "priority_tier": tier,
                "entity_id": properties["entity_id"],
                "stable_key": properties["stable_key"],
                "name": properties["name"],
                "latitude": properties["latitude"],
                "longitude": properties["longitude"],
                "country": properties["country"],
                "country_iso_a2": properties["country_iso_a2"],
                "country_iso_a3": properties["country_iso_a3"],
                "status": properties["status"],
                "status_as_of": properties["status_as_of"],
                "status_confidence": properties["status_confidence"],
                "classification": class_name,
                "classification_reason": classification.get("reason"),
                "lifecycle_hint": classification.get("lifecycle_hint"),
                "trigger_keys_json": _json(trigger_keys),
                "trigger_tags_json": _json(triggers),
                "tags_json": _json(properties["tags"]),
                "source_url": properties["source_url"],
                "source_published_at": properties["source_published_at"],
                "source_retrieved_at": properties["source_retrieved_at"],
                "review_only": "true",
                "data_center_identity_inferred": "false",
                "capacity_inferred": "false",
            }
        )

    rows.sort(key=lambda row: (row["priority_rank"], row["entity_id"]))
    if len(rows) + excluded != sum(classifications.values()):
        raise ValueError("fuzzy shortlist counts do not reconcile")
    top_patterns = [
        {
            "classification": key[0],
            "key": key[1],
            "value": key[2],
            "trigger_observations": count,
        }
        for key, count in sorted(
            excluded_patterns.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1], item[0][2]),
        )[:50]
    ]
    triage = {
        "schema_version": 1,
        "pipeline": "openstreetmap_fuzzy_review_triage",
        "as_of": as_of,
        "recorded_at": recorded_at,
        "review_only": True,
        "candidate_recall_expansion_not_census": True,
        "data_center_identity_inference": False,
        "capacity_inference": False,
        "counts": {
            "imported_supplemental_candidates": sum(classifications.values()),
            "shortlisted_candidates": len(rows),
            "excluded_source_or_reference_only_candidates": excluded,
            "by_classification": dict(sorted(classifications.items())),
            "shortlisted_by_priority_tier": dict(sorted(tiers.items())),
        },
        "priority_policy": [
            {"rank": 1, "tier": "explicit_lifecycle_marker"},
            {"rank": 2, "tier": "explicit_structural_marker"},
            {"rank": 3, "tier": "nonstandard_exact_marker"},
            {"rank": 4, "tier": "identity_text"},
            {"rank": 5, "tier": "context_text"},
            {"rank": 6, "tier": "ambiguous_identity_or_context"},
        ],
        "top_excluded_trigger_patterns": top_patterns,
    }
    return rows, triage


def shortlist_csv(rows: list[dict[str, Any]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=SHORTLIST_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


__all__ = [
    "SHORTLIST_FIELDS",
    "build_fuzzy_shortlist",
    "shortlist_csv",
    "shortlist_priority",
]
