"""Publish the exact v31-to-v32 federation successor for open seed v73."""

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


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v31.json"
BASE_INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v31"
V73_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v73.json"
V73_RELEASE = ROOT / "releases/2026-07-21-open-seed-v73"
DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v32.json"
INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v32"
PUBLICATION_LOCK = ROOT / ".federation-v32.lock"

GENERATED_AT = "2026-07-21T13:21:00Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v71"
NEW_RELEASE_ID = "epoch-official-open-seed-v73"
UNCHANGED_RELEASE_IDS = frozenset({"global-open-v3", "osm-fuzzy-review-v2"})

BASE_DEFINITION_PIN = (
    1_788,
    "83a878ee72563e6572a53cf09236c0af469e629bc04482401d6891b54d108ee1",
)
BASE_MANIFEST_PIN = (
    986,
    "7adc941dd73fa33315322ce19ff9c9887cdc2fb80cbd0aca3385a1c005781101",
)
BASE_TREE_SHA256 = "978b1a574071f0128538aafee4503436fd0ae95284a60e236b0ee9065834f55c"
V73_DEFINITION_PIN = (
    88_004,
    "cf8a4cfb8861ab732cdb9e72a01cbdd01d0e435102c47fd6d92bc30ebf11f97d",
)
V73_MANIFEST_PIN = (
    12_814,
    "229c572759ab493448b788946a0c8a61ff6995d0ab505bea2af08860a19e204d",
)
V73_TREE_SHA256 = "692583b86324b746fd6edf0ec2dc5101efa86ce0f08e04831e0d471e767a6394"

LICENSE_EXPRESSION = (
    "CC-BY-4.0 data plus source-linked factual claims from official company, "
    "government, utility, and exchange disclosures under source-specific terms"
)
RIGHTS_NOTICE = (
    "Epoch data is CC BY 4.0; official-source evidence remains source-linked "
    "and no underlying copyrighted page, filing, announcement, permit, or "
    "other source content is relicensed."
)

EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 534,
    "construction_pipeline_records": 420,
    "entities_by_kind": {"campus": 431, "project": 387},
    "evidence_records": 520,
    "resolution_candidates": 7,
    "source_family_entries": 294,
    "source_scoped_entity_records": 818,
}
EXPECTED_COUNTS = {
    "capacity_estimates": 1320,
    "construction_pipeline_records": 6670,
    "evidence_records": 13533,
    "non_review_construction_pipeline_records": 540,
    "non_review_source_scoped_entity_records": 10113,
    "release_bundles": 3,
    "resolution_candidates": 100412,
    "review_only_construction_pipeline_records": 6130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6130,
    "source_family_entries": 301,
    "source_scoped_entity_records": 16243,
    "unique_physical_sites": None,
}
EXPECTED_DELTA = {
    "capacity_estimates": 2,
    "construction_pipeline_records": 4,
    "evidence_records": 8,
    "non_review_construction_pipeline_records": 4,
    "non_review_source_scoped_entity_records": 8,
    "release_bundles": 0,
    "resolution_candidates": 1,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 6,
    "source_scoped_entity_records": 8,
}

CHILDREN = {
    NEW_RELEASE_ID: V73_RELEASE,
    "global-open-v3": ROOT / "releases/2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases/2026-07-18-osm-fuzzy-review-v2",
}


class FederationV32Error(RuntimeError):
    """Raised when the v32 lineage or publication contract differs."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise FederationV32Error(f"bundle contains symlink: {relative}")
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
            raise FederationV32Error(f"unsupported bundle entry: {relative}")
    return digest.hexdigest()


def _validate_file(path: Path, pin: tuple[int, str], *, mode: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise FederationV32Error(f"expected ordinary frozen file: {path}")
    raw = path.read_bytes()
    if (len(raw), hashlib.sha256(raw).hexdigest()) != pin:
        raise FederationV32Error(f"frozen file pin differs: {path}")
    if stat.S_IMODE(path.stat().st_mode) != mode:
        raise FederationV32Error(f"frozen file mode differs: {path}")
    return raw


def _validate_tree(path: Path, expected: str) -> None:
    if (
        path.is_symlink()
        or not path.is_dir()
        or stat.S_IMODE(path.stat().st_mode) != 0o555
        or tree_digest(path) != expected
    ):
        raise FederationV32Error(f"frozen tree pin differs: {path}")
    for member in path.rglob("*"):
        expected_mode = 0o555 if member.is_dir() else 0o444
        if member.is_symlink() or stat.S_IMODE(member.stat().st_mode) != expected_mode:
            raise FederationV32Error(f"frozen tree member differs: {member}")


def _validate_inputs() -> tuple[dict[str, Any], Mapping[str, Any]]:
    base_raw = _validate_file(BASE_DEFINITION, BASE_DEFINITION_PIN, mode=0o444)
    base = json.loads(base_raw)
    if base_raw != _canonical_json(base):
        raise FederationV32Error("accepted v31 definition is not canonical")
    _validate_file(
        BASE_INDEX_DIR / federation.MANIFEST_FILENAME,
        BASE_MANIFEST_PIN,
        mode=0o444,
    )
    _validate_tree(BASE_INDEX_DIR, BASE_TREE_SHA256)
    base_index = federation.validate_federated_release_index(BASE_INDEX_DIR)

    v73_raw = _validate_file(V73_DEFINITION, V73_DEFINITION_PIN, mode=0o444)
    v73 = json.loads(v73_raw)
    if (
        v73_raw != _canonical_json(v73)
        or v73.get("release_id") != "2026-07-21-open-seed-v73"
        or v73.get("build", {}).get("recorded_at") != "2026-07-21T13:15:51Z"
    ):
        raise FederationV32Error("accepted v73 definition contract differs")
    _validate_file(
        V73_RELEASE / federation.MANIFEST_FILENAME,
        V73_MANIFEST_PIN,
        mode=0o444,
    )
    _validate_tree(V73_RELEASE, V73_TREE_SHA256)
    child = legacy._ChildDefinition(
        release_id=NEW_RELEASE_ID,
        release_path=V73_RELEASE,
        reference="../../releases/2026-07-21-open-seed-v73/",
        expected_manifest_sha256=V73_MANIFEST_PIN[1],
        license_expression=LICENSE_EXPRESSION,
        rights_notice=RIGHTS_NOTICE,
    )
    descriptor = federation._inspect_child(child)
    if descriptor["counts"] != EXPECTED_OPEN_COUNTS:
        raise FederationV32Error("accepted v73 child counts differ")
    manifest = descriptor["manifest"]
    if (
        manifest.get("current_status_inferred") is not False
        or manifest.get("lifecycle_status_semantics") != "last_observed"
        or manifest.get("lifecycle_freshness_records") != 462
    ):
        raise FederationV32Error("accepted v73 current-status guardrail differs")
    return base, base_index


def build_definition() -> bytes:
    base, _ = _validate_inputs()
    definition = deepcopy(base)
    definition["generated_at"] = GENERATED_AT
    matches = [
        row for row in definition["children"] if row["release_id"] == OLD_RELEASE_ID
    ]
    if len(matches) != 1:
        raise FederationV32Error("accepted v31 open child differs")
    matches[0].update(
        {
            "expected_manifest_sha256": V73_MANIFEST_PIN[1],
            "reference": "../../releases/2026-07-21-open-seed-v73/",
            "release_id": NEW_RELEASE_ID,
            "release_path": "../releases/2026-07-21-open-seed-v73",
        }
    )
    if {row["release_id"] for row in definition["children"]} != (
        UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID}
    ):
        raise FederationV32Error("v32 child set differs")
    return _canonical_json(definition)


def _validate_counts(index: Mapping[str, Any], base: Mapping[str, Any]) -> None:
    if index.get("counts") != EXPECTED_COUNTS:
        raise FederationV32Error("v32 aggregate counts differ")
    delta = {
        key: index["counts"][key] - base["counts"][key] for key in EXPECTED_DELTA
    }
    if delta != EXPECTED_DELTA:
        raise FederationV32Error("v32 aggregate delta differs")
    by_id = {row["release_id"]: row for row in index["releases"]}
    base_by_id = {row["release_id"]: row for row in base["releases"]}
    if set(by_id) != UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID}:
        raise FederationV32Error("v32 release set differs")
    if any(by_id[release_id] != base_by_id[release_id] for release_id in UNCHANGED_RELEASE_IDS):
        raise FederationV32Error("v32 changed an inherited child descriptor")
    if by_id[NEW_RELEASE_ID]["counts"] != EXPECTED_OPEN_COUNTS:
        raise FederationV32Error("v32 v73 descriptor counts differ")
    if by_id[NEW_RELEASE_ID]["manifest"]["current_status_inferred"] is not False:
        raise FederationV32Error("v32 inferred a current status")
    if index["counts"]["unique_physical_sites"] is not None:
        raise FederationV32Error("v32 asserted a unique-site count")


def _generated_at() -> datetime:
    return datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00"))


def _validate_stage_times(definition: Path, bundle: Path) -> None:
    generated = _generated_at()
    for path in (definition, bundle, *bundle.rglob("*")):
        details = path.stat()
        born = datetime.fromtimestamp(
            getattr(details, "st_birthtime", details.st_ctime), UTC
        )
        modified = datetime.fromtimestamp(details.st_mtime, UTC)
        if max(born, modified) > generated:
            raise FederationV32Error(f"v32 stage post-dates generated_at: {path}")


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
        descriptor = os.open(PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise FederationV32Error("active v32 publication lock exists") from error
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


def validate_federation_v32() -> Mapping[str, Any]:
    expected_definition = build_definition()
    if _validate_file(
        DEFINITION,
        (len(expected_definition), hashlib.sha256(expected_definition).hexdigest()),
        mode=0o444,
    ) != expected_definition:
        raise FederationV32Error("published v32 definition differs")
    _, base = _validate_inputs()
    index = federation.validate_federated_release_index(
        INDEX_DIR, child_release_paths=CHILDREN
    )
    rebuilt = federation.build_federated_release_index(DEFINITION)
    expected_files = federation._bundle_payloads(rebuilt)
    if any((INDEX_DIR / name).read_bytes() != raw for name, raw in expected_files.items()):
        raise FederationV32Error("published v32 bundle is not reproducible")
    _validate_counts(index, base)
    generated = _generated_at()
    for path in (DEFINITION, INDEX_DIR):
        changed = datetime.fromtimestamp(path.stat().st_ctime, UTC)
        if changed < generated:
            raise FederationV32Error(f"v32 final root predates generated_at: {path}")
    return index


def build_and_publish_federation_v32() -> Mapping[str, Any]:
    if DEFINITION.exists() or DEFINITION.is_symlink() or INDEX_DIR.exists() or INDEX_DIR.is_symlink():
        raise FederationV32Error("v32 final path collision; refusing publication")
    now = datetime.now(UTC)
    if _generated_at() <= now:
        raise FederationV32Error("v32 generated_at must be future before staging")
    definition_raw = build_definition()
    with _publication_lock():
        stage_root = Path(tempfile.mkdtemp(prefix=".federation-v32-private-stage-", dir=ROOT))
        stage_root.chmod(0o700)
        staged_definition = stage_root / DEFINITION.name
        staged_bundle = stage_root / INDEX_DIR.name
        published = False
        try:
            legacy._write_bytes(staged_definition, definition_raw)
            staged_definition.chmod(0o444)
            federation.write_federated_release_index(staged_definition, staged_bundle)
            _validate_stage_times(staged_definition, staged_bundle)
            staged_tree = tree_digest(staged_bundle)
            staged_definition_raw = staged_definition.read_bytes()
            _wait_until_generated()
            if (
                staged_definition.read_bytes() != staged_definition_raw
                or tree_digest(staged_bundle) != staged_tree
            ):
                raise FederationV32Error("v32 private stage changed while waiting")
            _validate_stage_times(staged_definition, staged_bundle)
            _, base = _validate_inputs()
            index = publication.publish_staged_federation(
                staged_definition,
                staged_bundle,
                DEFINITION,
                INDEX_DIR,
                child_release_paths=CHILDREN,
            )
            published = True
            _validate_counts(index, base)
            return validate_federation_v32()
        finally:
            if not published and stage_root.exists() and not stage_root.is_symlink():
                for path in sorted(stage_root.rglob("*"), reverse=True):
                    if path.is_dir():
                        path.chmod(0o700)
                    elif path.is_file():
                        path.chmod(0o600)
                shutil.rmtree(stage_root)
            elif published and stage_root.exists():
                stage_root.rmdir()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--verify",
        action="store_true",
        help="validate the frozen publication instead of attempting publication",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    index = validate_federation_v32() if arguments.verify else build_and_publish_federation_v32()
    print(
        json.dumps(
            {
                "definition": str(DEFINITION.resolve()),
                "federated_index": str(INDEX_DIR.resolve()),
                "generated_at": GENERATED_AT,
                "counts": index["counts"],
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
    "FederationV32Error",
    "GENERATED_AT",
    "INDEX_DIR",
    "build_and_publish_federation_v32",
    "build_definition",
    "main",
    "tree_digest",
    "validate_federation_v32",
]
