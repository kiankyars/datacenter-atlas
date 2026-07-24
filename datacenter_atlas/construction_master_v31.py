"""Strict v31 successor for the role-preserving construction master.

V31 derives its definition from accepted master v30 and replaces only the
open-seed v83 projection with accepted open-seed v86. Federation v35, exact
identity v11, and timeline v8 are frozen acceptance gates, never row
provenance. Every inherited non-inference and rejection guard remains closed.
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


_BASE_SOURCE = Path(__file__).with_name("construction_master_v30.py")
_BASE_SOURCE_SHA256 = (
    "70590b5b6c3b675207dd2caff64d4234c8289823fcef4441e32c88f0bd5f288f"
)


def _successor_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_master_v31 accepted-v30 carrier changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_master_v30 changed; refusing v31 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("v30", "v31", 57),
    ("V30", "V31", 4),
    ("v83", "v86", 19),
    ("V83", "V86", 1),
    ('added_replacement_rows": 263', 'added_replacement_rows": 270', 2),
    ('replacement_rows": 462', 'replacement_rows": 469', 2),
    (
        'replacement_rows_with_any_role": 179',
        'replacement_rows_with_any_role": 186',
        2,
    ),
    ('rows_with_contract_marker": 462', 'rows_with_contract_marker": 469', 2),
    ('tier_a_rows": 582', 'tier_a_rows": 589', 2),
    ('total_rows": 109_374', 'total_rows": 109_381', 2),
    (
        'construction_pipeline_records") != 462',
        'construction_pipeline_records") != 469',
        1,
    ),
    ('added_rows": 263', 'added_rows": 270', 1),
    ("109,374", "109,381", 1),
    ("582 Tier A", "589 Tier A", 1),
    ("462-row", "469-row", 1),
    (
        'replacement_rows_with_operator": 82',
        'replacement_rows_with_operator": 89',
        2,
    ),
    (
        'replacement_rows_with_source_role_tags": 140',
        'replacement_rows_with_source_role_tags": 147',
        1,
    ),
):
    _source = _successor_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())


# All gates are final and independently green. The one-time future timestamp
# keeps every private-stage byte at or before the declared publication instant.
GENERATED_AT = "2026-07-22T00:05:00Z"
MASTER_ID = "2026-07-21-public-open-v31"
REPLACEMENT_ARTIFACT_ID = "epoch-official-open-seed-v86"
REPLACEMENT_RELEASE_ID = "epoch-official-open-seed-v86"
REPLACEMENT_DEFINITION_RELEASE_ID = "2026-07-21-open-seed-v86"

EXPECTED_FIXED = {
    "added_replacement_rows": 270,
    "base_replaced_rows": 199,
    "base_rows": 109_111,
    "inherited_rows": 108_912,
    "replacement_rows": 469,
    "replacement_rows_with_any_role": 186,
    "replacement_rows_with_customers": 2,
    "replacement_rows_with_operator": 89,
    "replacement_rows_with_owner": 53,
    "replacement_rows_with_source_role_tags": 147,
    "replacement_rows_with_tenants": 7,
    "replacement_rows_with_users": 37,
    "rows_with_contract_marker": 469,
    "satellite_recovery_control_plane_bytes": 15_313,
    "satellite_recovery_rows": 0,
    "tier_a_rows": 589,
    "tier_b_rows": 6_298,
    "tier_c_rows": 102_494,
    "total_rows": 109_381,
    "unchanged_replacement_rows": 199,
}

EXPECTED_DIGESTS = {
    "added_source_record_ids_sha256": (
        "8fa67daabafb928828126aed931795be2f05b6b42eb4b67ec8141b74afe1351b"
    ),
    "base_replaced_source_record_ids_sha256": (
        "f9801441dab6df464741d53f7bfc4e9c664b860e66a5de6797eeef8c82ca1950"
    ),
    "inherited_rows_without_roles_sha256": (
        "d6580ceaad528c3a6a489eb568368e7109a0488dfa4425bbe100dc0f1f13ac3f"
    ),
    "replacement_role_projection_sha256": (
        "5f03315283a507acbbc93b6f99784ffa2a5055186345c9202efc48f37bce6184"
    ),
    "replacement_rows_without_roles_sha256": (
        "5bcc3b34d2399bb34357caeb634b86eb11b3c6c1d86b7cec780bb724abd88a5e"
    ),
    "replacement_source_record_ids_sha256": (
        "8308c8d677e0e0c6c3496d2b49ca5b3cd8bb2880e184fc04f8fcec7f6f1362c6"
    ),
    "tier_a_arithmetic_projection_sha256": (
        "f124e8a9ed3c4a0ffd8987d663b2bb2a4bb4b8655efec71f30638e94821cc987"
    ),
}

PREDECESSOR_DEFINITION = {
    "bytes": 5_659,
    "path": "sources/construction-master-2026-07-21-public-open-v30.json",
    "sha256": "981bfd4dcf9bcb6f00f6825c4ac74d62b2bfefeb019fbfa945b774c136683a63",
}
PREDECESSOR_MANIFEST = {
    "bytes": 9_720,
    "path": "construction_master/2026-07-21-public-open-v30/manifest.json",
    "sha256": "8f81ded9c9f351caa0f7a75afce8b4a7abe673c3a078c5bf5fd7bb1f75eabf1f",
}
REPLACEMENT_INPUTS = {
    "artifact_id": "epoch-official-open-seed-v86",
    "data": {
        "bytes": 580_273,
        "path": "releases/2026-07-21-open-seed-v86/construction_pipeline.csv",
        "sha256": "bdb1196b1845bea465f3e1104dd26a7d909e5766f352d2915da6abdf0c798199",
    },
    "definition": {
        "bytes": 102_240,
        "path": "sources/open-seed-2026-07-21-v86.json",
        "sha256": "2a2f0cded9e95efd2ab90cbde1d8ad11306b14f019f42cb14086fb80a63fb25d",
    },
    "evidence": {
        "bytes": 240_378,
        "path": "releases/2026-07-21-open-seed-v86/evidence.csv",
        "sha256": "2cfbae5b2b9c24c91e95b421be44bfe789070dc0917e88f68712083aa7e8a6d7",
    },
    "manifest": {
        "bytes": 15_531,
        "path": "releases/2026-07-21-open-seed-v86/manifest.json",
        "sha256": "5bc24a692e2d4fc793192f03bd23fa921e434661a0675e6612370d354cf11488",
    },
    "publication_contract_version": 4,
    "release_id": "epoch-official-open-seed-v86",
}


ACCEPTED_DEPENDENCY_CLOSURE: dict[str, dict[str, Any]] = {
    "federation_v35": {
        "artifact_id": "2026-07-21-public-open-v35",
        "definition": {
            "bytes": 1_788,
            "path": "sources/federation-2026-07-21-public-open-v35.json",
            "sha256": "7c6f9c3d7892d86974b20ba694c24695c0a0d9a4fd91d830e9824ad2db49903f",
        },
        "manifest": {
            "bytes": 986,
            "path": "federated_indexes/2026-07-21-public-open-v35/manifest.json",
            "sha256": "7396e2854abd73f0209a02f13ab5b31fa79af6250059b92dff484442d61fe388",
        },
        "tree": {
            "path": "federated_indexes/2026-07-21-public-open-v35",
            "sha256": "37bb03f650d2d57823fbc226c471866a4997711ef201440d10dbc4ef6c14f5ba",
        },
    },
    "identity_v11": {
        "artifact_id": "2026-07-21-public-open-v11",
        "definition": {
            "bytes": 1_736,
            "path": "sources/exact-identity-decisions-2026-07-21-public-open-v11.json",
            "sha256": "658ca591e25045245e2709564cd11a3cdd7d338f5be11913aca4ba54a6656a40",
        },
        "manifest": {
            "bytes": 11_441,
            "path": "exact_identity_decisions/2026-07-21-public-open-v11/manifest.json",
            "sha256": "cd54ee06c75272974d2ba43859226b61965d04c7ca6c515d19e44447fe48cbb9",
        },
        "tree": {
            "path": "exact_identity_decisions/2026-07-21-public-open-v11",
            "sha256": "b25b7b568df098a0405452cf3c0608d9d840ace15af120625f7650423d22f6d9",
        },
    },
    "open_seed_v86": {
        "artifact_id": "2026-07-21-open-seed-v86",
        "definition": deepcopy(REPLACEMENT_INPUTS["definition"]),
        "manifest": deepcopy(REPLACEMENT_INPUTS["manifest"]),
        "tree": {
            "path": "releases/2026-07-21-open-seed-v86",
            "sha256": "593fe37f16cc81bd6e2011c9b893251be4041dc54376ffec2f743a510fb4d4de",
        },
    },
    "predecessor_master_v30": {
        "artifact_id": "2026-07-21-public-open-v30",
        "definition": deepcopy(PREDECESSOR_DEFINITION),
        "manifest": deepcopy(PREDECESSOR_MANIFEST),
        "tree": {
            "path": "construction_master/2026-07-21-public-open-v30",
            "sha256": "32d3370e3604434886d305c2a0b129458bfbe1c4e823760f0ccc3a16a3519e30",
        },
    },
    "timeline_v8": {
        "artifact_id": "2026-07-21-public-open-v8",
        "definition": {
            "bytes": 2_881,
            "path": "sources/construction-timeline-2026-07-21-public-open-v8.json",
            "sha256": "9f67b19847aadf326cdd3701c3e4a8aa5309a9b59c58d3d749a6369fdfc3ec97",
        },
        "manifest": {
            "bytes": 3_881,
            "path": "construction_timelines/2026-07-21-public-open-v8/manifest.json",
            "sha256": "4a71dd94b0ab97a8b0e9add0b4688bececec285832de991f7c71a23a7dc8a02d",
        },
        "tree": {
            "path": "construction_timelines/2026-07-21-public-open-v8",
            "sha256": "f3231947d338bd201bc416dd7d78cba51e5193d484a8fb84a0f2bab2b4b65f12",
        },
    },
}

ACCEPTED_DEPENDENCY_TIMESTAMPS = {
    "federation_v35": ("generated_at", "2026-07-21T20:45:00Z"),
    "identity_v11": ("recorded_at", "2026-07-21T23:44:08Z"),
    "open_seed_v86": ("build.recorded_at", "2026-07-21T20:19:16Z"),
    "predecessor_master_v30": ("generated_at", "2026-07-21T18:04:00Z"),
    "timeline_v8": ("generated_at", "2026-07-21T20:42:50Z"),
}

_CHECKPOINT_ONLY_TOKENS = (
    b"2026-07-21-public-open-v35",
    b"2026-07-21-public-open-v11",
    b"2026-07-21-public-open-v8",
    b"2026-07-21-public-open-v34",
    b"2026-07-21-public-open-v10",
    b"2026-07-21-public-open-v7",
    b"2026-07-21-public-open-v33",
    b"2026-07-21-public-open-v9",
    b"2026-07-21-public-open-v6",
    b"2026-07-21-public-open-v30",
    b"2026-07-21-public-open-v29",
)
_REJECTED_TOKENS = tuple(
    guard["token"].encode("ascii") for guard in REJECTED_GUARDS.values()
)


def _v31_error(message: str) -> Exception:
    return ConstructionMasterV31Error(message)


def _parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise _v31_error(f"{label} is absent")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise _v31_error(f"{label} is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise _v31_error(f"{label} must be UTC")
    return parsed


def _nested_value(document: dict[str, Any], dotted_path: str) -> Any:
    value: Any = document
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise _v31_error(
                f"dependency timestamp field is absent: {dotted_path}"
            )
        value = value[part]
    return value


def _validate_frozen_tree(path: Path, label: str) -> None:
    if stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise _v31_error(f"{label} directory is not frozen")
    for member in path.rglob("*"):
        if member.is_symlink():
            raise _v31_error(f"{label} contains a symlink")
        expected_mode = 0o555 if member.is_dir() else 0o444
        if stat.S_IMODE(member.stat().st_mode) != expected_mode:
            raise _v31_error(f"{label} member is not frozen: {member.name}")


def _validate_gate_boundaries() -> None:
    manifests = {
        lane: json.loads(
            _v31_resolve(details["manifest"]["path"], f"{lane} manifest").read_bytes()
        )
        for lane, details in ACCEPTED_DEPENDENCY_CLOSURE.items()
    }
    seed = manifests["open_seed_v86"]
    if (
        seed.get("current_status_inferred") is not False
        or seed.get("geometry_only_representative_point_inferred") is not False
        or seed.get("lifecycle_status_semantics") != "last_observed"
    ):
        raise _v31_error("open-seed v86 non-inference boundary changed")
    federation_scope = manifests["federation_v35"].get("scope", {})
    if (
        federation_scope.get("cross_source_deduplication") is not False
        or federation_scope.get("unique_physical_site_count") is not None
    ):
        raise _v31_error("federation v35 identity boundary changed")
    identity = manifests["identity_v11"]
    identity_scope = identity.get("scope", {})
    identity_counts = identity.get("counts", {})
    if (
        identity_scope.get("automatic_physical_site_merges") is not False
        or identity_scope.get("unique_physical_sites") is not None
        or identity_counts.get("unique_physical_sites") is not None
        or identity_counts.get("physical_site_lower_bound") is not None
        or identity_counts.get("physical_site_upper_bound") is not None
    ):
        raise _v31_error("identity v11 physical-site boundary changed")
    timeline_scope = manifests["timeline_v8"].get("scope", {})
    if (
        timeline_scope.get("current_status_classification") != "unknown"
        or timeline_scope.get("latest_status_semantics") != "last_observed"
        or timeline_scope.get("latest_observation_persistence_assumed") is not False
        or timeline_scope.get("current_construction_claimed") is not False
        or timeline_scope.get("unique_physical_sites") is not None
        or timeline_scope.get("satellite_cv_promoted_to_lifecycle") is not False
    ):
        raise _v31_error("timeline v8 current-status boundary changed")


def validate_dependency_closure_v31() -> None:
    """Require exact, frozen, temporally prior gates outside row provenance."""

    expected_lanes = {
        "federation_v35",
        "identity_v11",
        "open_seed_v86",
        "predecessor_master_v30",
        "timeline_v8",
    }
    if set(ACCEPTED_DEPENDENCY_CLOSURE) != expected_lanes:
        raise _v31_error("accepted v31 dependency closure is not final")
    if set(ACCEPTED_DEPENDENCY_TIMESTAMPS) != expected_lanes:
        raise _v31_error("accepted v31 dependency timestamps are not final")
    master_time = _parse_utc(GENERATED_AT, "v31 generated_at")
    for lane_name in sorted(expected_lanes):
        lane = ACCEPTED_DEPENDENCY_CLOSURE[lane_name]
        if set(lane) != {"artifact_id", "definition", "manifest", "tree"}:
            raise _v31_error(f"{lane_name} dependency schema changed")
        _v31_validate_checkpoint(lane["definition"], f"{lane_name} definition")
        _v31_validate_checkpoint(lane["manifest"], f"{lane_name} manifest")
        definition_path = _v31_resolve(
            lane["definition"]["path"], f"{lane_name} definition"
        )
        if stat.S_IMODE(definition_path.stat().st_mode) != 0o444:
            raise _v31_error(f"{lane_name} definition is not frozen")
        timestamp_field, expected_timestamp = ACCEPTED_DEPENDENCY_TIMESTAMPS[
            lane_name
        ]
        dependency_definition = json.loads(definition_path.read_bytes())
        observed_timestamp = _nested_value(dependency_definition, timestamp_field)
        if observed_timestamp != expected_timestamp:
            raise _v31_error(f"{lane_name} dependency timestamp changed")
        if _parse_utc(observed_timestamp, f"{lane_name} timestamp") >= master_time:
            raise _v31_error(f"{lane_name} is not temporally prior to v31")
        tree = lane["tree"]
        if set(tree) != {"path", "sha256"}:
            raise _v31_error(f"{lane_name} tree checkpoint schema changed")
        directory = _v31_resolve(tree["path"], f"{lane_name} tree")
        if directory.is_symlink() or not directory.is_dir():
            raise _v31_error(f"{lane_name} tree must be a regular directory")
        try:
            observed_tree = _v31_tree_digest(directory)
        except SystemExit as error:
            raise _v31_error(f"{lane_name} tree is unsafe: {error}") from error
        if observed_tree != tree["sha256"]:
            raise _v31_error(f"accepted dependency tree changed: {tree['path']}")
        _validate_frozen_tree(directory, lane_name)
    _validate_rejected_guards()
    _validate_gate_boundaries()


__all__ = [
    "ACCEPTED_DEPENDENCY_CLOSURE",
    "ACCEPTED_DEPENDENCY_TIMESTAMPS",
    "BUNDLE_PATH",
    "ConstructionMasterV31Error",
    "DEFINITION_PATH",
    "EXPECTED_DIGESTS",
    "EXPECTED_FIXED",
    "GENERATED_AT",
    "MASTER_ID",
    "PREPARATION_GENERATED_AT",
    "REJECTED_GUARDS",
    "REPLACEMENT_INPUTS",
    "SCOPE_POLICY",
    "construction_master_v31_definition",
    "construction_master_v31_definition_bytes",
    "discard_construction_master_v31_stage",
    "is_frozen_master_v31",
    "prepare_construction_master_v31",
    "publish_construction_master_v31",
    "validate_construction_master_v31",
    "validate_definition",
    "validate_dependency_closure_v31",
    "write_construction_master_v31",
]
