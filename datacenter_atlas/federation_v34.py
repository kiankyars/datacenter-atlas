"""Publish the strict v33-to-v34 federation successor for open seed v83."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence

from . import federated_release as legacy
from . import federated_release_v3 as federation
from . import federation_publication as publication
from . import federation_v33 as base


ROOT = base.ROOT
BASE_DEFINITION = base.DEFINITION
BASE_INDEX_DIR = base.INDEX_DIR
V83_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v83.json"
V83_RELEASE = ROOT / "releases/2026-07-21-open-seed-v83"
DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v34.json"
INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v34"
PUBLICATION_LOCK = ROOT / ".federation-v34.lock"

GENERATED_AT = "2026-07-21T17:47:00Z"
V83_RECORDED_AT = "2026-07-21T17:38:10Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v73"
NEW_RELEASE_ID = "epoch-official-open-seed-v83"
UNCHANGED_RELEASE_IDS = frozenset({"global-open-v3", "osm-fuzzy-review-v2"})

BASE_DEFINITION_PIN = (
    1_788,
    "6472c052092860af73da784b233261c6e8de6a7e9d853d215fa459d5347b4e89",
)
BASE_MANIFEST_PIN = (
    986,
    "4c2db492362d57d792fb9a162576e9505883bdc8daad6b08a9547d1ecb27ac7b",
)
BASE_TREE_SHA256 = "0fa59ad26d24d6266df33613102828a42e231eb2f231872bc0a9146c9aa0c760"
V83_DEFINITION_PIN = (
    98_808,
    "84534350a3cf40c7f85479b9d4d42b53604f1858d5325b79dfb0c93de03be4e7",
)
V83_MANIFEST_PIN = (
    14_812,
    "56f33ade743f50e36bd4b2d6f32fa71eaa2b117af79c8580f92d7319c77bd7d5",
)
V83_TREE_SHA256 = "1cc39e4079c989d558c33ef63c3109919da533c5feabe9eb02c7cd8347e1d94d"
DEFINITION_PIN = (
    1_788,
    "f01622e680fac69a3fc1ad78151d56cf5cd5b412a28efea91e998fceba367a82",
)
INDEX_PIN = (
    35_181,
    "6389e18f6a1085e0a2cba577e412406187ea89d017e921aba6e7fb3edede60ba",
)
MANIFEST_PIN = (
    986,
    "31f2d60f266045f01af510f9fc16e541642231697167f3feaf3a70012a376503",
)
SIDECAR_PIN = (
    80,
    "9700de599f58cd252acf4e4e0e25d24eeecb1c28c0007fa837e76ddf9b73fb4d",
)
TREE_SHA256 = "a65ae68300e8a6a5a4446e7b264485fcc850d96900de047c960370e57df46bf2"

LICENSE_EXPRESSION = base.rejected.LICENSE_EXPRESSION
RIGHTS_NOTICE = base.rejected.RIGHTS_NOTICE

EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 542,
    "construction_pipeline_records": 462,
    "entities_by_kind": {"campus": 474, "project": 431},
    "evidence_records": 586,
    "resolution_candidates": 7,
    "source_family_entries": 348,
    "source_scoped_entity_records": 905,
}
EXPECTED_COUNTS = {
    "capacity_estimates": 1328,
    "construction_pipeline_records": 6712,
    "evidence_records": 13599,
    "non_review_construction_pipeline_records": 582,
    "non_review_source_scoped_entity_records": 10200,
    "release_bundles": 3,
    "resolution_candidates": 100412,
    "review_only_construction_pipeline_records": 6130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6130,
    "source_family_entries": 355,
    "source_scoped_entity_records": 16330,
    "unique_physical_sites": None,
}
EXPECTED_DELTA = {
    "capacity_estimates": 8,
    "construction_pipeline_records": 42,
    "evidence_records": 66,
    "non_review_construction_pipeline_records": 42,
    "non_review_source_scoped_entity_records": 87,
    "release_bundles": 0,
    "resolution_candidates": 0,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 54,
    "source_scoped_entity_records": 87,
}

CHILDREN = {
    NEW_RELEASE_ID: V83_RELEASE,
    "global-open-v3": ROOT / "releases/2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases/2026-07-18-osm-fuzzy-review-v2",
}


class FederationV34Error(RuntimeError):
    """Raised when v34 lineage, counts, or publication differs."""


def _canonical_json(value: Any, *, sort_keys: bool = True) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=sort_keys, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise FederationV34Error(f"bundle contains symlink: {relative}")
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
        elif path.is_file():
            raw = path.read_bytes()
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{hashlib.sha256(raw).hexdigest()}\n"
                ).encode()
            )
        else:
            raise FederationV34Error(f"unsupported bundle entry: {relative}")
    return digest.hexdigest()


def _validate_file(path: Path, pin: tuple[int, str], *, mode: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise FederationV34Error(f"expected ordinary frozen file: {path}")
    raw = path.read_bytes()
    if (len(raw), hashlib.sha256(raw).hexdigest()) != pin:
        raise FederationV34Error(f"frozen file pin differs: {path}")
    if stat.S_IMODE(path.stat().st_mode) != mode:
        raise FederationV34Error(f"frozen file mode differs: {path}")
    return raw


def _validate_tree(path: Path, expected: str) -> None:
    if (
        path.is_symlink()
        or not path.is_dir()
        or stat.S_IMODE(path.stat().st_mode) != 0o555
        or tree_digest(path) != expected
    ):
        raise FederationV34Error(f"frozen tree pin differs: {path}")
    for member in path.rglob("*"):
        expected_mode = 0o555 if member.is_dir() else 0o444
        if member.is_symlink() or stat.S_IMODE(member.stat().st_mode) != expected_mode:
            raise FederationV34Error(f"frozen tree member differs: {member}")


def _validate_inputs() -> tuple[dict[str, Any], Mapping[str, Any]]:
    base_raw = _validate_file(BASE_DEFINITION, BASE_DEFINITION_PIN, mode=0o444)
    base_definition = json.loads(base_raw)
    if base_raw != _canonical_json(base_definition):
        raise FederationV34Error("accepted v33 definition is not canonical")
    _validate_file(
        BASE_INDEX_DIR / federation.MANIFEST_FILENAME,
        BASE_MANIFEST_PIN,
        mode=0o444,
    )
    _validate_tree(BASE_INDEX_DIR, BASE_TREE_SHA256)
    base_index = base.validate_federation_v33()
    if base_index.get("counts") != base.EXPECTED_COUNTS:
        raise FederationV34Error("accepted v33 counts differ")

    v83_raw = _validate_file(V83_DEFINITION, V83_DEFINITION_PIN, mode=0o444)
    v83 = json.loads(v83_raw)
    if (
        v83_raw != _canonical_json(v83, sort_keys=False)
        or v83.get("release_id") != "2026-07-21-open-seed-v83"
        or v83.get("build", {}).get("recorded_at") != V83_RECORDED_AT
        or len(v83.get("curated_inputs", ())) != 441
    ):
        raise FederationV34Error("accepted v83 definition contract differs")
    _validate_file(
        V83_RELEASE / federation.MANIFEST_FILENAME,
        V83_MANIFEST_PIN,
        mode=0o444,
    )
    _validate_tree(V83_RELEASE, V83_TREE_SHA256)
    child = legacy._ChildDefinition(
        release_id=NEW_RELEASE_ID,
        release_path=V83_RELEASE,
        reference="../../releases/2026-07-21-open-seed-v83/",
        expected_manifest_sha256=V83_MANIFEST_PIN[1],
        license_expression=LICENSE_EXPRESSION,
        rights_notice=RIGHTS_NOTICE,
    )
    descriptor = federation._inspect_child(child)
    if descriptor["counts"] != EXPECTED_OPEN_COUNTS:
        raise FederationV34Error("accepted v83 child counts differ")
    manifest = descriptor["manifest"]
    if (
        manifest.get("recorded_at") != V83_RECORDED_AT
        or manifest.get("current_status_inferred") is not False
        or manifest.get("lifecycle_status_semantics") != "last_observed"
        or manifest.get("lifecycle_freshness_records") != 506
    ):
        raise FederationV34Error("accepted v83 current-status guardrail differs")
    return base_definition, base_index


def build_definition() -> bytes:
    accepted, _ = _validate_inputs()
    definition = deepcopy(accepted)
    definition["generated_at"] = GENERATED_AT
    matches = [
        row for row in definition["children"] if row["release_id"] == OLD_RELEASE_ID
    ]
    if len(matches) != 1:
        raise FederationV34Error("accepted v33 open child differs")
    matches[0].update(
        {
            "expected_manifest_sha256": V83_MANIFEST_PIN[1],
            "reference": "../../releases/2026-07-21-open-seed-v83/",
            "release_id": NEW_RELEASE_ID,
            "release_path": "../releases/2026-07-21-open-seed-v83",
        }
    )
    if {row["release_id"] for row in definition["children"]} != (
        UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID}
    ):
        raise FederationV34Error("v34 child set differs")
    return _canonical_json(definition)


def _validate_counts(index: Mapping[str, Any], accepted: Mapping[str, Any]) -> None:
    if index.get("counts") != EXPECTED_COUNTS:
        raise FederationV34Error("v34 aggregate counts differ")
    delta = {
        key: index["counts"][key] - accepted["counts"][key]
        for key in EXPECTED_DELTA
    }
    if delta != EXPECTED_DELTA:
        raise FederationV34Error("v34 aggregate delta differs")
    by_id = {row["release_id"]: row for row in index["releases"]}
    accepted_by_id = {row["release_id"]: row for row in accepted["releases"]}
    if set(by_id) != UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID}:
        raise FederationV34Error("v34 release set differs")
    if any(
        by_id[release_id] != accepted_by_id[release_id]
        for release_id in UNCHANGED_RELEASE_IDS
    ):
        raise FederationV34Error("v34 changed an inherited child descriptor")
    child = by_id[NEW_RELEASE_ID]
    if child["counts"] != EXPECTED_OPEN_COUNTS:
        raise FederationV34Error("v34 v83 descriptor counts differ")
    manifest = child["manifest"]
    if (
        manifest.get("current_status_inferred") is not False
        or manifest.get("lifecycle_status_semantics") != "last_observed"
        or manifest.get("lifecycle_freshness_records") != 506
    ):
        raise FederationV34Error("v34 inferred a current status")
    if index["counts"]["unique_physical_sites"] is not None:
        raise FederationV34Error("v34 asserted a unique-site count")


def _generated_at() -> datetime:
    return datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00"))


def _validate_stage_times(definition: Path, bundle: Path) -> None:
    target = _generated_at()
    for path in (definition, bundle, *bundle.rglob("*")):
        details = path.stat()
        born = datetime.fromtimestamp(
            getattr(details, "st_birthtime", details.st_ctime), UTC
        )
        modified = datetime.fromtimestamp(details.st_mtime, UTC)
        if max(born, modified) > target:
            raise FederationV34Error(f"v34 staged bytes post-date generated_at: {path}")


def _wait_until_generated() -> None:
    target = _generated_at()
    while True:
        remaining = (target - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise FederationV34Error("active v34 publication lock exists") from error
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        yield
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if PUBLICATION_LOCK.exists() and not PUBLICATION_LOCK.is_symlink():
            PUBLICATION_LOCK.unlink()


def _validate_exact_definition(path: Path) -> bytes:
    expected = build_definition()
    raw = _validate_file(path, DEFINITION_PIN, mode=0o444)
    if (
        raw != expected
        or (len(expected), hashlib.sha256(expected).hexdigest()) != DEFINITION_PIN
    ):
        raise FederationV34Error("v34 definition differs")
    return raw


def validate_federation_v34() -> Mapping[str, Any]:
    _validate_exact_definition(DEFINITION)
    _, accepted = _validate_inputs()
    for filename, pin in (
        (federation.INDEX_FILENAME, INDEX_PIN),
        (federation.MANIFEST_FILENAME, MANIFEST_PIN),
        (federation.MANIFEST_HASH_FILENAME, SIDECAR_PIN),
    ):
        _validate_file(INDEX_DIR / filename, pin, mode=0o444)
    _validate_tree(INDEX_DIR, TREE_SHA256)
    index = federation.validate_federated_release_index(
        INDEX_DIR, child_release_paths=CHILDREN
    )
    rebuilt = federation.build_federated_release_index(DEFINITION)
    expected_files = federation._bundle_payloads(rebuilt)
    if any(
        (INDEX_DIR / name).read_bytes() != raw
        for name, raw in expected_files.items()
    ):
        raise FederationV34Error("v34 bundle is not exactly reproducible")
    _validate_counts(index, accepted)
    target = _generated_at()
    for path in (DEFINITION, INDEX_DIR):
        if datetime.fromtimestamp(path.stat().st_ctime, UTC) < target:
            raise FederationV34Error(f"v34 final root predates generated_at: {path}")
    return index


def _rollback_bundle(staged_bundle: Path) -> None:
    if staged_bundle.exists() or staged_bundle.is_symlink():
        raise FederationV34Error("v34 rollback destination is occupied")
    INDEX_DIR.chmod(0o755)
    federation._promote_noreplace(INDEX_DIR, staged_bundle)
    staged_bundle.chmod(0o555)


def build_and_publish_federation_v34() -> Mapping[str, Any]:
    if (
        DEFINITION.exists()
        or DEFINITION.is_symlink()
        or INDEX_DIR.exists()
        or INDEX_DIR.is_symlink()
    ):
        raise FederationV34Error("v34 final path collision; refusing publication")
    if _generated_at() <= datetime.now(UTC):
        raise FederationV34Error("v34 generated_at must be future before staging")
    definition_raw = build_definition()
    with _publication_lock():
        stage_root = Path(
            tempfile.mkdtemp(prefix=".federation-v34-private-stage-", dir=ROOT)
        )
        stage_root.chmod(0o700)
        staged_definition = stage_root / DEFINITION.name
        staged_bundle = stage_root / INDEX_DIR.name
        published_bundle = False
        published_definition = False
        bundle_members: dict[str, bytes] = {}
        try:
            legacy._write_bytes(staged_definition, definition_raw)
            staged_definition.chmod(0o444)
            federation.write_federated_release_index(staged_definition, staged_bundle)
            _validate_stage_times(staged_definition, staged_bundle)
            frozen_definition = staged_definition.read_bytes()
            frozen_tree = tree_digest(staged_bundle)
            if (
                (len(frozen_definition), hashlib.sha256(frozen_definition).hexdigest())
                != DEFINITION_PIN
                or frozen_tree != TREE_SHA256
            ):
                raise FederationV34Error("v34 private stage pins differ")
            bundle_members = {
                path.name: path.read_bytes() for path in staged_bundle.iterdir()
            }
            _wait_until_generated()
            if (
                staged_definition.read_bytes() != frozen_definition
                or tree_digest(staged_bundle) != frozen_tree
                or any(
                    (staged_bundle / name).read_bytes() != raw
                    for name, raw in bundle_members.items()
                )
            ):
                raise FederationV34Error("v34 private stage changed while waiting")
            _validate_stage_times(staged_definition, staged_bundle)
            publication.validate_prepublication_boundary(
                staged_definition,
                DEFINITION,
                INDEX_DIR,
                staged_bundle=staged_bundle,
            )

            staged_bundle.chmod(0o755)
            federation._promote_noreplace(staged_bundle, INDEX_DIR)
            published_bundle = True
            INDEX_DIR.chmod(0o555)
            try:
                federation._promote_noreplace(staged_definition, DEFINITION)
                published_definition = True
            except Exception:
                _rollback_bundle(staged_bundle)
                published_bundle = False
                raise

            _, accepted = _validate_inputs()
            index = federation.validate_federated_release_index(
                INDEX_DIR, child_release_paths=CHILDREN
            )
            _validate_counts(index, accepted)
            return validate_federation_v34()
        finally:
            if not published_definition and staged_definition.exists():
                staged_definition.chmod(0o600)
                staged_definition.unlink()
            if not published_bundle and staged_bundle.exists():
                staged_bundle.chmod(0o700)
                for path in staged_bundle.iterdir():
                    path.chmod(0o600)
                shutil.rmtree(staged_bundle)
            if stage_root.exists():
                stage_root.rmdir()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--verify", action="store_true")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    index = (
        validate_federation_v34()
        if arguments.verify
        else build_and_publish_federation_v34()
    )
    print(
        json.dumps(
            {
                "counts": index["counts"],
                "definition": str(DEFINITION.resolve()),
                "federated_index": str(INDEX_DIR.resolve()),
                "generated_at": GENERATED_AT,
                "release_ids": [row["release_id"] for row in index["releases"]],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFINITION",
    "EXPECTED_COUNTS",
    "EXPECTED_DELTA",
    "EXPECTED_OPEN_COUNTS",
    "FederationV34Error",
    "GENERATED_AT",
    "INDEX_DIR",
    "build_and_publish_federation_v34",
    "build_definition",
    "main",
    "tree_digest",
    "validate_federation_v34",
]
