"""Publish the fresh federation successor after rejected partial v32."""

from __future__ import annotations

from contextlib import contextmanager
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
from . import federation_v32 as rejected


ROOT = rejected.ROOT
BASE_DEFINITION = rejected.BASE_DEFINITION
BASE_INDEX_DIR = rejected.BASE_INDEX_DIR
V73_DEFINITION = rejected.V73_DEFINITION
V73_RELEASE = rejected.V73_RELEASE
DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v33.json"
INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v33"
PUBLICATION_LOCK = ROOT / ".federation-v33.lock"
GENERATED_AT = "2026-07-21T13:29:00Z"

OLD_RELEASE_ID = rejected.OLD_RELEASE_ID
NEW_RELEASE_ID = rejected.NEW_RELEASE_ID
UNCHANGED_RELEASE_IDS = rejected.UNCHANGED_RELEASE_IDS
EXPECTED_OPEN_COUNTS = rejected.EXPECTED_OPEN_COUNTS
EXPECTED_COUNTS = rejected.EXPECTED_COUNTS
EXPECTED_DELTA = rejected.EXPECTED_DELTA
CHILDREN = rejected.CHILDREN


class FederationV33Error(RuntimeError):
    """Raised when fresh v33 lineage or publication differs."""


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _generated_at() -> datetime:
    return datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00"))


def build_definition() -> bytes:
    document = json.loads(rejected.build_definition())
    document["generated_at"] = GENERATED_AT
    raw = _canonical_json(document)
    if (
        {row["release_id"] for row in document["children"]}
        != UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID}
        or any("v32" in row["release_id"] for row in document["children"])
    ):
        raise FederationV33Error("v33 child set differs")
    return raw


def _validate_stage_times(definition: Path, bundle: Path) -> None:
    target = _generated_at()
    for path in (definition, bundle, *bundle.rglob("*")):
        details = path.stat()
        born = datetime.fromtimestamp(
            getattr(details, "st_birthtime", details.st_ctime), UTC
        )
        modified = datetime.fromtimestamp(details.st_mtime, UTC)
        if max(born, modified) > target:
            raise FederationV33Error(f"v33 staged bytes post-date generated_at: {path}")


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
        raise FederationV33Error("active v33 publication lock exists") from error
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
    if path.is_symlink() or not path.is_file():
        raise FederationV33Error("v33 definition must be an ordinary file")
    raw = path.read_bytes()
    if (
        raw != expected
        or stat.S_IMODE(path.stat().st_mode) != 0o444
        or (len(raw), hashlib.sha256(raw).hexdigest())
        != (len(expected), hashlib.sha256(expected).hexdigest())
    ):
        raise FederationV33Error("v33 definition differs")
    return raw


def _validate_counts(index: Mapping[str, Any], base: Mapping[str, Any]) -> None:
    try:
        rejected._validate_counts(index, base)
    except rejected.FederationV32Error as error:
        raise FederationV33Error(str(error)) from error


def validate_federation_v33() -> Mapping[str, Any]:
    _validate_exact_definition(DEFINITION)
    _, base = rejected._validate_inputs()
    index = federation.validate_federated_release_index(
        INDEX_DIR, child_release_paths=CHILDREN
    )
    rebuilt = federation.build_federated_release_index(DEFINITION)
    expected_files = federation._bundle_payloads(rebuilt)
    if any((INDEX_DIR / name).read_bytes() != raw for name, raw in expected_files.items()):
        raise FederationV33Error("v33 bundle is not exactly reproducible")
    _validate_counts(index, base)
    target = _generated_at()
    for path in (DEFINITION, INDEX_DIR):
        if datetime.fromtimestamp(path.stat().st_ctime, UTC) < target:
            raise FederationV33Error(f"v33 final root predates generated_at: {path}")
    if stat.S_IMODE(INDEX_DIR.stat().st_mode) != 0o555:
        raise FederationV33Error("v33 final bundle root is not frozen")
    return index


def _rollback_bundle(staged_bundle: Path) -> None:
    if staged_bundle.exists() or staged_bundle.is_symlink():
        raise FederationV33Error("v33 rollback destination is occupied")
    INDEX_DIR.chmod(0o755)
    federation._promote_noreplace(INDEX_DIR, staged_bundle)
    staged_bundle.chmod(0o555)


def build_and_publish_federation_v33() -> Mapping[str, Any]:
    if (
        DEFINITION.exists()
        or DEFINITION.is_symlink()
        or INDEX_DIR.exists()
        or INDEX_DIR.is_symlink()
    ):
        raise FederationV33Error("v33 final path collision; refusing publication")
    if _generated_at() <= datetime.now(UTC):
        raise FederationV33Error("v33 generated_at must be future before staging")
    definition_raw = build_definition()
    with _publication_lock():
        stage_root = Path(
            tempfile.mkdtemp(prefix=".federation-v33-private-stage-", dir=ROOT)
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
            frozen_tree = rejected.tree_digest(staged_bundle)
            bundle_members = {
                path.name: path.read_bytes() for path in staged_bundle.iterdir()
            }
            _wait_until_generated()
            if (
                staged_definition.read_bytes() != frozen_definition
                or rejected.tree_digest(staged_bundle) != frozen_tree
                or any(
                    (staged_bundle / name).read_bytes() != raw
                    for name, raw in bundle_members.items()
                )
            ):
                raise FederationV33Error("v33 private stage changed while waiting")
            _validate_stage_times(staged_definition, staged_bundle)
            publication.validate_prepublication_boundary(
                staged_definition,
                DEFINITION,
                INDEX_DIR,
                staged_bundle=staged_bundle,
            )

            # macOS renamex_np(RENAME_EXCL) returns EACCES for a 0555 source
            # directory. Only the root is opened for the atomic rename; every
            # staged byte remains in a 0444 member and is rechecked above.
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

            _, base = rejected._validate_inputs()
            index = federation.validate_federated_release_index(
                INDEX_DIR, child_release_paths=CHILDREN
            )
            _validate_counts(index, base)
            return validate_federation_v33()
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
    index = validate_federation_v33() if arguments.verify else build_and_publish_federation_v33()
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
    "FederationV33Error",
    "GENERATED_AT",
    "INDEX_DIR",
    "build_and_publish_federation_v33",
    "build_definition",
    "main",
    "validate_federation_v33",
]
