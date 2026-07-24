"""Frozen v29 successor carrier for the role-preserving construction master.

V29 derives its definition from accepted master v28 and replaces only the
open-seed v71 projection with accepted open-seed v73. Federation v33, exact
identity v9, and timeline v6 are acceptance gates, never row provenance.
Rejected federation v32 and timeline v4 remain rejection guards only.
"""

# ruff: noqa: F821, F822 -- the byte-pinned carrier defines these names by exec.

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any


_BASE_SOURCE = Path(__file__).with_name("construction_master_v12.py")
_BASE_SOURCE_SHA256 = (
    "a08a75baad8a1a276f5347bd31f50a4bc64b697df2fbbd4c86e16cea30444c25"
)


def _carrier_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_master_v29 accepted-v28 carrier changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_master_v12 changed; refusing v29 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("construction_master_v12", "construction_master_v29", 13),
    ("ConstructionMasterV12Error", "ConstructionMasterV29Error", 3),
    ("is_frozen_master_v12", "is_frozen_master_v29", 2),
    ("v28", "v29", 186),
    ("V28", "V29", 15),
    ("v71", "v73", 13),
    ("V71", "V73", 1),
    ('added_replacement_rows": 217', 'added_replacement_rows": 221', 1),
    ('replacement_rows": 416', 'replacement_rows": 420', 1),
    (
        'replacement_rows_with_any_role": 145',
        'replacement_rows_with_any_role": 149',
        1,
    ),
    ('rows_with_contract_marker": 416', 'rows_with_contract_marker": 420', 1),
    ('tier_a_rows": 536', 'tier_a_rows": 540', 1),
    ('total_rows": 109_328', 'total_rows": 109_332', 1),
    (
        'construction_pipeline_records") != 416',
        'construction_pipeline_records") != 420',
        1,
    ),
    ('added_rows": 217', 'added_rows": 221', 1),
    ("109,328", "109,332", 1),
    ("536 Tier A", "540 Tier A", 1),
    ("416-row", "420-row", 1),
    ('"replacement_rows_with_operator": 59', '"replacement_rows_with_operator": 62', 1),
):
    _source = _carrier_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())


GENERATED_AT = "2026-07-21T13:43:00Z"
MASTER_ID = "2026-07-21-public-open-v29"
REPLACEMENT_ARTIFACT_ID = "epoch-official-open-seed-v73"
REPLACEMENT_RELEASE_ID = "epoch-official-open-seed-v73"
REPLACEMENT_DEFINITION_RELEASE_ID = "2026-07-21-open-seed-v73"

EXPECTED_FIXED = {
    "added_replacement_rows": 221,
    "base_replaced_rows": 199,
    "base_rows": 109_111,
    "inherited_rows": 108_912,
    "replacement_rows": 420,
    "replacement_rows_with_any_role": 149,
    "replacement_rows_with_customers": 2,
    "replacement_rows_with_operator": 62,
    "replacement_rows_with_owner": 48,
    "replacement_rows_with_source_role_tags": 110,
    "replacement_rows_with_tenants": 7,
    "replacement_rows_with_users": 36,
    "rows_with_contract_marker": 420,
    "satellite_recovery_control_plane_bytes": 15_313,
    "satellite_recovery_rows": 0,
    "tier_a_rows": 540,
    "tier_b_rows": 6_298,
    "tier_c_rows": 102_494,
    "total_rows": 109_332,
    "unchanged_replacement_rows": 199,
}

EXPECTED_DIGESTS = {
    "added_source_record_ids_sha256": (
        "3480d43754e33f76500fdf09bff59a864c641be0d15f1dcfb75480a9c9efe619"
    ),
    "base_replaced_source_record_ids_sha256": (
        "f9801441dab6df464741d53f7bfc4e9c664b860e66a5de6797eeef8c82ca1950"
    ),
    "inherited_rows_without_roles_sha256": (
        "d6580ceaad528c3a6a489eb568368e7109a0488dfa4425bbe100dc0f1f13ac3f"
    ),
    "replacement_role_projection_sha256": (
        "a084c49e69538b5a1424fbcca5a916c70bea24fdaa660b4e715b53f04d398c8e"
    ),
    "replacement_rows_without_roles_sha256": (
        "44c9d5ebd7f3427e4fc735a75c1f0089c204ecd888437f90a0ba9a048190ee12"
    ),
    "replacement_source_record_ids_sha256": (
        "60011ff904e5a430b963d033cf2ddc17aa014af4fb9ac499db8cf33d95d862b1"
    ),
    "tier_a_arithmetic_projection_sha256": (
        "223c78144ce86d035623a46547e7bcbe6f9b3e1ca36496bd07065efa0852be77"
    ),
}

PREDECESSOR_DEFINITION = {
    "bytes": 5_659,
    "path": "sources/construction-master-2026-07-21-public-open-v28.json",
    "sha256": "e93b0f3e7750c90a03cca5afe349ea04ae9790b607fa0b09de9ce394a1ad4533",
}
PREDECESSOR_MANIFEST = {
    "bytes": 9_720,
    "path": "construction_master/2026-07-21-public-open-v28/manifest.json",
    "sha256": "fbdd682a74cf762573fd607632c1f6b44a2ef2792db1fddb577e99ab8c2ba24c",
}
REPLACEMENT_INPUTS = {
    "artifact_id": "epoch-official-open-seed-v73",
    "data": {
        "bytes": 536_037,
        "path": "releases/2026-07-21-open-seed-v73/construction_pipeline.csv",
        "sha256": "751590cad43558ad2bbf655f2672be0109e12baadbbfa4288d3832b533200e59",
    },
    "definition": {
        "bytes": 88_004,
        "path": "sources/open-seed-2026-07-21-v73.json",
        "sha256": "cf8a4cfb8861ab732cdb9e72a01cbdd01d0e435102c47fd6d92bc30ebf11f97d",
    },
    "evidence": {
        "bytes": 204_886,
        "path": "releases/2026-07-21-open-seed-v73/evidence.csv",
        "sha256": "536730f17c17bb37f177dfec3cae1825897b8e98ebecea1ea4c2e370bc478018",
    },
    "manifest": {
        "bytes": 12_814,
        "path": "releases/2026-07-21-open-seed-v73/manifest.json",
        "sha256": "229c572759ab493448b788946a0c8a61ff6995d0ab505bea2af08860a19e204d",
    },
    "publication_contract_version": 4,
    "release_id": "epoch-official-open-seed-v73",
}


ACCEPTED_DEPENDENCY_CLOSURE: dict[str, dict[str, Any]] = {
    "federation_v33": {
        "artifact_id": "2026-07-21-public-open-v33",
        "definition": {
            "bytes": 1_788,
            "path": "sources/federation-2026-07-21-public-open-v33.json",
            "sha256": "6472c052092860af73da784b233261c6e8de6a7e9d853d215fa459d5347b4e89",
        },
        "manifest": {
            "bytes": 986,
            "path": "federated_indexes/2026-07-21-public-open-v33/manifest.json",
            "sha256": "4c2db492362d57d792fb9a162576e9505883bdc8daad6b08a9547d1ecb27ac7b",
        },
        "tree": {
            "path": "federated_indexes/2026-07-21-public-open-v33",
            "sha256": "0fa59ad26d24d6266df33613102828a42e231eb2f231872bc0a9146c9aa0c760",
        },
    },
    "identity_v9": {
        "artifact_id": "2026-07-21-public-open-v9",
        "definition": {
            "bytes": 1_735,
            "path": "sources/exact-identity-decisions-2026-07-21-public-open-v9.json",
            "sha256": "20b9a890b195029d64b29fb7d917956cca09e2062f5d91cc01f981e034aabcc1",
        },
        "manifest": {
            "bytes": 11_439,
            "path": "exact_identity_decisions/2026-07-21-public-open-v9/manifest.json",
            "sha256": "47b18c1eeb58eef7d1fa9d70489340e8d2651e428b9d945bc136ecc54c679e6c",
        },
        "tree": {
            "path": "exact_identity_decisions/2026-07-21-public-open-v9",
            "sha256": "a23703e6cf0469c2b81a0252d42c96cac95d64f1c772375c5529d3fb3b4e5a7a",
        },
    },
    "open_seed_v73": {
        "artifact_id": "2026-07-21-open-seed-v73",
        "definition": deepcopy(REPLACEMENT_INPUTS["definition"]),
        "manifest": deepcopy(REPLACEMENT_INPUTS["manifest"]),
        "tree": {
            "path": "releases/2026-07-21-open-seed-v73",
            "sha256": "692583b86324b746fd6edf0ec2dc5101efa86ce0f08e04831e0d471e767a6394",
        },
    },
    "predecessor_master_v28": {
        "artifact_id": "2026-07-21-public-open-v28",
        "definition": deepcopy(PREDECESSOR_DEFINITION),
        "manifest": deepcopy(PREDECESSOR_MANIFEST),
        "tree": {
            "path": "construction_master/2026-07-21-public-open-v28",
            "sha256": "ab0cd348fd72700e012902f5130a3cbb3045e897d9609f32583fc4fa0a25209f",
        },
    },
    "timeline_v6": {
        "artifact_id": "2026-07-21-public-open-v6",
        "definition": {
            "bytes": 3_001,
            "path": "sources/construction-timeline-2026-07-21-public-open-v6.json",
            "sha256": "cf89ac2d9672eb8d4e82ee65e7a6ed243887d71dbac0ef1d537a49000edc7afa",
        },
        "manifest": {
            "bytes": 3_957,
            "path": "construction_timelines/2026-07-21-public-open-v6/manifest.json",
            "sha256": "c01c91efd8c4100edcd197c0b8aa601a494d9c67ab60372cd46d25f045016543",
        },
        "tree": {
            "path": "construction_timelines/2026-07-21-public-open-v6",
            "sha256": "6f754dcaa6f9d0df7ded14a90da70b2eb7c14d75634ec7bd1c503d47ed060e8f",
        },
    },
}

REJECTED_GUARDS = {
    "federation_v32": {
        "bundle_path": "federated_indexes/2026-07-21-public-open-v32",
        "definition": {
            "bytes": 1_788,
            "path": "sources/federation-2026-07-21-public-open-v32.json",
            "sha256": "29ff67c72cbe83f48ed28db6e4c059f1513358cf43d20c6039ae5e27cc924dc9",
        },
        "final_bundle_must_be_absent": True,
        "token": "2026-07-21-public-open-v32",
    },
    "timeline_v4": {
        "definition": {
            "bytes": 2_676,
            "path": "sources/construction-timeline-2026-07-21-public-open-v4.json",
            "sha256": "8e45d010686c24c09411183caa31770df68496efb49be881b265be955e30ffdd",
        },
        "manifest": {
            "bytes": 3_632,
            "path": "construction_timelines/2026-07-21-public-open-v4/manifest.json",
            "sha256": "d09831798f54d245067498f1b8ddf46f048ffde1c4100a1b55435e5daf8f4589",
        },
        "token": "2026-07-21-public-open-v4",
        "tree": {
            "path": "construction_timelines/2026-07-21-public-open-v4",
            "sha256": "a46931052c9ba21d056a8bd7efedef09c9b2890fa60b4ded036dee519f3d30df",
        },
    },
}

_CHECKPOINT_ONLY_TOKENS = (
    b"2026-07-21-public-open-v33",
    b"2026-07-21-public-open-v9",
    b"2026-07-21-public-open-v6",
)
_REJECTED_TOKENS = tuple(
    guard["token"].encode("ascii") for guard in REJECTED_GUARDS.values()
)


def _v29_error(message: str) -> Exception:
    return ConstructionMasterV29Error(message)


def _validate_rejected_guards() -> None:
    for name, guard in REJECTED_GUARDS.items():
        _v29_validate_checkpoint(guard["definition"], f"rejected {name} definition")
    federation_bundle = _v29_resolve(
        REJECTED_GUARDS["federation_v32"]["bundle_path"],
        "rejected federation v32 bundle",
    )
    if federation_bundle.exists() or federation_bundle.is_symlink():
        raise _v29_error("rejected federation v32 final bundle appeared")
    timeline = REJECTED_GUARDS["timeline_v4"]
    _v29_validate_checkpoint(timeline["manifest"], "rejected timeline v4 manifest")
    timeline_tree = _v29_resolve(timeline["tree"]["path"], "rejected timeline v4 tree")
    if _v29_tree_digest(timeline_tree) != timeline["tree"]["sha256"]:
        raise _v29_error("rejected timeline v4 guard tree changed")


def validate_dependency_closure_v29() -> None:
    """Require exact accepted gates while excluding them from row provenance."""

    expected_lanes = {
        "federation_v33",
        "identity_v9",
        "open_seed_v73",
        "predecessor_master_v28",
        "timeline_v6",
    }
    if set(ACCEPTED_DEPENDENCY_CLOSURE) != expected_lanes:
        raise _v29_error("accepted v29 dependency closure is not final")
    for lane_name in sorted(expected_lanes):
        lane = ACCEPTED_DEPENDENCY_CLOSURE[lane_name]
        if set(lane) != {"artifact_id", "definition", "manifest", "tree"}:
            raise _v29_error(f"{lane_name} dependency schema changed")
        _v29_validate_checkpoint(lane["definition"], f"{lane_name} definition")
        _v29_validate_checkpoint(lane["manifest"], f"{lane_name} manifest")
        tree = lane["tree"]
        if set(tree) != {"path", "sha256"}:
            raise _v29_error(f"{lane_name} tree checkpoint schema changed")
        directory = _v29_resolve(str(tree["path"]), f"{lane_name} tree")
        if directory.is_symlink() or not directory.is_dir():
            raise _v29_error(f"{lane_name} tree must be a regular directory")
        if _v29_tree_digest(directory) != tree["sha256"]:
            raise _v29_error(f"accepted dependency tree changed: {tree['path']}")
    _validate_rejected_guards()
    manifest_path = _v29_resolve(
        REPLACEMENT_INPUTS["manifest"]["path"], "open-seed v73 manifest"
    )
    manifest = json.loads(manifest_path.read_bytes())
    if (
        manifest.get("current_status_inferred") is not False
        or manifest.get("lifecycle_status_semantics") != "last_observed"
    ):
        raise _v29_error("open-seed v73 current-status boundary changed")


def construction_master_v29_definition() -> dict[str, Any]:
    validate_dependency_closure_v29()
    predecessor_path = _v29_resolve(
        PREDECESSOR_DEFINITION["path"], "predecessor definition"
    )
    predecessor_raw = predecessor_path.read_bytes()
    if _checkpoint(predecessor_path) != {
        "bytes": PREDECESSOR_DEFINITION["bytes"],
        "sha256": PREDECESSOR_DEFINITION["sha256"],
    }:
        raise _v29_error("accepted v28 definition changed")
    try:
        document = json.loads(predecessor_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _v29_error("accepted v28 definition is invalid JSON") from error
    if predecessor_raw != _canonical_json(document):
        raise _v29_error("accepted v28 definition is not canonical")
    document["expected"] = {**EXPECTED_FIXED, **EXPECTED_DIGESTS}
    document["generated_at"] = GENERATED_AT
    document["inputs"]["replacement_release"] = deepcopy(REPLACEMENT_INPUTS)
    document["master_id"] = MASTER_ID
    document["scope"] = deepcopy(SCOPE_POLICY)
    raw = _canonical_json(document)
    for token in (*_CHECKPOINT_ONLY_TOKENS, *_REJECTED_TOKENS):
        if token in raw:
            raise _v29_error("checkpoint-only or rejected lineage entered definition")
    return document


def construction_master_v29_definition_bytes() -> bytes:
    return _canonical_json(construction_master_v29_definition())


_carrier_validate_construction_master_v29 = validate_construction_master_v29


def _forbidden_token(path: Path) -> bytes | None:
    tokens = (*_CHECKPOINT_ONLY_TOKENS, *_REJECTED_TOKENS)
    overlap = max(len(token) for token in tokens) - 1
    tail = b""
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            window = tail + chunk
            for token in tokens:
                if token in window:
                    return token
            tail = window[-overlap:]
    return None


def validate_construction_master_v29(
    directory: str | Path,
    *,
    definition_path: str | Path,
    reproduce: bool = True,
) -> dict[str, Any]:
    """Validate v29 and prove checkpoint/rejection tokens are not provenance."""

    manifest = _carrier_validate_construction_master_v29(
        directory, definition_path=definition_path, reproduce=reproduce
    )
    paths = [Path(definition_path), *sorted(Path(directory).iterdir())]
    for path in paths:
        token = _forbidden_token(path)
        if token is not None:
            raise _v29_error(
                f"checkpoint-only or rejected lineage entered {path.name}: "
                f"{token.decode('ascii')}"
            )
    return manifest


__all__ = [
    "ACCEPTED_DEPENDENCY_CLOSURE",
    "BUNDLE_PATH",
    "ConstructionMasterV29Error",
    "DEFINITION_PATH",
    "EXPECTED_DIGESTS",
    "EXPECTED_FIXED",
    "GENERATED_AT",
    "MASTER_ID",
    "PREPARATION_GENERATED_AT",
    "REJECTED_GUARDS",
    "SCOPE_POLICY",
    "construction_master_v29_definition",
    "construction_master_v29_definition_bytes",
    "discard_construction_master_v29_stage",
    "is_frozen_master_v29",
    "prepare_construction_master_v29",
    "publish_construction_master_v29",
    "validate_construction_master_v29",
    "validate_definition",
    "validate_dependency_closure_v29",
    "write_construction_master_v29",
]
