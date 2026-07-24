"""Strict private/prepublication v32 construction-master successor.

V32 replaces only the accepted v31 open-seed projection with open-seed v97.
Federation v38, exact identity v14, and timeline v11 are acceptance gates, not
row provenance.  The four bare source-record IDs shared by v97 and inherited
``global-open-v3`` rows remain separate observations because master identity is
the globally unique ``row_id`` (and, secondarily, source artifact plus record).

Exact identity v14 is now live at its frozen public paths.  The prospective
compatibility switch remains fail-closed for historical audit exercises, but
all current preparation, validation, and publication paths use the live public
default closure.
"""

# ruff: noqa: F821, F822 -- the byte-pinned carrier defines these names by exec.

from __future__ import annotations

import hashlib
import json
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_BASE_SOURCE = Path(__file__).with_name("construction_master_v31.py")
_BASE_SOURCE_SHA256 = "70e160500940712b8406f40907c6bf3d4b0ae8ad5a947d79bc4f63835be5a523"


def _successor_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_master_v32 accepted-v31 carrier changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_master_v31 changed; refusing v32 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("v31", "v32", 47),
    ("V31", "V32", 4),
    ("v86", "v97", 18),
    ("V86", "V97", 1),
    ('added_replacement_rows": 270', 'added_replacement_rows": 332', 2),
    ('replacement_rows": 469', 'replacement_rows": 531', 2),
    (
        'replacement_rows_with_any_role": 186',
        'replacement_rows_with_any_role": 205',
        2,
    ),
    ('rows_with_contract_marker": 469', 'rows_with_contract_marker": 531', 2),
    ('tier_a_rows": 589', 'tier_a_rows": 651', 2),
    ('total_rows": 109_381', 'total_rows": 109_443', 2),
    (
        'construction_pipeline_records") != 469',
        'construction_pipeline_records") != 531',
        1,
    ),
    ('added_rows": 270', 'added_rows": 332', 1),
    ("109,381", "109,443", 1),
    ("589 Tier A", "651 Tier A", 1),
    ("469-row", "531-row", 1),
    (
        'replacement_rows_with_operator": 89',
        'replacement_rows_with_operator": 96',
        2,
    ),
    (
        'replacement_rows_with_source_role_tags": 147',
        'replacement_rows_with_source_role_tags": 166',
        2,
    ),
    ('replacement_rows_with_owner": 53', 'replacement_rows_with_owner": 54', 1),
    ('replacement_rows_with_tenants": 7', 'replacement_rows_with_tenants": 10', 1),
    (
        'replacement_rows_with_customers": 2',
        'replacement_rows_with_customers": 3',
        1,
    ),
):
    _source = _successor_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())  # noqa: S102


GENERATED_AT = "2026-07-24T23:30:00Z"
MASTER_ID = "2026-07-22-public-open-v32"
REPLACEMENT_ARTIFACT_ID = "epoch-official-open-seed-v97"
REPLACEMENT_RELEASE_ID = "epoch-official-open-seed-v97"
REPLACEMENT_DEFINITION_RELEASE_ID = "2026-07-22-open-seed-v97"
DEFINITION_RELATIVE_PATH = "sources/construction-master-2026-07-22-public-open-v32.json"
BUNDLE_RELATIVE_PATH = "construction_master/2026-07-22-public-open-v32"
DEFINITION_PATH = ROOT / DEFINITION_RELATIVE_PATH
BUNDLE_PATH = ROOT / BUNDLE_RELATIVE_PATH

EXPECTED_FIXED = {
    "added_replacement_rows": 332,
    "base_replaced_rows": 199,
    "base_rows": 109_111,
    "inherited_rows": 108_912,
    "replacement_rows": 531,
    "replacement_rows_with_any_role": 205,
    "replacement_rows_with_customers": 3,
    "replacement_rows_with_operator": 96,
    "replacement_rows_with_owner": 54,
    "replacement_rows_with_source_role_tags": 166,
    "replacement_rows_with_tenants": 10,
    "replacement_rows_with_users": 37,
    "rows_with_contract_marker": 531,
    "satellite_recovery_control_plane_bytes": 15_313,
    "satellite_recovery_rows": 0,
    "tier_a_rows": 651,
    "tier_b_rows": 6_298,
    "tier_c_rows": 102_494,
    "total_rows": 109_443,
    "unchanged_replacement_rows": 199,
}

EXPECTED_DIGESTS = {
    "added_source_record_ids_sha256": (
        "b8d054dd8ab9235bdde74788244232ad9a046cfea10556700c08df2302e26007"
    ),
    "base_replaced_source_record_ids_sha256": (
        "f9801441dab6df464741d53f7bfc4e9c664b860e66a5de6797eeef8c82ca1950"
    ),
    "inherited_rows_without_roles_sha256": (
        "d6580ceaad528c3a6a489eb568368e7109a0488dfa4425bbe100dc0f1f13ac3f"
    ),
    "replacement_role_projection_sha256": (
        "9c1fb6774081f5f19cf85ace95836a325d29bc08671dd63f7ca21a82b7a1cb0e"
    ),
    "replacement_rows_without_roles_sha256": (
        "d578e0b658330dc487023d5752059e80d95b32236369e620c875cb6865bf4dbf"
    ),
    "replacement_source_record_ids_sha256": (
        "c42890130b64bc231ac204daed5883e03fb8234cdc532069e6597e71b09fa6fd"
    ),
    "tier_a_arithmetic_projection_sha256": (
        "ee164450914a44c4a094fd6a9c9c4be099199e2508aadab0883dce6c71b919f9"
    ),
}

PREDECESSOR_DEFINITION = {
    "bytes": 5_660,
    "path": "sources/construction-master-2026-07-21-public-open-v31.json",
    "sha256": "a1b4761820aa6adb3406d5ff3ad6bc52898309fed72fe4f857aca01197597c25",
}
PREDECESSOR_MANIFEST = {
    "bytes": 9_721,
    "path": "construction_master/2026-07-21-public-open-v31/manifest.json",
    "sha256": "8d2cb42034ca040c3341582ee0ac125013f208a6712c211fb334943763412c7e",
}
REPLACEMENT_INPUTS = {
    "artifact_id": REPLACEMENT_ARTIFACT_ID,
    "data": {
        "bytes": 635_843,
        "path": "releases/2026-07-22-open-seed-v97/construction_pipeline.csv",
        "sha256": "b39aed7653872bff0d0841ece2968f69e9d1d76bd07a242d103ab50e9b78c12f",
    },
    "definition": {
        "bytes": 120_979,
        "path": "sources/open-seed-2026-07-22-v97.json",
        "sha256": "32f22ccc74ec6ec33dc9bc7377a83bfee83f88dff3555555fc89cb43a27d673f",
    },
    "evidence": {
        "bytes": 271_797,
        "path": "releases/2026-07-22-open-seed-v97/evidence.csv",
        "sha256": "c73263c3b27f984c8bebf76f9db31b63a22059a3774dbec9ed944ceee344f2d1",
    },
    "manifest": {
        "bytes": 20_402,
        "path": "releases/2026-07-22-open-seed-v97/manifest.json",
        "sha256": "0a6f41f4239944df27f2ce70e81a089b91cec401f154bbae28412b27a4d00fdd",
    },
    "publication_contract_version": 4,
    "release_id": REPLACEMENT_RELEASE_ID,
}

ACCEPTED_DEPENDENCY_CLOSURE: dict[str, dict[str, Any]] = {
    "federation_v38": {
        "artifact_id": "2026-07-22-public-open-v38",
        "definition": {
            "bytes": 1_784,
            "path": "sources/federation-2026-07-22-public-open-v38.json",
            "sha256": "fc0f6985c403b1562f439c2abd31b244a6784f5ed7030edd349c6a8ba92a09fb",
        },
        "manifest": {
            "bytes": 986,
            "path": "federated_indexes/2026-07-22-public-open-v38/manifest.json",
            "sha256": "4c8f79ca5a17d9dfb1c02a1f7ee01da62ece19d2c265854b82cb701c8012b453",
        },
        "tree": {
            "path": "federated_indexes/2026-07-22-public-open-v38",
            "sha256": "84b7329e7f62da8ebf3e868d8026d03b49b36a8d5290bb0004c34d4518f9a5d5",
        },
    },
    "identity_v14": {
        "artifact_id": "2026-07-22-public-open-v14",
        "definition": {
            "bytes": 1_732,
            "path": (
                "sources/exact-identity-decisions-2026-07-22-public-open-v14.json"
            ),
            "sha256": "2efe24eaff33a91d210f3139a66b9538fb1768e9d8695e1f9ddebddd6d1475f1",
        },
        "manifest": {
            "bytes": 11_440,
            "path": (
                "exact_identity_decisions/2026-07-22-public-open-v14/manifest.json"
            ),
            "sha256": "268b064077e82ab5b3d90459234770743838b22cc90a72021b96f788d4947ba4",
        },
        "tree": {
            "path": "exact_identity_decisions/2026-07-22-public-open-v14",
            "sha256": "1a4c733425316103ea50c24e83617a38bb339d927f45f13c470937356d20b0ac",
        },
    },
    "open_seed_v97": {
        "artifact_id": "2026-07-22-open-seed-v97",
        "definition": deepcopy(REPLACEMENT_INPUTS["definition"]),
        "manifest": deepcopy(REPLACEMENT_INPUTS["manifest"]),
        "tree": {
            "path": "releases/2026-07-22-open-seed-v97",
            "sha256": "5136ad66f56b7474053ff3b8cbbffca1f3df3479d8a30745a1502917fa0e7954",
        },
    },
    "predecessor_master_v31": {
        "artifact_id": "2026-07-21-public-open-v31",
        "definition": deepcopy(PREDECESSOR_DEFINITION),
        "manifest": deepcopy(PREDECESSOR_MANIFEST),
        "tree": {
            "path": "construction_master/2026-07-21-public-open-v31",
            "sha256": "90790b8d72592bd8c1a9971576cc9bb27a4cbc334b16b0b13246e1ed2639b9da",
        },
    },
    "timeline_v11": {
        "artifact_id": "2026-07-22-public-open-v11",
        "definition": {
            "bytes": 8_245,
            "path": "sources/construction-timeline-2026-07-22-public-open-v11.json",
            "sha256": "86ad1866104028cf17b4cbc0a72c39f22b83a357ee03727ceb1daedfa2be66d0",
        },
        "manifest": {
            "bytes": 9_484,
            "path": "construction_timelines/2026-07-22-public-open-v11/manifest.json",
            "sha256": "d4c6708aa08241e8319aace1e14b21d9f189e996c5dcfe8a95ff77a0d8b746e1",
        },
        "tree": {
            "path": "construction_timelines/2026-07-22-public-open-v11",
            "sha256": "2930cad0dc7c9733b5b522cba1a2a9403d699ee363c86feaf890c923c6d19b87",
        },
    },
}

ACCEPTED_DEPENDENCY_TIMESTAMPS = {
    "federation_v38": ("generated_at", "2026-07-24T20:45:00Z"),
    "identity_v14": ("recorded_at", "2026-07-24T22:30:00Z"),
    "open_seed_v97": ("build.recorded_at", "2026-07-22T06:06:40Z"),
    "predecessor_master_v31": ("generated_at", "2026-07-22T00:05:00Z"),
    "timeline_v11": ("generated_at", "2026-07-24T20:30:00Z"),
}

_CHECKPOINT_ONLY_TOKENS = (
    b"2026-07-22-public-open-v38",
    b"2026-07-22-public-open-v14",
    b"2026-07-22-public-open-v11",
    b"2026-07-21-public-open-v35",
    b"2026-07-21-public-open-v11",
    b"2026-07-21-public-open-v8",
    b"2026-07-21-public-open-v31",
    b"2026-07-21-public-open-v30",
)
_REJECTED_TOKENS = tuple(
    guard["token"].encode("ascii") for guard in REJECTED_GUARDS.values()
)

EXPECTED_BARE_SOURCE_RECORD_COLLISIONS = frozenset(
    {
        "213cbb8d-9a75-569d-8254-c92397331870",
        "867d91cb-7a17-59db-a92e-4a50a499f54f",
        "b3656b35-f3ad-5119-8918-ac5237bf2a7f",
        "d84e71c3-cd2c-5443-912b-aadcec17ee71",
    }
)

_PROSPECTIVE_IDENTITY_ALLOWED = False
_carrier_definition = globals()["construction_master_v32_definition"]
_carrier_definition_bytes = globals()["construction_master_v32_definition_bytes"]
_carrier_prepare = globals()["prepare_construction_master_v32"]
_carrier_validate = globals()["validate_construction_master_v32"]


def _v32_error(message: str) -> Exception:
    return ConstructionMasterV32Error(message)


def _parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise _v32_error(f"{label} is absent")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise _v32_error(f"{label} is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise _v32_error(f"{label} must be UTC")
    return parsed


def _nested_value(document: dict[str, Any], dotted_path: str) -> Any:
    value: Any = document
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise _v32_error(f"dependency timestamp field is absent: {dotted_path}")
        value = value[part]
    return value


def _validate_frozen_tree(path: Path, label: str) -> None:
    if stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise _v32_error(f"{label} directory is not frozen")
    for member in path.rglob("*"):
        if member.is_symlink():
            raise _v32_error(f"{label} contains a symlink")
        expected_mode = 0o555 if member.is_dir() else 0o444
        if stat.S_IMODE(member.stat().st_mode) != expected_mode:
            raise _v32_error(f"{label} member is not frozen: {member.name}")


def _identity_final_state() -> tuple[bool, bool, bool]:
    lane = ACCEPTED_DEPENDENCY_CLOSURE["identity_v14"]
    return (
        (ROOT / lane["definition"]["path"]).exists(),
        (ROOT / lane["manifest"]["path"]).exists(),
        (ROOT / lane["tree"]["path"]).exists(),
    )


def _validate_gate_boundaries_v32(*, identity_is_live: bool) -> None:
    live_lanes = ("open_seed_v97", "federation_v38", "timeline_v11")
    manifests = {
        lane: json.loads(
            _v32_resolve(
                ACCEPTED_DEPENDENCY_CLOSURE[lane]["manifest"]["path"],
                f"{lane} manifest",
            ).read_bytes()
        )
        for lane in live_lanes
    }
    seed = manifests["open_seed_v97"]
    stale = seed.get("stale_status_suppression", {})
    if (
        seed.get("current_status_inferred") is not False
        or seed.get("geometry_only_representative_point_inferred") is not False
        or seed.get("lifecycle_status_semantics") != "last_observed"
        or stale.get("current_status_classification") != "unknown"
        or stale.get("current_construction_claim") is not False
        or stale.get("construction_pipeline_excluded") is not True
        or stale.get("stable_keys")
        != [
            "curated:cmc-creative-space-hanoi:data-center-tower",
            ("curated:edgnex-second-jakarta-ai-data-center:phase-1-early-construction"),
            "curated:oran-ai-data-center-campus:current-build",
        ]
    ):
        raise _v32_error("open-seed v97 non-inference or stale-status boundary changed")
    federation_scope = manifests["federation_v38"].get("scope", {})
    if (
        federation_scope.get("cross_source_deduplication") is not False
        or federation_scope.get("unique_physical_site_count") is not None
    ):
        raise _v32_error("federation v38 identity boundary changed")
    timeline_scope = manifests["timeline_v11"].get("scope", {})
    if (
        timeline_scope.get("current_status_classification") != "unknown"
        or timeline_scope.get("latest_status_semantics") != "last_observed"
        or timeline_scope.get("latest_observation_persistence_assumed") is not False
        or timeline_scope.get("current_construction_claimed") is not False
        or timeline_scope.get("unique_physical_sites") is not None
        or timeline_scope.get("satellite_cv_promoted_to_lifecycle") is not False
    ):
        raise _v32_error("timeline v11 current-status boundary changed")
    if identity_is_live:
        identity = json.loads(
            _v32_resolve(
                ACCEPTED_DEPENDENCY_CLOSURE["identity_v14"]["manifest"]["path"],
                "identity_v14 manifest",
            ).read_bytes()
        )
        identity_scope = identity.get("scope", {})
        identity_counts = identity.get("counts", {})
        if (
            identity_scope.get("automatic_physical_site_merges") is not False
            or identity_scope.get("unique_physical_sites") is not None
            or identity_counts.get("unique_physical_sites") is not None
            or identity_counts.get("physical_site_lower_bound") is not None
            or identity_counts.get("physical_site_upper_bound") is not None
            or identity_counts.get("source_scoped_entity_records") != 16_478
        ):
            raise _v32_error("identity v14 physical-site boundary changed")


def validate_dependency_closure_v32(
    *, allow_prospective_identity: bool | None = None
) -> None:
    """Validate exact gates, optionally accepting only an absent audited v14 final."""

    if allow_prospective_identity is None:
        allow_prospective_identity = _PROSPECTIVE_IDENTITY_ALLOWED
    expected_lanes = {
        "federation_v38",
        "identity_v14",
        "open_seed_v97",
        "predecessor_master_v31",
        "timeline_v11",
    }
    if set(ACCEPTED_DEPENDENCY_CLOSURE) != expected_lanes:
        raise _v32_error("accepted v32 dependency closure is not final")
    if set(ACCEPTED_DEPENDENCY_TIMESTAMPS) != expected_lanes:
        raise _v32_error("accepted v32 dependency timestamps are not final")
    identity_state = _identity_final_state()
    if any(identity_state) and not all(identity_state):
        raise _v32_error("identity v14 final paths are only partially present")
    identity_is_live = all(identity_state)
    if not identity_is_live and not allow_prospective_identity:
        raise _v32_error("accepted identity v14 final is absent")
    master_time = _parse_utc(GENERATED_AT, "v32 generated_at")
    for lane_name in sorted(expected_lanes):
        lane = ACCEPTED_DEPENDENCY_CLOSURE[lane_name]
        if set(lane) != {"artifact_id", "definition", "manifest", "tree"}:
            raise _v32_error(f"{lane_name} dependency schema changed")
        timestamp_field, expected_timestamp = ACCEPTED_DEPENDENCY_TIMESTAMPS[lane_name]
        if _parse_utc(expected_timestamp, f"{lane_name} timestamp") >= master_time:
            raise _v32_error(f"{lane_name} is not temporally prior to v32")
        if lane_name == "identity_v14" and not identity_is_live:
            continue
        _v32_validate_checkpoint(lane["definition"], f"{lane_name} definition")
        _v32_validate_checkpoint(lane["manifest"], f"{lane_name} manifest")
        definition_path = _v32_resolve(
            lane["definition"]["path"], f"{lane_name} definition"
        )
        if stat.S_IMODE(definition_path.stat().st_mode) != 0o444:
            raise _v32_error(f"{lane_name} definition is not frozen")
        dependency_definition = json.loads(definition_path.read_bytes())
        observed_timestamp = _nested_value(dependency_definition, timestamp_field)
        if observed_timestamp != expected_timestamp:
            raise _v32_error(f"{lane_name} dependency timestamp changed")
        tree = lane["tree"]
        if set(tree) != {"path", "sha256"}:
            raise _v32_error(f"{lane_name} tree checkpoint schema changed")
        directory = _v32_resolve(tree["path"], f"{lane_name} tree")
        if directory.is_symlink() or not directory.is_dir():
            raise _v32_error(f"{lane_name} tree must be a regular directory")
        try:
            observed_tree = _v32_tree_digest(directory)
        except SystemExit as error:
            raise _v32_error(f"{lane_name} tree is unsafe: {error}") from error
        if observed_tree != tree["sha256"]:
            raise _v32_error(f"accepted dependency tree changed: {tree['path']}")
        _validate_frozen_tree(directory, lane_name)
    _validate_rejected_guards()
    _validate_gate_boundaries_v32(identity_is_live=identity_is_live)


@contextmanager
def _prospective_identity_mode(enabled: bool) -> Iterator[None]:
    global _PROSPECTIVE_IDENTITY_ALLOWED
    previous = _PROSPECTIVE_IDENTITY_ALLOWED
    _PROSPECTIVE_IDENTITY_ALLOWED = enabled
    try:
        yield
    finally:
        _PROSPECTIVE_IDENTITY_ALLOWED = previous


def construction_master_v32_definition(
    *, allow_prospective_identity: bool | None = None
) -> dict[str, Any]:
    enabled = (
        _PROSPECTIVE_IDENTITY_ALLOWED
        if allow_prospective_identity is None
        else allow_prospective_identity
    )
    with _prospective_identity_mode(enabled):
        return _carrier_definition()


def construction_master_v32_definition_bytes(
    *, allow_prospective_identity: bool | None = None
) -> bytes:
    enabled = (
        _PROSPECTIVE_IDENTITY_ALLOWED
        if allow_prospective_identity is None
        else allow_prospective_identity
    )
    with _prospective_identity_mode(enabled):
        return _carrier_definition_bytes()


def prepare_construction_master_v32(
    *, allow_prospective_identity: bool = False
) -> tuple[Path, Path, Path]:
    """Build a private candidate; prospective v14 is never accepted for publish."""

    with _prospective_identity_mode(allow_prospective_identity):
        return _carrier_prepare()


def validate_construction_master_v32(
    directory: str | Path,
    *,
    definition_path: str | Path,
    reproduce: bool = True,
    allow_prospective_identity: bool | None = None,
) -> dict[str, Any]:
    """Validate a private candidate without weakening the public default."""

    enabled = (
        _PROSPECTIVE_IDENTITY_ALLOWED
        if allow_prospective_identity is None
        else allow_prospective_identity
    )
    with _prospective_identity_mode(enabled):
        return _carrier_validate(
            directory, definition_path=definition_path, reproduce=reproduce
        )


__all__ = [
    "ACCEPTED_DEPENDENCY_CLOSURE",
    "ACCEPTED_DEPENDENCY_TIMESTAMPS",
    "BUNDLE_PATH",
    "DEFINITION_PATH",
    "EXPECTED_BARE_SOURCE_RECORD_COLLISIONS",
    "EXPECTED_DIGESTS",
    "EXPECTED_FIXED",
    "GENERATED_AT",
    "MASTER_ID",
    "PREPARATION_GENERATED_AT",
    "REJECTED_GUARDS",
    "REPLACEMENT_INPUTS",
    "SCOPE_POLICY",
    "ConstructionMasterV32Error",
    "construction_master_v32_definition",
    "construction_master_v32_definition_bytes",
    "discard_construction_master_v32_stage",
    "is_frozen_master_v32",
    "prepare_construction_master_v32",
    "publish_construction_master_v32",
    "validate_construction_master_v32",
    "validate_definition",
    "validate_dependency_closure_v32",
    "write_construction_master_v32",
]
