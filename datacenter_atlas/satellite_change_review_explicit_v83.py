"""Immutable combined review carrier for the exact 68-job v83 preparation.

The carrier validates two identity-blind reviewer inputs before unsealing the
preparation's committed queue and source-entity lineage.  It distinguishes 68
decision rows from 65 unique exact four-image evidence sets.  Retention means
manual visible-change follow-up only and creates no Atlas or physical claim.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Mapping

from . import satellite_change_blind_preparation_explicit_v83 as preparation


class ExplicitV83AnalystReviewError(ValueError):
    """Raised when review inputs, lineage, accounting, or publication drift."""


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REVIEW_ID = (
    "2026-07-21-open-seed-v83-active-unreviewed-single-68-review-v1"
)
BLIND_REVIEW_ID = (
    "2026-07-21-open-seed-v83-explicit-68-combined-blind-review-v1"
)
OUTPUT_PATH = PACKAGE_ROOT / "satellite_change_reviews" / REVIEW_ID

PART_A_PATH = (
    PACKAGE_ROOT
    / "sources/satellite-change-blind-review-2026-07-21-"
    "open-seed-v83-explicit-68-part-a-v1.json"
)
PART_A_BYTES = 14_135
PART_A_SHA256 = (
    "2c752d82b541f2793bb02a4a4a3d916b6131f500f06452ae52721f70279bc396"
)
PART_A_REVIEW_ID = (
    "2026-07-21-open-seed-v83-explicit-68-part-a-blind-review-v1"
)
PART_A_RECORDED_AT = "2026-07-21T23:59:34Z"
PART_A_BIRTHTIME = "2026-07-22T00:02:00Z"

PART_B_PATH = (
    PACKAGE_ROOT
    / "sources/satellite-change-blind-review-2026-07-21-"
    "open-seed-v83-explicit-68-part-b-v1.json"
)
PART_B_BYTES = 13_230
PART_B_SHA256 = (
    "ae62a835bef166687bbc81653bf8c57bf55dd58d98801a3ced938512d315a11f"
)
PART_B_REVIEW_ID = (
    "2026-07-21-open-seed-v83-explicit-68-part-b-blind-review-v1"
)
PART_B_RECORDED_AT = "2026-07-22T00:14:00Z"
PART_B_BIRTHTIME = "2026-07-22T00:11:56Z"

SOURCE_PREPARATION_MANIFEST_BYTES = 44_116
SOURCE_PREPARATION_MANIFEST_SHA256 = (
    "c32618fe31eaa753cea9e75a04feac3c575deba6aa22ea84c0184840b6e57c7f"
)
SOURCE_PREPARATION_DEFINITION_BYTES = 4_041
SOURCE_PREPARATION_DEFINITION_SHA256 = (
    "1c09b9ba365f61241e7f86d5729fa7b347391ae96b1685d29952cb26752bd4ea"
)
SOURCE_PREPARATION_UNITS_BYTES = 45_200
SOURCE_PREPARATION_UNITS_SHA256 = (
    "7436f689999605beea6f0d3c88dc1bfa70471d57b9de0a3c671c8dda4b2a5a29"
)
SOURCE_PREPARATION_TREE = {
    "directories": 70,
    "file_bytes": 97_829_252,
    "files": 278,
    "inventory_sha256": (
        "732441572720e833823a655ad3e2658535e2be3a76f94e23332afbeeb05b3e90"
    ),
}
SOURCE_LINEAGE_COMMITMENT_SHA256 = (
    "441a2d6f2acce7a5a2348991da88878463cf53f41d1316304c1a2b8df08e9cc0"
)
SOURCE_RUN_PATH = preparation.SOURCE_RUN_PATH
SOURCE_RUN_MANIFEST_BYTES = preparation.SOURCE_RUN_MANIFEST_BYTES
SOURCE_RUN_MANIFEST_SHA256 = preparation.SOURCE_RUN_MANIFEST_SHA256
SOURCE_RUN_TREE = preparation.SOURCE_RUN_TREE
SOURCE_SELECTION_SHA256 = preparation.SOURCE_SELECTION_SHA256
SOURCE_ARTIFACT_NAMES = frozenset(preparation.SOURCE_ARTIFACT_FILENAMES)
VISUAL_ARTIFACT_NAMES = tuple(preparation.VISUAL_FILENAMES)

DECISION_SEMANTICS = {
    "rejected_for_site_promotion": (
        "reject imagery as a basis for site promotion"
    ),
    "retained_for_manual_followup": (
        "retain imagery for manual visible-change follow-up only"
    ),
}
SOURCE_GUARDRAILS = {
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
GUARDRAILS = {
    **SOURCE_GUARDRAILS,
    "exact_duplicate_visual_sets_counted_as_independent_confirmations": False,
    "reviewer_similarity_flag_used_for_exact_deduplication": False,
    "satellite_confirmation_claim_created": False,
}
SOURCE_METHOD = {
    "all_visual_artifacts_inspected_for_every_unit": True,
    "capacity_metadata_available_during_review": False,
    "fresh_context_without_parent_history": True,
    "identity_metadata_available_during_review": False,
    "lineage_metadata_available_during_review": False,
    "lineage_unsealed_after_visual_judgments_were_fixed": False,
    "manifest_definition_or_review_units_available_during_review": False,
    "mapping_metadata_available_during_review": False,
    "queue_metadata_available_during_review": False,
    "reviewer_received_only_neutral_image_paths": True,
    "site_metadata_available_during_review": False,
    "status_metadata_available_during_review": False,
    "visual_artifacts_inspected_per_unit": list(VISUAL_ARTIFACT_NAMES),
}
EXPECTED_ROW_COUNTS = {
    "image_quality": {
        "partially_obscured": 22,
        "unusable": 8,
        "usable": 38,
    },
    "promotion_dispositions": {
        "rejected_for_site_promotion": 21,
        "retained_for_manual_followup": 47,
    },
    "visible_change": {"ambiguous": 10, "clear": 47, "none": 11},
}
EXPECTED_UNIQUE_EXACT_COUNTS = {
    "image_quality": {
        "partially_obscured": 22,
        "unusable": 8,
        "usable": 35,
    },
    "promotion_dispositions": {
        "rejected_for_site_promotion": 21,
        "retained_for_manual_followup": 44,
    },
    "visible_change": {"ambiguous": 10, "clear": 44, "none": 11},
}
EXPECTED_EXACT_VISUAL_GROUPS = {
    "116499270c5d52dec49a674211b1f594b1c6a035c984bb1db0f977ef4cfce66c": (
        "V83-X008",
        "V83-X041",
    ),
    "c7a84ad205d2a3858dfe2cd61cc135993c44cdf672bb78dca30f16b91a2a03bc": (
        "V83-X021",
        "V83-X027",
    ),
    "61e1b3118ccdf8f6d2ebaed215e1ad4c9870d75554a78852ee2241bd8c1bc91f": (
        "V83-X025",
        "V83-X053",
    ),
}
EXPECTED_REVIEWER_LINKS = {
    ("V83-X027", "V83-X021"),
    ("V83-X052", "V83-X041"),
}
EXPECTED_APPROXIMATE_LINK = ("V83-X052", "V83-X041")

DEFINITION_FILENAME = "definition.json"
BLIND_DECISIONS_FILENAME = "blind-decisions.json"
PART_A_FILENAME = "blind-review-part-a.json"
PART_B_FILENAME = "blind-review-part-b.json"
REVIEWS_FILENAME = "analyst-reviews.jsonl"
SUMMARY_FILENAME = "summary.json"
README_FILENAME = "README.md"
ATTRIBUTION_FILENAME = "ATTRIBUTION.txt"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
BUILDER_PATH = Path(__file__).resolve()
ROOT_SHIM_PATH = PACKAGE_ROOT / "satellite_change_review_explicit_v83.py"
CLI_PATH = PACKAGE_ROOT / "scripts/build_satellite_change_review_explicit_v83.py"


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
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ExplicitV83AnalystReviewError(f"{label} is not UTF-8") from error

    def reject_constant(value: str) -> None:
        raise ExplicitV83AnalystReviewError(
            f"{label} contains non-finite number {value}"
        )

    try:
        return json.loads(text, parse_constant=reject_constant)
    except json.JSONDecodeError as error:
        raise ExplicitV83AnalystReviewError(
            f"{label} is not valid JSON"
        ) from error


def _exact_file(path: Path, size: int, digest: str, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ExplicitV83AnalystReviewError(
            f"{label} must be a regular non-symlink file"
        )
    raw = path.read_bytes()
    if len(raw) != size or _sha256(raw) != digest:
        raise ExplicitV83AnalystReviewError(f"{label} changed")
    return raw


def _file_record(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ExplicitV83AnalystReviewError(f"builder file missing: {path}")
    raw = path.read_bytes()
    return {
        "bytes": len(raw),
        "path": path.relative_to(PACKAGE_ROOT).as_posix(),
        "sha256": _sha256(raw),
    }


def _counts(decisions: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    return {
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


def _validate_review_part(
    *,
    path: Path,
    size: int,
    digest: str,
    review_id: str,
    recorded_at: str,
    label: str,
    start: int,
    end: int,
    expected_counts: dict[str, dict[str, int]],
    expected_links: set[tuple[str, str]],
) -> tuple[dict[str, Any], list[dict[str, Any]], bytes]:
    raw = _exact_file(path, size, digest, f"review part {label}")
    document = _strict_json(raw, f"review part {label}")
    if not isinstance(document, dict) or raw != _canonical_json(document):
        raise ExplicitV83AnalystReviewError(
            f"review part {label} is not canonical"
        )
    expected_ids = [
        f"{preparation.BLIND_ID_PREFIX}{index:03d}"
        for index in range(start, end + 1)
    ]
    if (
        document.get("artifact_type")
        != "analyst_identity_blind_satellite_change_review_input"
        or document.get("decision_semantics") != DECISION_SEMANTICS
        or document.get("guardrails") != SOURCE_GUARDRAILS
        or document.get("method") != SOURCE_METHOD
        or document.get("part")
        != {
            "blind_id_end": expected_ids[-1],
            "blind_id_start": expected_ids[0],
            "count": len(expected_ids),
            "label": label,
        }
        or document.get("recorded_at") != recorded_at
        or document.get("review_id") != review_id
        or document.get("schema_version") != 1
    ):
        raise ExplicitV83AnalystReviewError(
            f"review part {label} identity or method changed"
        )
    decisions = document.get("decisions")
    if (
        not isinstance(decisions, list)
        or [row.get("blind_id") for row in decisions] != expected_ids
    ):
        raise ExplicitV83AnalystReviewError(
            f"review part {label} decision inventory changed"
        )
    allowed = {
        "blind_id",
        "confidence",
        "disposition",
        "image_quality",
        "rationale",
        "visible_change",
        "visually_identical_to",
    }
    for row in decisions:
        confidence = row.get("confidence")
        visible_change = row.get("visible_change")
        expected_disposition = (
            "retained_for_manual_followup"
            if visible_change == "clear"
            else "rejected_for_site_promotion"
        )
        if (
            not isinstance(row, dict)
            or not set(row).issubset(allowed)
            or isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 1
            or row.get("disposition") != expected_disposition
            or row.get("image_quality")
            not in {"usable", "partially_obscured", "unusable"}
            or visible_change not in {"clear", "ambiguous", "none"}
            or not isinstance(row.get("rationale"), str)
            or not row["rationale"]
        ):
            raise ExplicitV83AnalystReviewError(
                f"review decision changed: {row.get('blind_id')}"
            )
        if "visually_identical_to" in row and not isinstance(
            row["visually_identical_to"], str
        ):
            raise ExplicitV83AnalystReviewError(
                f"review similarity flag changed: {row['blind_id']}"
            )
    links = {
        (row["blind_id"], row["visually_identical_to"])
        for row in decisions
        if "visually_identical_to" in row
    }
    counts = _counts(decisions)
    if links != expected_links or counts != expected_counts:
        raise ExplicitV83AnalystReviewError(
            f"review part {label} accounting changed"
        )
    if document.get("summary") != {
        "decisions": len(expected_ids),
        **expected_counts,
        "visual_identity_links": len(expected_links),
    }:
        raise ExplicitV83AnalystReviewError(
            f"review part {label} summary changed"
        )
    return document, decisions, raw


def _review_artifacts(
    unit: Mapping[str, Any], prep_manifest: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    blind_id = unit["blind_id"]
    views = unit.get("views")
    if not isinstance(views, dict) or set(views) != set(VISUAL_ARTIFACT_NAMES):
        raise ExplicitV83AnalystReviewError(
            f"review artifact inventory changed: {blind_id}"
        )
    result: dict[str, dict[str, Any]] = {}
    for name in VISUAL_ARTIFACT_NAMES:
        spec = views[name]
        expected_path = f"images/{blind_id}/{name}"
        if spec.get("path") != expected_path:
            raise ExplicitV83AnalystReviewError(
                f"review artifact path changed: {blind_id}/{name}"
            )
        raw = _exact_file(
            preparation.OUTPUT_PATH / expected_path,
            spec["bytes"],
            spec["sha256"],
            f"review artifact {blind_id}/{name}",
        )
        if prep_manifest["artifacts"].get(expected_path) != {
            "bytes": len(raw),
            "sha256": _sha256(raw),
        }:
            raise ExplicitV83AnalystReviewError(
                f"preparation manifest binding changed: {blind_id}/{name}"
            )
        result[name] = {
            "bytes": len(raw),
            "path": (
                preparation.OUTPUT_PATH.relative_to(PACKAGE_ROOT) / expected_path
            ).as_posix(),
            "sha256": _sha256(raw),
        }
    return result


def _source_artifacts(
    source: Mapping[str, Any], queue_id: str
) -> dict[str, dict[str, Any]]:
    artifacts = source["jobs"][queue_id].get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != SOURCE_ARTIFACT_NAMES:
        raise ExplicitV83AnalystReviewError(
            f"source artifact inventory changed: {queue_id}"
        )
    result: dict[str, dict[str, Any]] = {}
    for name, spec in sorted(artifacts.items()):
        path = SOURCE_RUN_PATH / "jobs" / queue_id / "change" / name
        raw = _exact_file(
            path, spec["bytes"], spec["sha256"], f"source {queue_id}/{name}"
        )
        result[name] = {
            "bytes": len(raw),
            "path": path.relative_to(PACKAGE_ROOT).as_posix(),
            "sha256": _sha256(raw),
        }
    return result


def _visual_set_sha256(review_artifacts: Mapping[str, Mapping[str, Any]]) -> str:
    evidence = {
        name: {
            "bytes": review_artifacts[name]["bytes"],
            "sha256": review_artifacts[name]["sha256"],
        }
        for name in sorted(review_artifacts)
    }
    return _sha256(_canonical_line(evidence))


def _validate_inputs() -> dict[str, Any]:
    if preparation._tree_inventory(preparation.OUTPUT_PATH) != (
        SOURCE_PREPARATION_TREE
    ):
        raise ExplicitV83AnalystReviewError("blind preparation tree changed")
    prep_definition_raw = _exact_file(
        preparation.OUTPUT_PATH / preparation.DEFINITION_FILENAME,
        SOURCE_PREPARATION_DEFINITION_BYTES,
        SOURCE_PREPARATION_DEFINITION_SHA256,
        "blind preparation definition",
    )
    prep_manifest_raw = _exact_file(
        preparation.OUTPUT_PATH / preparation.MANIFEST_FILENAME,
        SOURCE_PREPARATION_MANIFEST_BYTES,
        SOURCE_PREPARATION_MANIFEST_SHA256,
        "blind preparation manifest",
    )
    units_raw = _exact_file(
        preparation.OUTPUT_PATH / preparation.UNITS_FILENAME,
        SOURCE_PREPARATION_UNITS_BYTES,
        SOURCE_PREPARATION_UNITS_SHA256,
        "blind preparation review units",
    )
    prep_definition = _strict_json(
        prep_definition_raw, "blind preparation definition"
    )
    prep_manifest = _strict_json(prep_manifest_raw, "blind preparation manifest")
    expected_membership = {
        "accepted_change_run_selected_jobs": 68,
        "accepted_preparation_unreviewed_single_tile_ready_jobs": 68,
        "exact_set_equality": True,
        "selected_queue_ids_sha256": SOURCE_SELECTION_SHA256,
    }
    if (
        prep_definition.get("membership_proof") != expected_membership
        or prep_manifest.get("membership_proof") != expected_membership
        or prep_definition.get("blinding", {}).get(
            "lineage_commitment_sha256"
        )
        != SOURCE_LINEAGE_COMMITMENT_SHA256
        or prep_definition.get("blinding", {}).get("order_algorithm")
        != preparation.ORDER_ALGORITHM
        or prep_definition.get("blinding", {}).get("order_salt_sha256")
        != _sha256(preparation.ORDER_SALT.encode("utf-8"))
    ):
        raise ExplicitV83AnalystReviewError(
            "blind preparation membership or commitment changed"
        )

    if preparation._tree_inventory(SOURCE_RUN_PATH) != SOURCE_RUN_TREE:
        raise ExplicitV83AnalystReviewError("source run tree changed")
    source_raw = _exact_file(
        SOURCE_RUN_PATH / "batch-manifest.json",
        SOURCE_RUN_MANIFEST_BYTES,
        SOURCE_RUN_MANIFEST_SHA256,
        "source run manifest",
    )
    source = _strict_json(source_raw, "source run manifest")
    selection = source.get("selection")
    if not isinstance(selection, dict):
        raise ExplicitV83AnalystReviewError("source selection missing")
    selected = tuple(selection.get("selected_queue_ids", ()))
    if (
        source.get("state") != "completed"
        or source.get("summary") != preparation.SOURCE_RUN_SUMMARY
        or selection.get("mode") != "explicit_inclusion"
        or selection.get("exclude_queue_ids") != []
        or tuple(selection.get("include_queue_ids", ())) != selected
        or len(selected) != 68
        or len(set(selected)) != 68
        or set(source.get("jobs", {})) != set(selected)
        or _sha256(_canonical_json(sorted(selected))) != SOURCE_SELECTION_SHA256
    ):
        raise ExplicitV83AnalystReviewError("source run exact selection changed")

    part_a_counts = {
        "image_quality": {
            "partially_obscured": 11,
            "unusable": 4,
            "usable": 19,
        },
        "promotion_dispositions": {
            "rejected_for_site_promotion": 12,
            "retained_for_manual_followup": 22,
        },
        "visible_change": {"ambiguous": 9, "clear": 22, "none": 3},
    }
    part_b_counts = {
        "image_quality": {
            "partially_obscured": 11,
            "unusable": 4,
            "usable": 19,
        },
        "promotion_dispositions": {
            "rejected_for_site_promotion": 9,
            "retained_for_manual_followup": 25,
        },
        "visible_change": {"ambiguous": 1, "clear": 25, "none": 8},
    }
    part_a, decisions_a, raw_a = _validate_review_part(
        path=PART_A_PATH,
        size=PART_A_BYTES,
        digest=PART_A_SHA256,
        review_id=PART_A_REVIEW_ID,
        recorded_at=PART_A_RECORDED_AT,
        label="A",
        start=1,
        end=34,
        expected_counts=part_a_counts,
        expected_links={("V83-X027", "V83-X021")},
    )
    part_b, decisions_b, raw_b = _validate_review_part(
        path=PART_B_PATH,
        size=PART_B_BYTES,
        digest=PART_B_SHA256,
        review_id=PART_B_REVIEW_ID,
        recorded_at=PART_B_RECORDED_AT,
        label="B",
        start=35,
        end=68,
        expected_counts=part_b_counts,
        expected_links={EXPECTED_APPROXIMATE_LINK},
    )
    decisions = [*decisions_a, *decisions_b]
    if _counts(decisions) != EXPECTED_ROW_COUNTS:
        raise ExplicitV83AnalystReviewError("combined decision counts changed")

    units: list[dict[str, Any]] = []
    for index, line in enumerate(units_raw.splitlines(), 1):
        value = _strict_json(line, f"review unit line {index}")
        if not isinstance(value, dict):
            raise ExplicitV83AnalystReviewError(
                f"review unit line {index} is not an object"
            )
        units.append(value)
    order = preparation._blind_order(selected)
    expected_ids = [row["blind_id"] for row in decisions]
    if (
        len(units) != 68
        or [row.get("blind_id") for row in units] != expected_ids
        or [blind_id for blind_id, _queue_id in order] != expected_ids
        or preparation._lineage_commitment(source, order)
        != SOURCE_LINEAGE_COMMITMENT_SHA256
    ):
        raise ExplicitV83AnalystReviewError(
            "decision order or committed lineage changed"
        )

    review_artifacts: dict[str, dict[str, dict[str, Any]]] = {}
    fingerprints: dict[str, str] = {}
    grouped: dict[str, list[str]] = defaultdict(list)
    for unit in units:
        blind_id = unit["blind_id"]
        artifacts = _review_artifacts(unit, prep_manifest)
        fingerprint = _visual_set_sha256(artifacts)
        review_artifacts[blind_id] = artifacts
        fingerprints[blind_id] = fingerprint
        grouped[fingerprint].append(blind_id)
    exact_groups = {
        fingerprint: tuple(blind_ids)
        for fingerprint, blind_ids in sorted(grouped.items())
        if len(blind_ids) > 1
    }
    if exact_groups != EXPECTED_EXACT_VISUAL_GROUPS or len(grouped) != 65:
        raise ExplicitV83AnalystReviewError(
            "exact visual-evidence duplicate accounting changed"
        )
    by_id = {row["blind_id"]: row for row in decisions}
    for members in exact_groups.values():
        categorical = {
            (
                by_id[blind_id]["image_quality"],
                by_id[blind_id]["visible_change"],
                by_id[blind_id]["disposition"],
            )
            for blind_id in members
        }
        if len(categorical) != 1:
            raise ExplicitV83AnalystReviewError(
                f"exact duplicate decisions conflict: {members}"
            )
    reviewer_links = {
        (row["blind_id"], row["visually_identical_to"])
        for row in decisions
        if "visually_identical_to" in row
    }
    if (
        reviewer_links != EXPECTED_REVIEWER_LINKS
        or fingerprints[EXPECTED_APPROXIMATE_LINK[0]]
        == fingerprints[EXPECTED_APPROXIMATE_LINK[1]]
    ):
        raise ExplicitV83AnalystReviewError(
            "reviewer similarity and exact-hash distinction changed"
        )

    representatives = [blind_ids[0] for blind_ids in grouped.values()]
    unique_decisions = [by_id[blind_id] for blind_id in representatives]
    if _counts(unique_decisions) != EXPECTED_UNIQUE_EXACT_COUNTS:
        raise ExplicitV83AnalystReviewError(
            "unique exact visual-evidence counts changed"
        )
    for _blind_id, queue_id in order:
        entity = source["jobs"][queue_id].get("entity")
        if (
            not isinstance(entity, dict)
            or set(entity) != {"id", "name"}
            or not all(isinstance(entity[key], str) and entity[key] for key in entity)
        ):
            raise ExplicitV83AnalystReviewError(
                f"source entity lineage changed: {queue_id}"
            )
    return {
        "decisions": decisions,
        "exact_groups": exact_groups,
        "fingerprints": fingerprints,
        "grouped": {key: tuple(value) for key, value in grouped.items()},
        "order": order,
        "part_a": part_a,
        "part_b": part_b,
        "prep_definition": prep_definition,
        "prep_manifest": prep_manifest,
        "raw_a": raw_a,
        "raw_b": raw_b,
        "review_artifacts": review_artifacts,
        "source": source,
    }


def _part_source_spec(
    *,
    path: Path,
    member: str,
    raw: bytes,
    review_id: str,
    recorded_at: str,
    birthtime: str,
    temporal_status: str,
) -> dict[str, Any]:
    return {
        "artifact_birthtime": birthtime,
        "bytes": len(raw),
        "bundle_member": member,
        "path": path.relative_to(PACKAGE_ROOT).as_posix(),
        "recorded_at": recorded_at,
        "review_id": review_id,
        "sha256": _sha256(raw),
        "temporal_status": temporal_status,
    }


def _readme() -> bytes:
    return (
        "# Combined identity-blind review of 68 v83 comparisons\n\n"
        "This immutable carrier preserves two reviewer inputs and all 68 decisions "
        "unchanged, then unseals only the exact committed queue and source-entity "
        "lineage. Forty-seven rows are retained for manual visible-change follow-up "
        "and twenty-one are rejected as a basis for site promotion.\n\n"
        "Exact hashes of all four visual members identify 65 unique evidence sets. "
        "The three exact duplicate pairs are counted once each, reducing 47 retained "
        "rows to 44 unique retained evidence sets. The reviewer-reported X052 to X041 "
        "relationship is approximate visual similarity only: their four-image hashes "
        "differ, so both remain separate evidence sets and decisions. Exact duplicates "
        "are not independent satellite confirmations.\n\n"
        "Part A's recorded time precedes its filesystem birth time; the source remains "
        "unchanged and explicitly incident-marked, while this combined member is "
        "published under a later time gate. No Atlas mutation or identity, status, "
        "operator, type, capacity, power, energy, PUE, workload, site-count, or current-"
        "status claim is created.\n"
    ).encode("utf-8")


def _attribution() -> bytes:
    return (
        "Contains modified Copernicus Sentinel data 2024 and 2026.\n"
        "Catalog: Element 84 Earth Search v1.\n"
        "Dataset: Copernicus Sentinel-2 Level-2A.\n"
        "Source imagery is not duplicated in this review bundle; every upstream "
        "artifact and every frozen reviewer-facing visual is bound by exact path, "
        "byte count, and SHA-256.\n"
    ).encode("utf-8")


def build_analyst_review(generated_at: str) -> dict[str, bytes]:
    """Build deterministic combined carrier bytes from the two fixed inputs."""

    generated_at, _ = preparation._timestamp(generated_at, "generated_at")
    inputs = _validate_inputs()
    decisions: list[dict[str, Any]] = inputs["decisions"]
    decision_rows_sha256 = _sha256(
        b"".join(_canonical_line(decision) for decision in decisions)
    )
    part_a_spec = _part_source_spec(
        path=PART_A_PATH,
        member=PART_A_FILENAME,
        raw=inputs["raw_a"],
        review_id=PART_A_REVIEW_ID,
        recorded_at=PART_A_RECORDED_AT,
        birthtime=PART_A_BIRTHTIME,
        temporal_status="recorded_at_precedes_artifact_birthtime",
    )
    part_b_spec = _part_source_spec(
        path=PART_B_PATH,
        member=PART_B_FILENAME,
        raw=inputs["raw_b"],
        review_id=PART_B_REVIEW_ID,
        recorded_at=PART_B_RECORDED_AT,
        birthtime=PART_B_BIRTHTIME,
        temporal_status="artifact_birthtime_precedes_recorded_at",
    )
    exact_groups = [
        {"blind_ids": list(members), "visual_evidence_set_sha256": digest}
        for digest, members in sorted(
            inputs["exact_groups"].items(), key=lambda item: item[1]
        )
    ]
    reviewer_flags = []
    for source_id, target_id in sorted(EXPECTED_REVIEWER_LINKS):
        exact = inputs["fingerprints"][source_id] == inputs["fingerprints"][target_id]
        reviewer_flags.append(
            {
                "counted_as_exact_duplicate": exact,
                "exact_four_image_hash_match": exact,
                "reported_by": source_id,
                "reported_target": target_id,
                "type": (
                    "reviewer_reported_exact_visual_duplicate"
                    if exact
                    else "reviewer_reported_approximate_visual_similarity"
                ),
            }
        )
    combined = {
        "artifact_type": (
            "analyst_identity_blind_satellite_change_review_combined_carrier"
        ),
        "decision_rows_sha256": decision_rows_sha256,
        "decision_semantics": DECISION_SEMANTICS,
        "decisions": decisions,
        "duplicate_accounting": {
            "exact_four_image_hash_groups": exact_groups,
            "exact_groups_counted_once": True,
            "exact_visual_evidence_sets": 65,
            "reviewer_similarity_flags": reviewer_flags,
            "reviewer_similarity_without_exact_hash_does_not_deduplicate": True,
        },
        "guardrails": GUARDRAILS,
        "method": {
            **SOURCE_METHOD,
            "lineage_unsealed_after_visual_judgments_were_fixed": True,
        },
        "recorded_at": generated_at,
        "review_id": BLIND_REVIEW_ID,
        "reviewer_inputs": {"part_a": part_a_spec, "part_b": part_b_spec},
        "schema_version": 2,
        "summary": {
            "decision_rows": {"total": 68, **EXPECTED_ROW_COUNTS},
            "unique_exact_visual_evidence_sets": {
                "total": 65,
                **EXPECTED_UNIQUE_EXACT_COUNTS,
            },
        },
        "temporal_integrity": {
            "combined_member_staged_before_recorded_at": True,
            "decision_content_changed": False,
            "part_a_recorded_at_precedes_artifact_birthtime": True,
            "part_a_retained_unchanged": True,
            "part_b_artifact_birthtime_precedes_recorded_at": True,
            "part_b_retained_unchanged": True,
            "published_root_ctime_must_not_precede_recorded_at": True,
        },
    }
    combined_raw = _canonical_json(combined)
    combined_spec = {
        "bytes": len(combined_raw),
        "path": (Path("satellite_change_reviews") / REVIEW_ID / BLIND_DECISIONS_FILENAME).as_posix(),
        "sha256": _sha256(combined_raw),
    }

    source_pins = {
        "blind_preparation": {
            "bytes": SOURCE_PREPARATION_TREE["file_bytes"],
            "files": SOURCE_PREPARATION_TREE["files"],
            "generated_at": inputs["prep_definition"]["generated_at"],
            "lineage_commitment_sha256": SOURCE_LINEAGE_COMMITMENT_SHA256,
            "manifest_bytes": SOURCE_PREPARATION_MANIFEST_BYTES,
            "manifest_sha256": SOURCE_PREPARATION_MANIFEST_SHA256,
            "membership_proof": inputs["prep_definition"]["membership_proof"],
            "path": preparation.OUTPUT_PATH.relative_to(PACKAGE_ROOT).as_posix(),
            "review_units_bytes": SOURCE_PREPARATION_UNITS_BYTES,
            "review_units_sha256": SOURCE_PREPARATION_UNITS_SHA256,
            "tree_sha256": SOURCE_PREPARATION_TREE["inventory_sha256"],
        },
        "change_run": {
            "bytes": SOURCE_RUN_TREE["file_bytes"],
            "files": SOURCE_RUN_TREE["files"],
            "manifest_bytes": SOURCE_RUN_MANIFEST_BYTES,
            "manifest_sha256": SOURCE_RUN_MANIFEST_SHA256,
            "path": SOURCE_RUN_PATH.relative_to(PACKAGE_ROOT).as_posix(),
            "selected_queue_ids_sha256": SOURCE_SELECTION_SHA256,
            "tree_sha256": SOURCE_RUN_TREE["inventory_sha256"],
        },
        "combined_blind_decisions": combined_spec,
        "reviewer_input_part_a": part_a_spec,
        "reviewer_input_part_b": part_b_spec,
    }

    order = dict(inputs["order"])
    records: list[dict[str, Any]] = []
    for index, decision in enumerate(decisions):
        blind_id = decision["blind_id"]
        queue_id = order[blind_id]
        group = inputs["grouped"][inputs["fingerprints"][blind_id]]
        source_part = part_a_spec if index < 34 else part_b_spec
        similarity = None
        if "visually_identical_to" in decision:
            target = decision["visually_identical_to"]
            exact = inputs["fingerprints"][blind_id] == inputs["fingerprints"][target]
            similarity = {
                "counted_as_exact_duplicate": exact,
                "exact_four_image_hash_match": exact,
                "reported_target": target,
                "type": (
                    "reviewer_reported_exact_visual_duplicate"
                    if exact
                    else "reviewer_reported_approximate_visual_similarity"
                ),
            }
        record = {
            **decision,
            "combined_blind_decisions": combined_spec,
            "decision_scope": "identity_blind_visible_change_triage_only",
            "exact_visual_evidence": {
                "duplicate_group_members": list(group) if len(group) > 1 else [],
                "independent_satellite_confirmation_claim_created": False,
                "set_sha256": inputs["fingerprints"][blind_id],
                "unique_set_representative_for_accounting": blind_id == group[0],
            },
            "input_artifacts": _source_artifacts(inputs["source"], queue_id),
            "lineage_unsealed_after_visual_judgments_were_fixed": True,
            "queue_id": queue_id,
            "review_artifacts": inputs["review_artifacts"][blind_id],
            "reviewer_similarity_interpretation": similarity,
            "schema_version": 1,
            "source_blind_decision": source_part,
            "source_entity_lineage": inputs["source"]["jobs"][queue_id]["entity"],
            "visual_artifacts_inspected": list(VISUAL_ARTIFACT_NAMES),
        }
        records.append(record)
    reviews_raw = b"".join(_canonical_line(record) for record in records)

    builder = {
        "files": {
            "cli": _file_record(CLI_PATH),
            "module": _file_record(BUILDER_PATH),
            "root_shim": _file_record(ROOT_SHIM_PATH),
        }
    }
    accounting = {
        "decision_rows": {"total": 68, **EXPECTED_ROW_COUNTS},
        "exact_duplicate_groups": exact_groups,
        "reviewer_similarity_flags": reviewer_flags,
        "unique_exact_visual_evidence_sets": {
            "total": 65,
            **EXPECTED_UNIQUE_EXACT_COUNTS,
        },
    }
    definition = {
        "accounting": accounting,
        "builder": builder,
        "decision_semantics": DECISION_SEMANTICS,
        "format": "datacenter-atlas-explicit-v83-combined-analyst-review-definition",
        "generated_at": generated_at,
        "guardrails": GUARDRAILS,
        "publication_clock": {
            "combined_member_recorded_at": generated_at,
            "root_ctime_must_not_precede_generated_at": True,
            "stage_bytes_must_not_postdate_generated_at": True,
        },
        "review_id": REVIEW_ID,
        "runtime": inputs["prep_definition"]["runtime"],
        "schema_version": 1,
        "sources": source_pins,
    }
    summary = {
        "accounting": accounting,
        "counts": {
            "analyst_decision_rows": 68,
            "exact_duplicate_groups": 3,
            "review_artifacts_hash_bound": 272,
            "reviewer_approximate_similarity_flags": 1,
            "reviewer_inputs_preserved": 2,
            "source_artifacts_hash_bound": 408,
            "unique_exact_visual_evidence_sets": 65,
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
        BLIND_DECISIONS_FILENAME: combined_raw,
        DEFINITION_FILENAME: _canonical_json(definition),
        PART_A_FILENAME: inputs["raw_a"],
        PART_B_FILENAME: inputs["raw_b"],
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
        "format": "datacenter-atlas-explicit-v83-combined-analyst-review",
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
    projected = [
        {key: record[key] for key in decision}
        for decision, record in zip(decisions, records, strict=True)
    ]
    if projected != decisions:
        raise ExplicitV83AnalystReviewError(
            "blind decisions changed during lineage binding"
        )
    return output


def _write_file(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def publish_analyst_review(
    generated_at: str, output_path: Path = OUTPUT_PATH
) -> dict[str, Any]:
    """Stage, time-gate, and atomically no-replace publish the carrier."""

    canonical_time, target = preparation._timestamp(generated_at, "generated_at")
    if target <= datetime.now(UTC):
        raise ExplicitV83AnalystReviewError(
            "generated_at must be in the future at build start"
        )
    destination = output_path.resolve()
    if destination != OUTPUT_PATH.resolve():
        raise ExplicitV83AnalystReviewError("review output path changed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / f".{destination.name}.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise ExplicitV83AnalystReviewError(f"active output lock: {lock}") from error
    stage: Path | None = None
    promoted = False
    identity: tuple[int, int] | None = None
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        if destination.exists() or destination.is_symlink():
            raise ExplicitV83AnalystReviewError(
                f"refusing existing output: {destination}"
            )
        first = build_analyst_review(canonical_time)
        second = build_analyst_review(canonical_time)
        if first != second:
            raise ExplicitV83AnalystReviewError("two offline replays differ")
        stage = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        for name, raw in sorted(first.items()):
            _write_file(stage / name, raw)
        newest = max(
            max(entry.stat().st_mtime, getattr(entry.stat(), "st_birthtime", 0.0))
            for entry in [stage, *stage.rglob("*")]
        )
        if newest > target.timestamp() + 1e-6:
            raise ExplicitV83AnalystReviewError(
                "staged review bytes postdate generated_at"
            )
        preparation._freeze_tree(stage)
        frozen_inventory = preparation._tree_inventory(stage)
        while datetime.now(UTC) < target:
            remaining = (target - datetime.now(UTC)).total_seconds()
            time.sleep(min(max(remaining, 0.001), 0.25))
        if preparation._tree_inventory(stage) != frozen_inventory:
            raise ExplicitV83AnalystReviewError(
                "private review stage changed while waiting"
            )
        if destination.exists() or destination.is_symlink():
            raise ExplicitV83AnalystReviewError(
                f"review output appeared during publication: {destination}"
            )
        status = stage.stat()
        identity = (status.st_dev, status.st_ino)
        stage.chmod(0o755)
        preparation._promote_noreplace(stage, destination)
        stage = None
        promoted = True
        destination.chmod(0o555)
        if destination.stat().st_ctime + 1e-6 < target.timestamp():
            raise ExplicitV83AnalystReviewError(
                "review root ctime precedes generated_at"
            )
        return validate_analyst_review(destination)
    except BaseException:
        if promoted and destination.exists() and not destination.is_symlink() and identity:
            status = destination.stat()
            if (status.st_dev, status.st_ino) == identity:
                rollback = destination.parent / (
                    f".{destination.name}.rollback-{os.getpid()}"
                )
                if not rollback.exists() and not rollback.is_symlink():
                    destination.chmod(0o755)
                    preparation._promote_noreplace(destination, rollback)
                    preparation._thaw_and_remove(rollback)
        if stage is not None:
            preparation._thaw_and_remove(stage)
        raise
    finally:
        os.close(descriptor)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def validate_analyst_review(output_path: Path = OUTPUT_PATH) -> dict[str, Any]:
    """Rebuild and verify the frozen review carrier byte-for-byte offline."""

    destination = output_path.resolve()
    if destination != OUTPUT_PATH.resolve():
        raise ExplicitV83AnalystReviewError("review output path changed")
    definition_raw = (destination / DEFINITION_FILENAME).read_bytes()
    definition = _strict_json(definition_raw, "review definition")
    generated_at, target = preparation._timestamp(
        definition.get("generated_at"), "generated_at"
    )
    if destination.stat().st_ctime + 1e-6 < target.timestamp():
        raise ExplicitV83AnalystReviewError(
            "review root ctime precedes generated_at"
        )
    inventory = preparation._tree_inventory(destination)
    actual = {
        path.name: path.read_bytes()
        for path in destination.iterdir()
        if path.is_file()
    }
    expected = build_analyst_review(generated_at)
    if actual != expected:
        raise ExplicitV83AnalystReviewError(
            "review differs from offline reconstruction"
        )
    manifest_raw = actual[MANIFEST_FILENAME]
    if actual[MANIFEST_HASH_FILENAME] != (
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    ):
        raise ExplicitV83AnalystReviewError("review manifest sidecar changed")
    manifest = _strict_json(manifest_raw, "review manifest")
    return {**manifest, "tree_inventory": inventory}


__all__ = [
    "BLIND_DECISIONS_FILENAME",
    "DECISION_SEMANTICS",
    "DEFINITION_FILENAME",
    "EXPECTED_APPROXIMATE_LINK",
    "EXPECTED_EXACT_VISUAL_GROUPS",
    "EXPECTED_ROW_COUNTS",
    "EXPECTED_UNIQUE_EXACT_COUNTS",
    "ExplicitV83AnalystReviewError",
    "GUARDRAILS",
    "MANIFEST_FILENAME",
    "MANIFEST_HASH_FILENAME",
    "OUTPUT_PATH",
    "PART_A_FILENAME",
    "PART_A_PATH",
    "PART_A_SHA256",
    "PART_B_FILENAME",
    "PART_B_PATH",
    "PART_B_SHA256",
    "README_FILENAME",
    "REVIEW_ID",
    "REVIEWS_FILENAME",
    "SUMMARY_FILENAME",
    "build_analyst_review",
    "publish_analyst_review",
    "validate_analyst_review",
]
