"""Build and freeze official open seed v65 as the exact v64 successor.

V65 remains on the 2026-07-20 local research day. It adds only the accepted
Lancium/Crusoe/Oracle Abilene package. Lifecycle values remain dated,
last-observed facts and never become current-status inferences.
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
from .open_seed_release_v10 import (
    ADDITION_PINS,
    AS_OF,
    OUT_OF_SCOPE_EXCLUSIONS,
    PENDING_NEXT_DAY_EXCLUSIONS,
    RECORDED_AT,
    RELEASE_ID,
    STALE_EXCLUSIONS,
    V11_RECORDED_AT,
    _validate_local_research_day,
    freshness_contract,
    validate_open_seed_release_v10,
)
from .open_seed_v56 import (
    canonical_json,
    discard_release_stage,
    promote_noreplace,
    sha256,
    tree_digest,
)
from .open_seed_v61 import FRESHNESS_FIELDS, FRESHNESS_FILENAME, build_freshness_csv
from .publication_release import build_release_documents
from .service import summarize, validate_database


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v64.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v64"
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v65.json"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v65.lock"

BASE_DEFINITION_SHA256 = (
    "d398dfd242fe58863998ea45e10d35de0020c7f6b4fd6bc31af19980d871ec7e"
)
BASE_MANIFEST_SHA256 = (
    "5c5b19079ce237b859c2bdaf465bf1aec17392f52a75ad81805a919e1ee4cc1d"
)
BASE_TREE_SHA256 = "05901f4760e452d5d3deb4134b3434e248f7e8f15873a5f27cdad559582385da"

FRESHNESS_README = (
    "`lifecycle_freshness.csv` treats every published lifecycle value as a "
    "last-observed status, reports its age on the release date, and makes no "
    "current-construction inference. Its 0–90, 91–365, and over-365-day bands "
    "are review queues, not evidence that a status persisted. "
    "`current_status_classification` therefore remains `unknown` and "
    "`current_construction_claim` remains `false` for every row. The Abilene "
    "remaining-build observation is dated June 4, 2026 and is not rolled "
    "forward. Its 1,200 MW row is planned campus grid connection, not IT load, "
    "facility demand, generation, current load, consumption, or annual energy. "
    "Oracle's delivered 42% remains untyped metadata. No coordinate, geometry, "
    "tenant, operating model, PUE, or energy claim is inferred."
)

ABILENE_CAMPUS_KEY = "curated:lancium-clean-campus-abilene-ai-data-center"
ABILENE_PROJECT_KEY = f"{ABILENE_CAMPUS_KEY}:remaining-six-building-expansion"

ADDED_ENTITY_KEYS = frozenset(
    {
        ABILENE_CAMPUS_KEY,
        ABILENE_PROJECT_KEY,
    }
)
ADDED_PROJECT_KEYS = frozenset({ABILENE_PROJECT_KEY})
RELEVANT_ENTITY_KEYS = ADDED_ENTITY_KEYS
MUTATED_ENTITY_KEYS = frozenset()

LIFECYCLE_CONTRACT = {
    (ABILENE_PROJECT_KEY, "under_construction", "2026-06-04"),
}
STATUS_WINNERS = {
    stable_key: (status, observed)
    for stable_key, status, observed in LIFECYCLE_CONTRACT
}
CAPACITY_CONTRACT = {
    (
        ABILENE_CAMPUS_KEY,
        "grid_connection_mw",
        "planned",
        "MW",
        1200.0,
        1200.0,
        1200.0,
        "2025-03-18",
    ),
}

CSV_DELTA_CONTRACT = {
    "entities.csv": (
        753,
        2,
        "c2a932ba4895d002d871850c5ce9b27736a0f63925d3941c7ea6c24616c21c48",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "evidence.csv": (
        464,
        4,
        "db7c523669425e2809e334200806d99346d7f3a4a786452da689f89d63036997",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "capacity_estimates.csv": (
        511,
        1,
        "a55aeec843c32e9903c1e7daddf3a195ad639bd1a45ac114ecb79644ebf23e61",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_pipeline.csv": (
        386,
        1,
        "cf4984d500a441f3c551310a6fdda05c015ed74d8944700a6f2eb0205dac0cc8",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_source_signals.csv": (
        291,
        1,
        "19397755efdc7d814472b06ddab31d4fc78887bafaa11106dfb02ac3607cbfd5",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "resolution_candidates.csv": (
        5,
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
}

NEW_SOURCE_FAMILIES = {
    "city_of_abilene_planning_reports",
}


@contextmanager
def publication_lock() -> Iterator[None]:
    """Hold an exclusive v65 publication lock without replacing any file."""

    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise SystemExit(
            f"active publication lock exists: {PUBLICATION_LOCK}"
        ) from error
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


def _projected_source(document: Mapping[str, Any]) -> dict[str, Any]:
    def entity(name: str) -> dict[str, Any]:
        row = document[name]
        return {
            "stable_key": row.get("stable_key"),
            "roles": row.get("roles"),
            "coordinates": row.get("coordinates"),
            "geometry": row.get("geometry"),
        }

    return {
        "schema_version": document.get("schema_version"),
        "campus": entity("campus"),
        "project": entity("project"),
        "lifecycle": [
            (
                row.get("entity"),
                row.get("value"),
                row.get("as_of_date"),
                row.get("method"),
            )
            for row in document.get("lifecycle", [])
        ],
        "operating_models": [
            (
                row.get("entity"),
                row.get("value"),
                row.get("as_of_date"),
                row.get("method"),
            )
            for row in document.get("operating_models", [])
        ],
        "workloads": [
            (
                row.get("entity"),
                row.get("value"),
                row.get("as_of_date"),
                row.get("method"),
            )
            for row in document.get("workloads", [])
        ],
        "capacities": [
            (
                row.get("entity"),
                row.get("metric"),
                row.get("stage"),
                row.get("unit"),
                float(row.get("low")),
                float(row.get("base")),
                float(row.get("high")),
                row.get("as_of_date"),
            )
            for row in document.get("capacities", [])
        ],
    }


def _boundary(
    campus_key: str,
    project_key: str,
    *,
    schema_version: str = "1.1",
    roles: Mapping[str, list[str]] | None = None,
    lifecycle: tuple[str, str, str],
    capacities: list[tuple[str, str, str, str, float, float, float, str]] | None = None,
    operating_models: list[tuple[str, str, str, str]] | None = None,
    workloads: list[tuple[str, str, str, str]] | None = None,
) -> dict[str, Any]:
    entity_roles = dict(roles or {})
    return {
        "schema_version": schema_version,
        "campus": {
            "stable_key": campus_key,
            "roles": entity_roles,
            "coordinates": None,
            "geometry": None,
        },
        "project": {
            "stable_key": project_key,
            "roles": entity_roles,
            "coordinates": None,
            "geometry": None,
        },
        "lifecycle": [("project", lifecycle[0], lifecycle[1], lifecycle[2])],
        "operating_models": list(operating_models or []),
        "workloads": list(workloads or []),
        "capacities": list(capacities or []),
    }


SOURCE_BOUNDARIES: dict[str, dict[str, Any]] = {
    "sources/curated-official-2026-07-20-lancium-crusoe-oracle-abilene.json": _boundary(
        ABILENE_CAMPUS_KEY,
        ABILENE_PROJECT_KEY,
        schema_version="1.0",
        roles={"owner": ["Lancium"], "developer": ["Crusoe"]},
        lifecycle=(
            "under_construction",
            "2026-06-04",
            "authoritative_physical_status_update",
        ),
        capacities=[
            (
                "campus",
                "grid_connection_mw",
                "planned",
                "MW",
                1200.0,
                1200.0,
                1200.0,
                "2025-03-18",
            )
        ],
        workloads=[
            (
                "project",
                "ai_specialized_unspecified",
                "2026-01-31",
                "company_disclosure",
            )
        ],
    ),
}


def _validate_source_boundary(path: Path, document: Mapping[str, Any]) -> None:
    relative = str(path.relative_to(ROOT))
    expected = SOURCE_BOUNDARIES.get(relative)
    if expected is None:
        return
    if _projected_source(document) != expected:
        raise SystemExit(f"v65 source boundary differs: {relative}")


def selected_inputs(base: Mapping[str, Any]) -> tuple[list[dict[str, str]], list[Path]]:
    """Return the exact one-addition v64 successor."""

    if base.get("release_id") != "2026-07-20-open-seed-v64":
        raise SystemExit("v65 base must be exactly frozen v64")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 363:
        raise SystemExit("frozen v64 curated inventory differs")
    pins: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise SystemExit("frozen v64 curated row is invalid")
        source_path, digest = row["path"], row["sha256"]
        if (
            source_path in pins
            or not isinstance(source_path, str)
            or not isinstance(digest, str)
        ):
            raise SystemExit("frozen v64 curated inventory is invalid")
        pins[source_path] = digest
    for source_path, digest in ADDITION_PINS.items():
        if source_path in pins:
            raise SystemExit("a v65 addition already occurs in v64")
        pins[source_path] = digest
    excluded = STALE_EXCLUSIONS | PENDING_NEXT_DAY_EXCLUSIONS | OUT_OF_SCOPE_EXCLUSIONS
    if excluded & set(pins):
        raise SystemExit("an excluded v65 source was selected")
    if len(pins) != 364:
        raise SystemExit(f"expected 364 unique v65 inputs, found {len(pins)}")

    rows_out = [
        {"path": source_path, "sha256": pins[source_path]}
        for source_path in sorted(pins)
    ]
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
        if row["path"] in ADDITION_PINS:
            _validate_local_research_day(document, row["path"])
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
        "entities": 755,
        "evidence": 577,
        "lifecycle_observations": 444,
        "capacity_estimates": 513,
        "entity_snapshots": 775,
        "operating_model_observations": 56,
        "workload_observations": 125,
    }
    if counts != expected:
        raise SystemExit(f"fresh v65 database projection differs: {counts}")

    relevant = tuple(sorted(RELEVANT_ENTITY_KEYS))
    placeholders = ",".join("?" for _ in relevant)
    entity_rows = connection.execute(
        f"SELECT stable_key, kind FROM entities WHERE stable_key IN ({placeholders})",
        relevant,
    ).fetchall()
    if {row[0] for row in entity_rows} != RELEVANT_ENTITY_KEYS:
        raise SystemExit("v65 relevant identity set differs")
    if {row[0] for row in entity_rows if row[1] == "project"} != ADDED_PROJECT_KEYS:
        raise SystemExit("v65 project identity set differs")

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
    expected_targets = {
        ABILENE_PROJECT_KEY: ABILENE_CAMPUS_KEY,
    }
    if {row[0]: row[1] for row in target_rows} != expected_targets:
        raise SystemExit("v65 project-to-campus nesting differs")

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
    if {tuple(row) for row in lifecycle_rows} != LIFECYCLE_CONTRACT:
        raise SystemExit("v65 lifecycle delta differs")

    capacity_rows = connection.execute(
        f"""
        SELECT entities.stable_key, capacity_estimates.metric,
               capacity_estimates.stage, capacity_estimates.unit,
               capacity_estimates.low, capacity_estimates.base,
               capacity_estimates.high, capacity_estimates.as_of_date
        FROM capacity_estimates
        JOIN entities ON entities.id = capacity_estimates.entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        relevant,
    ).fetchall()
    if {tuple(row) for row in capacity_rows} != CAPACITY_CONTRACT:
        raise SystemExit(f"v65 typed capacity delta differs: {capacity_rows}")

    snapshot_rows = connection.execute(
        f"""
        SELECT entities.stable_key, entity_snapshots.latitude,
               entity_snapshots.longitude, entity_snapshots.geometry_json,
               entity_snapshots.tags_json
        FROM entity_snapshots
        JOIN entities ON entities.id = entity_snapshots.entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        relevant,
    ).fetchall()
    if (
        len(snapshot_rows) != len(RELEVANT_ENTITY_KEYS)
        or {row[0] for row in snapshot_rows} != RELEVANT_ENTITY_KEYS
    ):
        raise SystemExit("v65 snapshot identity set differs")
    expected_abilene_roles = {
        "role:owner": "Lancium",
        "role:developer": "Crusoe",
    }
    for stable_key, latitude, longitude, geometry_json, tags_json in snapshot_rows:
        tags = json.loads(tags_json)
        actual_roles = {
            key: value for key, value in tags.items() if key.startswith("role:")
        }
        expected_roles = expected_abilene_roles
        if actual_roles != expected_roles:
            raise SystemExit(f"v65 role tag differs: {stable_key}")
        if latitude is not None or longitude is not None or geometry_json is not None:
            raise SystemExit(f"v65 source gained invented geometry: {stable_key}")

    model_rows = connection.execute(
        f"""
        SELECT entities.stable_key,
               operating_model_observations.operating_model,
               operating_model_observations.as_of_date,
               operating_model_observations.method
        FROM operating_model_observations
        JOIN entities ON entities.id = operating_model_observations.entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        relevant,
    ).fetchall()
    if model_rows:
        raise SystemExit("v65 operating-model boundary differs")

    workload_rows = connection.execute(
        f"""
        SELECT entities.stable_key, workload_observations.workload
        FROM workload_observations
        JOIN entities ON entities.id = workload_observations.entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        relevant,
    ).fetchall()
    if {tuple(row) for row in workload_rows} != {
        (ABILENE_PROJECT_KEY, "ai_specialized_unspecified")
    }:
        raise SystemExit("v65 workload boundary differs")


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
        raise SystemExit("fresh Epoch import result differs from v64")
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
    """Add the v65 last-observed carrier and bind it into the manifest."""

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
            raise SystemExit(f"fresh v65 CSV delta differs: {filename}: {actual}")

    before_entities = _rows_by_key(BASE_RELEASE / "entities.csv")
    after_entities = _rows_by_key(stage / "entities.csv")
    if set(after_entities) - set(before_entities) != ADDED_ENTITY_KEYS:
        raise SystemExit("v65 added entity set differs")
    if set(before_entities) - set(after_entities):
        raise SystemExit("v65 unexpectedly removed an entity identity")
    changed_common = {
        key
        for key in before_entities.keys() & after_entities.keys()
        if before_entities[key] != after_entities[key]
    }
    if changed_common:
        raise SystemExit("v65 unexpectedly changed a frozen-v64 entity row")
    for key, (status, observed) in STATUS_WINNERS.items():
        row = after_entities[key]
        if row["status"] != status or row["status_as_of"] != observed:
            raise SystemExit(f"v65 status winner differs: {key}")


def _freshness_class(age_days: int) -> str:
    if age_days <= 90:
        return "recent_0_90_days"
    if age_days <= 365:
        return "aging_91_365_days"
    return "stale_over_365_days"


def _validate_freshness(stage: Path) -> None:
    with (stage / FRESHNESS_FILENAME).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 429 or tuple(rows[0]) != FRESHNESS_FIELDS:
        raise SystemExit(f"fresh v65 freshness shape differs: {len(rows)}")
    if any(
        row["status_semantics"] != "last_observed"
        or row["current_status_classification"] != "unknown"
        or row["current_construction_claim"] != "false"
        for row in rows
    ):
        raise SystemExit("v65 freshness rows infer current status")
    by_key = {row["stable_key"]: row for row in rows}
    for key, (status, observed) in STATUS_WINNERS.items():
        row = by_key[key]
        if (
            row["last_observed_status"] != status
            or row["last_observed_status_as_of"] != observed
            or row["current_status_classification"] != "unknown"
            or row["current_construction_claim"] != "false"
        ):
            raise SystemExit(f"v65 freshness semantics differ: {key}")
    if any(
        "stt-johor" in row["stable_key"] or "pure-dc-ams01" in row["stable_key"]
        for row in rows
    ):
        raise SystemExit("an excluded or unseeded source leaked into v65 freshness")
    as_of_date = date.fromisoformat(AS_OF)
    classes = Counter()
    for row in rows:
        expected_age = as_of_date - date.fromisoformat(
            row["last_observed_status_as_of"]
        )
        if row["observation_age_days"] != str(expected_age.days):
            raise SystemExit("v65 freshness age differs")
        expected_class = _freshness_class(expected_age.days)
        if row["freshness_class"] != expected_class:
            raise SystemExit("v65 freshness class differs")
        classes[expected_class] += 1
    if classes != {
        "recent_0_90_days": 219,
        "aging_91_365_days": 183,
        "stale_over_365_days": 27,
    }:
        raise SystemExit(f"v65 freshness distribution differs: {classes}")


def _validate_release_facts(stage: Path) -> None:
    summary = json.loads((stage / "summary.json").read_text(encoding="utf-8"))
    expected = {
        "campuses_total": 401,
        "campuses_with_coordinates": 123,
        "capacity_estimates_current": 512,
        "construction_pipeline_records": 387,
        "construction_source_signals": 292,
        "entities_total": 755,
        "entities_with_coordinates": 173,
        "evidence_total": 577,
        "lifecycle_observations_current": 429,
        "projects_total": 354,
        "recorded_at": RECORDED_AT,
    }
    actual = {key: summary.get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"fresh v65 summary facts differ: {actual}")
    if summary["capacity_estimates_by_metric"].get("critical_it_mw") != 251:
        raise SystemExit("fresh v65 critical-IT row count differs")
    if summary["capacity_estimates_by_metric"].get("grid_connection_mw") != 23:
        raise SystemExit("fresh v65 grid-connection row count differs")
    if summary["capacity_estimates_by_stage"].get("planned") != 145:
        raise SystemExit("fresh v65 planned-capacity row count differs")
    if summary["capacity_estimates_by_stage"].get("contracted") != 18:
        raise SystemExit("fresh v65 contracted-capacity row count differs")
    if summary["entities_by_status"].get("under_construction") != 282:
        raise SystemExit("fresh v65 under-construction observation count differs")
    if summary["entities_by_status"].get("shell") != 27:
        raise SystemExit("fresh v65 shell observation count differs")

    manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    expected_manifest = {
        "entities": 755,
        "evidence_records": 468,
        "capacity_estimates": 512,
        "construction_pipeline_records": 387,
        "construction_source_signals": 292,
        "resolution_candidates": 5,
        "lifecycle_freshness_records": 429,
        "lifecycle_status_semantics": "last_observed",
        "current_status_inferred": False,
    }
    actual_manifest = {key: manifest.get(key) for key in expected_manifest}
    if actual_manifest != expected_manifest:
        raise SystemExit(f"fresh v65 manifest facts differ: {actual_manifest}")
    base_manifest = json.loads(
        (BASE_RELEASE / "manifest.json").read_text(encoding="utf-8")
    )
    if set(manifest["source_families"]) - set(base_manifest["source_families"]) != (
        NEW_SOURCE_FAMILIES
    ):
        raise SystemExit("fresh v65 source-family delta differs")
    if set(base_manifest["source_families"]) - set(manifest["source_families"]):
        raise SystemExit("fresh v65 removed a source family")
    if len(manifest["source_families"]) != 256:
        raise SystemExit("fresh v65 source-family count differs")
    if len(list(stage.iterdir())) != 14:
        raise SystemExit("fresh v65 release must contain exactly 14 files")
    _validate_freshness(stage)


def build_open_seed_v65() -> dict[str, object]:
    """Build and freeze v65 exactly once, refusing every publication collision."""

    with publication_lock():
        if DEFINITION.exists() or DEFINITION.is_symlink():
            raise SystemExit(
                f"definition already exists; refusing overwrite: {DEFINITION}"
            )
        if RELEASE.exists() or RELEASE.is_symlink():
            raise SystemExit(f"release already exists; refusing overwrite: {RELEASE}")
        if sha256(BASE_DEFINITION) != BASE_DEFINITION_SHA256:
            raise SystemExit("accepted v64 definition hash differs")
        if sha256(BASE_RELEASE / "manifest.json") != BASE_MANIFEST_SHA256:
            raise SystemExit("accepted v64 manifest hash differs")
        if tree_digest(BASE_RELEASE) != BASE_TREE_SHA256:
            raise SystemExit("accepted v64 release tree differs")

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
                prefix="open-seed-v65-db-", dir=staging_root
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
            validate_open_seed_release_v10(definition_stage, release_stage)
            promote_noreplace(release_stage, RELEASE)
            published_release = True
            promote_noreplace(definition_stage, DEFINITION)
            validate_open_seed_release_v10(DEFINITION, RELEASE)
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
    print(json.dumps(build_open_seed_v65(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
