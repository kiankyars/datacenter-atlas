"""Private/prepublication coverage-audit v32 successor.

V32 replaces the active open-seed and federation inputs with v97 and v38 and
binds exact identity v14, timeline v11, construction master v32, and
construction map v32 as non-row-producing acceptance gates. Coverage remains
source scoped: children are not merged, current status is not inferred, and
unique physical sites and SemiAnalysis parity remain unknown.

Private preparation may validate only the byte-pinned master/map v32 candidate
paths. Public-default dependency validation requires their immutable final
paths and never falls back to candidates.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import coverage_audit_v5 as legacy
from . import coverage_audit_v31 as predecessor
from .open_seed_v56 import tree_digest

ROOT = Path(__file__).resolve().parents[1]
GENERATED_AT = "2026-07-24T22:33:00Z"
AUDIT_ID = "public-open-coverage-v32"
DEFINITION_RELATIVE_PATH = (
    "sources/coverage-audit-2026-07-22-public-open-v32.json"
)
BUNDLE_RELATIVE_PATH = "audits/2026-07-22-public-open-coverage-v32"
DEFINITION = ROOT / DEFINITION_RELATIVE_PATH
BUNDLE = ROOT / BUNDLE_RELATIVE_PATH

BASE_DEFINITION = ROOT / "sources/coverage-audit-2026-07-21-public-open-v31.json"
BASE_BUNDLE = ROOT / "audits/2026-07-21-public-open-coverage-v31"
OLD_RELEASE_ID = "epoch-official-open-seed-v86"
NEW_RELEASE_ID = "2026-07-22-open-seed-v97"

V83_SUPPORT_ID = predecessor.V83_SUPPORT_ID
EXPECTED_REVIEW_ACCOUNTING = predecessor.EXPECTED_REVIEW_ACCOUNTING
EXPECTED_EXACT_DUPLICATE_GROUPS = predecessor.EXPECTED_EXACT_DUPLICATE_GROUPS

EXPECTED_TIMELINE_GATE = {
    "multi_observation_timelines": 24,
    "observations": 607,
    "repeated_status_multi_observation_timelines": 9,
    "single_observation_timelines": 559,
    "single_old_observation_timelines": 38,
    "source_families": 297,
    "status_changing_multi_observation_timelines": 15,
    "timelines": 583,
}
EXPECTED_COVERAGE_COUNTS = {
    "confirmed_duplicate_relationships": None,
    "coverage_groups": 1_089,
    "methodology_support_artifacts": 2,
    "open_gaps": 5_048,
    "source_scoped_entity_records": 16_478,
    "unique_physical_sites": None,
    "v57_review_jobs": 74,
    "v57_review_views": 71,
    "v83_decision_rows": 68,
    "v83_exact_duplicate_groups": 3,
    "v83_promotions": 0,
    "v83_rejected_decision_rows": 21,
    "v83_retained_decision_rows": 47,
    "v83_unique_exact_visual_evidence_sets": 65,
    "v83_unique_retained_exact_visual_evidence_sets": 44,
}

DEPENDENCIES: Mapping[str, Mapping[str, Any]] = {
    "accepted_coverage_v31": {
        "bundle": "audits/2026-07-21-public-open-coverage-v31",
        "definition": "sources/coverage-audit-2026-07-21-public-open-v31.json",
        "definition_sha256": (
            "cd7e3f2a0b519ab0c8de44c31c1edf7facd5e3ccc2a43f136750cc209ad93030"
        ),
        "manifest_sha256": (
            "717917b2c566da936b2f85fd45f17d71b6ecd83ac48e2111d1bd183b052db132"
        ),
        "timestamp": "2026-07-22T01:17:00Z",
        "timestamp_keys": ("generated_at",),
        "tree_sha256": (
            "21b037ce0fb845184fe6cede7a954815482f5b7df84e79b62c06f1b70c77d45c"
        ),
    },
    "exact_identity_v14": {
        "bundle": "exact_identity_decisions/2026-07-22-public-open-v14",
        "definition": (
            "sources/exact-identity-decisions-2026-07-22-public-open-v14.json"
        ),
        "definition_sha256": (
            "2efe24eaff33a91d210f3139a66b9538fb1768e9d8695e1f9ddebddd6d1475f1"
        ),
        "manifest_sha256": (
            "268b064077e82ab5b3d90459234770743838b22cc90a72021b96f788d4947ba4"
        ),
        "timestamp": "2026-07-24T22:30:00Z",
        "timestamp_keys": ("recorded_at",),
        "tree_sha256": (
            "1a4c733425316103ea50c24e83617a38bb339d927f45f13c470937356d20b0ac"
        ),
    },
    "federation_v38": {
        "bundle": "federated_indexes/2026-07-22-public-open-v38",
        "definition": "sources/federation-2026-07-22-public-open-v38.json",
        "definition_sha256": (
            "fc0f6985c403b1562f439c2abd31b244a6784f5ed7030edd349c6a8ba92a09fb"
        ),
        "index_sha256": (
            "cb45c67a4286cb8ab8da9b6cdb5ea3733886fe035236c7590de14749aad7d6f0"
        ),
        "manifest_sha256": (
            "4c8f79ca5a17d9dfb1c02a1f7ee01da62ece19d2c265854b82cb701c8012b453"
        ),
        "timestamp": "2026-07-24T20:45:00Z",
        "timestamp_keys": ("generated_at",),
        "tree_sha256": (
            "84b7329e7f62da8ebf3e868d8026d03b49b36a8d5290bb0004c34d4518f9a5d5"
        ),
    },
    "map_v32": {
        "bundle": "construction_maps/2026-07-22-public-open-v32",
        "definition": "sources/construction-map-2026-07-22-public-open-v32.json",
        "definition_sha256": (
            "50248a1fafc5ce96693592b990be6fc9352233091e4c4210817db5d6936cef3f"
        ),
        "index_sha256": (
            "b52ece43b13e7d626115f3f8b3f1393e5e82d4e4821e09b4a383ee96d03f6712"
        ),
        "manifest_sha256": (
            "8b321d67ef80a6af0fbc0d39d60b5a10387777a1ab97d3a1a0f45a5b9bfa952d"
        ),
        "private_bundle": (
            "construction_maps/.2026-07-22-public-open-v32.candidate-z7hgjpib"
        ),
        "private_definition": (
            "sources/.construction-map-2026-07-22-public-open-v32.json."
            "candidate-jn5inlyj"
        ),
        "timestamp": "2026-07-24T22:32:00Z",
        "timestamp_keys": ("generated_at",),
        "tree_sha256": (
            "78d444c9b289ccc23acdbc7a7a2ff5fbedf0df16ece8100da328cb7fde05572e"
        ),
    },
    "master_v32": {
        "bundle": "construction_master/2026-07-22-public-open-v32",
        "definition": "sources/construction-master-2026-07-22-public-open-v32.json",
        "definition_sha256": (
            "05ed7f1eb48a54efb9e21224356d85108c897e977e2d458d52d10d2c0e14dbdb"
        ),
        "manifest_sha256": (
            "aee4310084012a0adc77b0833df6325c6a2da57d4379fe6b57b49b133876294a"
        ),
        "private_bundle": (
            ".construction-master-v32.transaction-8gsvvbir/bundle"
        ),
        "private_definition": (
            ".construction-master-v32.transaction-8gsvvbir/"
            "construction-master-2026-07-22-public-open-v32.json"
        ),
        "timestamp": "2026-07-24T22:31:00Z",
        "timestamp_keys": ("generated_at",),
        "tree_sha256": (
            "9a651415dbf66c99bcf07bc6aa268a05fc43aa03afaca1eea94cf8b31fed4084"
        ),
    },
    "open_seed_v97": {
        "bundle": "releases/2026-07-22-open-seed-v97",
        "definition": "sources/open-seed-2026-07-22-v97.json",
        "definition_sha256": (
            "32f22ccc74ec6ec33dc9bc7377a83bfee83f88dff3555555fc89cb43a27d673f"
        ),
        "manifest_sha256": (
            "0a6f41f4239944df27f2ce70e81a089b91cec401f154bbae28412b27a4d00fdd"
        ),
        "timestamp": "2026-07-22T06:06:40Z",
        "timestamp_keys": ("build", "recorded_at"),
        "tree_sha256": (
            "5136ad66f56b7474053ff3b8cbbffca1f3df3479d8a30745a1502917fa0e7954"
        ),
    },
    "timeline_v11": {
        "bundle": "construction_timelines/2026-07-22-public-open-v11",
        "definition": "sources/construction-timeline-2026-07-22-public-open-v11.json",
        "definition_sha256": (
            "86ad1866104028cf17b4cbc0a72c39f22b83a357ee03727ceb1daedfa2be66d0"
        ),
        "manifest_sha256": (
            "d4c6708aa08241e8319aace1e14b21d9f189e996c5dcfe8a95ff77a0d8b746e1"
        ),
        "timestamp": "2026-07-24T20:30:00Z",
        "timestamp_keys": ("generated_at",),
        "tree_sha256": (
            "2930cad0dc7c9733b5b522cba1a2a9403d699ee363c86feaf890c923c6d19b87"
        ),
    },
    "v83_review_support": {
        "bundle": (
            "satellite_change_reviews/"
            "2026-07-21-open-seed-v83-active-unreviewed-single-68-review-v1"
        ),
        "definition": (
            "satellite_change_reviews/"
            "2026-07-21-open-seed-v83-active-unreviewed-single-68-review-v1/"
            "definition.json"
        ),
        "definition_is_member": True,
        "definition_sha256": (
            "7ab24635cb6fd3bc8a64740f6318a4b21bcbd03b74e243a3489cc3fbb415a2f6"
        ),
        "manifest_sha256": predecessor.V83_REVIEW_MANIFEST_SHA256,
        "timestamp": "2026-07-22T00:36:00.000000Z",
        "timestamp_keys": ("generated_at",),
        "tree_sha256": predecessor.V83_REVIEW_TREE_SHA256,
    },
}

FORBIDDEN_STALE_ACTIVE_TOKENS = (
    b"../releases/2026-07-21-open-seed-v86",
    b"../federated_indexes/2026-07-21-public-open-v35",
    b"construction-master-2026-07-21-public-open-v31",
    b"construction-map-2026-07-21-public-open-v31",
    b"construction-timeline-2026-07-21-public-open-v8",
    b"exact-identity-decisions-2026-07-21-public-open-v11",
)

BUILDER_PATH = Path(__file__).resolve()
ROOT_SHIM_PATH = ROOT / "coverage_audit_v32.py"
CLI_PATH = ROOT / "scripts/build_coverage_audit_v32.py"
CARRIER_PATH = Path(legacy.__file__).resolve()
PREDECESSOR_PATH = Path(predecessor.__file__).resolve()


class CoverageAuditV32Error(RuntimeError):
    """Raised when the bounded v32 private successor cannot be proved."""


def _canonical_json(value: object) -> bytes:
    return predecessor._canonical_json(value)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _parse_utc(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CoverageAuditV32Error(f"{label} must use canonical UTC")
    try:
        parsed = datetime.fromisoformat(value).astimezone(UTC)
    except ValueError as error:
        raise CoverageAuditV32Error(f"{label} must use canonical UTC") from error
    allowed = {
        parsed.strftime("%Y-%m-%dT%H:%M:%SZ"),
        parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }
    if value not in allowed:
        raise CoverageAuditV32Error(f"{label} must use canonical UTC")
    return parsed


def _nested(document: Mapping[str, Any], keys: Sequence[str], label: str) -> Any:
    value: Any = document
    for key in keys:
        if not isinstance(value, Mapping) or key not in value:
            raise CoverageAuditV32Error(f"{label} timestamp field is absent")
        value = value[key]
    return value


def _resolved(
    lane: str, kind: str, *, allow_private_dependencies: bool
) -> tuple[Path, bool]:
    dependency = DEPENDENCIES[lane]
    private_key = f"private_{kind}"
    public = ROOT / dependency[kind]
    if public.exists() or not allow_private_dependencies or private_key not in dependency:
        return public, False
    private = ROOT / dependency[private_key]
    if not private.exists():
        raise CoverageAuditV32Error(
            f"{lane} public final and explicit private {kind} are absent"
        )
    return private, True


def _regular_bytes(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise CoverageAuditV32Error(f"{label} is not a regular file")
    return path.read_bytes()


def _require_frozen_tree(path: Path, expected: str, label: str) -> None:
    if path.is_symlink() or not path.is_dir():
        raise CoverageAuditV32Error(f"{label} is not a regular directory")
    if tree_digest(path) != expected:
        raise CoverageAuditV32Error(f"{label} tree changed")
    for member in (path, *path.rglob("*")):
        if member.is_symlink():
            raise CoverageAuditV32Error(f"{label} contains a symlink")
        expected_mode = 0o555 if member.is_dir() else 0o444
        if stat.S_IMODE(member.stat().st_mode) != expected_mode:
            raise CoverageAuditV32Error(f"{label} is not frozen: {member}")


def _require_dependency(
    lane: str, *, allow_private_dependencies: bool
) -> tuple[datetime, bool]:
    dependency = DEPENDENCIES[lane]
    definition, private_definition = _resolved(
        lane, "definition", allow_private_dependencies=allow_private_dependencies
    )
    bundle, private_bundle = _resolved(
        lane, "bundle", allow_private_dependencies=allow_private_dependencies
    )
    if private_definition != private_bundle:
        raise CoverageAuditV32Error(f"{lane} mixes private and public dependency roots")
    definition_raw = _regular_bytes(definition, f"{lane} definition")
    if (
        _sha256(definition_raw) != dependency["definition_sha256"]
        or stat.S_IMODE(definition.stat().st_mode) != 0o444
    ):
        raise CoverageAuditV32Error(f"{lane} definition changed")
    manifest_raw = _regular_bytes(bundle / "manifest.json", f"{lane} manifest")
    if _sha256(manifest_raw) != dependency["manifest_sha256"]:
        raise CoverageAuditV32Error(f"{lane} manifest changed")
    index_sha = dependency.get("index_sha256")
    if index_sha is not None:
        index_name = (
            "federated-index.json"
            if lane == "federation_v38"
            else "construction-map-index.json.gz"
        )
        if _sha256(_regular_bytes(bundle / index_name, f"{lane} index")) != index_sha:
            raise CoverageAuditV32Error(f"{lane} index changed")
    _require_frozen_tree(bundle, dependency["tree_sha256"], lane)
    document = json.loads(definition_raw)
    observed = _nested(document, dependency["timestamp_keys"], lane)
    if observed != dependency["timestamp"]:
        raise CoverageAuditV32Error(f"{lane} timestamp changed")
    timestamp = _parse_utc(observed, f"{lane} timestamp")
    paths = (definition, bundle, *bundle.rglob("*"))
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if max(birth, metadata.st_mtime) > timestamp.timestamp() + 0.000_001:
            raise CoverageAuditV32Error(f"{lane} post-dates its declared timestamp")
    if not private_definition:
        roots = (
            (bundle,)
            if dependency.get("definition_is_member")
            else (definition, bundle)
        )
        if any(
            root.stat(follow_symlinks=False).st_ctime + 0.000_001
            < timestamp.timestamp()
            for root in roots
        ):
            raise CoverageAuditV32Error(f"{lane} final rename predates its timestamp")
    return timestamp, private_definition


def _require_inputs(
    *, allow_private_dependencies: bool = False
) -> Mapping[str, bool]:
    private_modes = {}
    for lane in sorted(DEPENDENCIES):
        _timestamp, private = _require_dependency(
            lane, allow_private_dependencies=allow_private_dependencies
        )
        private_modes[lane] = private
    if not allow_private_dependencies and any(private_modes.values()):
        raise CoverageAuditV32Error("public validation accepted a private dependency")
    return private_modes


def _require_dependencies_before(
    target: datetime, *, allow_private_dependencies: bool
) -> None:
    for lane in sorted(DEPENDENCIES):
        timestamp, _private = _require_dependency(
            lane, allow_private_dependencies=allow_private_dependencies
        )
        if timestamp >= target:
            raise CoverageAuditV32Error(f"{lane} is not prior to coverage v32")


def definition_document(generated_at: str = GENERATED_AT) -> dict[str, Any]:
    """Return the exact accepted-v31 to v32 source-scoped definition."""

    parsed = _parse_utc(generated_at, "coverage v32 generated_at")
    if generated_at != parsed.strftime("%Y-%m-%dT%H:%M:%SZ"):
        raise CoverageAuditV32Error(
            "coverage v32 generated_at must use canonical UTC seconds"
        )
    raw = _regular_bytes(BASE_DEFINITION, "accepted coverage v31 definition")
    if _sha256(raw) != DEPENDENCIES["accepted_coverage_v31"]["definition_sha256"]:
        raise CoverageAuditV32Error("accepted coverage v31 definition changed")
    result = deepcopy(json.loads(raw))
    result["audit_id"] = AUDIT_ID
    result["generated_at"] = generated_at
    matches = [
        child for child in result["children"] if child["release_id"] == OLD_RELEASE_ID
    ]
    if len(matches) != 1:
        raise CoverageAuditV32Error("coverage v31 open-seed child boundary changed")
    matches[0].update(
        {
            "expected_manifest_sha256": DEPENDENCIES["open_seed_v97"][
                "manifest_sha256"
            ],
            "release_id": NEW_RELEASE_ID,
            "release_path": "../releases/2026-07-22-open-seed-v97",
        }
    )
    result["federated_index"] = {
        "expected_manifest_sha256": DEPENDENCIES["federation_v38"][
            "manifest_sha256"
        ],
        "path": "../federated_indexes/2026-07-22-public-open-v38",
    }
    replacements = 0
    for references in result["methodology_evidence_classification"].values():
        for reference in references:
            if reference["release_id"] == OLD_RELEASE_ID:
                reference["release_id"] = NEW_RELEASE_ID
                replacements += 1
    if replacements != 12:
        raise CoverageAuditV32Error(
            f"coverage v31 methodology boundary changed: {replacements}"
        )
    if result.get("public_benchmark") != json.loads(raw).get("public_benchmark"):
        raise CoverageAuditV32Error("public benchmark text changed")
    encoded = _canonical_json(result)
    if any(token in encoded for token in FORBIDDEN_STALE_ACTIVE_TOKENS):
        raise CoverageAuditV32Error("coverage v32 retains a stale active dependency")
    return result


def _legacy_definition(document: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(document)
    supports = result.get("methodology_support_artifacts")
    if (
        not isinstance(supports, list)
        or len(supports) != 2
        or supports[1].get("support_id") != V83_SUPPORT_ID
    ):
        raise CoverageAuditV32Error("coverage v32 support boundary changed")
    result["methodology_support_artifacts"] = supports[:1]
    return result


@contextmanager
def _temporary_legacy_definition(
    document: Mapping[str, Any],
) -> Iterator[Path]:
    descriptor, name = tempfile.mkstemp(
        prefix=".coverage-v32-private-legacy-",
        suffix=".json",
        dir=DEFINITION.parent,
    )
    path = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical_json(_legacy_definition(document)))
            stream.flush()
            os.fsync(stream.fileno())
        yield path
    finally:
        path.unlink(missing_ok=True)


def _timeline_gate() -> dict[str, Any]:
    lane = DEPENDENCIES["timeline_v11"]
    definition = json.loads((ROOT / lane["definition"]).read_bytes())
    expected = definition.get("expected")
    observed = {
        "multi_observation_timelines": expected.get("multi_observation_entities"),
        "observations": expected.get("raw_lifecycle_observations"),
        "repeated_status_multi_observation_timelines": expected.get(
            "repeated_status_multi_observation_entities"
        ),
        "single_observation_timelines": expected.get("single_observation_entities"),
        "single_old_observation_timelines": expected.get(
            "single_old_observation_entities"
        ),
        "source_families": expected.get("source_families"),
        "status_changing_multi_observation_timelines": expected.get(
            "status_changing_multi_observation_entities"
        ),
        "timelines": expected.get("entities_with_lifecycle_observations"),
    }
    if observed != EXPECTED_TIMELINE_GATE:
        raise CoverageAuditV32Error("timeline v11 bounded accounting changed")
    return {
        **observed,
        "definition_sha256": lane["definition_sha256"],
        "manifest_sha256": lane["manifest_sha256"],
        "scope": {
            "current_status_inferred": False,
            "every_facility_coverage_claimed": False,
            "quarterly_2017_2032_parity_claimed": False,
            "row_provenance": False,
            "unique_physical_sites": None,
        },
        "tree_sha256": lane["tree_sha256"],
    }


def _successor_delta(
    audit: Mapping[str, Any], gaps: Mapping[str, Any]
) -> dict[str, Any]:
    previous_audit = json.loads(
        (BASE_BUNDLE / legacy.AUDIT_FILENAME).read_bytes()
    )
    previous_gaps = json.loads(
        (BASE_BUNDLE / legacy.GAP_REGISTRY_FILENAME).read_bytes()
    )
    previous_unrelated = [
        row
        for row in previous_audit["groups"]
        if row["child_release"] != OLD_RELEASE_ID
    ]
    current_unrelated = [
        row for row in audit["groups"] if row["child_release"] != NEW_RELEASE_ID
    ]
    if previous_unrelated != current_unrelated:
        raise CoverageAuditV32Error("unrelated child coverage groups changed")
    previous_groups = {
        predecessor._group_key(row): row
        for row in previous_audit["groups"]
        if row["child_release"] == OLD_RELEASE_ID
    }
    current_groups = {
        predecessor._group_key(row): row
        for row in audit["groups"]
        if row["child_release"] == NEW_RELEASE_ID
    }
    group_deltas = []
    for key in sorted(set(previous_groups) | set(current_groups), key=str):
        old = previous_groups.get(key)
        new = current_groups.get(key)
        normalized_old = (
            {**old, "child_release": NEW_RELEASE_ID} if old is not None else None
        )
        changes = predecessor._numeric_leaf_deltas(normalized_old, new)
        if changes:
            group_deltas.append(
                {
                    "group_key": list(key),
                    "numeric_and_value_deltas": changes,
                }
            )
    previous_ids = {row["gap_id"] for row in previous_gaps["gaps"]}
    current_ids = {row["gap_id"] for row in gaps["gaps"]}
    return {
        "coverage_groups": {
            "current": len(audit["groups"]),
            "delta": len(audit["groups"]) - len(previous_audit["groups"]),
            "previous": len(previous_audit["groups"]),
        },
        "gap_id_changes": {
            "added": len(current_ids - previous_ids),
            "added_ids_sha256": _sha256(
                _canonical_json(sorted(current_ids - previous_ids))
            ),
            "removed": len(previous_ids - current_ids),
            "removed_ids_sha256": _sha256(
                _canonical_json(sorted(previous_ids - current_ids))
            ),
        },
        "gap_summary_deltas": predecessor._numeric_leaf_deltas(
            previous_gaps["summary"], gaps["summary"]
        ),
        "open_seed_group_deltas": group_deltas,
        "open_seed_groups": {
            "current": len(current_groups),
            "delta": len(current_groups) - len(previous_groups),
            "previous": len(previous_groups),
        },
        "totals_deltas": predecessor._numeric_leaf_deltas(
            previous_audit["totals"], audit["totals"]
        ),
        "unrelated_child_groups_byte_equivalent": True,
        "unrelated_child_groups_compared": len(previous_unrelated),
    }


def _implementation_pins() -> dict[str, Any]:
    paths = {
        "cli": CLI_PATH,
        "coverage_audit_v5_carrier": CARRIER_PATH,
        "coverage_audit_v31_predecessor": PREDECESSOR_PATH,
        "module": BUILDER_PATH,
        "root_shim": ROOT_SHIM_PATH,
    }
    result = {}
    for label, path in sorted(paths.items()):
        raw = _regular_bytes(path, f"implementation {label}")
        result[label] = {
            "bytes": len(raw),
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": _sha256(raw),
        }
    result["coverage_audit_v5_carrier"].update(
        {
            "adds_identity_claims": False,
            "adds_lifecycle_claims": False,
            "classification": "non_release_validator_dependency",
            "contract": "federation_v38_governed_manifest_validation_only",
            "release_artifact": False,
        }
    )
    return result


def _acceptance_gates() -> dict[str, Any]:
    result = {}
    for lane in (
        "exact_identity_v14",
        "federation_v38",
        "map_v32",
        "master_v32",
        "open_seed_v97",
        "timeline_v11",
    ):
        dependency = DEPENDENCIES[lane]
        gate = {
            "definition": {
                "path": dependency["definition"],
                "sha256": dependency["definition_sha256"],
            },
            "frozen_modes": {
                "bundle_directory": "0555",
                "bundle_files": "0444",
                "definition": "0444",
            },
            "manifest": {
                "path": f"{dependency['bundle']}/manifest.json",
                "sha256": dependency["manifest_sha256"],
            },
            "timestamp": {
                "field": ".".join(dependency["timestamp_keys"]),
                "value": dependency["timestamp"],
            },
            "tree": {
                "path": dependency["bundle"],
                "sha256": dependency["tree_sha256"],
            },
        }
        if "index_sha256" in dependency:
            gate["index_sha256"] = dependency["index_sha256"]
        result[lane] = gate
    return result


def _report_v32(audit: Mapping[str, Any], gaps: Mapping[str, Any]) -> bytes:
    report_input = deepcopy(audit)
    supports = report_input["inputs"]["methodology_support_artifacts"]
    v83 = next(row for row in supports if row["support_id"] == V83_SUPPORT_ID)
    v83["counts"] = {"jobs": 68, "views": 65}
    text = legacy._report(report_input, gaps).decode("utf-8")
    old = (
        f"- `{V83_SUPPORT_ID}`: **68 jobs / 65 views**, schema v4, last-observed "
        "status semantics; every claim-creation and promotion guardrail remains false."
    )
    new = (
        f"- `{V83_SUPPORT_ID}`: **68 decisions / 65 unique exact four-image sets**; "
        "47 decisions are retained for manual follow-up, representing 44 unique "
        "retained sets, while 21 are rejected. Three exact duplicate groups are "
        "counted once; X052/X041 is approximate-only and is not deduplicated. This "
        "artifact is non-countable and non-promoted."
    )
    if old not in text:
        raise CoverageAuditV32Error("coverage v32 support report anchor changed")
    text = text.replace(old, new, 1)
    anchor = "## SemiAnalysis public benchmark\n"
    insertion = (
        "## Validator carrier boundary\n\n"
        "The byte-pinned `coverage_audit_v5` carrier is a non-release validator "
        "dependency. It accepts federation v38's governed manifest fields without "
        "creating a lifecycle, identity, current-status, capacity, or site claim.\n\n"
        "## Bounded timeline gate evidence\n\n"
        "Accepted timeline v11 contains 583 source-scoped timelines and 607 dated "
        "observations, including 24 multi-observation timelines. These counts are "
        "a bounded acceptance-gate summary, not row provenance, current status, "
        "unique physical sites, persistence, or every-facility coverage.\n\n"
    )
    if anchor not in text:
        raise CoverageAuditV32Error("coverage v32 report anchor changed")
    return text.replace(anchor, insertion + anchor, 1).encode("utf-8")


def _patched_payloads(document: Mapping[str, Any]) -> Mapping[str, bytes]:
    definition_raw = _canonical_json(document)
    with _temporary_legacy_definition(document) as legacy_path:
        built = legacy.build_coverage_audit(legacy_path)
    payloads = dict(built.payloads)
    audit = json.loads(payloads[legacy.AUDIT_FILENAME])
    support = predecessor._validate_v83_support()
    supports = audit["inputs"]["methodology_support_artifacts"]
    supports.append(support)
    supports.sort(key=lambda row: row["support_id"])
    for category in ("computer_vision", "satellite_imagery"):
        record = audit["methodology_evidence_classification"][category]
        support_rows = record["methodology_support_artifacts"]
        support_rows.append(support)
        support_rows.sort(key=lambda row: row["support_id"])
        record["methodology_support_artifact_count"] = 2
        record["methodology_support_ids"] = [
            row["support_id"] for row in support_rows
        ]
        record["methodology_support_promotions"] = 0
    comparison = audit["semianalysis_public_comparison"]
    for row in comparison["comparisons"]:
        if row["claim_id"] == "evidence_methodology":
            for category in ("computer_vision", "satellite_imagery"):
                row["atlas_evidence"][category] = deepcopy(
                    audit["methodology_evidence_classification"][category]
                )
            row["atlas_evidence"]["methodology_scope"] = (
                "hash_bound_source_evidence_plus_non_countable_review_support"
            )
        elif row["claim_id"] == "construction_timeline_pjm":
            row["atlas_evidence"]["bounded_partial_timeline_gate"] = _timeline_gate()
            row["atlas_evidence"]["multi_milestone_construction_timelines"] = (
                "not_claimed_by_bounded_gate"
            )
            row["atlas_status"] = "partial_bounded_timeline_gate"
            row["parity_status"] = "pending"
        elif row["claim_id"] == "temporal_granularity":
            row["atlas_evidence"]["bounded_partial_timeline_gate"] = _timeline_gate()
            row["atlas_status"] = "partial_current_view_plus_bounded_timeline_gate"
            row["parity_status"] = "pending"
    comparison["overall_parity"] = {
        "reason": (
            "Public claims are not a row-level benchmark; Atlas unique physical "
            "sites remain unknown; bounded timeline-v11 gate evidence is not "
            "every-facility coverage; and reviewed methodology support does not "
            "close the material facility, FOIA, timeline, status, or capacity gaps."
        ),
        "status": "pending",
    }
    audit["bounded_partial_timeline_gate"] = _timeline_gate()
    gaps = legacy.legacy._gap_registry(
        audit["audit_id"], audit["generated_at"], audit["groups"], comparison
    )
    gaps["schema_version"] = legacy.SCHEMA_VERSION
    gaps["format"] = legacy.GAP_FORMAT
    audit["successor_delta_from_v31"] = _successor_delta(audit, gaps)
    artifacts = {
        legacy.AUDIT_FILENAME: _canonical_json(audit),
        legacy.COVERAGE_CSV_FILENAME: legacy.legacy._coverage_csv(audit["groups"]),
        legacy.GAP_REGISTRY_FILENAME: _canonical_json(gaps),
        legacy.REPORT_FILENAME: _report_v32(audit, gaps),
    }
    base_manifest = json.loads(payloads[legacy.MANIFEST_FILENAME])
    manifest = {
        **base_manifest,
        "acceptance_gates": _acceptance_gates(),
        "artifacts": {
            name: {"bytes": len(raw), "sha256": _sha256(raw)}
            for name, raw in sorted(artifacts.items())
        },
        "definition": {
            "bytes": len(definition_raw),
            "file": Path(DEFINITION_RELATIVE_PATH).name,
            "sha256": _sha256(definition_raw),
        },
        "implementation": _implementation_pins(),
        "inputs": {
            **base_manifest["inputs"],
            "methodology_support_artifacts": {
                **base_manifest["inputs"]["methodology_support_artifacts"],
                V83_SUPPORT_ID: {
                    "closed_tree_inventory_sha256": (
                        predecessor.V83_REVIEW_TREE_SHA256
                    ),
                    "manifest_sha256": predecessor.V83_REVIEW_MANIFEST_SHA256,
                    "member_sha256": {
                        name: digest
                        for name, (_size, digest) in sorted(
                            predecessor.V83_REVIEW_MEMBER_PINS.items()
                        )
                    },
                    "summary_sha256": predecessor.V83_REVIEW_MEMBER_PINS[
                        "summary.json"
                    ][1],
                },
            },
        },
        "successor_delta_from_v31": audit["successor_delta_from_v31"],
    }
    manifest["counts"] = dict(EXPECTED_COVERAGE_COUNTS)
    if (
        len(audit["groups"]) != EXPECTED_COVERAGE_COUNTS["coverage_groups"]
        or len(gaps["gaps"]) != EXPECTED_COVERAGE_COUNTS["open_gaps"]
        or audit["totals"]["source_scoped_entity_records"]
        != EXPECTED_COVERAGE_COUNTS["source_scoped_entity_records"]
    ):
        raise CoverageAuditV32Error("coverage v32 accounting changed")
    manifest_raw = _canonical_json(manifest)
    result = {
        **artifacts,
        legacy.MANIFEST_FILENAME: manifest_raw,
        legacy.MANIFEST_HASH_FILENAME: (
            f"{_sha256(manifest_raw)}  {legacy.MANIFEST_FILENAME}\n"
        ).encode("ascii"),
    }
    for name, raw in result.items():
        if any(token in raw for token in FORBIDDEN_STALE_ACTIVE_TOKENS):
            raise CoverageAuditV32Error(
                f"coverage v32 retains stale active lineage in {name}"
            )
    return result


def _write_candidate(
    candidate_root: Path,
    definition_raw: bytes,
    payloads: Mapping[str, bytes],
) -> tuple[Path, Path]:
    if candidate_root.exists() or candidate_root.is_symlink():
        raise CoverageAuditV32Error("private candidate root already exists")
    candidate_root.mkdir(mode=0o700)
    definition = candidate_root / Path(DEFINITION_RELATIVE_PATH).name
    bundle = candidate_root / "bundle"
    try:
        with definition.open("xb") as stream:
            stream.write(definition_raw)
            stream.flush()
            os.fsync(stream.fileno())
        bundle.mkdir(mode=0o700)
        for name, raw in sorted(payloads.items()):
            with (bundle / name).open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        definition.chmod(0o444)
        for member in bundle.iterdir():
            member.chmod(0o444)
        bundle.chmod(0o555)
    except BaseException:
        for member in bundle.iterdir() if bundle.is_dir() else ():
            member.chmod(0o600)
            member.unlink()
        if bundle.exists():
            bundle.chmod(0o700)
            bundle.rmdir()
        if definition.exists():
            definition.chmod(0o600)
            definition.unlink()
        candidate_root.rmdir()
        raise
    return definition, bundle


def validate_private_candidate(
    candidate_root: str | Path,
    *,
    rebuild: bool = True,
) -> Mapping[str, Any]:
    root = Path(candidate_root)
    definition = root / Path(DEFINITION_RELATIVE_PATH).name
    bundle = root / "bundle"
    if (
        root.is_symlink()
        or not root.is_dir()
        or definition.is_symlink()
        or not definition.is_file()
        or bundle.is_symlink()
        or not bundle.is_dir()
    ):
        raise CoverageAuditV32Error("private coverage candidate layout changed")
    if stat.S_IMODE(definition.stat().st_mode) != 0o444:
        raise CoverageAuditV32Error("private coverage definition is not frozen")
    _require_frozen_tree(bundle, tree_digest(bundle), "private coverage bundle")
    document_raw = definition.read_bytes()
    document = json.loads(document_raw)
    if document_raw != _canonical_json(document):
        raise CoverageAuditV32Error("private coverage definition is not canonical")
    if (
        document.get("audit_id") != AUDIT_ID
        or document.get("generated_at") != GENERATED_AT
        or document != definition_document(GENERATED_AT)
    ):
        raise CoverageAuditV32Error("private coverage definition changed")
    _require_dependencies_before(
        _parse_utc(GENERATED_AT, "coverage v32 generated_at"),
        allow_private_dependencies=True,
    )
    actual = {member.name: member.read_bytes() for member in bundle.iterdir()}
    if set(actual) != legacy.AUDIT_BUNDLE_FILES:
        raise CoverageAuditV32Error("private coverage bundle file set changed")
    manifest_raw = actual[legacy.MANIFEST_FILENAME]
    if actual[legacy.MANIFEST_HASH_FILENAME] != (
        f"{_sha256(manifest_raw)}  {legacy.MANIFEST_FILENAME}\n"
    ).encode("ascii"):
        raise CoverageAuditV32Error("private coverage sidecar changed")
    manifest = json.loads(manifest_raw)
    audit = json.loads(actual[legacy.AUDIT_FILENAME])
    gaps = json.loads(actual[legacy.GAP_REGISTRY_FILENAME])
    if not (
        manifest.get("audit_id")
        == audit.get("audit_id")
        == gaps.get("audit_id")
        == AUDIT_ID
    ):
        raise CoverageAuditV32Error("private coverage identities changed")
    if (
        manifest.get("counts") != EXPECTED_COVERAGE_COUNTS
        or manifest.get("acceptance_gates") != _acceptance_gates()
        or manifest.get("implementation") != _implementation_pins()
        or audit["scope"]["children_merged"] is not False
        or audit["scope"]["current_status_inferred"] is not False
        or audit["totals"]["unique_physical_sites"] is not None
        or audit["totals"]["source_scoped_entity_records"] != 16_478
        or audit["totals"]["non_review_source_scoped_entity_records"] != 10_348
        or audit["totals"]["review_only_source_scoped_entity_records"] != 6_130
        or len(audit["groups"]) != 1_089
        or len(audit["entity_source_families"]) != 349
        or len(gaps["gaps"]) != 5_048
        or audit["semianalysis_public_comparison"]["overall_parity"]["status"]
        != "pending"
    ):
        raise CoverageAuditV32Error("private coverage semantics changed")
    for name, checkpoint in manifest["artifacts"].items():
        raw = actual[name]
        if checkpoint != {"bytes": len(raw), "sha256": _sha256(raw)}:
            raise CoverageAuditV32Error(f"private coverage artifact changed: {name}")
    if audit["successor_delta_from_v31"] != _successor_delta(audit, gaps):
        raise CoverageAuditV32Error("private coverage successor delta changed")
    if actual[legacy.COVERAGE_CSV_FILENAME] != legacy.legacy._coverage_csv(
        audit["groups"]
    ):
        raise CoverageAuditV32Error("private coverage CSV changed")
    if actual[legacy.REPORT_FILENAME] != _report_v32(audit, gaps):
        raise CoverageAuditV32Error("private coverage report changed")
    if rebuild and actual != _patched_payloads(document):
        raise CoverageAuditV32Error("private coverage replay drifted")
    return manifest


def prepare_private_candidate(
    candidate_root: str | Path,
) -> tuple[Path, Path, Mapping[str, Any]]:
    """Double-build and freeze a private candidate without creating finals."""

    _require_inputs(allow_private_dependencies=True)
    target = _parse_utc(GENERATED_AT, "coverage v32 generated_at")
    _require_dependencies_before(target, allow_private_dependencies=True)
    document = definition_document(GENERATED_AT)
    definition_raw = _canonical_json(document)
    first = dict(_patched_payloads(document))
    second = dict(_patched_payloads(document))
    if first != second:
        raise CoverageAuditV32Error("two private coverage builds differ")
    definition, bundle = _write_candidate(
        Path(candidate_root), definition_raw, first
    )
    manifest = validate_private_candidate(
        definition.parent, rebuild=True
    )
    return definition, bundle, manifest


__all__ = [
    "AUDIT_ID",
    "BUNDLE_RELATIVE_PATH",
    "DEFINITION_RELATIVE_PATH",
    "DEPENDENCIES",
    "EXPECTED_COVERAGE_COUNTS",
    "EXPECTED_TIMELINE_GATE",
    "GENERATED_AT",
    "CoverageAuditV32Error",
    "definition_document",
    "prepare_private_candidate",
    "validate_private_candidate",
]
