#!/usr/bin/env python3
"""Build a research queue, NOT a core release or a physical-site acceptance list.

Generation and --check require the ignored, hash-pinned v97 construction CSV.
--check regenerates and compares exact bytes; it never overwrites. The default
write also refuses an existing output. --validate-snapshot works without v97:
it checks the independently pinned tracked snapshot, its frozen v0.17 baseline,
and all referenced curated source files. It does not claim to regenerate v97.

Only exact project-key AND derived status-evidence UUID matches recover source
documents. All matching variants are retained; a parent is resolved only when
every match supplies the same campus key. Campus-key grouping detects exact-key
duplicates, not geographic aliases. Neither project rows nor these unreviewed
groups are counted as new physical sites. No coordinates are promoted here.

Examples (from the repository root):
  python scripts/build_expansion_200_inventory.py --check
  python scripts/build_expansion_200_inventory.py --validate-snapshot
  python scripts/build_expansion_200_inventory.py --output /tmp/new-inventory.json
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from datetime import date
import hashlib
import io
import json
from pathlib import Path
from typing import Any
import uuid


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_PATH = "releases/2026-07-22-open-seed-v97/construction_pipeline.csv"
BASELINE_DIR = "verified_construction_core/2026-08-20-preview-v0.17"
OUTPUT_PATH = "research/expansion-200/candidate-inventory.json"
REFERENCE_DATE = date(2026, 8, 20)
MAX_STATUS_AGE_DAYS = 90
ATLAS_NAMESPACE = uuid.UUID("aa3d9079-c7f8-4a77-84d9-75ae2097549f")
# Independent of the inventory's self-reported input hashes. Updated only after
# reviewing a newly generated snapshot, never by the generator itself.
SNAPSHOT_SHA256 = "2cb184a58df3fb09f1c64595ba2eb7f35a45c009899e62b4652e03484c53f2f0"
PHYSICAL_STATUSES = frozenset(
    {
        "civil_works", "commissioning", "expansion", "foundations",
        "mep_electrical", "shell", "site_preparation", "under_construction",
    }
)
AUTHORITATIVE_STATUS_METHODS = frozenset(
    {
        "authoritative_construction_start", "authoritative_physical_status_update",
        "government_record", "physical_observation",
    }
)
PIPELINE_FIELDS = (
    "stable_key", "entity_kind", "name", "country", "status", "status_as_of",
    "status_method", "status_evidence_id", "source_url", "source_publisher",
)


class InventoryError(ValueError):
    """An input or a research-only accounting invariant is not satisfied."""


@dataclass(frozen=True)
class InputPins:
    pipeline_sha256: str = (
        "b39aed7653872bff0d0841ece2968f69e9d1d76bd07a242d103ab50e9b78c12f"
    )
    baseline_manifest_sha256: str = (
        "49cf79185742a2bd718a83683c924574ba8db4de1289d1228e56c5865154c8fc"
    )
    baseline_projects: int = 103
    baseline_sites: int = 100
    pipeline_rows: int = 531
    pipeline_nonprojects: int = 49
    selected_pipeline_projects: int = 97


DEFAULT_PINS = InputPins()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pinned_bytes(path: Path, expected: str) -> bytes:
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise InventoryError(f"required input missing: {path}") from exc
    if sha256(data) != expected:
        raise InventoryError(f"input SHA-256 differs: {path}")
    return data


def csv_rows(data: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8"), newline="")))


def unique_keys(rows: list[dict[str, str]], field: str) -> set[str]:
    keys = {row.get(field, "") for row in rows}
    if "" in keys or len(keys) != len(rows):
        raise InventoryError(f"missing or duplicate {field}")
    return keys


def load_baseline(root: Path, pins: InputPins) -> dict[str, Any]:
    relative = f"{BASELINE_DIR}/manifest.json"
    manifest = json.loads(pinned_bytes(root / relative, pins.baseline_manifest_sha256))
    counts = manifest["counts"]
    if (counts["projects"], counts["physical_sites"]) != (
        pins.baseline_projects, pins.baseline_sites,
    ):
        raise InventoryError("baseline counts differ")
    tables = {}
    for name in ("projects.csv", "sites.csv"):
        spec = manifest["files"][name]
        data = pinned_bytes(root / BASELINE_DIR / name, spec["sha256"])
        if len(data) != spec["bytes"]:
            raise InventoryError(f"baseline byte count differs: {name}")
        tables[name] = csv_rows(data)
    projects = unique_keys(tables["projects.csv"], "project_stable_key")
    sites = unique_keys(tables["sites.csv"], "physical_site_stable_key")
    if len(projects) != pins.baseline_projects or len(sites) != pins.baseline_sites:
        raise InventoryError("baseline table counts differ")
    if {row["physical_site_stable_key"] for row in tables["projects.csv"]} != sites:
        raise InventoryError("baseline project-to-site membership differs")
    return {
        "manifest_path": relative,
        "manifest_sha256": pins.baseline_manifest_sha256,
        "physical_sites": len(sites),
        "projects": len(projects),
        "project_stable_keys": sorted(projects),
        "physical_site_stable_keys": sorted(sites),
    }


def status_age(row: dict[str, str]) -> int | None:
    try:
        return (REFERENCE_DATE - date.fromisoformat(row["status_as_of"])).days
    except (KeyError, ValueError):
        return None


def first_failure(row: dict[str, str], selected: set[str]) -> str:
    """Mirror the frozen Aug-20 core policy, not today's apparent status."""
    if row.get("entity_kind") != "project":
        return "entity_kind_not_project"
    if row.get("status") not in PHYSICAL_STATUSES:
        return "status_not_physical"
    if row.get("status_method") not in AUTHORITATIVE_STATUS_METHODS:
        return "status_method_not_authoritative"
    age = status_age(row)
    if age is None:
        return "invalid_status_date"
    if age < 0 or age > MAX_STATUS_AGE_DAYS:
        return "status_outside_90_day_window"
    if row.get("stable_key") not in selected:
        return "not_in_reviewed_site_geometry_allowlist"
    return "selected"


def evidence_id(evidence: dict[str, Any]) -> str | None:
    if not evidence.get("key") or not evidence.get("content_hash"):
        return None
    parts = ("evidence", "curated-official", evidence["key"], evidence["content_hash"])
    return str(uuid.uuid5(ATLAS_NAMESPACE, "|".join(parts)))


def source_index(root: Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for path in sorted((root / "sources").glob("curated-*.json")):
        raw = path.read_bytes()
        document = json.loads(raw)
        project = document.get("project") or {}
        key = project.get("stable_key")
        if not key:
            continue
        campus = document.get("campus") or {}
        for evidence in document.get("evidence", []):
            identifier = evidence_id(evidence)
            if identifier is None:
                continue
            index[(key, identifier)].append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": sha256(raw),
                    "bytes": len(raw),
                    "parent_campus_key": campus.get("stable_key"),
                    "status_evidence_key": evidence["key"],
                    "status_evidence_content_hash": evidence["content_hash"],
                    "evidence_source_url": evidence.get("source_url"),
                    "evidence_publisher": evidence.get("publisher"),
                    "lifecycle_records": [
                        item for item in document.get("lifecycle", [])
                        if item.get("entity") == "project"
                        and item.get("evidence_key") == evidence["key"]
                    ],
                }
            )
    return index


def summarize(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    parents = {item["parent_campus_key"] for item in candidates if item["parent_campus_key"]}
    eligible = [
        item for item in candidates
        if item["first_failure"] == "not_in_reviewed_site_geometry_allowlist"
        and item["parent_campus_already_in_baseline"] is False
    ]
    return {
        "candidate_project_rows": len(candidates),
        "accepted_new_physical_sites": 0,
        "verified_additional_physical_sites": 0,
        "first_failure_counts": dict(sorted(Counter(
            item["first_failure"] for item in candidates
        ).items())),
        "priority_counts": dict(sorted(Counter(item["priority"] for item in candidates).items())),
        "exact_parent_key_groups_not_site_count": len(parents),
        "parent_unresolved_project_rows": sum(item["parent_campus_key"] is None for item in candidates),
        "already_in_baseline_parent_project_rows": sum(
            item["parent_campus_already_in_baseline"] is True for item in candidates
        ),
        "multiple_source_variant_project_rows": sum(len(item["source_matches"]) > 1 for item in candidates),
        "geometry_queue_rows_outside_baseline_by_exact_parent_key": len(eligible),
        "geometry_queue_parent_key_groups_outside_baseline_not_site_count": len(
            {item["parent_campus_key"] for item in eligible}
        ),
    }


def build_inventory(root: Path = ROOT, pins: InputPins = DEFAULT_PINS) -> dict[str, Any]:
    baseline = load_baseline(root, pins)
    raw = pinned_bytes(root / PIPELINE_PATH, pins.pipeline_sha256)
    rows = csv_rows(raw)
    unique_keys(rows, "stable_key")
    if any(not set(PIPELINE_FIELDS).issubset(row) for row in rows):
        raise InventoryError("pipeline columns differ")
    selected = set(baseline["project_stable_keys"])
    site_keys = set(baseline["physical_site_stable_keys"])
    nonprojects = [row for row in rows if row["entity_kind"] != "project"]
    selected_rows = [row for row in rows if row["entity_kind"] == "project" and row["stable_key"] in selected]
    if (len(rows), len(nonprojects), len(selected_rows)) != (
        pins.pipeline_rows, pins.pipeline_nonprojects, pins.selected_pipeline_projects,
    ):
        raise InventoryError("pipeline row accounting differs")
    index = source_index(root)
    candidates = []
    source_inputs = {}
    for row in sorted(rows, key=lambda item: item["stable_key"]):
        if row["entity_kind"] != "project" or row["stable_key"] in selected:
            continue
        matches = index.get((row["stable_key"], row["status_evidence_id"]), [])
        parent_options = {match["parent_campus_key"] for match in matches}
        parent = next(iter(parent_options)) if len(parent_options) == 1 and None not in parent_options else None
        refs = []
        for match in matches:
            source_inputs[match["path"]] = {
                key: match[key] for key in ("path", "sha256", "bytes")
            }
            refs.append(
                {
                    key: value for key, value in match.items()
                    if key not in {"sha256", "bytes", "lifecycle_records"}
                } | {
                    "exact_lifecycle_tuple_present": any(
                        item.get("value") == row["status"]
                        and item.get("as_of_date") == row["status_as_of"]
                        and item.get("method") == row["status_method"]
                        for item in match["lifecycle_records"]
                    ),
                }
            )
        failure = first_failure(row, selected)
        age = status_age(row)
        priority = {
            "not_in_reviewed_site_geometry_allowlist": "missing_geometry",
            "status_not_physical": "physical_status_evidence_required",
            "status_method_not_authoritative": "authoritative_status_evidence_required",
            "invalid_status_date": "status_date_review_required",
            "status_outside_90_day_window": "stale_status" if age is not None and age > 90 else "after_lifecycle_cutoff",
        }[failure]
        reasons = ["geographic_alias_and_physical_site_scope_review_not_performed"]
        if not matches:
            reasons.append("exact_project_and_status_evidence_source_unresolved")
        elif parent is None:
            reasons.append("parent_campus_missing_or_conflicting_across_matching_sources")
        if len(matches) > 1:
            reasons.append("multiple_matching_curated_source_variants_retained")
        if parent in site_keys:
            reasons.append("exact_parent_campus_key_already_in_frozen_baseline")
            priority = "existing_baseline_site_scope_review"
        candidates.append(
            {
                "project_stable_key": row["stable_key"],
                "name": row["name"],
                "country": row["country"],
                "status": row["status"],
                "status_date": row["status_as_of"],
                "status_age_days_at_cutoff": age,
                "status_method": row["status_method"],
                "status_evidence_id": row["status_evidence_id"],
                "source_url": row["source_url"],
                "publisher": row["source_publisher"],
                "first_failure": failure,
                "priority": priority,
                "parent_campus_key": parent,
                "parent_campus_already_in_baseline": parent in site_keys if parent else None,
                "source_match_resolution": "unresolved" if not matches else "unique_document" if len(matches) == 1 else "multiple_documents",
                "source_matches": refs,
                "duplicate_and_scope_reasons": reasons,
                "accepted_into_core": False,
                "verified_new_physical_site": False,
            }
        )
    siblings: dict[str, list[str]] = defaultdict(list)
    for item in candidates:
        if item["parent_campus_key"]:
            siblings[item["parent_campus_key"]].append(item["project_stable_key"])
    for item in candidates:
        item["same_parent_candidate_project_keys"] = [
            key for key in siblings[item["parent_campus_key"]]
            if key != item["project_stable_key"]
        ]
        if item["same_parent_candidate_project_keys"]:
            item["duplicate_and_scope_reasons"].append("shared_exact_parent_key_with_other_candidate_projects")
    return {
        "format": "datacenter-atlas-expansion-200-research-inventory-v1",
        "purpose": "Research toward 100 additional distinct physical sites beyond frozen v0.17; this queue accepts none.",
        "accepted_into_core": False,
        "lifecycle_reference_date": REFERENCE_DATE.isoformat(),
        "maximum_status_age_days": MAX_STATUS_AGE_DAYS,
        "baseline": baseline,
        "input_pipeline": {"path": PIPELINE_PATH, "bytes": len(raw), "sha256": pins.pipeline_sha256},
        "input_source_documents": [source_inputs[key] for key in sorted(source_inputs)],
        "accounting": {
            "input_pipeline_rows": len(rows),
            "excluded_nonproject_rows": len(nonprojects),
            "excluded_baseline_selected_project_rows": len(selected_rows),
            "baseline_post_v97_projects": len(selected) - len(selected_rows),
            "candidate_project_rows": len(candidates),
        },
        "summary": summarize(candidates),
        "limitations": [
            "Generation and --check require the ignored hash-pinned v97 pipeline; --validate-snapshot does not regenerate it.",
            "The queue retains historical pipeline status, not a present-day assertion. Later observations cannot move the Aug-20 cutoff.",
            "Baseline selection is by frozen project membership, preserving reviewed lifecycle overrides instead of re-evaluating selected raw rows.",
            "Only nonselected project rows are included; 49 nonproject rows are not promoted or counted as projects.",
            "Exact parent keys are unreviewed research groups, not verified distinct physical sites; aliases and constituent-building scope remain unresolved.",
            "Source variants are matched by project key and status evidence UUID; mismatching lifecycle tuples are disclosed, not silently preferred.",
            "No geometry, lifecycle, role, workload, power, energy or capacity is promoted into the core by this research inventory.",
        ],
        "candidates": candidates,
    }


def validate_snapshot(
    path: Path, root: Path = ROOT, pins: InputPins = DEFAULT_PINS,
    expected_sha256: str = SNAPSHOT_SHA256,
) -> dict[str, Any]:
    """Check portable frozen bytes and references; not a pipeline regeneration."""
    payload = json.loads(pinned_bytes(path, expected_sha256))
    if payload["baseline"] != load_baseline(root, pins):
        raise InventoryError("snapshot baseline differs")
    if payload["input_pipeline"]["sha256"] != pins.pipeline_sha256:
        raise InventoryError("snapshot pipeline pin differs")
    if payload.get("accepted_into_core") is not False or any(
        item.get("accepted_into_core") is not False
        or item.get("verified_new_physical_site") is not False
        for item in payload["candidates"]
    ):
        raise InventoryError("snapshot must be research-only")
    if payload["summary"] != summarize(payload["candidates"]):
        raise InventoryError("snapshot summary differs")
    for spec in payload["input_source_documents"]:
        source_path = Path(spec["path"])
        if source_path.is_absolute() or ".." in source_path.parts or source_path.parts[0] != "sources":
            raise InventoryError("nonportable source path")
        raw = pinned_bytes(root / source_path, spec["sha256"])
        if len(raw) != spec["bytes"]:
            raise InventoryError("source byte count differs")
    return payload


def emit(path: Path, payload: bytes, check: bool = False) -> None:
    if check:
        if not path.is_file() or path.read_bytes() != payload:
            raise InventoryError(f"inventory differs or is missing: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
    except FileExistsError as exc:
        raise InventoryError(f"refusing to overwrite existing inventory: {path}; use --check") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=ROOT / OUTPUT_PATH)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true", help="regenerate with v97 and compare exact bytes, without writing")
    modes.add_argument("--validate-snapshot", action="store_true", help="corpus-free frozen snapshot and source-pin verification only")
    args = parser.parse_args()
    try:
        if args.validate_snapshot:
            result = validate_snapshot(args.output)
        else:
            result = build_inventory()
            emit(args.output, json_bytes(result), args.check)
        print(json.dumps(result["summary"], sort_keys=True))
    except (InventoryError, OSError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(1, f"inventory error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
