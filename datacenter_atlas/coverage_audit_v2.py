"""Publication-v4-aware coverage audit with review-only method support.

This successor keeps facility arithmetic confined to the exact federated
children.  Independently frozen review artifacts may demonstrate that a
method was exercised, but they never become child evidence, facility rows,
lifecycle observations, or promotion inputs.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any, Mapping

from . import coverage_audit as legacy
from . import federated_release_v2 as federation_v2


AUDIT_FILENAME = legacy.AUDIT_FILENAME
COVERAGE_CSV_FILENAME = legacy.COVERAGE_CSV_FILENAME
GAP_REGISTRY_FILENAME = legacy.GAP_REGISTRY_FILENAME
REPORT_FILENAME = legacy.REPORT_FILENAME
MANIFEST_FILENAME = legacy.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = legacy.MANIFEST_HASH_FILENAME
AUDIT_BUNDLE_FILES = legacy.AUDIT_BUNDLE_FILES
AUDIT_FORMAT = "datacenter-atlas-coverage-audit-v2"
GAP_FORMAT = "datacenter-atlas-gap-registry-v2"
BUNDLE_FORMAT = "datacenter-atlas-coverage-audit-bundle-v2"
SCHEMA_VERSION = 2
FROZEN_DIRECTORY_MODE = 0o555
FROZEN_FILE_MODE = 0o444

METHODOLOGY_EVIDENCE_CATEGORIES = legacy.METHODOLOGY_EVIDENCE_CATEGORIES
SATELLITE_REVIEW_FORMAT = "datacenter-atlas-satellite-change-analyst-review-v4"
SATELLITE_REVIEW_SCHEMA_VERSION = 4
SATELLITE_SUPPORT_CATEGORIES = ("computer_vision", "satellite_imagery")
SATELLITE_SUPPORT_CLASSIFICATION = "review_only_methodology_support"
LAST_OBSERVED_REVIEW_SEMANTICS = (
    "dated_last_observed_metadata_not_current_status"
)

CoverageAuditError = legacy.CoverageAuditError
CoverageAuditBundle = legacy.CoverageAuditBundle


@dataclass(frozen=True, slots=True)
class _Checkpoint:
    path: Path
    display_path: str
    bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class _MethodologySupport:
    support_id: str
    directory: Path
    display_directory: str
    definition: _Checkpoint
    manifest_filename: str
    manifest_bytes: int
    manifest_sha256: str
    summary_filename: str
    summary_bytes: int
    summary_sha256: str
    reviews_filename: str
    reviews_bytes: int
    reviews_sha256: str
    closed_tree: Mapping[str, Any]
    categories: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _AuditDefinition:
    raw: bytes
    filename: str
    audit_id: str
    as_of: str
    generated_at: str
    federation_path: Path
    expected_federation_manifest_sha256: str
    children: tuple[legacy._ChildInput, ...]
    public_benchmark: Mapping[str, Any]
    methodology_evidence_classification: Mapping[
        str, tuple[legacy._EvidenceReference, ...]
    ]
    methodology_support_artifacts: tuple[_MethodologySupport, ...]


def _nonnegative_integer(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CoverageAuditError(f"{label} must be a nonnegative integer")
    return value


def _resolve_path(definition_path: Path, value: Any, label: str) -> tuple[Path, str]:
    display = legacy._required_text(value, label)
    result = Path(display)
    if not result.is_absolute():
        result = definition_path.parent / result
    return result, display


def _artifact_checkpoint(
    value: Any,
    *,
    directory: Path,
    expected_filename: str,
    label: str,
) -> tuple[str, int, str]:
    if not isinstance(value, Mapping) or set(value) != {"file", "bytes", "sha256"}:
        raise CoverageAuditError(f"{label} checkpoint schema is invalid")
    filename = legacy._required_text(value.get("file"), f"{label} file")
    if filename != expected_filename or Path(filename).name != filename:
        raise CoverageAuditError(f"{label} file must be {expected_filename}")
    return (
        filename,
        _nonnegative_integer(value.get("bytes"), f"{label} bytes"),
        legacy._sha256_text(value.get("sha256"), f"{label} SHA-256"),
    )


def _external_checkpoint(
    definition_path: Path, value: Any, label: str
) -> _Checkpoint:
    if not isinstance(value, Mapping) or set(value) != {"path", "bytes", "sha256"}:
        raise CoverageAuditError(f"{label} checkpoint schema is invalid")
    path, display = _resolve_path(definition_path, value.get("path"), f"{label} path")
    return _Checkpoint(
        path=path,
        display_path=display,
        bytes=_nonnegative_integer(value.get("bytes"), f"{label} bytes"),
        sha256=legacy._sha256_text(value.get("sha256"), f"{label} SHA-256"),
    )


def _closed_tree(value: Any, label: str) -> dict[str, Any]:
    fields = {
        "directories",
        "directory_mode",
        "file_bytes",
        "file_mode",
        "files",
        "inventory_sha256",
        "schema_version",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise CoverageAuditError(f"{label} closed-tree schema is invalid")
    result = {
        "directories": _nonnegative_integer(
            value.get("directories"), f"{label} directory count"
        ),
        "directory_mode": legacy._required_text(
            value.get("directory_mode"), f"{label} directory mode"
        ),
        "file_bytes": _nonnegative_integer(
            value.get("file_bytes"), f"{label} file bytes"
        ),
        "file_mode": legacy._required_text(
            value.get("file_mode"), f"{label} file mode"
        ),
        "files": _nonnegative_integer(value.get("files"), f"{label} file count"),
        "inventory_sha256": legacy._sha256_text(
            value.get("inventory_sha256"), f"{label} inventory SHA-256"
        ),
        "schema_version": value.get("schema_version"),
    }
    if (
        result["schema_version"] != 1
        or result["directory_mode"] != "0555"
        or result["file_mode"] != "0444"
    ):
        raise CoverageAuditError(f"{label} closed-tree policy is invalid")
    return result


def _support_artifact(
    definition_path: Path, value: Any, position: int
) -> _MethodologySupport:
    label = f"methodology support artifact {position}"
    fields = {
        "support_id",
        "directory",
        "definition",
        "manifest",
        "summary",
        "reviews",
        "closed_tree",
        "categories",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise CoverageAuditError(f"{label} schema is invalid")
    support_id = legacy._required_text(value.get("support_id"), f"{label} support_id")
    directory, display_directory = _resolve_path(
        definition_path, value.get("directory"), f"{label} directory"
    )
    categories_value = value.get("categories")
    if (
        not isinstance(categories_value, list)
        or categories_value != list(SATELLITE_SUPPORT_CATEGORIES)
    ):
        raise CoverageAuditError(
            f"{label} categories must be the canonical satellite/CV pair"
        )
    manifest = _artifact_checkpoint(
        value.get("manifest"),
        directory=directory,
        expected_filename="manifest.json",
        label=f"{label} manifest",
    )
    summary = _artifact_checkpoint(
        value.get("summary"),
        directory=directory,
        expected_filename="summary.json",
        label=f"{label} summary",
    )
    reviews = _artifact_checkpoint(
        value.get("reviews"),
        directory=directory,
        expected_filename="analyst-reviews.jsonl",
        label=f"{label} reviews",
    )
    return _MethodologySupport(
        support_id=support_id,
        directory=directory,
        display_directory=display_directory,
        definition=_external_checkpoint(
            definition_path, value.get("definition"), f"{label} definition"
        ),
        manifest_filename=manifest[0],
        manifest_bytes=manifest[1],
        manifest_sha256=manifest[2],
        summary_filename=summary[0],
        summary_bytes=summary[1],
        summary_sha256=summary[2],
        reviews_filename=reviews[0],
        reviews_bytes=reviews[1],
        reviews_sha256=reviews[2],
        closed_tree=_closed_tree(value.get("closed_tree"), label),
        categories=tuple(categories_value),
    )


def _definition(path: Path) -> _AuditDefinition:
    raw = legacy._regular_bytes(path, "coverage audit v2 definition")
    document = legacy._json_object(raw, "coverage audit v2 definition")
    if raw != legacy._canonical_json(document):
        raise CoverageAuditError("coverage audit v2 definition must be canonical JSON")
    required = {
        "schema_version",
        "audit_id",
        "as_of",
        "generated_at",
        "federated_index",
        "children",
        "public_benchmark",
        "methodology_evidence_classification",
        "methodology_support_artifacts",
    }
    if set(document) != required or document.get("schema_version") != SCHEMA_VERSION:
        raise CoverageAuditError("coverage audit v2 definition schema is invalid")
    audit_id = legacy._audit_id(document.get("audit_id"))
    as_of = legacy._calendar_date(document.get("as_of"), "coverage audit as_of")
    generated_at, _ = legacy._canonical_timestamp(
        document.get("generated_at"), "coverage audit generated_at"
    )
    federation = document.get("federated_index")
    if not isinstance(federation, Mapping) or set(federation) != {
        "path",
        "expected_manifest_sha256",
    }:
        raise CoverageAuditError("federated_index definition is invalid")
    federation_path, _ = _resolve_path(
        path, federation.get("path"), "federated_index path"
    )
    federation_sha256 = legacy._sha256_text(
        federation.get("expected_manifest_sha256"),
        "expected federated manifest SHA-256",
    )

    children_value = document.get("children")
    if not isinstance(children_value, list) or len(children_value) < 2:
        raise CoverageAuditError("coverage audit v2 must contain at least two children")
    children: list[legacy._ChildInput] = []
    for position, value in enumerate(children_value):
        label = f"coverage child {position}"
        if not isinstance(value, Mapping) or set(value) != {
            "release_id",
            "release_path",
            "expected_manifest_sha256",
        }:
            raise CoverageAuditError(f"{label} schema is invalid")
        release_path, _ = _resolve_path(
            path, value.get("release_path"), f"{label} release_path"
        )
        children.append(
            legacy._ChildInput(
                release_id=legacy._required_text(
                    value.get("release_id"), f"{label} release_id"
                ),
                release_path=release_path,
                expected_manifest_sha256=legacy._sha256_text(
                    value.get("expected_manifest_sha256"),
                    f"{label} expected manifest SHA-256",
                ),
            )
        )
    release_ids = [child.release_id for child in children]
    release_paths = [child.release_path.resolve() for child in children]
    if release_ids != sorted(set(release_ids)) or len(release_paths) != len(
        set(release_paths)
    ):
        raise CoverageAuditError("coverage children must be sorted and unique")

    classification = legacy._methodology_evidence_classification(
        document.get("methodology_evidence_classification")
    )
    referenced_releases = {
        reference.release_id
        for references in classification.values()
        for reference in references
    }
    unknown = referenced_releases - set(release_ids)
    if unknown:
        raise CoverageAuditError(
            "methodology evidence references unknown coverage children: "
            + ", ".join(sorted(unknown))
        )

    supports_value = document.get("methodology_support_artifacts")
    if not isinstance(supports_value, list) or not supports_value:
        raise CoverageAuditError(
            "coverage audit v2 requires methodology support artifacts"
        )
    supports = tuple(
        _support_artifact(path, value, position)
        for position, value in enumerate(supports_value)
    )
    support_ids = [support.support_id for support in supports]
    support_paths = [support.directory.resolve() for support in supports]
    if support_ids != sorted(set(support_ids)) or len(support_paths) != len(
        set(support_paths)
    ):
        raise CoverageAuditError(
            "methodology support artifacts must be sorted and unique"
        )
    return _AuditDefinition(
        raw=raw,
        filename=path.name,
        audit_id=audit_id,
        as_of=as_of,
        generated_at=generated_at,
        federation_path=federation_path,
        expected_federation_manifest_sha256=federation_sha256,
        children=tuple(children),
        public_benchmark=legacy._public_benchmark(document.get("public_benchmark")),
        methodology_evidence_classification=classification,
        methodology_support_artifacts=supports,
    )


def _tree_inventory(root: Path, label: str) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise CoverageAuditError(f"{label} must be a regular directory")
    digest = hashlib.sha256()
    directories = 0
    files = 0
    file_bytes = 0
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for item in paths:
        relative = "." if item == root else item.relative_to(root).as_posix()
        if item.is_symlink():
            raise CoverageAuditError(f"{label} contains a symlink: {relative}")
        mode = stat.S_IMODE(item.lstat().st_mode)
        if item.is_dir():
            if mode != FROZEN_DIRECTORY_MODE:
                raise CoverageAuditError(
                    f"{label} directory mode changed: {relative} is {mode:04o}"
                )
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
            directories += 1
        elif item.is_file():
            if mode != FROZEN_FILE_MODE:
                raise CoverageAuditError(
                    f"{label} file mode changed: {relative} is {mode:04o}"
                )
            raw = item.read_bytes()
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{hashlib.sha256(raw).hexdigest()}\n"
                ).encode()
            )
            files += 1
            file_bytes += len(raw)
        else:
            raise CoverageAuditError(f"{label} has unsupported entry: {relative}")
    return {
        "directories": directories,
        "directory_mode": "0555",
        "file_bytes": file_bytes,
        "file_mode": "0444",
        "files": files,
        "inventory_sha256": digest.hexdigest(),
        "schema_version": 1,
    }


def _checkpoint_bytes(
    path: Path, expected_bytes: int, expected_sha256: str, label: str
) -> bytes:
    raw = legacy._regular_bytes(path, label)
    if len(raw) != expected_bytes or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise CoverageAuditError(f"{label} checkpoint does not match")
    return raw


def _canonical_jsonl(raw: bytes, label: str) -> list[dict[str, Any]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CoverageAuditError(f"{label} must be UTF-8") from error
    if not text.endswith("\n"):
        raise CoverageAuditError(f"{label} must end with a newline")
    records: list[dict[str, Any]] = []
    for position, line in enumerate(text.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise CoverageAuditError(f"{label} line {position} is invalid JSON") from error
        if not isinstance(value, dict):
            raise CoverageAuditError(f"{label} line {position} must be an object")
        expected = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        if line != expected:
            raise CoverageAuditError(f"{label} line {position} is not canonical")
        records.append(value)
    return records


def _validate_support(support: _MethodologySupport) -> dict[str, Any]:
    label = f"methodology support {support.support_id}"
    tree = _tree_inventory(support.directory, label)
    if tree != dict(support.closed_tree):
        raise CoverageAuditError(f"{label} closed tree changed")
    definition_raw = _checkpoint_bytes(
        support.definition.path,
        support.definition.bytes,
        support.definition.sha256,
        f"{label} definition",
    )
    definition_document = legacy._json_object(definition_raw, f"{label} definition")
    if definition_raw != legacy._canonical_json(definition_document):
        raise CoverageAuditError(f"{label} definition is not canonical JSON")
    manifest_raw = _checkpoint_bytes(
        support.directory / support.manifest_filename,
        support.manifest_bytes,
        support.manifest_sha256,
        f"{label} manifest",
    )
    summary_raw = _checkpoint_bytes(
        support.directory / support.summary_filename,
        support.summary_bytes,
        support.summary_sha256,
        f"{label} summary",
    )
    reviews_raw = _checkpoint_bytes(
        support.directory / support.reviews_filename,
        support.reviews_bytes,
        support.reviews_sha256,
        f"{label} reviews",
    )
    manifest = legacy._json_object(manifest_raw, f"{label} manifest")
    summary = legacy._json_object(summary_raw, f"{label} summary")
    if manifest_raw != legacy._canonical_json(manifest) or summary_raw != legacy._canonical_json(
        summary
    ):
        raise CoverageAuditError(f"{label} JSON artifacts are not canonical")
    sidecar = legacy._regular_bytes(
        support.directory / "manifest.sha256", f"{label} manifest sidecar"
    )
    expected_sidecar = (
        f"{hashlib.sha256(manifest_raw).hexdigest()}  manifest.json\n"
    ).encode("ascii")
    if sidecar != expected_sidecar:
        raise CoverageAuditError(f"{label} manifest sidecar does not match")
    if (
        manifest.get("format") != SATELLITE_REVIEW_FORMAT
        or manifest.get("schema_version") != SATELLITE_REVIEW_SCHEMA_VERSION
        or manifest.get("review_id") != support.support_id
        or summary.get("schema_version") != SATELLITE_REVIEW_SCHEMA_VERSION
        or summary.get("review_id") != support.support_id
    ):
        raise CoverageAuditError(f"{label} schema-v4 identity is invalid")
    manifest_definition = manifest.get("definition")
    if not isinstance(manifest_definition, Mapping) or (
        manifest_definition.get("bytes") != support.definition.bytes
        or manifest_definition.get("sha256") != support.definition.sha256
    ):
        raise CoverageAuditError(f"{label} definition lineage does not match")
    artifacts = manifest.get("artifacts")
    expected_artifacts = {
        support.summary_filename: (support.summary_bytes, support.summary_sha256),
        support.reviews_filename: (support.reviews_bytes, support.reviews_sha256),
    }
    if not isinstance(artifacts, Mapping):
        raise CoverageAuditError(f"{label} artifact inventory is invalid")
    for filename, (expected_bytes, expected_sha256) in expected_artifacts.items():
        checkpoint = artifacts.get(filename)
        if not isinstance(checkpoint, Mapping) or (
            checkpoint.get("bytes") != expected_bytes
            or checkpoint.get("sha256") != expected_sha256
        ):
            raise CoverageAuditError(f"{label} artifact lineage changed: {filename}")
    manifest_guardrails = manifest.get("guardrails")
    summary_guardrails = summary.get("guardrails")
    if (
        not isinstance(manifest_guardrails, Mapping)
        or not manifest_guardrails
        or any(value is not False for value in manifest_guardrails.values())
        or summary_guardrails != manifest_guardrails
        or manifest_guardrails.get("atlas_mutation") is not False
        or manifest_guardrails.get("automated_promotion_allowed") is not False
        or manifest_guardrails.get("current_status_claim_created") is not False
        or manifest_guardrails.get("lifecycle_status_claim_created") is not False
        or manifest_guardrails.get("imagery_construction_truth_claim_created")
        is not False
    ):
        raise CoverageAuditError(f"{label} guardrails must all remain false")
    if (
        manifest.get("job_counts") != {"R": 11, "T": 44, "U": 19}
        or summary.get("job_counts") != {"R": 11, "T": 44, "U": 19}
        or summary.get("view_counts") != {"R": 11, "T": 41, "U": 19}
        or summary.get("counts")
        != {"jobs": 74, "source_artifacts_hash_bound": 444, "views": 71}
    ):
        raise CoverageAuditError(f"{label} reviewed job/view counts changed")
    status_policy = summary.get("status_observation_policy")
    if not isinstance(status_policy, Mapping) or (
        status_policy.get("semantics") != LAST_OBSERVED_REVIEW_SEMANTICS
        or status_policy.get("authoritative_refresh_completed_by_review") is not False
        or status_policy.get("authoritative_refresh_required_before_current_status_use")
        is not True
        or status_policy.get("imagery_can_satisfy_authoritative_status_refresh")
        is not False
        or status_policy.get("imagery_status_refresh_performed") is not False
    ):
        raise CoverageAuditError(f"{label} last-observed status policy changed")
    reviews = _canonical_jsonl(reviews_raw, f"{label} reviews")
    blind_ids = [record.get("blind_id") for record in reviews]
    if (
        len(reviews) != 71
        or blind_ids != sorted(set(blind_ids))
        or any(record.get("schema_version") != 4 for record in reviews)
        or sum(
            len(record.get("members", []))
            for record in reviews
            if isinstance(record.get("members"), list)
        )
        != 74
    ):
        raise CoverageAuditError(f"{label} review records do not reconcile")
    return {
        "support_id": support.support_id,
        "directory": support.display_directory,
        "classification": SATELLITE_SUPPORT_CLASSIFICATION,
        "categories": list(support.categories),
        "format": SATELLITE_REVIEW_FORMAT,
        "schema_version": SATELLITE_REVIEW_SCHEMA_VERSION,
        "status_semantics": "last_observed",
        "reviewed_at": manifest.get("reviewed_at"),
        "counts": {"jobs": 74, "views": 71},
        "decisions": {
            "job_counts": manifest["job_counts"],
            "view_counts": summary["view_counts"],
            "promotion_disposition_job_counts": summary[
                "promotion_disposition_job_counts"
            ],
        },
        "scope": {
            "review_only": True,
            "child_evidence": False,
            "facility_rows": False,
            "lifecycle_observations": False,
            "current_status_claim": False,
            "atlas_mutation": False,
            "promoted": False,
            "countable": False,
        },
        "guardrails": dict(manifest_guardrails),
        "definition": {
            "path": support.definition.display_path,
            "bytes": support.definition.bytes,
            "sha256": support.definition.sha256,
        },
        "manifest": {
            "file": support.manifest_filename,
            "bytes": support.manifest_bytes,
            "sha256": support.manifest_sha256,
        },
        "summary": {
            "file": support.summary_filename,
            "bytes": support.summary_bytes,
            "sha256": support.summary_sha256,
        },
        "reviews": {
            "file": support.reviews_filename,
            "bytes": support.reviews_bytes,
            "sha256": support.reviews_sha256,
        },
        "closed_tree": dict(support.closed_tree),
    }


def _methodology_evidence(
    definition: _AuditDefinition,
    descriptors: Mapping[str, Mapping[str, Any]],
    supports: list[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    child_evidence = legacy._resolve_methodology_evidence(
        definition.methodology_evidence_classification,
        children=definition.children,
        descriptors=descriptors,
    )
    if child_evidence is None:  # pragma: no cover - required by the v2 schema
        raise CoverageAuditError("methodology evidence classification is missing")
    result: dict[str, dict[str, Any]] = {}
    for category in METHODOLOGY_EVIDENCE_CATEGORIES:
        support_records = [
            support for support in supports if category in support["categories"]
        ]
        record = dict(child_evidence[category])
        record.update(
            {
                "methodology_support_artifact_count": len(support_records),
                "methodology_support_ids": [
                    support["support_id"] for support in support_records
                ],
                "methodology_support_artifacts": support_records,
                "methodology_support_is_child_evidence": False,
                "methodology_support_creates_facility_rows": False,
                "methodology_support_creates_lifecycle_observations": False,
                "methodology_support_is_promoted": False,
                "methodology_support_is_countable": False,
            }
        )
        if support_records:
            record["status"] = "partial_reviewed_method_evidence"
            record["support_scope"] = SATELLITE_SUPPORT_CLASSIFICATION
        result[category] = record
    return result


def _benchmark_comparison(
    benchmark: Mapping[str, Any],
    totals: Mapping[str, Any],
    methodology: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    result = legacy._benchmark_comparison(benchmark, totals, methodology)
    for comparison in result["comparisons"]:
        if comparison["claim_id"] == "evidence_methodology":
            comparison["atlas_status"] = (
                "partial_reviewed_method_evidence_with_material_gaps"
            )
            comparison["atlas_evidence"]["methodology_scope"] = (
                "hash_bound_child_evidence_plus_non_countable_review_support"
            )
            comparison["atlas_evidence"]["foia_gap"] = "absent"
            comparison["parity_status"] = "pending"
    result["overall_parity"] = {
        "status": "pending",
        "reason": (
            "Public claims are not a row-level benchmark; Atlas unique physical "
            "sites remain unknown; and partial reviewed method evidence does not "
            "close the material facility, FOIA, timeline, or capacity gaps."
        ),
    }
    return result


def _report(audit: Mapping[str, Any], gaps: Mapping[str, Any]) -> bytes:
    text = legacy._report(audit, gaps).decode("utf-8")
    generated_heading = (
        "# Global coverage and field-completeness audit — "
        f"{audit['generated_at'][:10]}"
    )
    as_of_heading = (
        "# Global coverage and field-completeness audit — "
        f"as of {audit['as_of']}"
    )
    if generated_heading not in text:
        raise CoverageAuditError("coverage report heading anchor changed")
    text = text.replace(generated_heading, as_of_heading, 1)
    fields = audit["totals"]["field_totals"]
    old = (
        f"There are {fields['non_review_under_construction_rows']:,} non-review "
        "source rows marked `under_construction` and "
        f"{fields['review_only_under_construction_lead_rows']:,} review-only "
        "under-construction leads."
    )
    new = (
        f"There are {fields['non_review_under_construction_rows']:,} non-review "
        "source rows whose last-observed lifecycle value is "
        "`under_construction` and "
        f"{fields['review_only_under_construction_lead_rows']:,} review-only "
        "under-construction leads. These are dated observations, not current-status "
        "assertions."
    )
    if old not in text:
        raise CoverageAuditError("coverage report construction wording anchor changed")
    text = text.replace(old, new, 1)
    anchor = "## SemiAnalysis public benchmark\n"
    supports = audit["inputs"]["methodology_support_artifacts"]
    support_lines = [
        "## Review-only methodology support",
        "",
        (
            "Satellite imagery and computer vision are classified as partial "
            "reviewed-method evidence from independently frozen support artifacts. "
            "They are not child evidence, facility rows, lifecycle or current-status "
            "claims, atlas mutations, promoted records, or countable observations."
        ),
        "",
    ]
    for support in supports:
        support_lines.append(
            f"- `{support['support_id']}`: **{support['counts']['jobs']} jobs / "
            f"{support['counts']['views']} views**, schema v4, last-observed status "
            "semantics; every claim-creation and promotion guardrail remains false."
        )
    support_lines.extend(["", anchor.rstrip("\n")])
    if anchor not in text:
        raise CoverageAuditError("coverage report benchmark anchor changed")
    return text.replace(anchor, "\n".join(support_lines) + "\n", 1).encode("utf-8")


def build_coverage_audit(
    definition_path: str | Path,
) -> CoverageAuditBundle:
    """Validate exact v2 inputs and construct the complete audit in memory."""

    definition_path = Path(definition_path)
    definition = _definition(definition_path)
    federation_manifest_raw = legacy._regular_bytes(
        definition.federation_path / MANIFEST_FILENAME,
        "federated index manifest",
    )
    federation_manifest_sha256 = hashlib.sha256(federation_manifest_raw).hexdigest()
    if federation_manifest_sha256 != definition.expected_federation_manifest_sha256:
        raise CoverageAuditError("federated index manifest SHA-256 does not match")
    child_paths = {
        child.release_id: child.release_path for child in definition.children
    }
    try:
        federation = federation_v2.validate_federated_release_index(
            definition.federation_path,
            child_release_paths=child_paths,
        )
    except ValueError as error:
        raise CoverageAuditError(f"federated v2 input validation failed: {error}") from error
    descriptors = {
        release["release_id"]: release for release in federation["releases"]
    }
    if set(descriptors) != set(child_paths):
        raise CoverageAuditError("audit children do not exactly match federation")
    for child in definition.children:
        if (
            descriptors[child.release_id]["manifest"]["sha256"]
            != child.expected_manifest_sha256
        ):
            raise CoverageAuditError(
                f"{child.release_id} manifest SHA-256 does not match audit definition"
            )

    lifecycle_children: list[dict[str, Any]] = []
    for release_id, descriptor in sorted(descriptors.items()):
        manifest = descriptor["manifest"]
        if manifest.get("publication_contract_version", 0) >= 4:
            if (
                manifest.get("current_status_inferred") is not False
                or manifest.get("lifecycle_status_semantics") != "last_observed"
                or not isinstance(manifest.get("lifecycle_freshness_records"), int)
            ):
                raise CoverageAuditError(
                    f"{release_id} publication-v4 lifecycle semantics changed"
                )
            lifecycle_children.append(
                {
                    "release_id": release_id,
                    "publication_contract_version": manifest[
                        "publication_contract_version"
                    ],
                    "current_status_inferred": False,
                    "lifecycle_status_semantics": "last_observed",
                    "lifecycle_freshness_records": manifest[
                        "lifecycle_freshness_records"
                    ],
                }
            )
    if not lifecycle_children:
        raise CoverageAuditError("coverage audit v2 requires a publication-v4 child")

    support_records = [
        _validate_support(support)
        for support in definition.methodology_support_artifacts
    ]
    methodology = _methodology_evidence(definition, descriptors, support_records)

    groups: list[dict[str, Any]] = []
    total_stats = legacy._Stats()
    input_children: list[dict[str, Any]] = []
    entity_source_families: set[str] = set()
    as_of_date = date.fromisoformat(definition.as_of)
    for child in definition.children:
        descriptor = descriptors[child.release_id]
        release_groups, release_stats, entity_sources = legacy._inspect_release(
            child, descriptor, as_of_date
        )
        groups.extend(release_groups)
        legacy._merge_stats(total_stats, release_stats)
        entity_source_families.update(entity_sources)
        input_children.append(
            {
                "release_id": child.release_id,
                "reference": descriptor["reference"],
                "review_only": descriptor["scope"]["review_only"],
                "manifest": descriptor["manifest"],
                "atlas_geojson": descriptor["files"]["atlas.geojson"],
                "evidence_csv": descriptor["files"]["evidence.csv"],
                "declared_source_families": descriptor["source_families"],
            }
        )
    groups.sort(
        key=lambda group: (
            group["child_release"],
            {"release": 0, "release_source": 1, "release_source_country": 2}[
                group["scope_type"]
            ],
            group["source_family"],
            group["country"],
            group["country_iso_a2"] or "",
            group["country_iso_a3"] or "",
        )
    )
    counts = federation["counts"]
    totals = {
        "source_scoped_entity_records": counts["source_scoped_entity_records"],
        "non_review_source_scoped_entity_records": counts[
            "non_review_source_scoped_entity_records"
        ],
        "review_only_source_scoped_entity_records": counts[
            "review_only_source_scoped_entity_records"
        ],
        "advisory_resolution_candidate_records": counts["resolution_candidates"],
        "confirmed_duplicate_relationships": None,
        "unique_physical_sites": None,
        "field_totals": total_stats.export(),
    }
    if totals["source_scoped_entity_records"] != total_stats.rows:
        raise CoverageAuditError("audit rows do not reconcile with federation")
    scrutica_included = any(
        source == "scrutica" or source.startswith("scrutica:")
        for child in input_children
        for source in child["declared_source_families"]
    )
    comparison = _benchmark_comparison(
        definition.public_benchmark, totals, methodology
    )
    scope = {
        "unit": "source_scoped_release_row",
        "provisional_open_layer_audit": not scrutica_included,
        "scrutica_included": scrutica_included,
        "children_merged": False,
        "cross_source_deduplication": False,
        "review_candidates_promoted": False,
        "review_only_rows_separately_counted": True,
        "source_declared_entity_kind_is_not_a_physical_site_count": True,
        "advisory_resolution_candidates_are_confirmed_duplicates": False,
        "confirmed_duplicate_relationships": None,
        "unique_physical_sites": None,
        "candidate_rows_counted_as_facilities": False,
        "lifecycle_status_semantics": "last_observed",
        "current_status_inferred": False,
        "methodology_support_artifacts_are_child_evidence": False,
        "methodology_support_artifacts_create_facility_rows": False,
        "methodology_support_artifacts_create_lifecycle_observations": False,
        "methodology_support_artifacts_are_promoted": False,
        "methodology_support_artifacts_are_countable": False,
    }
    federation_index_path = definition.federation_path / federation_v2.INDEX_FILENAME
    federation_index_raw = legacy._regular_bytes(
        federation_index_path, "federated index"
    )
    audit = {
        "schema_version": SCHEMA_VERSION,
        "format": AUDIT_FORMAT,
        "audit_id": definition.audit_id,
        "as_of": definition.as_of,
        "generated_at": definition.generated_at,
        "scope": scope,
        "lifecycle_contract": {
            "status_semantics": "last_observed",
            "current_status_inferred": False,
            "current_status_classification": "unknown",
            "publication_v4_children": lifecycle_children,
        },
        "freshness_buckets": {
            "reference_date": definition.as_of,
            "buckets": [
                "0_90_days",
                "91_365_days",
                "366_plus_days",
                "future",
                "invalid",
                "missing",
            ],
        },
        "inputs": {
            "federated_index": {
                "format": federation["format"],
                "generated_at": federation["generated_at"],
                "manifest": {
                    "bytes": len(federation_manifest_raw),
                    "sha256": federation_manifest_sha256,
                },
                "index": {
                    "bytes": len(federation_index_raw),
                    "sha256": hashlib.sha256(federation_index_raw).hexdigest(),
                },
            },
            "children": input_children,
            "methodology_support_artifacts": support_records,
        },
        "methodology_evidence_classification": methodology,
        "entity_source_families": sorted(entity_source_families),
        "totals": totals,
        "groups": groups,
        "semianalysis_public_comparison": comparison,
    }
    gaps = legacy._gap_registry(
        definition.audit_id, definition.generated_at, groups, comparison
    )
    gaps["schema_version"] = SCHEMA_VERSION
    gaps["format"] = GAP_FORMAT
    audit_bytes = legacy._canonical_json(audit)
    gaps_bytes = legacy._canonical_json(gaps)
    csv_bytes = legacy._coverage_csv(groups)
    report_bytes = _report(audit, gaps)
    artifacts = {
        AUDIT_FILENAME: audit_bytes,
        COVERAGE_CSV_FILENAME: csv_bytes,
        GAP_REGISTRY_FILENAME: gaps_bytes,
        REPORT_FILENAME: report_bytes,
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "format": BUNDLE_FORMAT,
        "audit_id": definition.audit_id,
        "as_of": definition.as_of,
        "generated_at": definition.generated_at,
        "definition": {
            "file": definition.filename,
            "bytes": len(definition.raw),
            "sha256": hashlib.sha256(definition.raw).hexdigest(),
        },
        "inputs": {
            "federated_manifest_sha256": federation_manifest_sha256,
            "child_manifest_sha256": {
                child.release_id: child.expected_manifest_sha256
                for child in definition.children
            },
            "methodology_support_artifacts": {
                support["support_id"]: {
                    "definition_sha256": support["definition"]["sha256"],
                    "manifest_sha256": support["manifest"]["sha256"],
                    "summary_sha256": support["summary"]["sha256"],
                    "reviews_sha256": support["reviews"]["sha256"],
                    "closed_tree_inventory_sha256": support["closed_tree"][
                        "inventory_sha256"
                    ],
                }
                for support in support_records
            },
        },
        "scope": scope,
        "counts": {
            "source_scoped_entity_records": totals[
                "source_scoped_entity_records"
            ],
            "non_review_source_scoped_entity_records": totals[
                "non_review_source_scoped_entity_records"
            ],
            "review_only_source_scoped_entity_records": totals[
                "review_only_source_scoped_entity_records"
            ],
            "coverage_groups": len(groups),
            "open_gaps": gaps["summary"]["open_gaps"],
            "methodology_support_artifacts": len(support_records),
            "methodology_support_jobs": sum(
                support["counts"]["jobs"] for support in support_records
            ),
            "methodology_support_views": sum(
                support["counts"]["views"] for support in support_records
            ),
            "confirmed_duplicate_relationships": None,
            "unique_physical_sites": None,
        },
        "artifacts": {
            filename: {
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
            for filename, raw in sorted(artifacts.items())
        },
    }
    manifest_bytes = legacy._canonical_json(manifest)
    sidecar_bytes = (
        f"{hashlib.sha256(manifest_bytes).hexdigest()}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    payloads = {
        **artifacts,
        MANIFEST_FILENAME: manifest_bytes,
        MANIFEST_HASH_FILENAME: sidecar_bytes,
    }
    return CoverageAuditBundle(
        payloads=payloads, audit=audit, gaps=gaps, manifest=manifest
    )


def validate_coverage_audit(
    directory_path: str | Path,
    *,
    definition_path: str | Path | None = None,
    require_frozen: bool = True,
) -> Mapping[str, Any]:
    """Validate a closed v2 audit and optionally rebuild it from exact inputs."""

    directory = Path(directory_path)
    if directory.is_symlink() or not directory.is_dir():
        raise CoverageAuditError(f"audit bundle must be a regular directory: {directory}")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != AUDIT_BUNDLE_FILES or len(entries) != len(
        AUDIT_BUNDLE_FILES
    ):
        raise CoverageAuditError("audit bundle file set is invalid")
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            raise CoverageAuditError(f"audit entry must be a regular file: {entry.name}")
    if require_frozen:
        if stat.S_IMODE(directory.stat().st_mode) != FROZEN_DIRECTORY_MODE:
            raise CoverageAuditError("audit root must have mode 0555")
        if any(stat.S_IMODE(entry.stat().st_mode) != FROZEN_FILE_MODE for entry in entries):
            raise CoverageAuditError("audit files must have mode 0444")
    payloads = {entry.name: entry.read_bytes() for entry in entries}
    manifest_raw = payloads[MANIFEST_FILENAME]
    expected_sidecar = (
        f"{hashlib.sha256(manifest_raw).hexdigest()}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    if payloads[MANIFEST_HASH_FILENAME] != expected_sidecar:
        raise CoverageAuditError("audit manifest sidecar does not match")
    manifest = legacy._json_object(manifest_raw, "audit manifest")
    audit = legacy._json_object(payloads[AUDIT_FILENAME], "coverage audit")
    gaps = legacy._json_object(payloads[GAP_REGISTRY_FILENAME], "gap registry")
    for value, raw, label in (
        (manifest, manifest_raw, "audit manifest"),
        (audit, payloads[AUDIT_FILENAME], "coverage audit"),
        (gaps, payloads[GAP_REGISTRY_FILENAME], "gap registry"),
    ):
        if raw != legacy._canonical_json(value):
            raise CoverageAuditError(f"{label} is not canonical JSON")
    if (
        manifest.get("format") != BUNDLE_FORMAT
        or manifest.get("schema_version") != SCHEMA_VERSION
        or audit.get("format") != AUDIT_FORMAT
        or audit.get("schema_version") != SCHEMA_VERSION
        or gaps.get("format") != GAP_FORMAT
        or gaps.get("schema_version") != SCHEMA_VERSION
    ):
        raise CoverageAuditError("coverage audit v2 bundle identity is invalid")
    if not (
        manifest.get("audit_id") == audit.get("audit_id") == gaps.get("audit_id")
        and manifest.get("generated_at")
        == audit.get("generated_at")
        == gaps.get("generated_at")
        and manifest.get("as_of") == audit.get("as_of")
    ):
        raise CoverageAuditError("coverage audit v2 identities do not reconcile")
    artifacts = manifest.get("artifacts")
    expected_artifacts = AUDIT_BUNDLE_FILES - {
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
    }
    if not isinstance(artifacts, Mapping) or set(artifacts) != expected_artifacts:
        raise CoverageAuditError("audit artifact inventory is invalid")
    for filename, checkpoint in artifacts.items():
        raw = payloads[filename]
        if not isinstance(checkpoint, Mapping) or (
            checkpoint.get("bytes") != len(raw)
            or checkpoint.get("sha256") != hashlib.sha256(raw).hexdigest()
        ):
            raise CoverageAuditError(f"audit artifact checkpoint mismatch: {filename}")

    scope = audit.get("scope")
    if not isinstance(scope, Mapping) or any(
        scope.get(field) is not False
        for field in (
            "current_status_inferred",
            "methodology_support_artifacts_are_child_evidence",
            "methodology_support_artifacts_create_facility_rows",
            "methodology_support_artifacts_create_lifecycle_observations",
            "methodology_support_artifacts_are_promoted",
            "methodology_support_artifacts_are_countable",
        )
    ) or scope.get("lifecycle_status_semantics") != "last_observed":
        raise CoverageAuditError("coverage audit v2 scope policy is invalid")
    lifecycle = audit.get("lifecycle_contract")
    if not isinstance(lifecycle, Mapping) or (
        lifecycle.get("status_semantics") != "last_observed"
        or lifecycle.get("current_status_inferred") is not False
        or lifecycle.get("current_status_classification") != "unknown"
        or not lifecycle.get("publication_v4_children")
    ):
        raise CoverageAuditError("coverage audit v2 lifecycle contract is invalid")
    inputs = audit.get("inputs")
    supports = inputs.get("methodology_support_artifacts") if isinstance(inputs, Mapping) else None
    if not isinstance(supports, list) or not supports:
        raise CoverageAuditError("methodology support artifact inputs are invalid")
    for support in supports:
        support_scope = support.get("scope") if isinstance(support, Mapping) else None
        guardrails = support.get("guardrails") if isinstance(support, Mapping) else None
        if (
            support.get("classification") != SATELLITE_SUPPORT_CLASSIFICATION
            or support.get("schema_version") != 4
            or support.get("status_semantics") != "last_observed"
            or support.get("counts") != {"jobs": 74, "views": 71}
            or not isinstance(support_scope, Mapping)
            or support_scope.get("review_only") is not True
            or any(
                support_scope.get(field) is not False
                for field in (
                    "child_evidence",
                    "facility_rows",
                    "lifecycle_observations",
                    "current_status_claim",
                    "atlas_mutation",
                    "promoted",
                    "countable",
                )
            )
            or not isinstance(guardrails, Mapping)
            or any(value is not False for value in guardrails.values())
        ):
            raise CoverageAuditError("methodology support scope or guardrails changed")
    methodology = audit.get("methodology_evidence_classification")
    if not isinstance(methodology, Mapping) or set(methodology) != set(
        METHODOLOGY_EVIDENCE_CATEGORIES
    ):
        raise CoverageAuditError("methodology evidence classification is invalid")
    for category in SATELLITE_SUPPORT_CATEGORIES:
        record = methodology[category]
        if (
            record.get("status") != "partial_reviewed_method_evidence"
            or record.get("evidence_reference_count") != 0
            or record.get("methodology_support_artifact_count") != len(supports)
            or record.get("methodology_support_is_child_evidence") is not False
            or record.get("methodology_support_creates_facility_rows") is not False
            or record.get("methodology_support_creates_lifecycle_observations")
            is not False
            or record.get("methodology_support_is_promoted") is not False
            or record.get("methodology_support_is_countable") is not False
        ):
            raise CoverageAuditError(f"{category} methodology classification changed")
    if methodology["foia"].get("status") != "absent_from_audited_children":
        raise CoverageAuditError("FOIA methodology gap must remain explicit")

    groups = audit.get("groups")
    if not isinstance(groups, list) or not groups:
        raise CoverageAuditError("coverage groups must be a non-empty array")
    order = [
        (
            group.get("child_release"),
            {"release": 0, "release_source": 1, "release_source_country": 2}.get(
                group.get("scope_type"), 99
            ),
            group.get("source_family"),
            group.get("country"),
            group.get("country_iso_a2") or "",
            group.get("country_iso_a3") or "",
        )
        for group in groups
        if isinstance(group, Mapping)
    ]
    if len(order) != len(groups) or order != sorted(set(order)):
        raise CoverageAuditError("coverage groups must be sorted and unique")
    totals = audit.get("totals")
    release_groups = [group for group in groups if group["scope_type"] == "release"]
    if not isinstance(totals, Mapping) or (
        totals.get("source_scoped_entity_records")
        != sum(group["source_scoped_rows"] for group in release_groups)
        or totals.get("non_review_source_scoped_entity_records")
        != sum(group["non_review_rows"] for group in release_groups)
        or totals.get("review_only_source_scoped_entity_records")
        != sum(group["review_only_rows"] for group in release_groups)
        or totals.get("unique_physical_sites") is not None
    ):
        raise CoverageAuditError("coverage totals do not reconcile")
    comparisons = audit.get("semianalysis_public_comparison", {}).get("comparisons")
    method_comparison = next(
        (
            value
            for value in comparisons or []
            if value.get("claim_id") == "evidence_methodology"
        ),
        None,
    )
    if not isinstance(method_comparison, Mapping) or (
        method_comparison.get("atlas_status")
        != "partial_reviewed_method_evidence_with_material_gaps"
        or method_comparison.get("parity_status") != "pending"
    ):
        raise CoverageAuditError("SemiAnalysis methodology comparison changed")
    gap_values = gaps.get("gaps")
    gap_summary = gaps.get("summary")
    if not isinstance(gap_values, list) or not isinstance(gap_summary, Mapping):
        raise CoverageAuditError("gap registry payload is invalid")
    severity_counts = Counter(gap["severity"] for gap in gap_values)
    field_counts = Counter(gap["field"] for gap in gap_values)
    if (
        gap_summary.get("open_gaps") != len(gap_values)
        or gap_summary.get("by_severity") != dict(sorted(severity_counts.items()))
        or gap_summary.get("by_field") != dict(sorted(field_counts.items()))
    ):
        raise CoverageAuditError("gap registry counts do not reconcile")
    if payloads[COVERAGE_CSV_FILENAME] != legacy._coverage_csv(groups):
        raise CoverageAuditError("coverage CSV does not reconcile with JSON")
    if payloads[REPORT_FILENAME] != _report(audit, gaps):
        raise CoverageAuditError("coverage report does not reconcile with JSON")
    manifest_counts = manifest.get("counts")
    if not isinstance(manifest_counts, Mapping) or (
        manifest_counts.get("coverage_groups") != len(groups)
        or manifest_counts.get("open_gaps") != len(gap_values)
        or manifest_counts.get("source_scoped_entity_records")
        != totals.get("source_scoped_entity_records")
        or manifest_counts.get("methodology_support_artifacts") != len(supports)
        or manifest_counts.get("methodology_support_jobs") != 74 * len(supports)
        or manifest_counts.get("methodology_support_views") != 71 * len(supports)
        or manifest_counts.get("unique_physical_sites") is not None
    ):
        raise CoverageAuditError("audit manifest counts do not reconcile")
    if definition_path is not None:
        rebuilt = build_coverage_audit(definition_path)
        if dict(rebuilt.payloads) != payloads:
            raise CoverageAuditError("audit bytes drifted from exact v2 source inputs")
    return audit


def _discard_stage(stage: Path) -> None:
    if not stage.exists() or stage.is_symlink() or not stage.is_dir():
        return
    stage.chmod(0o700)
    for entry in stage.iterdir():
        entry.chmod(0o600)
    shutil.rmtree(stage)


def write_coverage_audit(
    definition_path: str | Path, output_directory: str | Path
) -> Mapping[str, Any]:
    """Double-build, validate, freeze, and atomically publish a v2 audit."""

    first = build_coverage_audit(definition_path)
    second = build_coverage_audit(definition_path)
    if dict(first.payloads) != dict(second.payloads):
        raise CoverageAuditError("two offline coverage-audit reconstructions differ")
    output = Path(output_directory)
    if output.is_symlink():
        raise CoverageAuditError(f"audit output may not be a symlink: {output}")
    if output.exists():
        validate_coverage_audit(output, definition_path=definition_path)
        existing = {path.name: path.read_bytes() for path in output.iterdir()}
        if existing != dict(first.payloads):
            raise CoverageAuditError(
                "existing valid audit differs from requested bytes; refusing replacement"
            )
        return first.audit
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=parent))
    published = False
    try:
        for filename, raw in sorted(first.payloads.items()):
            legacy._write_bytes(stage / filename, raw)
        for entry in stage.iterdir():
            entry.chmod(FROZEN_FILE_MODE)
        stage.chmod(FROZEN_DIRECTORY_MODE)
        validate_coverage_audit(stage)
        federation_v2._promote_noreplace(stage, output)
        published = True
        validate_coverage_audit(output, definition_path=definition_path)
    finally:
        if not published:
            _discard_stage(stage)
    return first.audit


__all__ = [
    "AUDIT_FILENAME",
    "BUNDLE_FORMAT",
    "COVERAGE_CSV_FILENAME",
    "CoverageAuditBundle",
    "CoverageAuditError",
    "GAP_REGISTRY_FILENAME",
    "MANIFEST_FILENAME",
    "MANIFEST_HASH_FILENAME",
    "REPORT_FILENAME",
    "build_coverage_audit",
    "validate_coverage_audit",
    "write_coverage_audit",
]
