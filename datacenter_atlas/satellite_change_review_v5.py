"""Immutable carrier for the six-job singleton alternate-view review.

The review binds an identity-blind visual adjudication to the frozen singleton
preparation and run.  It carries visible-change triage only.  It does not
create or update atlas, identity, lifecycle, current-status, construction,
capacity, power, energy, PUE, type, operator, workload, or site-count facts.
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


REVIEW_ID = "2026-07-20-open-seed-v57-active-singleton-review-v1"
BLIND_REVIEW_ID = (
    "2026-07-20-open-seed-v57-active-singleton-blind-review-v1"
)
GENERATED_AT = "2026-07-21T04:01:00Z"
REVIEWED_AT = "2026-07-21T04:01:00Z"
DEFINITION_PATH = (
    "definitions/satellite_change_reviews/"
    "2026-07-20-open-seed-v57-active-singleton-review-v1.json"
)
OUTPUT_PATH = f"satellite_change_reviews/{REVIEW_ID}"
DEFINITION_SHA256 = (
    "262fb0f6716f6948eb81835c77a34a22e79eca592c9c83f748fb2820b6fcdb04"
)

BLIND_REVIEW_SOURCE = {
    "bytes": 11_630,
    "path": (
        "sources/satellite-change-blind-review-2026-07-20-"
        "open-seed-v57-singleton-v2.json"
    ),
    "sha256": "94927f4ef2d12f6c4e696fd624c35dc1a0506d1d3fe2ac062481a8ea80905124",
}

PREPARATION_PATH = (
    "satellite_change_preparation/"
    "2026-07-20-open-seed-v57-active-singleton-v2"
)
PREPARATION_DEFINITION = {
    "bytes": 9_822,
    "path": (
        "sources/satellite-change-singleton-preparation-2026-07-20-"
        "open-seed-v57-active-v2.json"
    ),
    "sha256": "a99b9ee8e96d7cf9a4edc079b1f48afe21152a6332428dbeba9fbfbd28dcaa67",
}
PREPARATION_MANIFEST = {
    "bytes": 4_847,
    "path": f"{PREPARATION_PATH}/manifest.json",
    "sha256": "def22b2a8db66c66515c91f1143c86f95b7e1905e1175304294e72c6b45f0183",
}
PREPARATION_PARTITION = {
    "bytes": 76_264,
    "path": f"{PREPARATION_PATH}/singleton-ready.jsonl",
    "records": 6,
    "sha256": "338b04682cceaaf87b76a795531855c38b480cbeeda837e68bc893adcbcd1b1e",
}
PREPARATION_TREE = {
    "directories": 1,
    "directory_mode": "0555",
    "file_bytes": 86_195,
    "file_mode": "0444",
    "files": 7,
    "inventory_sha256": "da4a864024ba7ff800a3f81a322d0040bb72c52ee45742bdcc9f7b36133de6b7",
    "path": PREPARATION_PATH,
    "schema_version": 1,
}

SOURCE_RUN_PATH = (
    "satellite_change_runs/"
    "2026-07-20-open-seed-v57-active-singleton-v2-001"
)
SOURCE_MANIFEST = {
    "bytes": 43_152,
    "path": f"{SOURCE_RUN_PATH}/batch-manifest.json",
    "sha256": "8099230c183bdf4fc39e32c132f7667d011aef728e2727f2e89368e0447d9cfd",
}
SOURCE_FREEZE = {
    "bytes": 11_358,
    "path": f"{SOURCE_RUN_PATH}/freeze.json",
    "sha256": "f44677ffd37fbd753ccb7ea87dc2173d893444df350ab977c0a205e011898adc",
}
SOURCE_FREEZE_SHA256 = {
    "bytes": 78,
    "path": f"{SOURCE_RUN_PATH}/freeze.sha256",
    "sha256": "6408b0997f5d5d79aaad10cff07776da9a2564d6995a8962af2bbe0521cdeff5",
}
SOURCE_PRODUCTION_TREE = {
    "directories": 13,
    "file_bytes": 10_730_021,
    "files": 37,
    "inventory_sha256": "8de0d2ebfd8d8afb40fbf0451e32e7f0b13a0cd181fedc1cdd47052225542259",
}
SOURCE_TREE = {
    "directories": 14,
    "directory_mode": "0555",
    "file_bytes": 10_741_457,
    "file_mode": "0444",
    "files": 39,
    "inventory_sha256": "7d731b920b07bd98f4609e823315a7715b6d2b045fa80248de1f75e9131e72a9",
    "path": SOURCE_RUN_PATH,
    "schema_version": 1,
}
SOURCE_REPLAY = {
    "artifact_inventory_sha256": (
        "9e68a00c8863bbca07e3d3e8429f8a758a6b2e7b9e7b3682f4b0964eea00d351"
    ),
    "artifacts_compared": 36,
    "jobs_replayed": 6,
    "status": "verified_byte_identical",
    "verified_at": "2026-07-21T03:42:13Z",
}

EXPECTED_QUEUE_IDS = (
    "satq-0ffe3647dc32ee25ef77eab7",
    "satq-54c6402eb93d14f1ea754e66",
    "satq-78500568b1f6227789ae36f4",
    "satq-96fca962064e09f0dbafa93b",
    "satq-cef871428da247c3ecfadec6",
    "satq-fb6b6f815dad079c059cf412",
)
EXPECTED_VERDICTS = {
    "satq-0ffe3647dc32ee25ef77eab7": "U",
    "satq-54c6402eb93d14f1ea754e66": "T",
    "satq-78500568b1f6227789ae36f4": "R",
    "satq-96fca962064e09f0dbafa93b": "T",
    "satq-cef871428da247c3ecfadec6": "T",
    "satq-fb6b6f815dad079c059cf412": "T",
}
DECISION_SEMANTICS = {
    "R": "reject_imagery_promotion",
    "T": "retain_for_visible_change_follow_up_only",
    "U": "inconclusive",
}
ALTERNATE_VIEW_SEMANTICS = {
    "catalog_rediscovery": False,
    "catalog_reranking": False,
    "description": (
        "alternate valid singleton tile view for six preselected queue jobs"
    ),
    "prior_failed_mosaic_outputs_reused": False,
    "queue_jobs_preselected_before_this_review": True,
    "selected_items_per_epoch": 1,
    "successor_selection_not_retry": True,
}
STATUS_OBSERVATION_POLICY = {
    "authoritative_refresh_completed_by_review": False,
    "imagery_can_satisfy_authoritative_status_refresh": False,
    "status_metadata_carried_into_review": False,
    "status_refresh_performed": False,
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

VISUAL_ARTIFACT_NAMES = frozenset(
    {"after.png", "before.png", "change-overlay.png", "comparison.png"}
)
SOURCE_ARTIFACT_NAMES = frozenset(
    {
        *VISUAL_ARTIFACT_NAMES,
        "change-proposals.geojson",
        "report.json",
    }
)
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


class SatelliteChangeReviewV5Error(ValueError):
    """Raised when v5 inputs, review semantics, or publication drift."""


@dataclass(frozen=True, slots=True)
class SatelliteChangeReviewV5Bundle:
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
        raise SatelliteChangeReviewV5Error(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SatelliteChangeReviewV5Error(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise SatelliteChangeReviewV5Error(f"{label} must be a JSON object")
    return value


def _read_pinned_bytes(
    package_root: Path, spec: Mapping[str, Any], label: str
) -> bytes:
    raw = _read_regular(package_root / str(spec["path"]), label)
    if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
        raise SatelliteChangeReviewV5Error(f"{label} checkpoint changed")
    return raw


def _read_pinned_json(
    package_root: Path, spec: Mapping[str, Any], label: str
) -> tuple[dict[str, Any], bytes]:
    raw = _read_pinned_bytes(package_root, spec, label)
    document = _json_object(raw, label)
    if raw != _canonical_json(document):
        raise SatelliteChangeReviewV5Error(f"{label} is not canonical JSON")
    return document, raw


def _tree_inventory(root: Path, label: str) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise SatelliteChangeReviewV5Error(f"{label} must be a regular directory")
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
            raise SatelliteChangeReviewV5Error(
                f"{label} contains a symlink: {relative}"
            )
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            if mode != 0o555:
                raise SatelliteChangeReviewV5Error(
                    f"{label} directory mode changed: {relative} is {mode:04o}"
                )
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
            directories += 1
        elif path.is_file():
            if mode != 0o444:
                raise SatelliteChangeReviewV5Error(
                    f"{label} file mode changed: {relative} is {mode:04o}"
                )
            raw = path.read_bytes()
            digest.update(
                (f"F\0{relative}\0{mode:04o}\0{len(raw)}\0{_sha256(raw)}\n").encode()
            )
            files += 1
            file_bytes += len(raw)
        else:
            raise SatelliteChangeReviewV5Error(
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
        raise SatelliteChangeReviewV5Error(f"{label} closed tree changed")
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
        raise SatelliteChangeReviewV5Error(f"{label} contains a positive claim")


def make_review_definition(package_root: str | Path) -> bytes:
    """Return the canonical v5 definition for the pinned singleton inputs."""

    Path(package_root).resolve()
    document = {
        "alternate_view_semantics": ALTERNATE_VIEW_SEMANTICS,
        "decision_semantics": DECISION_SEMANTICS,
        "format": "datacenter-atlas-satellite-change-review-definition-v5",
        "generated_at": GENERATED_AT,
        "guardrails": GUARDRAILS,
        "review_id": REVIEW_ID,
        "reviewed_at": REVIEWED_AT,
        "schema_version": 5,
        "source_blind_review": BLIND_REVIEW_SOURCE,
        "source_change_preparation": {
            "closed_tree": PREPARATION_TREE,
            "definition": PREPARATION_DEFINITION,
            "manifest": PREPARATION_MANIFEST,
            "partition": PREPARATION_PARTITION,
        },
        "source_change_run": {
            "closed_tree": SOURCE_TREE,
            "freeze_manifest": SOURCE_FREEZE,
            "freeze_sha256": SOURCE_FREEZE_SHA256,
            "manifest": SOURCE_MANIFEST,
            "production_tree": SOURCE_PRODUCTION_TREE,
            "replay": SOURCE_REPLAY,
            "run_input_definition": PREPARATION_DEFINITION,
        },
        "status_observation_policy": STATUS_OBSERVATION_POLICY,
    }
    return _canonical_json(document)


def _validate_definition(
    definition_path: str | Path,
) -> tuple[dict[str, Any], bytes, Path]:
    path = Path(definition_path).resolve()
    package_root = path.parents[2]
    if path != package_root / DEFINITION_PATH:
        raise SatelliteChangeReviewV5Error("review definition publication path changed")
    raw = _read_regular(path, "review definition")
    document = _json_object(raw, "review definition")
    if raw != _canonical_json(document):
        raise SatelliteChangeReviewV5Error("review definition is not canonical JSON")
    if _sha256(raw) != DEFINITION_SHA256:
        raise SatelliteChangeReviewV5Error("review definition content changed")
    expected = _json_object(make_review_definition(package_root), "expected definition")
    if document != expected:
        raise SatelliteChangeReviewV5Error("review definition semantics changed")
    if any(GUARDRAILS.values()) or document.get("guardrails") != GUARDRAILS:
        raise SatelliteChangeReviewV5Error("review guardrails changed")
    for timestamp in (GENERATED_AT, REVIEWED_AT):
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed > datetime.now(UTC):
            raise SatelliteChangeReviewV5Error("review timestamp is in the future")
    return document, raw, package_root


def _validate_blind_review(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    if (
        document.get("artifact_type")
        != "analyst_identity_blind_satellite_change_review_input"
        or document.get("review_id") != BLIND_REVIEW_ID
        or document.get("schema_version") != 1
        or document.get("decision_semantics") != DECISION_SEMANTICS
        or document.get("guardrails") != GUARDRAILS
        or document.get("job_counts") != {"R": 1, "T": 4, "U": 1}
        or document.get("view_counts") != {"R": 1, "T": 4, "U": 1}
        or document.get("source_view_semantics") != ALTERNATE_VIEW_SEMANTICS
    ):
        raise SatelliteChangeReviewV5Error("blind review contract changed")
    method = document.get("method")
    if not isinstance(method, Mapping) or method != {
        "analyst_reviews": 1,
        "blind_guard": (
            "The analyst used only neutral blind IDs and the comparison, before, "
            "after, and change-overlay rasters."
        ),
        "lineage_unsealed_after_visual_verdicts_were_fixed": True,
        "metadata_excluded_until_after_verdict_fixing": [
            "capacity",
            "current_status",
            "data_centre_type",
            "entity_identity",
            "lifecycle",
            "operator",
            "power",
            "pue",
            "queue_priority",
            "report_metrics",
            "workload",
        ],
        "reviewed_jobs": 6,
        "visual_artifacts_inspected_per_job": 4,
    }:
        raise SatelliteChangeReviewV5Error("blind review method changed")
    rows = document.get("lineage_records")
    if not isinstance(rows, list) or len(rows) != 6:
        raise SatelliteChangeReviewV5Error("blind review job count changed")
    if [row.get("blind_id") for row in rows] != [
        f"V57-S{index:03d}" for index in range(1, 7)
    ]:
        raise SatelliteChangeReviewV5Error("blind review ordering changed")
    if tuple(row.get("queue_id") for row in rows) != EXPECTED_QUEUE_IDS:
        raise SatelliteChangeReviewV5Error("blind review queue coverage changed")
    if Counter(row.get("visual_verdict") for row in rows) != Counter(
        {"T": 4, "R": 1, "U": 1}
    ):
        raise SatelliteChangeReviewV5Error("blind review verdict counts changed")
    for row in rows:
        queue_id = row["queue_id"]
        if row.get("visual_verdict") != EXPECTED_VERDICTS[queue_id]:
            raise SatelliteChangeReviewV5Error(
                f"blind review verdict changed: {queue_id}"
            )
        observations = row.get("visual_observations")
        if (
            not isinstance(observations, list)
            or len(observations) != 2
            or any(not isinstance(value, str) or not value for value in observations)
        ):
            raise SatelliteChangeReviewV5Error(
                f"blind review observations changed: {queue_id}"
            )
        artifacts = row.get("source_visual_artifacts")
        if not isinstance(artifacts, Mapping) or set(artifacts) != (
            VISUAL_ARTIFACT_NAMES
        ):
            raise SatelliteChangeReviewV5Error(
                f"blind review visual artifact set changed: {queue_id}"
            )
    return rows


def _validate_upstream(
    package_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    _validate_tree(package_root, PREPARATION_TREE, "source singleton preparation")
    _validate_tree(package_root, SOURCE_TREE, "source singleton run")
    blind_review, _ = _read_pinned_json(
        package_root, BLIND_REVIEW_SOURCE, "blind review source"
    )
    rows = _validate_blind_review(blind_review)
    preparation_definition, _ = _read_pinned_json(
        package_root, PREPARATION_DEFINITION, "preparation definition"
    )
    preparation_manifest, _ = _read_pinned_json(
        package_root, PREPARATION_MANIFEST, "preparation manifest"
    )
    partition_raw = _read_pinned_bytes(
        package_root, PREPARATION_PARTITION, "preparation singleton partition"
    )
    source_manifest, _ = _read_pinned_json(
        package_root, SOURCE_MANIFEST, "source singleton manifest"
    )
    source_freeze, source_freeze_raw = _read_pinned_json(
        package_root, SOURCE_FREEZE, "source singleton freeze"
    )
    freeze_sha_raw = _read_pinned_bytes(
        package_root, SOURCE_FREEZE_SHA256, "source singleton freeze sidecar"
    )
    if freeze_sha_raw != (
        f"{_sha256(source_freeze_raw)}  freeze.json\n".encode("ascii")
    ):
        raise SatelliteChangeReviewV5Error("source singleton freeze sidecar changed")

    try:
        from .satellite_change_singleton_batch_v2 import (
            validate_satellite_change_singleton_batch_v2,
        )
        from .satellite_change_singleton_preparation_v2 import (
            validate_satellite_change_singleton_preparation_v2,
        )

        validated_preparation = validate_satellite_change_singleton_preparation_v2(
            package_root / PREPARATION_PATH,
            definition_path=package_root / PREPARATION_DEFINITION["path"],
        )
        validated_run = validate_satellite_change_singleton_batch_v2(
            package_root / PREPARATION_PATH,
            package_root / SOURCE_RUN_PATH,
            definition_path=package_root / PREPARATION_DEFINITION["path"],
            require_frozen=True,
        )
    except Exception as error:
        raise SatelliteChangeReviewV5Error(
            f"singleton predecessor validation failed: {error}"
        ) from error
    if validated_preparation != preparation_manifest or validated_run != source_manifest:
        raise SatelliteChangeReviewV5Error("singleton predecessor semantics changed")

    if (
        preparation_definition.get("preparation_id")
        != "2026-07-20-open-seed-v57-active-singleton-reselection-preparation-v2"
        or preparation_manifest.get("summary")
        != {
            "candidate_bindings_assessed": 24,
            "catalog_rediscoveries": 0,
            "catalog_rerankings": 0,
            "jobs_ready": 6,
            "prior_companions_rebound_as_primary": 12,
            "source_multi_tile_rows": 6,
            "unique_singleton_pairs": 6,
        }
        or len(partition_raw.decode("utf-8").splitlines()) != 6
    ):
        raise SatelliteChangeReviewV5Error("singleton preparation contract changed")
    if (
        source_manifest.get("format")
        != "datacenter-atlas-satellite-change-singleton-batch-v2"
        or source_manifest.get("pipeline")
        != "satellite_review_change_singleton_batch_v2"
        or source_manifest.get("schema_version") != 2
        or source_manifest.get("state") != "completed"
        or source_manifest.get("summary")
        != {
            "jobs_completed": 6,
            "jobs_failed": 0,
            "jobs_pending": 0,
            "jobs_running": 0,
            "jobs_selected": 6,
            "output_artifacts": 36,
        }
        or source_manifest.get("determinism") != SOURCE_REPLAY
        or set(source_manifest.get("selection", {}).get("queue_ids", []))
        != set(EXPECTED_QUEUE_IDS)
        or source_manifest.get("selection", {}).get("selected_items_per_epoch") != 1
        or source_manifest.get("preparation", {}).get("definition")
        != PREPARATION_DEFINITION
        or source_manifest.get("preparation", {}).get("manifest")
        != PREPARATION_MANIFEST
        or source_manifest.get("preparation", {}).get("partition")
        != PREPARATION_PARTITION
    ):
        raise SatelliteChangeReviewV5Error("singleton source run contract changed")
    scope = source_manifest.get("scope")
    if (
        not isinstance(scope, Mapping)
        or scope.get("catalog_rediscovery") is not False
        or scope.get("catalog_reranking") is not False
        or scope.get("selected_items_per_epoch") != 1
        or scope.get("automated_promotion_allowed") is not False
        or scope.get("atlas_mutation") is not False
        or any(
            value is not False
            for key, value in scope.items()
            if key.startswith("imagery_") and key.endswith("_inference")
        )
    ):
        raise SatelliteChangeReviewV5Error("singleton source run scope changed")
    freeze_inventory = source_freeze.get("inventory")
    if (
        not isinstance(freeze_inventory, Mapping)
        or {
            key: freeze_inventory.get(key) for key in SOURCE_PRODUCTION_TREE
        }
        != SOURCE_PRODUCTION_TREE
        or source_freeze.get("manifest")
        != {
            "path": "batch-manifest.json",
            **{key: SOURCE_MANIFEST[key] for key in ("bytes", "sha256")},
        }
    ):
        raise SatelliteChangeReviewV5Error("singleton source freeze changed")

    source_jobs = source_manifest.get("jobs")
    if not isinstance(source_jobs, Mapping) or set(source_jobs) != set(
        EXPECTED_QUEUE_IDS
    ):
        raise SatelliteChangeReviewV5Error("singleton source job inventory changed")
    reports: dict[str, dict[str, Any]] = {}
    for row in rows:
        queue_id = row["queue_id"]
        source_job = source_jobs[queue_id]
        artifacts = source_job.get("artifacts")
        if (
            source_job.get("state") != "completed"
            or source_job.get("queue_id") != queue_id
            or not isinstance(artifacts, Mapping)
            or set(artifacts) != SOURCE_ARTIFACT_NAMES
        ):
            raise SatelliteChangeReviewV5Error(
                f"singleton source job changed: {queue_id}"
            )
        expected_visual = row["source_visual_artifacts"]
        for name, spec in artifacts.items():
            path = (
                package_root
                / SOURCE_RUN_PATH
                / "jobs"
                / queue_id
                / "change"
                / name
            )
            raw = _read_regular(path, f"{queue_id} {name}")
            if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
                raise SatelliteChangeReviewV5Error(
                    f"singleton source artifact changed: {queue_id}/{name}"
                )
            if name in VISUAL_ARTIFACT_NAMES:
                expected = {
                    "bytes": spec["bytes"],
                    "path": path.relative_to(package_root).as_posix(),
                    "sha256": spec["sha256"],
                }
                if expected_visual.get(name) != expected:
                    raise SatelliteChangeReviewV5Error(
                        f"blind visual binding changed: {queue_id}/{name}"
                    )
        report_path = (
            package_root
            / SOURCE_RUN_PATH
            / "jobs"
            / queue_id
            / "change"
            / "report.json"
        )
        report_raw = _read_regular(report_path, f"{queue_id} report")
        report = _json_object(report_raw, f"{queue_id} report")
        if report_raw != _canonical_json(report):
            raise SatelliteChangeReviewV5Error(
                f"singleton source report is not canonical: {queue_id}"
            )
        if (
            report.get("algorithm_version") != "sentinel-2-l2a-change-mosaic-v3"
            or source_job.get("report", {}).get("report_sha256")
            != artifacts["report.json"]["sha256"]
        ):
            raise SatelliteChangeReviewV5Error(
                f"singleton source report lineage changed: {queue_id}"
            )
        classification = report.get("classification")
        if not isinstance(classification, Mapping):
            raise SatelliteChangeReviewV5Error(
                f"singleton source classification changed: {queue_id}"
            )
        _validate_false_claims(classification, f"{queue_id} report")
        reports[queue_id] = report
    return source_manifest, rows, reports


def _artifact_bindings(
    package_root: Path, source_manifest: Mapping[str, Any], queue_id: str
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, spec in sorted(source_manifest["jobs"][queue_id]["artifacts"].items()):
        result[name] = {
            "bytes": spec["bytes"],
            "path": (
                Path(SOURCE_RUN_PATH) / "jobs" / queue_id / "change" / name
            ).as_posix(),
            "sha256": spec["sha256"],
        }
        if not (package_root / result[name]["path"]).is_file():
            raise SatelliteChangeReviewV5Error(
                f"singleton artifact disappeared: {queue_id}/{name}"
            )
    return result


def _readme_bytes() -> bytes:
    return (
        "# Identity-blind review of six v57 singleton alternate views\n\n"
        "This immutable v5 bundle carries one analyst's identity-blind visual "
        "review of six alternate valid singleton tile views for six queue jobs "
        "that were selected before review. The fixed verdicts are four T, one R, "
        "and one U. T retains imagery only for visible-change follow-up, R rejects "
        "imagery promotion, and U is inconclusive.\n\n"
        "The analyst inspected comparison, before, after, and change-overlay "
        "rasters under neutral blind IDs. Identity, operator, status, lifecycle, "
        "type, capacity, power, PUE, energy, workload, queue priority, and report "
        "metrics remained sealed until all six visual verdicts were fixed.\n\n"
        "The preparation definition, preparation manifest and tree, singleton run "
        "manifest, frozen production tree, complete frozen tree, and byte-identical "
        "replay digest are pinned exactly. The failed mosaic run was not reused; "
        "the singleton selection is a successor selection, not a retry.\n\n"
        "No review result creates identity, lifecycle, current or construction "
        "status, data-centre type, capacity, power, energy, PUE, operator, workload, "
        "unique-site, or site-count facts. Nothing is promoted automatically and "
        "the atlas is not mutated.\n"
    ).encode("utf-8")


def _attribution_bytes() -> bytes:
    return (
        "Contains modified Copernicus Sentinel data 2024 and 2026.\n"
        "Catalog: Element 84 Earth Search v1.\n"
        "Dataset: Copernicus Sentinel-2 Level-2A.\n"
        "Source imagery is not copied into this review bundle; exact source "
        "artifacts remain hash-linked under their upstream terms.\n"
    ).encode("utf-8")


def build_satellite_change_review_v5(
    definition_path: str | Path,
) -> SatelliteChangeReviewV5Bundle:
    """Build deterministic v5 bytes from the frozen singleton inputs."""

    definition, definition_raw, package_root = _validate_definition(definition_path)
    source_manifest, rows, reports = _validate_upstream(package_root)
    records: list[dict[str, Any]] = []
    for row in rows:
        queue_id = row["queue_id"]
        verdict = row["visual_verdict"]
        record = {
            "alternate_view_semantics": ALTERNATE_VIEW_SEMANTICS,
            "blind_id": row["blind_id"],
            "decision_scope": "imagery_visible_change_triage_only",
            "input_artifacts": _artifact_bindings(
                package_root, source_manifest, queue_id
            ),
            "promotion_disposition": DECISION_SEMANTICS[verdict],
            "promotion_disposition_basis": "identity_blind_visual_verdict",
            "queue_id": queue_id,
            "schema_version": 5,
            "source_lineage": {
                "change_manifest": SOURCE_MANIFEST,
                "freeze_manifest": SOURCE_FREEZE,
                "preparation_definition": PREPARATION_DEFINITION,
                "preparation_manifest": PREPARATION_MANIFEST,
                "replay": SOURCE_REPLAY,
                "source_report_sha256": source_manifest["jobs"][queue_id][
                    "report"
                ]["report_sha256"],
                "visual_algorithm_version": reports[queue_id]["algorithm_version"],
            },
            "source_review": BLIND_REVIEW_SOURCE,
            "visual_artifacts_inspected": sorted(VISUAL_ARTIFACT_NAMES),
            "visual_disposition": DECISION_SEMANTICS[verdict],
            "visual_observations": row["visual_observations"],
            "visual_verdict": verdict,
        }
        records.append(record)
    reviews_bytes = b"".join(_canonical_line(record) for record in records)
    counts = dict(sorted(Counter(row["visual_verdict"] for row in records).items()))
    promotion_counts = dict(
        sorted(Counter(row["promotion_disposition"] for row in records).items())
    )
    summary = {
        "alternate_view_semantics": ALTERNATE_VIEW_SEMANTICS,
        "counts": {
            "jobs": 6,
            "source_artifacts_hash_bound": 36,
            "views": 6,
            "visual_artifacts_inspected": 24,
        },
        "decision_semantics": DECISION_SEMANTICS,
        "generated_at": GENERATED_AT,
        "guardrails": GUARDRAILS,
        "promotion_disposition_job_counts": promotion_counts,
        "review_id": REVIEW_ID,
        "reviewed_at": REVIEWED_AT,
        "schema_version": 5,
        "source_blind_review": BLIND_REVIEW_SOURCE,
        "source_change_preparation": definition["source_change_preparation"],
        "source_change_run": definition["source_change_run"],
        "status_observation_policy": STATUS_OBSERVATION_POLICY,
        "view_counts": counts,
    }
    output_files = {
        ATTRIBUTION_FILENAME: _attribution_bytes(),
        README_FILENAME: _readme_bytes(),
        REVIEWS_FILENAME: reviews_bytes,
        SUMMARY_FILENAME: _canonical_json(summary),
    }
    manifest = {
        "alternate_view_semantics": ALTERNATE_VIEW_SEMANTICS,
        "artifacts": {
            filename: {"bytes": len(raw), "sha256": _sha256(raw)}
            for filename, raw in sorted(output_files.items())
        },
        "definition": {
            "bytes": len(definition_raw),
            "path": DEFINITION_PATH,
            "sha256": _sha256(definition_raw),
        },
        "format": "datacenter-atlas-satellite-change-analyst-review-v5",
        "generated_at": GENERATED_AT,
        "guardrails": GUARDRAILS,
        "promotion_disposition_job_counts": promotion_counts,
        "review_id": REVIEW_ID,
        "reviewed_at": REVIEWED_AT,
        "schema_version": 5,
        "source_artifacts": {
            record["queue_id"]: record["input_artifacts"] for record in records
        },
        "source_blind_review": BLIND_REVIEW_SOURCE,
        "source_change_preparation": definition["source_change_preparation"],
        "source_change_run": definition["source_change_run"],
        "status_observation_policy": STATUS_OBSERVATION_POLICY,
        "view_counts": counts,
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
    if promotion_counts != {
        "inconclusive": 1,
        "reject_imagery_promotion": 1,
        "retain_for_visible_change_follow_up_only": 4,
    }:
        raise SatelliteChangeReviewV5Error("promotion dispositions changed")
    for forbidden in (
        "capacity",
        "current_status",
        "data_centre_type",
        "entity",
        "lifecycle_status",
        "operator",
        "power",
        "pue",
        "site_count",
        "workload",
    ):
        if _contains_key(records, forbidden):
            raise SatelliteChangeReviewV5Error(
                f"forbidden review fact leaked: {forbidden}"
            )
    return SatelliteChangeReviewV5Bundle(files=files, manifest=manifest)


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
        raise SatelliteChangeReviewV5Error(
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
    """Atomically create, but never replace, the canonical v5 definition."""

    root = Path(package_root).resolve()
    destination = Path(output_path).resolve()
    if destination != root / DEFINITION_PATH:
        raise SatelliteChangeReviewV5Error("definition output path changed")
    raw = make_review_definition(root)
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise SatelliteChangeReviewV5Error(
                f"refusing existing output: {destination}"
            )
        stage = destination.parent / f".{destination.name}.{os.getpid()}.tmp"
        try:
            _write_file(stage, raw)
            if destination.exists() or destination.is_symlink():
                raise SatelliteChangeReviewV5Error(
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


def write_satellite_change_review_v5(
    definition_path: str | Path,
    output_path: str | Path,
    *,
    freeze: bool = True,
) -> dict[str, Any]:
    """Atomically publish a frozen v5 review without replacing anything."""

    if freeze is not True:
        raise SatelliteChangeReviewV5Error("review publication requires freeze=True")
    bundle = build_satellite_change_review_v5(definition_path)
    destination = Path(output_path).resolve()
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise SatelliteChangeReviewV5Error(
                f"refusing existing output: {destination}"
            )
        stage = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        try:
            for filename, raw in sorted(bundle.files.items()):
                _write_file(stage / filename, raw)
            if destination.exists() or destination.is_symlink():
                raise SatelliteChangeReviewV5Error(
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


def validate_satellite_change_review_v5(
    output_path: str | Path,
    *,
    definition_path: str | Path,
) -> dict[str, Any]:
    """Offline-reproduce a frozen v5 review byte-for-byte."""

    directory = Path(output_path)
    if directory.is_symlink() or not directory.is_dir():
        raise SatelliteChangeReviewV5Error("review bundle must be a regular directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES:
        raise SatelliteChangeReviewV5Error("review bundle file set changed")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555 or any(
        entry.is_symlink()
        or not entry.is_file()
        or stat.S_IMODE(entry.stat().st_mode) != 0o444
        for entry in entries
    ):
        raise SatelliteChangeReviewV5Error("review bundle must be frozen 0555/0444")
    actual = {
        filename: _read_regular(directory / filename, f"review {filename}")
        for filename in BUNDLE_FILES
    }
    expected_sidecar = (
        f"{_sha256(actual[MANIFEST_FILENAME])}  {MANIFEST_FILENAME}\n".encode("ascii")
    )
    if actual[MANIFEST_HASH_FILENAME] != expected_sidecar:
        raise SatelliteChangeReviewV5Error("review manifest sidecar changed")
    expected = build_satellite_change_review_v5(definition_path)
    if actual != expected.files:
        raise SatelliteChangeReviewV5Error(
            "review bundle differs from offline reconstruction"
        )
    manifest = _json_object(actual[MANIFEST_FILENAME], "review manifest")
    if manifest != expected.manifest:
        raise SatelliteChangeReviewV5Error("review manifest semantics changed")
    return dict(expected.manifest)


__all__ = [
    "ALTERNATE_VIEW_SEMANTICS",
    "BLIND_REVIEW_ID",
    "BLIND_REVIEW_SOURCE",
    "BUNDLE_FILES",
    "DECISION_SEMANTICS",
    "DEFINITION_PATH",
    "DEFINITION_SHA256",
    "EXPECTED_QUEUE_IDS",
    "EXPECTED_VERDICTS",
    "GENERATED_AT",
    "GUARDRAILS",
    "OUTPUT_PATH",
    "PREPARATION_DEFINITION",
    "PREPARATION_MANIFEST",
    "PREPARATION_PARTITION",
    "PREPARATION_TREE",
    "REVIEWED_AT",
    "REVIEW_ID",
    "SOURCE_FREEZE",
    "SOURCE_FREEZE_SHA256",
    "SOURCE_MANIFEST",
    "SOURCE_PRODUCTION_TREE",
    "SOURCE_REPLAY",
    "SOURCE_TREE",
    "STATUS_OBSERVATION_POLICY",
    "SatelliteChangeReviewV5Bundle",
    "SatelliteChangeReviewV5Error",
    "build_satellite_change_review_v5",
    "make_review_definition",
    "validate_satellite_change_review_v5",
    "write_review_definition",
    "write_satellite_change_review_v5",
]
