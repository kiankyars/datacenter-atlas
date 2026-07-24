"""Build the collision-isolated official open seed v50 exactly once.

V50 derives only from the accepted frozen v49 definition and release.  It
retains every inherited input pin byte-for-byte and adds four independently
reviewed official-source records.  The release remains a source-record
projection: it makes no completeness, parity, or unique-physical-site claim.
"""

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

from .curated import CuratedOfficialSourceAdapter
from .database import initialize
from .epoch import EpochAIAdapter
from .open_seed_release import validate_open_seed_release
from .publication_release import write_release
from .service import summarize, validate_database


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v49.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v49"
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v50.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v50"
PUBLICATION_LOCK = ROOT / ".open-seed-v50.lock"

BASE_DEFINITION_SHA256 = (
    "b7081b2bf511951434ee96a80bd1466e330516e415b46dde76ed171683b6c88c"
)
BASE_MANIFEST_SHA256 = (
    "8cd4859e8222fe9ddfcad4fcece7420a9e25a2ff10dd67ab1d8a237d9ee33489"
)
RECORDED_AT = "2026-07-20T18:00:00Z"
MAX_SELECTED_RETRIEVED_AT = "2026-07-20T16:57:56Z"

ADDITIONS = {
    "sources/curated-official-2026-07-20-leighton-anonymous-johor-groundbreaking.json": (
        "51b3bbd33dbe5f7d921f0e0428495277c433c48e629966eba5c092276306ebef"
    ),
    "sources/curated-official-2026-07-20-leighton-johor-bahru-57-6mw-contract.json": (
        "29ec37c89471f591a1f4f9d12d06da9021b257a0b1317e295f33d9a16d38553a"
    ),
    "sources/curated-official-2026-07-20-radiusdc-nashville-i.json": (
        "e402d328e2e9c7217d5692cbf7cf6394ae4875eda9ee6a7cceac1b5f568be7d8"
    ),
    "sources/curated-official-2026-07-20-uniserve-369-terminal-vancouver.json": (
        "fcbaef2079eb7058222a44390590ae80abe31faae184e7faf30c8306469381de"
    ),
}

EXPECTED_RELEASE_FACTS = {
    "capacity_estimates": 470,
    "construction_pipeline_records": 331,
    "construction_source_signals": 239,
    "entities": 637,
    "entities_by_kind": {"campus": 344, "project": 293},
    "evidence_records": 359,
    "resolution_candidates": 4,
}

EXPECTED_SUMMARY = {
    "entities_by_status": {
        "announced": 6,
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
        "under_construction": 234,
    },
    "entities_total": 637,
    "evidence_total": 423,
    "projects_total": 293,
}

def sha256(path: Path) -> str:
    """Return the SHA-256 digest of an ordinary file."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(document: object) -> bytes:
    """Serialize a definition in the repository's canonical JSON form."""

    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


@contextmanager
def publication_lock() -> Iterator[None]:
    """Hold an exclusive v50 publication lock without replacing any file."""

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
    """Best-effort fsync of a publication directory."""

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
    """Atomically publish ``stage`` only if ``destination`` is absent."""

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
    """Remove only the private release staging directory created by this run."""

    if not stage.exists() or stage.is_symlink():
        return
    stage.chmod(0o700)
    for path in stage.iterdir():
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"refusing contaminated release-stage cleanup: {path}")
        path.chmod(0o600)
    shutil.rmtree(stage)


def _validate_base_definition(base: dict[str, object]) -> None:
    """Prove that v49, and no rejected seed, is the selected lineage root."""

    accepted_definition = ROOT / "sources/open-seed-2026-07-20-v49.json"
    accepted_release = ROOT / "releases/2026-07-20-open-seed-v49"
    if BASE_DEFINITION != accepted_definition or BASE_RELEASE != accepted_release:
        raise SystemExit("v50 base paths must select exactly accepted v49")
    if base.get("release_id") != "2026-07-20-open-seed-v49":
        raise SystemExit("accepted seed base must be exactly v49")
    build = base.get("build")
    if not isinstance(build, dict) or build.get("recorded_at") != "2026-07-20T16:45:00Z":
        raise SystemExit("accepted v49 build metadata differs")
    expected = base.get("expected_release")
    if not isinstance(expected, dict):
        raise SystemExit("accepted v49 release contract is invalid")
    if expected.get("manifest_sha256") != BASE_MANIFEST_SHA256:
        raise SystemExit("accepted v49 manifest lineage differs")


def selected_inputs(base: dict[str, object]) -> tuple[dict[str, str], list[Path]]:
    """Return the exact inherited v49 pins plus the four accepted additions."""

    _validate_base_definition(base)
    base_rows = base.get("curated_inputs")
    if not isinstance(base_rows, list):
        raise SystemExit("accepted v49 curated input inventory is invalid")
    try:
        base_pins = {row["path"]: row["sha256"] for row in base_rows}
    except (KeyError, TypeError) as error:
        raise SystemExit("accepted v49 curated input inventory is invalid") from error
    if len(base_pins) != 297 or len(base_pins) != len(base_rows):
        raise SystemExit(f"expected 297 unique v49 inputs, found {len(base_pins)}")
    if set(base_pins) & set(ADDITIONS):
        raise SystemExit("one or more v50 additions already occurs in v49")

    pins = dict(base_pins)
    pins.update(ADDITIONS)
    if len(pins) != 301:
        raise SystemExit(f"expected 301 v50 inputs, found {len(pins)}")
    if any(pins[path] != digest for path, digest in base_pins.items()):
        raise SystemExit("one or more inherited v49 input pins changed")
    if {path: pins[path] for path in ADDITIONS} != ADDITIONS:
        raise SystemExit("v50 addition inventory changed")

    retrieved_at = [base["epoch_capture"]["retrieved_at"]]
    curated_paths: list[Path] = []
    for relative in sorted(pins):
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


def build_open_seed_v50() -> dict[str, object]:
    """Build and freeze v50 once, refusing every publication collision."""

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
            raise SystemExit("accepted v49 definition hash differs")
        if sha256(BASE_RELEASE / "manifest.json") != BASE_MANIFEST_SHA256:
            raise SystemExit("accepted v49 manifest hash differs")

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
                prefix="open-seed-v50-db-", dir=staging_root
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
                        raise SystemExit("fresh Epoch import result differs from v49")
                    for path in curated_paths:
                        document = json.loads(path.read_text(encoding="utf-8"))
                        timestamp = {
                            row["retrieved_at"] for row in document["evidence"]
                        }.pop()
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
            if len(manifest["source_families"]) != 181:
                raise SystemExit("fresh source-family count differs from 181")
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

    return {
        "definition": str(DEFINITION),
        "definition_sha256": sha256(DEFINITION),
        "manifest_sha256": sha256(RELEASE / "manifest.json"),
        "recorded_at": RECORDED_AT,
        "release": str(RELEASE),
        **EXPECTED_RELEASE_FACTS,
        "source_families": 181,
    }


def main() -> int:
    """Build v50 and print the frozen release facts."""

    print(json.dumps(build_open_seed_v50(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
