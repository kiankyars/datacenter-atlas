"""Immutable analyst-review carrier for eleven explicit-v1 change jobs.

The carrier binds decisions fixed by a fresh context-isolated reviewer against
the frozen metadata-free preparation, then unseals only opaque queue lineage.
It does not interpret identities or create Atlas, status, construction,
capacity, power, energy, PUE, type, operator, workload, or site-count facts.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any, Mapping

from . import satellite_change_blind_preparation_explicit_v1 as preparation
from . import satellite_change_explicit_v1_disposition as disposition


class ExplicitV1AnalystReviewError(ValueError):
    """Raised when blind decisions, lineage, or publication drift."""


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REVIEW_ID = "2026-07-21-open-seed-v71-active-explicit-11-review-v1"
OUTPUT_PATH = PACKAGE_ROOT / "satellite_change_reviews" / REVIEW_ID
BLIND_REVIEW_DRAFT_PATH = (
    PACKAGE_ROOT
    / "sources/satellite-change-blind-review-2026-07-21-"
    "open-seed-v71-explicit-11-v1.json"
)
BLIND_REVIEW_DRAFT_BYTES = 6_118
BLIND_REVIEW_DRAFT_SHA256 = (
    "6316fc870dc174579706fdd91543a1768602cac1bacaff44c12e1b769004347a"
)
BLIND_REVIEW_DRAFT_ID = (
    "2026-07-21-open-seed-v71-active-explicit-11-blind-review-v1"
)
BLIND_REVIEW_DRAFT_RECORDED_AT = "2026-07-21T14:17:09.562317Z"
BLIND_REVIEW_DRAFT_BIRTHTIME = "2026-07-21T14:17:47.477039Z"
BLIND_REVIEW_ID = (
    "2026-07-21-open-seed-v71-active-explicit-11-blind-review-v2"
)
SOURCE_PREPARATION_MANIFEST_SHA256 = (
    "353dad8aee795cafc8ab4c80fe83ee05c8188f153f8aa792584b021bec38dbea"
)
SOURCE_PREPARATION_TREE_SHA256 = (
    "184927d0fb85b4aae762fc768a4b73f4131f061254fe4ea9f880e578d39c2502"
)
SOURCE_PREPARATION_FILES = 50
SOURCE_PREPARATION_BYTES = 17_648_838
SOURCE_RUN_PATH = disposition.CHANGE_RUN_PATH
SOURCE_RUN_MANIFEST_BYTES = 68_289
SOURCE_RUN_MANIFEST_SHA256 = disposition.CHANGE_MANIFEST_SHA256
SOURCE_RUN_TREE_SHA256 = disposition.CHANGE_TREE_SHA256
SOURCE_RUN_FILES = disposition.CHANGE_FILE_COUNT
SOURCE_RUN_BYTES = preparation.SOURCE_CHANGE_BYTES
SOURCE_ARTIFACT_NAMES = frozenset(
    {
        "after.png",
        "before.png",
        "change-overlay.png",
        "change-proposals.geojson",
        "comparison.png",
        "report.json",
    }
)
VISUAL_ARTIFACT_NAMES = frozenset(preparation.VISUAL_FILENAMES)
DECISION_SEMANTICS = {
    "rejected_for_site_promotion": (
        "reject imagery as a basis for site promotion"
    ),
    "retained_for_manual_followup": (
        "retain imagery for manual visible-change follow-up only"
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
    "operator_claim_created": False,
    "power_claim_created": False,
    "pue_claim_created": False,
    "site_count_claim_created": False,
    "unique_site_claim_created": False,
    "workload_claim_created": False,
}
EXPECTED_COUNTS = {
    "image_quality": {"partially_obscured": 4, "usable": 7},
    "promotion_dispositions": {
        "rejected_for_site_promotion": 4,
        "retained_for_manual_followup": 7,
    },
    "visible_change": {"ambiguous": 4, "clear": 7},
}
DEFINITION_FILENAME = "definition.json"
BLIND_DECISIONS_FILENAME = "blind-decisions.json"
REVIEWS_FILENAME = "analyst-reviews.jsonl"
SUMMARY_FILENAME = "summary.json"
README_FILENAME = "README.md"
ATTRIBUTION_FILENAME = "ATTRIBUTION.txt"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
BUILDER_PATH = Path(__file__).resolve()
ROOT_SHIM_PATH = PACKAGE_ROOT / "satellite_change_review_explicit_v1.py"
CLI_PATH = PACKAGE_ROOT / "scripts/build_satellite_change_review_explicit_v1.py"


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
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExplicitV1AnalystReviewError(f"{label} is not valid JSON") from error
    return value


def _exact_file(path: Path, size: int, digest: str, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ExplicitV1AnalystReviewError(
            f"{label} must be a regular non-symlink file"
        )
    raw = path.read_bytes()
    if len(raw) != size or _sha256(raw) != digest:
        raise ExplicitV1AnalystReviewError(f"{label} changed")
    return raw


def _file_record(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ExplicitV1AnalystReviewError(f"builder file missing: {path}")
    raw = path.read_bytes()
    return {
        "bytes": len(raw),
        "path": path.relative_to(PACKAGE_ROOT).as_posix(),
        "sha256": _sha256(raw),
    }


def _validate_blind_review() -> tuple[dict[str, Any], list[dict[str, Any]], bytes]:
    raw = _exact_file(
        BLIND_REVIEW_DRAFT_PATH,
        BLIND_REVIEW_DRAFT_BYTES,
        BLIND_REVIEW_DRAFT_SHA256,
        "blind review draft",
    )
    document = _strict_json(raw, "blind review source")
    if not isinstance(document, dict) or raw != _canonical_json(document):
        raise ExplicitV1AnalystReviewError("blind review draft is not canonical")
    if (
        document.get("artifact_type")
        != "analyst_identity_blind_satellite_change_review_input"
        or document.get("review_id") != BLIND_REVIEW_DRAFT_ID
        or document.get("recorded_at") != BLIND_REVIEW_DRAFT_RECORDED_AT
        or document.get("decision_semantics") != DECISION_SEMANTICS
        or document.get("guardrails") != GUARDRAILS
        or document.get("schema_version") != 1
    ):
        raise ExplicitV1AnalystReviewError("blind review draft identity changed")
    method = document.get("method")
    if method != {
        "fresh_context_without_parent_history": True,
        "identity_metadata_available_during_review": False,
        "lineage_unsealed_after_visual_judgments_were_fixed": True,
        "manifest_definition_or_review_units_available_during_review": False,
        "reviewer_received_only_neutral_image_paths": True,
        "visual_artifacts_inspected_per_unit": sorted(VISUAL_ARTIFACT_NAMES),
    }:
        raise ExplicitV1AnalystReviewError("blind review method changed")
    decisions = document.get("decisions")
    blind_ids = [
        f"{preparation.BLIND_ID_PREFIX}{index:03d}"
        for index in range(1, disposition.SELECTED_JOB_COUNT + 1)
    ]
    if (
        not isinstance(decisions, list)
        or len(decisions) != disposition.SELECTED_JOB_COUNT
        or [row.get("blind_id") for row in decisions] != blind_ids
    ):
        raise ExplicitV1AnalystReviewError("blind review decision inventory changed")
    for row in decisions:
        allowed = {
            "blind_id",
            "confidence",
            "disposition",
            "image_quality",
            "rationale",
            "visible_change",
            "visually_identical_to",
        }
        if (
            not set(row).issubset(allowed)
            or row.get("disposition") not in DECISION_SEMANTICS
            or row.get("image_quality") not in {"usable", "partially_obscured"}
            or row.get("visible_change") not in {"clear", "ambiguous"}
            or not isinstance(row.get("confidence"), (int, float))
            or not 0 <= row["confidence"] <= 1
            or not isinstance(row.get("rationale"), str)
            or not row["rationale"]
        ):
            raise ExplicitV1AnalystReviewError(
                f"blind decision changed: {row.get('blind_id')}"
            )
    identity_links = {
        (row["blind_id"], row["visually_identical_to"])
        for row in decisions
        if "visually_identical_to" in row
    }
    if identity_links != {("V71-X001", "V71-X003"), ("V71-X003", "V71-X001")}:
        raise ExplicitV1AnalystReviewError("visual identity links changed")
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
    if counts != EXPECTED_COUNTS or document.get("summary") != {
        "decisions": 11,
        **EXPECTED_COUNTS,
        "visual_identity_links": 2,
    }:
        raise ExplicitV1AnalystReviewError("blind decision accounting changed")
    return document, decisions, raw


def _validate_inputs() -> tuple[
    dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]
]:
    prep_manifest = preparation.validate_blind_preparation(preparation.OUTPUT_PATH)
    if (
        _sha256((preparation.OUTPUT_PATH / "manifest.json").read_bytes())
        != SOURCE_PREPARATION_MANIFEST_SHA256
        or prep_manifest["tree_inventory"]
        != {
            "directories": 13,
            "file_bytes": SOURCE_PREPARATION_BYTES,
            "files": SOURCE_PREPARATION_FILES,
            "inventory_sha256": SOURCE_PREPARATION_TREE_SHA256,
        }
    ):
        raise ExplicitV1AnalystReviewError("blind preparation changed")
    prep_definition = _strict_json(
        (preparation.OUTPUT_PATH / "definition.json").read_bytes(),
        "blind preparation definition",
    )
    source_raw = _exact_file(
        SOURCE_RUN_PATH / "batch-manifest.json",
        SOURCE_RUN_MANIFEST_BYTES,
        SOURCE_RUN_MANIFEST_SHA256,
        "source run manifest",
    )
    source = _strict_json(source_raw, "source run manifest")
    if disposition.tree_sha256(SOURCE_RUN_PATH) != (
        SOURCE_RUN_TREE_SHA256,
        SOURCE_RUN_FILES,
        SOURCE_RUN_BYTES,
    ):
        raise ExplicitV1AnalystReviewError("source run tree changed")
    blind_review, decisions, _ = _validate_blind_review()
    order = preparation._blind_order()
    if preparation._lineage_commitment(source, order) != prep_definition[
        "blinding"
    ]["lineage_commitment_sha256"]:
        raise ExplicitV1AnalystReviewError("sealed lineage commitment changed")
    source_jobs = source.get("jobs")
    if not isinstance(source_jobs, dict) or set(source_jobs) != set(
        disposition.SELECTED_QUEUE_IDS
    ):
        raise ExplicitV1AnalystReviewError("source job inventory changed")
    units = [
        _strict_json(line, "blind preparation unit")
        for line in (preparation.OUTPUT_PATH / preparation.UNITS_FILENAME)
        .read_bytes()
        .splitlines()
    ]
    if [row["blind_id"] for row in units] != [row["blind_id"] for row in decisions]:
        raise ExplicitV1AnalystReviewError("decision and preparation order changed")
    return source, decisions, blind_review, prep_definition


def _source_artifacts(
    source: Mapping[str, Any], queue_id: str
) -> dict[str, dict[str, Any]]:
    artifacts = source["jobs"][queue_id]["artifacts"]
    if set(artifacts) != SOURCE_ARTIFACT_NAMES:
        raise ExplicitV1AnalystReviewError(f"source artifact set changed: {queue_id}")
    result: dict[str, dict[str, Any]] = {}
    for name, spec in sorted(artifacts.items()):
        path = SOURCE_RUN_PATH / "jobs" / queue_id / "change" / name
        raw = _exact_file(path, spec["bytes"], spec["sha256"], f"{queue_id}/{name}")
        result[name] = {
            "bytes": len(raw),
            "path": path.relative_to(PACKAGE_ROOT).as_posix(),
            "sha256": _sha256(raw),
        }
    return result


def _readme() -> bytes:
    return (
        "# Identity-blind analyst review of eleven explicit-v1 comparisons\n\n"
        "This immutable bundle binds eleven visual decisions fixed by a fresh, "
        "context-isolated reviewer who received only neutral image paths. Opaque "
        "queue lineage was unsealed only after every quality flag, visible-change "
        "label, disposition, confidence, rationale, and visual-identity link was "
        "fixed. The exact decision source is hash-pinned.\n\n"
        "Seven comparisons are retained for manual visible-change follow-up only; "
        "four are rejected as a basis for site promotion. These are imagery triage "
        "dispositions, not identity, construction, lifecycle, current-status, type, "
        "capacity, power, energy, PUE, operator, workload, unique-site, or site-count "
        "facts. Nothing is promoted automatically and the Atlas is not mutated.\n\n"
        "The first decision-source draft is retained but excluded because its "
        "recorded-at value preceded the artifact bytes. The corrected decision "
        "member changes none of the eleven decisions and is time-gated with this "
        "bundle.\n"
    ).encode("utf-8")


def _attribution() -> bytes:
    return (
        "Contains modified Copernicus Sentinel data 2024 and 2026.\n"
        "Catalog: Element 84 Earth Search v1.\n"
        "Dataset: Copernicus Sentinel-2 Level-2A.\n"
        "Source imagery is not duplicated in this review bundle; all six upstream "
        "artifacts per job are bound by exact path, byte count, and SHA-256.\n"
    ).encode("utf-8")


def build_analyst_review(generated_at: str) -> dict[str, bytes]:
    """Build deterministic review bytes from fixed blind decisions and lineage."""

    generated_at, _ = preparation._timestamp(generated_at, "generated_at")
    source, decisions, blind_review, prep_definition = _validate_inputs()
    order = dict(preparation._blind_order())
    decision_rows_sha256 = _sha256(
        b"".join(_canonical_line(decision) for decision in decisions)
    )
    corrected_blind_review = {
        "artifact_type": (
            "analyst_identity_blind_satellite_change_review_input_temporal_correction"
        ),
        "decision_semantics": DECISION_SEMANTICS,
        "decisions": decisions,
        "draft": {
            "bytes": BLIND_REVIEW_DRAFT_BYTES,
            "disposition": "rejected_temporal_metadata_only",
            "path": BLIND_REVIEW_DRAFT_PATH.relative_to(PACKAGE_ROOT).as_posix(),
            "sha256": BLIND_REVIEW_DRAFT_SHA256,
        },
        "guardrails": GUARDRAILS,
        "method": blind_review["method"],
        "preparation": blind_review["preparation"],
        "recorded_at": generated_at,
        "review_id": BLIND_REVIEW_ID,
        "schema_version": 2,
        "summary": blind_review["summary"],
        "temporal_integrity": {
            "accepted_member_staged_before_recorded_at": True,
            "decision_content_changed": False,
            "decision_rows_sha256": decision_rows_sha256,
            "draft_birthtime": BLIND_REVIEW_DRAFT_BIRTHTIME,
            "draft_recorded_at": BLIND_REVIEW_DRAFT_RECORDED_AT,
            "draft_recorded_at_precedes_artifact_bytes": True,
            "draft_retained_unchanged": True,
            "final_root_ctime_must_not_precede_recorded_at": True,
        },
    }
    corrected_blind_raw = _canonical_json(corrected_blind_review)
    blind_source_spec = {
        "bytes": len(corrected_blind_raw),
        "path": (Path("satellite_change_reviews") / REVIEW_ID / BLIND_DECISIONS_FILENAME).as_posix(),
        "sha256": _sha256(corrected_blind_raw),
    }
    records: list[dict[str, Any]] = []
    for decision in decisions:
        blind_id = decision["blind_id"]
        queue_id = order[blind_id]
        record = {
            **decision,
            "decision_scope": "identity_blind_visible_change_triage_only",
            "input_artifacts": _source_artifacts(source, queue_id),
            "lineage_unsealed_after_visual_judgments_were_fixed": True,
            "queue_id": queue_id,
            "schema_version": 1,
            "source_blind_decision": blind_source_spec,
            "visual_artifacts_inspected": sorted(VISUAL_ARTIFACT_NAMES),
        }
        records.append(record)
    reviews_raw = b"".join(_canonical_line(record) for record in records)
    source_pins = {
        "accepted_disposition": {
            "bytes": 7_204,
            "files": 5,
            "manifest_bytes": 610,
            "manifest_sha256": preparation.SOURCE_DISPOSITION_MANIFEST_SHA256,
            "path": disposition.DISPOSITION_PATH.relative_to(PACKAGE_ROOT).as_posix(),
            "tree_sha256": preparation.SOURCE_DISPOSITION_TREE_SHA256,
        },
        "blind_decision_draft": {
            "bytes": BLIND_REVIEW_DRAFT_BYTES,
            "disposition": "rejected_temporal_metadata_only",
            "path": BLIND_REVIEW_DRAFT_PATH.relative_to(PACKAGE_ROOT).as_posix(),
            "sha256": BLIND_REVIEW_DRAFT_SHA256,
        },
        "blind_decisions": blind_source_spec,
        "blind_preparation": {
            "bytes": SOURCE_PREPARATION_BYTES,
            "files": SOURCE_PREPARATION_FILES,
            "generated_at": prep_definition["generated_at"],
            "manifest_bytes": 8_812,
            "manifest_sha256": SOURCE_PREPARATION_MANIFEST_SHA256,
            "path": preparation.OUTPUT_PATH.relative_to(PACKAGE_ROOT).as_posix(),
            "tree_sha256": SOURCE_PREPARATION_TREE_SHA256,
        },
        "change_run": {
            "bytes": SOURCE_RUN_BYTES,
            "files": SOURCE_RUN_FILES,
            "manifest_bytes": SOURCE_RUN_MANIFEST_BYTES,
            "manifest_sha256": SOURCE_RUN_MANIFEST_SHA256,
            "path": SOURCE_RUN_PATH.relative_to(PACKAGE_ROOT).as_posix(),
            "tree_sha256": SOURCE_RUN_TREE_SHA256,
        },
    }
    definition = {
        "builder": {
            "files": {
                "cli": _file_record(CLI_PATH),
                "module": _file_record(BUILDER_PATH),
                "root_shim": _file_record(ROOT_SHIM_PATH),
            }
        },
        "decision_semantics": DECISION_SEMANTICS,
        "format": "datacenter-atlas-explicit-v1-analyst-review-definition",
        "generated_at": generated_at,
        "guardrails": GUARDRAILS,
        "review_id": REVIEW_ID,
        "runtime": prep_definition["runtime"],
        "schema_version": 1,
        "sources": source_pins,
    }
    summary = {
        "counts": {
            "analyst_decisions": 11,
            "image_quality": EXPECTED_COUNTS["image_quality"],
            "promotion_dispositions": EXPECTED_COUNTS["promotion_dispositions"],
            "source_artifacts_hash_bound": 66,
            "temporal_metadata_corrections": 1,
            "visible_change": EXPECTED_COUNTS["visible_change"],
            "visual_artifacts_inspected": 44,
            "visual_identity_links": 2,
        },
        "decision_semantics": DECISION_SEMANTICS,
        "generated_at": generated_at,
        "guardrails": GUARDRAILS,
        "lineage_unsealed_after_visual_judgments_were_fixed": True,
        "review_id": REVIEW_ID,
        "schema_version": 1,
        "sources": source_pins,
    }
    output = {
        ATTRIBUTION_FILENAME: _attribution(),
        BLIND_DECISIONS_FILENAME: corrected_blind_raw,
        DEFINITION_FILENAME: _canonical_json(definition),
        README_FILENAME: _readme(),
        REVIEWS_FILENAME: reviews_raw,
        SUMMARY_FILENAME: _canonical_json(summary),
    }
    manifest = {
        "artifacts": {
            name: {"bytes": len(raw), "sha256": _sha256(raw)}
            for name, raw in sorted(output.items())
        },
        "decision_semantics": DECISION_SEMANTICS,
        "format": "datacenter-atlas-explicit-v1-identity-blind-analyst-review",
        "generated_at": generated_at,
        "guardrails": GUARDRAILS,
        "review_id": REVIEW_ID,
        "schema_version": 1,
        "sources": source_pins,
        "summary": summary["counts"],
    }
    manifest_raw = _canonical_json(manifest)
    output[MANIFEST_FILENAME] = manifest_raw
    output[MANIFEST_HASH_FILENAME] = (
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    )
    if blind_review["decisions"] != [
        {key: value for key, value in record.items() if key in blind_review["decisions"][index]}
        for index, record in enumerate(records)
    ]:
        raise ExplicitV1AnalystReviewError("blind decisions changed during binding")
    return output


def _write_file(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def publish_analyst_review(
    generated_at: str, output_path: Path = OUTPUT_PATH
) -> dict[str, Any]:
    """Stage, time-gate, and no-replace publish the frozen analyst review."""

    canonical_time, target = preparation._timestamp(generated_at, "generated_at")
    destination = output_path.resolve()
    if destination != OUTPUT_PATH.resolve():
        raise ExplicitV1AnalystReviewError("review output path changed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / f".{destination.name}.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise ExplicitV1AnalystReviewError(f"active output lock: {lock}") from error
    stage: Path | None = None
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        if destination.exists() or destination.is_symlink():
            raise ExplicitV1AnalystReviewError(f"refusing existing output: {destination}")
        stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
        files = build_analyst_review(canonical_time)
        for name, raw in sorted(files.items()):
            _write_file(stage / name, raw)
        newest = max(
            max(item.stat().st_mtime, getattr(item.stat(), "st_birthtime", 0.0))
            for item in [stage, *stage.rglob("*")]
        )
        if newest > target.timestamp() + 1e-6:
            raise ExplicitV1AnalystReviewError("staged review bytes postdate generated_at")
        preparation._freeze_tree(stage)
        while datetime.now(UTC) < target:
            remaining = (target - datetime.now(UTC)).total_seconds()
            time.sleep(min(max(remaining, 0.0), 0.25))
        preparation._promote_noreplace(stage, destination)
        stage = None
        if destination.stat().st_ctime + 1e-6 < target.timestamp():
            raise ExplicitV1AnalystReviewError("review root ctime precedes generated_at")
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
    """Offline-reproduce the frozen review byte-for-byte."""

    destination = output_path.resolve()
    if destination != OUTPUT_PATH.resolve():
        raise ExplicitV1AnalystReviewError("review output path changed")
    inventory = preparation._tree_inventory(destination)
    definition = _strict_json(
        (destination / DEFINITION_FILENAME).read_bytes(), "review definition"
    )
    generated_at, target = preparation._timestamp(
        definition.get("generated_at"), "generated_at"
    )
    if destination.stat().st_ctime + 1e-6 < target.timestamp():
        raise ExplicitV1AnalystReviewError("review root ctime precedes generated_at")
    actual = {
        path.name: path.read_bytes()
        for path in destination.iterdir()
        if path.is_file()
    }
    expected = build_analyst_review(generated_at)
    if actual != expected:
        raise ExplicitV1AnalystReviewError("review differs from offline reconstruction")
    manifest_raw = actual[MANIFEST_FILENAME]
    if actual[MANIFEST_HASH_FILENAME] != (
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    ):
        raise ExplicitV1AnalystReviewError("review manifest sidecar changed")
    manifest = _strict_json(manifest_raw, "review manifest")
    return {**manifest, "tree_inventory": inventory}
