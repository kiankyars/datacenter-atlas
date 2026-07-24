"""Build and freeze official open seed v58 as the exact v57 successor.

The only input change is the addition of seven audited schema-1.0 construction
sources.  V58 remains source scoped and makes no completeness, site-count,
capacity-sum, energy, or commercial-parity claim.
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
from .open_seed_release_v3 import (
    ADDITIONS,
    ADDITION_PINS,
    validate_open_seed_release_v3,
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
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v57.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v57"
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v58.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v58"
PUBLICATION_LOCK = ROOT / ".open-seed-v58.lock"

BASE_DEFINITION_SHA256 = (
    "421a8992616cea1e0b9779d47ed1f7052465cbf59c22c3d00b8a79d9463c1bc8"
)
BASE_MANIFEST_SHA256 = (
    "37f33308466d3707e2bf9f5225bd3c3546dcb2539e7f537286dd8237728d6403"
)
BASE_TREE_SHA256 = "2651d54295954e4a791e0dbc44b9e2f6947f6b519473468bcec5277299f4c8fe"
RECORDED_AT = "2026-07-21T00:21:00Z"
V11_RECORDED_AT = "2026-07-20T23:56:00Z"
AS_OF = "2026-07-20"

ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:cra-prague-gateway-data-center-campus",
        "curated:cra-prague-gateway-data-center-campus:first-building",
        "curated:jefferson-lab-newport-news-campus",
        "curated:jefferson-lab-newport-news-campus:jldc-building",
        "curated:maincubes-fra03-schwalbach-data-center",
        "curated:maincubes-fra03-schwalbach-data-center:phase-2",
        "curated:pdg-mu2-navi-mumbai-data-center-campus",
        "curated:pdg-mu2-navi-mumbai-data-center-campus:current-development",
        "curated:penzance-chantilly-premier-data-center",
        "curated:penzance-chantilly-premier-data-center:current-facility-build",
        "curated:t5-chicago-iii-northlake-data-center",
        "curated:t5-chicago-iii-northlake-data-center:current-facility-build",
        "curated:verne-mantsala-data-center-campus",
        "curated:verne-mantsala-data-center-campus:current-development",
    }
)
PROJECT_KEYS = frozenset(
    key for key in ADDED_ENTITY_KEYS if ":" in key.removeprefix("curated:")
)
CAPACITY_CONTRACT = {
    "curated:pdg-mu2-navi-mumbai-data-center-campus": (
        "critical_it_mw",
        "planned",
        "MW",
        120.0,
        "2026-07-20",
    ),
    "curated:t5-chicago-iii-northlake-data-center:current-facility-build": (
        "critical_it_mw",
        "planned",
        "MW",
        36.0,
        "2024-09-07",
    ),
}

# Common, added, added hash, removed, removed hash against frozen v57.
CSV_DELTA_CONTRACT = {
    "entities.csv": (
        671,
        14,
        "69548b25db8dd8885a6f9eb4ab5f6e10c8e170e8b9ef9f8f0734c37eeed7e0f5",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "evidence.csv": (
        391,
        9,
        "3b99c83a56cdf7cf92a0d18135334d867d4a8439de47b389011679c04bd8c4df",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "capacity_estimates.csv": (
        484,
        2,
        "16bf731b4a4f69181c69d77bc86f6fbb777b2e5f9d171d29f0a7f253ec9c649a",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_pipeline.csv": (
        350,
        7,
        "2bbd3322d55b7350ed685b89797d21f5197a33e3eb59045ceff9d1940abc1d60",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_source_signals.csv": (
        256,
        7,
        "4cd1f480a682a2dbabac3787d9d8034ec41c09b6a0cbeaa13c5de9d92eaa9dec",
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
    """Hold an exclusive v58 publication lock without replacing any file."""

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
    """Return the exact seven-addition v57 successor inventory."""

    if base.get("release_id") != "2026-07-20-open-seed-v57":
        raise SystemExit("v58 base must be exactly frozen v57")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 320:
        raise SystemExit("frozen v57 curated inventory differs")
    pins: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise SystemExit("frozen v57 curated row is invalid")
        path, digest = row["path"], row["sha256"]
        if path in pins or not isinstance(path, str) or not isinstance(digest, str):
            raise SystemExit("frozen v57 curated inventory is invalid")
        pins[path] = digest
    if ADDITIONS & set(pins):
        raise SystemExit("one or more v58 additions already occurs in v57")
    pins.update(ADDITION_PINS)
    if len(pins) != 327:
        raise SystemExit(f"expected 327 unique v58 inputs, found {len(pins)}")
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


def _import_curated(connection: sqlite3.Connection, path: Path) -> object:
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
            connection, path, recorded_at=V11_RECORDED_AT
        )
    raise SystemExit(f"unsupported curated schema: {path.name}")


def _validate_database_delta(connection: sqlite3.Connection) -> None:
    """Pin the narrow seven-source semantic delta before publication."""

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
    if counts != {"entities": 685, "evidence": 480, "capacity": 487, "lifecycle": 397}:
        raise SystemExit(f"fresh v58 database projection differs: {counts}")

    placeholders = ",".join("?" for _ in ADDED_ENTITY_KEYS)
    entity_rows = connection.execute(
        f"SELECT stable_key, kind FROM entities WHERE stable_key IN ({placeholders})",
        tuple(sorted(ADDED_ENTITY_KEYS)),
    ).fetchall()
    if {row[0] for row in entity_rows} != ADDED_ENTITY_KEYS:
        raise SystemExit("v58 added entity identity set differs")
    if {row[0] for row in entity_rows if row[1] == "project"} != PROJECT_KEYS:
        raise SystemExit("v58 project identity set differs")

    lifecycle_rows = connection.execute(
        f"""
        SELECT entities.stable_key, lifecycle_observations.status
        FROM lifecycle_observations
        JOIN entities ON entities.id = lifecycle_observations.entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        tuple(sorted(ADDED_ENTITY_KEYS)),
    ).fetchall()
    if len(lifecycle_rows) != 7 or {
        (row[0], row[1]) for row in lifecycle_rows
    } != {(key, "under_construction") for key in PROJECT_KEYS}:
        raise SystemExit("v58 lifecycle delta differs")

    capacity_rows = connection.execute(
        f"""
        SELECT entities.stable_key, capacity_estimates.metric,
               capacity_estimates.stage, capacity_estimates.unit,
               capacity_estimates.base, capacity_estimates.as_of_date
        FROM capacity_estimates
        JOIN entities ON entities.id = capacity_estimates.entity_id
        WHERE entities.stable_key IN ({placeholders})
        ORDER BY entities.stable_key
        """,
        tuple(sorted(ADDED_ENTITY_KEYS)),
    ).fetchall()
    actual_capacity = {
        row[0]: (row[1], row[2], row[3], row[4], row[5]) for row in capacity_rows
    }
    if actual_capacity != CAPACITY_CONTRACT:
        raise SystemExit(f"v58 typed capacity delta differs: {actual_capacity}")


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
    expected_files = {
        "entities.csv",
        "evidence.csv",
        "capacity_estimates.csv",
        "construction_pipeline.csv",
        "construction_source_signals.csv",
        "resolution_candidates.csv",
    }
    if set(CSV_DELTA_CONTRACT) != expected_files:
        raise SystemExit("v58 CSV delta contract is incomplete")
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
            raise SystemExit(f"fresh v58 CSV delta differs: {filename}: {actual}")
    added_entities = _csv_counter(stage / "entities.csv") - _csv_counter(
        BASE_RELEASE / "entities.csv"
    )
    added_rows = [dict(row) for row in added_entities.elements()]
    if {row["stable_key"] for row in added_rows} != ADDED_ENTITY_KEYS:
        raise SystemExit("fresh v58 added entity boundary differs")
    if Counter(row["country"] for row in added_rows) != Counter(
        {
            "Czechia": 2,
            "Finland": 2,
            "Germany": 2,
            "India": 2,
            "United States": 6,
        }
    ):
        raise SystemExit("fresh v58 added country boundary differs")


def _validate_release_facts(stage: Path) -> None:
    summary = json.loads((stage / "summary.json").read_text(encoding="utf-8"))
    expected = {
        "campuses_total": 368,
        "campuses_with_coordinates": 117,
        "capacity_estimates_current": 486,
        "construction_pipeline_records": 357,
        "construction_source_signals": 263,
        "entities_total": 685,
        "entities_with_coordinates": 164,
        "evidence_total": 480,
        "lifecycle_observations_current": 392,
        "projects_total": 317,
        "recorded_at": RECORDED_AT,
    }
    actual = {key: summary.get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"fresh v58 summary facts differ: {actual}")
    if summary["capacity_estimates_by_metric"].get("critical_it_mw") != 230:
        raise SystemExit("fresh v58 critical-IT row count differs")
    if summary["capacity_estimates_by_stage"].get("planned") != 123:
        raise SystemExit("fresh v58 planned-capacity row count differs")
    if summary["entities_by_status"].get("under_construction") != 258:
        raise SystemExit("fresh v58 under-construction entity count differs")

    manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    manifest_expected = {
        "entities": 685,
        "evidence_records": 400,
        "capacity_estimates": 486,
        "construction_pipeline_records": 357,
        "construction_source_signals": 263,
        "resolution_candidates": 4,
    }
    manifest_actual = {key: manifest.get(key) for key in manifest_expected}
    if manifest_actual != manifest_expected:
        raise SystemExit(f"fresh v58 manifest facts differ: {manifest_actual}")


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
        raise SystemExit("fresh Epoch import result differs from v57")
    try:
        for path in paths:
            imported = _import_curated(connection, path)
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


def build_open_seed_v58() -> dict[str, object]:
    """Build and freeze v58 exactly once, refusing every publication collision."""

    with publication_lock():
        if DEFINITION.exists() or DEFINITION.is_symlink():
            raise SystemExit(f"definition already exists; refusing overwrite: {DEFINITION}")
        if RELEASE.exists() or RELEASE.is_symlink():
            raise SystemExit(f"release already exists; refusing overwrite: {RELEASE}")
        if sha256(BASE_DEFINITION) != BASE_DEFINITION_SHA256:
            raise SystemExit("accepted v57 definition hash differs")
        if sha256(BASE_RELEASE / "manifest.json") != BASE_MANIFEST_SHA256:
            raise SystemExit("accepted v57 manifest hash differs")
        if tree_digest(BASE_RELEASE) != BASE_TREE_SHA256:
            raise SystemExit("accepted v57 release tree differs")

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
                prefix="open-seed-v58-db-", dir=staging_root
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
            _validate_release_facts(release_stage)
            manifest_raw = (release_stage / "manifest.json").read_bytes()
            manifest = json.loads(manifest_raw)
            if len(list(release_stage.iterdir())) != 13:
                raise SystemExit("fresh v58 release must contain exactly 13 files")
            expected_release = {
                key: value for key, value in manifest.items() if key != "files"
            }
            expected_release["manifest_sha256"] = hashlib.sha256(
                manifest_raw
            ).hexdigest()
            expected_summary = {key: summary[key] for key in base["expected_summary"]}
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
            validate_open_seed_release_v3(definition_stage, release_stage)
            promote_noreplace(release_stage, RELEASE)
            published_release = True
            promote_noreplace(definition_stage, DEFINITION)
            validate_open_seed_release_v3(DEFINITION, RELEASE)
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
        **{
            key: value
            for key, value in manifest.items()
            if key not in {"files", "source_families"}
        },
        "source_families": len(manifest["source_families"]),
    }


def main() -> int:
    print(json.dumps(build_open_seed_v58(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
