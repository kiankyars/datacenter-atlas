"""Governed v37-to-v38 federation successor for live open seed v97.

V38 replaces only the accepted open-seed-v92 child descriptor in immutable
federation v37.  The global-open-v3 and osm-fuzzy-review-v2 layers remain
byte-pinned and descriptor-identical.  The default path is a private
prepublication replay; live publication requires explicit authorization.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import federated_release as legacy
from . import federated_release_v5 as carrier_v5
from . import federated_release_v6 as federation
from . import federation_v37 as base
from . import open_seed_v69 as v69
from . import open_seed_v96 as v96
from . import open_seed_v97 as open_seed

ROOT = base.ROOT
BASE_DEFINITION = base.DEFINITION
BASE_INDEX_DIR = base.INDEX_DIR
V97_DEFINITION = open_seed.DEFINITION
V97_RELEASE = open_seed.RELEASE
DEFINITION = ROOT / "sources/federation-2026-07-22-public-open-v38.json"
INDEX_DIR = ROOT / "federated_indexes/2026-07-22-public-open-v38"
PUBLICATION_LOCK = ROOT / ".federation-v38.lock"

OLD_RELEASE_ID = base.NEW_RELEASE_ID
NEW_RELEASE_ID = open_seed.RELEASE_ID
UNCHANGED_RELEASE_IDS = frozenset({"global-open-v3", "osm-fuzzy-review-v2"})
V97_RECORDED_AT = "2026-07-22T06:06:40Z"

BASE_DEFINITION_PIN = base.DEFINITION_PIN
BASE_INDEX_PIN = base.INDEX_PIN
BASE_MANIFEST_PIN = base.MANIFEST_PIN
BASE_SIDECAR_PIN = base.SIDECAR_PIN
BASE_TREE_SHA256 = base.TREE_SHA256
V97_DEFINITION_PIN = (
    120_979,
    "32f22ccc74ec6ec33dc9bc7377a83bfee83f88dff3555555fc89cb43a27d673f",
)
V97_MANIFEST_PIN = (
    20_402,
    "0a6f41f4239944df27f2ce70e81a089b91cec401f154bbae28412b27a4d00fdd",
)
V97_TREE_SHA256 = "5136ad66f56b7474053ff3b8cbbffca1f3df3479d8a30745a1502917fa0e7954"

GLOBAL_RELEASE = ROOT / "releases/2026-07-18-global-open-v3"
OSM_REVIEW_RELEASE = ROOT / "releases/2026-07-18-osm-fuzzy-review-v2"
UNCHANGED_INPUTS = {
    "global-open-v3": {
        "path": GLOBAL_RELEASE,
        "manifest_pin": (
            2_547,
            "fe14c1b264ce7d5f589c717147e584f7ace97b832b0987389f2ee03ded6bb562",
        ),
        "tree_sha256": "dc84eae9920fbdf5374551091cfcb31821db7f3a85908fd3ba86becb0af9deb8",
    },
    "osm-fuzzy-review-v2": {
        "path": OSM_REVIEW_RELEASE,
        "manifest_pin": (
            2_811,
            "60ecf42e7b260c2f1822c65b9efb184e9fdbca3a36bd4b467960d26e8c9bb07c",
        ),
        "tree_sha256": "104eb5d5b4255c7eff5f93789a9624f80528de0af58193097d9bd853515261b9",
    },
}

CARRIER_SOURCE = ROOT / "datacenter_atlas/federated_release_v6.py"
CARRIER_SOURCE_PIN: tuple[int, str] | None = (
    13_001,
    "6f420a96b8c24639d2ea748948d6bedaf02a0025255bdb285c601d8f2844371a",
)

LICENSE_EXPRESSION = base.LICENSE_EXPRESSION
RIGHTS_NOTICE = base.RIGHTS_NOTICE

EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 570,
    "construction_pipeline_records": 531,
    "entities_by_kind": {"campus": 545, "project": 508},
    "evidence_records": 693,
    "resolution_candidates": 9,
    "source_family_entries": 424,
    "source_scoped_entity_records": 1_053,
}
EXPECTED_COUNTS = {
    "capacity_estimates": 1_356,
    "construction_pipeline_records": 6_781,
    "evidence_records": 13_706,
    "non_review_construction_pipeline_records": 651,
    "non_review_source_scoped_entity_records": 10_348,
    "release_bundles": 3,
    "resolution_candidates": 100_414,
    "review_only_construction_pipeline_records": 6_130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6_130,
    "source_family_entries": 431,
    "source_scoped_entity_records": 16_478,
    "unique_physical_sites": None,
}
EXPECTED_DELTA = {
    "capacity_estimates": 12,
    "construction_pipeline_records": 30,
    "evidence_records": 48,
    "non_review_construction_pipeline_records": 30,
    "non_review_source_scoped_entity_records": 65,
    "release_bundles": 0,
    "resolution_candidates": 0,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 40,
    "source_scoped_entity_records": 65,
}

CHILDREN = {
    NEW_RELEASE_ID: V97_RELEASE,
    "global-open-v3": GLOBAL_RELEASE,
    "osm-fuzzy-review-v2": OSM_REVIEW_RELEASE,
}
BANNED_CLAIMS = (
    "semianalysis",
    "semi-analysis",
    "global completeness",
    "regional completeness",
    "comprehensive",
    "parity",
)
PROMOTION_CONTRACT = {
    "atomic_no_replace_required": True,
    "directory_descriptor_bound_rename_required": True,
    "definition_and_bundle_same_filesystem_as_final_parent": True,
    "identity_checked_before_and_after_promotion": True,
    "rollback_uses_atomic_no_replace": True,
    "rollback_refuses_identity_mismatch": True,
    "replay_count": 2,
    "stage_adoption_allowed": False,
}


class FederationV38Error(RuntimeError):
    """Raised when v38 lineage, semantics, or publication differs."""


ParentBindings = Mapping[str, tuple[Path, tuple[int, int], int]]


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pin(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), _sha256(raw)


def tree_digest(root: Path) -> str:
    return v69.tree_digest(root)


def _validate_file(path: Path, pin: tuple[int, str], *, mode: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise FederationV38Error(f"expected ordinary pinned file: {path}")
    raw = path.read_bytes()
    if (len(raw), _sha256(raw)) != pin:
        raise FederationV38Error(f"pinned file differs: {path}")
    if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) != mode:
        raise FederationV38Error(f"pinned file mode differs: {path}")
    return raw


def _validate_frozen_tree(path: Path, expected: str) -> None:
    if (
        path.is_symlink()
        or not path.is_dir()
        or stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) != 0o555
        or tree_digest(path) != expected
    ):
        raise FederationV38Error(f"frozen tree pin differs: {path}")
    for member in path.rglob("*"):
        expected_mode = 0o555 if member.is_dir() else 0o444
        if (
            member.is_symlink()
            or stat.S_IMODE(member.stat(follow_symlinks=False).st_mode) != expected_mode
        ):
            raise FederationV38Error(f"frozen tree member differs: {member}")


def _validate_unchanged_child(release_id: str) -> None:
    spec = UNCHANGED_INPUTS[release_id]
    path = spec["path"]
    manifest_pin = spec["manifest_pin"]
    tree_sha256 = spec["tree_sha256"]
    if not isinstance(path, Path) or not isinstance(manifest_pin, tuple):
        raise FederationV38Error("static unchanged-child specification differs")
    if (
        path.is_symlink()
        or not path.is_dir()
        or _pin(path / federation.MANIFEST_FILENAME) != manifest_pin
        or tree_digest(path) != tree_sha256
    ):
        raise FederationV38Error(f"unchanged child pin differs: {release_id}")
    manifest = json.loads((path / federation.MANIFEST_FILENAME).read_text())
    if set(manifest.get("files", {})) != {
        member.name
        for member in path.iterdir()
        if member.is_file() and member.name != federation.MANIFEST_FILENAME
    }:
        raise FederationV38Error(f"unchanged child file set differs: {release_id}")
    for filename, row in manifest["files"].items():
        member = path / filename
        if (
            member.is_symlink()
            or not member.is_file()
            or _pin(member)
            != (
                row["bytes"],
                row["sha256"],
            )
        ):
            raise FederationV38Error(
                f"unchanged child member differs: {release_id}/{filename}"
            )


def _validate_no_completeness_claims(*documents: Mapping[str, Any]) -> None:
    text = "\n".join(
        _canonical_json(document).decode().casefold() for document in documents
    )
    marker = next((claim for claim in BANNED_CLAIMS if claim in text), None)
    if marker is not None:
        raise FederationV38Error(f"v38 asserted prohibited completeness: {marker}")


def _parse_generated(value: str, *, label: str = "generated_at") -> datetime:
    target = legacy._timestamp(value, label, require_canonical_utc=True)
    return datetime.fromisoformat(target)


def _validate_v97() -> dict[str, Any]:
    if CARRIER_SOURCE_PIN is None:
        raise FederationV38Error("v6 carrier source pin is not reviewed")
    _validate_file(CARRIER_SOURCE, CARRIER_SOURCE_PIN, mode=0o644)
    definition_raw = _validate_file(V97_DEFINITION, V97_DEFINITION_PIN, mode=0o444)
    definition = json.loads(definition_raw)
    if (
        definition_raw != _canonical_json(definition)
        or definition.get("release_id") != NEW_RELEASE_ID
        or definition.get("build", {}).get("recorded_at") != V97_RECORDED_AT
        or len(definition.get("curated_inputs", ())) != 519
    ):
        raise FederationV38Error("accepted v97 definition differs")
    _validate_file(
        V97_RELEASE / federation.MANIFEST_FILENAME,
        V97_MANIFEST_PIN,
        mode=0o444,
    )
    _validate_frozen_tree(V97_RELEASE, V97_TREE_SHA256)
    try:
        guard = open_seed._guard_state()
        open_seed._validate_guard(guard)
        manifest = open_seed._validate_release_facts(
            V97_RELEASE, recorded_at=V97_RECORDED_AT
        )
        open_seed._validate_publication_times(
            V97_DEFINITION,
            V97_RELEASE,
            recorded_at=V97_RECORDED_AT,
            require_live=True,
        )
    except RuntimeError as error:
        raise FederationV38Error(f"accepted v97 release differs: {error}") from error
    if (
        manifest.get("current_status_inferred") is not False
        or manifest.get("lifecycle_status_semantics") != "last_observed"
        or manifest.get(federation.GEOMETRY_NON_INFERENCE_FIELD) is not False
        or manifest.get("capacity_estimates") != 570
        or manifest.get("resolution_candidates") != 9
        or manifest.get("claim_boundary") != open_seed.CLAIM_BOUNDARY
        or manifest.get("coordinate_boundary") != open_seed.COORDINATE_BOUNDARY
        or manifest.get("stale_status_suppression") != open_seed.STALE_POLICY
        or manifest.get("governed_base_row_replacements") != {}
    ):
        raise FederationV38Error("accepted v97 non-inference boundary differs")
    for filename in (
        "capacity_estimates.csv",
        "resolution_candidates.csv",
        "resolution_candidates.json",
    ):
        if (V97_RELEASE / filename).read_bytes() != (
            v96.RELEASE / filename
        ).read_bytes():
            raise FederationV38Error(
                f"v97 inferred or changed unsupported rows: {filename}"
            )
    return definition


def _v97_child_definition() -> legacy._ChildDefinition:
    return legacy._ChildDefinition(
        release_id=NEW_RELEASE_ID,
        release_path=V97_RELEASE,
        reference="../../releases/2026-07-22-open-seed-v97/",
        expected_manifest_sha256=V97_MANIFEST_PIN[1],
        license_expression=LICENSE_EXPRESSION,
        rights_notice=RIGHTS_NOTICE,
    )


def _validate_inputs() -> tuple[dict[str, Any], Mapping[str, Any], dict[str, Any]]:
    base_raw = _validate_file(BASE_DEFINITION, BASE_DEFINITION_PIN, mode=0o444)
    base_definition = json.loads(base_raw)
    if base_raw != _canonical_json(base_definition):
        raise FederationV38Error("accepted v37 definition is not canonical")
    _validate_file(
        BASE_INDEX_DIR / federation.INDEX_FILENAME, BASE_INDEX_PIN, mode=0o444
    )
    _validate_file(
        BASE_INDEX_DIR / federation.MANIFEST_FILENAME,
        BASE_MANIFEST_PIN,
        mode=0o444,
    )
    _validate_file(
        BASE_INDEX_DIR / federation.MANIFEST_HASH_FILENAME,
        BASE_SIDECAR_PIN,
        mode=0o444,
    )
    _validate_frozen_tree(BASE_INDEX_DIR, BASE_TREE_SHA256)
    try:
        base_index = carrier_v5.validate_federated_release_index(
            BASE_INDEX_DIR, child_release_paths=base.CHILDREN
        )
    except carrier_v5.FederatedReleaseError as error:
        raise FederationV38Error(f"accepted v37 index is invalid: {error}") from error
    if base_index.get("counts") != base.EXPECTED_COUNTS:
        raise FederationV38Error("accepted v37 counts differ")
    for release_id in UNCHANGED_RELEASE_IDS:
        _validate_unchanged_child(release_id)
    _validate_v97()
    try:
        descriptor = federation._inspect_child(_v97_child_definition())
    except federation.FederatedReleaseError as error:
        raise FederationV38Error(
            f"v97 federation descriptor invalid: {error}"
        ) from error
    if descriptor.get("counts") != EXPECTED_OPEN_COUNTS:
        raise FederationV38Error("v97 federation descriptor counts differ")
    manifest = descriptor["manifest"]
    if (
        manifest.get("recorded_at") != V97_RECORDED_AT
        or manifest.get("current_status_inferred") is not False
        or manifest.get("lifecycle_status_semantics") != "last_observed"
        or manifest.get("lifecycle_freshness_records") != 583
        or manifest.get(federation.GEOMETRY_NON_INFERENCE_FIELD) is not False
    ):
        raise FederationV38Error("v97 descriptor inferred status or geometry")
    return base_definition, base_index, descriptor


def build_definition(generated_at: str) -> bytes:
    accepted, _base_index, _descriptor = _validate_inputs()
    target = _parse_generated(generated_at)
    if target <= _parse_generated(V97_RECORDED_AT, label="v97 recorded_at"):
        raise FederationV38Error("v38 generated_at must follow v97 recorded_at")
    definition = deepcopy(accepted)
    definition["generated_at"] = generated_at
    matches = [
        row for row in definition["children"] if row["release_id"] == OLD_RELEASE_ID
    ]
    if len(matches) != 1:
        raise FederationV38Error("accepted v37 open child differs")
    matches[0].update(
        {
            "expected_manifest_sha256": V97_MANIFEST_PIN[1],
            "reference": "../../releases/2026-07-22-open-seed-v97/",
            "release_id": NEW_RELEASE_ID,
            "release_path": "../releases/2026-07-22-open-seed-v97",
        }
    )
    if {row["release_id"] for row in definition["children"]} != (
        UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID}
    ):
        raise FederationV38Error("v38 child set differs")
    base_by_id = {row["release_id"]: row for row in accepted["children"]}
    current_by_id = {row["release_id"]: row for row in definition["children"]}
    if any(
        current_by_id[release_id] != base_by_id[release_id]
        for release_id in UNCHANGED_RELEASE_IDS
    ):
        raise FederationV38Error("v38 changed an ODbL child definition")
    _validate_no_completeness_claims(definition)
    return _canonical_json(definition)


def _child_definitions(document: Mapping[str, Any]) -> list[legacy._ChildDefinition]:
    children: list[legacy._ChildDefinition] = []
    rows = document.get("children")
    if not isinstance(rows, list) or len(rows) != 3:
        raise FederationV38Error("v38 definition child inventory differs")
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping) or set(row) != {
            "release_id",
            "release_path",
            "reference",
            "expected_manifest_sha256",
            "license_expression",
            "rights_notice",
        }:
            raise FederationV38Error(f"v38 child schema differs: {index}")
        release_id = legacy._release_id(row["release_id"], "v38 release_id")
        if release_id not in CHILDREN:
            raise FederationV38Error(f"v38 unexpected child: {release_id}")
        children.append(
            legacy._ChildDefinition(
                release_id=release_id,
                release_path=CHILDREN[release_id],
                reference=legacy._reference(row["reference"], "v38 reference"),
                expected_manifest_sha256=legacy._sha256(
                    row["expected_manifest_sha256"], "v38 child manifest hash"
                ),
                license_expression=legacy._required_text(
                    row["license_expression"], "v38 child license"
                ),
                rights_notice=legacy._required_text(
                    row["rights_notice"], "v38 child rights"
                ),
            )
        )
    if len({row.release_id for row in children}) != 3:
        raise FederationV38Error("v38 duplicate child release id")
    return sorted(children, key=lambda row: row.release_id)


def build_bundle(definition_raw: bytes) -> federation.FederatedIndexBundle:
    try:
        document = legacy._json_object(definition_raw, "v38 federation definition")
    except legacy.FederatedReleaseError as error:
        raise FederationV38Error(str(error)) from error
    if definition_raw != _canonical_json(document) or set(document) != {
        "children",
        "generated_at",
        "schema_version",
    }:
        raise FederationV38Error("v38 definition bytes differ")
    if document.get("schema_version") != 1:
        raise FederationV38Error("v38 definition schema version differs")
    generated_at = legacy._timestamp(
        document.get("generated_at"),
        "v38 generated_at",
        require_canonical_utc=True,
    )
    definitions = _child_definitions(document)
    try:
        releases = [federation._inspect_child(child) for child in definitions]
    except federation.FederatedReleaseError as error:
        raise FederationV38Error(f"v38 child inspection failed: {error}") from error
    latest_child = max(
        _parse_generated(row["manifest"]["recorded_at"], label="child recorded_at")
        for row in releases
    )
    if _parse_generated(generated_at) <= latest_child:
        raise FederationV38Error("v38 generated_at does not follow every child")
    counts = legacy._aggregate_counts(releases, include_scope_splits=True)
    index = {
        "schema_version": federation.INDEX_SCHEMA_VERSION,
        "format": federation.INDEX_FORMAT,
        "generated_at": generated_at,
        "policy": dict(federation.FEDERATION_POLICY),
        "counts": counts,
        "releases": releases,
    }
    index_bytes = legacy._canonical_json(index)
    manifest = {
        "schema_version": federation.INDEX_SCHEMA_VERSION,
        "format": federation.BUNDLE_FORMAT,
        "generated_at": generated_at,
        "scope": dict(federation.FEDERATION_POLICY),
        "definition": {
            "file": DEFINITION.name,
            "bytes": len(definition_raw),
            "sha256": _sha256(definition_raw),
        },
        "artifacts": {
            federation.INDEX_FILENAME: {
                "format": federation.INDEX_FORMAT,
                "release_bundles": len(releases),
                "bytes": len(index_bytes),
                "sha256": _sha256(index_bytes),
            }
        },
    }
    manifest_bytes = legacy._canonical_json(manifest)
    sidecar = (f"{_sha256(manifest_bytes)}  {federation.MANIFEST_FILENAME}\n").encode(
        "ascii"
    )
    return federation.FederatedIndexBundle(
        index_bytes=index_bytes,
        manifest_bytes=manifest_bytes,
        manifest_hash_bytes=sidecar,
        index=index,
        manifest=manifest,
    )


def _bundle_payloads(bundle: federation.FederatedIndexBundle) -> dict[str, bytes]:
    return {
        federation.INDEX_FILENAME: bundle.index_bytes,
        federation.MANIFEST_FILENAME: bundle.manifest_bytes,
        federation.MANIFEST_HASH_FILENAME: bundle.manifest_hash_bytes,
    }


def _validate_counts(index: Mapping[str, Any], accepted: Mapping[str, Any]) -> None:
    if index.get("counts") != EXPECTED_COUNTS:
        raise FederationV38Error(f"v38 aggregate counts differ: {index.get('counts')}")
    delta = {
        key: index["counts"][key] - accepted["counts"][key] for key in EXPECTED_DELTA
    }
    if delta != EXPECTED_DELTA:
        raise FederationV38Error(f"v38 aggregate delta differs: {delta}")
    by_id = {row["release_id"]: row for row in index["releases"]}
    accepted_by_id = {row["release_id"]: row for row in accepted["releases"]}
    if set(by_id) != UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID}:
        raise FederationV38Error("v38 release set differs")
    if any(
        by_id[release_id] != accepted_by_id[release_id]
        for release_id in UNCHANGED_RELEASE_IDS
    ):
        raise FederationV38Error("v38 changed an inherited child descriptor")
    child = by_id[NEW_RELEASE_ID]
    if child["counts"] != EXPECTED_OPEN_COUNTS:
        raise FederationV38Error("v38 v97 descriptor counts differ")
    manifest = child["manifest"]
    if (
        manifest.get("recorded_at") != V97_RECORDED_AT
        or manifest.get("current_status_inferred") is not False
        or manifest.get("lifecycle_status_semantics") != "last_observed"
        or manifest.get("lifecycle_freshness_records") != 583
        or manifest.get(federation.GEOMETRY_NON_INFERENCE_FIELD) is not False
    ):
        raise FederationV38Error("v38 inferred current status or geometry")
    policy = index.get("policy")
    if policy != federation.FEDERATION_POLICY or (
        policy.get("child_entities_merged") is not False
        or policy.get("cross_source_deduplication") is not False
        or policy.get("licenses_or_attributions_combined") is not False
        or policy.get("unique_physical_site_count") is not None
        or index["counts"]["unique_physical_sites"] is not None
    ):
        raise FederationV38Error(
            "v38 weakened unresolved-identity or rights separation"
        )
    if (
        "ODbL" in child["rights"]["license_expression"]
        or "ODbL" not in by_id["global-open-v3"]["rights"]["license_expression"]
        or "ODbL" not in by_id["osm-fuzzy-review-v2"]["rights"]["license_expression"]
        or by_id["osm-fuzzy-review-v2"]["scope"]["review_only"] is not True
    ):
        raise FederationV38Error("v38 combined ODbL and official-source rights")
    _validate_no_completeness_claims(index)


def _write_new_file(
    path: Path,
    payload: bytes,
    *,
    identity_tracker: dict[str, tuple[str, int, int]] | None = None,
    tracker_key: str | None = None,
) -> None:
    descriptor = os.open(
        path,
        os.O_CREAT
        | os.O_EXCL
        | os.O_WRONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        details = _fstat_identity_with_retry(
            descriptor,
            expected_kind="file",
            expected_mode=0o600,
            label=f"v38 stage file {path.name}",
        )
    except BaseException:
        os.close(descriptor)
        raise
    if identity_tracker is not None:
        if tracker_key is None:
            raise FederationV38Error("v38 stage tracker key is missing")
        identity_tracker[tracker_key] = ("file", details[0], details[1])
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _write_bundle(
    stage: Path,
    bundle: federation.FederatedIndexBundle,
    identities: dict[str, tuple[str, int, int]],
) -> None:
    if stage.is_symlink() or not stage.is_dir() or any(stage.iterdir()):
        raise FederationV38Error("v38 bundle stage is not owned and empty")
    expected_root = identities.get(".")
    if expected_root != ("directory", *_identity(stage, directory=True)):
        raise FederationV38Error("v38 bundle stage root identity changed")
    for filename, raw in _bundle_payloads(bundle).items():
        _write_new_file(
            stage / filename,
            raw,
            identity_tracker=identities,
            tracker_key=filename,
        )
    if _tree_identities(stage) != identities:
        raise FederationV38Error("v38 bundle member identities differ")


def _validate_definition_bytes(path: Path, generated_at: str, *, frozen: bool) -> bytes:
    mode = 0o444 if frozen else 0o600
    if (
        path.is_symlink()
        or not path.is_file()
        or stat.S_IMODE(path.stat().st_mode) != mode
    ):
        raise FederationV38Error("v38 staged definition mode differs")
    raw = path.read_bytes()
    expected = build_definition(generated_at)
    if raw != expected:
        raise FederationV38Error("v38 definition differs")
    return raw


def _validate_bundle_facts(
    definition: Path,
    bundle_path: Path,
    *,
    generated_at: str,
    frozen: bool,
) -> Mapping[str, Any]:
    definition_raw = _validate_definition_bytes(definition, generated_at, frozen=frozen)
    expected_bundle = build_bundle(definition_raw)
    expected_payloads = _bundle_payloads(expected_bundle)
    expected_mode = 0o555 if frozen else 0o700
    file_mode = 0o444 if frozen else 0o600
    if (
        bundle_path.is_symlink()
        or not bundle_path.is_dir()
        or stat.S_IMODE(bundle_path.stat().st_mode) != expected_mode
    ):
        raise FederationV38Error("v38 bundle stage mode differs")
    entries = {path.name: path for path in bundle_path.iterdir()}
    if set(entries) != set(expected_payloads):
        raise FederationV38Error("v38 bundle file set differs")
    for filename, raw in expected_payloads.items():
        path = entries[filename]
        if (
            path.is_symlink()
            or not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != file_mode
            or path.read_bytes() != raw
        ):
            raise FederationV38Error(f"v38 bundle member differs: {filename}")
    try:
        index = federation.validate_federated_release_index(
            bundle_path,
            child_release_paths=CHILDREN,
            require_frozen=frozen,
        )
    except federation.FederatedReleaseError as error:
        raise FederationV38Error(f"v38 bundle validation failed: {error}") from error
    _accepted_definition, accepted_index, _descriptor = _validate_inputs()
    _validate_counts(index, accepted_index)
    if index != expected_bundle.index:
        raise FederationV38Error("v38 bundle index differs from canonical replay")
    return index


def _identity(path: Path, *, directory: bool) -> tuple[int, int]:
    if path.is_symlink():
        raise FederationV38Error(f"symlinked v38 publication member: {path}")
    metadata = path.stat(follow_symlinks=False)
    if directory and not stat.S_ISDIR(metadata.st_mode):
        raise FederationV38Error(f"v38 member is not a directory: {path}")
    if not directory and not stat.S_ISREG(metadata.st_mode):
        raise FederationV38Error(f"v38 member is not a file: {path}")
    return metadata.st_dev, metadata.st_ino


def _fstat_identity_with_retry(
    descriptor: int,
    *,
    expected_kind: str,
    label: str,
    expected_mode: int | None = None,
    attempts: int = 2,
) -> tuple[int, int, str]:
    if attempts < 1:
        raise ValueError("identity attempts must be positive")
    last_error: OSError | None = None
    for _attempt in range(attempts):
        try:
            metadata = os.fstat(descriptor)
        except OSError as error:
            last_error = error
            continue
        actual_kind = (
            "directory"
            if stat.S_ISDIR(metadata.st_mode)
            else "file"
            if stat.S_ISREG(metadata.st_mode)
            else "other"
        )
        if actual_kind != expected_kind:
            raise FederationV38Error(
                f"{label} is not an owned {expected_kind}; retained fail-closed"
            )
        if (
            expected_mode is not None
            and stat.S_IMODE(metadata.st_mode) != expected_mode
        ):
            raise FederationV38Error(f"{label} mode differs; retained fail-closed")
        return metadata.st_dev, metadata.st_ino, actual_kind
    raise FederationV38Error(
        f"{label} identity unavailable after {attempts} attempts; retained fail-closed"
    ) from last_error


def _has_identity(path: Path, identity: tuple[int, int], *, directory: bool) -> bool:
    try:
        return _identity(path, directory=directory) == identity
    except (FileNotFoundError, FederationV38Error):
        return False


@contextmanager
def _bound_parent_bindings() -> Iterator[dict[str, tuple[Path, tuple[int, int], int]]]:
    bindings: dict[str, tuple[Path, tuple[int, int], int]] = {}
    descriptors: list[int] = []
    try:
        for label, parent in (
            ("definition", DEFINITION.parent),
            ("index", INDEX_DIR.parent),
        ):
            try:
                descriptor = os.open(
                    parent,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                )
            except OSError as error:
                raise FederationV38Error(
                    f"v38 {label} parent cannot be opened: {parent}"
                ) from error
            descriptors.append(descriptor)
            metadata = _fstat_identity_with_retry(
                descriptor,
                expected_kind="directory",
                label=f"v38 {label} parent binding",
            )
            identity = metadata[:2]
            if not _has_identity(parent, identity, directory=True):
                raise FederationV38Error(f"v38 {label} parent changed while binding")
            bindings[label] = (parent, identity, descriptor)
        _assert_parent_bindings(bindings, label="parent binding")
        yield bindings
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


@contextmanager
def _current_parent_binding(
    parent: Path, *, label: str
) -> Iterator[tuple[Path, tuple[int, int], int]]:
    try:
        descriptor = os.open(
            parent,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as error:
        raise FederationV38Error(
            f"{label} v38 current parent cannot be opened: {parent}"
        ) from error
    try:
        metadata = _fstat_identity_with_retry(
            descriptor,
            expected_kind="directory",
            label=f"{label} v38 current parent",
        )
        identity = metadata[:2]
        if not _has_identity(parent, identity, directory=True):
            raise FederationV38Error(
                f"{label} v38 current parent changed while binding"
            )
        yield parent, identity, descriptor
    finally:
        os.close(descriptor)


def _assert_binding_descriptors(bindings: ParentBindings, *, label: str) -> None:
    for name, (_path, identity, descriptor) in bindings.items():
        metadata = _fstat_identity_with_retry(
            descriptor,
            expected_kind="directory",
            label=f"{label} v38 {name} parent descriptor",
        )
        if metadata[:2] != identity:
            raise FederationV38Error(
                f"{label} v38 {name} parent descriptor identity changed"
            )


def _assert_parent_bindings(bindings: ParentBindings, *, label: str) -> None:
    expected_paths = {
        "definition": DEFINITION.parent,
        "index": INDEX_DIR.parent,
    }
    if set(bindings) != set(expected_paths):
        raise FederationV38Error(f"{label} v38 parent-binding schema differs")
    for name, current_path in expected_paths.items():
        bound_path, bound_identity, _descriptor = bindings[name]
        if bound_path != current_path or not _has_identity(
            current_path, bound_identity, directory=True
        ):
            raise FederationV38Error(f"{label} v38 {name} parent identity changed")
    _assert_binding_descriptors(bindings, label=label)


def _binding_for_parent(
    bindings: ParentBindings, parent: Path
) -> tuple[Path, tuple[int, int], int]:
    matches = [binding for binding in bindings.values() if binding[0] == parent]
    if len(matches) != 1:
        raise FederationV38Error(f"v38 parent is not uniquely bound: {parent}")
    return matches[0]


def _bound_identity(
    binding: tuple[Path, tuple[int, int], int],
    name: str,
    *,
    directory: bool,
) -> tuple[int, int]:
    if not name or name in {".", ".."} or "/" in name or "\0" in name:
        raise FederationV38Error(f"invalid v38 bound member name: {name!r}")
    try:
        metadata = os.stat(name, dir_fd=binding[2], follow_symlinks=False)
    except OSError as error:
        raise FederationV38Error(f"v38 bound member is unavailable: {name}") from error
    if directory and not stat.S_ISDIR(metadata.st_mode):
        raise FederationV38Error(f"v38 bound member is not a directory: {name}")
    if not directory and not stat.S_ISREG(metadata.st_mode):
        raise FederationV38Error(f"v38 bound member is not a file: {name}")
    return metadata.st_dev, metadata.st_ino


def _has_bound_identity(
    binding: tuple[Path, tuple[int, int], int],
    name: str,
    identity: tuple[int, int],
    *,
    directory: bool,
) -> bool:
    try:
        return _bound_identity(binding, name, directory=directory) == identity
    except FederationV38Error:
        return False


def _bound_member_exists(binding: tuple[Path, tuple[int, int], int], name: str) -> bool:
    try:
        os.stat(name, dir_fd=binding[2], follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise FederationV38Error(
            f"v38 bound member presence is unavailable: {name}"
        ) from error
    return True


def _bundle_descendants(root: Path) -> list[Path]:
    return sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix())


def _tree_identities(root: Path) -> dict[str, tuple[str, int, int]]:
    identities: dict[str, tuple[str, int, int]] = {}
    for path in [root, *_bundle_descendants(root)]:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise FederationV38Error(f"v38 bundle contains symlink: {relative}")
        metadata = path.stat(follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            kind = "directory"
        elif stat.S_ISREG(metadata.st_mode):
            kind = "file"
        else:
            raise FederationV38Error(f"v38 bundle has special member: {relative}")
        identities[relative] = (kind, metadata.st_dev, metadata.st_ino)
    return identities


def _assert_tree_identities(
    root: Path, expected: Mapping[str, tuple[str, int, int]]
) -> None:
    if _tree_identities(root) != dict(expected):
        raise FederationV38Error("v38 recursive bundle identity changed")


def _bound_tree_identities(
    binding: tuple[Path, tuple[int, int], int], root_name: str
) -> dict[str, tuple[str, int, int]]:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        root_descriptor = os.open(root_name, flags, dir_fd=binding[2])
    except OSError as error:
        raise FederationV38Error(
            f"v38 bound bundle root is unavailable: {root_name}"
        ) from error
    identities: dict[str, tuple[str, int, int]] = {}

    def walk(descriptor: int, relative: str) -> None:
        metadata = os.fstat(descriptor)
        identities[relative] = ("directory", metadata.st_dev, metadata.st_ino)
        for name in sorted(os.listdir(descriptor)):
            if not name or name in {".", ".."} or "/" in name or "\0" in name:
                raise FederationV38Error(f"invalid v38 bound tree member: {name!r}")
            child_relative = name if relative == "." else f"{relative}/{name}"
            child = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISDIR(child.st_mode):
                child_descriptor = os.open(name, flags, dir_fd=descriptor)
                try:
                    walk(child_descriptor, child_relative)
                finally:
                    os.close(child_descriptor)
            elif stat.S_ISREG(child.st_mode):
                identities[child_relative] = (
                    "file",
                    child.st_dev,
                    child.st_ino,
                )
            else:
                raise FederationV38Error(
                    f"v38 bound tree has special member: {child_relative}"
                )

    try:
        walk(root_descriptor, ".")
    finally:
        os.close(root_descriptor)
    return identities


def _assert_bound_tree_identities(
    binding: tuple[Path, tuple[int, int], int],
    root_name: str,
    expected: Mapping[str, tuple[str, int, int]],
) -> None:
    if _bound_tree_identities(binding, root_name) != dict(expected):
        raise FederationV38Error("v38 recursive bound bundle identity changed")


def _discard_bundle_stage(
    root: Path, expected: Mapping[str, tuple[str, int, int]]
) -> None:
    if not root.exists() and not root.is_symlink():
        return
    _assert_tree_identities(root, expected)
    root.chmod(0o700)
    for path in _bundle_descendants(root):
        path.chmod(0o700 if path.is_dir() else 0o600)
    shutil.rmtree(root)


def _discard_file_stage(path: Path, identity: tuple[int, int]) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if _identity(path, directory=False) != identity:
        raise FederationV38Error("refusing substituted v38 definition cleanup")
    path.chmod(0o600)
    path.unlink()


def _discard_bound_file_stage(
    binding: tuple[Path, tuple[int, int], int],
    name: str,
    identity: tuple[int, int],
) -> bool:
    if not _bound_member_exists(binding, name):
        return False
    if not _has_bound_identity(binding, name, identity, directory=False):
        raise FederationV38Error("refusing substituted bound v38 definition cleanup")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(name, flags, dir_fd=binding[2])
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or (metadata.st_dev, metadata.st_ino) != identity
        ):
            raise FederationV38Error("refusing substituted open v38 definition cleanup")
        os.fchmod(descriptor, 0o600)
        if not _has_bound_identity(binding, name, identity, directory=False):
            raise FederationV38Error("refusing late-substituted v38 definition cleanup")
        os.unlink(name, dir_fd=binding[2])
    finally:
        os.close(descriptor)
    if _bound_member_exists(binding, name):
        raise FederationV38Error("v38 bound definition cleanup left residue")
    return True


def _discard_bound_bundle_stage(
    binding: tuple[Path, tuple[int, int], int],
    root_name: str,
    expected: Mapping[str, tuple[str, int, int]],
) -> bool:
    if not _bound_member_exists(binding, root_name):
        return False
    _assert_bound_tree_identities(binding, root_name, expected)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    root_descriptor = os.open(root_name, flags, dir_fd=binding[2])

    def children(relative: str) -> dict[str, tuple[str, int, int]]:
        prefix = "" if relative == "." else f"{relative}/"
        result: dict[str, tuple[str, int, int]] = {}
        for path, row in expected.items():
            if path == relative or not path.startswith(prefix):
                continue
            remainder = path[len(prefix) :]
            if "/" not in remainder:
                result[remainder] = row
        return result

    def discard_directory(descriptor: int, relative: str) -> None:
        directory_metadata = os.fstat(descriptor)
        expected_directory = expected.get(relative)
        if expected_directory != (
            "directory",
            directory_metadata.st_dev,
            directory_metadata.st_ino,
        ):
            raise FederationV38Error(
                f"refusing substituted bound v38 directory cleanup: {relative}"
            )
        expected_children = children(relative)
        if set(os.listdir(descriptor)) != set(expected_children):
            raise FederationV38Error(
                f"refusing changed bound v38 directory cleanup: {relative}"
            )
        os.fchmod(descriptor, 0o700)
        for name, expected_child in sorted(expected_children.items()):
            child_relative = name if relative == "." else f"{relative}/{name}"
            metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            observed_kind = (
                "directory"
                if stat.S_ISDIR(metadata.st_mode)
                else "file"
                if stat.S_ISREG(metadata.st_mode)
                else "other"
            )
            if expected_child != (
                observed_kind,
                metadata.st_dev,
                metadata.st_ino,
            ):
                raise FederationV38Error(
                    f"refusing substituted bound v38 member cleanup: {child_relative}"
                )
            if observed_kind == "directory":
                child_descriptor = os.open(name, flags, dir_fd=descriptor)
                try:
                    discard_directory(child_descriptor, child_relative)
                finally:
                    os.close(child_descriptor)
                current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if expected_child != (
                    "directory",
                    current.st_dev,
                    current.st_ino,
                ):
                    raise FederationV38Error(
                        f"refusing late-substituted v38 directory cleanup: {child_relative}"
                    )
                os.rmdir(name, dir_fd=descriptor)
            elif observed_kind == "file":
                file_flags = (
                    os.O_RDONLY
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0)
                )
                file_descriptor = os.open(name, file_flags, dir_fd=descriptor)
                try:
                    opened = os.fstat(file_descriptor)
                    if expected_child != (
                        "file",
                        opened.st_dev,
                        opened.st_ino,
                    ):
                        raise FederationV38Error(
                            f"refusing substituted open v38 member cleanup: {child_relative}"
                        )
                    os.fchmod(file_descriptor, 0o600)
                    current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                    if expected_child != (
                        "file",
                        current.st_dev,
                        current.st_ino,
                    ):
                        raise FederationV38Error(
                            f"refusing late-substituted v38 member cleanup: {child_relative}"
                        )
                    os.unlink(name, dir_fd=descriptor)
                finally:
                    os.close(file_descriptor)
            else:  # pragma: no cover - rejected by the equality check above
                raise FederationV38Error(
                    f"unsupported bound v38 cleanup member: {child_relative}"
                )

    try:
        discard_directory(root_descriptor, ".")
    finally:
        os.close(root_descriptor)
    root_identity = expected.get(".")
    if root_identity is None or not _has_bound_identity(
        binding,
        root_name,
        (root_identity[1], root_identity[2]),
        directory=True,
    ):
        raise FederationV38Error("refusing late-substituted v38 bundle cleanup")
    os.rmdir(root_name, dir_fd=binding[2])
    if _bound_member_exists(binding, root_name):
        raise FederationV38Error("v38 bound bundle cleanup left residue")
    return True


def _create_owned_bundle_stage() -> tuple[Path, dict[str, tuple[str, int, int]]]:
    """Create a same-parent bundle stage without adopting an unknown path."""

    stage = Path(tempfile.mkdtemp(prefix=f".{INDEX_DIR.name}.", dir=INDEX_DIR.parent))
    descriptor: int | None = None
    identity: tuple[int, int] | None = None
    try:
        descriptor = os.open(
            stage,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        metadata = _fstat_identity_with_retry(
            descriptor,
            expected_kind="directory",
            expected_mode=0o700,
            label="v38 bundle stage root",
        )
        identity = metadata[:2]
        if not _has_identity(stage, identity, directory=True):
            raise FederationV38Error(
                "v38 bundle stage differs from creation descriptor; retained fail-closed"
            )
        return stage, {".": ("directory", *identity)}
    except BaseException as error:
        if identity is not None and _has_identity(stage, identity, directory=True):
            try:
                _discard_bundle_stage(stage, {".": ("directory", *identity)})
            except Exception as cleanup_error:  # noqa: BLE001 - preserve creation failure
                error.add_note(f"v38 owned bundle-root cleanup failed: {cleanup_error}")
        else:
            error.add_note(f"v38 unknown bundle stage retained fail-closed: {stage}")
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _create_owned_definition_stage(payload: bytes) -> tuple[Path, tuple[int, int]]:
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{DEFINITION.name}.", suffix=".stage", dir=DEFINITION.parent
    )
    stage = Path(temporary)
    identity: tuple[int, int] | None = None
    descriptor_open = True
    try:
        metadata = _fstat_identity_with_retry(
            descriptor,
            expected_kind="file",
            expected_mode=0o600,
            label="v38 definition stage",
        )
        identity = metadata[:2]
        if not _has_identity(stage, identity, directory=False):
            raise FederationV38Error(
                "v38 definition stage differs from creation descriptor; retained fail-closed"
            )
        with os.fdopen(descriptor, "wb") as stream:
            descriptor_open = False
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        return stage, identity
    except BaseException as error:
        if descriptor_open:
            os.close(descriptor)
        if identity is not None and _has_identity(stage, identity, directory=False):
            try:
                _discard_file_stage(stage, identity)
            except Exception as cleanup_error:  # noqa: BLE001 - preserve creation failure
                error.add_note(f"v38 owned definition cleanup failed: {cleanup_error}")
        else:
            error.add_note(
                f"v38 unknown definition stage retained fail-closed: {stage}"
            )
        raise


def _rename_bound_noreplace(
    binding: tuple[Path, tuple[int, int], int],
    source_name: str,
    destination_name: str,
) -> None:
    for name in (source_name, destination_name):
        if not name or name in {".", ".."} or "/" in name or "\0" in name:
            raise FederationV38Error(f"invalid v38 rename member: {name!r}")
    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    destination = os.fsencode(destination_name)
    descriptor = binding[2]
    if sys.platform == "darwin":
        function = getattr(library, "renameatx_np", None)
        if function is None:  # pragma: no cover
            raise FederationV38Error("bound atomic no-replace rename is unavailable")
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(descriptor, source, descriptor, destination, 0x00000004)
    elif sys.platform.startswith("linux"):
        function = getattr(library, "renameat2", None)
        if function is None:  # pragma: no cover
            raise FederationV38Error("bound atomic no-replace rename is unavailable")
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(descriptor, source, descriptor, destination, 0x00000001)
    else:  # pragma: no cover
        raise FederationV38Error("bound atomic no-replace rename is unavailable")
    if result == 0:
        os.fsync(descriptor)
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FederationV38Error(
            f"late output collision; refusing overwrite: {destination_name}"
        )
    raise FederationV38Error(
        "bound atomic no-replace rename failed: "
        f"{source_name} -> {destination_name}: {os.strerror(error_number)}"
    )


def _promote_noreplace(
    stage: Path,
    destination: Path,
    *,
    directory: bool,
    parent_bindings: ParentBindings | None = None,
) -> tuple[int, int]:
    if parent_bindings is not None:
        _assert_parent_bindings(parent_bindings, label="before promotion")
        source_binding = _binding_for_parent(parent_bindings, stage.parent)
        destination_binding = _binding_for_parent(parent_bindings, destination.parent)
        if source_binding != destination_binding:
            raise FederationV38Error("v38 promotion crosses bound parents")
        identity = _bound_identity(source_binding, stage.name, directory=directory)
        if not _has_identity(stage, identity, directory=directory):
            raise FederationV38Error("v38 stage path differs from bound source")
        try:
            _rename_bound_noreplace(source_binding, stage.name, destination.name)
            if not _has_bound_identity(
                destination_binding,
                destination.name,
                identity,
                directory=directory,
            ):
                raise FederationV38Error("v38 bound promoted identity differs")
        finally:
            _assert_parent_bindings(parent_bindings, label="after promotion")
        return identity
    identity = _identity(stage, directory=directory)
    if stage.parent.stat().st_dev != destination.parent.stat().st_dev:
        raise FederationV38Error("v38 promotion crosses filesystems")
    try:
        federation._promote_noreplace(stage, destination)
    except federation.FederatedReleaseError as error:
        raise FederationV38Error(str(error)) from error
    if not _has_identity(destination, identity, directory=directory):
        raise FederationV38Error("v38 promoted identity differs")
    return identity


def _rollback_noreplace(
    destination: Path,
    stage: Path,
    identity: tuple[int, int],
    *,
    directory: bool,
    parent_bindings: ParentBindings | None = None,
) -> None:
    if parent_bindings is not None:
        _assert_binding_descriptors(parent_bindings, label="before rollback")
        binding = _binding_for_parent(parent_bindings, destination.parent)
        if _binding_for_parent(parent_bindings, stage.parent) != binding:
            raise FederationV38Error("v38 rollback crosses bound parents")
        if not _has_bound_identity(
            binding, destination.name, identity, directory=directory
        ):
            raise FederationV38Error("v38 refuses identity-mismatched rollback")
        if _bound_member_exists(binding, stage.name):
            raise FederationV38Error("v38 bound rollback stage is occupied")
        _rename_bound_noreplace(binding, destination.name, stage.name)
        if not _has_bound_identity(binding, stage.name, identity, directory=directory):
            raise FederationV38Error("v38 bound rollback identity differs")
        _assert_binding_descriptors(parent_bindings, label="after rollback")
        return
    if not _has_identity(destination, identity, directory=directory):
        raise FederationV38Error("v38 refuses identity-mismatched rollback")
    if stage.exists() or stage.is_symlink():
        raise FederationV38Error("v38 rollback stage is occupied")
    _promote_noreplace(destination, stage, directory=directory)
    if not _has_identity(stage, identity, directory=directory):
        raise FederationV38Error("v38 rollback identity differs")


def _fsync(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | (getattr(os, "O_DIRECTORY", 0) if path.is_dir() else 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _freeze(definition: Path, bundle: Path) -> None:
    definition.chmod(0o444)
    _fsync(definition)
    descendants = _bundle_descendants(bundle)
    for path in descendants:
        if path.is_file():
            path.chmod(0o444)
            _fsync(path)
    for path in sorted(
        (path for path in descendants if path.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        path.chmod(0o555)
        _fsync(path)
    bundle.chmod(0o555)
    _fsync(bundle)


def _validate_publication_times(
    definition: Path,
    bundle: Path,
    *,
    generated_at: str,
    require_live: bool,
) -> None:
    target = _parse_generated(generated_at)
    paths = [definition, bundle, *_bundle_descendants(bundle)]
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        birth = getattr(metadata, "st_birthtime", metadata.st_mtime)
        if max(birth, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise FederationV38Error(
                f"v38 inode birth/mtime post-dates generated_at: {path}"
            )
    if require_live:
        if datetime.now(UTC) < target:
            raise FederationV38Error("v38 generated_at is not live")
        for path in paths:
            if path.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
                raise FederationV38Error(
                    f"v38 recursive ctime predates generated_at: {path}"
                )


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _refresh_publication_ctimes(definition: Path, bundle: Path) -> None:
    definition.chmod(0o400)
    definition.chmod(0o444)
    _fsync(definition)
    descendants = _bundle_descendants(bundle)
    for path in descendants:
        if path.is_file():
            path.chmod(0o400)
            path.chmod(0o444)
            _fsync(path)
    for path in sorted(
        (path for path in descendants if path.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        path.chmod(0o500)
        path.chmod(0o555)
        _fsync(path)
    bundle.chmod(0o500)
    bundle.chmod(0o555)
    _fsync(bundle)


def _guard_state() -> dict[str, Any]:
    return {
        "base_definition": _pin(BASE_DEFINITION),
        "base_index": _pin(BASE_INDEX_DIR / federation.INDEX_FILENAME),
        "base_manifest": _pin(BASE_INDEX_DIR / federation.MANIFEST_FILENAME),
        "base_sidecar": _pin(BASE_INDEX_DIR / federation.MANIFEST_HASH_FILENAME),
        "base_tree": tree_digest(BASE_INDEX_DIR),
        "v97_definition": _pin(V97_DEFINITION),
        "v97_manifest": _pin(V97_RELEASE / federation.MANIFEST_FILENAME),
        "v97_tree": tree_digest(V97_RELEASE),
        "carrier": _pin(CARRIER_SOURCE),
        "unchanged": {
            release_id: {
                "manifest": _pin(spec["path"] / federation.MANIFEST_FILENAME),
                "tree": tree_digest(spec["path"]),
            }
            for release_id, spec in sorted(UNCHANGED_INPUTS.items())
        },
    }


def _validate_guard(expected: Mapping[str, Any]) -> None:
    if CARRIER_SOURCE_PIN is None:
        raise FederationV38Error("v6 carrier source pin is not reviewed")
    reviewed = {
        "base_definition": BASE_DEFINITION_PIN,
        "base_index": BASE_INDEX_PIN,
        "base_manifest": BASE_MANIFEST_PIN,
        "base_sidecar": BASE_SIDECAR_PIN,
        "base_tree": BASE_TREE_SHA256,
        "v97_definition": V97_DEFINITION_PIN,
        "v97_manifest": V97_MANIFEST_PIN,
        "v97_tree": V97_TREE_SHA256,
        "carrier": CARRIER_SOURCE_PIN,
        "unchanged": {
            release_id: {
                "manifest": spec["manifest_pin"],
                "tree": spec["tree_sha256"],
            }
            for release_id, spec in sorted(UNCHANGED_INPUTS.items())
        },
    }
    current = _guard_state()
    if dict(expected) != current or current != reviewed:
        raise FederationV38Error("v38 accepted-input guard differs")


def _two_replay_gate(digests: Sequence[str]) -> str:
    if len(digests) != 2 or not all(
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
        for value in digests
    ):
        raise FederationV38Error("v38 requires exactly two replay digests")
    if digests[0] != digests[1]:
        raise FederationV38Error("v38 replay digests differ")
    return digests[0]


def _validate_offline_replays(
    definition: Path, bundle_path: Path, *, replay_count: int
) -> str:
    if replay_count != 2:
        raise FederationV38Error("v38 requires exactly two offline replays")
    definition_raw = definition.read_bytes()
    staged = {
        path.name: path.read_bytes()
        for path in bundle_path.iterdir()
        if path.is_file() and not path.is_symlink()
    }
    digests: list[str] = []
    for _replay in range(replay_count):
        payloads = _bundle_payloads(build_bundle(definition_raw))
        if payloads != staged:
            raise FederationV38Error("v38 offline replay differs from staged bundle")
        digests.append(_sha256(payloads[federation.MANIFEST_FILENAME]))
    return _two_replay_gate(digests)


def _private_promotion_roundtrip(
    definition: Path,
    bundle: Path,
    *,
    definition_identity: tuple[int, int],
    bundle_identities: Mapping[str, tuple[str, int, int]],
    parent_bindings: ParentBindings,
) -> None:
    token = f"{os.getpid()}-{time.time_ns()}"
    promoted_definition = definition.parent / f".{DEFINITION.name}.roundtrip-{token}"
    promoted_bundle = bundle.parent / f".{INDEX_DIR.name}.roundtrip-{token}"
    if (
        promoted_definition.exists()
        or promoted_definition.is_symlink()
        or promoted_bundle.exists()
        or promoted_bundle.is_symlink()
    ):
        raise FederationV38Error("v38 private roundtrip destination collision")
    bundle_identity = _identity(bundle, directory=True)
    bundle_promoted = False
    definition_promoted = False
    operation_error: BaseException | None = None
    try:
        _promote_noreplace(
            bundle,
            promoted_bundle,
            directory=True,
            parent_bindings=parent_bindings,
        )
        bundle_promoted = True
        _assert_tree_identities(promoted_bundle, bundle_identities)
        _promote_noreplace(
            definition,
            promoted_definition,
            directory=False,
            parent_bindings=parent_bindings,
        )
        definition_promoted = True
        if not _has_identity(promoted_definition, definition_identity, directory=False):
            raise FederationV38Error("v38 private definition identity changed")
    except BaseException as error:  # noqa: BLE001 - rollback before propagating interrupts
        operation_error = error
        definition_promoted = definition_promoted or _has_identity(
            promoted_definition, definition_identity, directory=False
        )
        bundle_promoted = bundle_promoted or _has_identity(
            promoted_bundle, bundle_identity, directory=True
        )
    rollback_errors: list[Exception] = []
    if definition_promoted:
        try:
            _rollback_noreplace(
                promoted_definition,
                definition,
                definition_identity,
                directory=False,
                parent_bindings=parent_bindings,
            )
        except Exception as error:  # noqa: BLE001 - aggregate rollback failures
            rollback_errors.append(error)
    if bundle_promoted:
        try:
            _assert_tree_identities(promoted_bundle, bundle_identities)
            _rollback_noreplace(
                promoted_bundle,
                bundle,
                bundle_identity,
                directory=True,
                parent_bindings=parent_bindings,
            )
            _assert_tree_identities(bundle, bundle_identities)
        except Exception as error:  # noqa: BLE001 - aggregate rollback failures
            rollback_errors.append(error)
    if operation_error is not None:
        for error in rollback_errors:
            operation_error.add_note(f"v38 private rollback failed: {error}")
        raise operation_error
    if rollback_errors:
        primary = rollback_errors[0]
        for error in rollback_errors[1:]:
            primary.add_note(f"additional v38 private rollback failure: {error}")
        raise primary
    if promoted_definition.exists() or promoted_bundle.exists():
        raise FederationV38Error("v38 private promotion roundtrip left residue")


def _require_final_absent(label: str, *, include_lock: bool = False) -> None:
    paths = [DEFINITION, INDEX_DIR]
    if include_lock:
        paths.append(PUBLICATION_LOCK)
    present = [str(path) for path in paths if path.exists() or path.is_symlink()]
    if present:
        raise FederationV38Error(f"{label} v38 final path collision: {present!r}")


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK,
            os.O_CREAT
            | os.O_EXCL
            | os.O_WRONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
    except FileExistsError as error:
        raise FederationV38Error("active v38 publication lock exists") from error
    identity: tuple[int, int] | None = None
    try:
        identity = _fstat_identity_with_retry(
            descriptor,
            expected_kind="file",
            expected_mode=0o600,
            label="v38 publication lock",
        )[:2]
        payload = f"pid={os.getpid()}\n".encode("ascii")
        if os.write(descriptor, payload) != len(payload):
            raise FederationV38Error("short v38 publication-lock write")
        os.fsync(descriptor)
        yield
    finally:
        try:
            os.close(descriptor)
        finally:
            if identity is not None:
                try:
                    current = PUBLICATION_LOCK.stat(follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    if (
                        not stat.S_ISREG(current.st_mode)
                        or (current.st_dev, current.st_ino) != identity
                    ):
                        raise FederationV38Error(
                            "refusing substituted v38 publication-lock cleanup"
                        )
                    PUBLICATION_LOCK.unlink()


def _target_timestamp(
    generated_at: str | None, *, future: bool
) -> tuple[str, datetime]:
    target = (
        _parse_generated(generated_at)
        if generated_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=90)
    )
    if target <= _parse_generated(V97_RECORDED_AT, label="v97 recorded_at"):
        raise FederationV38Error("v38 generated_at must follow v97 recorded_at")
    if future and target <= datetime.now(UTC):
        raise FederationV38Error("v38 generated_at must be future before staging")
    return target.isoformat(timespec="seconds").replace("+00:00", "Z"), target


def _bundle_report(bundle_path: Path) -> dict[str, dict[str, Any]]:
    return {
        path.name: {
            "bytes": len(path.read_bytes()),
            "sha256": _sha256(path.read_bytes()),
        }
        for path in sorted(bundle_path.iterdir(), key=lambda item: item.name)
    }


def validate_federation_v38(
    definition: Path = DEFINITION,
    index_directory: Path = INDEX_DIR,
    *,
    require_live: bool = True,
    require_frozen: bool = True,
    replay_count: int = 2,
    parent_bindings: ParentBindings | None = None,
) -> Mapping[str, Any]:
    if replay_count != 2:
        raise FederationV38Error("v38 requires exactly two offline replays")
    if parent_bindings is None:
        with _bound_parent_bindings() as bindings:
            return validate_federation_v38(
                definition,
                index_directory,
                require_live=require_live,
                require_frozen=require_frozen,
                replay_count=replay_count,
                parent_bindings=bindings,
            )
    bindings = parent_bindings
    _assert_parent_bindings(bindings, label="start of final validation")
    guard = _guard_state()
    _validate_guard(guard)
    if definition.is_symlink() or not definition.is_file():
        raise FederationV38Error("v38 definition is not an ordinary file")
    document = json.loads(definition.read_bytes())
    generated_at = legacy._timestamp(
        document.get("generated_at"),
        "v38 generated_at",
        require_canonical_utc=True,
    )
    index = _validate_bundle_facts(
        definition,
        index_directory,
        generated_at=generated_at,
        frozen=require_frozen,
    )
    _assert_parent_bindings(bindings, label="during final validation")
    _validate_offline_replays(definition, index_directory, replay_count=replay_count)
    _assert_parent_bindings(bindings, label="during final replay validation")
    _validate_publication_times(
        definition,
        index_directory,
        generated_at=generated_at,
        require_live=require_live,
    )
    _assert_parent_bindings(bindings, label="before final guard validation")
    if _guard_state() != guard:
        raise FederationV38Error("v38 validation mutated accepted inputs")
    _assert_parent_bindings(bindings, label="end of final validation")
    return index


def _cleanup_private_stages(
    *,
    definition: Path | None,
    definition_identity: tuple[int, int] | None,
    bundle: Path | None,
    bundle_identities: Mapping[str, tuple[str, int, int]] | None,
    parent_bindings: ParentBindings,
    active_error: BaseException | None,
) -> None:
    cleanup_errors: list[Exception] = []
    if bundle is not None and bundle_identities is not None:
        binding = _binding_for_parent(parent_bindings, bundle.parent)
        try:
            _assert_binding_descriptors(parent_bindings, label="bound bundle cleanup")
            _discard_bound_bundle_stage(binding, bundle.name, bundle_identities)
        except Exception as error:  # noqa: BLE001 - aggregate fail-closed cleanup
            cleanup_errors.append(error)
        try:
            with _current_parent_binding(
                bundle.parent, label="bundle cleanup fallback"
            ) as current_binding:
                _discard_bound_bundle_stage(
                    current_binding, bundle.name, bundle_identities
                )
        except Exception as error:  # noqa: BLE001 - aggregate fail-closed cleanup
            cleanup_errors.append(error)
    if definition is not None and definition_identity is not None:
        binding = _binding_for_parent(parent_bindings, definition.parent)
        try:
            _assert_binding_descriptors(
                parent_bindings, label="bound definition cleanup"
            )
            _discard_bound_file_stage(binding, definition.name, definition_identity)
        except Exception as error:  # noqa: BLE001 - aggregate fail-closed cleanup
            cleanup_errors.append(error)
        try:
            with _current_parent_binding(
                definition.parent, label="definition cleanup fallback"
            ) as current_binding:
                _discard_bound_file_stage(
                    current_binding, definition.name, definition_identity
                )
        except Exception as error:  # noqa: BLE001 - aggregate fail-closed cleanup
            cleanup_errors.append(error)
    if cleanup_errors:
        if active_error is not None:
            for error in cleanup_errors:
                active_error.add_note(f"v38 cleanup failed: {error}")
        else:
            primary = cleanup_errors[0]
            for error in cleanup_errors[1:]:
                primary.add_note(f"additional v38 cleanup failed: {error}")
            raise primary


def prepare_federation_v38(
    generated_at: str | None = None, *, replay_count: int = 2
) -> dict[str, Any]:
    """Validate a private v38 stage and stop before either final promotion."""

    with _bound_parent_bindings() as parent_bindings:
        return _prepare_federation_v38(
            generated_at,
            replay_count=replay_count,
            parent_bindings=parent_bindings,
        )


def _prepare_federation_v38(
    generated_at: str | None,
    *,
    replay_count: int,
    parent_bindings: ParentBindings,
) -> dict[str, Any]:
    _assert_parent_bindings(parent_bindings, label="prepublication start")
    _require_final_absent("prepublication", include_lock=True)
    if replay_count != 2:
        raise FederationV38Error("v38 requires exactly two offline replays")
    timestamp, _target = _target_timestamp(generated_at, future=True)
    guard = _guard_state()
    _validate_guard(guard)
    definition_raw = build_definition(timestamp)
    definition_stage: Path | None = None
    definition_identity: tuple[int, int] | None = None
    bundle_stage: Path | None = None
    bundle_identities: dict[str, tuple[str, int, int]] | None = None
    result: dict[str, Any]
    try:
        bundle_stage, bundle_identities = _create_owned_bundle_stage()
        _assert_parent_bindings(parent_bindings, label="after bundle-stage creation")
        definition_stage, definition_identity = _create_owned_definition_stage(
            definition_raw
        )
        _assert_parent_bindings(
            parent_bindings, label="after definition-stage creation"
        )
        bundle = build_bundle(definition_raw)
        _write_bundle(bundle_stage, bundle, bundle_identities)
        _freeze(definition_stage, bundle_stage)
        _assert_tree_identities(bundle_stage, bundle_identities)
        index = _validate_bundle_facts(
            definition_stage,
            bundle_stage,
            generated_at=timestamp,
            frozen=True,
        )
        replay_digest = _validate_offline_replays(
            definition_stage, bundle_stage, replay_count=replay_count
        )
        _validate_publication_times(
            definition_stage,
            bundle_stage,
            generated_at=timestamp,
            require_live=False,
        )
        frozen_definition = definition_stage.read_bytes()
        frozen_tree = tree_digest(bundle_stage)
        _private_promotion_roundtrip(
            definition_stage,
            bundle_stage,
            definition_identity=definition_identity,
            bundle_identities=bundle_identities,
            parent_bindings=parent_bindings,
        )
        if (
            definition_stage.read_bytes() != frozen_definition
            or tree_digest(bundle_stage) != frozen_tree
        ):
            raise FederationV38Error("v38 private bytes changed during roundtrip")
        _assert_tree_identities(bundle_stage, bundle_identities)
        _assert_parent_bindings(parent_bindings, label="prepublication completion")
        result = {
            "status": "prepublication-validated",
            "publication_authorized": False,
            "barrier": "stopped-before-final-no-replace-promotion",
            "generated_at": timestamp,
            "definition_bytes": len(frozen_definition),
            "definition_sha256": _sha256(frozen_definition),
            "bundle_files": _bundle_report(bundle_stage),
            "bundle_tree_sha256": frozen_tree,
            "two_replay_manifest_sha256": replay_digest,
            "counts": index["counts"],
            "delta_from_v37": dict(EXPECTED_DELTA),
            "release_ids": [row["release_id"] for row in index["releases"]],
            "private_no_replace_roundtrip_validated": True,
            "final_definition_absent": not DEFINITION.exists(),
            "final_index_absent": not INDEX_DIR.exists(),
            "publication_lock_absent": not PUBLICATION_LOCK.exists(),
        }
    finally:
        _cleanup_private_stages(
            definition=definition_stage,
            definition_identity=definition_identity,
            bundle=bundle_stage,
            bundle_identities=bundle_identities,
            parent_bindings=parent_bindings,
            active_error=sys.exception(),
        )
    if _guard_state() != guard:
        raise FederationV38Error("v38 prepublication mutated accepted inputs")
    _require_final_absent("post-prepublication", include_lock=True)
    return result


def _rollback_bundle(
    identity: tuple[int, int],
    identities: Mapping[str, tuple[str, int, int]],
    stage: Path,
    parent_bindings: ParentBindings,
) -> None:
    _assert_binding_descriptors(parent_bindings, label="bundle rollback")
    binding = _binding_for_parent(parent_bindings, INDEX_DIR.parent)
    if not _has_bound_identity(binding, INDEX_DIR.name, identity, directory=True):
        raise FederationV38Error("refusing rollback of substituted v38 bundle")
    _assert_bound_tree_identities(binding, INDEX_DIR.name, identities)
    _rollback_noreplace(
        INDEX_DIR,
        stage,
        identity,
        directory=True,
        parent_bindings=parent_bindings,
    )
    _assert_bound_tree_identities(binding, stage.name, identities)
    _assert_binding_descriptors(parent_bindings, label="completed bundle rollback")


def _rollback_definition(
    identity: tuple[int, int], stage: Path, parent_bindings: ParentBindings
) -> None:
    _assert_binding_descriptors(parent_bindings, label="definition rollback")
    binding = _binding_for_parent(parent_bindings, DEFINITION.parent)
    if not _has_bound_identity(binding, DEFINITION.name, identity, directory=False):
        raise FederationV38Error("refusing rollback of substituted v38 definition")
    _rollback_noreplace(
        DEFINITION,
        stage,
        identity,
        directory=False,
        parent_bindings=parent_bindings,
    )
    if not _has_bound_identity(binding, stage.name, identity, directory=False):
        raise FederationV38Error("v38 bound definition rollback identity differs")
    _assert_binding_descriptors(parent_bindings, label="completed definition rollback")


def _existing_identical(
    generated_at: str | None, parent_bindings: ParentBindings
) -> dict[str, Any]:
    _assert_parent_bindings(parent_bindings, label="existing-identical validation")
    document = json.loads(DEFINITION.read_bytes())
    existing_generated_at = document.get("generated_at")
    if not isinstance(existing_generated_at, str):
        raise FederationV38Error("existing v38 generated_at is missing")
    if generated_at is not None and generated_at != existing_generated_at:
        raise FederationV38Error("existing v38 generated_at differs")
    index = validate_federation_v38(
        DEFINITION, INDEX_DIR, parent_bindings=parent_bindings
    )
    _assert_parent_bindings(parent_bindings, label="existing-identical completion")
    return {
        "status": "existing-identical",
        "definition": str(DEFINITION),
        "definition_sha256": _sha256(DEFINITION.read_bytes()),
        "federated_index": str(INDEX_DIR),
        "bundle_files": _bundle_report(INDEX_DIR),
        "bundle_tree_sha256": tree_digest(INDEX_DIR),
        "generated_at": existing_generated_at,
        "counts": index["counts"],
        "release_ids": [row["release_id"] for row in index["releases"]],
    }


def build_and_publish_federation_v38(
    generated_at: str | None = None, *, publication_authorized: bool = False
) -> dict[str, Any]:
    """Publish v38 only after explicit authorization and every governed gate."""

    if not publication_authorized:
        raise FederationV38Error("v38 publication requires explicit authorization")
    with _bound_parent_bindings() as parent_bindings:
        return _build_and_publish_federation_v38(
            generated_at, parent_bindings=parent_bindings
        )


def _build_and_publish_federation_v38(
    generated_at: str | None, *, parent_bindings: ParentBindings
) -> dict[str, Any]:
    with _publication_lock():
        _assert_parent_bindings(parent_bindings, label="inside publication lock")
        definition_present = DEFINITION.exists() or DEFINITION.is_symlink()
        index_present = INDEX_DIR.exists() or INDEX_DIR.is_symlink()
        if definition_present and index_present:
            return _existing_identical(generated_at, parent_bindings)
        if definition_present or index_present:
            raise FederationV38Error("partial v38 final-path collision")
        timestamp, target = _target_timestamp(generated_at, future=True)
        guard = _guard_state()
        _validate_guard(guard)
        definition_raw = build_definition(timestamp)
        _assert_parent_bindings(parent_bindings, label="before staging")
        _require_final_absent("initial")
        bundle_stage, bundle_identities = _create_owned_bundle_stage()
        _assert_parent_bindings(parent_bindings, label="after bundle-stage creation")
        definition_stage: Path | None = None
        definition_identity: tuple[int, int] | None = None
        published_bundle = False
        published_definition = False
        try:
            definition_stage, definition_identity = _create_owned_definition_stage(
                definition_raw
            )
            _assert_parent_bindings(
                parent_bindings, label="after definition-stage creation"
            )
            bundle = build_bundle(definition_raw)
            _write_bundle(bundle_stage, bundle, bundle_identities)
            _freeze(definition_stage, bundle_stage)
            _assert_tree_identities(bundle_stage, bundle_identities)
            _validate_bundle_facts(
                definition_stage,
                bundle_stage,
                generated_at=timestamp,
                frozen=True,
            )
            _validate_offline_replays(definition_stage, bundle_stage, replay_count=2)
            _validate_publication_times(
                definition_stage,
                bundle_stage,
                generated_at=timestamp,
                require_live=False,
            )
            _private_promotion_roundtrip(
                definition_stage,
                bundle_stage,
                definition_identity=definition_identity,
                bundle_identities=bundle_identities,
                parent_bindings=parent_bindings,
            )
            frozen_definition = definition_stage.read_bytes()
            frozen_tree = tree_digest(bundle_stage)
            _assert_parent_bindings(parent_bindings, label="before publication wait")
            _require_final_absent("pre-wait")
            _wait_until(target)
            _assert_parent_bindings(parent_bindings, label="after publication wait")
            _require_final_absent("late")
            if not _has_identity(
                definition_stage, definition_identity, directory=False
            ):
                raise FederationV38Error("v38 definition stage identity changed")
            _assert_tree_identities(bundle_stage, bundle_identities)
            if (
                definition_stage.read_bytes() != frozen_definition
                or tree_digest(bundle_stage) != frozen_tree
                or _guard_state() != guard
            ):
                raise FederationV38Error(
                    "v38 private stage or inputs changed while waiting"
                )
            _refresh_publication_ctimes(definition_stage, bundle_stage)
            if not _has_identity(
                definition_stage, definition_identity, directory=False
            ):
                raise FederationV38Error("v38 refreshed definition identity changed")
            _assert_tree_identities(bundle_stage, bundle_identities)
            if (
                definition_stage.read_bytes() != frozen_definition
                or tree_digest(bundle_stage) != frozen_tree
            ):
                raise FederationV38Error("v38 private bytes changed at publication")
            _validate_publication_times(
                definition_stage,
                bundle_stage,
                generated_at=timestamp,
                require_live=True,
            )

            bundle_binding = _binding_for_parent(parent_bindings, INDEX_DIR.parent)
            definition_binding = _binding_for_parent(parent_bindings, DEFINITION.parent)
            bundle_identity = _bound_identity(
                bundle_binding, bundle_stage.name, directory=True
            )
            try:
                promoted_bundle_identity = _promote_noreplace(
                    bundle_stage,
                    INDEX_DIR,
                    directory=True,
                    parent_bindings=parent_bindings,
                )
                published_bundle = True
                if promoted_bundle_identity != bundle_identity:
                    raise FederationV38Error("v38 bundle promotion identity differs")
                _assert_bound_tree_identities(
                    bundle_binding, INDEX_DIR.name, bundle_identities
                )
                if tree_digest(INDEX_DIR) != frozen_tree:
                    raise FederationV38Error("v38 promoted bundle bytes differ")
                promoted_definition_identity = _promote_noreplace(
                    definition_stage,
                    DEFINITION,
                    directory=False,
                    parent_bindings=parent_bindings,
                )
                published_definition = True
                if promoted_definition_identity != definition_identity:
                    raise FederationV38Error(
                        "v38 definition promotion identity differs"
                    )
                if DEFINITION.read_bytes() != frozen_definition:
                    raise FederationV38Error("v38 promoted definition bytes differ")
            except BaseException as error:
                published_definition = published_definition or _has_bound_identity(
                    definition_binding,
                    DEFINITION.name,
                    definition_identity,
                    directory=False,
                )
                published_bundle = published_bundle or _has_bound_identity(
                    bundle_binding,
                    INDEX_DIR.name,
                    bundle_identity,
                    directory=True,
                )
                if published_definition:
                    try:
                        _rollback_definition(
                            definition_identity,
                            definition_stage,
                            parent_bindings,
                        )
                        published_definition = False
                    except Exception as rollback_error:  # noqa: BLE001 - preserve primary failure
                        error.add_note(
                            f"v38 definition rollback failed: {rollback_error}"
                        )
                if published_bundle:
                    try:
                        _rollback_bundle(
                            bundle_identity,
                            bundle_identities,
                            bundle_stage,
                            parent_bindings,
                        )
                        published_bundle = False
                    except Exception as rollback_error:  # noqa: BLE001 - preserve primary failure
                        error.add_note(f"v38 bundle rollback failed: {rollback_error}")
                raise

            try:
                index = validate_federation_v38(
                    DEFINITION,
                    INDEX_DIR,
                    parent_bindings=parent_bindings,
                )
                if _guard_state() != guard:
                    raise FederationV38Error("v38 publication mutated accepted inputs")
                _assert_parent_bindings(parent_bindings, label="after final validation")
            except BaseException as error:
                rollback_errors: list[Exception] = []
                try:
                    _rollback_definition(
                        definition_identity, definition_stage, parent_bindings
                    )
                    published_definition = False
                except Exception as rollback_error:  # noqa: BLE001 - aggregate rollback failures
                    rollback_errors.append(rollback_error)
                try:
                    _rollback_bundle(
                        bundle_identity,
                        bundle_identities,
                        bundle_stage,
                        parent_bindings,
                    )
                    published_bundle = False
                except Exception as rollback_error:  # noqa: BLE001 - aggregate rollback failures
                    rollback_errors.append(rollback_error)
                for rollback_error in rollback_errors:
                    error.add_note(f"v38 rollback failed: {rollback_error}")
                raise
            _assert_parent_bindings(parent_bindings, label="publication completion")
            result = {
                "status": "published",
                "definition": str(DEFINITION),
                "definition_sha256": _sha256(DEFINITION.read_bytes()),
                "federated_index": str(INDEX_DIR),
                "bundle_files": _bundle_report(INDEX_DIR),
                "bundle_tree_sha256": tree_digest(INDEX_DIR),
                "generated_at": timestamp,
                "counts": index["counts"],
                "release_ids": [row["release_id"] for row in index["releases"]],
            }
        finally:
            active_error = sys.exception()
            _cleanup_private_stages(
                definition=(None if published_definition else definition_stage),
                definition_identity=definition_identity,
                bundle=(None if published_bundle else bundle_stage),
                bundle_identities=bundle_identities,
                parent_bindings=parent_bindings,
                active_error=active_error,
            )
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--generated-at")
    result.add_argument("--publish-authorized", action="store_true")
    result.add_argument("--verify", action="store_true")
    return result


def main(
    argv: Sequence[str] | None = None, *, publication_authorized: bool = False
) -> int:
    arguments = parser().parse_args(argv)
    if arguments.verify:
        index = validate_federation_v38()
        result: Mapping[str, Any] = {
            "status": "validated",
            "definition": str(DEFINITION),
            "federated_index": str(INDEX_DIR),
            "counts": index["counts"],
            "generated_at": index["generated_at"],
            "release_ids": [row["release_id"] for row in index["releases"]],
        }
    elif publication_authorized or arguments.publish_authorized:
        result = build_and_publish_federation_v38(
            arguments.generated_at, publication_authorized=True
        )
    else:
        result = prepare_federation_v38(arguments.generated_at)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFINITION",
    "EXPECTED_COUNTS",
    "EXPECTED_DELTA",
    "EXPECTED_OPEN_COUNTS",
    "INDEX_DIR",
    "PROMOTION_CONTRACT",
    "FederationV38Error",
    "build_and_publish_federation_v38",
    "build_bundle",
    "build_definition",
    "main",
    "prepare_federation_v38",
    "tree_digest",
    "validate_federation_v38",
]
