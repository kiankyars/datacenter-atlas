"""Build and freeze official open seed v61 as the exact v60 successor.

V61 remains on the 2026-07-20 local research day. It adds only the official
Batelco/Qareeb Beyon Data Oasis record. The 2025 construction observation and
2026 commissioning observation remain last-observed facts, never a current
status inference.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import csv
from dataclasses import asdict
from datetime import date
import hashlib
import io
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
from .open_seed_release_v6 import (
    ADDITION_PINS,
    AS_OF,
    OUT_OF_SCOPE_EXCLUSIONS,
    PENDING_NEXT_DAY_EXCLUSIONS,
    RECORDED_AT,
    RELEASE_ID,
    STALE_EXCLUSIONS,
    V11_RECORDED_AT,
    freshness_contract,
    validate_open_seed_release_v6,
)
from .open_seed_v56 import (
    canonical_json,
    discard_release_stage,
    promote_noreplace,
    sha256,
    tree_digest,
)
from .open_seed_v60 import FRESHNESS_FIELDS, FRESHNESS_FILENAME, build_freshness_csv
from .publication_release import build_release_documents
from .service import summarize, validate_database


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v60.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v60"
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v61.json"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v61.lock"

BASE_DEFINITION_SHA256 = (
    "4f3a81ad33c3cb73565eefe0904fcf4118d57bfc071852dc226e331e3dd32b66"
)
BASE_MANIFEST_SHA256 = (
    "d69ded6f7b86415b4dc8ad84cbee65835d878e310fbcb2c8954636066173f430"
)
BASE_TREE_SHA256 = "1d58652f691b8030717b7af6c61d2717b2b3427520f7d1b402b75b7670beb138"

FRESHNESS_README = (
    "`lifecycle_freshness.csv` treats every published lifecycle value as a "
    "last-observed status, reports its age on the release date, and makes no "
    "current-construction inference. Its 0–90, 91–365, and over-365-day bands "
    "are review queues, not evidence that a status persisted. "
    "`current_status_classification` therefore remains `unknown` and "
    "`current_construction_claim` remains `false` for every row. The new "
    "Batelco/Qareeb project preserves its 2025 construction observation and "
    "its later 2026 commissioning observation without asserting present-day "
    "operation or construction. Its 6,000-square-metre scalable-space figure "
    "and qualitative energy language remain source metadata, not normalized "
    "capacity, energy, or PUE. Pure AMS01 remains pending the next local "
    "release day; the separate Applied Digital record is not selected."
)

ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:batelco-qareeb-beyon-data-oasis-edge-data-center",
        "curated:batelco-qareeb-beyon-data-oasis-edge-data-center:facility-build",
    }
)
ADDED_PROJECT_KEYS = frozenset(
    {
        "curated:batelco-qareeb-beyon-data-oasis-edge-data-center:facility-build",
    }
)
MUTATED_ENTITY_KEYS = frozenset()

LIFECYCLE_CONTRACT = {
    (
        "curated:batelco-qareeb-beyon-data-oasis-edge-data-center:facility-build",
        "under_construction",
        "2025-02-05",
    ),
    (
        "curated:batelco-qareeb-beyon-data-oasis-edge-data-center:facility-build",
        "commissioning",
        "2026-01-13",
    ),
}

CAPACITY_CONTRACT: dict[str, tuple[object, ...]] = {}
COMMISSIONING_WINNER = {
    "curated:batelco-qareeb-beyon-data-oasis-edge-data-center:facility-build": (
        "commissioning",
        "2026-01-13",
    )
}

CSV_DELTA_CONTRACT = {
    "entities.csv": (725, 2, "ada5ce995970834d20cc9bf02f60a4924cec7ca896e7903a0cecacb8a7c1e3ea", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
    "evidence.csv": (439, 1, "c7fc3e22b8d151c4dfc2a1076a3ed2843544a0a9f70bd1a9227719a44a329d81", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
    "capacity_estimates.csv": (500, 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
    "construction_pipeline.csv": (371, 1, "f99f8b2fe4aeb02d1df8f6376dbf80927bcc9f4daa570d0f0f3d093c82b9c2f9", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
    "construction_source_signals.csv": (278, 1, "e47896bcb232d0e2230a1feaf648247c3c3f43c7bc0e821ae64aac8eafa5c47f", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
    "resolution_candidates.csv": (5, 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
}

NEW_SOURCE_FAMILIES = {"batelco_business_news"}


@contextmanager
def publication_lock() -> Iterator[None]:
    """Hold an exclusive v61 publication lock without replacing any file."""

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


def _validate_source_boundary(path: Path, document: Mapping[str, Any]) -> None:
    """Guard source-level identity, roles, geometry, and capacity boundaries."""

    relative = str(path.relative_to(ROOT))
    if relative not in ADDITION_PINS:
        return
    if document.get("schema_version") != "1.1":
        raise SystemExit(f"v61 successor source must use schema 1.1: {relative}")
    campus = document.get("campus")
    project = document.get("project")
    if not isinstance(campus, dict) or not isinstance(project, dict):
        raise SystemExit(f"v61 source must contain one campus and one project: {relative}")
    if project["stable_key"] not in ADDED_PROJECT_KEYS:
        raise SystemExit(f"v61 project identity differs: {relative}")
    if not project["stable_key"].startswith(campus["stable_key"] + ":"):
        raise SystemExit(f"v61 phase does not nest under its named campus: {relative}")
    expected_roles = {"operator": ["Qareeb Data Centers"]}
    for entity in (campus, project):
        if entity.get("roles") != expected_roles:
            raise SystemExit(f"v61 Qareeb operator role differs: {relative}")
        if entity.get("coordinates") is not None or entity.get("geometry") is not None:
            raise SystemExit(f"v61 source invented geometry: {relative}")
    if document.get("capacities") != [] or document.get("workloads") != []:
        raise SystemExit(f"v61 source normalized unsupported capacity/workload: {relative}")
    if document.get("operating_models") != [
        {
            "entity": "project",
            "value": "colocation",
            "evidence_key": (
                "batelco-qareeb-beyon-data-oasis-operational-readiness-"
                "2026-01-13-captured-2026-07-20"
            ),
            "as_of_date": "2026-01-13",
            "method": "company_disclosure",
            "confidence": 0.99,
        }
    ]:
        raise SystemExit(f"v61 colocation observation differs: {relative}")


def selected_inputs(base: Mapping[str, Any]) -> tuple[list[dict[str, str]], list[Path]]:
    """Return the exact one-addition v60 successor."""

    if base.get("release_id") != "2026-07-20-open-seed-v60":
        raise SystemExit("v61 base must be exactly frozen v60")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 347:
        raise SystemExit("frozen v60 curated inventory differs")
    pins: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise SystemExit("frozen v60 curated row is invalid")
        path, digest = row["path"], row["sha256"]
        if path in pins or not isinstance(path, str) or not isinstance(digest, str):
            raise SystemExit("frozen v60 curated inventory is invalid")
        pins[path] = digest
    for path, digest in ADDITION_PINS.items():
        if path in pins:
            raise SystemExit("a v61 addition already occurs in v60")
        pins[path] = digest
    excluded = STALE_EXCLUSIONS | PENDING_NEXT_DAY_EXCLUSIONS | OUT_OF_SCOPE_EXCLUSIONS
    if excluded & set(pins):
        raise SystemExit("an excluded v61 source was selected")
    if len(pins) != 348:
        raise SystemExit(f"expected 348 unique v61 inputs, found {len(pins)}")

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
        document = json.loads(path.read_text(encoding="utf-8"))
        _validate_source_boundary(path, document)
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
    counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "entities",
            "evidence",
            "lifecycle_observations",
            "capacity_estimates",
            "entity_snapshots",
            "operating_model_observations",
            "workload_observations",
        )
    }
    expected = {
        "entities": 727,
        "evidence": 542,
        "lifecycle_observations": 428,
        "capacity_estimates": 501,
        "entity_snapshots": 746,
        "operating_model_observations": 51,
        "workload_observations": 122,
    }
    if counts != expected:
        raise SystemExit(f"fresh v61 database projection differs: {counts}")

    relevant = tuple(sorted(ADDED_ENTITY_KEYS | MUTATED_ENTITY_KEYS))
    placeholders = ",".join("?" for _ in relevant)
    entity_rows = connection.execute(
        f"SELECT stable_key, kind FROM entities WHERE stable_key IN ({placeholders})",
        relevant,
    ).fetchall()
    if {row[0] for row in entity_rows} != ADDED_ENTITY_KEYS:
        raise SystemExit("v61 entity identity set differs")
    if {row[0] for row in entity_rows if row[1] == "project"} != ADDED_PROJECT_KEYS:
        raise SystemExit("v61 project identity set differs")

    target_rows = connection.execute(
        f"""
        SELECT project_entity.stable_key, target_entity.stable_key
        FROM projects
        JOIN entities AS project_entity ON project_entity.id = projects.entity_id
        JOIN entities AS target_entity ON target_entity.id = projects.target_entity_id
        WHERE project_entity.stable_key IN ({placeholders})
        """,
        relevant,
    ).fetchall()
    expected_targets = {key: key.rsplit(":", 1)[0] for key in ADDED_PROJECT_KEYS}
    if {row[0]: row[1] for row in target_rows} != expected_targets:
        raise SystemExit("v61 project-to-campus nesting differs")

    lifecycle_rows = connection.execute(
        f"""
        SELECT entities.stable_key, lifecycle_observations.status,
               lifecycle_observations.as_of_date
        FROM lifecycle_observations
        JOIN entities ON entities.id = lifecycle_observations.entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        relevant,
    ).fetchall()
    if {(row[0], row[1], row[2]) for row in lifecycle_rows} != LIFECYCLE_CONTRACT:
        raise SystemExit("v61 lifecycle delta differs")

    capacity_rows = connection.execute(
        f"""
        SELECT entities.stable_key, capacity_estimates.metric,
               capacity_estimates.stage, capacity_estimates.unit,
               capacity_estimates.low, capacity_estimates.base,
               capacity_estimates.high, capacity_estimates.as_of_date
        FROM capacity_estimates
        JOIN entities ON entities.id = capacity_estimates.entity_id
        WHERE entities.stable_key IN ({placeholders})
        ORDER BY entities.stable_key
        """,
        relevant,
    ).fetchall()
    actual_capacity = {
        row[0]: (row[1], row[2], row[3], row[4], row[5], row[6], row[7])
        for row in capacity_rows
    }
    if actual_capacity != CAPACITY_CONTRACT:
        raise SystemExit(f"v61 typed capacity delta differs: {actual_capacity}")

    coordinate_count = connection.execute(
        f"""
        SELECT COUNT(*) FROM entity_snapshots
        JOIN entities ON entities.id = entity_snapshots.entity_id
        WHERE entities.stable_key IN ({placeholders})
          AND (latitude IS NOT NULL OR longitude IS NOT NULL OR geometry_json IS NOT NULL)
        """,
        relevant,
    ).fetchone()[0]
    if coordinate_count:
        raise SystemExit("v61 added or replacement records gained invented geometry")

    snapshot_rows = connection.execute(
        f"""
        SELECT entities.stable_key, entity_snapshots.tags_json
        FROM entity_snapshots
        JOIN entities ON entities.id = entity_snapshots.entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        relevant,
    ).fetchall()
    expected_operator_tag = {"role:operator": "Qareeb Data Centers"}
    for stable_key, tags_json in snapshot_rows:
        tags = json.loads(tags_json)
        if {key: value for key, value in tags.items() if key.startswith("role:")} != (
            expected_operator_tag
        ):
            raise SystemExit(f"v61 Qareeb operator tag differs: {stable_key}")

    model_rows = connection.execute(
        """
        SELECT entities.stable_key, operating_model_observations.operating_model,
               operating_model_observations.as_of_date,
               operating_model_observations.method
        FROM operating_model_observations
        JOIN entities ON entities.id = operating_model_observations.entity_id
        WHERE entities.stable_key = ?
        """,
        (next(iter(ADDED_PROJECT_KEYS)),),
    ).fetchall()
    if [tuple(row) for row in model_rows] != [
        (
            next(iter(ADDED_PROJECT_KEYS)),
            "colocation",
            "2026-01-13",
            "company_disclosure",
        )
    ]:
        raise SystemExit("v61 Qareeb colocation observation differs")


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
        raise SystemExit("fresh Epoch import result differs from v60")
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


def augment_release_documents(
    documents: Mapping[str, str], *, as_of: str
) -> dict[str, str]:
    """Add the v61 last-observed carrier and bind it into the manifest."""

    output = dict(documents)
    if FRESHNESS_FILENAME in output:
        raise RuntimeError("freshness filename already exists")
    freshness = build_freshness_csv(output["entities.csv"], as_of=as_of)
    output[FRESHNESS_FILENAME] = freshness
    readme = output["README.md"].rstrip() + "\n\n" + FRESHNESS_README + "\n"
    output["README.md"] = readme
    manifest = json.loads(output["manifest.json"])
    manifest["files"]["README.md"] = {
        "bytes": len(readme.encode("utf-8")),
        "sha256": hashlib.sha256(readme.encode("utf-8")).hexdigest(),
    }
    manifest["files"][FRESHNESS_FILENAME] = {
        "bytes": len(freshness.encode("utf-8")),
        "sha256": hashlib.sha256(freshness.encode("utf-8")).hexdigest(),
    }
    freshness_rows = list(csv.DictReader(io.StringIO(freshness)))
    manifest["current_status_inferred"] = False
    manifest["lifecycle_freshness_records"] = len(freshness_rows)
    manifest["lifecycle_status_semantics"] = "last_observed"
    output["manifest.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    return output


def _write_augmented_release(connection: sqlite3.Connection, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    documents = build_release_documents(
        connection,
        as_of=AS_OF,
        recorded_at=RECORDED_AT,
        publication_contract_version=4,
    )
    for filename, text in augment_release_documents(documents, as_of=AS_OF).items():
        (output / filename).write_text(text, encoding="utf-8")


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


def _rows_by_key(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return {row["stable_key"]: row for row in csv.DictReader(stream)}


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
            raise SystemExit(f"fresh v61 CSV delta differs: {filename}: {actual}")

    before_entities = _rows_by_key(BASE_RELEASE / "entities.csv")
    after_entities = _rows_by_key(stage / "entities.csv")
    if set(after_entities) - set(before_entities) != ADDED_ENTITY_KEYS:
        raise SystemExit("v61 added entity set differs")
    if set(before_entities) - set(after_entities):
        raise SystemExit("v61 unexpectedly removed an entity identity")
    changed_common = {
        key
        for key in before_entities.keys() & after_entities.keys()
        if before_entities[key] != after_entities[key]
    }
    if changed_common:
        raise SystemExit("v61 unexpectedly changed a frozen-v60 entity row")
    for key, (status, observed) in COMMISSIONING_WINNER.items():
        row = after_entities[key]
        if row["status"] != status or row["status_as_of"] != observed:
            raise SystemExit(f"later commissioning observation did not win: {key}")


def _freshness_class(age_days: int) -> str:
    if age_days <= 90:
        return "recent_0_90_days"
    if age_days <= 365:
        return "aging_91_365_days"
    return "stale_over_365_days"


def _validate_freshness(stage: Path) -> None:
    with (stage / FRESHNESS_FILENAME).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 413 or tuple(rows[0]) != FRESHNESS_FIELDS:
        raise SystemExit(f"fresh v61 freshness shape differs: {len(rows)}")
    if any(
        row["status_semantics"] != "last_observed"
        or row["current_status_classification"] != "unknown"
        or row["current_construction_claim"] != "false"
        for row in rows
    ):
        raise SystemExit("v61 freshness rows infer current status")
    by_key = {row["stable_key"]: row for row in rows}
    qareeb = by_key[next(iter(ADDED_PROJECT_KEYS))]
    if (
        qareeb["last_observed_status"] != "commissioning"
        or qareeb["last_observed_status_as_of"] != "2026-01-13"
        or qareeb["current_status_classification"] != "unknown"
        or qareeb["current_construction_claim"] != "false"
    ):
        raise SystemExit("v61 Qareeb freshness semantics differ")
    if any(
        "stt-johor" in row["stable_key"]
        or "pure-dc-ams01" in row["stable_key"]
        or "applied-digital-pf1-building-2-phase-1" in row["stable_key"]
        for row in rows
    ):
        raise SystemExit("an excluded source leaked into v61 freshness output")
    as_of_date = date.fromisoformat(AS_OF)
    classes = Counter()
    for row in rows:
        expected_age = as_of_date - date.fromisoformat(row["last_observed_status_as_of"])
        if row["observation_age_days"] != str(expected_age.days):
            raise SystemExit("v61 freshness age differs")
        expected_class = _freshness_class(expected_age.days)
        if row["freshness_class"] != expected_class:
            raise SystemExit("v61 freshness class differs")
        classes[expected_class] += 1
    if classes != {
        "recent_0_90_days": 211,
        "aging_91_365_days": 175,
        "stale_over_365_days": 27,
    }:
        raise SystemExit(f"v61 freshness distribution differs: {classes}")


def _validate_release_facts(stage: Path) -> None:
    summary = json.loads((stage / "summary.json").read_text(encoding="utf-8"))
    expected = {
        "campuses_total": 389,
        "campuses_with_coordinates": 122,
        "capacity_estimates_current": 500,
        "construction_pipeline_records": 372,
        "construction_source_signals": 279,
        "entities_total": 727,
        "entities_with_coordinates": 170,
        "evidence_total": 542,
        "lifecycle_observations_current": 413,
        "projects_total": 338,
        "recorded_at": RECORDED_AT,
    }
    actual = {key: summary.get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"fresh v61 summary facts differ: {actual}")
    if summary["capacity_estimates_by_metric"].get("critical_it_mw") != 244:
        raise SystemExit("fresh v61 critical-IT row count differs")
    if summary["capacity_estimates_by_stage"].get("planned") != 136:
        raise SystemExit("fresh v61 planned-capacity row count differs")
    if summary["entities_by_status"].get("under_construction") != 268:
        raise SystemExit("fresh v61 under-construction observation count differs")
    if summary["entities_by_status"].get("commissioning") != 2:
        raise SystemExit("fresh v61 commissioning observation count differs")

    manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    expected_manifest = {
        "entities": 727,
        "evidence_records": 440,
        "capacity_estimates": 500,
        "construction_pipeline_records": 372,
        "construction_source_signals": 279,
        "resolution_candidates": 5,
        "lifecycle_freshness_records": 413,
        "lifecycle_status_semantics": "last_observed",
        "current_status_inferred": False,
    }
    actual_manifest = {key: manifest.get(key) for key in expected_manifest}
    if actual_manifest != expected_manifest:
        raise SystemExit(f"fresh v61 manifest facts differ: {actual_manifest}")
    base_manifest = json.loads(
        (BASE_RELEASE / "manifest.json").read_text(encoding="utf-8")
    )
    if set(manifest["source_families"]) - set(base_manifest["source_families"]) != (
        NEW_SOURCE_FAMILIES
    ):
        raise SystemExit("fresh v61 source-family delta differs")
    if set(base_manifest["source_families"]) - set(manifest["source_families"]):
        raise SystemExit("fresh v61 removed a source family")
    if len(manifest["source_families"]) != 240:
        raise SystemExit("fresh v61 source-family count differs")
    if len(list(stage.iterdir())) != 14:
        raise SystemExit("fresh v61 release must contain exactly 14 files")
    _validate_freshness(stage)


def build_open_seed_v61() -> dict[str, object]:
    """Build and freeze v61 exactly once, refusing every publication collision."""

    with publication_lock():
        if DEFINITION.exists() or DEFINITION.is_symlink():
            raise SystemExit(f"definition already exists; refusing overwrite: {DEFINITION}")
        if RELEASE.exists() or RELEASE.is_symlink():
            raise SystemExit(f"release already exists; refusing overwrite: {RELEASE}")
        if sha256(BASE_DEFINITION) != BASE_DEFINITION_SHA256:
            raise SystemExit("accepted v60 definition hash differs")
        if sha256(BASE_RELEASE / "manifest.json") != BASE_MANIFEST_SHA256:
            raise SystemExit("accepted v60 manifest hash differs")
        if tree_digest(BASE_RELEASE) != BASE_TREE_SHA256:
            raise SystemExit("accepted v60 release tree differs")

        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        input_rows, paths = selected_inputs(base)
        staging_root = ROOT / ".staging"
        staging_root.mkdir(exist_ok=True)
        release_stage = Path(
            tempfile.mkdtemp(prefix=f".{RELEASE.name}.", dir=RELEASE.parent)
        )
        release_stage.rmdir()
        definition_stage = DEFINITION.parent / f".{DEFINITION.name}.{os.getpid()}.tmp"
        published_release = False
        try:
            with tempfile.TemporaryDirectory(
                prefix="open-seed-v61-db-", dir=staging_root
            ) as temporary:
                connection = _build_database(
                    base, paths, Path(temporary) / "atlas.sqlite"
                )
                try:
                    _write_augmented_release(connection, release_stage)
                    summary = summarize(
                        connection, as_of=AS_OF, recorded_at=RECORDED_AT
                    )
                finally:
                    connection.close()

            _validate_release_delta(release_stage)
            _validate_release_facts(release_stage)
            manifest_raw = (release_stage / "manifest.json").read_bytes()
            manifest = json.loads(manifest_raw)
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
            definition["freshness_contract"] = freshness_contract()
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
            validate_open_seed_release_v6(definition_stage, release_stage)
            promote_noreplace(release_stage, RELEASE)
            published_release = True
            promote_noreplace(definition_stage, DEFINITION)
            validate_open_seed_release_v6(DEFINITION, RELEASE)
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
    print(json.dumps(build_open_seed_v61(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
