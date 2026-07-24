"""Strict v30 successor for the role-preserving construction master.

V30 derives its definition from accepted master v29 and replaces only the
open-seed v73 projection with accepted open-seed v83. Federation v34, exact
identity v10, and timeline v7 are frozen acceptance gates, never row
provenance. The v29 rejection guards remain fail-closed.
"""

# ruff: noqa: F821, F822 -- the byte-pinned carrier defines these names by exec.

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import stat
from typing import Any


_BASE_SOURCE = Path(__file__).with_name("construction_master_v29.py")
_BASE_SOURCE_SHA256 = (
    "2c34537338a8f710275a3dd08979fc13c6e63178df794070790f29cf03a71f0a"
)


def _successor_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_master_v30 accepted-v29 carrier changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_master_v29 changed; refusing v30 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("v29", "v30", 52),
    ("V29", "V30", 5),
    ("v73", "v83", 17),
    ("V73", "V83", 1),
    ('added_replacement_rows": 221', 'added_replacement_rows": 263', 2),
    ('replacement_rows": 420', 'replacement_rows": 462', 2),
    (
        'replacement_rows_with_any_role": 149',
        'replacement_rows_with_any_role": 179',
        2,
    ),
    ('rows_with_contract_marker": 420', 'rows_with_contract_marker": 462', 2),
    ('tier_a_rows": 540', 'tier_a_rows": 582', 2),
    ('total_rows": 109_332', 'total_rows": 109_374', 2),
    (
        'construction_pipeline_records") != 420',
        'construction_pipeline_records") != 462',
        1,
    ),
    ('added_rows": 221', 'added_rows": 263', 1),
    ("109,332", "109,374", 1),
    ("540 Tier A", "582 Tier A", 1),
    ("420-row", "462-row", 1),
    ('replacement_rows_with_operator": 62', 'replacement_rows_with_operator": 82', 2),
):
    _source = _successor_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())


# Every accepted dependency has now been independently verified. The future
# timestamp lets all private-stage bytes predate the declared publication time.
GENERATED_AT = "2026-07-21T18:04:00Z"
MASTER_ID = "2026-07-21-public-open-v30"
REPLACEMENT_ARTIFACT_ID = "epoch-official-open-seed-v83"
REPLACEMENT_RELEASE_ID = "epoch-official-open-seed-v83"
REPLACEMENT_DEFINITION_RELEASE_ID = "2026-07-21-open-seed-v83"

EXPECTED_FIXED = {
    "added_replacement_rows": 263,
    "base_replaced_rows": 199,
    "base_rows": 109_111,
    "inherited_rows": 108_912,
    "replacement_rows": 462,
    "replacement_rows_with_any_role": 179,
    "replacement_rows_with_customers": 2,
    "replacement_rows_with_operator": 82,
    "replacement_rows_with_owner": 53,
    "replacement_rows_with_source_role_tags": 140,
    "replacement_rows_with_tenants": 7,
    "replacement_rows_with_users": 37,
    "rows_with_contract_marker": 462,
    "satellite_recovery_control_plane_bytes": 15_313,
    "satellite_recovery_rows": 0,
    "tier_a_rows": 582,
    "tier_b_rows": 6_298,
    "tier_c_rows": 102_494,
    "total_rows": 109_374,
    "unchanged_replacement_rows": 199,
}

EXPECTED_DIGESTS = {
    "added_source_record_ids_sha256": (
        "b91fc2d15d8124eb031e92b6328c9e562b89b20966ee65988dec35a4d6de14bc"
    ),
    "base_replaced_source_record_ids_sha256": (
        "f9801441dab6df464741d53f7bfc4e9c664b860e66a5de6797eeef8c82ca1950"
    ),
    "inherited_rows_without_roles_sha256": (
        "d6580ceaad528c3a6a489eb568368e7109a0488dfa4425bbe100dc0f1f13ac3f"
    ),
    "replacement_role_projection_sha256": (
        "3a8f2f7b1504516d9868436e031ad117d2f2dca8ab8c2eb856023ab8c65d9a79"
    ),
    "replacement_rows_without_roles_sha256": (
        "2f2d00871fc49dedc914050775719453ba3d8f4f419ed79eb1eea168167526f2"
    ),
    "replacement_source_record_ids_sha256": (
        "dd532fc205956cdc0695bef880b7410f0d66b503d27e864ac262401c6c279c4e"
    ),
    "tier_a_arithmetic_projection_sha256": (
        "64ca9b92bf53a0b4eb6886b304b4685f8d791e6b6ac5afbf6d9ddda1cd58b815"
    ),
}

PREDECESSOR_DEFINITION = {
    "bytes": 5_659,
    "path": "sources/construction-master-2026-07-21-public-open-v29.json",
    "sha256": "cd691202ee07e3a4a541c94c8c619da2120e7fa426a7dd468822b77452bcda3d",
}
PREDECESSOR_MANIFEST = {
    "bytes": 9_720,
    "path": "construction_master/2026-07-21-public-open-v29/manifest.json",
    "sha256": "4d1146c4fe8a3c4d8112e7b33ac825febac42a149df2871863e0ed87300a610c",
}
REPLACEMENT_INPUTS = {
    "artifact_id": "epoch-official-open-seed-v83",
    "data": {
        "bytes": 572_434,
        "path": "releases/2026-07-21-open-seed-v83/construction_pipeline.csv",
        "sha256": "f1504f274daf6e41427f4417e540c3d679f712a4e96730b43ec2b0ec12775307",
    },
    "definition": {
        "bytes": 98_808,
        "path": "sources/open-seed-2026-07-21-v83.json",
        "sha256": "84534350a3cf40c7f85479b9d4d42b53604f1858d5325b79dfb0c93de03be4e7",
    },
    "evidence": {
        "bytes": 230_666,
        "path": "releases/2026-07-21-open-seed-v83/evidence.csv",
        "sha256": "897743f94f8e529dcd569e9b5d370523f34ed417cd00bb10c6ce658e918a43a9",
    },
    "manifest": {
        "bytes": 14_812,
        "path": "releases/2026-07-21-open-seed-v83/manifest.json",
        "sha256": "56f33ade743f50e36bd4b2d6f32fa71eaa2b117af79c8580f92d7319c77bd7d5",
    },
    "publication_contract_version": 4,
    "release_id": "epoch-official-open-seed-v83",
}


ACCEPTED_DEPENDENCY_CLOSURE: dict[str, dict[str, Any]] = {
    "federation_v34": {
        "artifact_id": "2026-07-21-public-open-v34",
        "definition": {
            "bytes": 1_788,
            "path": "sources/federation-2026-07-21-public-open-v34.json",
            "sha256": "f01622e680fac69a3fc1ad78151d56cf5cd5b412a28efea91e998fceba367a82",
        },
        "manifest": {
            "bytes": 986,
            "path": "federated_indexes/2026-07-21-public-open-v34/manifest.json",
            "sha256": "31f2d60f266045f01af510f9fc16e541642231697167f3feaf3a70012a376503",
        },
        "tree": {
            "path": "federated_indexes/2026-07-21-public-open-v34",
            "sha256": "a65ae68300e8a6a5a4446e7b264485fcc850d96900de047c960370e57df46bf2",
        },
    },
    "identity_v10": {
        "artifact_id": "2026-07-21-public-open-v10",
        "definition": {
            "bytes": 1_736,
            "path": "sources/exact-identity-decisions-2026-07-21-public-open-v10.json",
            "sha256": "b68c6cd6f84405844b518dcf1aa421f86202c7d2f86c1325905333e5f281d78b",
        },
        "manifest": {
            "bytes": 11_441,
            "path": "exact_identity_decisions/2026-07-21-public-open-v10/manifest.json",
            "sha256": "5806448df1316aa56e4ba82a63961f5dd0b6337ee455de29929c369288a940fe",
        },
        "tree": {
            "path": "exact_identity_decisions/2026-07-21-public-open-v10",
            "sha256": "22363d1472487077386510c51ee373b15b2c1ee9f6343d80267f98ca4cd4a5fa",
        },
    },
    "open_seed_v83": {
        "artifact_id": "2026-07-21-open-seed-v83",
        "definition": deepcopy(REPLACEMENT_INPUTS["definition"]),
        "manifest": deepcopy(REPLACEMENT_INPUTS["manifest"]),
        "tree": {
            "path": "releases/2026-07-21-open-seed-v83",
            "sha256": "1cc39e4079c989d558c33ef63c3109919da533c5feabe9eb02c7cd8347e1d94d",
        },
    },
    "predecessor_master_v29": {
        "artifact_id": "2026-07-21-public-open-v29",
        "definition": deepcopy(PREDECESSOR_DEFINITION),
        "manifest": deepcopy(PREDECESSOR_MANIFEST),
        "tree": {
            "path": "construction_master/2026-07-21-public-open-v29",
            "sha256": "09a76700020e35b1daa95e00cbd6c6bdf90aede9d9f794f5a4c70a607541eff8",
        },
    },
    "timeline_v7": {
        "artifact_id": "2026-07-21-public-open-v7",
        "definition": {
            "bytes": 2_941,
            "path": "sources/construction-timeline-2026-07-21-public-open-v7.json",
            "sha256": "2fa593cbb2f135e1e6feb5baf3e18efa0fd4b9a88a4b264884306a50e43aece1",
        },
        "manifest": {
            "bytes": 3_897,
            "path": "construction_timelines/2026-07-21-public-open-v7/manifest.json",
            "sha256": "a5378eb55f42132193d1e82b97dec5a252e950fa5c4d0c22b278c404ad921265",
        },
        "tree": {
            "path": "construction_timelines/2026-07-21-public-open-v7",
            "sha256": "b7dd059de068366d12da84970ca750fc3a2872f59069b5563ac47c5e05ce568c",
        },
    },
}

ACCEPTED_DEPENDENCY_TIMESTAMPS = {
    "federation_v34": ("generated_at", "2026-07-21T17:47:00Z"),
    "identity_v10": ("recorded_at", "2026-07-21T17:50:27Z"),
    "open_seed_v83": ("build.recorded_at", "2026-07-21T17:38:10Z"),
    "predecessor_master_v29": ("generated_at", "2026-07-21T13:43:00Z"),
    "timeline_v7": ("generated_at", "2026-07-21T17:50:50Z"),
}

_CHECKPOINT_ONLY_TOKENS = (
    b"2026-07-21-public-open-v34",
    b"2026-07-21-public-open-v10",
    b"2026-07-21-public-open-v7",
    b"2026-07-21-public-open-v33",
    b"2026-07-21-public-open-v9",
    b"2026-07-21-public-open-v6",
    b"2026-07-21-public-open-v29",
)
_REJECTED_TOKENS = tuple(
    guard["token"].encode("ascii") for guard in REJECTED_GUARDS.values()
)


def _v30_error(message: str) -> Exception:
    return ConstructionMasterV30Error(message)


def _parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise _v30_error(f"{label} is absent")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise _v30_error(f"{label} is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise _v30_error(f"{label} must be UTC")
    return parsed


def _nested_value(document: dict[str, Any], dotted_path: str) -> Any:
    value: Any = document
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise _v30_error(f"dependency timestamp field is absent: {dotted_path}")
        value = value[part]
    return value


def _validate_frozen_tree(path: Path, label: str) -> None:
    if stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise _v30_error(f"{label} directory is not frozen")
    for member in path.rglob("*"):
        if member.is_symlink():
            raise _v30_error(f"{label} contains a symlink")
        expected_mode = 0o555 if member.is_dir() else 0o444
        if stat.S_IMODE(member.stat().st_mode) != expected_mode:
            raise _v30_error(f"{label} member is not frozen: {member.name}")


def _validate_gate_boundaries() -> None:
    manifests = {
        lane: json.loads(
            _v30_resolve(details["manifest"]["path"], f"{lane} manifest").read_bytes()
        )
        for lane, details in ACCEPTED_DEPENDENCY_CLOSURE.items()
    }
    seed = manifests["open_seed_v83"]
    if (
        seed.get("current_status_inferred") is not False
        or seed.get("lifecycle_status_semantics") != "last_observed"
    ):
        raise _v30_error("open-seed v83 current-status boundary changed")
    federation_scope = manifests["federation_v34"].get("scope", {})
    if (
        federation_scope.get("cross_source_deduplication") is not False
        or federation_scope.get("unique_physical_site_count") is not None
    ):
        raise _v30_error("federation v34 identity boundary changed")
    identity = manifests["identity_v10"]
    identity_scope = identity.get("scope", {})
    identity_counts = identity.get("counts", {})
    if (
        identity_scope.get("automatic_physical_site_merges") is not False
        or identity_scope.get("unique_physical_sites") is not None
        or identity_counts.get("unique_physical_sites") is not None
        or identity_counts.get("physical_site_lower_bound") is not None
        or identity_counts.get("physical_site_upper_bound") is not None
    ):
        raise _v30_error("identity v10 physical-site boundary changed")
    timeline_scope = manifests["timeline_v7"].get("scope", {})
    if (
        timeline_scope.get("current_status_classification") != "unknown"
        or timeline_scope.get("latest_status_semantics") != "last_observed"
        or timeline_scope.get("latest_observation_persistence_assumed") is not False
        or timeline_scope.get("current_construction_claimed") is not False
        or timeline_scope.get("unique_physical_sites") is not None
    ):
        raise _v30_error("timeline v7 current-status boundary changed")


def validate_dependency_closure_v30() -> None:
    """Require exact, frozen, temporally prior gates outside row provenance."""

    expected_lanes = {
        "federation_v34",
        "identity_v10",
        "open_seed_v83",
        "predecessor_master_v29",
        "timeline_v7",
    }
    if set(ACCEPTED_DEPENDENCY_CLOSURE) != expected_lanes:
        raise _v30_error("accepted v30 dependency closure is not final")
    if set(ACCEPTED_DEPENDENCY_TIMESTAMPS) != expected_lanes:
        raise _v30_error("accepted v30 dependency timestamps are not final")
    master_time = _parse_utc(GENERATED_AT, "v30 generated_at")
    for lane_name in sorted(expected_lanes):
        lane = ACCEPTED_DEPENDENCY_CLOSURE[lane_name]
        if set(lane) != {"artifact_id", "definition", "manifest", "tree"}:
            raise _v30_error(f"{lane_name} dependency schema changed")
        _v30_validate_checkpoint(lane["definition"], f"{lane_name} definition")
        _v30_validate_checkpoint(lane["manifest"], f"{lane_name} manifest")
        definition_path = _v30_resolve(
            lane["definition"]["path"], f"{lane_name} definition"
        )
        if stat.S_IMODE(definition_path.stat().st_mode) != 0o444:
            raise _v30_error(f"{lane_name} definition is not frozen")
        timestamp_field, expected_timestamp = ACCEPTED_DEPENDENCY_TIMESTAMPS[
            lane_name
        ]
        dependency_definition = json.loads(definition_path.read_bytes())
        observed_timestamp = _nested_value(dependency_definition, timestamp_field)
        if observed_timestamp != expected_timestamp:
            raise _v30_error(f"{lane_name} dependency timestamp changed")
        if _parse_utc(observed_timestamp, f"{lane_name} timestamp") >= master_time:
            raise _v30_error(f"{lane_name} is not temporally prior to v30")
        tree = lane["tree"]
        if set(tree) != {"path", "sha256"}:
            raise _v30_error(f"{lane_name} tree checkpoint schema changed")
        directory = _v30_resolve(tree["path"], f"{lane_name} tree")
        if directory.is_symlink() or not directory.is_dir():
            raise _v30_error(f"{lane_name} tree must be a regular directory")
        try:
            observed_tree = _v30_tree_digest(directory)
        except SystemExit as error:
            raise _v30_error(f"{lane_name} tree is unsafe: {error}") from error
        if observed_tree != tree["sha256"]:
            raise _v30_error(f"accepted dependency tree changed: {tree['path']}")
        _validate_frozen_tree(directory, lane_name)
    _validate_rejected_guards()
    _validate_gate_boundaries()


def construction_master_v30_definition() -> dict[str, Any]:
    """Derive v30 only from the pinned v29 definition and v83 projection."""

    validate_dependency_closure_v30()
    predecessor_path = _v30_resolve(
        PREDECESSOR_DEFINITION["path"], "predecessor definition"
    )
    predecessor_raw = predecessor_path.read_bytes()
    if _checkpoint(predecessor_path) != {
        "bytes": PREDECESSOR_DEFINITION["bytes"],
        "sha256": PREDECESSOR_DEFINITION["sha256"],
    }:
        raise _v30_error("accepted v29 definition changed")
    try:
        document = json.loads(predecessor_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _v30_error("accepted v29 definition is invalid JSON") from error
    if predecessor_raw != _canonical_json(document):
        raise _v30_error("accepted v29 definition is not canonical")
    document["expected"] = {**EXPECTED_FIXED, **EXPECTED_DIGESTS}
    document["generated_at"] = GENERATED_AT
    document["inputs"]["replacement_release"] = deepcopy(REPLACEMENT_INPUTS)
    document["master_id"] = MASTER_ID
    document["scope"] = deepcopy(SCOPE_POLICY)
    raw = _canonical_json(document)
    for token in (*_CHECKPOINT_ONLY_TOKENS, *_REJECTED_TOKENS):
        if token in raw:
            raise _v30_error("checkpoint-only or rejected lineage entered definition")
    return document


def construction_master_v30_definition_bytes() -> bytes:
    return _canonical_json(construction_master_v30_definition())


__all__ = [
    "ACCEPTED_DEPENDENCY_CLOSURE",
    "ACCEPTED_DEPENDENCY_TIMESTAMPS",
    "BUNDLE_PATH",
    "ConstructionMasterV30Error",
    "DEFINITION_PATH",
    "EXPECTED_DIGESTS",
    "EXPECTED_FIXED",
    "GENERATED_AT",
    "MASTER_ID",
    "PREPARATION_GENERATED_AT",
    "REJECTED_GUARDS",
    "REPLACEMENT_INPUTS",
    "SCOPE_POLICY",
    "construction_master_v30_definition",
    "construction_master_v30_definition_bytes",
    "discard_construction_master_v30_stage",
    "is_frozen_master_v30",
    "prepare_construction_master_v30",
    "publish_construction_master_v30",
    "validate_construction_master_v30",
    "validate_definition",
    "validate_dependency_closure_v30",
    "write_construction_master_v30",
]
