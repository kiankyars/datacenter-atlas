#!/usr/bin/env python3
"""Build the collision-isolated open-seed v49 successor exactly once."""

from __future__ import annotations

from contextlib import contextmanager
import ctypes
from dataclasses import asdict
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from typing import Iterator


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.epoch import EpochAIAdapter
from datacenter_atlas.open_seed_release import validate_open_seed_release
from datacenter_atlas.publication_release import write_release
from datacenter_atlas.service import summarize, validate_database


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v47.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v47"
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v49.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v49"
PUBLICATION_LOCK = ROOT / ".open-seed-v49.lock"

BASE_DEFINITION_SHA256 = (
    "af6d130e0139495d0569115614d8112b56b7a16a5cc158efdcf24115fc076db2"
)
BASE_MANIFEST_SHA256 = (
    "c0e228ed27e28830b466592bfc9a937f3c0d684be4fb97c7a20ac78e1c8a22a1"
)
RECORDED_AT = "2026-07-20T16:45:00Z"
MAX_SELECTED_RETRIEVED_AT = "2026-07-20T10:42:21Z"

DIGIPOWER_V1 = {
    "sources/curated-official-2026-07-20-digipower-columbiana-shell.json": (
        "7728f26d064c0ec3a47ac34aa60fdb635770a7b49e2fa90c4a0de91ca91e2ace"
    )
}

ADDITIONS = {
    "sources/curated-official-2026-07-20-coresite-de3-denver.json": (
        "8bfb0b31e468647753a142e9fc0ba3306e06e8272b02e6fbe848809a3bd69868"
    ),
    "sources/curated-official-2026-07-20-digipower-columbiana-shell-v2.json": (
        "a137bd6356ead2052ad160aa50c7ab27d7871f4b2552dba276ffa86949f46ccd"
    ),
    "sources/curated-official-2026-07-20-edged-atl01-3-atlanta-topout.json": (
        "0213438b6b2844bbad14674ed8381e3a019c3d240ef55db3625c1543a4f98c06"
    ),
    "sources/curated-official-2026-07-20-edged-ord01-2-chicago-topout.json": (
        "576e5d80846805d130dbebc50b0af8a23cbdac619ccf664dbf2421cdaeaa5a7c"
    ),
    "sources/curated-official-2026-07-20-flexential-parker-colorado-shell.json": (
        "caab2c8be10a81a8b26f2cc5acbfe3b4229dc9b8fbcbaef61028efb688fbb34a"
    ),
    "sources/curated-official-2026-07-20-goodman-ams01-amsterdam-v2.json": (
        "802d18c2dab6091add67c798064c60dbed843a0c639abc3b843adaf68d77f1a0"
    ),
    "sources/curated-official-2026-07-20-goodman-fra02-frankfurt-v2.json": (
        "2016970c6feda0ed1df7299c346713a29c86eed4088994f74fce515ddb809830"
    ),
    "sources/curated-official-2026-07-20-goodman-hkg09-kwai-chung-v2.json": (
        "e4e0f0c9db3ce6295696427e425a41cc458441cc06d9413e8b6cab50a40367d1"
    ),
    "sources/curated-official-2026-07-20-goodman-hkg10-tsuen-wan-v2.json": (
        "ce187a48475f227603a73922320a14cf03b7f6c88374830e969f5cba6d1138b9"
    ),
    "sources/curated-official-2026-07-20-goodman-lax01-los-angeles-v2.json": (
        "296b17b45a9a6f56037b137ca68f37e549607317c2550b3e606a59e640528249"
    ),
    "sources/curated-official-2026-07-20-goodman-par01-paris-v2.json": (
        "f7d558d0e0234379ae3013bd794bd878a0c70ae9ccfcefd1718ee23406c6711c"
    ),
    "sources/curated-official-2026-07-20-goodman-par02-paris-v2.json": (
        "f7e770519d244a8b57d7710c7ae1674ec2390bcd44f8d1b73d8c642adf5319c6"
    ),
    "sources/curated-official-2026-07-20-goodman-syd01-macquarie-park-v2.json": (
        "4667aea59067cd587bba475d9c42f26ac08e4edbdac058412b5a8df8a738d660"
    ),
    "sources/curated-official-2026-07-20-goodman-ty005-tokyo-v2.json": (
        "045cf3bb76bc9171ce017784562bcebab5eb5fc306c9ab017981631ce2e84764"
    ),
    "sources/curated-official-2026-07-20-goodman-ty006-tokyo-v2.json": (
        "991f66bc60af577f47d2ad0a87ce861524ab805090d0215b1ff3bf5407dffdb4"
    ),
}

EXPECTED_RELEASE_FACTS = {
    "capacity_estimates": 467,
    "construction_pipeline_records": 327,
    "construction_source_signals": 235,
    "entities": 629,
    "entities_by_kind": {"campus": 340, "project": 289},
    "evidence_records": 352,
    "resolution_candidates": 4,
}

EXPECTED_SUMMARY = {
    "entities_by_status": {
        "announced": 5,
        "civil_works": 2,
        "commissioning": 1,
        "expansion": 27,
        "foundations": 2,
        "mep_electrical": 19,
        "operational": 35,
        "permitted": 3,
        "proposed": 2,
        "shell": 23,
        "site_preparation": 12,
        "under_construction": 231,
    },
    "entities_total": 629,
    "evidence_total": 415,
    "projects_total": 289,
}

GOODMAN_V1_PATHS = {
    path.removesuffix("-v2.json") + ".json"
    for path in ADDITIONS
    if "/curated-official-2026-07-20-goodman-" in path
}
GOODMAN_V2_PATHS = {
    path
    for path in ADDITIONS
    if "/curated-official-2026-07-20-goodman-" in path
}
VNET_V1_PATHS = {
    f"sources/curated-official-2026-07-20-vnet-{slug}.json"
    for slug in (
        "e-js03b",
        "n-hb02",
        "n-hb03",
        "n-hb04",
        "n-or01",
        "n-or02a",
        "n-or02b",
        "n-or03",
    )
}
VNET_V2_PATHS = {
    path.removesuffix(".json") + "-v2.json" for path in VNET_V1_PATHS
}
OTHER_REJECTED_INPUTS = {
    "sources/curated-official-2026-07-20-hyperco-dayone-koria.json",
    "sources/curated-official-2026-07-20-teraco-jb7-isando.json",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(document: object) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


@contextmanager
def publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise SystemExit(f"active publication lock exists: {PUBLICATION_LOCK}") from error
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            PUBLICATION_LOCK.unlink()
        except FileNotFoundError:
            pass


def fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def promote_noreplace(stage: Path, destination: Path) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(stage)
    target = os.fsencode(destination)
    if sys.platform == "darwin":
        function = getattr(library, "renamex_np", None)
        if function is None:  # pragma: no cover
            raise SystemExit("atomic no-clobber publication is unavailable")
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(source, target, 0x00000004)
    elif sys.platform.startswith("linux"):
        function = getattr(library, "renameat2", None)
        if function is None:  # pragma: no cover
            raise SystemExit("atomic no-clobber publication is unavailable")
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(-100, source, -100, target, 0x00000001)
    else:  # pragma: no cover
        raise SystemExit("atomic no-clobber publication is unavailable")
    if result == 0:
        fsync_directory(destination.parent)
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise SystemExit(f"late output collision; refusing overwrite: {destination}")
    raise SystemExit(
        f"atomic no-clobber publication failed: {os.strerror(error_number)}"
    )


def discard_release_stage(stage: Path) -> None:
    if not stage.exists() or stage.is_symlink():
        return
    stage.chmod(0o700)
    for path in stage.iterdir():
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"refusing contaminated release-stage cleanup: {path}")
        path.chmod(0o600)
    shutil.rmtree(stage)


def selected_inputs(base: dict[str, object]) -> tuple[dict[str, str], list[Path]]:
    base_rows = base.get("curated_inputs")
    if not isinstance(base_rows, list):
        raise SystemExit("accepted v47 curated input inventory is invalid")
    base_pins = {row["path"]: row["sha256"] for row in base_rows}
    if len(base_pins) != 283 or len(base_pins) != len(base_rows):
        raise SystemExit(f"expected 283 unique v47 inputs, found {len(base_pins)}")
    if any(base_pins.get(path) != digest for path, digest in DIGIPOWER_V1.items()):
        raise SystemExit("accepted v47 DigiPower v1 input differs")
    if set(base_pins) & set(ADDITIONS):
        raise SystemExit("one or more v49 additions already occurs in v47")

    pins = dict(base_pins)
    for path in DIGIPOWER_V1:
        del pins[path]
    pins.update(ADDITIONS)
    if len(pins) != 297:
        raise SystemExit(f"expected 297 v49 inputs, found {len(pins)}")
    paths = sorted(pins)
    selected = set(paths)
    if selected & (GOODMAN_V1_PATHS | VNET_V1_PATHS | OTHER_REJECTED_INPUTS):
        raise SystemExit("v49 selected a rejected or superseded curated input")
    if not GOODMAN_V2_PATHS <= selected or not VNET_V2_PATHS <= selected:
        raise SystemExit("v49 is missing an accepted Goodman or VNET v2 input")
    if not any("stack-stafford-first-topout" in path for path in selected):
        raise SystemExit("v49 must retain accepted STACK Stafford")
    if set(DIGIPOWER_V1) & selected or not set(ADDITIONS) <= selected:
        raise SystemExit("v49 replacement/addition inventory changed")

    retrieved_at = [base["epoch_capture"]["retrieved_at"]]
    curated_paths: list[Path] = []
    for relative in paths:
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"input must be an ordinary file: {relative}")
        if stat.S_IMODE(path.stat().st_mode) != 0o644:
            raise SystemExit(f"input mode must be 0644: {relative}")
        if sha256(path) != pins[relative]:
            raise SystemExit(f"input hash differs: {relative}")
        document = json.loads(path.read_text(encoding="utf-8"))
        timestamps = {row["retrieved_at"] for row in document.get("evidence", [])}
        if len(timestamps) != 1:
            raise SystemExit(f"input must use one evidence retrieved_at: {relative}")
        retrieved_at.extend(timestamps)
        curated_paths.append(path)
    if max(retrieved_at) != MAX_SELECTED_RETRIEVED_AT:
        raise SystemExit(
            "selected retrieval maximum differs: "
            f"{max(retrieved_at)} != {MAX_SELECTED_RETRIEVED_AT}"
        )
    cutoff = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
    if not all(
        datetime.fromisoformat(value.replace("Z", "+00:00")) < cutoff
        for value in retrieved_at
    ):
        raise SystemExit("recorded_at must be strictly after every selected retrieval")
    if datetime.now(timezone.utc) >= cutoff:
        raise SystemExit("recorded_at must be strictly after the build-start clock")
    return pins, curated_paths


def main() -> int:
    with publication_lock():
        if DEFINITION.exists() or DEFINITION.is_symlink():
            raise SystemExit(
                f"definition already exists; refusing to overwrite: {DEFINITION}"
            )
        if RELEASE.exists() or RELEASE.is_symlink():
            raise SystemExit(
                f"release already exists; refusing to overwrite: {RELEASE}"
            )
        if sha256(BASE_DEFINITION) != BASE_DEFINITION_SHA256:
            raise SystemExit("accepted v47 definition hash differs")
        if sha256(BASE_RELEASE / "manifest.json") != BASE_MANIFEST_SHA256:
            raise SystemExit("accepted v47 manifest hash differs")

        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        pins, curated_paths = selected_inputs(base)

        staging_root = ROOT / ".staging"
        staging_root.mkdir(exist_ok=True)
        release_stage = Path(
            tempfile.mkdtemp(prefix=f".{RELEASE.name}.", dir=RELEASE.parent)
        )
        definition_stage = DEFINITION.parent / (
            f".{DEFINITION.name}.{os.getpid()}.tmp"
        )
        published_release = False
        try:
            with tempfile.TemporaryDirectory(
                prefix="open-seed-v49-db-", dir=staging_root
            ) as temporary:
                temporary_root = Path(temporary)
                connection, _ = initialize(temporary_root / "atlas.sqlite")
                try:
                    epoch = base["epoch_capture"]
                    epoch_result = EpochAIAdapter().import_file(
                        connection,
                        ROOT / epoch["archive"],
                        map_html=ROOT / epoch["map"],
                        retrieved_at=epoch["retrieved_at"],
                        as_of_date="2026-07-20",
                    )
                    normalized_epoch = json.loads(json.dumps(asdict(epoch_result)))
                    if normalized_epoch != base["expected_epoch_result"]:
                        raise SystemExit("fresh Epoch import result differs from v47")
                    for path in curated_paths:
                        document = json.loads(path.read_text(encoding="utf-8"))
                        timestamp = {row["retrieved_at"] for row in document["evidence"]}.pop()
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection, path, retrieved_at=timestamp
                        )
                        if result.warnings:
                            raise SystemExit(
                                f"curated import warnings for {path.name}: "
                                f"{result.warnings}"
                            )
                    errors = validate_database(connection)
                    if errors:
                        raise SystemExit(
                            "fresh database validation failed: " + "; ".join(errors)
                        )
                    write_release(
                        connection,
                        release_stage,
                        as_of="2026-07-20",
                        recorded_at=RECORDED_AT,
                        publication_contract_version=4,
                    )
                    summary = summarize(
                        connection,
                        as_of="2026-07-20",
                        recorded_at=RECORDED_AT,
                    )
                finally:
                    connection.close()

            manifest_path = release_stage / "manifest.json"
            manifest_raw = manifest_path.read_bytes()
            manifest = json.loads(manifest_raw)
            actual = {key: manifest[key] for key in EXPECTED_RELEASE_FACTS}
            if actual != EXPECTED_RELEASE_FACTS:
                raise SystemExit(
                    "fresh release projection differs; refusing to publish:\n"
                    + json.dumps(
                        {"actual": actual, "expected": EXPECTED_RELEASE_FACTS},
                        indent=2,
                        sort_keys=True,
                    )
                )
            actual_summary = {key: summary[key] for key in EXPECTED_SUMMARY}
            if actual_summary != EXPECTED_SUMMARY:
                raise SystemExit(
                    "fresh summary projection differs; refusing to publish:\n"
                    + json.dumps(
                        {"actual": actual_summary, "expected": EXPECTED_SUMMARY},
                        indent=2,
                        sort_keys=True,
                    )
                )
            if len(manifest["source_families"]) != 178:
                raise SystemExit("fresh source-family count differs from 178")
            if len(list(release_stage.iterdir())) != 13:
                raise SystemExit("fresh release must contain exactly 13 files")

            expected_release = {
                key: value for key, value in manifest.items() if key != "files"
            }
            expected_release["manifest_sha256"] = hashlib.sha256(
                manifest_raw
            ).hexdigest()
            definition = dict(base)
            definition["build"] = {
                "as_of": "2026-07-20",
                "recorded_at": RECORDED_AT,
            }
            definition["curated_inputs"] = [
                {"path": path, "sha256": pins[path]} for path in sorted(pins)
            ]
            definition["expected_release"] = expected_release
            definition["expected_summary"] = EXPECTED_SUMMARY
            definition["release_id"] = RELEASE.name
            with definition_stage.open("xb") as stream:
                stream.write(canonical_json(definition))
                stream.flush()
                os.fsync(stream.fileno())
            definition_stage.chmod(0o644)

            for path in release_stage.iterdir():
                path.chmod(0o444)
            release_stage.chmod(0o555)
            validate_open_seed_release(definition_stage, release_stage)
            promote_noreplace(release_stage, RELEASE)
            published_release = True
            promote_noreplace(definition_stage, DEFINITION)
            validate_open_seed_release(DEFINITION, RELEASE)
        finally:
            if not published_release:
                discard_release_stage(release_stage)
            try:
                definition_stage.unlink()
            except FileNotFoundError:
                pass

    print(
        json.dumps(
            {
                "definition": str(DEFINITION),
                "definition_sha256": sha256(DEFINITION),
                "manifest_sha256": sha256(RELEASE / "manifest.json"),
                "recorded_at": RECORDED_AT,
                "release": str(RELEASE),
                **EXPECTED_RELEASE_FACTS,
                "source_families": 178,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
