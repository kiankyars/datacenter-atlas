"""Immutable carrier for the v57 identity-blind satellite-change review.

The carrier publishes hash-bound visual triage for 71 blind views covering 74
single-tile jobs.  It does not promote imagery into an atlas, identity,
lifecycle, current-status, construction-status, capacity, energy, type,
operator, workload, or site-count fact.  Queue status fields are retained only
as dated last-observed metadata and always require an authoritative refresh
before they may be treated as current.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
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


REVIEW_ID = "2026-07-20-open-seed-v57-active-review-v1"
GENERATED_AT = "2026-07-21T02:35:00Z"
REVIEWED_AT = "2026-07-21T02:30:00Z"
DEFINITION_PATH = (
    "definitions/satellite_change_reviews/"
    "2026-07-20-open-seed-v57-active-review-v1.json"
)
OUTPUT_PATH = f"satellite_change_reviews/{REVIEW_ID}"
DEFINITION_SHA256 = "eb009c496f805d8c68e9510904f45f5a7c82af3fe3f0428a4c96d97dd38aa482"

BLIND_REVIEW_SOURCE = {
    "bytes": 189_885,
    "path": (
        "sources/satellite-change-blind-review-2026-07-20-"
        "open-seed-v57-single-tile-v1.json"
    ),
    "sha256": "4880a51f3b5bf974b43543f256a4469af72d38aaaebfd706646b4e2eb26ffe0f",
}

QUEUE_RUN_PATH = "satellite_review_queues/2026-07-20-open-seed-v57"
QUEUE_MANIFEST = {
    "bytes": 13_586,
    "path": f"{QUEUE_RUN_PATH}/manifest.json",
    "sha256": "578b4778e552b86c0c07c419a6dd72572d48aaef324ce42154e3e8621401a48c",
}
QUEUE_FILE = {
    "bytes": 449_902,
    "path": f"{QUEUE_RUN_PATH}/satellite-review-queue.jsonl",
    "sha256": "a91f57f706e8c70a1b768e0506bfac7b2ac5c200f9fe0bbf8ee8a9a826bada99",
}
QUEUE_TREE = {
    "directories": 1,
    "directory_mode": "0555",
    "file_bytes": 463_568,
    "file_mode": "0444",
    "files": 3,
    "inventory_sha256": "ad8f9478172097aa29540fcb1e4507670280d100c745173633ea83cc74119ec8",
    "path": QUEUE_RUN_PATH,
    "schema_version": 1,
}

CATALOG_RUN_PATH = "satellite_review_runs/2026-07-20-open-seed-v57-active-001"
CATALOG_MANIFEST = {
    "bytes": 100_439,
    "path": f"{CATALOG_RUN_PATH}/batch-manifest.json",
    "sha256": "4a701a4e099b4cbbfd2d3ed9750edabe20c5fdac20df566e239c15e28f99fbef",
}
CATALOG_TREE = {
    "directories": 174,
    "directory_mode": "0555",
    "file_bytes": 56_500_969,
    "file_mode": "0444",
    "files": 256,
    "inventory_sha256": "355b4ced1d5722cce60abcd99b4af76f0e3816d2af86c07b8d697e0551f444a4",
    "path": CATALOG_RUN_PATH,
    "schema_version": 1,
}

PREPARATION_RUN_PATH = (
    "satellite_change_preparation/2026-07-20-open-seed-v57-active-v1"
)
PREPARATION_DEFINITION = {
    "bytes": 4_181,
    "path": (
        "sources/satellite-change-preparation-2026-07-20-"
        "open-seed-v57-active-v1.json"
    ),
    "sha256": "9700380bf1e45110d4b4efa8538ce3bc98793a79343ddfca018fc73ef962f8d8",
}
PREPARATION_MANIFEST = {
    "bytes": 5_885,
    "path": f"{PREPARATION_RUN_PATH}/manifest.json",
    "sha256": "84073fc695a3ef500bd11d5077935083a7869cd4adb30db5342f6c0e215011ff",
}
PREPARATION_SINGLE_TILE = {
    "bytes": 979_200,
    "path": f"{PREPARATION_RUN_PATH}/single-tile-ready.jsonl",
    "sha256": "c98d73b20411ac1fc7ee065bd6d34f35839ddb8e679c389c068f181eecd12e6c",
}
PREPARATION_TREE = {
    "directories": 1,
    "directory_mode": "0555",
    "file_bytes": 1_284_397,
    "file_mode": "0444",
    "files": 11,
    "inventory_sha256": "6ba201e2c634a98816fdca5d6cdef2f18b2d04a516a38d3d76370fbb74cd72b6",
    "path": PREPARATION_RUN_PATH,
    "schema_version": 1,
}

SOURCE_RUN_PATH = (
    "satellite_change_runs/2026-07-20-open-seed-v57-active-single-tile-v1-001"
)
SOURCE_MANIFEST = {
    "bytes": 418_083,
    "path": f"{SOURCE_RUN_PATH}/batch-manifest.json",
    "sha256": "69b749f599ff5b36b98cbbf3c13add7f242164ee04666d60551c0e85e193a62d",
}
SOURCE_TREE = {
    "directories": 150,
    "directory_mode": "0555",
    "file_bytes": 119_253_658,
    "file_mode": "0444",
    "files": 445,
    "inventory_sha256": "575bc6c94cffc7e43bbc3ae5913cea9f5bad2af5d0a303fb1efe15fbb7cce75d",
    "path": SOURCE_RUN_PATH,
    "schema_version": 1,
}

PREDECESSOR_REVIEW_ID = "2026-07-20-open-seed-v56-active-review-v1"
PREDECESSOR_DEFINITION = {
    "bytes": 23_421,
    "path": (
        "definitions/satellite_change_reviews/"
        "2026-07-20-open-seed-v56-active-review-v1.json"
    ),
    "sha256": "c35728fab6b3fa909586d89cb605d978653d9353196a5e7cc56796985e0e4e6c",
}
PREDECESSOR_MANIFEST = {
    "bytes": 17_652,
    "path": (
        "satellite_change_reviews/2026-07-20-open-seed-v56-active-review-v1/"
        "manifest.json"
    ),
    "sha256": "269fe8133138d82680b0fa9498f24ee3a886a3e32c58ab4013276d719868dba9",
}
PREDECESSOR_TREE = {
    "directories": 1,
    "directory_mode": "0555",
    "file_bytes": 66_834,
    "file_mode": "0444",
    "files": 6,
    "inventory_sha256": "b38079438e238da999a6afa52bb835ac70b57c0c8706082281e58a68d87e5fe4",
    "path": f"satellite_change_reviews/{PREDECESSOR_REVIEW_ID}",
    "schema_version": 1,
}

PENTAPOINT_QUEUE_ID = "satq-b6f121dc644b91ad78eb479a"
DECISION_SEMANTICS = {
    "R": "reject_imagery_promotion",
    "T": "retain_for_visible_change_follow_up_only",
    "U": "inconclusive",
}
PENTAPOINT_OVERRIDE = {
    "final_promotion_disposition": "reject_imagery_promotion",
    "official_evidence_constraint": "interior_fit_out_unobservable_at_10m",
    "predecessor_decision_preserved": True,
    "predecessor_review_id": PREDECESSOR_REVIEW_ID,
    "queue_id": PENTAPOINT_QUEUE_ID,
    "visual_verdict": "U",
}
STATUS_OBSERVATION_POLICY = {
    "authoritative_refresh_completed_by_review": False,
    "authoritative_refresh_required_before_current_status_use": True,
    "imagery_can_satisfy_authoritative_status_refresh": False,
    "imagery_status_refresh_performed": False,
    "metadata_source": "source_queue_input_only",
    "semantics": "dated_last_observed_metadata_not_current_status",
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
NEAR_DUPLICATE_RELATIONSHIPS = [
    {
        "blind_ids": ["V57-B042", "V57-B046"],
        "disposition": (
            "treat_as_one_near_identical_visual_site_candidate_until_"
            "exact_identity_resolution"
        ),
        "evidence": (
            "same Sentinel scene pair and AOI bounds differing by less than one "
            "microdegree; comparison pixels are near-identical but not byte-identical"
        ),
        "unique_site_claim_created": False,
    }
]

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


class SatelliteChangeReviewV4Error(ValueError):
    """Raised when v4 inputs, semantics, or publication fail closed."""


@dataclass(frozen=True, slots=True)
class SatelliteChangeReviewV4Bundle:
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
        raise SatelliteChangeReviewV4Error(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SatelliteChangeReviewV4Error(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise SatelliteChangeReviewV4Error(f"{label} must be a JSON object")
    return value


def _read_pinned_bytes(
    package_root: Path, spec: Mapping[str, Any], label: str
) -> bytes:
    raw = _read_regular(package_root / str(spec["path"]), label)
    if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
        raise SatelliteChangeReviewV4Error(f"{label} checkpoint changed")
    return raw


def _read_pinned_json(
    package_root: Path, spec: Mapping[str, Any], label: str
) -> tuple[dict[str, Any], bytes]:
    raw = _read_pinned_bytes(package_root, spec, label)
    return _json_object(raw, label), raw


def _jsonl_objects(raw: bytes, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise SatelliteChangeReviewV4Error(f"{label} is not UTF-8") from error
    for index, line in enumerate(lines, start=1):
        if not line:
            raise SatelliteChangeReviewV4Error(f"{label} has blank line {index}")
        rows.append(_json_object(line.encode("utf-8"), f"{label} line {index}"))
    return rows


def _tree_inventory(root: Path, label: str) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise SatelliteChangeReviewV4Error(f"{label} must be a regular directory")
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
            raise SatelliteChangeReviewV4Error(
                f"{label} contains a symlink: {relative}"
            )
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            if mode != 0o555:
                raise SatelliteChangeReviewV4Error(
                    f"{label} directory mode changed: {relative} is {mode:04o}"
                )
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
            directories += 1
        elif path.is_file():
            if mode != 0o444:
                raise SatelliteChangeReviewV4Error(
                    f"{label} file mode changed: {relative} is {mode:04o}"
                )
            raw = path.read_bytes()
            digest.update(
                (f"F\0{relative}\0{mode:04o}\0{len(raw)}\0{_sha256(raw)}\n").encode()
            )
            files += 1
            file_bytes += len(raw)
        else:
            raise SatelliteChangeReviewV4Error(
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
        raise SatelliteChangeReviewV4Error(f"{label} closed tree changed")
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
        raise SatelliteChangeReviewV4Error(f"{label} contains a positive claim")


def make_review_definition(package_root: str | Path) -> bytes:
    """Return the canonical v4 definition for the hash-pinned local inputs."""

    Path(package_root).resolve()
    document = {
        "decision_semantics": DECISION_SEMANTICS,
        "format": "datacenter-atlas-satellite-change-review-definition-v4",
        "generated_at": GENERATED_AT,
        "guardrails": GUARDRAILS,
        "near_duplicate_visual_relationships": NEAR_DUPLICATE_RELATIONSHIPS,
        "predecessor_review": {
            "closed_tree": PREDECESSOR_TREE,
            "definition": PREDECESSOR_DEFINITION,
            "manifest": PREDECESSOR_MANIFEST,
            "review_id": PREDECESSOR_REVIEW_ID,
        },
        "review_id": REVIEW_ID,
        "reviewed_at": REVIEWED_AT,
        "schema_version": 4,
        "source_blind_review": BLIND_REVIEW_SOURCE,
        "source_catalog_run": {
            "closed_tree": CATALOG_TREE,
            "manifest": CATALOG_MANIFEST,
        },
        "source_change_preparation": {
            "closed_tree": PREPARATION_TREE,
            "definition": PREPARATION_DEFINITION,
            "manifest": PREPARATION_MANIFEST,
            "single_tile_ready": PREPARATION_SINGLE_TILE,
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
        "special_post_lineage_dispositions": [PENTAPOINT_OVERRIDE],
        "status_observation_policy": STATUS_OBSERVATION_POLICY,
    }
    return _canonical_json(document)


def _validate_definition(
    definition_path: str | Path,
) -> tuple[dict[str, Any], bytes, Path]:
    path = Path(definition_path).resolve()
    package_root = path.parents[2]
    if path != package_root / DEFINITION_PATH:
        raise SatelliteChangeReviewV4Error("review definition publication path changed")
    raw = _read_regular(path, "review definition")
    document = _json_object(raw, "review definition")
    if raw != _canonical_json(document):
        raise SatelliteChangeReviewV4Error("review definition is not canonical JSON")
    if _sha256(raw) != DEFINITION_SHA256:
        raise SatelliteChangeReviewV4Error("review definition content changed")
    expected = _json_object(make_review_definition(package_root), "expected definition")
    if document != expected:
        raise SatelliteChangeReviewV4Error("review definition semantics changed")
    if any(GUARDRAILS.values()) or document.get("guardrails") != GUARDRAILS:
        raise SatelliteChangeReviewV4Error("review guardrails changed")
    if _contains_key(document, "confidence"):
        raise SatelliteChangeReviewV4Error("confidence is forbidden in this review")
    for timestamp in (GENERATED_AT, REVIEWED_AT):
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed > datetime.now(UTC):
            raise SatelliteChangeReviewV4Error("review timestamp is in the future")
    return document, raw, package_root


def _unique_by(rows: list[dict[str, Any]], key: str, label: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for row in rows:
        value = row.get(key)
        if not isinstance(value, str) or value in result:
            raise SatelliteChangeReviewV4Error(f"{label} {key} values changed")
        result[value] = row
    return result


def _validate_blind_review(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    if (
        document.get("artifact_type")
        != "analyst_identity_blind_satellite_change_review_input"
        or document.get("review_id")
        != "2026-07-20-open-seed-v57-active-single-tile-blind-review-v1"
        or document.get("schema_version") != 1
        or document.get("decision_semantics")
        != {
            "R": "reject_imagery_promotion",
            "T": "retain_for_visible_change_follow_up_only",
            "U": "uncertain_due_to_image_quality_or_ambiguous_visible_change",
        }
        or document.get("view_counts") != {"R": 11, "T": 41, "U": 19}
        or document.get("job_counts") != {"R": 11, "T": 44, "U": 19}
        or document.get("near_duplicate_visual_relationships")
        != NEAR_DUPLICATE_RELATIONSHIPS
        or document.get("source_run")
        != {"closed_tree": SOURCE_TREE, "manifest": SOURCE_MANIFEST}
    ):
        raise SatelliteChangeReviewV4Error("blind review contract changed")
    guardrails = document.get("guardrails")
    if not isinstance(guardrails, Mapping) or not guardrails or any(
        value is not False for value in guardrails.values()
    ):
        raise SatelliteChangeReviewV4Error("blind review guardrails changed")
    method = document.get("method", {})
    if (
        method.get("reviewed_views") != 71
        or method.get("independent_reviews") != 2
        or method.get("agreement_views") != 59
        or method.get("disagreement_views") != 12
        or method.get("lineage_unsealed_after_adjudication_sha256_was_fixed")
        is not True
    ):
        raise SatelliteChangeReviewV4Error("blind review method changed")
    rows = document.get("lineage_records")
    if not isinstance(rows, list) or len(rows) != 71:
        raise SatelliteChangeReviewV4Error("blind review view count changed")
    if [row.get("blind_id") for row in rows] != [
        f"V57-B{index:03d}" for index in range(1, 72)
    ]:
        raise SatelliteChangeReviewV4Error("blind review ordering changed")
    if Counter(row.get("visual_verdict") for row in rows) != Counter(
        {"R": 11, "T": 41, "U": 19}
    ):
        raise SatelliteChangeReviewV4Error("blind review verdict counts changed")
    members = [member for row in rows for member in row.get("members", [])]
    if (
        len(members) != 74
        or len({member.get("queue_id") for member in members}) != 74
        or Counter(
            row.get("visual_verdict")
            for row in rows
            for _member in row.get("members", [])
        )
        != Counter({"R": 11, "T": 44, "U": 19})
    ):
        raise SatelliteChangeReviewV4Error("blind review job coverage changed")
    penta = [
        row
        for row in rows
        if any(
            member.get("queue_id") == PENTAPOINT_QUEUE_ID
            for member in row.get("members", [])
        )
    ]
    if len(penta) != 1 or penta[0].get("visual_verdict") != "U":
        raise SatelliteChangeReviewV4Error("PentaPoint visual verdict changed")
    return rows


def _validate_source_report(
    package_root: Path,
    queue_id: str,
    member: Mapping[str, Any],
    source_job: Mapping[str, Any],
) -> dict[str, Any]:
    artifacts = member.get("source_artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != SOURCE_ARTIFACT_NAMES:
        raise SatelliteChangeReviewV4Error(f"source artifact set changed: {queue_id}")
    expected_artifacts = {
        name: {"bytes": spec["bytes"], "sha256": spec["sha256"]}
        for name, spec in artifacts.items()
    }
    if source_job.get("artifacts") != expected_artifacts:
        raise SatelliteChangeReviewV4Error(
            f"source artifact manifest changed: {queue_id}"
        )
    for name, spec in artifacts.items():
        raw = _read_regular(package_root / spec["path"], f"{queue_id} {name}")
        if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
            raise SatelliteChangeReviewV4Error(f"source artifact changed: {queue_id}")
    report_spec = artifacts["report.json"]
    report_raw = _read_regular(
        package_root / report_spec["path"], f"{queue_id} report"
    )
    report = _json_object(report_raw, f"{queue_id} report")
    if report_raw != _canonical_json(report):
        raise SatelliteChangeReviewV4Error(f"source report is not canonical: {queue_id}")
    if (
        report.get("algorithm_version") != "sentinel-2-l2a-change-v2"
        or report.get("entity")
        != {"id": member["entity_id"], "name": member["entity_name"]}
        or source_job.get("report", {}).get("report_sha256")
        != report_spec["sha256"]
    ):
        raise SatelliteChangeReviewV4Error(f"source report lineage changed: {queue_id}")
    _validate_false_claims(report.get("classification", {}), f"{queue_id} report")
    if report.get("outputs") != {
        name: expected_artifacts[name]
        for name in sorted(expected_artifacts)
        if name != "report.json"
    }:
        raise SatelliteChangeReviewV4Error(f"source report outputs changed: {queue_id}")
    return report


def _validate_upstream(
    package_root: Path,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    for spec, label in (
        (QUEUE_TREE, "source queue bundle"),
        (CATALOG_TREE, "source catalog run"),
        (PREPARATION_TREE, "source change preparation"),
        (SOURCE_TREE, "source change run"),
        (PREDECESSOR_TREE, "predecessor review bundle"),
    ):
        _validate_tree(package_root, spec, label)

    blind_review, _ = _read_pinned_json(
        package_root, BLIND_REVIEW_SOURCE, "blind review source"
    )
    rows = _validate_blind_review(blind_review)
    queue_manifest, _ = _read_pinned_json(
        package_root, QUEUE_MANIFEST, "source queue manifest"
    )
    queue_raw = _read_pinned_bytes(package_root, QUEUE_FILE, "source queue file")
    queue_rows = _unique_by(
        _jsonl_objects(queue_raw, "source queue file"), "queue_id", "source queue"
    )
    catalog_manifest, _ = _read_pinned_json(
        package_root, CATALOG_MANIFEST, "source catalog manifest"
    )
    preparation_definition, _ = _read_pinned_json(
        package_root, PREPARATION_DEFINITION, "preparation definition"
    )
    preparation_manifest, _ = _read_pinned_json(
        package_root, PREPARATION_MANIFEST, "preparation manifest"
    )
    ready_raw = _read_pinned_bytes(
        package_root, PREPARATION_SINGLE_TILE, "single-tile preparation rows"
    )
    ready_rows = _unique_by(
        _jsonl_objects(ready_raw, "single-tile preparation rows"),
        "queue_id",
        "single-tile preparation",
    )
    source_manifest, _ = _read_pinned_json(
        package_root, SOURCE_MANIFEST, "source change manifest"
    )
    predecessor_definition, _ = _read_pinned_json(
        package_root, PREDECESSOR_DEFINITION, "predecessor review definition"
    )
    _read_pinned_json(
        package_root, PREDECESSOR_MANIFEST, "predecessor review manifest"
    )

    if (
        queue_manifest.get("pipeline") != "global_satellite_review_queue"
        or queue_manifest.get("counts", {}).get("queue_jobs") != 164
        or queue_manifest.get("artifacts", {})
        .get("satellite-review-queue.jsonl", {})
        .get("sha256")
        != QUEUE_FILE["sha256"]
        or catalog_manifest.get("pipeline") != "satellite_review_catalog_batch"
        or catalog_manifest.get("state") != "completed"
        or catalog_manifest.get("summary", {}).get("jobs_completed") != 85
        or catalog_manifest.get("queue_bundle", {}).get("manifest_sha256")
        != QUEUE_MANIFEST["sha256"]
        or catalog_manifest.get("queue_bundle", {}).get("queue_sha256")
        != QUEUE_FILE["sha256"]
    ):
        raise SatelliteChangeReviewV4Error("queue or catalog lineage changed")
    if (
        preparation_definition.get("preparation_id")
        != "2026-07-20-open-seed-v57-active-change-preparation-v1"
        or preparation_definition.get("expected_partition", {}).get(
            "single_tile_ready"
        )
        != 74
        or preparation_manifest.get("preparation_id")
        != preparation_definition.get("preparation_id")
        or preparation_manifest.get("summary")
        != preparation_definition.get("expected_partition")
        or preparation_manifest.get("definition") != PREPARATION_DEFINITION
        or preparation_manifest.get("artifacts", {})
        .get("single-tile-ready.jsonl", {})
        .get("sha256")
        != PREPARATION_SINGLE_TILE["sha256"]
        or len(ready_rows) != 74
    ):
        raise SatelliteChangeReviewV4Error("preparation lineage changed")
    selected_queue_ids = [
        member["queue_id"] for row in rows for member in row["members"]
    ]
    if (
        source_manifest.get("pipeline") != "satellite_review_change_batch"
        or source_manifest.get("state") != "completed"
        or source_manifest.get("summary", {}).get("jobs_completed") != 74
        or source_manifest.get("summary", {}).get("jobs_selected") != 74
        or source_manifest.get("summary", {}).get("jobs_failed") != 0
        or source_manifest.get("queue_bundle", {}).get("manifest_sha256")
        != QUEUE_MANIFEST["sha256"]
        or source_manifest.get("queue_bundle", {}).get("queue_sha256")
        != QUEUE_FILE["sha256"]
        or source_manifest.get("catalog_batches", [{}])[0].get("manifest_sha256")
        != CATALOG_MANIFEST["sha256"]
        or len(source_manifest.get("selection", {}).get("selected_queue_ids", []))
        != 74
        or set(source_manifest.get("selection", {}).get("selected_queue_ids", []))
        != set(selected_queue_ids)
        or set(ready_rows) != set(selected_queue_ids)
    ):
        raise SatelliteChangeReviewV4Error("source change lineage changed")

    predecessor_penta = {
        row["queue_id"]: row for row in predecessor_definition.get("decisions", [])
    }.get(PENTAPOINT_QUEUE_ID)
    if (
        predecessor_penta is None
        or predecessor_penta.get("decision") != "reject_for_site_promotion"
        or not any(
            "interior-floor fit-out" in observation
            and "10 m optical change cannot be attributed" in observation
            for observation in predecessor_penta.get("observations", [])
        )
    ):
        raise SatelliteChangeReviewV4Error("PentaPoint predecessor limit changed")

    reports: dict[str, dict[str, Any]] = {}
    source_jobs = source_manifest.get("jobs", {})
    catalog_jobs = catalog_manifest.get("jobs", {})
    atlas_as_of = queue_manifest.get("source", {}).get("atlas_as_of")
    if not isinstance(atlas_as_of, str):
        raise SatelliteChangeReviewV4Error("queue atlas_as_of changed")
    for row in rows:
        relationship_id = row["aoi_relationship_id"]
        for member in row["members"]:
            queue_id = member["queue_id"]
            queue_row = queue_rows.get(queue_id)
            catalog_job = catalog_jobs.get(queue_id)
            ready_row = ready_rows.get(queue_id)
            source_job = source_jobs.get(queue_id)
            if not all(
                isinstance(value, Mapping)
                for value in (queue_row, catalog_job, ready_row, source_job)
            ):
                raise SatelliteChangeReviewV4Error(
                    f"missing upstream job lineage: {queue_id}"
                )
            expected_entity = {
                "id": member["entity_id"],
                "name": member["entity_name"],
            }
            if (
                queue_row.get("entity", {}).get("id") != member["entity_id"]
                or queue_row.get("entity", {}).get("name") != member["entity_name"]
                or queue_row.get("entity", {}).get("stable_key")
                != member["stable_key"]
                or catalog_job.get("state") != "completed"
                or catalog_job.get("entity_id") != member["entity_id"]
                or ready_row.get("state") != "single_tile_ready"
                or ready_row.get("aoi_relationship", {}).get("aoi_relationship_id")
                != relationship_id
                or source_job.get("state") != "completed"
                or source_job.get("entity") != expected_entity
                or source_job.get("attempts") != 1
            ):
                raise SatelliteChangeReviewV4Error(
                    f"upstream job semantics changed: {queue_id}"
                )
            freshness = queue_row.get("status_freshness")
            if (
                not isinstance(freshness, Mapping)
                or freshness.get("missing") is not False
                or freshness.get("status_as_of")
                != queue_row.get("entity", {}).get("status_as_of")
                or not isinstance(freshness.get("age_days_at_atlas_as_of"), int)
                or freshness["age_days_at_atlas_as_of"] < 0
            ):
                raise SatelliteChangeReviewV4Error(
                    f"queue status freshness changed: {queue_id}"
                )
            reports[queue_id] = _validate_source_report(
                package_root, queue_id, member, source_job
            )
    return source_manifest, queue_manifest, rows, queue_rows, reports


def _status_metadata(
    queue_row: Mapping[str, Any], queue_manifest: Mapping[str, Any]
) -> dict[str, Any]:
    freshness = queue_row["status_freshness"]
    return {
        "age_days_at_atlas_as_of": freshness["age_days_at_atlas_as_of"],
        "atlas_as_of": queue_manifest["source"]["atlas_as_of"],
        "last_observed_value": queue_row["priority"]["lifecycle_status"],
        "missing": freshness["missing"],
        "queue_input_only": True,
        "status_as_of": freshness["status_as_of"],
    }


def _member_record(
    member: Mapping[str, Any],
    visual_verdict: str,
    queue_row: Mapping[str, Any],
    queue_manifest: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
    report: Mapping[str, Any],
) -> dict[str, Any]:
    queue_id = str(member["queue_id"])
    is_penta = queue_id == PENTAPOINT_QUEUE_ID
    visual_disposition = DECISION_SEMANTICS[visual_verdict]
    final_disposition = (
        PENTAPOINT_OVERRIDE["final_promotion_disposition"]
        if is_penta
        else visual_disposition
    )
    return {
        "authoritative_status_refresh": {
            "completed_by_this_review": False,
            "imagery_can_satisfy_refresh": False,
            "imagery_refresh_performed": False,
            "required_before_treating_last_observation_as_current": True,
        },
        "entity": {
            "id": member["entity_id"],
            "name": member["entity_name"],
            "stable_key": member["stable_key"],
        },
        "input_artifacts": member["source_artifacts"],
        "last_observed_status_metadata": _status_metadata(
            queue_row, queue_manifest
        ),
        "promotion_disposition": final_disposition,
        "promotion_disposition_basis": (
            "predecessor_official_evidence_limit_preserved_not_imagery"
            if is_penta
            else "identity_blind_visual_verdict"
        ),
        "queue_id": queue_id,
        "source_lineage": {
            "algorithm_version": report["algorithm_version"],
            "baseline": {
                key: report["baseline"][key]
                for key in ("datetime", "id", "mgrs_tile", "stac_item_sha256")
            },
            "catalog_manifest": CATALOG_MANIFEST,
            "change_manifest": SOURCE_MANIFEST,
            "current": {
                key: report["current"][key]
                for key in ("datetime", "id", "mgrs_tile", "stac_item_sha256")
            },
            "preparation_manifest": PREPARATION_MANIFEST,
            "queue_manifest": QUEUE_MANIFEST,
            "queue_sha256": QUEUE_FILE["sha256"],
            "report_source": report["source"],
            "source_report_sha256": source_manifest["jobs"][queue_id]["report"][
                "report_sha256"
            ],
        },
        "visual_disposition": visual_disposition,
    }


def _readme_bytes() -> bytes:
    return (
        "# Identity-blind review of v57 single-tile satellite change\n\n"
        "This immutable bundle carries the adjudicated identity-blind visual "
        "review of 71 views covering 74 single-tile jobs. Visual verdicts are "
        "preserved exactly: 41 T, 11 R, and 19 U by view; 44 T, 11 R, and 19 U "
        "by job. T retains an output only for visible-change follow-up, R rejects "
        "imagery promotion, and U is inconclusive.\n\n"
        "PentaPoint BKK-01 remains visually U, while its final promotion "
        "disposition remains reject because predecessor official evidence says "
        "the interior fit-out is unobservable at 10 m. This is an evidence-limit "
        "preservation, not an imagery-derived status decision.\n\n"
        "Every job binds all six frozen source artifacts. The v57 queue, catalog, "
        "change preparation, change run, blind-review input, and predecessor "
        "review are pinned by byte count, SHA-256, and closed-tree inventory where "
        "applicable. Reproduction and validation require no network access.\n\n"
        "Queue status values and ages appear only as dated last-observed metadata. "
        "They are not current status; an authoritative source refresh is required, "
        "and imagery cannot perform or satisfy that refresh.\n\n"
        "B042 and B046 are one near-identical visual-site candidate pending exact "
        "identity resolution, not a unique-site or site-count claim. No imagery "
        "outcome establishes identity, lifecycle, construction or current status, "
        "capacity, energy, data-centre type, operator, workload, or site count.\n"
    ).encode("utf-8")


def _attribution_bytes() -> bytes:
    return (
        "Contains modified Copernicus Sentinel data 2024 and 2026.\n"
        "Catalog: Element 84 Earth Search v1.\n"
        "Dataset: Copernicus Sentinel-2 Level-2A.\n"
        "Source imagery is not copied into this review bundle; exact source "
        "artifacts remain hash-linked under their upstream terms.\n"
    ).encode("utf-8")


def build_satellite_change_review_v4(
    definition_path: str | Path,
) -> SatelliteChangeReviewV4Bundle:
    """Build deterministic v4 bytes from the frozen accepted inputs."""

    definition, definition_raw, package_root = _validate_definition(definition_path)
    source_manifest, queue_manifest, rows, queue_rows, reports = _validate_upstream(
        package_root
    )
    records: list[dict[str, Any]] = []
    for row in rows:
        verdict = row["visual_verdict"]
        record = {
            "aoi_relationship_id": row["aoi_relationship_id"],
            "blind_id": row["blind_id"],
            "decision_scope": "imagery_visible_change_triage_only",
            "members": [
                _member_record(
                    member,
                    verdict,
                    queue_rows[member["queue_id"]],
                    queue_manifest,
                    source_manifest,
                    reports[member["queue_id"]],
                )
                for member in row["members"]
            ],
            "schema_version": 4,
            "source_comparison_sha256": row["source_comparison_sha256"],
            "source_review": BLIND_REVIEW_SOURCE,
            "visual_disposition": DECISION_SEMANTICS[verdict],
            "visual_verdict": verdict,
        }
        records.append(record)
    reviews_bytes = b"".join(_canonical_line(record) for record in records)
    members = [member for record in records for member in record["members"]]
    promotion_counts = dict(
        sorted(Counter(member["promotion_disposition"] for member in members).items())
    )
    summary = {
        "counts": {
            "jobs": 74,
            "source_artifacts_hash_bound": 444,
            "views": 71,
        },
        "decision_semantics": DECISION_SEMANTICS,
        "generated_at": GENERATED_AT,
        "guardrails": GUARDRAILS,
        "job_counts": {"R": 11, "T": 44, "U": 19},
        "near_duplicate_visual_relationships": NEAR_DUPLICATE_RELATIONSHIPS,
        "predecessor_review": definition["predecessor_review"],
        "promotion_disposition_job_counts": promotion_counts,
        "review_id": REVIEW_ID,
        "reviewed_at": REVIEWED_AT,
        "schema_version": 4,
        "source_blind_review": BLIND_REVIEW_SOURCE,
        "source_catalog_run": definition["source_catalog_run"],
        "source_change_preparation": definition["source_change_preparation"],
        "source_change_run": definition["source_change_run"],
        "source_queue_bundle": definition["source_queue_bundle"],
        "special_post_lineage_dispositions": [PENTAPOINT_OVERRIDE],
        "status_observation_policy": STATUS_OBSERVATION_POLICY,
        "view_counts": {"R": 11, "T": 41, "U": 19},
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
        "format": "datacenter-atlas-satellite-change-analyst-review-v4",
        "generated_at": GENERATED_AT,
        "guardrails": GUARDRAILS,
        "job_counts": {"R": 11, "T": 44, "U": 19},
        "near_duplicate_visual_relationships": NEAR_DUPLICATE_RELATIONSHIPS,
        "predecessor_review": definition["predecessor_review"],
        "promotion_disposition_job_counts": promotion_counts,
        "review_id": REVIEW_ID,
        "reviewed_at": REVIEWED_AT,
        "schema_version": 4,
        "source_artifacts": {
            member["queue_id"]: member["input_artifacts"] for member in members
        },
        "source_blind_review": BLIND_REVIEW_SOURCE,
        "source_catalog_run": definition["source_catalog_run"],
        "source_change_preparation": definition["source_change_preparation"],
        "source_change_run": definition["source_change_run"],
        "source_queue_bundle": definition["source_queue_bundle"],
        "special_post_lineage_dispositions": [PENTAPOINT_OVERRIDE],
        "status_observation_policy": STATUS_OBSERVATION_POLICY,
        "view_counts": {"R": 11, "T": 41, "U": 19},
    }
    manifest_bytes = _canonical_json(manifest)
    sidecar_bytes = f"{_sha256(manifest_bytes)}  {MANIFEST_FILENAME}\n".encode(
        "ascii"
    )
    files = {
        **output_files,
        MANIFEST_FILENAME: manifest_bytes,
        MANIFEST_HASH_FILENAME: sidecar_bytes,
    }
    if any(
        _contains_key(value, "confidence") for value in (records, summary, manifest)
    ):
        raise SatelliteChangeReviewV4Error("confidence leaked into review bundle")
    if promotion_counts != {
        "inconclusive": 18,
        "reject_imagery_promotion": 12,
        "retain_for_visible_change_follow_up_only": 44,
    }:
        raise SatelliteChangeReviewV4Error("promotion dispositions changed")
    return SatelliteChangeReviewV4Bundle(files=files, manifest=manifest)


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
        raise SatelliteChangeReviewV4Error(
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
    """Atomically create, but never replace, the canonical v4 definition."""

    root = Path(package_root).resolve()
    destination = Path(output_path).resolve()
    if destination != root / DEFINITION_PATH:
        raise SatelliteChangeReviewV4Error("definition output path changed")
    raw = make_review_definition(root)
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise SatelliteChangeReviewV4Error(
                f"refusing existing output: {destination}"
            )
        stage = destination.parent / f".{destination.name}.{os.getpid()}.tmp"
        try:
            _write_file(stage, raw)
            if destination.exists() or destination.is_symlink():
                raise SatelliteChangeReviewV4Error(
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


def write_satellite_change_review_v4(
    definition_path: str | Path,
    output_path: str | Path,
    *,
    freeze: bool = True,
) -> dict[str, Any]:
    """Atomically publish a frozen v4 review without replacing anything."""

    if freeze is not True:
        raise SatelliteChangeReviewV4Error("review publication requires freeze=True")
    bundle = build_satellite_change_review_v4(definition_path)
    destination = Path(output_path).resolve()
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise SatelliteChangeReviewV4Error(
                f"refusing existing output: {destination}"
            )
        stage = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        try:
            for filename, raw in sorted(bundle.files.items()):
                _write_file(stage / filename, raw)
            if destination.exists() or destination.is_symlink():
                raise SatelliteChangeReviewV4Error(
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


def validate_satellite_change_review_v4(
    output_path: str | Path,
    *,
    definition_path: str | Path,
) -> dict[str, Any]:
    """Offline-reproduce a frozen v4 review byte-for-byte."""

    directory = Path(output_path)
    if directory.is_symlink() or not directory.is_dir():
        raise SatelliteChangeReviewV4Error("review bundle must be a regular directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES:
        raise SatelliteChangeReviewV4Error("review bundle file set changed")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555 or any(
        entry.is_symlink()
        or not entry.is_file()
        or stat.S_IMODE(entry.stat().st_mode) != 0o444
        for entry in entries
    ):
        raise SatelliteChangeReviewV4Error("review bundle must be frozen 0555/0444")
    actual = {
        filename: _read_regular(directory / filename, f"review {filename}")
        for filename in BUNDLE_FILES
    }
    manifest = _json_object(actual[MANIFEST_FILENAME], "review manifest")
    expected_sidecar = (
        f"{_sha256(actual[MANIFEST_FILENAME])}  {MANIFEST_FILENAME}\n".encode("ascii")
    )
    if actual[MANIFEST_HASH_FILENAME] != expected_sidecar:
        raise SatelliteChangeReviewV4Error("review manifest sidecar changed")
    expected = build_satellite_change_review_v4(definition_path)
    if actual != expected.files:
        raise SatelliteChangeReviewV4Error(
            "review bundle differs from offline reconstruction"
        )
    if manifest != expected.manifest:
        raise SatelliteChangeReviewV4Error("review manifest semantics changed")
    return dict(expected.manifest)


__all__ = [
    "BLIND_REVIEW_SOURCE",
    "BUNDLE_FILES",
    "CATALOG_MANIFEST",
    "CATALOG_TREE",
    "DECISION_SEMANTICS",
    "DEFINITION_PATH",
    "DEFINITION_SHA256",
    "GENERATED_AT",
    "GUARDRAILS",
    "NEAR_DUPLICATE_RELATIONSHIPS",
    "OUTPUT_PATH",
    "PENTAPOINT_OVERRIDE",
    "PENTAPOINT_QUEUE_ID",
    "PREPARATION_DEFINITION",
    "PREPARATION_MANIFEST",
    "PREPARATION_SINGLE_TILE",
    "PREPARATION_TREE",
    "QUEUE_FILE",
    "QUEUE_MANIFEST",
    "QUEUE_TREE",
    "REVIEWED_AT",
    "REVIEW_ID",
    "SOURCE_MANIFEST",
    "SOURCE_TREE",
    "STATUS_OBSERVATION_POLICY",
    "SatelliteChangeReviewV4Bundle",
    "SatelliteChangeReviewV4Error",
    "build_satellite_change_review_v4",
    "make_review_definition",
    "validate_satellite_change_review_v4",
    "write_review_definition",
    "write_satellite_change_review_v4",
]
