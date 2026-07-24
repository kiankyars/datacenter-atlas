"""Frozen review checkpoint for the accepted Unknown034 catalog delta.

The carrier proves the exact ordered 22-pair catalog increment, deduplicates
only byte-identical AOI/scene-pair review keys, binds 21 completed algorithm-v2
comparisons plus one typed native-window blocker, and publishes visual
dispositions without creating any atlas or imagery-derived facility fact.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
from typing import Any, Mapping


REVIEW_ID = "2026-07-21-global-open-v3-unknown-034-delta-review-v1"
DEFINITION_PATH = Path(
    "definitions/satellite_change_reviews/"
    "2026-07-21-global-open-v3-unknown-034-delta-review-v1.json"
)
OUTPUT_PATH = Path("satellite_change_reviews") / REVIEW_ID
DEFINITION_SHA256 = "66c382bc6d0e8ff43bec25209a37968c2c4f685b6cacdfd78f29b85c53002a1a"

MANIFEST_FILENAME = "review-manifest.json"
SIDECAR_FILENAME = "manifest.sha256"
CATALOG_DELTA_FILENAME = "ordered-catalog-pair-delta.jsonl"
REVIEW_UNITS_FILENAME = "review-units.jsonl"
REVIEWS_FILENAME = "analyst-reviews.jsonl"
BLOCKERS_FILENAME = "blockers.jsonl"
README_FILENAME = "README.md"

LABELS = frozenset({"retain", "reject", "uncertain", "manual-review"})
EXPECTED_PAIR_ROWS = (
    (4770, "satq-4692109c8b9517195887b8ab"),
    (4771, "satq-9dfb9843e8c68c8abcab6986"),
    (4772, "satq-2e213312fcc0eaed7a74c3f4"),
    (4774, "satq-e2731a09ededb28f8493e272"),
    (4775, "satq-a3932f317df914a8dda25cd2"),
    (4776, "satq-6ac1ca957a8c224fae0087cb"),
    (4777, "satq-ef0aee299bdef0cbf6265c76"),
    (4778, "satq-7ad994bba2bb69e18520cd28"),
    (4779, "satq-bf22be4abdfaa45de36add4b"),
    (4782, "satq-e6f40be2128a474624768ae1"),
    (4783, "satq-219dc683ceaae518f75e4dfc"),
    (4784, "satq-a12a1ca6e988d815555d797f"),
    (4785, "satq-1b4b1bdaee8ffcfb11550cc5"),
    (4786, "satq-6bfb8ae8d11b18a965c3784b"),
    (4787, "satq-199fa5f0ed4434242db3bf77"),
    (4788, "satq-1ee95b7ed40ff30d2355519c"),
    (4789, "satq-f97d8e127d30d8c1e3477f6a"),
    (4790, "satq-7cff555ce9ba0769a02f8c34"),
    (4791, "satq-37893e519dad0a189ef58620"),
    (4792, "satq-8e26459767dc9f39b57697dd"),
    (4793, "satq-3793948ad491017d1be91fdc"),
    (4794, "satq-29360218b6ae3f12a014bb33"),
)
NO_SCENE_ROWS = (
    (4773, "satq-d24e538796a2ddcd5947aaf4"),
    (4780, "satq-abd001cb72ef68053ac0b683"),
    (4781, "satq-096a168063a356491b6b5136"),
)
BLOCKED_QUEUE_ID = "satq-6bfb8ae8d11b18a965c3784b"
RESELECTION_CANDIDATES = (
    "satq-e2731a09ededb28f8493e272",
    "satq-a3932f317df914a8dda25cd2",
    "satq-a12a1ca6e988d815555d797f",
    BLOCKED_QUEUE_ID,
    "satq-8e26459767dc9f39b57697dd",
)
RESELECTED_QUEUE_IDS = tuple(
    queue_id for queue_id in RESELECTION_CANDIDATES if queue_id != BLOCKED_QUEUE_ID
)
DIRECT_QUEUE_IDS = tuple(
    queue_id
    for _position, queue_id in EXPECTED_PAIR_ROWS
    if queue_id not in set(RESELECTION_CANDIDATES)
)
MOSAIC_V1_QUEUE_IDS = (
    "satq-54c6402eb93d14f1ea754e66",
    "satq-cef871428da247c3ecfadec6",
    "satq-96fca962064e09f0dbafa93b",
    "satq-78500568b1f6227789ae36f4",
    "satq-fb6b6f815dad079c059cf412",
    "satq-0ffe3647dc32ee25ef77eab7",
)

EXPECTED_INPUTS = {
    "accepted_continuation": (
        "satellite_review_continuations/"
        "2026-07-21-global-open-v3-unknown-034-continued-25/"
        "continuation-manifest.json"
    ),
    "catalog_batch": (
        "satellite_review_runs/"
        "2026-07-21-global-open-v3-unknown-034/batch-manifest.json"
    ),
    "catalog_parent": (
        "satellite_review_recoveries/"
        "2026-07-19-global-open-v3-unknown-033-recovered-25/"
        "batch/batch-manifest.json"
    ),
    "direct_change_batch": (
        "satellite_change_runs/"
        "2026-07-21-global-open-v3-unknown-034-delta-single-asset-v2-001/"
        "batch-manifest.json"
    ),
    "mosaic_contract": "datacenter_atlas/satellite_change_mosaic_batch_v1.py",
    "queue_manifest": (
        "satellite_review_queues/2026-07-18-global-open-v3/manifest.json"
    ),
    "queue_rows": (
        "satellite_review_queues/2026-07-18-global-open-v3/"
        "satellite-review-queue.jsonl"
    ),
    "reselected_change_batch": (
        "satellite_change_runs/"
        "2026-07-21-global-open-v3-unknown-034-delta-reselected-v2-001/"
        "batch-manifest.json"
    ),
    "reselection_manifest": (
        "satellite_catalog_reselection_runs/"
        "2026-07-21-global-open-v3-unknown-034-delta-reselection-v2-001/"
        "batch-manifest.json"
    ),
    "reselection_unresolved": (
        "satellite_catalog_reselection_runs/"
        "2026-07-21-global-open-v3-unknown-034-delta-reselection-v2-001/"
        "unresolved-multitile-needed.json"
    ),
}

SCOPE = {
    "atlas_mutation": False,
    "automated_promotion_allowed": False,
    "change_analysis_executed_by_checkpoint": False,
    "identical_aoi_scene_pair_deduplication": True,
    "imagery_construction_status_inference": False,
    "imagery_data_centre_type_inference": False,
    "imagery_energy_inference": False,
    "imagery_identity_inference": False,
    "imagery_it_capacity_inference": False,
    "imagery_lifecycle_inference": False,
    "imagery_load_inference": False,
    "imagery_operating_status_inference": False,
    "imagery_operator_inference": False,
    "imagery_power_inference": False,
    "imagery_pue_inference": False,
    "imagery_workload_inference": False,
    "network_access_during_build": False,
    "network_access_during_validation": False,
    "review_labels_are_visual_dispositions_only": True,
    "review_required": True,
    "source_comparison_images_copied_exactly": True,
    "unique_site_claim_created": False,
}

BUILDER_FILES = (
    "datacenter_atlas/satellite_unknown034_delta_review_v1.py",
    "satellite_unknown034_delta_review_v1.py",
    "scripts/build_satellite_unknown034_delta_review_v1.py",
)


class Unknown034DeltaReviewV1Error(ValueError):
    """Raised when accepted lineage, accounting, or review bytes drift."""


def _sha256(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_line(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def _canonical_hash(value: Any) -> str:
    return _sha256(_canonical_line(value).rstrip(b"\n"))


def _safe_parts(value: str, label: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or "\\" in value:
        raise Unknown034DeltaReviewV1Error(f"{label} is not a safe relative path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or pure.as_posix() != value or any(
        part in {"", ".", ".."} for part in pure.parts
    ):
        raise Unknown034DeltaReviewV1Error(f"{label} is not a safe relative path")
    return pure.parts


def _regular_file(root: Path, relative: str, label: str) -> Path:
    path = root.joinpath(*_safe_parts(relative, label))
    resolved_root = root.resolve()
    resolved = path.resolve(strict=False)
    if resolved_root not in resolved.parents:
        raise Unknown034DeltaReviewV1Error(f"{label} escapes package root")
    current = root
    for part in _safe_parts(relative, label):
        current = current / part
        if current.is_symlink():
            raise Unknown034DeltaReviewV1Error(f"{label} traverses a symlink")
    if not path.is_file():
        raise Unknown034DeltaReviewV1Error(f"{label} is not a regular file")
    return path


def _file_record(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def _path_record(root: Path, relative: str) -> dict[str, Any]:
    return {"path": relative, **_file_record(_regular_file(root, relative, relative))}


def _decode_json(raw: bytes, label: str) -> Any:
    try:
        return json.loads(
            raw.decode("utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                Unknown034DeltaReviewV1Error(
                    f"{label} contains non-finite number {value}"
                )
            ),
        )
    except UnicodeDecodeError as error:
        raise Unknown034DeltaReviewV1Error(f"{label} is not UTF-8") from error
    except json.JSONDecodeError as error:
        raise Unknown034DeltaReviewV1Error(f"{label} is not JSON") from error


def _json_object(path: Path, label: str) -> dict[str, Any]:
    value = _decode_json(path.read_bytes(), label)
    if not isinstance(value, dict):
        raise Unknown034DeltaReviewV1Error(f"{label} is not an object")
    return value


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise Unknown034DeltaReviewV1Error(f"{label} is not a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise Unknown034DeltaReviewV1Error(
            f"{label} is not a UTC timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.astimezone(UTC).isoformat() != value.replace(
        "Z", "+00:00"
    ):
        raise Unknown034DeltaReviewV1Error(f"{label} is not canonical UTC")
    return value


def _definition(path: str | Path) -> tuple[Path, dict[str, Any]]:
    package_root = Path(__file__).resolve().parents[1]
    expected = package_root / DEFINITION_PATH
    supplied = Path(os.path.abspath(os.fspath(path)))
    if supplied != expected or supplied.is_symlink() or not supplied.is_file():
        raise Unknown034DeltaReviewV1Error("review definition path changed")
    raw = supplied.read_bytes()
    if _sha256(raw) != DEFINITION_SHA256:
        raise Unknown034DeltaReviewV1Error("review definition bytes changed")
    value = _decode_json(raw, "review definition")
    if not isinstance(value, dict) or raw != _canonical_json(value):
        raise Unknown034DeltaReviewV1Error(
            "review definition is not canonical JSON"
        )
    expected_keys = {
        "format",
        "inputs",
        "review_id",
        "reviewed_at",
        "schema_version",
        "scope",
        "visual_decisions",
    }
    if set(value) != expected_keys:
        raise Unknown034DeltaReviewV1Error("review definition schema changed")
    if (
        value["format"]
        != "datacenter-atlas-unknown034-delta-review-definition-v1"
        or value["schema_version"] != 1
        or value["review_id"] != REVIEW_ID
        or value["inputs"] != EXPECTED_INPUTS
        or value["scope"] != SCOPE
    ):
        raise Unknown034DeltaReviewV1Error("review definition semantics changed")
    _timestamp(value["reviewed_at"], "reviewed_at")
    decisions = value["visual_decisions"]
    if not isinstance(decisions, list):
        raise Unknown034DeltaReviewV1Error("visual decisions are not an array")
    expected_reviewed = tuple(
        pair for pair in EXPECTED_PAIR_ROWS if pair[1] != BLOCKED_QUEUE_ID
    )
    actual = tuple(
        (row.get("queue_position"), row.get("queue_id"))
        for row in decisions
        if isinstance(row, dict)
    )
    if actual != expected_reviewed or len(actual) != len(decisions):
        raise Unknown034DeltaReviewV1Error("visual decision ordering changed")
    for row in decisions:
        if set(row) != {"label", "observation", "queue_id", "queue_position"}:
            raise Unknown034DeltaReviewV1Error("visual decision schema changed")
        if row["label"] not in LABELS:
            raise Unknown034DeltaReviewV1Error("visual decision label changed")
        if not isinstance(row["observation"], str) or not row["observation"].strip():
            raise Unknown034DeltaReviewV1Error("visual observation is empty")
    return package_root, value


def _queue_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_bytes().splitlines(), start=1):
        value = _decode_json(line, f"queue row {number}")
        if not isinstance(value, dict):
            raise Unknown034DeltaReviewV1Error(f"queue row {number} is invalid")
        rows.append(value)
    positions = [row.get("queue_position") for row in rows]
    ids = [row.get("queue_id") for row in rows]
    if positions != list(range(1, len(rows) + 1)) or len(ids) != len(set(ids)):
        raise Unknown034DeltaReviewV1Error("queue ordering or IDs changed")
    return rows


def _accepted_lineage(
    root: Path,
    definition: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    inputs = definition["inputs"]
    pins = {name: _path_record(root, relative) for name, relative in inputs.items()}
    wrapper = _json_object(
        _regular_file(root, inputs["accepted_continuation"], "accepted continuation"),
        "accepted continuation",
    )
    wrapper_bindings = {
        "catalog_parent": wrapper["source_recovery"]["batch_manifest"],
        "catalog_batch": wrapper["output"]["batch_manifest"],
        "queue_manifest": wrapper["queue_bundle"]["manifest"],
        "queue_rows": wrapper["queue_bundle"]["queue"],
    }
    for name, expected in wrapper_bindings.items():
        if expected != pins[name]:
            raise Unknown034DeltaReviewV1Error(
                f"accepted continuation no longer binds {name}"
            )
    parent = _json_object(
        _regular_file(root, inputs["catalog_parent"], "catalog parent"),
        "catalog parent",
    )
    output = _json_object(
        _regular_file(root, inputs["catalog_batch"], "catalog batch"),
        "catalog batch",
    )
    return parent, output, pins


def _catalog_delta(
    root: Path,
    definition: Mapping[str, Any],
    parent: Mapping[str, Any],
    output: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    parent_jobs = parent.get("jobs")
    output_jobs = output.get("jobs")
    if not isinstance(parent_jobs, dict) or not isinstance(output_jobs, dict):
        raise Unknown034DeltaReviewV1Error("catalog task inventories are invalid")
    if set(parent_jobs) != set(output_jobs):
        raise Unknown034DeltaReviewV1Error("catalog task inventory changed")
    changed = {
        queue_id for queue_id in parent_jobs if parent_jobs[queue_id] != output_jobs[queue_id]
    }
    expected_changed = {queue_id for _position, queue_id in EXPECTED_PAIR_ROWS} | {
        queue_id for _position, queue_id in NO_SCENE_ROWS
    }
    if changed != expected_changed:
        raise Unknown034DeltaReviewV1Error("catalog task delta is not the exact tranche")
    queue = _queue_rows(
        _regular_file(root, definition["inputs"]["queue_rows"], "queue rows")
    )
    queue_by_id = {row["queue_id"]: row for row in queue}
    rows: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for position, queue_id in EXPECTED_PAIR_ROWS:
        source_task = parent_jobs[queue_id]
        task = output_jobs[queue_id]
        queue_row = queue_by_id[queue_id]
        if (
            source_task.get("state") != "pending"
            or source_task.get("attempts") != 0
            or task.get("state") != "completed"
            or task.get("attempts") != 1
            or task.get("queue_position") != position
            or queue_row.get("queue_position") != position
        ):
            raise Unknown034DeltaReviewV1Error(
                f"catalog pair transition changed for {queue_id}"
            )
        selected_ids = task.get("selected_ids")
        if not isinstance(selected_ids, dict) or set(selected_ids) != {
            "baseline",
            "current",
        }:
            raise Unknown034DeltaReviewV1Error(
                f"catalog selected IDs changed for {queue_id}"
            )
        review_key = {
            "aoi_bbox_wgs84": queue_row["location"]["aoi_bbox_wgs84"],
            "selected_ids": selected_ids,
        }
        row = {
            "accepted_catalog_pair_key_sha256": _canonical_hash(review_key),
            "aoi_bbox_wgs84": review_key["aoi_bbox_wgs84"],
            "catalog_artifacts": task["artifacts"],
            "output_catalog_task_sha256": _canonical_hash(task),
            "parent_catalog_task_sha256": _canonical_hash(source_task),
            "queue_id": queue_id,
            "queue_position": position,
            "queue_record_sha256": _canonical_hash(queue_row),
            "selected_ids": selected_ids,
        }
        rows.append(row)
        by_id[queue_id] = row
    for position, queue_id in NO_SCENE_ROWS:
        source_task = parent_jobs[queue_id]
        task = output_jobs[queue_id]
        if (
            source_task.get("state") != "pending"
            or task.get("state") != "unavailable_no_scene"
            or task.get("queue_position") != position
        ):
            raise Unknown034DeltaReviewV1Error(
                f"catalog no-scene transition changed for {queue_id}"
            )
    before = parent["summary"]
    after = output["summary"]
    arithmetic = (
        after["jobs_completed"] - before["jobs_completed"],
        after["jobs_unavailable_no_scene"] - before["jobs_unavailable_no_scene"],
        after["jobs_pending"] - before["jobs_pending"],
        after["jobs_failed"] - before["jobs_failed"],
    )
    if arithmetic != (22, 3, -25, 0):
        raise Unknown034DeltaReviewV1Error("catalog delta arithmetic changed")
    keys = [row["accepted_catalog_pair_key_sha256"] for row in rows]
    if len(keys) != 22 or len(set(keys)) != 22:
        raise Unknown034DeltaReviewV1Error(
            "identical AOI/scene-pair deduplication changed"
        )
    return rows, by_id


def _change_inputs(
    root: Path,
    definition: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    inputs = definition["inputs"]
    reselection = _json_object(
        _regular_file(root, inputs["reselection_manifest"], "reselection manifest"),
        "reselection manifest",
    )
    unresolved = _json_object(
        _regular_file(root, inputs["reselection_unresolved"], "unresolved assessment"),
        "unresolved assessment",
    )
    direct = _json_object(
        _regular_file(root, inputs["direct_change_batch"], "direct change batch"),
        "direct change batch",
    )
    reselected = _json_object(
        _regular_file(
            root,
            inputs["reselected_change_batch"],
            "reselected change batch",
        ),
        "reselected change batch",
    )
    configuration = reselection.get("configuration", {})
    if (
        reselection.get("state") != "complete"
        or tuple(configuration.get("candidate_queue_ids", []))
        != RESELECTION_CANDIDATES
        or tuple(configuration.get("supported_queue_ids", []))
        != RESELECTED_QUEUE_IDS
        or configuration.get("unresolved_queue_ids") != [BLOCKED_QUEUE_ID]
        or reselection.get("summary", {}).get("jobs_reselected") != 4
        or reselection.get("summary", {}).get("jobs_unresolved_multitile_needed")
        != 1
    ):
        raise Unknown034DeltaReviewV1Error("reselection partition changed")
    unresolved_jobs = unresolved.get("jobs")
    if not isinstance(unresolved_jobs, list) or len(unresolved_jobs) != 1:
        raise Unknown034DeltaReviewV1Error("unresolved assessment changed")
    blocker = unresolved_jobs[0]
    if (
        blocker.get("queue_id") != BLOCKED_QUEUE_ID
        or blocker.get("resolution_reason") != "no_full_cover_baseline_candidate"
        or blocker.get("outcome")
        != "unresolved_multitile_or_supplemental_scene_required"
        or blocker.get("full_cover_eligible_ids", {}).get("baseline") != []
        or blocker.get("change_analysis_executed") is not False
    ):
        raise Unknown034DeltaReviewV1Error("typed native-window blocker changed")
    expected_batches = (
        (direct, "satellite_review_change_batch", DIRECT_QUEUE_IDS),
        (
            reselected,
            "satellite_review_reselected_change_batch_v2",
            RESELECTED_QUEUE_IDS,
        ),
    )
    for document, pipeline, queue_ids in expected_batches:
        if (
            document.get("pipeline") != pipeline
            or document.get("state") != "completed"
            or tuple(document.get("selection", {}).get("selected_queue_ids", []))
            != queue_ids
            or document.get("summary", {}).get("jobs_completed") != len(queue_ids)
            or document.get("summary", {}).get("jobs_failed") != 0
            or document.get("processor", {}).get("algorithm_version")
            != "sentinel-2-l2a-change-v2"
        ):
            raise Unknown034DeltaReviewV1Error(f"{pipeline} checkpoint changed")
        scope = document.get("scope", {})
        if scope.get("review_required") is not True or any(
            value is not False
            for name, value in scope.items()
            if name.startswith("imagery_") or name == "atlas_mutation"
        ):
            raise Unknown034DeltaReviewV1Error(f"{pipeline} scope changed")
    if BLOCKED_QUEUE_ID in MOSAIC_V1_QUEUE_IDS:
        raise Unknown034DeltaReviewV1Error("mosaic-v1 contract unexpectedly matches")
    mosaic_source = _regular_file(
        root, inputs["mosaic_contract"], "mosaic-v1 contract"
    ).read_text(encoding="utf-8")
    for queue_id in MOSAIC_V1_QUEUE_IDS:
        if queue_id not in mosaic_source:
            raise Unknown034DeltaReviewV1Error("mosaic-v1 queue contract changed")
    if BLOCKED_QUEUE_ID in mosaic_source:
        raise Unknown034DeltaReviewV1Error(
            "blocked Unknown034 row entered fixed mosaic-v1 contract"
        )
    return reselection, unresolved, direct, reselected


def _change_records(
    root: Path,
    definition: Mapping[str, Any],
    direct: Mapping[str, Any],
    reselected: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for lane, document, input_name in (
        ("original_full_cover", direct, "direct_change_batch"),
        ("coverage_reselected", reselected, "reselected_change_batch"),
    ):
        batch_manifest = definition["inputs"][input_name]
        batch_root = _regular_file(root, batch_manifest, input_name).parent
        for queue_id in document["selection"]["selected_queue_ids"]:
            task = document["jobs"][queue_id]
            if (
                task.get("state") != "completed"
                or task.get("attempts") != 1
                or task.get("failures") != []
                or task.get("report", {}).get("algorithm_version")
                != "sentinel-2-l2a-change-v2"
            ):
                raise Unknown034DeltaReviewV1Error(
                    f"completed change task changed for {queue_id}"
                )
            relative_dir = task["change_job"]["output_directory"]
            comparison_relative = f"{relative_dir}/comparison.png"
            report_relative = f"{relative_dir}/report.json"
            comparison = _regular_file(
                batch_root, comparison_relative, f"{queue_id} comparison"
            )
            report = _regular_file(batch_root, report_relative, f"{queue_id} report")
            if (
                _file_record(comparison) != task["artifacts"]["comparison.png"]
                or _file_record(report) != task["artifacts"]["report.json"]
            ):
                raise Unknown034DeltaReviewV1Error(
                    f"change output pin changed for {queue_id}"
                )
            report_document = _json_object(report, f"{queue_id} report")
            classification = report_document.get("classification", {})
            if (
                report_document.get("algorithm_version")
                != "sentinel-2-l2a-change-v2"
                or classification.get("review_required") is not True
                or any(
                    classification.get(field) is not False
                    for field in (
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
                    )
                )
            ):
                raise Unknown034DeltaReviewV1Error(
                    f"change report scope changed for {queue_id}"
                )
            records[queue_id] = {
                "analysis_lane": lane,
                "analysis_selected_ids": task["catalog_source"]["selected_ids"],
                "batch_manifest": batch_manifest,
                "comparison_bytes": comparison.read_bytes(),
                "comparison_source": {
                    "path": f"{batch_root.relative_to(root).as_posix()}/"
                    f"{comparison_relative}",
                    **_file_record(comparison),
                },
                "report": {
                    "path": f"{batch_root.relative_to(root).as_posix()}/"
                    f"{report_relative}",
                    **_file_record(report),
                },
                "report_metrics": task["report"]["metrics"],
            }
    expected = {queue_id for _position, queue_id in EXPECTED_PAIR_ROWS} - {
        BLOCKED_QUEUE_ID
    }
    if set(records) != expected:
        raise Unknown034DeltaReviewV1Error("change output coverage changed")
    return records


def _artifact_record(raw: bytes, *, records: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"bytes": len(raw), "sha256": _sha256(raw)}
    if records is not None:
        result["records"] = records
    return result


def _readme() -> bytes:
    return (
        "# Unknown034 bounded satellite delta review\n\n"
        "This frozen checkpoint starts only from the 22 completed catalog-pair "
        "rows added by accepted Unknown034 over its accepted Unknown033 recovery "
        "parent. Exact AOI plus accepted scene-pair keys form 22 review units; "
        "there are no identical duplicates, and this is not a unique-site count.\n\n"
        "Twenty-one units have completed `sentinel-2-l2a-change-v2` comparison "
        "artifacts: 17 original full-cover pairs and four coverage-reselected pairs. "
        "One unit remains a typed `no_full_cover_baseline_candidate` blocker. The "
        "existing mosaic-v1 runner is a fixed six-job contract and does not accept "
        "that queue row.\n\n"
        "Review labels are visual dispositions only. They create no identity, "
        "construction, lifecycle, operating-status, type, capacity, load, power, "
        "energy, PUE, workload, operator, or atlas claim.\n"
    ).encode("utf-8")


def build_unknown034_delta_review_v1(
    definition_path: str | Path,
) -> dict[str, bytes]:
    """Reproduce the complete review bundle from frozen local inputs only."""

    root, definition = _definition(definition_path)
    parent, output, input_pins = _accepted_lineage(root, definition)
    delta_rows, delta_by_id = _catalog_delta(
        root, definition, parent, output
    )
    reselection, unresolved, direct, reselected = _change_inputs(root, definition)
    changes = _change_records(root, definition, direct, reselected)
    decision_by_id = {
        row["queue_id"]: row for row in definition["visual_decisions"]
    }

    files: dict[str, bytes] = {}
    review_rows: list[dict[str, Any]] = []
    blocker_rows: list[dict[str, Any]] = []
    unit_rows: list[dict[str, Any]] = []
    for position, queue_id in EXPECTED_PAIR_ROWS:
        delta = delta_by_id[queue_id]
        unit_id = f"satru-{delta['accepted_catalog_pair_key_sha256'][:24]}"
        if queue_id == BLOCKED_QUEUE_ID:
            source_blocker = unresolved["jobs"][0]
            blocker = {
                "accepted_catalog_pair_key_sha256": delta[
                    "accepted_catalog_pair_key_sha256"
                ],
                "change_analysis_executed": False,
                "full_cover_eligible_ids": source_blocker[
                    "full_cover_eligible_ids"
                ],
                "label": "manual-review",
                "mosaic_lane": {
                    "applied": False,
                    "contract": "satellite_review_change_mosaic_batch_v1",
                    "contract_queue_ids": list(MOSAIC_V1_QUEUE_IDS),
                    "exact_contract_match": False,
                    "reason": "fixed_v57_six_job_contract_does_not_include_queue_id",
                },
                "outcome": source_blocker["outcome"],
                "queue_id": queue_id,
                "queue_position": position,
                "resolution_reason": source_blocker["resolution_reason"],
                "review_unit_id": unit_id,
                "source_unresolved_assessment": input_pins[
                    "reselection_unresolved"
                ],
            }
            blocker_rows.append(blocker)
            unit_rows.append(
                {
                    "accepted_catalog_pair_key_sha256": delta[
                        "accepted_catalog_pair_key_sha256"
                    ],
                    "analysis_outcome": "typed_native_window_blocker",
                    "deduplicated_member_queue_ids": [queue_id],
                    "label": "manual-review",
                    "queue_id": queue_id,
                    "queue_position": position,
                    "review_unit_id": unit_id,
                }
            )
            continue

        decision = decision_by_id[queue_id]
        change = changes[queue_id]
        copied = f"comparisons/{position}-{queue_id}.png"
        files[copied] = change["comparison_bytes"]
        review = {
            "accepted_catalog_pair_key_sha256": delta[
                "accepted_catalog_pair_key_sha256"
            ],
            "analysis_lane": change["analysis_lane"],
            "analysis_selected_ids": change["analysis_selected_ids"],
            "catalog_selected_ids": delta["selected_ids"],
            "comparison": {
                "copied_path": copied,
                "source": change["comparison_source"],
            },
            "label": decision["label"],
            "observation": decision["observation"],
            "queue_id": queue_id,
            "queue_position": position,
            "report": change["report"],
            "review_scope": "visible_comparison_disposition_only",
            "review_unit_id": unit_id,
            "reviewed_at": definition["reviewed_at"],
        }
        review_rows.append(review)
        unit_rows.append(
            {
                "accepted_catalog_pair_key_sha256": delta[
                    "accepted_catalog_pair_key_sha256"
                ],
                "analysis_outcome": "comparison_reviewed",
                "deduplicated_member_queue_ids": [queue_id],
                "label": decision["label"],
                "queue_id": queue_id,
                "queue_position": position,
                "review_unit_id": unit_id,
            }
        )

    if len({row["review_unit_id"] for row in unit_rows}) != 22:
        raise Unknown034DeltaReviewV1Error("review-unit deduplication changed")
    files[CATALOG_DELTA_FILENAME] = b"".join(
        _canonical_line(row) for row in delta_rows
    )
    files[REVIEW_UNITS_FILENAME] = b"".join(
        _canonical_line(row) for row in unit_rows
    )
    files[REVIEWS_FILENAME] = b"".join(
        _canonical_line(row) for row in review_rows
    )
    files[BLOCKERS_FILENAME] = b"".join(
        _canonical_line(row) for row in blocker_rows
    )
    files[README_FILENAME] = _readme()

    builder = {
        relative: _path_record(root, relative) for relative in BUILDER_FILES
    }
    label_counts = Counter(row["label"] for row in unit_rows)
    artifact_records = {
        name: _artifact_record(
            raw,
            records=(
                len(raw.splitlines())
                if name.endswith(".jsonl")
                else None
            ),
        )
        for name, raw in sorted(files.items())
    }
    inventory_hash = _canonical_hash(
        [{"path": name, **record} for name, record in artifact_records.items()]
    )
    manifest = {
        "artifacts": artifact_records,
        "builder": {"files": builder},
        "catalog_delta": {
            "completed_pair_rows": 22,
            "no_scene_rows_excluded_before_change_analysis": [
                {"queue_id": queue_id, "queue_position": position}
                for position, queue_id in NO_SCENE_ROWS
            ],
            "ordered_queue_positions": [
                position for position, _queue_id in EXPECTED_PAIR_ROWS
            ],
            "parent_to_output_arithmetic": {
                "jobs_completed": 22,
                "jobs_failed": 0,
                "jobs_pending": -25,
                "jobs_unavailable_no_scene": 3,
            },
        },
        "format": "datacenter-atlas-unknown034-delta-review-v1",
        "input_pins": input_pins,
        "review_id": REVIEW_ID,
        "reviewed_at": definition["reviewed_at"],
        "schema_version": 1,
        "scope": dict(SCOPE),
        "source_contracts": {
            "change_algorithm": "sentinel-2-l2a-change-v2",
            "direct_change_pipeline": direct["pipeline"],
            "mosaic_v1_applied": False,
            "mosaic_v1_queue_ids": list(MOSAIC_V1_QUEUE_IDS),
            "reselected_change_pipeline": reselected["pipeline"],
            "reselection_pipeline": reselection["pipeline"],
        },
        "summary": {
            "analysis_failures": 0,
            "catalog_pair_rows": 22,
            "comparison_images_copied": 21,
            "exact_aoi_scene_pair_duplicate_rows": 0,
            "exact_aoi_scene_pair_review_units": 22,
            "label_counts": dict(sorted(label_counts.items())),
            "native_window_blockers": 1,
            "original_full_cover_comparisons": 17,
            "reselected_full_cover_comparisons": 4,
            "reviewed_comparisons": 21,
            "unique_sites_claimed": 0,
        },
        "tree_inventory_sha256": inventory_hash,
    }
    files[MANIFEST_FILENAME] = _canonical_json(manifest)
    files[SIDECAR_FILENAME] = (
        f"{_sha256(files[MANIFEST_FILENAME])}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    return files


def _expected_paths(files: Mapping[str, bytes]) -> set[str]:
    return set(files)


def _closed_tree(directory: Path, files: Mapping[str, bytes]) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise Unknown034DeltaReviewV1Error("review bundle is not a regular directory")
    actual_files: set[str] = set()
    directories = [directory]
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise Unknown034DeltaReviewV1Error("review bundle contains a symlink")
        relative = path.relative_to(directory).as_posix()
        if path.is_file():
            actual_files.add(relative)
            if stat.S_IMODE(path.stat().st_mode) != 0o444:
                raise Unknown034DeltaReviewV1Error(
                    f"review file is not frozen: {relative}"
                )
        elif path.is_dir():
            directories.append(path)
        else:
            raise Unknown034DeltaReviewV1Error(
                f"review bundle contains a non-regular path: {relative}"
            )
    if actual_files != _expected_paths(files):
        raise Unknown034DeltaReviewV1Error("review bundle file set changed")
    if any(stat.S_IMODE(path.stat().st_mode) != 0o555 for path in directories):
        raise Unknown034DeltaReviewV1Error("review bundle directory mode changed")


def _freeze_tree(directory: Path) -> None:
    for path in sorted(directory.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_file():
            path.chmod(0o444)
        elif path.is_dir():
            path.chmod(0o555)
    directory.chmod(0o555)


def _fsync_tree(directory: Path) -> None:
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            descriptor = os.open(path, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)


def write_unknown034_delta_review_v1(
    definition_path: str | Path,
    output_directory: str | Path,
    *,
    freeze: bool = True,
) -> dict[str, Any]:
    """Atomically publish a collision-isolated immutable review bundle."""

    if not freeze:
        raise Unknown034DeltaReviewV1Error("review publication requires freeze=True")
    root, _definition_value = _definition(definition_path)
    expected_output = root / OUTPUT_PATH
    output = Path(os.path.abspath(os.fspath(output_directory)))
    if output != expected_output:
        raise Unknown034DeltaReviewV1Error("review output path changed")
    if output.exists() or output.is_symlink():
        raise Unknown034DeltaReviewV1Error("review output already exists")
    if output.parent.is_symlink() or not output.parent.is_dir():
        raise Unknown034DeltaReviewV1Error("review output parent is invalid")
    files = build_unknown034_delta_review_v1(definition_path)
    stage = output.with_name(f".{output.name}.staging-v1")
    if stage.exists() or stage.is_symlink():
        raise Unknown034DeltaReviewV1Error("review staging path already exists")
    stage.mkdir(mode=0o755)
    moved = False
    try:
        for relative, raw in files.items():
            destination = stage.joinpath(*_safe_parts(relative, relative))
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        _fsync_tree(stage)
        _freeze_tree(stage)
        _closed_tree(stage, files)
        os.replace(stage, output)
        moved = True
        descriptor = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except BaseException:
        if not moved and stage.exists() and not stage.is_symlink():
            for path in sorted(
                stage.rglob("*"), key=lambda item: len(item.parts), reverse=True
            ):
                if path.is_dir():
                    path.chmod(0o755)
                elif path.is_file():
                    path.chmod(0o644)
            stage.chmod(0o755)
            shutil.rmtree(stage)
        raise
    return validate_unknown034_delta_review_v1(output, definition_path)


def validate_unknown034_delta_review_v1(
    bundle_directory: str | Path,
    definition_path: str | Path,
) -> dict[str, Any]:
    """Offline-reproduce the frozen checkpoint and compare every byte."""

    root, _definition_value = _definition(definition_path)
    bundle = Path(os.path.abspath(os.fspath(bundle_directory)))
    if bundle != root / OUTPUT_PATH:
        raise Unknown034DeltaReviewV1Error("review bundle path changed")
    expected = build_unknown034_delta_review_v1(definition_path)
    _closed_tree(bundle, expected)
    for relative, raw in expected.items():
        actual = _regular_file(bundle, relative, f"review {relative}").read_bytes()
        if actual != raw:
            raise Unknown034DeltaReviewV1Error(
                f"review bundle differs from offline replay: {relative}"
            )
    manifest = _json_object(bundle / MANIFEST_FILENAME, "review manifest")
    if manifest.get("review_id") != REVIEW_ID or manifest.get("scope") != SCOPE:
        raise Unknown034DeltaReviewV1Error("review manifest semantics changed")
    return manifest


__all__ = [
    "BLOCKED_QUEUE_ID",
    "DEFINITION_PATH",
    "DEFINITION_SHA256",
    "OUTPUT_PATH",
    "REVIEW_ID",
    "Unknown034DeltaReviewV1Error",
    "build_unknown034_delta_review_v1",
    "validate_unknown034_delta_review_v1",
    "write_unknown034_delta_review_v1",
]
