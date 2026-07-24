"""Immutable calibration audit over pinned Sentinel analyst-review pairs.

This module intentionally evaluates only descriptive triage rules against a
small, selected set of site-aligned follow-up decisions.  It does not turn the
decisions into pixel truth, construction truth, or atlas claims.
"""

from __future__ import annotations

from collections import Counter
import csv
from datetime import UTC, datetime
import hashlib
import io
import json
from math import fsum, isfinite
import os
from pathlib import Path
import re
import shutil
from statistics import median
import tempfile
from typing import Any, Mapping, Sequence

from .candidate_fusion import CandidateFusionError, validate_candidate_fusion


FORMAT = "datacenter-atlas-satellite-calibration-v1"
SCHEMA_VERSION = 1
CALIBRATION_ID_V1 = "analyst-reviews-2026-07-18-v1"
CALIBRATION_ID_V2 = "analyst-reviews-2026-07-18-v2"
CALIBRATION_ID_V3 = "analyst-reviews-2026-07-18-v3"
CALIBRATION_ID_V4 = "analyst-reviews-2026-07-18-v4"
CALIBRATION_ID = CALIBRATION_ID_V1
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
RECORDS_FILENAME = "calibration-records.jsonl"
RECORDS_CSV_FILENAME = "calibration-records.csv"
SUMMARY_FILENAME = "summary.json"
README_FILENAME = "README.md"
ATTRIBUTION_FILENAME = "ATTRIBUTION.txt"
BUNDLE_FILES = frozenset(
    {
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
        RECORDS_FILENAME,
        RECORDS_CSV_FILENAME,
        SUMMARY_FILENAME,
        README_FILENAME,
        ATTRIBUTION_FILENAME,
    }
)

METRIC_FIELDS = (
    ("valid_pixel_fraction", "fraction"),
    ("proposal_component_count", "count"),
    ("proposal_area_m2_after_component_filter", "square_metres"),
    ("proposal_pixel_fraction_of_valid", "fraction"),
    ("mean_absolute_reflectance_change", "reflectance"),
    ("mean_baseline_ndvi", "index"),
    ("mean_current_ndvi", "index"),
    ("mean_ndvi_change", "index_change"),
    ("mean_ndbi_change", "index_change"),
)
METRIC_NAMES = tuple(name for name, _unit in METRIC_FIELDS)
METRIC_UNITS = dict(METRIC_FIELDS)

DECISION_OUTCOMES = {
    "reject_automated_mask_for_site_promotion": "reject",
    "retain_site_aligned_change_candidate_for_manual_followup": "retain",
}
EXPECTED_REVIEW_SCOPE = {
    "data_center_identity_confirmed": False,
    "lifecycle_status_confirmed": False,
    "operating_status_inferred": False,
    "power_or_energy_inferred": False,
    "review_required": True,
}
SCOPE_POLICY = {
    "accuracy_generalization_claimed": False,
    "analyst_decision_is_construction_truth": False,
    "analyst_decision_is_pixel_truth": False,
    "analyst_decision_is_site_aligned_followup_label": True,
    "automatic_merge_performed": False,
    "identity_claim_promoted": False,
    "lifecycle_claim_promoted": False,
    "operating_status_promoted": False,
    "power_or_energy_promoted": False,
    "production_threshold_selected": False,
    "raw_images_included": False,
    "recall_denominator_available": False,
    "sample_is_random": False,
    "sample_is_selected": True,
    "sample_size": 25,
    "type_or_workload_claim_promoted": False,
    "unique_physical_site_count": None,
}
SCOPE_POLICY_V2 = {**SCOPE_POLICY, "sample_size": 31}
SCOPE_POLICY_V3 = {**SCOPE_POLICY, "sample_size": 37}
SCOPE_POLICY_V4 = {**SCOPE_POLICY, "sample_size": 43}
_CALIBRATION_CONFIGS = {
    CALIBRATION_ID_V1: {
        "candidate_fusion_version": "v9",
        "scope": SCOPE_POLICY,
    },
    CALIBRATION_ID_V2: {
        "candidate_fusion_version": "v10",
        "scope": SCOPE_POLICY_V2,
    },
    CALIBRATION_ID_V3: {
        "candidate_fusion_version": "v11",
        "scope": SCOPE_POLICY_V3,
    },
    CALIBRATION_ID_V4: {
        "candidate_fusion_version": "v13",
        "scope": SCOPE_POLICY_V4,
    },
}
_RULE_RATIONALE = (
    "Round, interpretable audit anchor declared before this calibration artifact; "
    "not a label-tuned or production threshold."
)
PREDECLARED_RULES = (
    {
        "id": "any-filtered-component",
        "metric": "proposal_component_count",
        "operator": ">=",
        "threshold": 1,
        "unit": "count",
        "rationale": _RULE_RATIONALE,
    },
    {
        "id": "proposal-area-ge-10000-m2",
        "metric": "proposal_area_m2_after_component_filter",
        "operator": ">=",
        "threshold": 10_000,
        "unit": "square_metres",
        "rationale": _RULE_RATIONALE,
    },
    {
        "id": "proposal-area-ge-50000-m2",
        "metric": "proposal_area_m2_after_component_filter",
        "operator": ">=",
        "threshold": 50_000,
        "unit": "square_metres",
        "rationale": _RULE_RATIONALE,
    },
    {
        "id": "proposal-fraction-ge-0.01",
        "metric": "proposal_pixel_fraction_of_valid",
        "operator": ">=",
        "threshold": 0.01,
        "unit": "fraction",
        "rationale": _RULE_RATIONALE,
    },
    {
        "id": "proposal-fraction-ge-0.05",
        "metric": "proposal_pixel_fraction_of_valid",
        "operator": ">=",
        "threshold": 0.05,
        "unit": "fraction",
        "rationale": _RULE_RATIONALE,
    },
)

ROW_FIELDS = (
    "schema_version",
    "queue_id",
    "source_run",
    "entity_id",
    "entity_name",
    "mgrs_tile",
    "baseline_datetime",
    "current_datetime",
    "baseline_stac_item_sha256",
    "current_stac_item_sha256",
    "source_dataset",
    "source_catalog",
    "reviewed_at",
    "decision",
    "outcome",
    "report_path",
    "report_bytes",
    "report_sha256",
    "review_path",
    "review_bytes",
    "review_sha256",
) + METRIC_NAMES

_HASH_RE = re.compile(r"[0-9a-f]{64}")
_QUEUE_RE = re.compile(r"satq-[0-9a-f]{24}")
_RUN_RE = re.compile(r"global-open-v3-(?:active|proposed|unknown)-\d{3}")
_INPUT_PATH_RE = re.compile(
    r"\.\./satellite_review_runs/2026-07-18-"
    r"(?P<run>global-open-v3-(?:active|proposed|unknown)-\d{3})/jobs/"
    r"(?P<queue>satq-[0-9a-f]{24})/change/(?P<name>report|analyst-review)\.json"
)


class SatelliteCalibrationError(ValueError):
    """Raised when the calibration definition, input, or bundle fails closed."""


def _calibration_config(calibration_id: Any) -> Mapping[str, Any]:
    if not isinstance(calibration_id, str):
        raise SatelliteCalibrationError("calibration identity is unsupported")
    config = _CALIBRATION_CONFIGS.get(calibration_id)
    if config is None:
        raise SatelliteCalibrationError("calibration identity is unsupported")
    return config


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_line(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _bytes_checkpoint(raw: bytes) -> dict[str, Any]:
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def _checkpoint(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def _timestamp(value: Any, label: str, *, whole_seconds: bool = False) -> str:
    if not isinstance(value, str) or not value:
        raise SatelliteCalibrationError(f"{label} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SatelliteCalibrationError(f"{label} must be ISO 8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SatelliteCalibrationError(f"{label} must include a timezone")
    if whole_seconds:
        canonical = parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
        if canonical != value:
            raise SatelliteCalibrationError(
                f"{label} must be canonical UTC whole seconds"
            )
    return value


def _json_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise SatelliteCalibrationError(f"{label} must be a regular file: {path}")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SatelliteCalibrationError(f"{label} must be valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise SatelliteCalibrationError(f"{label} must be a JSON object")
    return value, raw


def _safe_relative(root: Path, raw_path: Any, label: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise SatelliteCalibrationError(f"{label} path must be non-empty text")
    supplied = Path(raw_path)
    if supplied.is_absolute():
        raise SatelliteCalibrationError(f"{label} path must be relative")
    resolved = (root / supplied).resolve()
    package_root = root.parent.resolve()
    if resolved != package_root and package_root not in resolved.parents:
        raise SatelliteCalibrationError(f"{label} path escapes the package root")
    return resolved


def _checkpoint_spec(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"path", "bytes", "sha256"}:
        raise SatelliteCalibrationError(f"{label} checkpoint schema changed")
    if (
        not isinstance(value["path"], str)
        or not value["path"]
        or not isinstance(value["bytes"], int)
        or isinstance(value["bytes"], bool)
        or value["bytes"] <= 0
        or not isinstance(value["sha256"], str)
        or _HASH_RE.fullmatch(value["sha256"]) is None
    ):
        raise SatelliteCalibrationError(f"{label} checkpoint is invalid")
    return value


def _verify_checkpoint(path: Path, spec: Mapping[str, Any], label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise SatelliteCalibrationError(f"{label} must be a regular file")
    if _checkpoint(path) != {"bytes": spec["bytes"], "sha256": spec["sha256"]}:
        raise SatelliteCalibrationError(f"{label} hash or byte count changed")


def _load_definition(
    path: str | Path,
) -> tuple[dict[str, Any], bytes, Path]:
    supplied = Path(path)
    definition, raw = _json_object(supplied, "calibration definition")
    if raw != _canonical_json(definition):
        raise SatelliteCalibrationError(
            "calibration definition must be canonical pretty JSON"
        )
    if set(definition) != {
        "schema_version",
        "calibration_id",
        "generated_at",
        "candidate_fusion",
        "review_pairs",
        "rules",
        "scope",
    }:
        raise SatelliteCalibrationError("calibration definition schema changed")
    config = _calibration_config(definition.get("calibration_id"))
    scope = config["scope"]
    if (
        definition.get("schema_version") != SCHEMA_VERSION
        or definition.get("scope") != scope
        or definition.get("rules") != list(PREDECLARED_RULES)
    ):
        raise SatelliteCalibrationError(
            "calibration definition identity, rules, or safeguards changed"
        )
    _timestamp(
        definition.get("generated_at"),
        "calibration definition generated_at",
        whole_seconds=True,
    )
    fusion = definition.get("candidate_fusion")
    if not isinstance(fusion, Mapping) or set(fusion) != {"definition", "manifest"}:
        raise SatelliteCalibrationError("candidate-fusion pin schema changed")
    _checkpoint_spec(fusion["definition"], "candidate-fusion definition")
    _checkpoint_spec(fusion["manifest"], "candidate-fusion manifest")

    pairs = definition.get("review_pairs")
    sample_size = scope["sample_size"]
    if not isinstance(pairs, list) or len(pairs) != sample_size:
        raise SatelliteCalibrationError(
            f"calibration must pin exactly {sample_size} review pairs"
        )
    queue_ids: list[str] = []
    report_hashes: set[str] = set()
    review_hashes: set[str] = set()
    for index, pair in enumerate(pairs):
        if not isinstance(pair, Mapping) or set(pair) != {
            "queue_id",
            "source_run",
            "report",
            "review",
        }:
            raise SatelliteCalibrationError(f"review pair {index} schema changed")
        queue_id = pair.get("queue_id")
        source_run = pair.get("source_run")
        if not isinstance(queue_id, str) or _QUEUE_RE.fullmatch(queue_id) is None:
            raise SatelliteCalibrationError(f"review pair {index} queue_id is invalid")
        if not isinstance(source_run, str) or _RUN_RE.fullmatch(source_run) is None:
            raise SatelliteCalibrationError(f"review pair {index} source_run is invalid")
        report = _checkpoint_spec(pair.get("report"), f"review pair {index} report")
        review = _checkpoint_spec(pair.get("review"), f"review pair {index} review")
        report_match = _INPUT_PATH_RE.fullmatch(report["path"])
        review_match = _INPUT_PATH_RE.fullmatch(review["path"])
        if (
            report_match is None
            or review_match is None
            or report_match.group("name") != "report"
            or review_match.group("name") != "analyst-review"
            or report_match.group("queue") != queue_id
            or review_match.group("queue") != queue_id
            or report_match.group("run") != source_run
            or review_match.group("run") != source_run
        ):
            raise SatelliteCalibrationError(f"review pair {index} path lineage changed")
        if report["sha256"] in report_hashes or review["sha256"] in review_hashes:
            raise SatelliteCalibrationError(f"review pair {index} repeats an input hash")
        queue_ids.append(queue_id)
        report_hashes.add(report["sha256"])
        review_hashes.add(review["sha256"])
    if queue_ids != sorted(queue_ids) or len(set(queue_ids)) != len(queue_ids):
        raise SatelliteCalibrationError(
            "review pairs must have unique queue IDs in lexical order"
        )
    return definition, raw, supplied.resolve()


def _finite_number(value: Any, label: str) -> int | float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(float(value))
    ):
        raise SatelliteCalibrationError(f"{label} must be a finite number")
    return value


def _validate_metrics(metrics: Any, label: str) -> dict[str, int | float]:
    if not isinstance(metrics, Mapping) or set(metrics) != set(METRIC_NAMES):
        raise SatelliteCalibrationError(f"{label} metric schema changed")
    values = {name: _finite_number(metrics[name], f"{label} {name}") for name in METRIC_NAMES}
    if (
        not 0 <= float(values["valid_pixel_fraction"]) <= 1
        or not 0 <= float(values["proposal_pixel_fraction_of_valid"]) <= 1
        or float(values["proposal_area_m2_after_component_filter"]) < 0
        or float(values["mean_absolute_reflectance_change"]) < 0
        or not -1 <= float(values["mean_baseline_ndvi"]) <= 1
        or not -1 <= float(values["mean_current_ndvi"]) <= 1
        or not -2 <= float(values["mean_ndvi_change"]) <= 2
        or not -2 <= float(values["mean_ndbi_change"]) <= 2
    ):
        raise SatelliteCalibrationError(f"{label} metric bounds changed")
    component_count = values["proposal_component_count"]
    if not isinstance(component_count, int) or isinstance(component_count, bool) or component_count < 0:
        raise SatelliteCalibrationError(f"{label} component count must be a non-negative integer")
    return values


def _row_from_pair(
    pair: Mapping[str, Any], root: Path, index: int
) -> dict[str, Any]:
    report_spec = pair["report"]
    review_spec = pair["review"]
    report_path = _safe_relative(root, report_spec["path"], f"review pair {index} report")
    review_path = _safe_relative(root, review_spec["path"], f"review pair {index} review")
    _verify_checkpoint(report_path, report_spec, f"review pair {index} report")
    _verify_checkpoint(review_path, review_spec, f"review pair {index} review")
    report, _report_raw = _json_object(report_path, f"review pair {index} report")
    review, _review_raw = _json_object(review_path, f"review pair {index} review")

    decision = review.get("decision")
    classification = report.get("classification")
    if (
        decision not in DECISION_OUTCOMES
        or review.get("input_report_sha256") != report_spec["sha256"]
        or review.get("atlas_claims_created") is not False
        or review.get("automated_promotion_allowed") is not False
        or review.get("scope") != EXPECTED_REVIEW_SCOPE
        or review.get("review_method") != "manual_visual_inspection_of_comparison_png"
        or not isinstance(classification, Mapping)
        or classification.get("identity_claim") is not False
        or classification.get("lifecycle_claim") is not False
        or classification.get("review_required") is not True
    ):
        raise SatelliteCalibrationError(f"review pair {index} safeguards changed")

    entity = report.get("entity")
    baseline = report.get("baseline")
    current = report.get("current")
    source = report.get("source")
    if not all(isinstance(value, Mapping) for value in (entity, baseline, current, source)):
        raise SatelliteCalibrationError(f"review pair {index} report metadata changed")
    entity_id = entity.get("id")
    entity_name = entity.get("name")
    mgrs_tile = baseline.get("mgrs_tile")
    if (
        not isinstance(entity_id, str)
        or not entity_id
        or not isinstance(entity_name, str)
        or not entity_name
        or not isinstance(mgrs_tile, str)
        or not mgrs_tile
        or current.get("mgrs_tile") != mgrs_tile
    ):
        raise SatelliteCalibrationError(f"review pair {index} entity or tile changed")
    baseline_datetime = _timestamp(
        baseline.get("datetime"), f"review pair {index} baseline datetime"
    )
    current_datetime = _timestamp(
        current.get("datetime"), f"review pair {index} current datetime"
    )
    reviewed_at = _timestamp(
        review.get("reviewed_at"),
        f"review pair {index} reviewed_at",
        whole_seconds=True,
    )
    if datetime.fromisoformat(baseline_datetime.replace("Z", "+00:00")) >= datetime.fromisoformat(
        current_datetime.replace("Z", "+00:00")
    ):
        raise SatelliteCalibrationError(f"review pair {index} scene order changed")
    for label, digest in (
        ("baseline STAC item", baseline.get("stac_item_sha256")),
        ("current STAC item", current.get("stac_item_sha256")),
    ):
        if not isinstance(digest, str) or _HASH_RE.fullmatch(digest) is None:
            raise SatelliteCalibrationError(f"review pair {index} {label} hash is invalid")
    dataset = source.get("dataset")
    catalog = source.get("catalog")
    if not isinstance(dataset, str) or not dataset or not isinstance(catalog, str) or not catalog:
        raise SatelliteCalibrationError(f"review pair {index} source metadata changed")

    row = {
        "schema_version": SCHEMA_VERSION,
        "queue_id": pair["queue_id"],
        "source_run": pair["source_run"],
        "entity_id": entity_id,
        "entity_name": entity_name,
        "mgrs_tile": mgrs_tile,
        "baseline_datetime": baseline_datetime,
        "current_datetime": current_datetime,
        "baseline_stac_item_sha256": baseline["stac_item_sha256"],
        "current_stac_item_sha256": current["stac_item_sha256"],
        "source_dataset": dataset,
        "source_catalog": catalog,
        "reviewed_at": reviewed_at,
        "decision": decision,
        "outcome": DECISION_OUTCOMES[decision],
        "report_path": report_spec["path"],
        "report_bytes": report_spec["bytes"],
        "report_sha256": report_spec["sha256"],
        "review_path": review_spec["path"],
        "review_bytes": review_spec["bytes"],
        "review_sha256": review_spec["sha256"],
    }
    row.update(_validate_metrics(report.get("metrics"), f"review pair {index}"))
    if set(row) != set(ROW_FIELDS):
        raise SatelliteCalibrationError("internal calibration row schema changed")
    return row


def _load_inputs(
    definition: Mapping[str, Any], definition_path: Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root = definition_path.parent
    fusion_spec = definition["candidate_fusion"]
    candidate_definition_path = _safe_relative(
        root, fusion_spec["definition"]["path"], "candidate-fusion definition"
    )
    candidate_manifest_path = _safe_relative(
        root, fusion_spec["manifest"]["path"], "candidate-fusion manifest"
    )
    _verify_checkpoint(
        candidate_definition_path,
        fusion_spec["definition"],
        "candidate-fusion definition",
    )
    _verify_checkpoint(
        candidate_manifest_path,
        fusion_spec["manifest"],
        "candidate-fusion manifest",
    )
    try:
        candidate_manifest = validate_candidate_fusion(candidate_manifest_path.parent)
    except CandidateFusionError as error:
        raise SatelliteCalibrationError(
            f"candidate-fusion validation failed: {error}"
        ) from error
    if candidate_manifest_path.name != MANIFEST_FILENAME or candidate_manifest.get(
        "definition"
    ) != {
        "filename": candidate_definition_path.name,
        "bytes": fusion_spec["definition"]["bytes"],
        "sha256": fusion_spec["definition"]["sha256"],
    }:
        raise SatelliteCalibrationError("candidate-fusion definition lineage changed")
    candidate_definition, _ = _json_object(
        candidate_definition_path, "candidate-fusion definition"
    )
    candidate_specs = candidate_definition.get("inputs", {}).get(
        "satellite_analyst_reviews"
    )
    sample_size = definition["scope"]["sample_size"]
    if not isinstance(candidate_specs, list) or len(candidate_specs) != sample_size:
        raise SatelliteCalibrationError(
            f"candidate-fusion does not pin the expected {sample_size} review pairs"
        )
    candidate_by_queue: dict[str, Mapping[str, Any]] = {}
    for spec in candidate_specs:
        if not isinstance(spec, Mapping) or set(spec) != {
            "path",
            "queue_id",
            "report_path",
            "report_sha256",
            "sha256",
        }:
            raise SatelliteCalibrationError("candidate-fusion review spec changed")
        queue_id = spec["queue_id"]
        if queue_id in candidate_by_queue:
            raise SatelliteCalibrationError("candidate-fusion repeats a review queue")
        candidate_by_queue[queue_id] = spec
    if set(candidate_by_queue) != {
        pair["queue_id"] for pair in definition["review_pairs"]
    }:
        raise SatelliteCalibrationError("calibration review-pair set differs from candidate-fusion")

    rows: list[dict[str, Any]] = []
    for index, pair in enumerate(definition["review_pairs"]):
        candidate_spec = candidate_by_queue[pair["queue_id"]]
        if (
            pair["report"]["path"] != candidate_spec["report_path"]
            or pair["report"]["sha256"] != candidate_spec["report_sha256"]
            or pair["review"]["path"] != candidate_spec["path"]
            or pair["review"]["sha256"] != candidate_spec["sha256"]
        ):
            raise SatelliteCalibrationError(
                f"review pair {index} differs from candidate-fusion pins"
            )
        rows.append(_row_from_pair(pair, root, index))
    return rows, {
        "candidate_fusion": {
            "definition": dict(fusion_spec["definition"]),
            "manifest": dict(fusion_spec["manifest"]),
        },
        "review_pairs": [
            {
                "queue_id": pair["queue_id"],
                "source_run": pair["source_run"],
                "report": dict(pair["report"]),
                "review": dict(pair["review"]),
            }
            for pair in definition["review_pairs"]
        ],
    }


def evaluate_rule(record: Mapping[str, Any], rule: Mapping[str, Any]) -> bool:
    """Return a predeclared rule result without interpreting it as truth."""

    if rule not in PREDECLARED_RULES:
        raise SatelliteCalibrationError("rule is not one of the predeclared audit rules")
    value = _finite_number(record.get(rule["metric"]), f"rule {rule['id']} metric")
    if rule["operator"] != ">=":
        raise SatelliteCalibrationError("unsupported calibration rule operator")
    return float(value) >= float(rule["threshold"])


def _distribution(values: Sequence[int | float]) -> dict[str, Any]:
    if not values:
        raise SatelliteCalibrationError("distribution cannot be empty")
    return {
        "count": len(values),
        "min": min(values),
        "mean": fsum(float(value) for value in values) / len(values),
        "median": median(values),
        "max": max(values),
    }


def _summary(
    records: Sequence[Mapping[str, Any]],
    generated_at: str,
    calibration_id: str,
) -> dict[str, Any]:
    config = _calibration_config(calibration_id)
    outcomes = Counter(record["outcome"] for record in records)
    source_runs = Counter(record["source_run"] for record in records)
    distributions: dict[str, Any] = {}
    for metric in METRIC_NAMES:
        distributions[metric] = {
            "unit": METRIC_UNITS[metric],
            "all": _distribution([record[metric] for record in records]),
            "retain": _distribution(
                [record[metric] for record in records if record["outcome"] == "retain"]
            ),
            "reject": _distribution(
                [record[metric] for record in records if record["outcome"] == "reject"]
            ),
        }
    evaluations: list[dict[str, Any]] = []
    for rule in PREDECLARED_RULES:
        contingency = Counter()
        for record in records:
            state = "positive" if evaluate_rule(record, rule) else "negative"
            contingency[f"analyst_{record['outcome']}_rule_{state}"] += 1
        evaluations.append(
            {
                "rule": dict(rule),
                "sample_size": len(records),
                "contingency": {
                    key: contingency[key]
                    for key in (
                        "analyst_reject_rule_negative",
                        "analyst_reject_rule_positive",
                        "analyst_retain_rule_negative",
                        "analyst_retain_rule_positive",
                    )
                },
                "interpretation": (
                    "Descriptive counts on this selected sample only; not a production "
                    "threshold, accuracy estimate, or recall estimate."
                ),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "calibration_id": calibration_id,
        "generated_at": generated_at,
        "scope": config["scope"],
        "sample": {
            "count": len(records),
            "outcome_counts": dict(sorted(outcomes.items())),
            "source_run_counts": dict(sorted(source_runs.items())),
        },
        "metric_distributions": distributions,
        "rule_evaluations": evaluations,
    }


def _csv_bytes(records: Sequence[Mapping[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=ROW_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows({field: record[field] for field in ROW_FIELDS} for record in records)
    return output.getvalue().encode("utf-8")


def _readme(summary: Mapping[str, Any]) -> bytes:
    counts = summary["sample"]["outcome_counts"]
    sample_size = summary["sample"]["count"]
    candidate_fusion_version = _calibration_config(summary["calibration_id"])[
        "candidate_fusion_version"
    ]
    return f"""# Sentinel analyst-review calibration audit

This immutable audit contains report-level metrics and hash-linked decision labels for exactly
{sample_size} report/review pairs pinned by candidate-fusion {candidate_fusion_version}: {counts['retain']} retain and
{counts['reject']} reject decisions. No raw imagery is copied into this bundle.

The sample is selected and non-random. The analyst decisions are site-aligned follow-up labels,
not pixel truth and not construction truth. The simple rules were predeclared as round,
interpretable audit anchors; none is selected here as a production threshold. The audit has no
recall denominator and provides no basis for generalising accuracy beyond these {sample_size} pairs.

Nothing here promotes data-centre identity, lifecycle or operating status, type or workload,
power, or energy claims. `calibration-records.jsonl` is the complete row-level distribution;
`summary.json` reports per-outcome descriptive distributions and rule contingency counts.
""".encode("utf-8")


def _attribution() -> bytes:
    return (
        "Contains derived metrics from modified Copernicus Sentinel-2 Level-2A data.\n"
        "Imagery was accessed through Element 84 Earth Search; no raw imagery is included.\n"
    ).encode("utf-8")


def _payloads(
    records: Sequence[Mapping[str, Any]],
    generated_at: str,
    calibration_id: str = CALIBRATION_ID,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    summary = _summary(records, generated_at, calibration_id)
    payloads = {
        RECORDS_FILENAME: b"".join(_canonical_line(record) for record in records),
        RECORDS_CSV_FILENAME: _csv_bytes(records),
        SUMMARY_FILENAME: _canonical_json(summary),
        README_FILENAME: _readme(summary),
        ATTRIBUTION_FILENAME: _attribution(),
    }
    return payloads, summary


def _manifest(
    definition: Mapping[str, Any],
    definition_raw: bytes,
    definition_file: Path,
    inputs: Mapping[str, Any],
    payloads: Mapping[str, bytes],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    outputs = {
        name: {
            **_bytes_checkpoint(raw),
            **(
                {"records": summary["sample"]["count"]}
                if name in {RECORDS_FILENAME, RECORDS_CSV_FILENAME}
                else {}
            ),
        }
        for name, raw in payloads.items()
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "format": FORMAT,
        "calibration_id": definition["calibration_id"],
        "generated_at": definition["generated_at"],
        "scope": definition["scope"],
        "rules": list(PREDECLARED_RULES),
        "definition": {
            "filename": definition_file.name,
            "bytes": len(definition_raw),
            "sha256": _sha256(definition_raw),
        },
        "inputs": inputs,
        "counts": summary["sample"],
        "outputs": outputs,
    }


def _write_fsync(path: Path, raw: bytes) -> None:
    with path.open("wb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())


def write_satellite_calibration(
    definition_path: str | Path,
    output_directory: str | Path,
    *,
    freeze: bool = True,
) -> dict[str, Any]:
    definition, definition_raw, definition_file = _load_definition(definition_path)
    records, inputs = _load_inputs(definition, definition_file)
    payloads, summary = _payloads(
        records,
        definition["generated_at"],
        definition["calibration_id"],
    )
    manifest = _manifest(
        definition,
        definition_raw,
        definition_file,
        inputs,
        payloads,
        summary,
    )
    manifest_raw = _canonical_json(manifest)
    sidecar = f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    destination = Path(os.path.abspath(os.fspath(output_directory)))
    if destination.exists() or destination.is_symlink():
        raise SatelliteCalibrationError(
            f"refusing existing satellite-calibration output: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent)
    )
    try:
        for name, raw in payloads.items():
            _write_fsync(stage / name, raw)
        _write_fsync(stage / MANIFEST_FILENAME, manifest_raw)
        _write_fsync(stage / MANIFEST_HASH_FILENAME, sidecar)
        validate_satellite_calibration(stage)
        if freeze:
            for path in stage.iterdir():
                path.chmod(0o444)
            stage.chmod(0o555)
        stage.replace(destination)
    except BaseException:
        if stage.exists() and not stage.is_symlink():
            stage.chmod(0o755)
            for path in stage.iterdir():
                if not path.is_symlink():
                    path.chmod(0o644)
            shutil.rmtree(stage)
        raise
    return manifest


def _read_records(path: Path, calibration_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise SatelliteCalibrationError(
                    f"calibration record line {line_number} is invalid JSON"
                ) from error
            if not isinstance(value, dict) or set(value) != set(ROW_FIELDS):
                raise SatelliteCalibrationError(
                    f"calibration record line {line_number} schema changed"
                )
            if _canonical_line(value) != line.encode("utf-8"):
                raise SatelliteCalibrationError(
                    f"calibration record line {line_number} is not canonical"
                )
            records.append(value)
    sample_size = _calibration_config(calibration_id)["scope"]["sample_size"]
    if len(records) != sample_size:
        raise SatelliteCalibrationError("calibration record count changed")
    queue_ids = [record["queue_id"] for record in records]
    if queue_ids != sorted(queue_ids) or len(set(queue_ids)) != len(queue_ids):
        raise SatelliteCalibrationError("calibration record ordering changed")
    for index, record in enumerate(records):
        if (
            record.get("schema_version") != SCHEMA_VERSION
            or record.get("decision") not in DECISION_OUTCOMES
            or record.get("outcome") != DECISION_OUTCOMES[record["decision"]]
            or not isinstance(record.get("queue_id"), str)
            or _QUEUE_RE.fullmatch(record["queue_id"]) is None
            or not isinstance(record.get("source_run"), str)
            or _RUN_RE.fullmatch(record["source_run"]) is None
        ):
            raise SatelliteCalibrationError(f"calibration record {index} identity changed")
        _validate_metrics(
            {name: record[name] for name in METRIC_NAMES},
            f"calibration record {index}",
        )
        for prefix in ("report", "review"):
            digest = record.get(f"{prefix}_sha256")
            size = record.get(f"{prefix}_bytes")
            path = record.get(f"{prefix}_path")
            if (
                not isinstance(digest, str)
                or _HASH_RE.fullmatch(digest) is None
                or not isinstance(size, int)
                or isinstance(size, bool)
                or size <= 0
                or not isinstance(path, str)
            ):
                raise SatelliteCalibrationError(
                    f"calibration record {index} {prefix} lineage changed"
                )
    return records


def validate_satellite_calibration(
    directory: str | Path, *, definition_path: str | Path | None = None
) -> dict[str, Any]:
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise SatelliteCalibrationError(
            "satellite-calibration bundle must be a regular directory"
        )
    entries = list(root.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise SatelliteCalibrationError(
            "satellite-calibration closed file set changed"
        )
    manifest, manifest_raw = _json_object(
        root / MANIFEST_FILENAME, "satellite-calibration manifest"
    )
    if manifest_raw != _canonical_json(manifest):
        raise SatelliteCalibrationError(
            "satellite-calibration manifest is not canonical"
        )
    if (root / MANIFEST_HASH_FILENAME).read_bytes() != (
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    ):
        raise SatelliteCalibrationError(
            "satellite-calibration manifest sidecar changed"
        )
    calibration_id = manifest.get("calibration_id")
    config = _calibration_config(calibration_id)
    if (
        set(manifest)
        != {
            "schema_version",
            "format",
            "calibration_id",
            "generated_at",
            "scope",
            "rules",
            "definition",
            "inputs",
            "counts",
            "outputs",
        }
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != FORMAT
        or manifest.get("scope") != config["scope"]
        or manifest.get("rules") != list(PREDECLARED_RULES)
    ):
        raise SatelliteCalibrationError(
            "satellite-calibration identity, rules, or safeguards changed"
        )
    _timestamp(
        manifest.get("generated_at"),
        "satellite-calibration generated_at",
        whole_seconds=True,
    )
    outputs = manifest.get("outputs")
    payload_names = BUNDLE_FILES - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    if not isinstance(outputs, Mapping) or set(outputs) != payload_names:
        raise SatelliteCalibrationError(
            "satellite-calibration output inventory changed"
        )
    for name, expected in outputs.items():
        if not isinstance(expected, Mapping):
            raise SatelliteCalibrationError(f"satellite-calibration output {name} changed")
        if _checkpoint(root / name) != {
            "bytes": expected.get("bytes"),
            "sha256": expected.get("sha256"),
        }:
            raise SatelliteCalibrationError(f"satellite-calibration output changed: {name}")

    records = _read_records(root / RECORDS_FILENAME, calibration_id)
    payloads, summary = _payloads(
        records,
        manifest["generated_at"],
        calibration_id,
    )
    if payloads != {name: (root / name).read_bytes() for name in payload_names}:
        raise SatelliteCalibrationError(
            "satellite-calibration payloads do not reconcile"
        )
    if manifest.get("counts") != summary["sample"]:
        raise SatelliteCalibrationError(
            "satellite-calibration counts do not reconcile"
        )
    sample_size = config["scope"]["sample_size"]
    if outputs[RECORDS_FILENAME].get("records") != sample_size or outputs[
        RECORDS_CSV_FILENAME
    ].get("records") != sample_size:
        raise SatelliteCalibrationError(
            "satellite-calibration output record counts changed"
        )
    for name in payload_names - {RECORDS_FILENAME, RECORDS_CSV_FILENAME}:
        if "records" in outputs[name]:
            raise SatelliteCalibrationError(
                f"satellite-calibration non-tabular record count changed: {name}"
            )

    inputs = manifest.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != {
        "candidate_fusion",
        "review_pairs",
    }:
        raise SatelliteCalibrationError("satellite-calibration input lineage changed")
    pairs = inputs.get("review_pairs")
    if not isinstance(pairs, list) or len(pairs) != sample_size:
        raise SatelliteCalibrationError("satellite-calibration input pair count changed")
    record_lineage = [
        {
            "queue_id": record["queue_id"],
            "source_run": record["source_run"],
            "report": {
                "path": record["report_path"],
                "bytes": record["report_bytes"],
                "sha256": record["report_sha256"],
            },
            "review": {
                "path": record["review_path"],
                "bytes": record["review_bytes"],
                "sha256": record["review_sha256"],
            },
        }
        for record in records
    ]
    if pairs != record_lineage:
        raise SatelliteCalibrationError(
            "satellite-calibration row and manifest lineage differ"
        )

    if definition_path is not None:
        definition, definition_raw, definition_file = _load_definition(definition_path)
        reproduced_records, reproduced_inputs = _load_inputs(definition, definition_file)
        reproduced_payloads, reproduced_summary = _payloads(
            reproduced_records,
            definition["generated_at"],
            definition["calibration_id"],
        )
        reproduced_manifest = _manifest(
            definition,
            definition_raw,
            definition_file,
            reproduced_inputs,
            reproduced_payloads,
            reproduced_summary,
        )
        if reproduced_payloads != {
            name: (root / name).read_bytes() for name in payload_names
        }:
            raise SatelliteCalibrationError(
                "satellite-calibration outputs do not reproduce"
            )
        if manifest != reproduced_manifest:
            raise SatelliteCalibrationError(
                "satellite-calibration manifest does not reproduce"
            )
    return manifest


__all__ = [
    "CALIBRATION_ID",
    "CALIBRATION_ID_V2",
    "CALIBRATION_ID_V3",
    "CALIBRATION_ID_V4",
    "PREDECLARED_RULES",
    "SCOPE_POLICY",
    "SCOPE_POLICY_V2",
    "SCOPE_POLICY_V3",
    "SCOPE_POLICY_V4",
    "SatelliteCalibrationError",
    "evaluate_rule",
    "validate_satellite_calibration",
    "write_satellite_calibration",
]
