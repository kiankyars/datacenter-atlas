"""Immutable analyst review for the v56 runtime-correct satellite-change retry.

This carrier publishes only hash-bound analyst triage. It never copies source
imagery, mutates atlas data, or turns optical change into an identity,
lifecycle, construction-status, type, capacity, power, energy, PUE, workload,
operator, or physical-site claim. The failed no-raster incident run is retained
only as explicitly excluded technical lineage.
"""

from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any, Iterator, Mapping


REVIEW_ID = "2026-07-20-open-seed-v56-active-review-v1"
GENERATED_AT = "2026-07-20T23:12:00Z"
REVIEWED_AT = "2026-07-20T23:11:00Z"
DEFINITION_PATH = (
    "definitions/satellite_change_reviews/"
    "2026-07-20-open-seed-v56-active-review-v1.json"
)
OUTPUT_PATH = f"satellite_change_reviews/{REVIEW_ID}"
DEFINITION_SHA256 = "c35728fab6b3fa909586d89cb605d978653d9353196a5e7cc56796985e0e4e6c"

SOURCE_RUN_PATH = (
    "satellite_change_runs/2026-07-20-open-seed-v56-active-runtime-retry-001"
)
SOURCE_MANIFEST = {
    "bytes": 42_990,
    "path": f"{SOURCE_RUN_PATH}/batch-manifest.json",
    "sha256": "f94fb3298b352dc579ae5d07020e442889424e782ee04dbbe6f306826270c5f8",
}
SOURCE_TREE = {
    "directories": 15,
    "directory_mode": "0555",
    "file_bytes": 10_674_666,
    "file_mode": "0444",
    "files": 37,
    "inventory_sha256": (
        "1305b37c874bc6c136da1e0d4f31b254c3bea5a831bc87d19eb5d9830b815806"
    ),
    "path": SOURCE_RUN_PATH,
    "schema_version": 1,
}

QUEUE_RUN_PATH = "satellite_review_queues/2026-07-20-open-seed-v56"
QUEUE_MANIFEST = {
    "bytes": 13_472,
    "path": f"{QUEUE_RUN_PATH}/manifest.json",
    "sha256": "d02dca01f2f86915d01355ac54fd10c43796576bd2a484d58e3f69f4046834e2",
}
QUEUE_FILE = {
    "bytes": 422_650,
    "path": f"{QUEUE_RUN_PATH}/satellite-review-queue.jsonl",
    "sha256": "e065c7024a4ba88fa74f87d846b2272a0a0ef006c64eca69acfb7f6e156101b7",
}
QUEUE_TREE = {
    "directories": 1,
    "directory_mode": "0555",
    "file_bytes": 436_202,
    "file_mode": "0444",
    "files": 3,
    "inventory_sha256": (
        "11558db05baf9df827429f95270020956239b7c7d93d1ada46d3aad13a614d70"
    ),
    "path": QUEUE_RUN_PATH,
    "schema_version": 1,
}

CATALOG_RUN_PATH = "satellite_review_runs/2026-07-20-open-seed-v56-active-001"
CATALOG_MANIFEST = {
    "bytes": 46_497,
    "path": f"{CATALOG_RUN_PATH}/batch-manifest.json",
    "sha256": "ab5cbf2f747b97f603def872d03a7dc4f8786108b28f78e98cc192bd3911b1d3",
}
CATALOG_TREE = {
    "directories": 16,
    "directory_mode": "0555",
    "file_bytes": 4_887_386,
    "file_mode": "0444",
    "files": 22,
    "inventory_sha256": (
        "edd17eec057cf6f7d1da02bb4f28c2de44f31297ed6d3d20c5601f958dd8b93e"
    ),
    "path": CATALOG_RUN_PATH,
    "schema_version": 1,
}

INCIDENT_RUN_PATH = "satellite_change_runs/2026-07-20-open-seed-v56-active-001"
INCIDENT_MANIFEST = {
    "bytes": 29_299,
    "path": f"{INCIDENT_RUN_PATH}/batch-manifest.json",
    "sha256": "d2897172ad301f51e6a93e5beaf6f2a4dc4945833c520e2b704b907e705ca67c",
}
INCIDENT_TREE = {
    "directories": 9,
    "directory_mode": "0555",
    "file_bytes": 29_299,
    "file_mode": "0444",
    "files": 1,
    "inventory_sha256": (
        "2ed63f1c25e590a654c944b6abac1da5f28a46a9d0bfaeb0eead4eaaadd12db7"
    ),
    "path": INCIDENT_RUN_PATH,
    "schema_version": 1,
}

PREDECESSOR_REVIEW_ID = "2026-07-20-open-seed-v55-active-review-v1"
PREDECESSOR_DEFINITION = {
    "bytes": 18_540,
    "path": (
        "definitions/satellite_change_reviews/"
        "2026-07-20-open-seed-v55-active-review-v1.json"
    ),
    "sha256": "5dbe5e35da8af84a84e62717355c0d5b3c0cc228a2206f6dedb20b41eab83cc3",
}
PREDECESSOR_MANIFEST = {
    "bytes": 18_667,
    "path": (
        "satellite_change_reviews/2026-07-20-open-seed-v55-active-review-v1/"
        "manifest.json"
    ),
    "sha256": "19e025f4435c413ce9d9af1176bd54996ab474fab216277a7b5a5165980a170a",
}
PREDECESSOR_TREE = {
    "directories": 1,
    "directory_mode": "0555",
    "file_bytes": 54_993,
    "file_mode": "0444",
    "files": 6,
    "inventory_sha256": (
        "baf1172ab85658ea80f34fdafc68868e2f8fc112ab5fc06e219015b6361c4a59"
    ),
    "path": f"satellite_change_reviews/{PREDECESSOR_REVIEW_ID}",
    "schema_version": 1,
}

CARRIED_QUEUE_IDS = (
    "satq-02a713b5d0ec25375cffb0c3",
    "satq-511257788faac7f8fe916b55",
    "satq-5feb20b3df63076cce05ab3f",
    "satq-ac9d66dd45f3a868190ec4c1",
    "satq-ef22ae26b5cba60034c8567f",
)
PENTAPOINT_QUEUE_ID = "satq-b6f121dc644b91ad78eb479a"
QUEUE_IDS = (*CARRIED_QUEUE_IDS, PENTAPOINT_QUEUE_ID)
TECHNICAL_BLOCKER_QUEUE_IDS = ("satq-54c6402eb93d14f1ea754e66",)
SOURCE_SELECTED_QUEUE_IDS = (
    "satq-ac9d66dd45f3a868190ec4c1",
    "satq-02a713b5d0ec25375cffb0c3",
    "satq-54c6402eb93d14f1ea754e66",
    "satq-b6f121dc644b91ad78eb479a",
    "satq-ef22ae26b5cba60034c8567f",
    "satq-511257788faac7f8fe916b55",
    "satq-5feb20b3df63076cce05ab3f",
)

RETAIN_DECISION = "retain_for_site_aligned_visible_change_follow_up"
REJECT_DECISION = "reject_for_site_promotion"
REVIEW_METHOD = (
    "completed_analyst_visual_inspection_of_before_after_comparison_overlay_"
    "and_proposals_at_original_resolution"
)

SCOPE = {
    "atlas_claim_created": False,
    "atlas_mutation": False,
    "automated_promotion_allowed": False,
    "capacity_claim_created": False,
    "construction_area_claim_created": False,
    "construction_status_claim_created": False,
    "data_centre_type_claim_created": False,
    "decision_applies_only_to_imagery_visible_change_triage": True,
    "energy_claim_created": False,
    "excluded_incident_run_used_as_imagery_evidence": False,
    "identity_claim_created": False,
    "imagery_change_is_construction_truth": False,
    "it_capacity_claim_created": False,
    "lifecycle_status_claim_created": False,
    "manual_review_completed": True,
    "operating_status_claim_created": False,
    "operator_claim_created": False,
    "power_claim_created": False,
    "pue_claim_created": False,
    "separately_sourced_facts_negated": False,
    "site_count_claim_created": False,
    "source_change_artifacts_copied": False,
    "technical_blockers_are_review_decisions": False,
    "unique_site_claim_created": False,
    "workload_claim_created": False,
}

PENTAPOINT_DECISION = {
    "decision": REJECT_DECISION,
    "entity": {
        "id": "a75eaf2b-790f-5266-be60-3f2bafee2eeb",
        "name": "PentaPoint EMD BKK-01 Development",
    },
    "observations": [
        "The original-resolution comparison and overlay cover a broad central-Bangkok AOI with diffuse spectral change across unrelated urban roofs and roads, plus invalid or cloud-masked pixels.",
        "BKK-01 is an interior-floor fit-out in an existing tower, so 10 m optical change cannot be attributed to it; this rejection applies only to imagery promotion and does not negate the official under-construction record.",
    ],
    "queue_id": PENTAPOINT_QUEUE_ID,
    "report_metrics": {
        "interpretation": "report_derived_change_mask_metadata_not_construction_area",
        "label": "large_spectral_change_candidate",
        "proposal_area_m2_after_component_filter": 115_400.0,
        "proposal_component_count": 14,
        "valid_pixel_fraction": 0.9212862188152785,
        "valid_pixel_percent_display": 92.13,
    },
    "review_method": REVIEW_METHOD,
    "reviewed_at": REVIEWED_AT,
}

TECHNICAL_BLOCKERS = (
    {
        "artifacts_hash_bound": 0,
        "blocker": "multi_tile_mosaic_required",
        "detail": (
            "AOI covering window crosses asset red; a future multi-tile mosaic "
            "is required"
        ),
        "entity": {
            "id": "6710faa1-0010-5269-b1f3-7d7ebcda1ced",
            "name": "Menlo Digital MD-PHX1 Current Site Preparation",
        },
        "metadata_only": True,
        "queue_id": "satq-54c6402eb93d14f1ea754e66",
        "review_decision_created": False,
        "source_state": "failed",
    },
)

EXCLUDED_INCIDENT = {
    "closed_tree": INCIDENT_TREE,
    "disposition": "excluded_technical_lineage_only",
    "imagery_evidence_used": False,
    "manifest": INCIDENT_MANIFEST,
    "raster_artifacts_hash_bound": 0,
    "reason": "required_imagery_runtime_unavailable_no_raster_outputs",
    "review_decision_created": False,
}

REVIEWS_FILENAME = "analyst-reviews.jsonl"
SUMMARY_FILENAME = "summary.json"
README_FILENAME = "README.md"
ATTRIBUTION_FILENAME = "ATTRIBUTION.txt"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
BUNDLE_FILES = frozenset(
    {
        ATTRIBUTION_FILENAME,
        README_FILENAME,
        REVIEWS_FILENAME,
        SUMMARY_FILENAME,
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
    }
)


class SatelliteChangeReviewV3Error(ValueError):
    """Raised when review inputs, semantics, or publication fail closed."""


@dataclass(frozen=True, slots=True)
class SatelliteChangeReviewV3Bundle:
    files: Mapping[str, bytes]
    manifest: Mapping[str, Any]


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


def _read_regular(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise SatelliteChangeReviewV3Error(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SatelliteChangeReviewV3Error(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise SatelliteChangeReviewV3Error(f"{label} must be a JSON object")
    return value


def _read_pinned_bytes(
    package_root: Path, spec: Mapping[str, Any], label: str
) -> bytes:
    raw = _read_regular(package_root / str(spec["path"]), label)
    if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
        raise SatelliteChangeReviewV3Error(f"{label} checkpoint changed")
    return raw


def _read_pinned_json(
    package_root: Path, spec: Mapping[str, Any], label: str
) -> tuple[dict[str, Any], bytes]:
    raw = _read_pinned_bytes(package_root, spec, label)
    return _json_object(raw, label), raw


def _tree_inventory(root: Path, label: str) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise SatelliteChangeReviewV3Error(f"{label} must be a regular directory")
    digest = hashlib.sha256()
    directories = 0
    files = 0
    file_bytes = 0
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise SatelliteChangeReviewV3Error(
                f"{label} contains a symlink: {relative}"
            )
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            if mode != 0o555:
                raise SatelliteChangeReviewV3Error(
                    f"{label} directory mode changed: {relative} is {mode:04o}"
                )
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
            directories += 1
        elif path.is_file():
            if mode != 0o444:
                raise SatelliteChangeReviewV3Error(
                    f"{label} file mode changed: {relative} is {mode:04o}"
                )
            raw = path.read_bytes()
            digest.update(
                (f"F\0{relative}\0{mode:04o}\0{len(raw)}\0{_sha256(raw)}\n").encode()
            )
            files += 1
            file_bytes += len(raw)
        else:
            raise SatelliteChangeReviewV3Error(
                f"{label} contains unsupported entry: {relative}"
            )
    return {
        "directories": directories,
        "directory_mode": "0555",
        "file_bytes": file_bytes,
        "file_mode": "0444",
        "files": files,
        "inventory_sha256": digest.hexdigest(),
        "schema_version": 1,
    }


def _validate_tree(
    package_root: Path, spec: Mapping[str, Any], label: str
) -> dict[str, Any]:
    inventory = _tree_inventory(package_root / str(spec["path"]), label)
    expected = {key: value for key, value in spec.items() if key != "path"}
    if inventory != expected:
        raise SatelliteChangeReviewV3Error(f"{label} closed tree changed")
    return inventory


def _contains_key(value: Any, forbidden: str) -> bool:
    if isinstance(value, Mapping):
        return forbidden in value or any(
            _contains_key(child, forbidden) for child in value.values()
        )
    if isinstance(value, list):
        return any(_contains_key(child, forbidden) for child in value)
    return False


def _validate_false_claims(value: Mapping[str, Any], label: str) -> None:
    claim_keys = {
        "data_centre_type_claim",
        "energy_claim",
        "identity_claim",
        "it_capacity_claim",
        "lifecycle_claim",
        "operating_status_claim",
        "operator_claim",
        "power_claim",
        "pue_claim",
        "workload_claim",
    }
    if any(value.get(key) is not False for key in claim_keys):
        raise SatelliteChangeReviewV3Error(f"{label} contains a positive claim")


def _source_artifact_paths(
    source_manifest: Mapping[str, Any], queue_id: str
) -> dict[str, dict[str, Any]]:
    job = source_manifest["jobs"][queue_id]
    artifacts = job.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {
        "after.png",
        "before.png",
        "change-overlay.png",
        "change-proposals.geojson",
        "comparison.png",
        "report.json",
    }:
        raise SatelliteChangeReviewV3Error(f"source artifact set changed: {queue_id}")
    base = f"{SOURCE_RUN_PATH}/jobs/{queue_id}/change"
    return {
        name: {
            "bytes": spec["bytes"],
            "path": f"{base}/{name}",
            "sha256": spec["sha256"],
        }
        for name, spec in sorted(artifacts.items())
    }


def _definition_rows(package_root: Path) -> list[dict[str, Any]]:
    predecessor, _ = _read_pinned_json(
        package_root, PREDECESSOR_DEFINITION, "predecessor review definition"
    )
    source_manifest, _ = _read_pinned_json(
        package_root, SOURCE_MANIFEST, "source change manifest"
    )
    predecessor_rows = {
        str(row.get("queue_id")): row for row in predecessor.get("decisions", [])
    }
    if set(predecessor_rows) != set(CARRIED_QUEUE_IDS):
        raise SatelliteChangeReviewV3Error("predecessor decisions changed")
    rows: list[dict[str, Any]] = []
    for queue_id in CARRIED_QUEUE_IDS:
        row = copy.deepcopy(predecessor_rows[queue_id])
        rebound = _source_artifact_paths(source_manifest, queue_id)
        for name, source_spec in rebound.items():
            predecessor_spec = row["input_artifacts"][name]
            if {
                "bytes": predecessor_spec["bytes"],
                "sha256": predecessor_spec["sha256"],
            } != {
                "bytes": source_spec["bytes"],
                "sha256": source_spec["sha256"],
            }:
                raise SatelliteChangeReviewV3Error(
                    f"carried source artifact changed: {queue_id} {name}"
                )
        row["input_artifacts"] = rebound
        rows.append(row)

    penta = copy.deepcopy(PENTAPOINT_DECISION)
    penta["input_artifacts"] = _source_artifact_paths(
        source_manifest, PENTAPOINT_QUEUE_ID
    )
    rows.append(penta)
    return rows


def make_review_definition(package_root: str | Path) -> bytes:
    """Return canonical v3 definition bytes from hash-pinned local inputs."""

    root = Path(package_root).resolve()
    document = {
        "decisions": _definition_rows(root),
        "excluded_incident_run": EXCLUDED_INCIDENT,
        "generated_at": GENERATED_AT,
        "predecessor_review": {
            "closed_tree": PREDECESSOR_TREE,
            "definition": PREDECESSOR_DEFINITION,
            "manifest": PREDECESSOR_MANIFEST,
            "review_id": PREDECESSOR_REVIEW_ID,
        },
        "review_id": REVIEW_ID,
        "schema_version": 3,
        "scope": SCOPE,
        "source_catalog_run": {
            "closed_tree": CATALOG_TREE,
            "manifest": CATALOG_MANIFEST,
        },
        "source_change_run": {
            "closed_tree": SOURCE_TREE,
            "manifest": SOURCE_MANIFEST,
        },
        "source_queue_bundle": {
            "closed_tree": QUEUE_TREE,
            "manifest": QUEUE_MANIFEST,
            "queue": QUEUE_FILE,
        },
        "technical_blockers": list(TECHNICAL_BLOCKERS),
    }
    return _canonical_json(document)


def _validate_definition_semantics(
    document: Mapping[str, Any], expected: Mapping[str, Any]
) -> None:
    if document != expected:
        raise SatelliteChangeReviewV3Error("review definition semantics changed")
    if _contains_key(document, "confidence"):
        raise SatelliteChangeReviewV3Error("confidence is forbidden in this review")
    decisions = document.get("decisions")
    if not isinstance(decisions, list) or [
        row.get("queue_id") for row in decisions
    ] != list(QUEUE_IDS):
        raise SatelliteChangeReviewV3Error("review decisions changed")
    counts = {RETAIN_DECISION: 0, REJECT_DECISION: 0}
    for row in decisions:
        decision = row.get("decision")
        if decision not in counts:
            raise SatelliteChangeReviewV3Error("review decision value changed")
        counts[str(decision)] += 1
        if row.get("review_method") != REVIEW_METHOD:
            raise SatelliteChangeReviewV3Error("review method changed")
        artifacts = row.get("input_artifacts")
        if not isinstance(artifacts, Mapping) or len(artifacts) != 6:
            raise SatelliteChangeReviewV3Error("review artifact binding changed")
    if counts != {RETAIN_DECISION: 3, REJECT_DECISION: 3}:
        raise SatelliteChangeReviewV3Error("review decision counts changed")
    if document.get("scope") != SCOPE or any(
        document["scope"].get(key) is not False
        for key in (
            "atlas_claim_created",
            "capacity_claim_created",
            "construction_status_claim_created",
            "data_centre_type_claim_created",
            "energy_claim_created",
            "identity_claim_created",
            "lifecycle_status_claim_created",
            "operating_status_claim_created",
            "operator_claim_created",
            "power_claim_created",
            "pue_claim_created",
            "site_count_claim_created",
            "unique_site_claim_created",
            "workload_claim_created",
        )
    ):
        raise SatelliteChangeReviewV3Error("review scope changed")
    if document.get("excluded_incident_run") != EXCLUDED_INCIDENT:
        raise SatelliteChangeReviewV3Error("excluded incident lineage changed")


def _validate_definition(
    definition_path: str | Path,
) -> tuple[dict[str, Any], bytes, Path]:
    path = Path(definition_path).resolve()
    package_root = path.parents[2]
    if path != package_root / DEFINITION_PATH:
        raise SatelliteChangeReviewV3Error("review definition publication path changed")
    raw = _read_regular(path, "review definition")
    document = _json_object(raw, "review definition")
    if raw != _canonical_json(document):
        raise SatelliteChangeReviewV3Error("review definition is not canonical JSON")
    if _sha256(raw) != DEFINITION_SHA256:
        raise SatelliteChangeReviewV3Error("review definition content changed")
    expected = _json_object(make_review_definition(package_root), "expected definition")
    _validate_definition_semantics(document, expected)
    for timestamp in (GENERATED_AT, REVIEWED_AT):
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed > datetime.now(UTC):
            raise SatelliteChangeReviewV3Error("review timestamp is in the future")
    return document, raw, package_root


def _validate_upstream(
    package_root: Path, definition: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    for spec, label in (
        (QUEUE_TREE, "source queue bundle"),
        (CATALOG_TREE, "source catalog run"),
        (SOURCE_TREE, "source runtime retry run"),
        (INCIDENT_TREE, "excluded no-raster incident run"),
        (PREDECESSOR_TREE, "predecessor review bundle"),
    ):
        _validate_tree(package_root, spec, label)
    queue_manifest, _ = _read_pinned_json(
        package_root, QUEUE_MANIFEST, "source queue manifest"
    )
    _read_pinned_bytes(package_root, QUEUE_FILE, "source queue file")
    catalog_manifest, _ = _read_pinned_json(
        package_root, CATALOG_MANIFEST, "source catalog manifest"
    )
    source_manifest, _ = _read_pinned_json(
        package_root, SOURCE_MANIFEST, "source runtime retry manifest"
    )
    incident_manifest, _ = _read_pinned_json(
        package_root, INCIDENT_MANIFEST, "excluded incident manifest"
    )
    _read_pinned_json(package_root, PREDECESSOR_MANIFEST, "predecessor review manifest")

    if (
        queue_manifest.get("pipeline") != "global_satellite_review_queue"
        or catalog_manifest.get("pipeline") != "satellite_review_catalog_batch"
        or source_manifest.get("pipeline") != "satellite_review_change_batch"
        or source_manifest.get("state") != "incomplete"
        or source_manifest.get("queue_bundle", {}).get("manifest_sha256")
        != QUEUE_MANIFEST["sha256"]
        or source_manifest.get("queue_bundle", {}).get("queue_sha256")
        != QUEUE_FILE["sha256"]
        or source_manifest.get("catalog_batches", [{}])[0].get("manifest_sha256")
        != CATALOG_MANIFEST["sha256"]
        or source_manifest.get("selection", {}).get("selected_queue_ids")
        != list(SOURCE_SELECTED_QUEUE_IDS)
        or source_manifest.get("summary", {}).get("jobs_completed") != 6
        or source_manifest.get("summary", {}).get("jobs_failed") != 1
        or source_manifest.get("summary", {}).get("jobs_selected") != 7
    ):
        raise SatelliteChangeReviewV3Error("accepted source lineage changed")
    if (
        incident_manifest.get("pipeline") != "satellite_review_change_batch"
        or incident_manifest.get("summary", {}).get("jobs_completed") != 0
        or incident_manifest.get("summary", {}).get("jobs_failed") != 7
        or incident_manifest.get("processor", {})
        .get("runtime", {})
        .get("required_packages_available")
        is not False
        or any(
            job.get("artifacts") is not None or job.get("report") is not None
            for job in incident_manifest.get("jobs", {}).values()
        )
    ):
        raise SatelliteChangeReviewV3Error(
            "excluded incident acquired imagery-evidence semantics"
        )

    definition_rows = {row["queue_id"]: row for row in definition["decisions"]}
    reports: dict[str, dict[str, Any]] = {}
    for queue_id in QUEUE_IDS:
        row = definition_rows[queue_id]
        job = source_manifest["jobs"][queue_id]
        catalog_job = catalog_manifest["jobs"][queue_id]
        if (
            job.get("state") != "completed"
            or job.get("attempts") != 1
            or job.get("entity") != row["entity"]
            or catalog_job.get("state") != "completed"
            or catalog_job.get("entity_id") != row["entity"]["id"]
        ):
            raise SatelliteChangeReviewV3Error(f"source job changed: {queue_id}")
        expected_artifacts = {
            name: {"bytes": spec["bytes"], "sha256": spec["sha256"]}
            for name, spec in row["input_artifacts"].items()
        }
        if job.get("artifacts") != expected_artifacts:
            raise SatelliteChangeReviewV3Error(
                f"source artifact manifest changed: {queue_id}"
            )
        for name, spec in row["input_artifacts"].items():
            raw = _read_regular(package_root / spec["path"], f"{queue_id} {name}")
            if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
                raise SatelliteChangeReviewV3Error(
                    f"source artifact changed: {queue_id} {name}"
                )
        report_spec = row["input_artifacts"]["report.json"]
        report_raw = _read_regular(
            package_root / report_spec["path"], f"{queue_id} report"
        )
        report = _json_object(report_raw, f"{queue_id} report")
        if report_raw != _canonical_json(report):
            raise SatelliteChangeReviewV3Error(
                f"source report is not canonical: {queue_id}"
            )
        metrics = row["report_metrics"]
        report_metrics = report.get("metrics", {})
        if (
            report.get("algorithm_version") != "sentinel-2-l2a-change-v2"
            or report.get("entity") != row["entity"]
            or report_metrics.get("proposal_component_count")
            != metrics["proposal_component_count"]
            or report_metrics.get("proposal_area_m2_after_component_filter")
            != metrics["proposal_area_m2_after_component_filter"]
            or report_metrics.get("valid_pixel_fraction")
            != metrics["valid_pixel_fraction"]
            or round(report_metrics["valid_pixel_fraction"] * 100, 2)
            != metrics["valid_pixel_percent_display"]
            or (
                "label" in metrics
                and report.get("classification", {}).get("label") != metrics["label"]
            )
        ):
            raise SatelliteChangeReviewV3Error(f"report metrics changed: {queue_id}")
        _validate_false_claims(report.get("classification", {}), f"{queue_id} report")
        if report.get("outputs") != {
            name: expected_artifacts[name]
            for name in sorted(expected_artifacts)
            if name != "report.json"
        }:
            raise SatelliteChangeReviewV3Error(f"report outputs changed: {queue_id}")
        reports[queue_id] = report

    blocker_metadata = []
    blocker_rows = {row["queue_id"]: row for row in definition["technical_blockers"]}
    for queue_id in TECHNICAL_BLOCKER_QUEUE_IDS:
        blocker = blocker_rows[queue_id]
        job = source_manifest["jobs"][queue_id]
        if (
            job.get("state") != "failed"
            or job.get("attempts") != 1
            or job.get("entity") != blocker["entity"]
            or job.get("artifacts") is not None
            or job.get("report") is not None
            or len(job.get("failures", [])) != 1
            or not job["failures"][0].get("error", "").endswith(blocker["detail"])
        ):
            raise SatelliteChangeReviewV3Error(f"technical blocker changed: {queue_id}")
        blocker_metadata.append(
            {
                **blocker,
                "source_change_manifest": SOURCE_MANIFEST,
                "source_failure_sha256": _sha256(_canonical_json(job["failures"])),
            }
        )
    return source_manifest, reports, blocker_metadata


def _review_record(
    decision: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
    report: Mapping[str, Any],
) -> dict[str, Any]:
    queue_id = str(decision["queue_id"])
    carried = queue_id in CARRIED_QUEUE_IDS
    return {
        "decision": decision["decision"],
        "decision_scope": "imagery_visible_change_triage_only",
        "entity": decision["entity"],
        "input_artifacts": decision["input_artifacts"],
        "observations": decision["observations"],
        "queue_id": queue_id,
        "report_metrics": decision["report_metrics"],
        "review_method": decision["review_method"],
        "review_origin": (
            {
                "kind": "carried_forward_byte_identical_change_artifacts",
                "predecessor_definition": PREDECESSOR_DEFINITION,
                "predecessor_manifest": PREDECESSOR_MANIFEST,
                "predecessor_review_id": PREDECESSOR_REVIEW_ID,
            }
            if carried
            else {
                "kind": "new_original_resolution_visual_review",
                "predecessor_review_id": None,
            }
        ),
        "reviewed_at": decision["reviewed_at"],
        "schema_version": 3,
        "scope": SCOPE,
        "source_lineage": {
            "algorithm_version": report["algorithm_version"],
            "baseline": {
                key: report["baseline"][key]
                for key in ("datetime", "id", "mgrs_tile", "stac_item_sha256")
            },
            "catalog_batch_manifest": CATALOG_MANIFEST,
            "current": {
                key: report["current"][key]
                for key in ("datetime", "id", "mgrs_tile", "stac_item_sha256")
            },
            "queue_manifest": QUEUE_MANIFEST,
            "queue_sha256": QUEUE_FILE["sha256"],
            "report_source": report["source"],
            "source_change_manifest": SOURCE_MANIFEST,
            "source_report_sha256": source_manifest["jobs"][queue_id]["report"][
                "report_sha256"
            ],
        },
    }


def _readme_bytes() -> bytes:
    return (
        "# Analyst review of v56 runtime-correct satellite-change outputs\n\n"
        "This immutable bundle records six original-resolution analyst decisions: "
        "three outputs are retained only for site-aligned visible-change follow-up "
        "and three are rejected for imagery-based site promotion. Five decisions "
        "carry forward the accepted v55 review over byte-identical six-file change "
        "artifacts; the PentaPoint BKK-01 output is newly rejected because diffuse "
        "central-Bangkok change and invalid pixels cannot isolate an interior-floor "
        "fit-out at 10 m resolution. The imagery rejection does not negate the "
        "official construction record.\n\n"
        "One MD-PHX1 job is a metadata-only multi-tile technical blocker, not a "
        "decision. The earlier no-raster incident run is preserved only as excluded "
        "technical lineage and supplies no imagery evidence.\n\n"
        "The source reports, PNGs, and GeoJSON remain in the frozen runtime-correct "
        "change run; this bundle copies none and binds all 36 decision artifacts by "
        "path, byte count, and SHA-256. Component counts, proposal areas, and valid-"
        "pixel fractions are change-mask metadata, not construction areas.\n\n"
        "These decisions create no atlas, identity, lifecycle, construction-status, "
        "operating-status, operator, data-centre type, workload, capacity, power, "
        "energy, PUE, or site-count claim, and negate no separately sourced fact.\n"
    ).encode("utf-8")


def _attribution_bytes() -> bytes:
    return (
        "Contains modified Copernicus Sentinel data 2024 and 2026.\n"
        "Catalog: Element 84 Earth Search v1.\n"
        "Dataset: Copernicus Sentinel-2 Level-2A.\n"
        "Source imagery is not copied into this review bundle; exact source artifacts "
        "remain hash-linked under their upstream terms.\n"
    ).encode("utf-8")


def build_satellite_change_review_v3(
    definition_path: str | Path,
) -> SatelliteChangeReviewV3Bundle:
    """Build deterministic review bytes from the frozen accepted inputs."""

    definition, definition_raw, package_root = _validate_definition(definition_path)
    source_manifest, reports, blocker_metadata = _validate_upstream(
        package_root, definition
    )
    decisions = {row["queue_id"]: row for row in definition["decisions"]}
    records = [
        _review_record(decisions[queue_id], source_manifest, reports[queue_id])
        for queue_id in QUEUE_IDS
    ]
    reviews_bytes = b"".join(_canonical_line(record) for record in records)
    summary = {
        "counts": {
            "decisions": 6,
            "excluded_no_raster_incident_runs": 1,
            "reject_for_site_promotion": 3,
            "retain_for_site_aligned_visible_change_follow_up": 3,
            "source_artifacts_hash_bound": 36,
            "technical_multitile_failures": 1,
        },
        "decisions": [
            {
                "decision": record["decision"],
                "entity": record["entity"],
                "queue_id": record["queue_id"],
                "report_metrics": record["report_metrics"],
                "review_origin": record["review_origin"],
            }
            for record in records
        ],
        "excluded_incident_run": EXCLUDED_INCIDENT,
        "generated_at": GENERATED_AT,
        "predecessor_review": definition["predecessor_review"],
        "review_id": REVIEW_ID,
        "reviewed_at": REVIEWED_AT,
        "schema_version": 3,
        "scope": SCOPE,
        "source_catalog_run": definition["source_catalog_run"],
        "source_change_run": definition["source_change_run"],
        "source_queue_bundle": definition["source_queue_bundle"],
        "technical_blockers": blocker_metadata,
    }
    output_files = {
        ATTRIBUTION_FILENAME: _attribution_bytes(),
        README_FILENAME: _readme_bytes(),
        REVIEWS_FILENAME: reviews_bytes,
        SUMMARY_FILENAME: _canonical_json(summary),
    }
    manifest = {
        "artifacts": {
            filename: {"bytes": len(raw), "sha256": _sha256(raw)}
            for filename, raw in sorted(output_files.items())
        },
        "definition": {
            "bytes": len(definition_raw),
            "path": DEFINITION_PATH,
            "sha256": _sha256(definition_raw),
        },
        "excluded_incident_run": EXCLUDED_INCIDENT,
        "format": "datacenter-atlas-satellite-change-analyst-review-v3",
        "generated_at": GENERATED_AT,
        "predecessor_review": definition["predecessor_review"],
        "review_id": REVIEW_ID,
        "reviewed_at": REVIEWED_AT,
        "schema_version": 3,
        "scope": SCOPE,
        "source_artifacts": {
            queue_id: decisions[queue_id]["input_artifacts"] for queue_id in QUEUE_IDS
        },
        "source_catalog_run": definition["source_catalog_run"],
        "source_change_run": definition["source_change_run"],
        "source_queue_bundle": definition["source_queue_bundle"],
        "technical_blockers": blocker_metadata,
    }
    manifest_bytes = _canonical_json(manifest)
    sidecar_bytes = f"{_sha256(manifest_bytes)}  {MANIFEST_FILENAME}\n".encode("ascii")
    files = {
        **output_files,
        MANIFEST_FILENAME: manifest_bytes,
        MANIFEST_HASH_FILENAME: sidecar_bytes,
    }
    if any(
        _contains_key(value, "confidence") for value in (records, summary, manifest)
    ):
        raise SatelliteChangeReviewV3Error("confidence leaked into review bundle")
    return SatelliteChangeReviewV3Bundle(files=files, manifest=manifest)


def _write_file(path: Path, raw: bytes) -> None:
    with path.open("xb") as destination:
        destination.write(raw)
        destination.flush()
        os.fsync(destination.fileno())


@contextmanager
def _exclusive_output_lock(destination: Path) -> Iterator[None]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / f".{destination.name}.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise SatelliteChangeReviewV3Error(
            f"refusing active output lock: {lock}"
        ) from error
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def write_review_definition(
    package_root: str | Path,
    output_path: str | Path,
) -> str:
    """Atomically create, but never replace, the canonical v3 definition."""

    root = Path(package_root).resolve()
    destination = Path(output_path).resolve()
    if destination != root / DEFINITION_PATH:
        raise SatelliteChangeReviewV3Error("definition output path changed")
    raw = make_review_definition(root)
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise SatelliteChangeReviewV3Error(
                f"refusing existing output: {destination}"
            )
        stage = destination.parent / f".{destination.name}.{os.getpid()}.tmp"
        try:
            _write_file(stage, raw)
            if destination.exists() or destination.is_symlink():
                raise SatelliteChangeReviewV3Error(
                    f"refusing late output collision: {destination}"
                )
            stage.replace(destination)
            _fsync_directory(destination.parent)
        finally:
            try:
                stage.unlink()
            except FileNotFoundError:
                pass
    return _sha256(raw)


def write_satellite_change_review_v3(
    definition_path: str | Path,
    output_path: str | Path,
    *,
    freeze: bool = True,
) -> dict[str, Any]:
    """Atomically publish a frozen v3 review without replacing anything."""

    if freeze is not True:
        raise SatelliteChangeReviewV3Error("review publication requires freeze=True")
    bundle = build_satellite_change_review_v3(definition_path)
    destination = Path(output_path).resolve()
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise SatelliteChangeReviewV3Error(
                f"refusing existing output: {destination}"
            )
        stage = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        try:
            for filename, raw in sorted(bundle.files.items()):
                _write_file(stage / filename, raw)
            if destination.exists() or destination.is_symlink():
                raise SatelliteChangeReviewV3Error(
                    f"refusing late output collision: {destination}"
                )
            stage.replace(destination)
            _fsync_directory(destination.parent)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
    for filename in BUNDLE_FILES:
        (destination / filename).chmod(0o444)
    destination.chmod(0o555)
    return dict(bundle.manifest)


def validate_satellite_change_review_v3(
    output_path: str | Path,
    *,
    definition_path: str | Path,
) -> dict[str, Any]:
    """Offline-reproduce a frozen v3 review byte-for-byte."""

    directory = Path(output_path)
    if directory.is_symlink() or not directory.is_dir():
        raise SatelliteChangeReviewV3Error("review bundle must be a regular directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES:
        raise SatelliteChangeReviewV3Error("review bundle file set changed")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555 or any(
        entry.is_symlink()
        or not entry.is_file()
        or stat.S_IMODE(entry.stat().st_mode) != 0o444
        for entry in entries
    ):
        raise SatelliteChangeReviewV3Error("review bundle must be frozen 0555/0444")
    actual = {
        filename: _read_regular(directory / filename, f"review {filename}")
        for filename in BUNDLE_FILES
    }
    manifest = _json_object(actual[MANIFEST_FILENAME], "review manifest")
    expected_sidecar = (
        f"{_sha256(actual[MANIFEST_FILENAME])}  {MANIFEST_FILENAME}\n".encode("ascii")
    )
    if actual[MANIFEST_HASH_FILENAME] != expected_sidecar:
        raise SatelliteChangeReviewV3Error("review manifest sidecar changed")
    expected = build_satellite_change_review_v3(definition_path)
    if actual != expected.files:
        raise SatelliteChangeReviewV3Error(
            "review bundle differs from offline reconstruction"
        )
    if manifest != expected.manifest:
        raise SatelliteChangeReviewV3Error("review manifest semantics changed")
    return dict(expected.manifest)


__all__ = [
    "BUNDLE_FILES",
    "CATALOG_MANIFEST",
    "CATALOG_RUN_PATH",
    "CATALOG_TREE",
    "DEFINITION_PATH",
    "DEFINITION_SHA256",
    "GENERATED_AT",
    "INCIDENT_MANIFEST",
    "INCIDENT_RUN_PATH",
    "INCIDENT_TREE",
    "OUTPUT_PATH",
    "PENTAPOINT_QUEUE_ID",
    "QUEUE_FILE",
    "QUEUE_IDS",
    "QUEUE_MANIFEST",
    "QUEUE_RUN_PATH",
    "QUEUE_TREE",
    "REJECT_DECISION",
    "RETAIN_DECISION",
    "REVIEWED_AT",
    "REVIEW_ID",
    "SCOPE",
    "SOURCE_MANIFEST",
    "SOURCE_RUN_PATH",
    "SOURCE_TREE",
    "TECHNICAL_BLOCKER_QUEUE_IDS",
    "SatelliteChangeReviewV3Bundle",
    "SatelliteChangeReviewV3Error",
    "build_satellite_change_review_v3",
    "make_review_definition",
    "validate_satellite_change_review_v3",
    "write_review_definition",
    "write_satellite_change_review_v3",
]
