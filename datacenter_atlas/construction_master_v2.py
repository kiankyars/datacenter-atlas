"""Role-preserving construction-master schema v2.

This module deliberately does not extend the historical v1 implementation.
It consumes the frozen v14 master as a byte-pinned base, replaces only the
v33 open-seed block with the publication-contract-v4 v42 block, and appends a
single ``roles`` object to every row.  The Unknown033 recovery is admitted as
four small control-plane checkpoints only; it contributes no rows and this
builder never traverses its batch, inventory, snapshot, or payload tree.
"""

from __future__ import annotations

from collections import Counter
import csv
import hashlib
from itertools import chain
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any, Iterable, Iterator, Mapping

from . import construction_master as legacy


DEFINITION_SCHEMA_VERSION = 2
SCHEMA_VERSION = 2
DEFINITION_FORMAT = "datacenter-atlas-construction-master-definition-v2"
FORMAT = "datacenter-atlas-construction-master-v2"
BUNDLE_FORMAT = "datacenter-atlas-construction-master-bundle-v2"
MASTER_ID = "2026-07-20-public-open-v16"
GENERATED_AT = "2026-07-20T06:00:00Z"
BASE_MASTER_ID = "2026-07-19-public-open-v14"
BASE_ARTIFACT_ID = "epoch-official-open-seed-v33"
REPLACEMENT_ARTIFACT_ID = "epoch-official-open-seed-v42"
REPLACEMENT_RELEASE_ID = "epoch-official-open-seed-v42"
REPLACEMENT_DEFINITION_RELEASE_ID = "2026-07-20-open-seed-v42"
PUBLICATION_CONTRACT_VERSION = 4
RECOVERY_ARTIFACT_ID = "2026-07-19-global-open-v3-unknown-033-recovered-25"

JSONL_FILENAME = "construction-master.jsonl"
CSV_FILENAME = "construction-master.csv"
COVERAGE_FILENAME = "coverage.json"
README_FILENAME = "README.md"
ATTRIBUTION_FILENAME = "ATTRIBUTION.txt"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
BUNDLE_FILES = frozenset(
    {
        JSONL_FILENAME,
        CSV_FILENAME,
        COVERAGE_FILENAME,
        README_FILENAME,
        ATTRIBUTION_FILENAME,
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
    }
)

ROLE_KEYS = (
    "source_publication_contract_version",
    "owner",
    "operator",
    "users",
    "tenants",
    "customers",
    "source_role_tags",
)
CORE_ROLE_KEYS = ("owner", "operator", "users", "tenants", "customers")
CSV_FIELDS = legacy.CSV_FIELDS + (
    "source_publication_contract_version",
    "owner",
    "operator",
    "users",
    "tenants",
    "customers",
    "source_role_tags_json",
)

SCOPE_POLICY = {
    **legacy.SCOPE_POLICY,
    "historical_status_is_not_current_status_claim": True,
    "roles_copied_only_from_marked_publication_contract": True,
    "source_role_tags_preserved_opaquely_without_normalization": True,
    "satellite_recovery_control_plane_only": True,
    "satellite_recovery_payload_traversed": False,
    "satellite_recovery_rows_created": 0,
}

EXPECTED_FIXED = {
    "added_replacement_rows": 63,
    "base_replaced_rows": 199,
    "base_rows": 109_111,
    "inherited_rows": 108_912,
    "replacement_rows": 262,
    "replacement_rows_with_any_role": 89,
    "replacement_rows_with_customers": 1,
    "replacement_rows_with_operator": 30,
    "replacement_rows_with_owner": 46,
    "replacement_rows_with_source_role_tags": 50,
    "replacement_rows_with_tenants": 4,
    "replacement_rows_with_users": 36,
    "rows_with_contract_marker": 262,
    "satellite_recovery_control_plane_bytes": 15_313,
    "satellite_recovery_rows": 0,
    "tier_a_rows": 382,
    "tier_b_rows": 6_298,
    "tier_c_rows": 102_494,
    "total_rows": 109_174,
    "unchanged_replacement_rows": 199,
}
DIGEST_KEYS = {
    "added_source_record_ids_sha256",
    "base_replaced_source_record_ids_sha256",
    "inherited_rows_without_roles_sha256",
    "replacement_role_projection_sha256",
    "replacement_rows_without_roles_sha256",
    "replacement_source_record_ids_sha256",
    "tier_a_arithmetic_projection_sha256",
}
EXPECTED_KEYS = {*EXPECTED_FIXED, *DIGEST_KEYS}
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")

NULL_ROLES = {
    "source_publication_contract_version": None,
    "owner": None,
    "operator": None,
    "users": None,
    "tenants": None,
    "customers": None,
    "source_role_tags": {},
}


class ConstructionMasterV2Error(ValueError):
    """Raised when the v2 definition, lineage, or frozen output drifts."""


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_line(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _compact(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _is_exact_publication_contract_version(value: Any) -> bool:
    return type(value) is int and value == PUBLICATION_CONTRACT_VERSION


def _checkpoint(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def _json_file(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise ConstructionMasterV2Error(f"{label} must be a regular file")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConstructionMasterV2Error(f"{label} must be valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ConstructionMasterV2Error(f"{label} must be a JSON object")
    return value, raw


def _safe_path(package_root: Path, supplied: Any, label: str) -> Path:
    if not isinstance(supplied, str) or not supplied or "\\" in supplied:
        raise ConstructionMasterV2Error(f"{label} path is invalid")
    relative = Path(supplied)
    if relative.is_absolute() or ".." in relative.parts:
        raise ConstructionMasterV2Error(f"{label} path escapes the package")
    resolved = (package_root / relative).resolve()
    try:
        resolved.relative_to(package_root)
    except ValueError as error:
        raise ConstructionMasterV2Error(f"{label} path escapes the package") from error
    return resolved


def _checkpoint_spec(
    package_root: Path, spec: Any, label: str
) -> tuple[Path, dict[str, Any]]:
    if not isinstance(spec, Mapping) or set(spec) != {"bytes", "path", "sha256"}:
        raise ConstructionMasterV2Error(f"{label} checkpoint schema changed")
    size = spec.get("bytes")
    digest = spec.get("sha256")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise ConstructionMasterV2Error(f"{label} bytes is invalid")
    if not isinstance(digest, str) or not _SHA_RE.fullmatch(digest):
        raise ConstructionMasterV2Error(f"{label} sha256 is invalid")
    path = _safe_path(package_root, spec.get("path"), label)
    if path.is_symlink() or not path.is_file():
        raise ConstructionMasterV2Error(f"{label} must be a regular file")
    if _checkpoint(path) != {"bytes": size, "sha256": digest}:
        raise ConstructionMasterV2Error(f"pinned input changed: {spec.get('path')}")
    return path, {"bytes": size, "path": str(spec["path"]), "sha256": digest}


def _expected(document: Mapping[str, Any]) -> dict[str, Any]:
    expected = document.get("expected")
    if not isinstance(expected, Mapping) or set(expected) != EXPECTED_KEYS:
        raise ConstructionMasterV2Error("replacement expected invariant schema changed")
    if any(expected.get(key) != value for key, value in EXPECTED_FIXED.items()):
        raise ConstructionMasterV2Error("replacement fixed count contract changed")
    for key in DIGEST_KEYS:
        value = expected.get(key)
        if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
            raise ConstructionMasterV2Error(f"replacement {key} is invalid")
    return dict(expected)


def _input_specs(inputs: Mapping[str, Any]) -> list[tuple[str, Any]]:
    base = inputs["base_master"]
    replacement = inputs["replacement_release"]
    recovery = inputs["satellite_recovery_acceptance"]
    return [
        ("inputs.base_master.attribution", base["attribution"]),
        ("inputs.base_master.definition", base["definition"]),
        ("inputs.base_master.jsonl", base["jsonl"]),
        ("inputs.base_master.manifest", base["manifest"]),
        ("inputs.replacement_release.data", replacement["data"]),
        ("inputs.replacement_release.definition", replacement["definition"]),
        ("inputs.replacement_release.evidence", replacement["evidence"]),
        ("inputs.replacement_release.manifest", replacement["manifest"]),
        ("inputs.satellite_recovery_acceptance.acceptance", recovery["acceptance"]),
        ("inputs.satellite_recovery_acceptance.definition", recovery["definition"]),
        (
            "inputs.satellite_recovery_acceptance.recovery_manifest",
            recovery["recovery_manifest"],
        ),
        ("inputs.satellite_recovery_acceptance.sidecar", recovery["sidecar"]),
    ]


def _validate_recovery_control_plane(
    recovery: Mapping[str, Any], resolved: Mapping[str, Path]
) -> dict[str, Any]:
    allowed = {"acceptance", "artifact_id", "definition", "recovery_manifest", "sidecar"}
    if set(recovery) != allowed or recovery.get("artifact_id") != RECOVERY_ARTIFACT_ID:
        raise ConstructionMasterV2Error("Unknown033 control-plane definition changed")
    total = sum(int(recovery[key]["bytes"]) for key in allowed - {"artifact_id"})
    if total != EXPECTED_FIXED["satellite_recovery_control_plane_bytes"]:
        raise ConstructionMasterV2Error("Unknown033 control-plane byte count changed")

    acceptance, acceptance_raw = _json_file(
        resolved[str(recovery["acceptance"]["path"])], "recovery acceptance"
    )
    definition, definition_raw = _json_file(
        resolved[str(recovery["definition"]["path"])], "recovery definition"
    )
    manifest, manifest_raw = _json_file(
        resolved[str(recovery["recovery_manifest"]["path"])], "recovery manifest"
    )
    sidecar = resolved[str(recovery["sidecar"]["path"])].read_bytes()
    if acceptance_raw != _canonical_json(acceptance):
        raise ConstructionMasterV2Error("recovery acceptance is not canonical")
    if definition_raw != _canonical_json(definition):
        raise ConstructionMasterV2Error("recovery definition is not canonical")
    if manifest_raw != _canonical_json(manifest):
        raise ConstructionMasterV2Error("recovery manifest is not canonical")
    accepted = acceptance.get("accepted")
    if (
        acceptance.get("format")
        != "datacenter-atlas-satellite-recovery-acceptance-v1"
        or not isinstance(accepted, Mapping)
        or accepted.get("artifact_id") != RECOVERY_ARTIFACT_ID
        or acceptance.get("scope", {}).get("source_batch_promoted") is not False
        or acceptance.get("scope", {}).get("imagery_inference_created") is not False
        or acceptance.get("scope", {}).get("atlas_release_integration") is not False
    ):
        raise ConstructionMasterV2Error("Unknown033 acceptance boundary changed")
    for key in ("definition", "recovery_manifest", "sidecar"):
        if accepted.get(key) != dict(recovery[key]):
            raise ConstructionMasterV2Error(
                f"Unknown033 acceptance {key} binding changed"
            )
    if (
        definition.get("artifact_id") != RECOVERY_ARTIFACT_ID
        or definition.get("incident", {}).get("reported_guard_pid") != 4234
        or manifest.get("artifact_id") != RECOVERY_ARTIFACT_ID
        or manifest.get("scope", {}).get("source_batch_promoted") is not False
        or manifest.get("scope", {}).get("source_evidence_accepted_for_release")
        is not False
        or manifest.get("scope", {}).get("imagery_identity_inference") is not False
        or manifest.get("scope", {}).get("imagery_lifecycle_inference") is not False
        or manifest.get("scope", {}).get("imagery_power_inference") is not False
        or manifest.get("reconciliation", {}).get("later_job_leakage") != 0
        or manifest.get("selection", {}).get("jobs") != 25
        or manifest.get("selection", {}).get("queue_position_start") != 4745
        or manifest.get("selection", {}).get("queue_position_end") != 4769
        or manifest.get("output", {}).get("batch_summary")
        != {
            "jobs_completed": 4375,
            "jobs_failed": 0,
            "jobs_pending": 2061,
            "jobs_selected": 6736,
            "jobs_unavailable_no_scene": 300,
        }
    ):
        raise ConstructionMasterV2Error("Unknown033 metadata boundary changed")
    if sidecar != (
        f"{recovery['recovery_manifest']['sha256']}  recovery-manifest.json\n"
    ).encode("ascii"):
        raise ConstructionMasterV2Error("Unknown033 sidecar changed")
    return {
        "accepted_artifact_id": RECOVERY_ARTIFACT_ID,
        "batch_summary": dict(manifest["output"]["batch_summary"]),
        "control_plane_bytes": total,
        "control_plane_files": 4,
        "imagery_inference_created": False,
        "later_job_leakage": 0,
        "payload_traversed": False,
        "queue_position_end": 4769,
        "queue_position_start": 4745,
        "rows_created": 0,
        "selected_jobs": 25,
        "source_batch_promoted": False,
    }


def validate_definition(
    definition_path: str | Path,
) -> tuple[dict[str, Any], bytes, Path, dict[str, Path], dict[str, Any]]:
    path = Path(definition_path)
    document, raw = _json_file(path, "construction-master v2 definition")
    if raw != _canonical_json(document):
        raise ConstructionMasterV2Error("definition must be canonical JSON")
    if set(document) != {
        "expected",
        "format",
        "generated_at",
        "inputs",
        "master_id",
        "schema_version",
        "scope",
    }:
        raise ConstructionMasterV2Error("definition keys differ from v2 contract")
    if (
        document.get("schema_version") != DEFINITION_SCHEMA_VERSION
        or document.get("format") != DEFINITION_FORMAT
        or document.get("master_id") != MASTER_ID
        or document.get("generated_at") != GENERATED_AT
        or document.get("scope") != SCOPE_POLICY
    ):
        raise ConstructionMasterV2Error("master definition identity or scope changed")
    _expected(document)
    inputs = document.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != {
        "base_master",
        "replacement_release",
        "satellite_recovery_acceptance",
    }:
        raise ConstructionMasterV2Error("master input lanes changed")
    base = inputs["base_master"]
    replacement = inputs["replacement_release"]
    if (
        not isinstance(base, Mapping)
        or set(base)
        != {"attribution", "definition", "jsonl", "manifest", "master_id"}
        or base.get("master_id") != BASE_MASTER_ID
        or not isinstance(replacement, Mapping)
        or set(replacement)
        != {
            "artifact_id",
            "data",
            "definition",
            "evidence",
            "manifest",
            "publication_contract_version",
            "release_id",
        }
        or replacement.get("artifact_id") != REPLACEMENT_ARTIFACT_ID
        or replacement.get("release_id") != REPLACEMENT_RELEASE_ID
        or not _is_exact_publication_contract_version(
            replacement.get("publication_contract_version")
        )
    ):
        raise ConstructionMasterV2Error("base or replacement lane changed")
    package_root = path.parent.parent.resolve()
    resolved: dict[str, Path] = {}
    lineage: list[dict[str, Any]] = []
    seen: set[str] = set()
    for label, spec in _input_specs(inputs):
        input_path, normalized = _checkpoint_spec(package_root, spec, label)
        if normalized["path"] in seen:
            raise ConstructionMasterV2Error("input checkpoint path repeats")
        seen.add(normalized["path"])
        resolved[normalized["path"]] = input_path
        lineage.append({"label": label, **normalized})
    recovery_summary = _validate_recovery_control_plane(
        inputs["satellite_recovery_acceptance"], resolved
    )

    base_manifest, _ = _json_file(
        resolved[str(base["manifest"]["path"])], "base master manifest"
    )
    release_manifest, _ = _json_file(
        resolved[str(replacement["manifest"]["path"])], "replacement release manifest"
    )
    release_definition, _ = _json_file(
        resolved[str(replacement["definition"]["path"])],
        "replacement source definition",
    )
    if (
        base_manifest.get("master_id") != BASE_MASTER_ID
        or base_manifest.get("row_counts", {}).get("total") != 109_111
        or base_manifest.get("row_counts", {}).get("by_tier")
        != {"A": 319, "B": 6298, "C": 102494}
    ):
        raise ConstructionMasterV2Error("pinned v14 base identity changed")
    if (
        release_manifest.get("format") != "datacenter-atlas-release-v1"
        or not _is_exact_publication_contract_version(
            release_manifest.get("publication_contract_version")
        )
        or release_manifest.get("construction_pipeline_records") != 262
        or release_manifest.get("files", {}).get("construction_pipeline.csv")
        != {
            "bytes": replacement["data"]["bytes"],
            "sha256": replacement["data"]["sha256"],
        }
        or release_manifest.get("files", {}).get("evidence.csv")
        != {
            "bytes": replacement["evidence"]["bytes"],
            "sha256": replacement["evidence"]["sha256"],
        }
    ):
        raise ConstructionMasterV2Error(
            "replacement publication contract or file binding changed"
        )
    expected_release = release_definition.get("expected_release")
    if (
        release_definition.get("release_id") != REPLACEMENT_DEFINITION_RELEASE_ID
        or not _is_exact_publication_contract_version(
            release_definition.get("publication_contract_version")
        )
        or not isinstance(expected_release, Mapping)
        or not _is_exact_publication_contract_version(
            expected_release.get("publication_contract_version")
        )
        or expected_release.get("construction_pipeline_records") != 262
        or expected_release.get("manifest_sha256")
        != replacement["manifest"]["sha256"]
    ):
        raise ConstructionMasterV2Error(
            "replacement source definition publication contract changed"
        )
    return document, raw, package_root, resolved, {
        "input_lineage": lineage,
        "recovery": recovery_summary,
    }


def _jsonl_rows(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("rb") as source:
        for line_number, raw in enumerate(source, start=1):
            try:
                row = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ConstructionMasterV2Error(
                    f"base master line {line_number} is invalid"
                ) from error
            if not isinstance(row, dict) or raw != _canonical_line(row):
                raise ConstructionMasterV2Error(
                    f"base master line {line_number} is not canonical"
                )
            yield row


def _roles_from_source(source_row: Mapping[str, str]) -> dict[str, Any]:
    try:
        tags = json.loads(source_row.get("tags_json", "{}"))
    except json.JSONDecodeError as error:
        raise ConstructionMasterV2Error("replacement tags_json is invalid") from error
    if not isinstance(tags, dict):
        raise ConstructionMasterV2Error("replacement tags_json must be an object")
    source_role_tags = {
        str(key): value for key, value in tags.items() if str(key).startswith("role:")
    }
    return {
        "source_publication_contract_version": PUBLICATION_CONTRACT_VERSION,
        **{key: source_row.get(key) or None for key in CORE_ROLE_KEYS},
        "source_role_tags": source_role_tags,
    }


def _validate_roles(roles: Any, *, marked: bool) -> None:
    if not isinstance(roles, Mapping) or tuple(roles) != ROLE_KEYS:
        raise ConstructionMasterV2Error("row role object schema changed")
    if not isinstance(roles.get("source_role_tags"), dict) or any(
        not isinstance(key, str) or not key.startswith("role:")
        for key in roles["source_role_tags"]
    ):
        raise ConstructionMasterV2Error("source_role_tags changed or was normalized")
    if any(
        roles.get(key) is not None and not isinstance(roles.get(key), str)
        for key in CORE_ROLE_KEYS
    ):
        raise ConstructionMasterV2Error("core role values must be exact text or null")
    if marked:
        if not _is_exact_publication_contract_version(
            roles.get("source_publication_contract_version")
        ):
            raise ConstructionMasterV2Error("marked replacement row lost contract marker")
    elif dict(roles) != NULL_ROLES:
        raise ConstructionMasterV2Error("unmarked inherited row gained a role")


def _strip_roles(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result.pop("roles", None)
    return result


def _role_projection(record_id: str, roles: Mapping[str, Any]) -> dict[str, Any]:
    return {"record_id": record_id, "roles": dict(roles)}


def _id_digest(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(values):
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


class _BuildCounts:
    def __init__(self) -> None:
        self.total = 0
        self.row_ids: set[str] = set()
        self.tiers: Counter[str] = Counter()
        self.artifacts: Counter[str] = Counter()
        self.kinds: Counter[str] = Counter()
        self.statuses: Counter[str] = Counter()
        self.marker_rows = 0
        self.rows_with_any_role = 0
        self.rows_with_source_role_tags = 0
        self.role_presence: Counter[str] = Counter()
        self.tier_a_digest = hashlib.sha256()

    def add(self, row: Mapping[str, Any]) -> None:
        stripped = _strip_roles(row)
        try:
            legacy._validate_output_row(stripped)
        except legacy.ConstructionMasterError as error:
            raise ConstructionMasterV2Error(str(error)) from error
        row_id = row.get("row_id")
        if not isinstance(row_id, str) or row_id in self.row_ids:
            raise ConstructionMasterV2Error("master row ID is absent or repeated")
        self.row_ids.add(row_id)
        marked = row["source"]["artifact_id"] == REPLACEMENT_ARTIFACT_ID
        _validate_roles(row.get("roles"), marked=marked)
        roles = row["roles"]
        self.total += 1
        self.tiers[str(row["tier"])] += 1
        self.artifacts[str(row["source"]["artifact_id"])] += 1
        self.kinds[str(row["observation_kind"])] += 1
        self.statuses[str(row["lifecycle"]["normalized_status"])] += 1
        self.marker_rows += marked
        any_role = any(roles.get(key) is not None for key in CORE_ROLE_KEYS) or bool(
            roles["source_role_tags"]
        )
        self.rows_with_any_role += any_role
        self.rows_with_source_role_tags += bool(roles["source_role_tags"])
        for key in CORE_ROLE_KEYS:
            self.role_presence[key] += roles.get(key) is not None
        if row["tier"] == "A":
            self.tier_a_digest.update(
                _canonical_line(legacy._tier_a_arithmetic_projection(stripped))
            )


def _replacement_rows(
    replacement: Mapping[str, Any],
    resolved: Mapping[str, Path],
    old_rows: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data_path = resolved[str(replacement["data"]["path"])]
    evidence_path = resolved[str(replacement["evidence"]["path"])]
    source_rows = list(legacy._csv_rows(data_path))
    if len(source_rows) != EXPECTED_FIXED["replacement_rows"]:
        raise ConstructionMasterV2Error("replacement row count changed")
    fieldnames = set(source_rows[0]) if source_rows else set()
    if not {*CORE_ROLE_KEYS, "tags_json"}.issubset(fieldnames):
        raise ConstructionMasterV2Error("replacement role columns are absent")
    evidence = legacy._evidence_map(evidence_path)
    replacement_ids: set[str] = set()
    result: list[dict[str, Any]] = []
    role_digest = hashlib.sha256()
    row_content_digest = hashlib.sha256()
    transferred_satellite_links = 0
    transferred_resolution_advisories = 0
    for source_row in source_rows:
        entity_id = source_row.get("entity_id", "")
        if not entity_id or entity_id in replacement_ids:
            raise ConstructionMasterV2Error(
                "replacement source record ID is absent or repeated"
            )
        replacement_ids.add(entity_id)
        previous = old_rows.get(entity_id)
        satellite_links = (
            {entity_id: list(previous["satellite_links"])} if previous else {}
        )
        advisories = (
            {entity_id: list(previous["resolution_advisories"])} if previous else {}
        )
        if previous:
            transferred_satellite_links += len(previous["satellite_links"])
            transferred_resolution_advisories += len(previous["resolution_advisories"])
        try:
            row = legacy._release_row(
                source_row,
                artifact=replacement,
                artifact_sha=str(replacement["data"]["sha256"]),
                manifest_sha=str(replacement["manifest"]["sha256"]),
                evidence=evidence,
                satellite_by_entity=satellite_links,
                advisories_by_entity=advisories,
                tier="A",
            )
        except legacy.ConstructionMasterError as error:
            raise ConstructionMasterV2Error(str(error)) from error
        roles = _roles_from_source(source_row)
        row["roles"] = roles
        role_digest.update(_canonical_line(_role_projection(entity_id, roles)))
        row_content_digest.update(_canonical_line(_strip_roles(row)))
        result.append(row)
    old_ids = set(old_rows)
    if not old_ids.issubset(replacement_ids):
        raise ConstructionMasterV2Error("replacement removed a v33 construction row")
    return result, {
        "added_ids": replacement_ids - old_ids,
        "replacement_ids": replacement_ids,
        "role_projection_sha256": role_digest.hexdigest(),
        "rows_without_roles_sha256": row_content_digest.hexdigest(),
        "transferred_resolution_advisories": transferred_resolution_advisories,
        "transferred_satellite_links": transferred_satellite_links,
        "unchanged_ids": replacement_ids & old_ids,
    }


def _rows_and_invariants(
    definition: Mapping[str, Any], resolved: Mapping[str, Path]
) -> tuple[Iterator[dict[str, Any]], dict[str, Any]]:
    inputs = definition["inputs"]
    base = inputs["base_master"]
    base_path = resolved[str(base["jsonl"]["path"])]
    source = _jsonl_rows(base_path)
    old_rows: dict[str, dict[str, Any]] = {}
    first_inherited: dict[str, Any] | None = None
    for row in source:
        artifact_id = row.get("source", {}).get("artifact_id")
        if artifact_id == BASE_ARTIFACT_ID:
            if first_inherited is not None:
                raise ConstructionMasterV2Error("v33 base rows are not one prefix block")
            record_id = row.get("source", {}).get("record_id")
            if not isinstance(record_id, str) or record_id in old_rows:
                raise ConstructionMasterV2Error("v33 base record ID repeats")
            old_rows[record_id] = row
            continue
        first_inherited = row
        break
    if len(old_rows) != EXPECTED_FIXED["base_replaced_rows"] or first_inherited is None:
        raise ConstructionMasterV2Error("v14 replacement boundary changed")
    replacement_rows, replacement_meta = _replacement_rows(
        inputs["replacement_release"], resolved, old_rows
    )
    inherited_digest = hashlib.sha256()
    inherited_count = 0

    def rows() -> Iterator[dict[str, Any]]:
        nonlocal inherited_count
        yield from replacement_rows
        assert first_inherited is not None
        for base_row in chain((first_inherited,), source):
            if base_row.get("source", {}).get("artifact_id") == BASE_ARTIFACT_ID:
                raise ConstructionMasterV2Error("v33 row occurs after replacement boundary")
            inherited_digest.update(_canonical_line(base_row))
            inherited_count += 1
            inherited = dict(base_row)
            inherited["roles"] = dict(NULL_ROLES)
            if _strip_roles(inherited) != base_row:
                raise ConstructionMasterV2Error("inherited row changed beyond roles")
            yield inherited

    invariants = {
        "added_source_record_ids_sha256": _id_digest(replacement_meta["added_ids"]),
        "base_replaced_source_record_ids_sha256": _id_digest(old_rows),
        "inherited_digest": inherited_digest,
        "inherited_rows": lambda: inherited_count,
        "replacement_role_projection_sha256": replacement_meta[
            "role_projection_sha256"
        ],
        "replacement_rows_without_roles_sha256": replacement_meta[
            "rows_without_roles_sha256"
        ],
        "replacement_source_record_ids_sha256": _id_digest(
            replacement_meta["replacement_ids"]
        ),
        "transferred_resolution_advisories": replacement_meta[
            "transferred_resolution_advisories"
        ],
        "transferred_satellite_links": replacement_meta[
            "transferred_satellite_links"
        ],
        "unchanged_rows": len(replacement_meta["unchanged_ids"]),
    }
    return rows(), invariants


def _flatten(row: Mapping[str, Any]) -> dict[str, Any]:
    result = legacy._flatten(_strip_roles(row))
    roles = row["roles"]
    result.update(
        {
            "source_publication_contract_version": roles[
                "source_publication_contract_version"
            ],
            **{key: roles[key] for key in CORE_ROLE_KEYS},
            "source_role_tags_json": _compact(roles["source_role_tags"]),
        }
    )
    return result


def _assert_expected(
    expected: Mapping[str, Any], counts: _BuildCounts, invariants: Mapping[str, Any]
) -> None:
    actual_fixed = {
        "added_replacement_rows": 63,
        "base_replaced_rows": 199,
        "base_rows": 109_111,
        "inherited_rows": invariants["inherited_rows"](),
        "replacement_rows": counts.artifacts[REPLACEMENT_ARTIFACT_ID],
        "replacement_rows_with_any_role": counts.rows_with_any_role,
        "replacement_rows_with_customers": counts.role_presence["customers"],
        "replacement_rows_with_operator": counts.role_presence["operator"],
        "replacement_rows_with_owner": counts.role_presence["owner"],
        "replacement_rows_with_source_role_tags": counts.rows_with_source_role_tags,
        "replacement_rows_with_tenants": counts.role_presence["tenants"],
        "replacement_rows_with_users": counts.role_presence["users"],
        "rows_with_contract_marker": counts.marker_rows,
        "satellite_recovery_control_plane_bytes": 15_313,
        "satellite_recovery_rows": 0,
        "tier_a_rows": counts.tiers["A"],
        "tier_b_rows": counts.tiers["B"],
        "tier_c_rows": counts.tiers["C"],
        "total_rows": counts.total,
        "unchanged_replacement_rows": invariants["unchanged_rows"],
    }
    if actual_fixed != EXPECTED_FIXED or any(
        expected[key] != value for key, value in actual_fixed.items()
    ):
        raise ConstructionMasterV2Error(
            f"replacement fixed invariants drifted: {actual_fixed!r}"
        )
    actual_digests = {
        "added_source_record_ids_sha256": invariants[
            "added_source_record_ids_sha256"
        ],
        "base_replaced_source_record_ids_sha256": invariants[
            "base_replaced_source_record_ids_sha256"
        ],
        "inherited_rows_without_roles_sha256": invariants[
            "inherited_digest"
        ].hexdigest(),
        "replacement_role_projection_sha256": invariants[
            "replacement_role_projection_sha256"
        ],
        "replacement_rows_without_roles_sha256": invariants[
            "replacement_rows_without_roles_sha256"
        ],
        "replacement_source_record_ids_sha256": invariants[
            "replacement_source_record_ids_sha256"
        ],
        "tier_a_arithmetic_projection_sha256": counts.tier_a_digest.hexdigest(),
    }
    if any(expected[key] != value for key, value in actual_digests.items()):
        raise ConstructionMasterV2Error(
            f"replacement digest invariants drifted: {actual_digests!r}"
        )


def _coverage(
    counts: _BuildCounts,
    expected: Mapping[str, Any],
    recovery: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "freshness": {
            "historical_status_warning": (
                "Lifecycle values are source-scoped historical observations anchored "
                "to reported_status_date. Inclusion does not prove that construction "
                "persisted after that date; a project may since have opened, stalled, "
                "changed, or been cancelled."
            ),
            "latest_recorded_pipeline_view_not_current_census": True,
        },
        "replacement": {
            "added_rows": 63,
            "base_artifact_id": BASE_ARTIFACT_ID,
            "base_rows_replaced": 199,
            "publication_contract_version": 4,
            "replacement_artifact_id": REPLACEMENT_ARTIFACT_ID,
            "replacement_rows": 262,
            "unchanged_source_record_ids": 199,
        },
        "role_counts": {
            "rows_with_any_role": counts.rows_with_any_role,
            "rows_with_contract_marker": counts.marker_rows,
            "rows_with_source_role_tags": counts.rows_with_source_role_tags,
            "with_core_role": dict(sorted(counts.role_presence.items())),
        },
        "row_counts": {
            "by_normalized_status": dict(sorted(counts.statuses.items())),
            "by_observation_kind": dict(sorted(counts.kinds.items())),
            "by_source_artifact": dict(sorted(counts.artifacts.items())),
            "by_tier": dict(sorted(counts.tiers.items())),
            "total": counts.total,
            "unique_physical_site_count": None,
        },
        "satellite_recovery_acceptance": dict(recovery),
        "scope": SCOPE_POLICY,
        "schema_version": SCHEMA_VERSION,
        "replacement_invariants": dict(expected),
    }


def _readme() -> bytes:
    return (
        "# Public/open construction master v16 (schema v2)\n\n"
        "This immutable source-observation ledger contains 109,174 rows: 382 Tier A "
        "source-supported pipeline observations, 6,298 Tier B review leads, and "
        "102,494 Tier C structural or computer-vision discovery observations. It is "
        "not a deduplicated physical-site census and claims no global completeness.\n\n"
        "V16 byte-pins v14, replaces only its 199 v33 open-seed rows with the 262-row "
        "publication-contract-v4 v42 pipeline, and preserves the other 108,912 rows "
        "exactly after the v2 roles object is removed. Role strings are copied verbatim "
        "only from marked v42 columns. All role:* tags are retained as an opaque "
        "source_role_tags dictionary; developer, contractor, tenant, customer, user, "
        "owner, and operator labels are never inferred or relabelled.\n\n"
        "Lifecycle values are historical observations anchored to each row's reported "
        "status date. Inclusion does not prove that construction persisted: a project "
        "may since have opened, stalled, changed, or been cancelled. Capacity values "
        "retain their source type and stage and are not globally additive.\n\n"
        "Unknown033 is represented only by four accepted control-plane files totaling "
        "15,313 bytes. It contributes zero rows, creates no imagery inference, promotes "
        "no source batch, and this builder never traverses its batch, inventory, source "
        "snapshot, or payload files.\n"
    ).encode("utf-8")


def _attribution(base_attribution: bytes) -> bytes:
    suffix = (
        "\nV16 role values and lifecycle observations are compact factual fields copied "
        "from the pinned open-seed v42 release under each source row's recorded terms.\n"
        "Unknown033 recovery metadata is review-only control-plane context; no satellite "
        "payload, imagery inference, or recovered source row is redistributed here.\n"
    ).encode("utf-8")
    return base_attribution.rstrip(b"\n") + b"\n" + suffix


def _write(path: Path, raw: bytes) -> None:
    with path.open("xb") as destination:
        destination.write(raw)
        destination.flush()
        os.fsync(destination.fileno())


def _build_into(definition_path: Path, destination: Path) -> dict[str, Any]:
    definition, definition_raw, package_root, resolved, context = validate_definition(
        definition_path
    )
    rows, invariants = _rows_and_invariants(definition, resolved)
    counts = _BuildCounts()
    jsonl_path = destination / JSONL_FILENAME
    csv_path = destination / CSV_FILENAME
    with jsonl_path.open("xb") as jsonl, csv_path.open(
        "x", encoding="utf-8", newline=""
    ) as csv_output:
        writer = csv.DictWriter(
            csv_output, fieldnames=CSV_FIELDS, extrasaction="raise", lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            counts.add(row)
            jsonl.write(_canonical_line(row))
            writer.writerow(_flatten(row))
        jsonl.flush()
        os.fsync(jsonl.fileno())
        csv_output.flush()
        os.fsync(csv_output.fileno())
    _assert_expected(definition["expected"], counts, invariants)
    coverage = _coverage(counts, definition["expected"], context["recovery"])
    base_attribution = resolved[
        str(definition["inputs"]["base_master"]["attribution"]["path"])
    ].read_bytes()
    _write(destination / COVERAGE_FILENAME, _canonical_json(coverage))
    _write(destination / README_FILENAME, _readme())
    _write(destination / ATTRIBUTION_FILENAME, _attribution(base_attribution))
    output_names = BUNDLE_FILES - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    outputs = {
        name: _checkpoint(destination / name) for name in sorted(output_names)
    }
    outputs[JSONL_FILENAME]["records"] = counts.total
    outputs[CSV_FILENAME]["records"] = counts.total
    manifest = {
        "definition": {
            "bytes": len(definition_raw),
            "path": definition_path.resolve().relative_to(package_root).as_posix(),
            "sha256": _sha256(definition_raw),
        },
        "format": BUNDLE_FORMAT,
        "generated_at": GENERATED_AT,
        "input_checkpoints": context["input_lineage"],
        "master_id": MASTER_ID,
        "outputs": outputs,
        "row_counts": coverage["row_counts"],
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE_POLICY,
    }
    manifest_raw = _canonical_json(manifest)
    _write(destination / MANIFEST_FILENAME, manifest_raw)
    _write(
        destination / MANIFEST_HASH_FILENAME,
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii"),
    )
    return manifest


def write_construction_master_v2(
    definition_path: str | Path,
    output_directory: str | Path,
    *,
    freeze: bool = False,
) -> dict[str, Any]:
    """Atomically build the v16 role-preserving master without network access."""

    definition = Path(definition_path)
    destination = Path(os.path.abspath(os.fspath(output_directory)))
    if destination.exists() or destination.is_symlink():
        raise ConstructionMasterV2Error(f"refusing existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent)
    )
    try:
        manifest = _build_into(definition, stage)
        _validate_static(stage, frozen=False)
        if freeze:
            for entry in stage.iterdir():
                entry.chmod(0o444)
            stage.chmod(0o555)
        stage.replace(destination)
    except BaseException:
        if stage.exists() and not stage.is_symlink():
            stage.chmod(0o755)
            for entry in stage.iterdir():
                if not entry.is_symlink():
                    entry.chmod(0o644)
            shutil.rmtree(stage)
        raise
    return manifest


def is_frozen_master_v2(directory: str | Path) -> bool:
    root = Path(directory)
    return (
        not root.is_symlink()
        and root.is_dir()
        and stat.S_IMODE(root.stat().st_mode) == 0o555
        and all(
            entry.is_file()
            and not entry.is_symlink()
            and stat.S_IMODE(entry.stat().st_mode) == 0o444
            for entry in root.iterdir()
        )
    )


def _validate_static(directory: Path, *, frozen: bool) -> dict[str, Any]:
    if directory.is_symlink() or not directory.is_dir():
        raise ConstructionMasterV2Error("v2 master must be a regular directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise ConstructionMasterV2Error("v2 master closed file set changed")
    manifest, manifest_raw = _json_file(directory / MANIFEST_FILENAME, "manifest")
    if manifest_raw != _canonical_json(manifest):
        raise ConstructionMasterV2Error("v2 manifest is not canonical")
    if (directory / MANIFEST_HASH_FILENAME).read_bytes() != (
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    ):
        raise ConstructionMasterV2Error("v2 manifest sidecar changed")
    if (
        manifest.get("format") != BUNDLE_FORMAT
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("master_id") != MASTER_ID
        or manifest.get("generated_at") != GENERATED_AT
        or manifest.get("scope") != SCOPE_POLICY
    ):
        raise ConstructionMasterV2Error("v2 manifest identity changed")
    expected_outputs = BUNDLE_FILES - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    if set(manifest.get("outputs", {})) != expected_outputs:
        raise ConstructionMasterV2Error("v2 output inventory changed")
    for name in expected_outputs:
        expected = manifest["outputs"][name]
        if _checkpoint(directory / name) != {
            "bytes": expected.get("bytes"),
            "sha256": expected.get("sha256"),
        }:
            raise ConstructionMasterV2Error(f"v2 output changed: {name}")
    coverage, coverage_raw = _json_file(directory / COVERAGE_FILENAME, "coverage")
    if (
        coverage_raw != _canonical_json(coverage)
        or coverage.get("scope") != SCOPE_POLICY
        or coverage.get("row_counts") != manifest.get("row_counts")
        or coverage.get("replacement_invariants") is None
    ):
        raise ConstructionMasterV2Error("v2 coverage differs from manifest")
    if frozen and not is_frozen_master_v2(directory):
        raise ConstructionMasterV2Error("v2 master must be frozen 0555/0444")
    return manifest


def validate_construction_master_v2(
    directory: str | Path,
    *,
    definition_path: str | Path,
    reproduce: bool = True,
) -> dict[str, Any]:
    """Validate the frozen bundle and optionally reproduce every byte offline."""

    root = Path(directory)
    manifest = _validate_static(root, frozen=True)
    definition, _raw, _package_root, _resolved, _context = validate_definition(
        definition_path
    )
    if manifest.get("definition", {}).get("sha256") != _sha256(
        _canonical_json(definition)
    ):
        raise ConstructionMasterV2Error("v2 manifest definition binding changed")
    if reproduce:
        with tempfile.TemporaryDirectory(
            prefix="construction-master-v2-reproduce-"
        ) as temporary:
            rebuilt = Path(temporary) / "bundle"
            write_construction_master_v2(definition_path, rebuilt)
            for name in sorted(BUNDLE_FILES):
                if _checkpoint(root / name) != _checkpoint(rebuilt / name):
                    raise ConstructionMasterV2Error(
                        f"v2 output differs from offline reproduction: {name}"
                    )
    return manifest


__all__ = [
    "ConstructionMasterV2Error",
    "CSV_FIELDS",
    "MASTER_ID",
    "NULL_ROLES",
    "PUBLICATION_CONTRACT_VERSION",
    "ROLE_KEYS",
    "SCOPE_POLICY",
    "is_frozen_master_v2",
    "validate_construction_master_v2",
    "validate_definition",
    "write_construction_master_v2",
]
