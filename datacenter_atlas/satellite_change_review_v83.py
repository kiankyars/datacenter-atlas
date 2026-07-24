"""Immutable identity-blind analyst review of three accepted v83 change jobs.

The reviewer saw only neutral A/B/C copies of before, after, comparison,
change-overlay, and proposal artifacts.  This carrier validates the accepted
queue, catalog, corrective change publication, and separate technical incident
before unsealing queue lineage.  It creates no Atlas or physical-world claim.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, Mapping

from . import satellite_change_batch_explicit_v83 as execution
from . import satellite_change_batch_explicit_v83_audit as audit
from . import satellite_change_blind_preparation_explicit_v1 as publication


class SatelliteChangeReviewV83Error(ValueError):
    """Raised when accepted inputs, blind decisions, or publication drift."""


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REVIEW_ID = (
    "2026-07-21-open-seed-v83-active-explicit-new-projects-3-review-v2"
)
BLIND_REVIEW_ID = (
    "2026-07-21-open-seed-v83-active-explicit-new-projects-3-blind-review-v2"
)
OUTPUT_PATH = PACKAGE_ROOT / "satellite_change_reviews" / REVIEW_ID
SOURCE_CHANGE_PATH = execution.DEFAULT_OUTPUT_PATH
SOURCE_QUEUE_PATH = execution.DEFAULT_QUEUE_PATH
SOURCE_CATALOG_PATH = execution.DEFAULT_CATALOG_RUN_PATH
SOURCE_INCIDENT_PATH = (
    PACKAGE_ROOT
    / "satellite_change_run_incidents/"
    "2026-07-21-open-seed-v83-post-run-order-assertion-v1"
)
PREMATURE_DRAFT_TRASH_PATH = (
    Path("/Users/kian/.Trash/")
    / "dc-v83-blind-review-premature-definition-20260721-184411/"
    "satellite-change-blind-review-2026-07-21-open-seed-v83-"
    "explicit-new-projects-3-v1.json"
)
REJECTED_DEFINITION_NAMESPACE = (
    "sources/satellite-change-blind-review-2026-07-21-"
    "open-seed-v83-explicit-new-projects-3-v1.json"
)
REJECTED_REVIEW_NAMESPACE = (
    "satellite_change_reviews/2026-07-21-open-seed-v83-"
    "active-explicit-new-projects-3-review-v1"
)

PREMATURE_DRAFT_BYTES = 4_247
PREMATURE_DRAFT_SHA256 = (
    "916053495480ebaebafbe858cc600f5b697403a8f3d60049d53f85d9f6b92dbf"
)
SOURCE_CHANGE_MANIFEST_BYTES = 25_320
SOURCE_CHANGE_MANIFEST_SHA256 = audit.STAGE_MANIFEST_SHA256
SOURCE_CHANGE_TREE_SHA256 = audit.STAGE_PHYSICAL_TREE_SHA256
SOURCE_CHANGE_FILES = 19
SOURCE_CHANGE_BYTES = 5_676_344
SOURCE_QUEUE_TREE_SHA256 = (
    "2b9fc5a30525e2e815154d1635c49badf06c436e354ccb04a4898e6f42d22eee"
)
SOURCE_QUEUE_FILES = 3
SOURCE_QUEUE_BYTES = 573_623
SOURCE_CATALOG_TREE_SHA256 = (
    "8f4409c43f34512c2b092c657fedc362bda1a1afbe0a0b23da53ef955edfe937"
)
SOURCE_CATALOG_FILES = 12
SOURCE_CATALOG_BYTES = 1_451_213
SOURCE_INCIDENT_BYTES = 2_414
SOURCE_INCIDENT_SHA256 = (
    "2a1df815a1c3c7ea1d7a2762ed1ec34266e06312219a8e40a8d7239506c7a5a7"
)
SOURCE_INCIDENT_TREE_SHA256 = (
    "b5605169b5668a339989fa518cae18f61e54e79a70be58470c521da921217ee4"
)

ORDER_SALT = "dc-atlas-v83-three-job-blind-order-2026-07-21-v1"
SOURCE_ARTIFACT_NAMES = frozenset(
    {
        "after.png",
        "before.png",
        "change-overlay.png",
        "change-proposals.geojson",
        "comparison.png",
    }
)
VISUAL_ARTIFACT_NAMES = frozenset(
    {"after.png", "before.png", "change-overlay.png", "comparison.png"}
)
PNG_FORBIDDEN_METADATA_CHUNKS = publication.PNG_FORBIDDEN_METADATA_CHUNKS
PROPOSAL_PROPERTY_KEYS = frozenset(
    {
        "area_m2",
        "class",
        "data_centre_type_claim",
        "energy_claim",
        "identity_claim",
        "it_capacity_claim",
        "lifecycle_claim",
        "operating_status_claim",
        "operator_claim",
        "power_claim",
        "pue_claim",
        "review_required",
        "workload_claim",
    }
)
PROPOSAL_FALSE_CLAIM_KEYS = PROPOSAL_PROPERTY_KEYS - {
    "area_m2",
    "class",
    "review_required",
}

DECISION_SEMANTICS = {
    "rejected_for_site_promotion": (
        "reject the machine proposal set as a basis for site promotion"
    ),
    "retained_for_manual_followup": (
        "retain the machine proposal set for manual visible-change follow-up only"
    ),
    "uncertain_for_manual_followup": (
        "retain an ambiguous machine proposal set for manual visible-change "
        "follow-up only"
    ),
}
GUARDRAILS = {
    "atlas_mutation": False,
    "automated_promotion_allowed": False,
    "capacity_claim_created": False,
    "construction_status_claim_created": False,
    "current_status_claim_created": False,
    "data_centre_identity_claim_created": False,
    "data_centre_type_claim_created": False,
    "energy_claim_created": False,
    "imagery_construction_truth_claim_created": False,
    "it_capacity_claim_created": False,
    "lifecycle_status_claim_created": False,
    "location_claim_created": False,
    "operator_claim_created": False,
    "power_claim_created": False,
    "project_claim_created": False,
    "pue_claim_created": False,
    "site_count_claim_created": False,
    "unique_site_claim_created": False,
    "workload_claim_created": False,
}
EXPECTED_COUNTS = {
    "image_quality": {"partially_obscured": 2, "usable": 1, "unusable": 0},
    "promotion_dispositions": {
        "rejected_for_site_promotion": 2,
        "retained_for_manual_followup": 0,
        "uncertain_for_manual_followup": 1,
    },
    "visible_change": {"ambiguous": 1, "clear": 1, "none": 1},
}
BLIND_DECISIONS = (
    {
        "blind_id": "A",
        "confidence": 0.78,
        "disposition": "uncertain_for_manual_followup",
        "image_quality": "partially_obscured",
        "proposal_area_m2_max": 36_300.0,
        "proposal_area_m2_min": 5_100.0,
        "proposal_area_m2_total": 285_200.0,
        "proposal_class": "large_spectral_change_candidate",
        "proposal_count": 25,
        "rationale": (
            "Responses are widely dispersed across bright surfaces, exposed "
            "ground, and edges; extensive gray masking and scene-wide tonal "
            "differences materially confound them. A few localized ground-surface "
            "patches appear potentially coherent, warranting manual review "
            "without promotion."
        ),
        "visible_change": "ambiguous",
    },
    {
        "blind_id": "B",
        "confidence": 0.93,
        "disposition": "rejected_for_site_promotion",
        "image_quality": "partially_obscured",
        "proposal_area_m2_max": 74_900.0,
        "proposal_area_m2_min": 5_100.0,
        "proposal_area_m2_total": 162_600.0,
        "proposal_class": "large_spectral_change_candidate",
        "proposal_count": 10,
        "rationale": (
            "Clear differences follow field-shaped bare-soil and vegetation "
            "patches across the frame, while large central areas are masked. The "
            "signal is dominated by seasonal or agricultural surface variation "
            "rather than a coherent localized structural footprint."
        ),
        "visible_change": "clear",
    },
    {
        "blind_id": "C",
        "confidence": 0.97,
        "disposition": "rejected_for_site_promotion",
        "image_quality": "usable",
        "proposal_area_m2_max": None,
        "proposal_area_m2_min": None,
        "proposal_area_m2_total": 0.0,
        "proposal_class": None,
        "proposal_count": 0,
        "rationale": (
            "There are no machine proposals. The overlay contains only sparse "
            "narrow edge fragments and isolated bright-surface pixels, with no "
            "coherent contiguous visible-change footprint."
        ),
        "visible_change": "none",
    },
)

DEFINITION_FILENAME = "definition.json"
BLIND_DECISIONS_FILENAME = "blind-decisions.json"
REVIEWS_FILENAME = "analyst-reviews.jsonl"
SUMMARY_FILENAME = "summary.json"
PUBLICATION_INCIDENT_FILENAME = "publication-incident.json"
README_FILENAME = "README.md"
ATTRIBUTION_FILENAME = "ATTRIBUTION.txt"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
BUILDER_PATH = Path(__file__).resolve()
ROOT_SHIM_PATH = PACKAGE_ROOT / "satellite_change_review_v83.py"
CLI_PATH = PACKAGE_ROOT / "scripts/build_satellite_change_review_v83.py"


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_line(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _strict_json(raw: bytes, label: str) -> Any:
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SatelliteChangeReviewV83Error(f"{label} is not valid JSON") from error


def _exact_file(
    path: Path,
    expected_bytes: int,
    expected_sha256: str,
    label: str,
) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise SatelliteChangeReviewV83Error(
            f"{label} must be a regular non-symlink file"
        )
    raw = path.read_bytes()
    if len(raw) != expected_bytes or _sha256(raw) != expected_sha256:
        raise SatelliteChangeReviewV83Error(f"{label} changed")
    return raw


def _file_record(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise SatelliteChangeReviewV83Error(f"builder file missing: {path}")
    raw = path.read_bytes()
    return {
        "bytes": len(raw),
        "path": path.relative_to(PACKAGE_ROOT).as_posix(),
        "sha256": _sha256(raw),
    }


def _blind_order() -> tuple[tuple[str, str], ...]:
    ranked = sorted(
        execution.SELECTED_QUEUE_IDS,
        key=lambda queue_id: hashlib.sha256(
            f"{ORDER_SALT}\0{queue_id}".encode("utf-8")
        ).digest(),
    )
    return tuple(zip(("A", "B", "C"), ranked, strict=True))


def _proposal_summary(raw: bytes, label: str) -> dict[str, Any]:
    document = _strict_json(raw, label)
    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        raise SatelliteChangeReviewV83Error(f"{label} is not a FeatureCollection")
    features = document.get("features")
    if not isinstance(features, list):
        raise SatelliteChangeReviewV83Error(f"{label} features changed")
    areas: list[float] = []
    classes: set[str] = set()
    for feature in features:
        if not isinstance(feature, dict) or set(feature) != {
            "geometry",
            "id",
            "properties",
            "type",
        }:
            raise SatelliteChangeReviewV83Error(f"{label} feature shape changed")
        properties = feature.get("properties")
        if not isinstance(properties, dict) or set(properties) != PROPOSAL_PROPERTY_KEYS:
            raise SatelliteChangeReviewV83Error(f"{label} properties changed")
        if properties.get("review_required") is not True or any(
            properties.get(key) is not False for key in PROPOSAL_FALSE_CLAIM_KEYS
        ):
            raise SatelliteChangeReviewV83Error(f"{label} claim flags changed")
        area = properties.get("area_m2")
        proposal_class = properties.get("class")
        if (
            isinstance(area, bool)
            or not isinstance(area, (int, float))
            or area <= 0
            or not isinstance(proposal_class, str)
            or not proposal_class
        ):
            raise SatelliteChangeReviewV83Error(f"{label} metrics changed")
        areas.append(float(area))
        classes.add(proposal_class)
    if len(classes) > 1:
        raise SatelliteChangeReviewV83Error(f"{label} proposal classes changed")
    return {
        "proposal_area_m2_max": max(areas) if areas else None,
        "proposal_area_m2_min": min(areas) if areas else None,
        "proposal_area_m2_total": sum(areas),
        "proposal_class": next(iter(classes)) if classes else None,
        "proposal_count": len(features),
    }


def _validate_incidents() -> tuple[dict[str, Any], dict[str, Any]]:
    raw = _exact_file(
        SOURCE_INCIDENT_PATH / "incident.json",
        SOURCE_INCIDENT_BYTES,
        SOURCE_INCIDENT_SHA256,
        "technical incident",
    )
    if audit.physical_tree_sha256(SOURCE_INCIDENT_PATH) != (
        SOURCE_INCIDENT_TREE_SHA256
    ):
        raise SatelliteChangeReviewV83Error("technical incident tree changed")
    incident = _strict_json(raw, "technical incident")
    if (
        incident.get("assertion_failure", {}).get("technical_not_model_outcome")
        is not True
        or incident.get("impact", {}).get("change_jobs_completed_before_assertion")
        != 3
        or incident.get("impact", {}).get("change_jobs_failed") != 0
        or incident.get("impact", {}).get("job_retried") is not False
        or incident.get("lineage", {}).get("final_manifest_sha256")
        != SOURCE_CHANGE_MANIFEST_SHA256
        or incident.get("lineage", {}).get("final_mode_sensitive_tree_sha256")
        != SOURCE_CHANGE_TREE_SHA256
    ):
        raise SatelliteChangeReviewV83Error("technical incident semantics changed")
    premature_raw = _exact_file(
        PREMATURE_DRAFT_TRASH_PATH,
        PREMATURE_DRAFT_BYTES,
        PREMATURE_DRAFT_SHA256,
        "rejected premature definition",
    )
    rejected_definition = PACKAGE_ROOT / REJECTED_DEFINITION_NAMESPACE
    rejected_review = PACKAGE_ROOT / REJECTED_REVIEW_NAMESPACE
    if (
        rejected_definition.exists()
        or rejected_definition.is_symlink()
        or rejected_review.exists()
        or rejected_review.is_symlink()
    ):
        raise SatelliteChangeReviewV83Error(
            "rejected premature final namespace was reused"
        )
    premature = {
        "atlas_mutated": False,
        "bytes": len(premature_raw),
        "decision_content_changed_in_rebuild": False,
        "detected_condition": "definition_appeared_alone_in_final_namespace",
        "disposition": "rejected_publication_control_violation",
        "model_or_analyst_outcome_created": False,
        "original_definition_namespace": REJECTED_DEFINITION_NAMESPACE,
        "original_review_namespace": REJECTED_REVIEW_NAMESPACE,
        "preserved_recoverably_in_trash": True,
        "sha256": _sha256(premature_raw),
        "trash_path": str(PREMATURE_DRAFT_TRASH_PATH),
    }
    return incident, premature


def _validate_source() -> dict[str, Any]:
    execution.validate_explicit_change_inputs_v83(
        SOURCE_QUEUE_PATH, SOURCE_CATALOG_PATH
    )
    if audit.physical_tree_sha256(SOURCE_QUEUE_PATH) != SOURCE_QUEUE_TREE_SHA256:
        raise SatelliteChangeReviewV83Error("source queue tree changed")
    if audit.physical_tree_sha256(SOURCE_CATALOG_PATH) != SOURCE_CATALOG_TREE_SHA256:
        raise SatelliteChangeReviewV83Error("source catalog tree changed")
    document = audit.validate_explicit_satellite_change_batch_v83_audit(
        SOURCE_CHANGE_PATH
    )
    raw = _exact_file(
        SOURCE_CHANGE_PATH / "batch-manifest.json",
        SOURCE_CHANGE_MANIFEST_BYTES,
        SOURCE_CHANGE_MANIFEST_SHA256,
        "source change manifest",
    )
    if _strict_json(raw, "source change manifest") != document:
        raise SatelliteChangeReviewV83Error("source change validator changed")
    if audit.physical_tree_sha256(SOURCE_CHANGE_PATH) != SOURCE_CHANGE_TREE_SHA256:
        raise SatelliteChangeReviewV83Error("source change tree changed")
    if (
        tuple(document.get("selection", {}).get("selected_queue_ids", ()))
        != execution.SELECTED_QUEUE_IDS
        or tuple(document.get("selection", {}).get("exclude_queue_ids", ()))
        != execution.EXCLUDED_QUEUE_IDS
        or document.get("summary", {}).get("jobs_completed") != 3
        or document.get("summary", {}).get("jobs_failed") != 0
    ):
        raise SatelliteChangeReviewV83Error("source selection changed")
    return document


def _blind_decision_document(recorded_at: str) -> tuple[dict[str, Any], bytes]:
    recorded_at, _ = publication._timestamp(recorded_at, "recorded_at")
    decisions = [dict(row) for row in BLIND_DECISIONS]
    counts = {
        "image_quality": dict(
            sorted(Counter(row["image_quality"] for row in decisions).items())
        ),
        "promotion_dispositions": dict(
            sorted(Counter(row["disposition"] for row in decisions).items())
        ),
        "visible_change": dict(
            sorted(Counter(row["visible_change"] for row in decisions).items())
        ),
    }
    for category, expected in EXPECTED_COUNTS.items():
        for key in expected:
            counts[category].setdefault(key, 0)
        counts[category] = dict(sorted(counts[category].items()))
    if counts != EXPECTED_COUNTS:
        raise SatelliteChangeReviewV83Error("blind decision accounting changed")
    document = {
        "artifact_type": "analyst_identity_blind_satellite_change_review_input",
        "decision_semantics": DECISION_SEMANTICS,
        "decisions": decisions,
        "guardrails": {
            key: value
            for key, value in GUARDRAILS.items()
            if key != "construction_status_claim_created"
        },
        "method": {
            "fresh_context_without_parent_history": True,
            "identity_metadata_available_during_review": False,
            "lineage_unsealed_after_visual_judgments_were_fixed": True,
            "manifest_or_report_available_during_review": False,
            "proposal_fields_used": ["area_m2", "claim_flags", "class", "count"],
            "reviewer_received_only_private_neutral_paths": True,
            "visual_artifacts_inspected_per_unit": sorted(VISUAL_ARTIFACT_NAMES),
        },
        "recorded_at": recorded_at,
        "review_id": BLIND_REVIEW_ID,
        "schema_version": 2,
        "summary": {
            "decisions": 3,
            **EXPECTED_COUNTS,
            "proposal_features_reviewed": 35,
        },
        "temporal_integrity": {
            "decision_content_changed_after_fresh_review": False,
            "final_root_ctime_must_not_precede_recorded_at": True,
            "member_staged_before_recorded_at": True,
            "premature_definition_rejected": True,
            "premature_definition_sha256": PREMATURE_DRAFT_SHA256,
            "published_in_same_frozen_transaction_as_review": True,
        },
    }
    return document, _canonical_json(document)


def _source_artifacts(
    source: Mapping[str, Any], queue_id: str
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    all_artifacts = source["jobs"][queue_id]["artifacts"]
    if set(all_artifacts) != SOURCE_ARTIFACT_NAMES | {"report.json"}:
        raise SatelliteChangeReviewV83Error(
            f"source artifact inventory changed: {queue_id}"
        )
    result: dict[str, dict[str, Any]] = {}
    proposal: dict[str, Any] | None = None
    for name in sorted(SOURCE_ARTIFACT_NAMES):
        spec = all_artifacts[name]
        path = SOURCE_CHANGE_PATH / "jobs" / queue_id / "change" / name
        raw = _exact_file(path, spec["bytes"], spec["sha256"], f"{queue_id}/{name}")
        if name.endswith(".png"):
            publication._png_chunks(raw, f"{queue_id}/{name}")
        else:
            proposal = _proposal_summary(raw, f"{queue_id}/{name}")
        result[name] = {
            "bytes": len(raw),
            "path": path.relative_to(PACKAGE_ROOT).as_posix(),
            "sha256": _sha256(raw),
        }
    if proposal is None:
        raise SatelliteChangeReviewV83Error(f"proposal missing: {queue_id}")
    return result, proposal


def _source_pins(
    incident: Mapping[str, Any],
    premature: Mapping[str, Any],
    blind_spec: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "blind_decisions": dict(blind_spec),
        "catalog": {
            "bytes": SOURCE_CATALOG_BYTES,
            "files": SOURCE_CATALOG_FILES,
            "manifest_bytes": 65_077,
            "manifest_sha256": execution.CATALOG_MANIFEST_SHA256,
            "path": SOURCE_CATALOG_PATH.relative_to(PACKAGE_ROOT).as_posix(),
            "selection_receipt_sha256": execution.SELECTION_RECEIPT_SHA256,
            "tree_sha256": SOURCE_CATALOG_TREE_SHA256,
        },
        "change_run": {
            "bytes": SOURCE_CHANGE_BYTES,
            "files": SOURCE_CHANGE_FILES,
            "manifest_bytes": SOURCE_CHANGE_MANIFEST_BYTES,
            "manifest_sha256": SOURCE_CHANGE_MANIFEST_SHA256,
            "path": SOURCE_CHANGE_PATH.relative_to(PACKAGE_ROOT).as_posix(),
            "tree_sha256": SOURCE_CHANGE_TREE_SHA256,
        },
        "queue": {
            "bytes": SOURCE_QUEUE_BYTES,
            "files": SOURCE_QUEUE_FILES,
            "manifest_bytes": 19_851,
            "manifest_sha256": execution.QUEUE_MANIFEST_SHA256,
            "path": SOURCE_QUEUE_PATH.relative_to(PACKAGE_ROOT).as_posix(),
            "queue_sha256": execution.QUEUE_SHA256,
            "tree_sha256": SOURCE_QUEUE_TREE_SHA256,
        },
        "rejected_premature_definition": dict(premature),
        "technical_incident": {
            "analyst_decision_created": False,
            "bytes": SOURCE_INCIDENT_BYTES,
            "classification": "post_run_presentation_assertion",
            "model_outcome_created": False,
            "path": (SOURCE_INCIDENT_PATH / "incident.json")
            .relative_to(PACKAGE_ROOT)
            .as_posix(),
            "sha256": SOURCE_INCIDENT_SHA256,
            "technical_not_model_outcome": incident["assertion_failure"][
                "technical_not_model_outcome"
            ],
            "tree_sha256": SOURCE_INCIDENT_TREE_SHA256,
        },
        "unavailable_catalog_job": {
            "analyst_decision_created": False,
            "count": 1,
            "queue_ids": list(execution.EXCLUDED_QUEUE_IDS),
            "reason": "baseline_scene_unavailable",
            "selection_receipt_sha256": execution.EXCLUSION_SHA256,
        },
    }


def _readme() -> bytes:
    return (
        "# Identity-blind analyst review of three v83 change jobs\n\n"
        "A fresh reviewer received only neutral A/B/C paths to before, after, "
        "comparison, change-overlay, and proposal artifacts. One proposal set is "
        "uncertain and retained for manual visible-change follow-up; two are "
        "rejected as bases for site promotion. No proposal set is promoted.\n\n"
        "These are visible-change triage dispositions only. They do not establish "
        "identity, location, project, construction, lifecycle, current status, "
        "operator, type, capacity, power, energy, PUE, workload, unique-site, or "
        "site-count facts, and the Atlas is not mutated.\n\n"
        "The earlier post-run order assertion is pinned separately as a technical "
        "incident, not a model or analyst outcome. Three change jobs had completed "
        "once with zero failures or retries before that assertion. The unavailable "
        "catalog job is also pinned outside the three review units and has no "
        "analyst disposition.\n"
    ).encode("utf-8")


def _attribution() -> bytes:
    return (
        "Contains modified Copernicus Sentinel data 2024 and 2026.\n"
        "Catalog: Element 84 Earth Search v1.\n"
        "Dataset: Copernicus Sentinel-2 Level-2A.\n"
        "The review bundle does not duplicate imagery; every inspected artifact "
        "is bound to its accepted upstream bytes by path, byte count, and SHA-256.\n"
    ).encode("utf-8")


def build_analyst_review(generated_at: str) -> dict[str, bytes]:
    """Build deterministic review bytes from accepted inputs and blind decisions."""

    generated_at, _ = publication._timestamp(generated_at, "generated_at")
    source = _validate_source()
    incident, premature = _validate_incidents()
    blind, blind_raw = _blind_decision_document(generated_at)
    decisions = blind["decisions"]
    order = dict(_blind_order())
    records: list[dict[str, Any]] = []
    for decision in decisions:
        queue_id = order[decision["blind_id"]]
        artifacts, proposal = _source_artifacts(source, queue_id)
        if any(decision[key] != value for key, value in proposal.items()):
            raise SatelliteChangeReviewV83Error(
                f"reviewed proposal metrics changed: {decision['blind_id']}"
            )
        records.append(
            {
                **decision,
                "decision_scope": "identity_blind_visible_change_triage_only",
                "input_artifacts": artifacts,
                "lineage_unsealed_after_visual_judgments_were_fixed": True,
                "queue_id": queue_id,
                "schema_version": 1,
                "visual_artifacts_inspected": sorted(VISUAL_ARTIFACT_NAMES),
            }
        )
    if [
        {key: record[key] for key in decision}
        for record, decision in zip(records, decisions, strict=True)
    ] != decisions:
        raise SatelliteChangeReviewV83Error("blind decisions changed during binding")
    blind_spec = {
        "bytes": len(blind_raw),
        "path": (
            Path("satellite_change_reviews") / REVIEW_ID / BLIND_DECISIONS_FILENAME
        ).as_posix(),
        "recorded_at": blind["recorded_at"],
        "sha256": _sha256(blind_raw),
    }
    sources = _source_pins(incident, premature, blind_spec)
    runtime = source["processor"]["runtime"]
    definition = {
        "blinding": {
            "blind_ids": ["A", "B", "C"],
            "lineage_unsealed_after_visual_judgments_were_fixed": True,
            "manifest_or_report_available_during_review": False,
            "order_algorithm": "ascending_sha256_utf8_salt_nul_queue_id",
            "order_salt_sha256": _sha256(ORDER_SALT.encode("utf-8")),
            "private_neutral_copies_only": True,
        },
        "builder": {
            "files": {
                "cli": _file_record(CLI_PATH),
                "module": _file_record(BUILDER_PATH),
                "root_shim": _file_record(ROOT_SHIM_PATH),
            }
        },
        "decision_semantics": DECISION_SEMANTICS,
        "format": "datacenter-atlas-v83-identity-blind-change-review-definition",
        "generated_at": generated_at,
        "guardrails": GUARDRAILS,
        "review_id": REVIEW_ID,
        "runtime": runtime,
        "schema_version": 1,
        "sources": sources,
    }
    counts = {
        "analyst_decisions": 3,
        "change_jobs_reviewed": 3,
        "image_quality": EXPECTED_COUNTS["image_quality"],
        "machine_proposal_features_reviewed": 35,
        "machine_run_failures": 0,
        "machine_run_jobs_completed_once": 3,
        "machine_run_retries": 0,
        "promotion_dispositions": EXPECTED_COUNTS["promotion_dispositions"],
        "review_input_artifacts_hash_bound": 15,
        "technical_incidents_without_model_or_analyst_outcome": 1,
        "unavailable_catalog_jobs_without_analyst_decision": 1,
        "visible_change": EXPECTED_COUNTS["visible_change"],
        "visual_artifacts_inspected": 12,
    }
    summary = {
        "counts": counts,
        "decision_semantics": DECISION_SEMANTICS,
        "generated_at": generated_at,
        "guardrails": GUARDRAILS,
        "review_id": REVIEW_ID,
        "schema_version": 1,
        "sources": sources,
    }
    output = {
        ATTRIBUTION_FILENAME: _attribution(),
        BLIND_DECISIONS_FILENAME: blind_raw,
        DEFINITION_FILENAME: _canonical_json(definition),
        PUBLICATION_INCIDENT_FILENAME: _canonical_json(
            {
                "artifact_type": "review_publication_control_incident",
                "final_paths_absent_before_rebuild": True,
                "incident": premature,
                "new_review_id": REVIEW_ID,
                "recorded_at": generated_at,
                "schema_version": 1,
                "transaction": {
                    "atomic_no_replace_root_promotion": True,
                    "private_stage_before_publication": True,
                    "rollback_on_prepublication_failure": True,
                    "single_frozen_root_contains_decisions_and_review": True,
                },
            }
        ),
        README_FILENAME: _readme(),
        REVIEWS_FILENAME: b"".join(_canonical_line(row) for row in records),
        SUMMARY_FILENAME: _canonical_json(summary),
    }
    manifest = {
        "artifacts": {
            name: {"bytes": len(raw), "sha256": _sha256(raw)}
            for name, raw in sorted(output.items())
        },
        "decision_semantics": DECISION_SEMANTICS,
        "format": "datacenter-atlas-v83-identity-blind-change-review",
        "generated_at": generated_at,
        "guardrails": GUARDRAILS,
        "review_id": REVIEW_ID,
        "schema_version": 1,
        "sources": sources,
        "summary": counts,
    }
    manifest_raw = _canonical_json(manifest)
    output[MANIFEST_FILENAME] = manifest_raw
    output[MANIFEST_HASH_FILENAME] = (
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    )
    return output


def _write_file(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def suggested_generated_at() -> str:
    target = datetime.now(UTC) + timedelta(seconds=120)
    return target.isoformat(timespec="microseconds").replace("+00:00", "Z")


def publish_analyst_review(
    generated_at: str,
    output_path: Path = OUTPUT_PATH,
) -> dict[str, Any]:
    """Build in a private stage, time-gate, freeze, and publish no-replace."""

    canonical_time, target = publication._timestamp(generated_at, "generated_at")
    destination = output_path.resolve()
    if destination != OUTPUT_PATH.resolve():
        raise SatelliteChangeReviewV83Error("review output path changed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / f".{destination.name}.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise SatelliteChangeReviewV83Error(f"active output lock: {lock}") from error
    stage: Path | None = None
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        if destination.exists() or destination.is_symlink():
            raise SatelliteChangeReviewV83Error(
                f"refusing existing output: {destination}"
            )
        stage = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        if stat.S_IMODE(stage.stat().st_mode) != 0o700:
            raise SatelliteChangeReviewV83Error("review stage is not private")
        files = build_analyst_review(canonical_time)
        for name, raw in sorted(files.items()):
            _write_file(stage / name, raw)
        newest = max(
            max(item.stat().st_mtime, getattr(item.stat(), "st_birthtime", 0.0))
            for item in [stage, *stage.rglob("*")]
        )
        if newest > target.timestamp() + 1e-6:
            raise SatelliteChangeReviewV83Error(
                "staged review bytes postdate generated_at"
            )
        publication._freeze_tree(stage)
        while datetime.now(UTC) < target:
            remaining = (target - datetime.now(UTC)).total_seconds()
            time.sleep(min(max(remaining, 0.0), 0.25))
        try:
            publication._promote_noreplace(stage, destination)
        except Exception as error:
            raise SatelliteChangeReviewV83Error(str(error)) from error
        stage = None
        if destination.stat().st_ctime + 1e-6 < target.timestamp():
            raise SatelliteChangeReviewV83Error(
                "review root ctime precedes generated_at"
            )
        return validate_analyst_review(destination)
    finally:
        os.close(descriptor)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)


def validate_analyst_review(output_path: Path = OUTPUT_PATH) -> dict[str, Any]:
    """Rebuild and verify the frozen review byte-for-byte offline."""

    destination = output_path.resolve()
    if destination != OUTPUT_PATH.resolve():
        raise SatelliteChangeReviewV83Error("review output path changed")
    definition = _strict_json(
        (destination / DEFINITION_FILENAME).read_bytes(), "review definition"
    )
    generated_at, target = publication._timestamp(
        definition.get("generated_at"), "generated_at"
    )
    if destination.stat().st_ctime + 1e-6 < target.timestamp():
        raise SatelliteChangeReviewV83Error(
            "review root ctime precedes generated_at"
        )
    inventory = publication._tree_inventory(destination)
    actual = {
        path.name: path.read_bytes()
        for path in destination.iterdir()
        if path.is_file()
    }
    expected = build_analyst_review(generated_at)
    if actual != expected:
        raise SatelliteChangeReviewV83Error(
            "review differs from offline reconstruction"
        )
    manifest_raw = actual[MANIFEST_FILENAME]
    if actual[MANIFEST_HASH_FILENAME] != (
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    ):
        raise SatelliteChangeReviewV83Error("review manifest sidecar changed")
    return {
        **_strict_json(manifest_raw, "review manifest"),
        "tree_inventory": inventory,
    }


__all__ = [
    "GUARDRAILS",
    "OUTPUT_PATH",
    "REVIEW_ID",
    "SatelliteChangeReviewV83Error",
    "build_analyst_review",
    "publish_analyst_review",
    "suggested_generated_at",
    "validate_analyst_review",
]
