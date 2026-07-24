"""Publish the strict v34-to-v35 federation successor for open seed v86."""

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
from . import federated_release_v4 as federation
from . import federation_v34 as base


ROOT = base.ROOT
BASE_DEFINITION = base.DEFINITION
BASE_INDEX_DIR = base.INDEX_DIR
V86_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v86.json"
V86_RELEASE = ROOT / "releases/2026-07-21-open-seed-v86"
DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v35.json"
INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v35"
PUBLICATION_LOCK = ROOT / ".federation-v35.lock"

GENERATED_AT = "2026-07-21T20:45:00Z"
V86_RECORDED_AT = "2026-07-21T20:19:16Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v83"
NEW_RELEASE_ID = "epoch-official-open-seed-v86"
UNCHANGED_RELEASE_IDS = frozenset({"global-open-v3", "osm-fuzzy-review-v2"})

BASE_DEFINITION_PIN = (
    1_788,
    "f01622e680fac69a3fc1ad78151d56cf5cd5b412a28efea91e998fceba367a82",
)
BASE_MANIFEST_PIN = (
    986,
    "31f2d60f266045f01af510f9fc16e541642231697167f3feaf3a70012a376503",
)
BASE_TREE_SHA256 = "a65ae68300e8a6a5a4446e7b264485fcc850d96900de047c960370e57df46bf2"
V86_DEFINITION_PIN = (
    102_240,
    "2a2f0cded9e95efd2ab90cbde1d8ad11306b14f019f42cb14086fb80a63fb25d",
)
V86_MANIFEST_PIN = (
    15_531,
    "5bc24a692e2d4fc793192f03bd23fa921e434661a0675e6612370d354cf11488",
)
V86_TREE_SHA256 = "593fe37f16cc81bd6e2011c9b893251be4041dc54376ffec2f743a510fb4d4de"

DEFINITION_PIN = (
    1_788,
    "7c6f9c3d7892d86974b20ba694c24695c0a0d9a4fd91d830e9824ad2db49903f",
)
INDEX_PIN = (
    36_400,
    "f7cf31d905bf497a6bc7ba3db7f22fb8e281e7b1452e1f2853ea79af1d9ea802",
)
MANIFEST_PIN = (
    986,
    "7396e2854abd73f0209a02f13ab5b31fa79af6250059b92dff484442d61fe388",
)
SIDECAR_PIN = (
    80,
    "52def2639a47b81caaa2813a19cff9b5c6ca1c6de125bdb0c3897198ed86cd3b",
)
TREE_SHA256 = "37bb03f650d2d57823fbc226c471866a4997711ef201440d10dbc4ef6c14f5ba"

LICENSE_EXPRESSION = base.LICENSE_EXPRESSION
RIGHTS_NOTICE = base.RIGHTS_NOTICE

EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 552,
    "construction_pipeline_records": 469,
    "entities_by_kind": {"campus": 485, "project": 442},
    "evidence_records": 611,
    "resolution_candidates": 9,
    "source_family_entries": 366,
    "source_scoped_entity_records": 927,
}
EXPECTED_COUNTS = {
    "capacity_estimates": 1338,
    "construction_pipeline_records": 6719,
    "evidence_records": 13624,
    "non_review_construction_pipeline_records": 589,
    "non_review_source_scoped_entity_records": 10222,
    "release_bundles": 3,
    "resolution_candidates": 100414,
    "review_only_construction_pipeline_records": 6130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6130,
    "source_family_entries": 373,
    "source_scoped_entity_records": 16352,
    "unique_physical_sites": None,
}
EXPECTED_DELTA = {
    "capacity_estimates": 10,
    "construction_pipeline_records": 7,
    "evidence_records": 25,
    "non_review_construction_pipeline_records": 7,
    "non_review_source_scoped_entity_records": 22,
    "release_bundles": 0,
    "resolution_candidates": 2,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 18,
    "source_scoped_entity_records": 22,
}

CHILDREN = {
    NEW_RELEASE_ID: V86_RELEASE,
    "global-open-v3": ROOT / "releases/2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases/2026-07-18-osm-fuzzy-review-v2",
}


class FederationV35Error(RuntimeError):
    """Raised when v35 lineage, counts, or publication differs."""


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
            raise FederationV35Error(f"bundle contains symlink: {relative}")
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
            raise FederationV35Error(f"unsupported bundle entry: {relative}")
    return digest.hexdigest()


def _validate_file(path: Path, pin: tuple[int, str], *, mode: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise FederationV35Error(f"expected ordinary frozen file: {path}")
    raw = path.read_bytes()
    if (len(raw), hashlib.sha256(raw).hexdigest()) != pin:
        raise FederationV35Error(f"frozen file pin differs: {path}")
    if stat.S_IMODE(path.stat().st_mode) != mode:
        raise FederationV35Error(f"frozen file mode differs: {path}")
    return raw


def _validate_tree(path: Path, expected: str) -> None:
    if (
        path.is_symlink()
        or not path.is_dir()
        or stat.S_IMODE(path.stat().st_mode) != 0o555
        or tree_digest(path) != expected
    ):
        raise FederationV35Error(f"frozen tree pin differs: {path}")
    for member in path.rglob("*"):
        expected_mode = 0o555 if member.is_dir() else 0o444
        if member.is_symlink() or stat.S_IMODE(member.stat().st_mode) != expected_mode:
            raise FederationV35Error(f"frozen tree member differs: {member}")


def _validate_inputs() -> tuple[dict[str, Any], Mapping[str, Any]]:
    base_raw = _validate_file(BASE_DEFINITION, BASE_DEFINITION_PIN, mode=0o444)
    base_definition = json.loads(base_raw)
    if base_raw != _canonical_json(base_definition):
        raise FederationV35Error("accepted v34 definition is not canonical")
    _validate_file(
        BASE_INDEX_DIR / federation.MANIFEST_FILENAME,
        BASE_MANIFEST_PIN,
        mode=0o444,
    )
    _validate_tree(BASE_INDEX_DIR, BASE_TREE_SHA256)
    base_index = base.validate_federation_v34()
    if base_index.get("counts") != base.EXPECTED_COUNTS:
        raise FederationV35Error("accepted v34 counts differ")

    v86_raw = _validate_file(V86_DEFINITION, V86_DEFINITION_PIN, mode=0o444)
    v86 = json.loads(v86_raw)
    if (
        v86_raw != _canonical_json(v86, sort_keys=False)
        or v86.get("release_id") != "2026-07-21-open-seed-v86"
        or v86.get("build", {}).get("recorded_at") != V86_RECORDED_AT
        or len(v86.get("curated_inputs", ())) != 452
    ):
        raise FederationV35Error("accepted v86 definition contract differs")
    _validate_file(
        V86_RELEASE / federation.MANIFEST_FILENAME,
        V86_MANIFEST_PIN,
        mode=0o444,
    )
    _validate_tree(V86_RELEASE, V86_TREE_SHA256)
    child = legacy._ChildDefinition(
        release_id=NEW_RELEASE_ID,
        release_path=V86_RELEASE,
        reference="../../releases/2026-07-21-open-seed-v86/",
        expected_manifest_sha256=V86_MANIFEST_PIN[1],
        license_expression=LICENSE_EXPRESSION,
        rights_notice=RIGHTS_NOTICE,
    )
    descriptor = federation._inspect_child(child)
    if descriptor["counts"] != EXPECTED_OPEN_COUNTS:
        raise FederationV35Error("accepted v86 child counts differ")
    manifest = descriptor["manifest"]
    if (
        manifest.get("recorded_at") != V86_RECORDED_AT
        or manifest.get("current_status_inferred") is not False
        or manifest.get("lifecycle_status_semantics") != "last_observed"
        or manifest.get("lifecycle_freshness_records") != 517
        or manifest.get(federation.GEOMETRY_NON_INFERENCE_FIELD) is not False
    ):
        raise FederationV35Error("accepted v86 current-status guardrail differs")
    return base_definition, base_index


def build_definition() -> bytes:
    accepted, _ = _validate_inputs()
    definition = deepcopy(accepted)
    definition["generated_at"] = GENERATED_AT
    matches = [
        row for row in definition["children"] if row["release_id"] == OLD_RELEASE_ID
    ]
    if len(matches) != 1:
        raise FederationV35Error("accepted v34 open child differs")
    matches[0].update(
        {
            "expected_manifest_sha256": V86_MANIFEST_PIN[1],
            "reference": "../../releases/2026-07-21-open-seed-v86/",
            "release_id": NEW_RELEASE_ID,
            "release_path": "../releases/2026-07-21-open-seed-v86",
        }
    )
    if {row["release_id"] for row in definition["children"]} != (
        UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID}
    ):
        raise FederationV35Error("v35 child set differs")
    return _canonical_json(definition)


def _validate_counts(index: Mapping[str, Any], accepted: Mapping[str, Any]) -> None:
    if index.get("counts") != EXPECTED_COUNTS:
        raise FederationV35Error("v35 aggregate counts differ")
    delta = {
        key: index["counts"][key] - accepted["counts"][key]
        for key in EXPECTED_DELTA
    }
    if delta != EXPECTED_DELTA:
        raise FederationV35Error("v35 aggregate delta differs")
    by_id = {row["release_id"]: row for row in index["releases"]}
    accepted_by_id = {row["release_id"]: row for row in accepted["releases"]}
    if set(by_id) != UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID}:
        raise FederationV35Error("v35 release set differs")
    if any(
        by_id[release_id] != accepted_by_id[release_id]
        for release_id in UNCHANGED_RELEASE_IDS
    ):
        raise FederationV35Error("v35 changed an inherited child descriptor")
    child = by_id[NEW_RELEASE_ID]
    if child["counts"] != EXPECTED_OPEN_COUNTS:
        raise FederationV35Error("v35 v86 descriptor counts differ")
    manifest = child["manifest"]
    if (
        manifest.get("current_status_inferred") is not False
        or manifest.get("lifecycle_status_semantics") != "last_observed"
        or manifest.get("lifecycle_freshness_records") != 517
        or manifest.get(federation.GEOMETRY_NON_INFERENCE_FIELD) is not False
    ):
        raise FederationV35Error("v35 inferred a current status")
    if index["counts"]["unique_physical_sites"] is not None:
        raise FederationV35Error("v35 asserted a unique-site count")


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
            raise FederationV35Error(f"v35 staged bytes post-date generated_at: {path}")


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
        raise FederationV35Error("active v35 publication lock exists") from error
    lock_stat = os.fstat(descriptor)
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        yield
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            current = PUBLICATION_LOCK.lstat()
        except FileNotFoundError:
            pass
        else:
            if (
                stat.S_ISREG(current.st_mode)
                and current.st_dev == lock_stat.st_dev
                and current.st_ino == lock_stat.st_ino
            ):
                PUBLICATION_LOCK.unlink()


def _validate_exact_definition(path: Path) -> bytes:
    expected = build_definition()
    raw = _validate_file(path, DEFINITION_PIN, mode=0o444)
    if (
        raw != expected
        or (len(expected), hashlib.sha256(expected).hexdigest()) != DEFINITION_PIN
    ):
        raise FederationV35Error("v35 definition differs")
    return raw


def _validate_offline_replays(definition: Path, bundle: Path) -> None:
    frozen = {path.name: path.read_bytes() for path in bundle.iterdir()}
    replay_payloads: list[dict[str, bytes]] = []
    for _ in range(2):
        replay = federation._bundle_payloads(
            federation.build_federated_release_index(definition)
        )
        if replay != frozen:
            raise FederationV35Error("v35 offline replay differs from private stage")
        replay_payloads.append(replay)
    if replay_payloads[0] != replay_payloads[1]:
        raise FederationV35Error("v35 offline replays differ")


def _validate_prepublication_boundary(
    staged_definition: Path, staged_bundle: Path
) -> None:
    raw = legacy._regular_bytes(staged_definition, "staged federation definition")
    document = legacy._json_object(raw, "staged federation definition")
    if raw != legacy._canonical_json(document):
        raise FederationV35Error("staged federation definition is not canonical")
    if set(document) != {"children", "generated_at", "schema_version"}:
        raise FederationV35Error("staged federation definition schema differs")
    generated_at = datetime.fromisoformat(
        legacy._timestamp(
            document["generated_at"],
            "federation generated_at",
            require_canonical_utc=True,
        ).replace("Z", "+00:00")
    )
    if datetime.now(UTC) < generated_at:
        raise FederationV35Error("v35 generated_at is not yet live")
    if (
        DEFINITION.exists()
        or DEFINITION.is_symlink()
        or INDEX_DIR.exists()
        or INDEX_DIR.is_symlink()
    ):
        raise FederationV35Error("v35 final path collision; refusing publication")
    federation.validate_federated_release_index(staged_bundle)
    for path in (staged_definition, staged_bundle):
        details = path.stat()
        born = datetime.fromtimestamp(
            getattr(details, "st_birthtime", details.st_ctime), UTC
        )
        modified = datetime.fromtimestamp(details.st_mtime, UTC)
        if max(born, modified) > generated_at:
            raise FederationV35Error("v35 stage post-dates generated_at")


def validate_federation_v35() -> Mapping[str, Any]:
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
        raise FederationV35Error("v35 bundle is not exactly reproducible")
    _validate_counts(index, accepted)
    target = _generated_at()
    for path in (DEFINITION, INDEX_DIR):
        if datetime.fromtimestamp(path.stat().st_ctime, UTC) < target:
            raise FederationV35Error(f"v35 final root predates generated_at: {path}")
    return index


def _rollback_bundle(staged_bundle: Path) -> None:
    if staged_bundle.exists() or staged_bundle.is_symlink():
        raise FederationV35Error("v35 rollback destination is occupied")
    INDEX_DIR.chmod(0o755)
    federation._promote_noreplace(INDEX_DIR, staged_bundle)
    staged_bundle.chmod(0o555)


def _rollback_definition(staged_definition: Path) -> None:
    if staged_definition.exists() or staged_definition.is_symlink():
        raise FederationV35Error("v35 definition rollback destination is occupied")
    federation._promote_noreplace(DEFINITION, staged_definition)


def build_and_publish_federation_v35() -> Mapping[str, Any]:
    if (
        DEFINITION.exists()
        or DEFINITION.is_symlink()
        or INDEX_DIR.exists()
        or INDEX_DIR.is_symlink()
    ):
        raise FederationV35Error("v35 final path collision; refusing publication")
    if _generated_at() <= datetime.now(UTC):
        raise FederationV35Error("v35 generated_at must be future before staging")
    definition_raw = build_definition()
    with _publication_lock():
        stage_root = Path(
            tempfile.mkdtemp(prefix=".federation-v35-private-stage-", dir=ROOT)
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
            _validate_offline_replays(staged_definition, staged_bundle)
            _validate_stage_times(staged_definition, staged_bundle)
            frozen_definition = staged_definition.read_bytes()
            frozen_tree = tree_digest(staged_bundle)
            if (
                (len(frozen_definition), hashlib.sha256(frozen_definition).hexdigest())
                != DEFINITION_PIN
                or frozen_tree != TREE_SHA256
            ):
                raise FederationV35Error("v35 private stage pins differ")
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
                or build_definition() != frozen_definition
            ):
                raise FederationV35Error("v35 private stage or inputs changed while waiting")
            _validate_stage_times(staged_definition, staged_bundle)
            _validate_prepublication_boundary(staged_definition, staged_bundle)

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

            try:
                _, accepted = _validate_inputs()
                index = federation.validate_federated_release_index(
                    INDEX_DIR, child_release_paths=CHILDREN
                )
                _validate_counts(index, accepted)
                return validate_federation_v35()
            except Exception:
                if published_definition:
                    _rollback_definition(staged_definition)
                    published_definition = False
                if published_bundle:
                    _rollback_bundle(staged_bundle)
                    published_bundle = False
                raise
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
        validate_federation_v35()
        if arguments.verify
        else build_and_publish_federation_v35()
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
    "FederationV35Error",
    "GENERATED_AT",
    "INDEX_DIR",
    "build_and_publish_federation_v35",
    "build_definition",
    "main",
    "tree_digest",
    "validate_federation_v35",
]
