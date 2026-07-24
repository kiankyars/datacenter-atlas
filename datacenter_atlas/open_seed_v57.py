"""Build and freeze official open seed v57 as the exact v56 successor.

The only input changes are five NEXTDC schema-1.1 coordinate successors and
two narrow schema-1.0 lifecycle additions.  V57 remains source scoped and
makes no completeness, site-count, capacity-sum, or commercial-parity claim.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import csv
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
from typing import Any, Iterator, Mapping

from .curated import CuratedOfficialSourceAdapter
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .epoch import EpochAIAdapter
from .open_seed_release_v2 import (
    ADDITIONS,
    REPLACEMENTS,
    validate_open_seed_release_v2,
)
from .open_seed_v56 import (
    canonical_json,
    discard_release_stage,
    promote_noreplace,
    sha256,
    tree_digest,
)
from .publication_release import write_release
from .service import summarize, validate_database


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v56.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v56"
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v57.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v57"
PUBLICATION_LOCK = ROOT / ".open-seed-v57.lock"

BASE_DEFINITION_SHA256 = (
    "b41bf23073c51aed7756f1fa5ae7d081c5d349914b9794531fe0c1010396962c"
)
BASE_MANIFEST_SHA256 = (
    "f8bc9b4bef238288f72160e7a21533321b452d7b571d707b1de492a2f62f1cdd"
)
BASE_TREE_SHA256 = "c75b3b4b2fb066dce2e8549bdfa6fdbf06412c9885b5a9aeaea7eb36fcfe61d2"
RECORDED_AT = "2026-07-20T23:56:00Z"
AS_OF = "2026-07-20"

SUCCESSOR_PINS = {
    "sources/curated-official-2026-07-19-nextdc-b2-brisbane-1h26-fitout-v2.json": (
        "0e5c6c9dc979bc0604a8b49541d6c4f9af548d69b6f7864b99b23893e7d8ea3e"
    ),
    "sources/curated-official-2026-07-19-nextdc-kl1-kuala-lumpur-1h26-fitout-v2.json": (
        "748522f0e5cfbc0c24de6929d986fa886f763d03897fdf97346635daf2797bc4"
    ),
    "sources/curated-official-2026-07-19-nextdc-m2-melbourne-1h26-fitout-v2.json": (
        "fb7ba690ad00ea6734a1299167131ac744c4db11f78dd3d27cbc87490d618134"
    ),
    "sources/curated-official-2026-07-19-nextdc-p1-perth-1h26-fitout-v2.json": (
        "ab8f3acc96ec0e94dc3c7ebcaac321f087c9e7c960ab572436b9eb008de002dc"
    ),
    "sources/curated-official-2026-07-19-nextdc-p2-perth-1h26-fitout-v2.json": (
        "4802ae0d901e31536c56521910c061ca503b01602078d494b684d92e24b06bb7"
    ),
}
ADDITION_PINS = {
    "sources/curated-official-2026-07-20-aligned-iad06-frederick-topout.json": (
        "1321b938e409635e883e6e417beb55ac56736bfc9d956bbefcc062df35192103"
    ),
    "sources/curated-official-2026-07-20-google-bermuda-hundred-chesterfield.json": (
        "cf283bdd697427ea54cc282b37078af2ca4e0ba85aee08352b38427bcc8f4724"
    ),
}

ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:aligned-quantum-frederick-campus",
        "curated:aligned-quantum-frederick-campus:iad06",
        "curated:google-bermuda-hundred-chesterfield-campus",
        "curated:google-bermuda-hundred-chesterfield-campus:current-development",
    }
)
NEXTDC_KEYS = frozenset(
    {
        "curated:nextdc-b2-brisbane",
        "curated:nextdc-b2-brisbane:incremental-in-progress-fit-out",
        "curated:nextdc-kl1-kuala-lumpur",
        "curated:nextdc-kl1-kuala-lumpur:incremental-in-progress-fit-out",
        "curated:nextdc-m2-melbourne",
        "curated:nextdc-m2-melbourne:incremental-in-progress-fit-out",
        "curated:nextdc-p1-perth",
        "curated:nextdc-p1-perth:incremental-in-progress-fit-out",
        "curated:nextdc-p2-perth",
        "curated:nextdc-p2-perth:incremental-in-progress-fit-out",
    }
)

# Common, added, added hash, removed, removed hash against frozen v56.
CSV_DELTA_CONTRACT = {
    "entities.csv": (
        657,
        14,
        "13f5b8d147d38acd5fcc577421cf35548cb6fff2afefa7df9b726d78c6e2b0b4",
        10,
        "e9c1661d81a1633c855447de46cae760458abad7156152bb94ed0b914c332236",
    ),
    "evidence.csv": (
        388,
        3,
        "6f9b72789336ba621b7b9cd8b9f49a29e9b12d8b9926577c2b369e56fb3d3f94",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "capacity_estimates.csv": (
        484,
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_pipeline.csv": (
        343,
        7,
        "b581640a8a3e824cc58ca6d3d1c89a1fef80258add66924b4f0f64879335fb36",
        5,
        "e578451c4f9fb5c39ae1bf237febcbed81c37ac81c0e6a6e02942ad46490efd8",
    ),
    "construction_source_signals.csv": (
        254,
        2,
        "687a7f5eb9127197d2044bd598ffb3b66b73b1bb50369bc14d72bc803a370209",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "resolution_candidates.csv": (
        4,
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
}


@contextmanager
def publication_lock() -> Iterator[None]:
    """Hold an exclusive v57 publication lock without replacing any file."""

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


def selected_inputs(base: Mapping[str, Any]) -> tuple[list[dict[str, str]], list[Path]]:
    """Return the exact five-replacement/two-addition v56 successor inventory."""

    if base.get("release_id") != "2026-07-20-open-seed-v56":
        raise SystemExit("v57 base must be exactly frozen v56")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 318:
        raise SystemExit("frozen v56 curated inventory differs")
    base_pins: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise SystemExit("frozen v56 curated row is invalid")
        path, digest = row["path"], row["sha256"]
        if path in base_pins or not isinstance(path, str) or not isinstance(digest, str):
            raise SystemExit("frozen v56 curated inventory is invalid")
        base_pins[path] = digest
    if set(REPLACEMENTS) - set(base_pins):
        raise SystemExit("one or more NEXTDC predecessors is absent from v56")
    if set(REPLACEMENTS.values()) & set(base_pins):
        raise SystemExit("one or more NEXTDC successors already occurs in v56")
    if set(ADDITIONS) & set(base_pins):
        raise SystemExit("one or more v57 additions already occurs in v56")

    pins = {path: digest for path, digest in base_pins.items() if path not in REPLACEMENTS}
    pins.update(SUCCESSOR_PINS)
    pins.update(ADDITION_PINS)
    if len(pins) != 320:
        raise SystemExit(f"expected 320 unique v57 inputs, found {len(pins)}")
    rows_out = [{"path": path, "sha256": pins[path]} for path in sorted(pins)]
    paths: list[Path] = []
    for row in rows_out:
        path = ROOT / row["path"]
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"input must be an ordinary file: {row['path']}")
        if stat.S_IMODE(path.stat().st_mode) != 0o644:
            raise SystemExit(f"input mode must be 0644: {row['path']}")
        if sha256(path) != row["sha256"]:
            raise SystemExit(f"input hash differs: {row['path']}")
        paths.append(path)
    return rows_out, paths


def _import_curated(
    connection: sqlite3.Connection, path: Path, *, recorded_at: str
) -> object:
    document = json.loads(path.read_text(encoding="utf-8"))
    timestamps = {item["retrieved_at"] for item in document["evidence"]}
    if document["schema_version"] == "1.0":
        if len(timestamps) != 1:
            raise SystemExit(f"schema 1.0 source has multiple timestamps: {path.name}")
        return CuratedOfficialSourceAdapter().import_file(
            connection, path, retrieved_at=next(iter(timestamps))
        )
    if document["schema_version"] == "1.1":
        return CuratedOfficialSourceAdapterV11().import_file(
            connection, path, recorded_at=recorded_at
        )
    raise SystemExit(f"unsupported curated schema: {path.name}")


def _validate_database_delta(connection: sqlite3.Connection) -> None:
    """Pin the narrow semantic delta before publication."""

    counts = {
        "entities": connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
        "evidence": connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
        "capacity": connection.execute(
            "SELECT COUNT(*) FROM capacity_estimates"
        ).fetchone()[0],
        "lifecycle": connection.execute(
            "SELECT COUNT(*) FROM lifecycle_observations"
        ).fetchone()[0],
    }
    if counts != {"entities": 671, "evidence": 470, "capacity": 485, "lifecycle": 390}:
        raise SystemExit(f"fresh v57 database projection differs: {counts}")
    keys = {
        row[0]
        for row in connection.execute(
            "SELECT stable_key FROM entities WHERE stable_key IN ({})".format(
                ",".join("?" for _ in ADDED_ENTITY_KEYS)
            ),
            tuple(sorted(ADDED_ENTITY_KEYS)),
        )
    }
    if keys != ADDED_ENTITY_KEYS:
        raise SystemExit("v57 added entity identity set differs")
    if connection.execute(
        "SELECT COUNT(*) FROM capacity_estimates WHERE entity_id IN "
        "(SELECT id FROM entities WHERE stable_key LIKE 'curated:aligned-quantum-%')"
    ).fetchone()[0]:
        raise SystemExit("Aligned untyped 72 MW must not become a capacity estimate")


def _csv_counter(path: Path) -> Counter[tuple[tuple[str, str], ...]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return Counter(tuple(row.items()) for row in csv.DictReader(stream))


def _counter_hash(counter: Counter[tuple[tuple[str, str], ...]]) -> str:
    rows = [dict(packed) for packed in counter.elements()]
    rows.sort(
        key=lambda row: json.dumps(
            row, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    )
    raw = (
        json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _validate_release_delta(stage: Path) -> None:
    for filename, expected in CSV_DELTA_CONTRACT.items():
        before = _csv_counter(BASE_RELEASE / filename)
        after = _csv_counter(stage / filename)
        common = before & after
        added = after - common
        removed = before - common
        actual = (
            sum(common.values()),
            sum(added.values()),
            _counter_hash(added),
            sum(removed.values()),
            _counter_hash(removed),
        )
        if actual != expected:
            raise SystemExit(f"fresh v57 CSV delta differs: {filename}: {actual}")
    added_entities = _csv_counter(stage / "entities.csv") - _csv_counter(
        BASE_RELEASE / "entities.csv"
    )
    added_keys = {dict(row)["stable_key"] for row in added_entities.elements()}
    if added_keys != ADDED_ENTITY_KEYS | NEXTDC_KEYS:
        raise SystemExit("fresh v57 changed entity boundary differs")


def _build_database(base: Mapping[str, Any], paths: list[Path], sqlite_path: Path):
    connection, _ = initialize(sqlite_path)
    epoch = base["epoch_capture"]
    result = EpochAIAdapter().import_file(
        connection,
        ROOT / epoch["archive"],
        map_html=ROOT / epoch["map"],
        retrieved_at=epoch["retrieved_at"],
        as_of_date=AS_OF,
    )
    if json.loads(json.dumps(asdict(result))) != base["expected_epoch_result"]:
        connection.close()
        raise SystemExit("fresh Epoch import result differs from v56")
    try:
        for path in paths:
            imported = _import_curated(connection, path, recorded_at=RECORDED_AT)
            if getattr(imported, "warnings"):
                raise SystemExit(f"curated import warnings for {path.name}")
        errors = validate_database(connection)
        if errors:
            raise SystemExit("fresh database validation failed: " + "; ".join(errors))
        _validate_database_delta(connection)
        return connection
    except Exception:
        connection.close()
        raise


def build_open_seed_v57() -> dict[str, object]:
    """Build and freeze v57 exactly once, refusing every publication collision."""

    with publication_lock():
        if DEFINITION.exists() or DEFINITION.is_symlink():
            raise SystemExit(f"definition already exists; refusing overwrite: {DEFINITION}")
        if RELEASE.exists() or RELEASE.is_symlink():
            raise SystemExit(f"release already exists; refusing overwrite: {RELEASE}")
        if sha256(BASE_DEFINITION) != BASE_DEFINITION_SHA256:
            raise SystemExit("accepted v56 definition hash differs")
        if sha256(BASE_RELEASE / "manifest.json") != BASE_MANIFEST_SHA256:
            raise SystemExit("accepted v56 manifest hash differs")
        if tree_digest(BASE_RELEASE) != BASE_TREE_SHA256:
            raise SystemExit("accepted v56 release tree differs")

        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        input_rows, paths = selected_inputs(base)
        staging_root = ROOT / ".staging"
        staging_root.mkdir(exist_ok=True)
        release_stage = Path(
            tempfile.mkdtemp(prefix=f".{RELEASE.name}.", dir=RELEASE.parent)
        )
        definition_stage = DEFINITION.parent / f".{DEFINITION.name}.{os.getpid()}.tmp"
        published_release = False
        try:
            with tempfile.TemporaryDirectory(
                prefix="open-seed-v57-db-", dir=staging_root
            ) as temporary:
                connection = _build_database(
                    base, paths, Path(temporary) / "atlas.sqlite"
                )
                try:
                    write_release(
                        connection,
                        release_stage,
                        as_of=AS_OF,
                        recorded_at=RECORDED_AT,
                        publication_contract_version=4,
                    )
                    summary = summarize(
                        connection, as_of=AS_OF, recorded_at=RECORDED_AT
                    )
                finally:
                    connection.close()

            _validate_release_delta(release_stage)
            manifest_raw = (release_stage / "manifest.json").read_bytes()
            manifest = json.loads(manifest_raw)
            if len(list(release_stage.iterdir())) != 13:
                raise SystemExit("fresh v57 release must contain exactly 13 files")
            expected_release = {key: value for key, value in manifest.items() if key != "files"}
            expected_release["manifest_sha256"] = hashlib.sha256(manifest_raw).hexdigest()
            expected_summary = {
                key: summary[key] for key in base["expected_summary"]
            }
            definition = dict(base)
            definition["build"] = {"as_of": AS_OF, "recorded_at": RECORDED_AT}
            definition["curated_inputs"] = input_rows
            definition["expected_release"] = expected_release
            definition["expected_summary"] = expected_summary
            definition["publication_contract_version"] = 4
            definition["release_id"] = RELEASE.name
            with definition_stage.open("xb") as stream:
                stream.write(canonical_json(definition))
                stream.flush()
                os.fsync(stream.fileno())
            definition_stage.chmod(0o644)

            for path in release_stage.iterdir():
                path.chmod(0o444)
            release_stage.chmod(0o555)
            validate_open_seed_release_v2(definition_stage, release_stage)
            promote_noreplace(release_stage, RELEASE)
            published_release = True
            promote_noreplace(definition_stage, DEFINITION)
            validate_open_seed_release_v2(DEFINITION, RELEASE)
        finally:
            if not published_release:
                discard_release_stage(release_stage)
            try:
                definition_stage.unlink()
            except FileNotFoundError:
                pass

    manifest = json.loads((RELEASE / "manifest.json").read_text(encoding="utf-8"))
    return {
        "definition": str(DEFINITION),
        "definition_sha256": sha256(DEFINITION),
        "manifest_sha256": sha256(RELEASE / "manifest.json"),
        "recorded_at": RECORDED_AT,
        "release": str(RELEASE),
        "release_tree_sha256": tree_digest(RELEASE),
        **{key: value for key, value in manifest.items() if key not in {"files", "source_families"}},
        "source_families": len(manifest["source_families"]),
    }


def main() -> int:
    print(json.dumps(build_open_seed_v57(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
