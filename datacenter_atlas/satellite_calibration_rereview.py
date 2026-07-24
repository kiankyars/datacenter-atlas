"""Fail-closed preparation of a blind algorithm-v2 calibration re-review queue.

The release produced here contains no analyst decisions and makes no calibration
claim.  Historical decisions are copied only into a permission-sealed lineage
sidecar so they cannot enter the reviewer-facing queue accidentally.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable, Mapping

from .satellite_change import canonical_sha256, select_feature


FORMAT = "datacenter-atlas-satellite-calibration-rereview-preparation-v1"
SCHEMA_VERSION = 1
TARGET_ALGORITHM = "sentinel-2-l2a-change-v2"
HISTORICAL_ALGORITHM = "sentinel-2-l2a-change-v1"
PUBLIC_FILES = frozenset(
    {
        "ATTRIBUTION.txt",
        "README.md",
        "manifest.json",
        "manifest.sha256",
        "reviewer-queue.jsonl",
        "rerun-specs.jsonl",
        "run-inventory.json",
        "summary.json",
    }
)
SEALED_FILES = frozenset({"sealed/lineage.jsonl"})
BUNDLE_FILES = PUBLIC_FILES | SEALED_FILES
FORBIDDEN_REVIEW_KEYS = frozenset(
    {
        "decision",
        "outcome",
        "queue_id",
        "report_bytes",
        "report_path",
        "report_sha256",
        "review_bytes",
        "review_path",
        "review_sha256",
        "reviewed_at",
        "source_run",
    }
)


class SatelliteCalibrationRereviewError(ValueError):
    """Raised when an input or preparation release fails closed."""


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


def _checkpoint(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def _checked_path(project_root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise SatelliteCalibrationRereviewError(f"{label} path is invalid")
    relative = Path(value)
    if ".." in relative.parts:
        raise SatelliteCalibrationRereviewError(f"{label} path escapes the project")
    path = (project_root / relative).resolve()
    try:
        path.relative_to(project_root.resolve())
    except ValueError as error:
        raise SatelliteCalibrationRereviewError(
            f"{label} path escapes the project"
        ) from error
    if not path.is_file() or path.is_symlink():
        raise SatelliteCalibrationRereviewError(f"{label} is not a regular file")
    return path


def _verify_checkpoint(path: Path, expected: Mapping[str, Any], label: str) -> None:
    actual = _checkpoint(path)
    if actual != {"bytes": expected.get("bytes"), "sha256": expected.get("sha256")}:
        raise SatelliteCalibrationRereviewError(f"{label} checkpoint mismatch")


def _load_definition(definition_path: Path) -> tuple[dict[str, Any], Path]:
    raw = definition_path.read_bytes()
    try:
        definition = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SatelliteCalibrationRereviewError("definition is not valid JSON") from error
    if raw != _canonical_json(definition):
        raise SatelliteCalibrationRereviewError("definition is not canonical JSON")
    if definition.get("format") != FORMAT or definition.get("schema_version") != 1:
        raise SatelliteCalibrationRereviewError("definition format is unsupported")
    if definition.get("target_algorithm") != TARGET_ALGORITHM:
        raise SatelliteCalibrationRereviewError("target algorithm is unsupported")
    if definition.get("historical_algorithm") != HISTORICAL_ALGORITHM:
        raise SatelliteCalibrationRereviewError("historical algorithm is unsupported")
    project_root = definition_path.resolve().parent.parent
    return definition, project_root


def _input_file(
    project_root: Path, descriptor: Mapping[str, Any], label: str
) -> Path:
    path = _checked_path(project_root, descriptor.get("path"), label)
    _verify_checkpoint(path, descriptor, label)
    return path


def _json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except json.JSONDecodeError as error:
        raise SatelliteCalibrationRereviewError(f"{label} is invalid JSON") from error
    if not isinstance(value, dict):
        raise SatelliteCalibrationRereviewError(f"{label} must be an object")
    return value


def _jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for index, line in enumerate(path.read_bytes().splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise SatelliteCalibrationRereviewError(
                f"{label} line {index} is invalid JSON"
            ) from error
        if not isinstance(value, dict):
            raise SatelliteCalibrationRereviewError(
                f"{label} line {index} must be an object"
            )
        values.append(value)
    return values


def _review_source_path(project_root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.startswith("../satellite_review_runs/"):
        raise SatelliteCalibrationRereviewError(f"{label} path is unsupported")
    return _checked_path(project_root, value.removeprefix("../"), label)


def _bbox_from_arguments(arguments: Any) -> tuple[float, float, float, float]:
    if not isinstance(arguments, list):
        raise SatelliteCalibrationRereviewError("change arguments are invalid")
    try:
        raw = arguments[arguments.index("--bbox") + 1]
        values = tuple(float(part) for part in raw.split(","))
    except (ValueError, IndexError, AttributeError) as error:
        raise SatelliteCalibrationRereviewError("change bbox is invalid") from error
    if len(values) != 4:
        raise SatelliteCalibrationRereviewError("change bbox is invalid")
    return values  # type: ignore[return-value]


def _identity_projection(
    *, queue_id: str, entity_id: str, aoi: Iterable[float], report: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "aoi_bbox_wgs84": list(aoi),
        "baseline_stac_item_sha256": report["baseline"]["stac_item_sha256"],
        "current_stac_item_sha256": report["current"]["stac_item_sha256"],
        "entity_id": entity_id,
        "queue_id": queue_id,
    }


def _historical_inputs(
    project_root: Path, definition: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source = definition.get("historical_calibration")
    if not isinstance(source, dict):
        raise SatelliteCalibrationRereviewError("historical calibration is missing")
    definition_path = _input_file(project_root, source["definition"], "calibration definition")
    manifest_path = _input_file(project_root, source["manifest"], "calibration manifest")
    records_path = _input_file(project_root, source["records"], "calibration records")
    manifest = _json(manifest_path, "calibration manifest")
    records = _jsonl(records_path, "calibration records")
    expected_count = definition.get("expected_historical_items")
    if len(records) != expected_count or manifest.get("counts", {}).get("count") != expected_count:
        raise SatelliteCalibrationRereviewError("historical item count mismatch")
    review_pairs = {
        pair.get("queue_id"): pair for pair in manifest.get("inputs", {}).get("review_pairs", [])
    }
    if len(review_pairs) != expected_count:
        raise SatelliteCalibrationRereviewError("calibration review-pair count mismatch")
    items: list[dict[str, Any]] = []
    seen_queue: set[str] = set()
    seen_identity: set[str] = set()
    for line_number, row in enumerate(records, 1):
        queue_id = row.get("queue_id")
        entity_id = row.get("entity_id")
        if not isinstance(queue_id, str) or not isinstance(entity_id, str):
            raise SatelliteCalibrationRereviewError("historical identity is invalid")
        report_path = _review_source_path(project_root, row.get("report_path"), "historical report")
        review_path = _review_source_path(project_root, row.get("review_path"), "historical review")
        _verify_checkpoint(
            report_path,
            {"bytes": row.get("report_bytes"), "sha256": row.get("report_sha256")},
            "historical report",
        )
        _verify_checkpoint(
            review_path,
            {"bytes": row.get("review_bytes"), "sha256": row.get("review_sha256")},
            "historical review",
        )
        pair = review_pairs.get(queue_id)
        if not pair or pair.get("report", {}).get("sha256") != row.get("report_sha256") or pair.get("review", {}).get("sha256") != row.get("review_sha256"):
            raise SatelliteCalibrationRereviewError("historical lineage mismatch")
        report = _json(report_path, "historical report")
        if report.get("algorithm_version") != HISTORICAL_ALGORITHM:
            raise SatelliteCalibrationRereviewError("historical algorithm mismatch")
        if report.get("entity") != {"id": entity_id, "name": row.get("entity_name")}:
            raise SatelliteCalibrationRereviewError("historical entity mismatch")
        if report.get("baseline", {}).get("stac_item_sha256") != row.get("baseline_stac_item_sha256") or report.get("current", {}).get("stac_item_sha256") != row.get("current_stac_item_sha256"):
            raise SatelliteCalibrationRereviewError("historical scene binding mismatch")
        aoi = report.get("aoi_bbox_wgs84")
        if not isinstance(aoi, list) or len(aoi) != 4:
            raise SatelliteCalibrationRereviewError("historical AOI is invalid")
        identity = _identity_projection(
            queue_id=queue_id, entity_id=entity_id, aoi=aoi, report=report
        )
        identity_sha = _sha256(_canonical_line(identity))
        if queue_id in seen_queue or identity_sha in seen_identity:
            raise SatelliteCalibrationRereviewError("historical identity is duplicated")
        seen_queue.add(queue_id)
        seen_identity.add(identity_sha)
        catalog_dir = report_path.parent.parent / "catalog"
        catalog_paths = {
            name: catalog_dir / name
            for name in ("baseline-response.json", "current-response.json", "manifest.json")
        }
        if any(not path.is_file() or path.is_symlink() for path in catalog_paths.values()):
            raise SatelliteCalibrationRereviewError("historical catalog artifact is missing")
        catalog_manifest = _json(catalog_paths["manifest.json"], "historical catalog manifest")
        selected_ids = {
            "baseline": report["baseline"]["id"],
            "current": report["current"]["id"],
        }
        if catalog_manifest.get("selected_ids") != selected_ids:
            raise SatelliteCalibrationRereviewError("historical catalog selection mismatch")
        selected_feature_hashes: dict[str, str] = {}
        for epoch in ("baseline", "current"):
            response = _json(catalog_paths[f"{epoch}-response.json"], f"historical {epoch} response")
            try:
                feature = select_feature(response, selected_ids[epoch])
            except ValueError as error:
                raise SatelliteCalibrationRereviewError(
                    f"historical {epoch} feature is missing"
                ) from error
            selected_feature_hashes[epoch] = canonical_sha256(feature)
            if selected_feature_hashes[epoch] != report[epoch]["stac_item_sha256"]:
                raise SatelliteCalibrationRereviewError(
                    f"historical {epoch} feature hash mismatch"
                )
        items.append(
            {
                "aoi": aoi,
                "blind_item_id": f"v2rr-{identity_sha[:24]}",
                "identity": identity,
                "identity_sha256": identity_sha,
                "line_number": line_number,
                "catalog_artifacts": {
                    name: {
                        "path": str(path.relative_to(project_root)),
                        **_checkpoint(path),
                    }
                    for name, path in sorted(catalog_paths.items())
                },
                "selected_feature_hashes": selected_feature_hashes,
                "report": report,
                "report_checkpoint": _checkpoint(report_path),
                "report_path": row["report_path"],
                "review_checkpoint": _checkpoint(review_path),
                "review_path": row["review_path"],
                "row": row,
            }
        )
    if len({tuple(item["aoi"]) for item in items}) != expected_count:
        raise SatelliteCalibrationRereviewError("historical AOIs are not unique")
    return sorted(items, key=lambda item: item["blind_item_id"]), {
        "definition": {"path": str(definition_path.relative_to(project_root)), **_checkpoint(definition_path)},
        "manifest": {"path": str(manifest_path.relative_to(project_root)), **_checkpoint(manifest_path)},
        "records": {"path": str(records_path.relative_to(project_root)), **_checkpoint(records_path)},
    }


def _v2_outputs(
    project_root: Path, definition: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    descriptors = definition.get("frozen_change_run_manifests")
    if not isinstance(descriptors, list) or not descriptors:
        raise SatelliteCalibrationRereviewError("change-run inventory is missing")
    outputs: list[dict[str, Any]] = []
    inventory: list[dict[str, Any]] = []
    seen_v2_queue: set[str] = set()
    v2_processor_files: Mapping[str, Any] | None = None
    for descriptor in descriptors:
        path = _input_file(project_root, descriptor, "change-run manifest")
        if path.stat().st_mode & 0o777 != 0o444 or path.parent.stat().st_mode & 0o777 != 0o555:
            raise SatelliteCalibrationRereviewError("change-run manifest is not frozen")
        manifest = _json(path, "change-run manifest")
        algorithm = manifest.get("processor", {}).get("algorithm_version")
        state_counts = Counter(job.get("state") for job in manifest.get("jobs", {}).values())
        completed = 0
        identity_index: list[dict[str, Any]] = []
        for queue_id, job in sorted(manifest.get("jobs", {}).items()):
            if job.get("state") != "completed":
                continue
            completed += 1
            if algorithm != TARGET_ALGORITHM:
                continue
            if queue_id in seen_v2_queue:
                raise SatelliteCalibrationRereviewError("v2 output queue identity is duplicated")
            seen_v2_queue.add(queue_id)
            report_path = path.parent / "jobs" / queue_id / "change" / "report.json"
            if not report_path.is_file() or report_path.is_symlink():
                raise SatelliteCalibrationRereviewError("v2 report is missing")
            report_checkpoint = _checkpoint(report_path)
            if report_checkpoint != job.get("artifacts", {}).get("report.json"):
                raise SatelliteCalibrationRereviewError("v2 report checkpoint mismatch")
            report = _json(report_path, "v2 report")
            if report.get("algorithm_version") != TARGET_ALGORITHM:
                raise SatelliteCalibrationRereviewError("v2 report algorithm mismatch")
            aoi = _bbox_from_arguments(job.get("change_job", {}).get("arguments"))
            identity = _identity_projection(
                queue_id=queue_id,
                entity_id=job.get("entity", {}).get("id"),
                aoi=aoi,
                report=report,
            )
            item = {
                "identity": identity,
                "report": report_checkpoint,
                "report_path": str(report_path.relative_to(project_root)),
                "run_id": path.parent.name,
            }
            outputs.append(item)
            identity_index.append(identity)
        processor_files = manifest.get("processor", {}).get("files", {})
        if algorithm == TARGET_ALGORITHM:
            if v2_processor_files is None:
                v2_processor_files = processor_files
            elif processor_files != v2_processor_files:
                raise SatelliteCalibrationRereviewError("v2 processor code hashes differ")
        inventory.append(
            {
                "algorithm_version": algorithm,
                "completed_output_identity_index_sha256": _sha256(
                    b"".join(_canonical_line(value) for value in identity_index)
                ),
                "manifest": {"path": str(path.relative_to(project_root)), **_checkpoint(path)},
                "processor_files": processor_files,
                "run_id": path.parent.name,
                "state": manifest.get("state"),
                "summary": manifest.get("summary"),
                "verified_completed_reports": completed,
                "verified_job_state_counts": dict(sorted(state_counts.items())),
            }
        )
    expected_runs = definition.get("expected_run_counts", {})
    if len(inventory) != expected_runs.get("all_frozen_runs"):
        raise SatelliteCalibrationRereviewError("frozen run count mismatch")
    if len(outputs) != expected_runs.get("completed_v2_outputs"):
        raise SatelliteCalibrationRereviewError("completed v2 output count mismatch")
    if sum(1 for value in inventory if value["algorithm_version"] == TARGET_ALGORITHM) != expected_runs.get("v2_runs"):
        raise SatelliteCalibrationRereviewError("v2 run count mismatch")
    return outputs, inventory


def _match_counts(historical: Mapping[str, Any], outputs: list[dict[str, Any]]) -> dict[str, int]:
    identity = historical["identity"]
    return {
        "aoi_only_or_weaker_candidates": sum(
            candidate["identity"]["aoi_bbox_wgs84"] == identity["aoi_bbox_wgs84"]
            for candidate in outputs
        ),
        "entity_id_candidates": sum(
            candidate["identity"]["entity_id"] == identity["entity_id"]
            for candidate in outputs
        ),
        "queue_id_candidates": sum(
            candidate["identity"]["queue_id"] == identity["queue_id"]
            for candidate in outputs
        ),
        "scene_pair_only_or_weaker_candidates": sum(
            candidate["identity"]["baseline_stac_item_sha256"]
            == identity["baseline_stac_item_sha256"]
            and candidate["identity"]["current_stac_item_sha256"]
            == identity["current_stac_item_sha256"]
            for candidate in outputs
        ),
    }


def _render(
    definition_path: Path,
) -> tuple[dict[str, bytes], dict[str, bytes], dict[str, Any]]:
    definition, project_root = _load_definition(definition_path)
    historical, historical_inputs = _historical_inputs(project_root, definition)
    v2_outputs, run_inventory = _v2_outputs(project_root, definition)
    exact_matches = 0
    weak_aoi_items = 0
    weak_scene_items = 0
    reviewer_rows: list[dict[str, Any]] = []
    rerun_specs: list[dict[str, Any]] = []
    lineage_rows: list[dict[str, Any]] = []
    for item in historical:
        identity = item["identity"]
        matches = [candidate for candidate in v2_outputs if candidate["identity"] == identity]
        if len(matches) > 1:
            raise SatelliteCalibrationRereviewError("multiple exact v2 outputs found")
        counts = _match_counts(item, v2_outputs)
        weak_aoi_items += counts["aoi_only_or_weaker_candidates"] > 0
        weak_scene_items += counts["scene_pair_only_or_weaker_candidates"] > 0
        exact = matches[0] if matches else None
        exact_matches += exact is not None
        report = item["report"]
        processor = definition.get("rerun_processor")
        if not isinstance(processor, dict):
            raise SatelliteCalibrationRereviewError("rerun processor binding is missing")
        for label, descriptor in processor.get("files", {}).items():
            _input_file(project_root, descriptor, f"rerun processor {label}")
        rerun_spec = {
            "aoi_bbox_wgs84": item["aoi"],
            "blind_item_id": item["blind_item_id"],
            "entity": report["entity"],
            "execution": {
                "arguments": [
                    "--baseline-stac",
                    item["catalog_artifacts"]["baseline-response.json"]["path"],
                    "--baseline-id",
                    report["baseline"]["id"],
                    "--current-stac",
                    item["catalog_artifacts"]["current-response.json"]["path"],
                    "--current-id",
                    report["current"]["id"],
                    "--bbox",
                    ",".join(str(value) for value in item["aoi"]),
                    "--entity-id",
                    report["entity"]["id"],
                    "--entity-name",
                    report["entity"]["name"],
                    "--output-dir",
                    "{job_output_dir}",
                    "--minimum-component-area-m2",
                    str(processor["minimum_component_area_m2"]),
                ],
                "script": processor["files"]["script"]["path"],
            },
            "historical_identity_sha256": item["identity_sha256"],
            "historical_queue_id": identity["queue_id"],
            "processor": processor,
            "schema_version": 1,
            "selected_scenes": {
                "baseline": {
                    "id": report["baseline"]["id"],
                    "stac_item_sha256": report["baseline"]["stac_item_sha256"],
                },
                "current": {
                    "id": report["current"]["id"],
                    "stac_item_sha256": report["current"]["stac_item_sha256"],
                },
            },
            "source_catalog_artifacts": item["catalog_artifacts"],
            "status": "ready_for_exact_algorithm_v2_rerun",
        }
        rerun_spec_sha256 = _sha256(_canonical_line(rerun_spec))
        rerun_specs.append(rerun_spec)
        reviewer_rows.append(
            {
                "algorithm_v2_output": (
                    {
                        "artifact": exact["report"],
                        "algorithm_version": TARGET_ALGORITHM,
                        "run_id": exact["run_id"],
                    }
                    if exact
                    else None
                ),
                "aoi_bbox_wgs84": item["aoi"],
                "blind_item_id": item["blind_item_id"],
                "entity": report["entity"],
                "historical_input_anchor": {
                    "baseline": {
                        "datetime": report["baseline"]["datetime"],
                        "id": report["baseline"]["id"],
                        "stac_item_sha256": report["baseline"]["stac_item_sha256"],
                    },
                    "current": {
                        "datetime": report["current"]["datetime"],
                        "id": report["current"]["id"],
                        "stac_item_sha256": report["current"]["stac_item_sha256"],
                    },
                },
                "mapping_status": (
                    "exact_algorithm_v2_output_available"
                    if exact
                    else "unavailable_no_exact_identity_output"
                ),
                "non_substitution_audit": counts,
                "preparation_only": True,
                "review_material_status": (
                    "ready_for_blind_review"
                    if exact
                    else "blocked_algorithm_v2_output_unavailable"
                ),
                "rerun_spec_sha256": rerun_spec_sha256,
                "schema_version": 1,
            }
        )
        row = item["row"]
        lineage_rows.append(
            {
                "blind_item_id": item["blind_item_id"],
                "historical_identity": identity,
                "historical_identity_sha256": item["identity_sha256"],
                "historical_provenance": {
                    "calibration_record_line": item["line_number"],
                    "report": {"path": item["report_path"], **item["report_checkpoint"]},
                    "review": {"path": item["review_path"], **item["review_checkpoint"]},
                    "source_run": row["source_run"],
                },
                "prior_analyst_provenance": {
                    "decision": row["decision"],
                    "outcome": row["outcome"],
                    "reviewed_at": row["reviewed_at"],
                },
                "policy": {
                    "may_seed_algorithm_v2_decision": False,
                    "may_join_before_blind_review_closes": False,
                    "provenance_only": True,
                },
                "schema_version": 1,
            }
        )
    expected = definition.get("expected_mapping_counts", {})
    observed = {
        "exact_v2_outputs": exact_matches,
        "historical_items_with_aoi_only_or_weaker_overlap": weak_aoi_items,
        "historical_items_with_scene_pair_only_or_weaker_overlap": weak_scene_items,
    }
    if observed != expected:
        raise SatelliteCalibrationRereviewError("mapping count mismatch")
    if exact_matches != 0:
        raise SatelliteCalibrationRereviewError("this preparation release expects zero exact outputs")
    summary = {
        "algorithm_v2_outputs_available": exact_matches,
        "analyst_decisions_performed": 0,
        "blind_items_blocked_missing_output": len(historical) - exact_matches,
        "blind_items_ready": exact_matches,
        "generated_at": definition["generated_at"],
        "historical_algorithm": HISTORICAL_ALGORITHM,
        "historical_items": len(historical),
        "labels_reused": 0,
        "mapping_audit": {
            **observed,
            "weak_matches_substituted": 0,
        },
        "preparation_id": definition["preparation_id"],
        "preparation_only": True,
        "numerical_reruns_executed": 0,
        "rerun_inputs_validated": len(rerun_specs),
        "rerun_specs_ready": len(rerun_specs),
        "schema_version": 1,
        "target_algorithm": TARGET_ALGORITHM,
        "unique_aois": len({tuple(item["aoi"]) for item in historical}),
        "v2_calibration_claimed": False,
        "v2_completed_outputs_searched": len(v2_outputs),
        "v2_frozen_runs_searched": sum(
            value["algorithm_version"] == TARGET_ALGORITHM for value in run_inventory
        ),
    }
    inventory_document = {
        "exact_identity_rule": [
            "queue_id",
            "entity_id",
            "aoi_bbox_wgs84",
            "baseline_stac_item_sha256",
            "current_stac_item_sha256",
        ],
        "frozen_runs": run_inventory,
        "generated_at": definition["generated_at"],
        "historical_inputs": historical_inputs,
        "non_substitution_policy": "Any partial-key overlap is audit evidence only and is never a corresponding output.",
        "preparation_id": definition["preparation_id"],
        "schema_version": 1,
    }
    readme = f"""# Algorithm-v2 calibration re-review preparation

This immutable release prepares {len(historical)} historical algorithm-v1 items for a future blind re-review. It contains {exact_matches} exact algorithm-v2 outputs, so all {len(historical)} queue rows are blocked. No analyst decisions were performed, no earlier labels were reused, and this is not algorithm-v2 calibration.

`reviewer-queue.jsonl` is the only reviewer-facing item queue. It exposes exact AOIs and input scene anchors but no historical queue IDs, review artifacts, decisions, or outcomes. A row becomes reviewable only after an algorithm-v2 output matching every field in the identity rule is bound.

`rerun-specs.jsonl` is an operator-facing set of {len(rerun_specs)} executable specifications. Each specification binds the original queue identity, entity, AOI, exact selected STAC feature hashes, all three source catalog artifacts, the unchanged algorithm-v2 processor hashes, and a deterministic argument vector. Validate these inputs before numerical execution. This file is not a reviewer surface.

`run-inventory.json` checkpoints every frozen change-run manifest searched and the processor code hashes embedded in each run. Partial AOI or scene-pair overlaps are counted only to document why substitution was rejected.

`sealed/lineage.jsonl` is provenance-only and mode `0400` under a mode `0500` directory. Do not distribute it to reviewers or join it before the blind review closes. Filesystem modes are an operational seal, not encryption.

Validate every local input without opening imagery:

```
python3 scripts/run_satellite_calibration_reruns.py --validate-inputs-only --preparation-dir satellite_calibration_rereview/2026-07-19-algorithm-v2-preparation-v1 --definition sources/satellite-calibration-rereview-2026-07-19-algorithm-v2-preparation-v1.json
```

Numerical execution is deliberately separate and bounded. Use the established runtime command `uv run --python 3.12 --with numpy==2.5.1 --with pillow==12.3.0 --with rasterio==1.5.0 python scripts/run_satellite_calibration_reruns.py`; the runner additionally invokes its frozen processor snapshot with `-B` and `PYTHONDONTWRITEBYTECODE=1`. An explicit one-item immutable shard uses `--start-index 0 --max-jobs 1` plus a new `--output-dir`. Validate a published shard offline under the same pinned runtime with the same preparation and definition plus `--validate-only --output-dir PATH`.
""".encode("utf-8")
    attribution = (
        "Historical and current change evidence: Contains modified Copernicus "
        "Sentinel data, processed by ESA and accessed through Element 84 Earth "
        "Search. This bundle contains metadata and hashes only; it adds no imagery "
        "license or analyst decision.\n"
    ).encode("utf-8")
    public_payloads = {
        "ATTRIBUTION.txt": attribution,
        "README.md": readme,
        "reviewer-queue.jsonl": b"".join(_canonical_line(row) for row in reviewer_rows),
        "rerun-specs.jsonl": b"".join(_canonical_line(row) for row in rerun_specs),
        "run-inventory.json": _canonical_json(inventory_document),
        "summary.json": _canonical_json(summary),
    }
    sealed_payloads = {
        "sealed/lineage.jsonl": b"".join(_canonical_line(row) for row in lineage_rows)
    }
    module_path = Path(__file__).resolve()
    script_path = project_root / "scripts" / "build_satellite_calibration_rereview.py"
    runner_module_path = project_root / "datacenter_atlas" / "satellite_calibration_rerun.py"
    runner_script_path = project_root / "scripts" / "run_satellite_calibration_reruns.py"
    builder_files = {
        str(path.relative_to(project_root)): _checkpoint(path)
        for path in (module_path, script_path, runner_module_path, runner_script_path)
    }
    outputs = {
        name: {
            "bytes": len(raw),
            "mode": "0400" if name.startswith("sealed/") else "0444",
            "sha256": _sha256(raw),
        }
        for name, raw in sorted({**public_payloads, **sealed_payloads}.items())
    }
    definition_raw = definition_path.read_bytes()
    manifest = {
        "builder_files": builder_files,
        "counts": summary,
        "definition": {
            "bytes": len(definition_raw),
            "filename": definition_path.name,
            "sha256": _sha256(definition_raw),
        },
        "format": FORMAT,
        "generated_at": definition["generated_at"],
        "outputs": outputs,
        "preparation_id": definition["preparation_id"],
        "schema_version": 1,
        "sealed_lineage_policy": {
            "directory_mode": "0500",
            "file_mode": "0400",
            "not_encrypted": True,
            "reviewer_distribution_allowed": False,
        },
    }
    manifest_raw = _canonical_json(manifest)
    public_payloads["manifest.json"] = manifest_raw
    public_payloads["manifest.sha256"] = (
        f"{_sha256(manifest_raw)}  manifest.json\n".encode("ascii")
    )
    return public_payloads, sealed_payloads, manifest


def _keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _keys(child)


def _validate_tree(output: Path) -> None:
    if not output.is_dir() or output.is_symlink():
        raise SatelliteCalibrationRereviewError("output is not a regular directory")
    if output.stat().st_mode & 0o777 != 0o555:
        raise SatelliteCalibrationRereviewError("output directory mode must be 0555")
    actual: set[str] = set()
    for path in output.rglob("*"):
        if path.is_symlink():
            raise SatelliteCalibrationRereviewError("release contains a symlink")
        relative = path.relative_to(output).as_posix()
        if path.is_dir():
            if relative != "sealed" or path.stat().st_mode & 0o777 != 0o500:
                raise SatelliteCalibrationRereviewError("release directory tree is invalid")
            continue
        actual.add(relative)
        expected_mode = 0o400 if relative.startswith("sealed/") else 0o444
        if path.stat().st_mode & 0o777 != expected_mode:
            raise SatelliteCalibrationRereviewError(f"{relative} mode mismatch")
    if actual != BUNDLE_FILES:
        raise SatelliteCalibrationRereviewError("release file set is not closed")


def validate_satellite_calibration_rereview(
    output: Path, *, definition_path: Path
) -> dict[str, Any]:
    """Validate the closed tree and reproduce every byte from frozen inputs."""

    _validate_tree(output)
    public, sealed, expected_manifest = _render(definition_path)
    for relative, expected in {**public, **sealed}.items():
        actual = (output / relative).read_bytes()
        if actual != expected:
            raise SatelliteCalibrationRereviewError(f"{relative} does not reproduce")
    rows = _jsonl(output / "reviewer-queue.jsonl", "reviewer queue")
    forbidden = FORBIDDEN_REVIEW_KEYS & {key for row in rows for key in _keys(row)}
    if forbidden:
        raise SatelliteCalibrationRereviewError("reviewer queue leaks historical keys")
    queue_raw = (output / "reviewer-queue.jsonl").read_bytes().lower()
    if b'"retain"' in queue_raw or b'"reject"' in queue_raw:
        raise SatelliteCalibrationRereviewError("reviewer queue leaks historical labels")
    manifest = _json(output / "manifest.json", "release manifest")
    if manifest != expected_manifest:
        raise SatelliteCalibrationRereviewError("manifest semantic mismatch")
    return manifest


def write_satellite_calibration_rereview(
    definition_path: Path, output: Path, *, freeze: bool = True
) -> dict[str, Any]:
    """Write a new release, refusing to replace any existing path."""

    if output.exists() or output.is_symlink():
        raise SatelliteCalibrationRereviewError("output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    public, sealed, manifest = _render(definition_path)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        (staging / "sealed").mkdir()
        for relative, raw in {**public, **sealed}.items():
            path = staging / relative
            path.write_bytes(raw)
        if freeze:
            for path in staging.iterdir():
                if path.is_file():
                    os.chmod(path, 0o444)
            os.chmod(staging / "sealed" / "lineage.jsonl", 0o400)
            os.chmod(staging / "sealed", 0o500)
            os.chmod(staging, 0o555)
        os.replace(staging, output)
    except Exception:
        if staging.exists():
            os.chmod(staging, 0o755)
            sealed_dir = staging / "sealed"
            if sealed_dir.exists():
                os.chmod(sealed_dir, 0o700)
            shutil.rmtree(staging)
        raise
    validate_satellite_calibration_rereview(output, definition_path=definition_path)
    return manifest
