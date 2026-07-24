"""Immutable analyst review for the two reselected satellite-change jobs.

This carrier creates a separate review bundle.  It never writes into the
source change run, never mutates atlas data, and never turns imagery into an
identity, lifecycle, type, capacity, power, energy, PUE, workload, operator,
or unique-site claim.
"""

from __future__ import annotations

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
from typing import Any, Iterator, Mapping, Sequence


REVIEW_ID = "2026-07-20-open-seed-v43-active-reselected-v2-review-v1"
GENERATED_AT = "2026-07-20T09:13:00Z"
REVIEWED_AT = "2026-07-20T09:12:00Z"
DEFINITION_PATH = (
    "definitions/satellite_change_reviews/"
    "2026-07-20-open-seed-v43-active-reselected-v2-review-v1.json"
)
OUTPUT_PATH = f"satellite_change_reviews/{REVIEW_ID}"
DEFINITION_SHA256 = "7c84666520844b0e308f3d0fddb8223217648efe02c08ef134c19eb31a16a161"

SOURCE_RUN_PATH = (
    "satellite_change_runs/2026-07-20-open-seed-v43-active-reselected-v2-001"
)
SOURCE_MANIFEST = {
    "bytes": 23_729,
    "path": f"{SOURCE_RUN_PATH}/batch-manifest.json",
    "sha256": "cfafe8788fa2f7bf4321947f01b1b95a7454569c73e286009a296adc93515112",
}
SOURCE_TREE = {
    "directories": 6,
    "directory_mode": "0555",
    "file_bytes": 3_651_687,
    "file_mode": "0444",
    "files": 13,
    "inventory_sha256": (
        "ce8d252c12a68d9908a0ef636843cf2acdcb5ee1a717c6d9a8f53b4670aa88d2"
    ),
    "path": SOURCE_RUN_PATH,
    "schema_version": 1,
}

QUEUE_IDS = (
    "satq-cef871428da247c3ecfadec6",
    "satq-d0a872a7aee9f9f54a8631ef",
)

SCOPE = {
    "atlas_claim_created": False,
    "atlas_mutation": False,
    "automated_promotion_allowed": False,
    "construction_area_claim_created": False,
    "data_centre_type_claim_created": False,
    "decision_applies_only_to_imagery_site_promotion": True,
    "energy_claim_created": False,
    "identity_claim_created": False,
    "imagery_change_is_construction_truth": False,
    "it_capacity_claim_created": False,
    "lifecycle_status_claim_created": False,
    "manual_review_completed": True,
    "operating_status_claim_created": False,
    "operator_claim_created": False,
    "power_claim_created": False,
    "pue_claim_created": False,
    "separately_sourced_construction_facts_negated": False,
    "source_change_artifacts_copied": False,
    "unique_site_claim_created": False,
    "workload_claim_created": False,
}

_SOURCE_LINEAGE_SHA256 = {
    "catalog_batches": "f2cdf041540c1e0092f185254628ca6fdbbc706829c71d99831a1b7a94480b63",
    "catalog_reselection_v2": (
        "1104ae4778e98364466227eaeeb62fc23c68311962c5b1a6d84e6b0e62b2f35e"
    ),
    "processor": "beb014db43ac6822b7ee356d1096ad6f2dd097f59221ec37c8e239660c8084d6",
    "queue_bundle": "6da24c2e84d27c0f7118718f512bdfacf9322d080a8bedc7bf24373f345c5ded",
}

_JOB_LINEAGE_SHA256 = {
    "satq-cef871428da247c3ecfadec6": {
        "baseline": "61af7b3037b41ce56c720cd080d93fc8f2628b62aa9bc35e1eea0cd12f2e9d03",
        "catalog_reselection_v2": (
            "eed75c81f831a101e48bbab5e1bdf9b944ed4c47b236c748bf85259bfbf4db36"
        ),
        "catalog_source": "57127f8a533d6062deb1a1396a9de18261308df3b288aa6d42f7cb4e9b0d1e07",
        "change_job": "222522e2477a14eb4bf6f356ec1132d4cb6badb5b3f8464c907a749bcde71ae6",
        "current": "1ac9d79d16f750544f09be6c006463ddac6112dc950a3fcf513ce1e49ec13a29",
        "report_source": "ad3322c0cb2c6f4f62aefa635b2aec975638ce860ba23da02638b5f48b13e4b8",
    },
    "satq-d0a872a7aee9f9f54a8631ef": {
        "baseline": "e065112e6da048cd96a1f7146eabf32697cd93b206781153f8586f16741201e2",
        "catalog_reselection_v2": (
            "ba4bb0260bdac3ecb52abf52024557be0022e936c55ab5f4096508873dd2b1a2"
        ),
        "catalog_source": "8783a894da57a8879bac28158d097c76bb36540e7b5583d7ecc4dbe8ee72685c",
        "change_job": "4175a8e9f101720355694d58e77ad3596a57b0e5d1bc860270c682f5737ea77e",
        "current": "be240856650b4d99d2a868965aade26799a8da4b0c68db54d8172b865838c560",
        "report_source": "ad3322c0cb2c6f4f62aefa635b2aec975638ce860ba23da02638b5f48b13e4b8",
    },
}

_ARTIFACTS = {
    "satq-cef871428da247c3ecfadec6": {
        "after.png": {
            "bytes": 339_736,
            "sha256": "7a1ce3be29ed7facc0a453cb68575d7a7102c2c7e7f8bac46e81cef569870afd",
        },
        "before.png": {
            "bytes": 332_325,
            "sha256": "035abf9ed4aab3f4b9c96908e5d6452e06f1d787d803e6676edef1ce8a0deb5e",
        },
        "change-overlay.png": {
            "bytes": 342_073,
            "sha256": "8879fcea680b66917ecb7c5b22eaa4867eeac0f57dc49a3071bf0e606b7ace6c",
        },
        "change-proposals.geojson": {
            "bytes": 61_219,
            "sha256": "2b2e33649d3ca31837de6c28e0404baa3af720c19025b2688f7b943d35c858d1",
        },
        "comparison.png": {
            "bytes": 703_513,
            "sha256": "86abfb901e4390dd86a32ce092c3135ec439c239ef3150c2d7270480f963c5ad",
        },
        "report.json": {
            "bytes": 6_672,
            "sha256": "cd493abb67e3048a0ff35fd191f1fd558474328e68e0174396c93a647f10dceb",
        },
    },
    "satq-d0a872a7aee9f9f54a8631ef": {
        "after.png": {
            "bytes": 321_821,
            "sha256": "cd594d32ff63844aa31db275437d9f4d823aeab27f72269a2b8c4e872d68cfc3",
        },
        "before.png": {
            "bytes": 319_622,
            "sha256": "9d50e66080b2df1c86bc87b7c2d83bc8a1eda7a81a0a02c3ce9f241836f6b7cc",
        },
        "change-overlay.png": {
            "bytes": 323_700,
            "sha256": "4c9bd13b789bf2c914b6c7af52ef183091f089c295c4ba91c9f5a863eefd1bc2",
        },
        "change-proposals.geojson": {
            "bytes": 183_336,
            "sha256": "fe20d9e0d39fc8050f72cd96515527b89dbf96cc62a4036d05591acbbdaad715",
        },
        "comparison.png": {
            "bytes": 687_284,
            "sha256": "de598f3c4f94e7568705956498c61549a65d2816e10fad39dbdf702aefb93a03",
        },
        "report.json": {
            "bytes": 6_657,
            "sha256": "29b5f5a2eee618df37247c1e014da4914a81610d16166ba5eb4d03b5732a9a73",
        },
    },
}

_DECISIONS = (
    {
        "decision": "reject_for_site_promotion",
        "entity": {
            "id": "627a4c00-7a7a-5c0d-9f03-a76eb10df7b3",
            "name": "Ada Infrastructure Docklands Three-Building Development",
        },
        "excluded_context": [
            "A separate pre-existing parcel-cropped evidence bundle remains outside this review and is neither accepted nor rejected here."
        ],
        "observations": [
            "The city-scale AOI contains widespread airport, water, rooftop, and surface changes.",
            "The automated proposals are not isolated to the data-centre site and cannot support imagery-based site promotion.",
        ],
        "queue_id": "satq-cef871428da247c3ecfadec6",
        "report_metrics": {
            "interpretation": "report_derived_change_mask_metadata_not_construction_area",
            "proposal_area_m2_after_component_filter": 156_800.0,
            "proposal_component_count": 11,
            "valid_pixel_fraction": 0.9752989585473198,
            "valid_pixel_percent_display": 97.53,
        },
    },
    {
        "decision": "reject_for_site_promotion",
        "entity": {
            "id": "296ce9ca-8904-5976-9226-aa9ee6b9ae70",
            "name": "NEXTDC SC2 Current Data Center Build",
        },
        "excluded_context": [],
        "observations": [
            "The mask is dominated by tidal or coastal morphology, cloud or atmospheric effects, and unrelated urban or rooftop changes.",
            "The automated proposals are not isolated to the data-centre site and cannot support imagery-based site promotion.",
        ],
        "queue_id": "satq-d0a872a7aee9f9f54a8631ef",
        "report_metrics": {
            "interpretation": "report_derived_change_mask_metadata_not_construction_area",
            "proposal_area_m2_after_component_filter": 518_200.0,
            "proposal_component_count": 29,
            "valid_pixel_fraction": 0.9159353753197771,
            "valid_pixel_percent_display": 91.59,
        },
    },
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


class SatelliteChangeReviewV1Error(ValueError):
    """Raised when review inputs, semantics, or publication fail closed."""


@dataclass(frozen=True, slots=True)
class SatelliteChangeReviewV1Bundle:
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
        raise SatelliteChangeReviewV1Error(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SatelliteChangeReviewV1Error(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise SatelliteChangeReviewV1Error(f"{label} must be a JSON object")
    return value


def _tree_inventory(root: Path, label: str) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise SatelliteChangeReviewV1Error(f"{label} must be a regular directory")
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
            raise SatelliteChangeReviewV1Error(
                f"{label} contains a symlink: {relative}"
            )
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            if mode != 0o555:
                raise SatelliteChangeReviewV1Error(
                    f"{label} directory mode changed: {relative} is {mode:04o}"
                )
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode("utf-8"))
            directories += 1
        elif path.is_file():
            if mode != 0o444:
                raise SatelliteChangeReviewV1Error(
                    f"{label} file mode changed: {relative} is {mode:04o}"
                )
            raw = path.read_bytes()
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{_sha256(raw)}\n"
                ).encode("utf-8")
            )
            files += 1
            file_bytes += len(raw)
        else:
            raise SatelliteChangeReviewV1Error(
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


def _artifact_paths(queue_id: str) -> dict[str, dict[str, Any]]:
    base = f"{SOURCE_RUN_PATH}/jobs/{queue_id}/change"
    return {
        name: {"bytes": spec["bytes"], "path": f"{base}/{name}", "sha256": spec["sha256"]}
        for name, spec in sorted(_ARTIFACTS[queue_id].items())
    }


def make_review_definition(
    decisions: Sequence[Mapping[str, Any]] | None = None,
) -> bytes:
    """Return canonical definition bytes, independent of input decision order."""

    selected = list(_DECISIONS if decisions is None else decisions)
    by_id = {str(decision.get("queue_id")): dict(decision) for decision in selected}
    if set(by_id) != set(QUEUE_IDS) or len(selected) != len(QUEUE_IDS):
        raise SatelliteChangeReviewV1Error(
            "definition decisions must contain exactly the two reviewed queue IDs"
        )
    rows = []
    for queue_id in QUEUE_IDS:
        row = dict(by_id[queue_id])
        row["input_artifacts"] = _artifact_paths(queue_id)
        row["review_method"] = (
            "completed_analyst_visual_inspection_of_before_after_comparison_overlay_"
            "and_proposals"
        )
        row["reviewed_at"] = REVIEWED_AT
        rows.append(row)
    document = {
        "decisions": rows,
        "generated_at": GENERATED_AT,
        "review_id": REVIEW_ID,
        "schema_version": 1,
        "scope": SCOPE,
        "source_change_run": {
            "closed_tree": SOURCE_TREE,
            "manifest": SOURCE_MANIFEST,
        },
    }
    return _canonical_json(document)


def _validate_definition(
    definition_path: str | Path,
) -> tuple[dict[str, Any], bytes, Path]:
    path = Path(definition_path).resolve()
    package_root = path.parents[2]
    if path != package_root / DEFINITION_PATH:
        raise SatelliteChangeReviewV1Error("review definition publication path changed")
    raw = _read_regular(path, "review definition")
    document = _json_object(raw, "review definition")
    if raw != _canonical_json(document):
        raise SatelliteChangeReviewV1Error("review definition is not canonical JSON")
    if _sha256(raw) != DEFINITION_SHA256:
        raise SatelliteChangeReviewV1Error("review definition content changed")
    if raw != make_review_definition():
        raise SatelliteChangeReviewV1Error("review definition semantics changed")
    if set(document) != {
        "decisions",
        "generated_at",
        "review_id",
        "schema_version",
        "scope",
        "source_change_run",
    }:
        raise SatelliteChangeReviewV1Error("review definition keys changed")
    if (
        document.get("review_id") != REVIEW_ID
        or document.get("generated_at") != GENERATED_AT
        or document.get("schema_version") != 1
        or document.get("scope") != SCOPE
        or document.get("source_change_run")
        != {"closed_tree": SOURCE_TREE, "manifest": SOURCE_MANIFEST}
    ):
        raise SatelliteChangeReviewV1Error(
            "review identity, source, schema, or scope changed"
        )
    for timestamp in (GENERATED_AT, REVIEWED_AT):
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed > datetime.now(UTC):
            raise SatelliteChangeReviewV1Error("review timestamp is in the future")
    decisions = document.get("decisions")
    if not isinstance(decisions, list) or [row.get("queue_id") for row in decisions] != list(QUEUE_IDS):
        raise SatelliteChangeReviewV1Error("review decisions are missing or out of order")
    for row in decisions:
        if (
            row.get("decision") != "reject_for_site_promotion"
            or row.get("reviewed_at") != REVIEWED_AT
            or row.get("input_artifacts") != _artifact_paths(row["queue_id"])
        ):
            raise SatelliteChangeReviewV1Error(
                f"review decision changed: {row.get('queue_id')}"
            )
        metrics = row.get("report_metrics")
        if not isinstance(metrics, Mapping) or metrics.get("interpretation") != (
            "report_derived_change_mask_metadata_not_construction_area"
        ):
            raise SatelliteChangeReviewV1Error("review metric interpretation changed")
    return document, raw, package_root


def _validate_source_tree(package_root: Path) -> dict[str, Any]:
    root = package_root / SOURCE_RUN_PATH
    inventory = _tree_inventory(root, "source change run")
    expected_inventory = {key: value for key, value in SOURCE_TREE.items() if key != "path"}
    if inventory != expected_inventory:
        raise SatelliteChangeReviewV1Error("source change run closed tree changed")
    expected_paths = {"batch-manifest.json"}
    for queue_id in QUEUE_IDS:
        expected_paths.update(
            f"jobs/{queue_id}/change/{name}" for name in _ARTIFACTS[queue_id]
        )
    actual_paths = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    if actual_paths != expected_paths:
        raise SatelliteChangeReviewV1Error("source change run file inventory changed")
    return inventory


def _canonical_object_sha256(value: Any) -> str:
    return _sha256(_canonical_line(value))


def _validate_false_claims(value: Mapping[str, Any], label: str) -> None:
    claim_keys = {
        "atlas_mutation",
        "data_centre_type_claim",
        "energy_claim",
        "identity_claim",
        "imagery_data_centre_type_inference",
        "imagery_energy_inference",
        "imagery_identity_inference",
        "imagery_it_capacity_inference",
        "imagery_lifecycle_inference",
        "imagery_load_inference",
        "imagery_operating_status_inference",
        "imagery_operator_inference",
        "imagery_power_inference",
        "imagery_pue_inference",
        "imagery_unique_site_inference",
        "imagery_workload_inference",
        "it_capacity_claim",
        "lifecycle_claim",
        "operating_status_claim",
        "operator_claim",
        "power_claim",
        "pue_claim",
        "workload_claim",
    }
    for key in claim_keys & set(value):
        if value[key] is not False:
            raise SatelliteChangeReviewV1Error(f"{label} enables claim: {key}")


def _source_documents(
    package_root: Path,
    definition: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    manifest_raw = _read_regular(package_root / SOURCE_MANIFEST["path"], "source manifest")
    if (
        len(manifest_raw) != SOURCE_MANIFEST["bytes"]
        or _sha256(manifest_raw) != SOURCE_MANIFEST["sha256"]
    ):
        raise SatelliteChangeReviewV1Error("source change manifest changed")
    manifest = _json_object(manifest_raw, "source manifest")
    if manifest_raw != _canonical_json(manifest):
        raise SatelliteChangeReviewV1Error("source change manifest is not canonical")
    if (
        manifest.get("pipeline") != "satellite_review_reselected_change_batch_v2"
        or manifest.get("schema_version") != 2
        or manifest.get("state") != "completed"
        or manifest.get("selection", {}).get("selected_queue_ids") != list(QUEUE_IDS)
        or manifest.get("summary", {}).get("jobs_completed") != 2
        or set(manifest.get("jobs", {})) != set(QUEUE_IDS)
    ):
        raise SatelliteChangeReviewV1Error("source change manifest contract changed")
    _validate_false_claims(manifest.get("scope", {}), "source manifest scope")
    for key, expected_sha256 in _SOURCE_LINEAGE_SHA256.items():
        if _canonical_object_sha256(manifest.get(key)) != expected_sha256:
            raise SatelliteChangeReviewV1Error(f"source lineage changed: {key}")

    reports: dict[str, dict[str, Any]] = {}
    definition_decisions = {
        row["queue_id"]: row for row in definition["decisions"]
    }
    for queue_id in QUEUE_IDS:
        job = manifest["jobs"][queue_id]
        decision = definition_decisions[queue_id]
        if (
            job.get("queue_id") != queue_id
            or job.get("state") != "completed"
            or job.get("entity") != decision["entity"]
            or job.get("artifacts") != _ARTIFACTS[queue_id]
        ):
            raise SatelliteChangeReviewV1Error(f"source job changed: {queue_id}")
        for key, expected_sha256 in _JOB_LINEAGE_SHA256[queue_id].items():
            if key in {"baseline", "current", "report_source"}:
                continue
            if _canonical_object_sha256(job.get(key)) != expected_sha256:
                raise SatelliteChangeReviewV1Error(
                    f"source job lineage changed: {queue_id} {key}"
                )
        for name, spec in decision["input_artifacts"].items():
            raw = _read_regular(package_root / spec["path"], f"{queue_id} {name}")
            if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
                raise SatelliteChangeReviewV1Error(
                    f"source artifact changed: {queue_id} {name}"
                )
            if {"bytes": spec["bytes"], "sha256": spec["sha256"]} != job[
                "artifacts"
            ][name]:
                raise SatelliteChangeReviewV1Error(
                    f"source manifest artifact binding changed: {queue_id} {name}"
                )
        report_spec = decision["input_artifacts"]["report.json"]
        report_raw = _read_regular(package_root / report_spec["path"], f"{queue_id} report")
        report = _json_object(report_raw, f"{queue_id} report")
        if report_raw != _canonical_json(report):
            raise SatelliteChangeReviewV1Error(f"source report is not canonical: {queue_id}")
        if (
            report.get("algorithm_version") != "sentinel-2-l2a-change-v2"
            or report.get("entity") != decision["entity"]
            or report.get("metrics", {}).get("proposal_component_count")
            != decision["report_metrics"]["proposal_component_count"]
            or report.get("metrics", {}).get("proposal_area_m2_after_component_filter")
            != decision["report_metrics"]["proposal_area_m2_after_component_filter"]
            or report.get("metrics", {}).get("valid_pixel_fraction")
            != decision["report_metrics"]["valid_pixel_fraction"]
            or round(report["metrics"]["valid_pixel_fraction"] * 100, 2)
            != decision["report_metrics"]["valid_pixel_percent_display"]
        ):
            raise SatelliteChangeReviewV1Error(f"report metrics changed: {queue_id}")
        _validate_false_claims(report.get("classification", {}), f"{queue_id} report")
        if report.get("outputs") != {
            name: _ARTIFACTS[queue_id][name]
            for name in sorted(_ARTIFACTS[queue_id])
            if name != "report.json"
        }:
            raise SatelliteChangeReviewV1Error(f"report outputs changed: {queue_id}")
        for key, source_key in (
            ("baseline", "baseline"),
            ("current", "current"),
            ("report_source", "source"),
        ):
            if (
                _canonical_object_sha256(report.get(source_key))
                != _JOB_LINEAGE_SHA256[queue_id][key]
            ):
                raise SatelliteChangeReviewV1Error(
                    f"report source lineage changed: {queue_id} {source_key}"
                )
        reports[queue_id] = report
    return manifest, reports


def _review_record(
    decision: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
    report: Mapping[str, Any],
) -> dict[str, Any]:
    queue_id = str(decision["queue_id"])
    job = source_manifest["jobs"][queue_id]
    return {
        "decision": "reject_for_site_promotion",
        "decision_scope": "imagery_site_promotion_only",
        "entity": decision["entity"],
        "excluded_context": decision["excluded_context"],
        "input_artifacts": decision["input_artifacts"],
        "observations": decision["observations"],
        "queue_id": queue_id,
        "report_metrics": decision["report_metrics"],
        "review_method": decision["review_method"],
        "reviewed_at": REVIEWED_AT,
        "schema_version": 1,
        "scope": SCOPE,
        "source_lineage": {
            "algorithm_version": report["algorithm_version"],
            "baseline": {
                key: report["baseline"][key]
                for key in ("datetime", "id", "mgrs_tile", "stac_item_sha256")
            },
            "catalog_reselection_v2_sha256": _JOB_LINEAGE_SHA256[queue_id][
                "catalog_reselection_v2"
            ],
            "catalog_source_sha256": _JOB_LINEAGE_SHA256[queue_id]["catalog_source"],
            "change_job_sha256": _JOB_LINEAGE_SHA256[queue_id]["change_job"],
            "current": {
                key: report["current"][key]
                for key in ("datetime", "id", "mgrs_tile", "stac_item_sha256")
            },
            "processor_sha256": _SOURCE_LINEAGE_SHA256["processor"],
            "report_source": report["source"],
            "source_change_manifest": SOURCE_MANIFEST,
            "source_report_sha256": job["report"]["report_sha256"],
        },
    }


def _readme_bytes() -> bytes:
    return (
        "# Analyst review of reselected satellite-change v2 outputs\n\n"
        "This immutable bundle records two completed manual visual-review decisions. "
        "Both automated masks are rejected for imagery-based site promotion because "
        "the visible changes are not isolated to the named data-centre sites.\n\n"
        "The source reports, PNGs, and GeoJSON remain in the frozen source change run; "
        "this bundle copies none of them and binds every file by path, byte count, and "
        "SHA-256. Reported component counts, proposal areas, and valid-pixel fractions "
        "are change-mask metadata, not construction areas.\n\n"
        "These decisions do not negate separately sourced construction facts and create "
        "no identity, lifecycle, operating-status, operator, type, workload, capacity, "
        "power, energy, PUE, unique-site, or atlas claim. The separate pre-existing "
        "parcel-cropped Docklands evidence bundle is outside this review.\n"
    ).encode("utf-8")


def _attribution_bytes() -> bytes:
    return (
        "Contains modified Copernicus Sentinel data 2024 and 2026.\n"
        "Catalog: Element 84 Earth Search v1.\n"
        "Dataset: Copernicus Sentinel-2 Level-2A.\n"
        "Source imagery is not copied into this review bundle; exact source artifacts "
        "remain hash-linked under their upstream terms.\n"
    ).encode("utf-8")


def build_satellite_change_review_v1(
    definition_path: str | Path,
) -> SatelliteChangeReviewV1Bundle:
    """Build deterministic review bytes from the frozen source run."""

    definition, definition_raw, package_root = _validate_definition(definition_path)
    source_inventory = _validate_source_tree(package_root)
    source_manifest, reports = _source_documents(package_root, definition)
    decisions = {row["queue_id"]: row for row in definition["decisions"]}
    review_records = [
        _review_record(decisions[queue_id], source_manifest, reports[queue_id])
        for queue_id in QUEUE_IDS
    ]
    reviews_bytes = b"".join(_canonical_line(record) for record in review_records)
    summary = {
        "counts": {
            "decisions": 2,
            "reject_for_site_promotion": 2,
            "source_artifacts_hash_bound": 12,
        },
        "decisions": [
            {
                "decision": record["decision"],
                "entity": record["entity"],
                "queue_id": record["queue_id"],
                "report_metrics": record["report_metrics"],
            }
            for record in review_records
        ],
        "generated_at": GENERATED_AT,
        "review_id": REVIEW_ID,
        "reviewed_at": REVIEWED_AT,
        "schema_version": 1,
        "scope": SCOPE,
        "source_change_run": {
            "closed_tree": {**source_inventory, "path": SOURCE_RUN_PATH},
            "manifest": SOURCE_MANIFEST,
        },
    }
    summary_bytes = _canonical_json(summary)
    readme_bytes = _readme_bytes()
    attribution_bytes = _attribution_bytes()
    output_files = {
        ATTRIBUTION_FILENAME: attribution_bytes,
        README_FILENAME: readme_bytes,
        REVIEWS_FILENAME: reviews_bytes,
        SUMMARY_FILENAME: summary_bytes,
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
        "format": "datacenter-atlas-satellite-change-analyst-review-v1",
        "generated_at": GENERATED_AT,
        "review_id": REVIEW_ID,
        "reviewed_at": REVIEWED_AT,
        "schema_version": 1,
        "scope": SCOPE,
        "source_artifacts": {
            queue_id: _artifact_paths(queue_id) for queue_id in QUEUE_IDS
        },
        "source_change_run": {
            "closed_tree": {**source_inventory, "path": SOURCE_RUN_PATH},
            "manifest": SOURCE_MANIFEST,
        },
        "source_lineage": {
            "catalog_batches": source_manifest["catalog_batches"],
            "catalog_reselection_v2": source_manifest["catalog_reselection_v2"],
            "processor": source_manifest["processor"],
            "queue_bundle": source_manifest["queue_bundle"],
            "sha256": _SOURCE_LINEAGE_SHA256,
        },
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
    return SatelliteChangeReviewV1Bundle(files=files, manifest=manifest)


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
        raise SatelliteChangeReviewV1Error(
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
    """Atomically create, but never replace, the canonical review definition."""

    root = Path(package_root).resolve()
    destination = Path(output_path).resolve()
    if destination != root / DEFINITION_PATH:
        raise SatelliteChangeReviewV1Error("definition output path changed")
    raw = make_review_definition()
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise SatelliteChangeReviewV1Error(
                f"refusing existing output: {destination}"
            )
        stage = destination.parent / f".{destination.name}.{os.getpid()}.tmp"
        try:
            _write_file(stage, raw)
            if destination.exists() or destination.is_symlink():
                raise SatelliteChangeReviewV1Error(
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


def write_satellite_change_review_v1(
    definition_path: str | Path,
    output_path: str | Path,
    *,
    freeze: bool = True,
) -> dict[str, Any]:
    """Atomically publish a frozen review bundle without replacing anything."""

    if freeze is not True:
        raise SatelliteChangeReviewV1Error("review publication requires freeze=True")
    bundle = build_satellite_change_review_v1(definition_path)
    destination = Path(output_path).resolve()
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise SatelliteChangeReviewV1Error(
                f"refusing existing output: {destination}"
            )
        stage = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        try:
            for filename, raw in sorted(bundle.files.items()):
                _write_file(stage / filename, raw)
            if destination.exists() or destination.is_symlink():
                raise SatelliteChangeReviewV1Error(
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


def validate_satellite_change_review_v1(
    output_path: str | Path,
    *,
    definition_path: str | Path,
) -> dict[str, Any]:
    """Offline-reproduce a frozen review bundle byte-for-byte."""

    directory = Path(output_path)
    if directory.is_symlink() or not directory.is_dir():
        raise SatelliteChangeReviewV1Error("review bundle must be a regular directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES:
        raise SatelliteChangeReviewV1Error("review bundle file set changed")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555 or any(
        entry.is_symlink()
        or not entry.is_file()
        or stat.S_IMODE(entry.stat().st_mode) != 0o444
        for entry in entries
    ):
        raise SatelliteChangeReviewV1Error(
            "review bundle must be frozen 0555/0444"
        )
    actual = {
        filename: _read_regular(directory / filename, f"review {filename}")
        for filename in BUNDLE_FILES
    }
    manifest = _json_object(actual[MANIFEST_FILENAME], "review manifest")
    expected_sidecar = (
        f"{_sha256(actual[MANIFEST_FILENAME])}  {MANIFEST_FILENAME}\n".encode(
            "ascii"
        )
    )
    if actual[MANIFEST_HASH_FILENAME] != expected_sidecar:
        raise SatelliteChangeReviewV1Error("review manifest sidecar changed")
    expected = build_satellite_change_review_v1(definition_path)
    if actual != expected.files:
        raise SatelliteChangeReviewV1Error(
            "review bundle differs from offline reconstruction"
        )
    if manifest != expected.manifest:
        raise SatelliteChangeReviewV1Error("review manifest semantics changed")
    return dict(expected.manifest)


__all__ = [
    "BUNDLE_FILES",
    "DEFINITION_PATH",
    "DEFINITION_SHA256",
    "GENERATED_AT",
    "OUTPUT_PATH",
    "QUEUE_IDS",
    "REVIEWED_AT",
    "REVIEW_ID",
    "SCOPE",
    "SOURCE_MANIFEST",
    "SOURCE_RUN_PATH",
    "SOURCE_TREE",
    "SatelliteChangeReviewV1Bundle",
    "SatelliteChangeReviewV1Error",
    "build_satellite_change_review_v1",
    "make_review_definition",
    "validate_satellite_change_review_v1",
    "write_review_definition",
    "write_satellite_change_review_v1",
]
