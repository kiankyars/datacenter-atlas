"""Build and freeze official open seed v63 as the exact v62 successor.

V63 remains on the 2026-07-20 local research day. It adds only DataBank IAD6,
PowerHouse Irving Building 1, Core Scientific Dalton 4, and the source-bounded
QTS Fayetteville active-construction program. Lifecycle values remain dated,
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
from .open_seed_release_v8 import (
    ADDITION_PINS,
    AS_OF,
    OUT_OF_SCOPE_EXCLUSIONS,
    PENDING_NEXT_DAY_EXCLUSIONS,
    RECORDED_AT,
    RELEASE_ID,
    STALE_EXCLUSIONS,
    V11_RECORDED_AT,
    freshness_contract,
    validate_open_seed_release_v8,
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
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v62.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v62"
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v63.json"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v63.lock"

BASE_DEFINITION_SHA256 = (
    "e992f321a463c4a4316ed617dcc1efef505f01792fb91f6e13aded94e10b6f66"
)
BASE_MANIFEST_SHA256 = (
    "60c7172a20a7ff43a3644902d5c186b015e06228737ea8b39c7a5082d3d94ea6"
)
BASE_TREE_SHA256 = "71ec5c0a2f0af7d5557de5479f81fcb29dca0ae6342736681e3bdc12ac4ae8fb"

FRESHNESS_README = (
    "`lifecycle_freshness.csv` treats every published lifecycle value as a "
    "last-observed status, reports its age on the release date, and makes no "
    "current-construction inference. Its 0–90, 91–365, and over-365-day bands "
    "are review queues, not evidence that a status persisted. "
    "`current_status_classification` therefore remains `unknown` and "
    "`current_construction_claim` remains `false` for every row. DataBank IAD6 "
    "records planned 120 MW critical IT at the shared Culpeper address point. "
    "PowerHouse Irving Building 1 records shell top-out while the campus-only "
    "201 MW maximum utility-power value remains planned grid connection and is "
    "not allocated to the building. Core Scientific Dalton 4 records distinct "
    "contracted 145 MW critical IT and 220 MW grid connection. QTS Fayetteville "
    "records one source-bounded active campus construction program without "
    "inventing unnamed building projects, capacity, coordinates, or energy."
)

CORE_CAMPUS_KEY = "curated:core-scientific-dalton-4-data-center-campus"
CORE_PROJECT_KEY = f"{CORE_CAMPUS_KEY}:greenfield-build"
DATABANK_CAMPUS_KEY = "curated:databank-culpeper-campus"
DATABANK_IAD5_KEY = f"{DATABANK_CAMPUS_KEY}:iad5-current-build"
DATABANK_IAD6_KEY = f"{DATABANK_CAMPUS_KEY}:iad6-current-build"
POWERHOUSE_CAMPUS_KEY = "curated:powerhouse-irving-data-center-campus"
POWERHOUSE_PROJECT_KEY = f"{POWERHOUSE_CAMPUS_KEY}:building-1-current-build"
QTS_CAMPUS_KEY = "curated:qts-fayetteville-georgia-data-center-campus"
QTS_PROJECT_KEY = f"{QTS_CAMPUS_KEY}:active-campus-construction-program"

ADDED_ENTITY_KEYS = frozenset(
    {
        CORE_CAMPUS_KEY,
        CORE_PROJECT_KEY,
        DATABANK_IAD6_KEY,
        POWERHOUSE_CAMPUS_KEY,
        POWERHOUSE_PROJECT_KEY,
        QTS_CAMPUS_KEY,
        QTS_PROJECT_KEY,
    }
)
ADDED_PROJECT_KEYS = frozenset(
    {
        CORE_PROJECT_KEY,
        DATABANK_IAD6_KEY,
        POWERHOUSE_PROJECT_KEY,
        QTS_PROJECT_KEY,
    }
)
RELEVANT_ENTITY_KEYS = ADDED_ENTITY_KEYS | {DATABANK_CAMPUS_KEY}
MUTATED_ENTITY_KEYS = frozenset()

LIFECYCLE_CONTRACT = {
    (CORE_PROJECT_KEY, "under_construction", "2026-05-06"),
    (DATABANK_IAD6_KEY, "under_construction", "2026-02-19"),
    (POWERHOUSE_PROJECT_KEY, "shell", "2026-03-27"),
    (QTS_PROJECT_KEY, "under_construction", "2026-05-13"),
}
STATUS_WINNERS = {
    CORE_PROJECT_KEY: ("under_construction", "2026-05-06"),
    DATABANK_IAD6_KEY: ("under_construction", "2026-02-19"),
    POWERHOUSE_PROJECT_KEY: ("shell", "2026-03-27"),
    QTS_PROJECT_KEY: ("under_construction", "2026-05-13"),
}
CAPACITY_CONTRACT = {
    (
        CORE_PROJECT_KEY,
        "critical_it_mw",
        "contracted",
        "MW",
        145.0,
        145.0,
        145.0,
        "2026-04-21",
    ),
    (
        CORE_PROJECT_KEY,
        "grid_connection_mw",
        "contracted",
        "MW",
        220.0,
        220.0,
        220.0,
        "2026-04-21",
    ),
    (
        DATABANK_IAD6_KEY,
        "critical_it_mw",
        "planned",
        "MW",
        120.0,
        120.0,
        120.0,
        "2026-05-14",
    ),
    (
        POWERHOUSE_CAMPUS_KEY,
        "grid_connection_mw",
        "planned",
        "MW",
        201.0,
        201.0,
        201.0,
        "2026-07-20",
    ),
}

CSV_DELTA_CONTRACT = {
    "entities.csv": (
        730,
        7,
        "01cca34ce1e3db9919073c5c56734b7da0d27ff75a1919a071b3238d8e7d362f",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "evidence.csv": (
        444,
        8,
        "8e47c2defab67bfd9efd293e008861a955b9f16acb53a69c1e5fdcf2d206597f",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "capacity_estimates.csv": (
        502,
        4,
        "0b880458685a40a0acaeafd15ffe383286c3806c9070a50a6769df6276a796bf",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_pipeline.csv": (
        373,
        4,
        "038b51a2af68c3c608349450fbd575d9706e6043c4539f8ba6a45c807a16d4b9",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_source_signals.csv": (
        280,
        4,
        "fb25faa6df0cb7fca409626094644b0cf3ee41089776884452f5d4dea1c68467",
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
    "fayette_county_georgia_board_minutes",
    "powerhouse_data_centers_facility_pages",
    "powerhouse_data_centers_linkedin_company_posts",
}


@contextmanager
def publication_lock() -> Iterator[None]:
    """Hold an exclusive v63 publication lock without replacing any file."""

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


SOURCE_BOUNDARIES: dict[str, dict[str, Any]] = {
    "sources/curated-official-2026-07-20-core-scientific-dalton-4.json": {
        "schema_version": "1.1",
        "campus": {
            "stable_key": CORE_CAMPUS_KEY,
            "roles": {
                "developer": ["Core Scientific"],
                "operator": ["Core Scientific"],
            },
            "coordinates": None,
            "geometry": None,
        },
        "project": {
            "stable_key": CORE_PROJECT_KEY,
            "roles": {
                "developer": ["Core Scientific"],
                "operator": ["Core Scientific"],
                "tenant": ["CoreWeave"],
            },
            "coordinates": None,
            "geometry": None,
        },
        "lifecycle": [
            (
                "project",
                "under_construction",
                "2026-05-06",
                "authoritative_physical_status_update",
            )
        ],
        "operating_models": [
            ("project", "hyperscale_lease", "2026-04-21", "company_disclosure")
        ],
        "workloads": [
            (
                "project",
                "ai_specialized_unspecified",
                "2026-04-21",
                "company_disclosure",
            )
        ],
        "capacities": [
            (
                "project",
                "critical_it_mw",
                "contracted",
                "MW",
                145.0,
                145.0,
                145.0,
                "2026-04-21",
            ),
            (
                "project",
                "grid_connection_mw",
                "contracted",
                "MW",
                220.0,
                220.0,
                220.0,
                "2026-04-21",
            ),
        ],
    },
    "sources/curated-official-2026-07-20-databank-iad6-culpeper.json": {
        "schema_version": "1.1",
        "campus": {
            "stable_key": DATABANK_CAMPUS_KEY,
            "roles": {"developer": ["DataBank"], "operator": ["DataBank"]},
            "coordinates": {
                "latitude": 38.45185992,
                "longitude": -77.98378765,
            },
            "geometry": {
                "type": "Point",
                "coordinates": [-77.98378765, 38.45185992],
            },
        },
        "project": {
            "stable_key": DATABANK_IAD6_KEY,
            "roles": {"developer": ["DataBank"], "operator": ["DataBank"]},
            "coordinates": {
                "latitude": 38.45185992,
                "longitude": -77.98378765,
            },
            "geometry": {
                "type": "Point",
                "coordinates": [-77.98378765, 38.45185992],
            },
        },
        "lifecycle": [
            (
                "project",
                "under_construction",
                "2026-02-19",
                "authoritative_physical_status_update",
            )
        ],
        "operating_models": [
            ("project", "colocation", "2026-05-14", "company_disclosure")
        ],
        "workloads": [],
        "capacities": [
            (
                "project",
                "critical_it_mw",
                "planned",
                "MW",
                120.0,
                120.0,
                120.0,
                "2026-05-14",
            )
        ],
    },
    "sources/curated-official-2026-07-20-powerhouse-irving-building-1-topout.json": {
        "schema_version": "1.1",
        "campus": {
            "stable_key": POWERHOUSE_CAMPUS_KEY,
            "roles": {"developer": ["PowerHouse Data Centers"]},
            "coordinates": None,
            "geometry": None,
        },
        "project": {
            "stable_key": POWERHOUSE_PROJECT_KEY,
            "roles": {
                "developer": ["PowerHouse Data Centers"],
                "contractor": ["Brasfield & Gorrie, LLC"],
            },
            "coordinates": None,
            "geometry": None,
        },
        "lifecycle": [
            (
                "project",
                "shell",
                "2026-03-27",
                "authoritative_physical_status_update",
            )
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [
            (
                "campus",
                "grid_connection_mw",
                "planned",
                "MW",
                201.0,
                201.0,
                201.0,
                "2026-07-20",
            )
        ],
    },
    "sources/curated-official-2026-07-20-qts-fayetteville-active-construction-program.json": {
        "schema_version": "1.1",
        "campus": {
            "stable_key": QTS_CAMPUS_KEY,
            "roles": {},
            "coordinates": None,
            "geometry": None,
        },
        "project": {
            "stable_key": QTS_PROJECT_KEY,
            "roles": {},
            "coordinates": None,
            "geometry": None,
        },
        "lifecycle": [
            (
                "project",
                "under_construction",
                "2026-05-13",
                "authoritative_physical_status_update",
            )
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    },
}


def _validate_source_boundary(path: Path, document: Mapping[str, Any]) -> None:
    relative = str(path.relative_to(ROOT))
    expected = SOURCE_BOUNDARIES.get(relative)
    if expected is None:
        return
    if _projected_source(document) != expected:
        raise SystemExit(f"v63 source boundary differs: {relative}")


def selected_inputs(base: Mapping[str, Any]) -> tuple[list[dict[str, str]], list[Path]]:
    """Return the exact four-addition v62 successor."""

    if base.get("release_id") != "2026-07-20-open-seed-v62":
        raise SystemExit("v63 base must be exactly frozen v62")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 350:
        raise SystemExit("frozen v62 curated inventory differs")
    pins: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise SystemExit("frozen v62 curated row is invalid")
        source_path, digest = row["path"], row["sha256"]
        if (
            source_path in pins
            or not isinstance(source_path, str)
            or not isinstance(digest, str)
        ):
            raise SystemExit("frozen v62 curated inventory is invalid")
        pins[source_path] = digest
    for source_path, digest in ADDITION_PINS.items():
        if source_path in pins:
            raise SystemExit("a v63 addition already occurs in v62")
        pins[source_path] = digest
    excluded = STALE_EXCLUSIONS | PENDING_NEXT_DAY_EXCLUSIONS | OUT_OF_SCOPE_EXCLUSIONS
    if excluded & set(pins):
        raise SystemExit("an excluded v63 source was selected")
    if len(pins) != 354:
        raise SystemExit(f"expected 354 unique v63 inputs, found {len(pins)}")

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
        "entities": 737,
        "evidence": 557,
        "lifecycle_observations": 434,
        "capacity_estimates": 507,
        "entity_snapshots": 757,
        "operating_model_observations": 55,
        "workload_observations": 124,
    }
    if counts != expected:
        raise SystemExit(f"fresh v63 database projection differs: {counts}")

    relevant = tuple(sorted(RELEVANT_ENTITY_KEYS))
    placeholders = ",".join("?" for _ in relevant)
    entity_rows = connection.execute(
        f"SELECT stable_key, kind FROM entities WHERE stable_key IN ({placeholders})",
        relevant,
    ).fetchall()
    if {row[0] for row in entity_rows} != RELEVANT_ENTITY_KEYS:
        raise SystemExit("v63 relevant identity set differs")
    if {row[0] for row in entity_rows if row[1] == "project"} != ADDED_PROJECT_KEYS:
        raise SystemExit("v63 project identity set differs")

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
        CORE_PROJECT_KEY: CORE_CAMPUS_KEY,
        DATABANK_IAD6_KEY: DATABANK_CAMPUS_KEY,
        POWERHOUSE_PROJECT_KEY: POWERHOUSE_CAMPUS_KEY,
        QTS_PROJECT_KEY: QTS_CAMPUS_KEY,
    }
    if {row[0]: row[1] for row in target_rows} != expected_targets:
        raise SystemExit("v63 project-to-campus nesting differs")

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
        raise SystemExit("v63 lifecycle delta differs")

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
        raise SystemExit(f"v63 typed capacity delta differs: {capacity_rows}")

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
        raise SystemExit("v63 snapshot identity set differs")
    expected_roles = {
        CORE_CAMPUS_KEY: {
            "role:developer": "Core Scientific",
            "role:operator": "Core Scientific",
        },
        CORE_PROJECT_KEY: {
            "role:developer": "Core Scientific",
            "role:operator": "Core Scientific",
            "role:tenant": "CoreWeave",
        },
        DATABANK_CAMPUS_KEY: {
            "role:developer": "DataBank",
            "role:operator": "DataBank",
        },
        DATABANK_IAD6_KEY: {
            "role:developer": "DataBank",
            "role:operator": "DataBank",
        },
        POWERHOUSE_CAMPUS_KEY: {"role:developer": "PowerHouse Data Centers"},
        POWERHOUSE_PROJECT_KEY: {
            "role:contractor": "Brasfield & Gorrie, LLC",
            "role:developer": "PowerHouse Data Centers",
        },
        QTS_CAMPUS_KEY: {},
        QTS_PROJECT_KEY: {},
    }
    for stable_key, latitude, longitude, geometry_json, tags_json in snapshot_rows:
        tags = json.loads(tags_json)
        actual_roles = {
            key: value for key, value in tags.items() if key.startswith("role:")
        }
        if actual_roles != expected_roles[stable_key]:
            raise SystemExit(f"v63 role tag differs: {stable_key}")
        if stable_key in {DATABANK_CAMPUS_KEY, DATABANK_IAD6_KEY}:
            if (
                latitude != 38.45185992
                or longitude != -77.98378765
                or json.loads(geometry_json)
                != {
                    "type": "Point",
                    "coordinates": [-77.98378765, 38.45185992],
                }
            ):
                raise SystemExit(f"v63 DataBank address point differs: {stable_key}")
        elif latitude is not None or longitude is not None or geometry_json is not None:
            raise SystemExit(f"v63 source gained invented geometry: {stable_key}")

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
    if {tuple(row) for row in model_rows} != {
        (CORE_PROJECT_KEY, "hyperscale_lease", "2026-04-21", "company_disclosure"),
        (DATABANK_IAD6_KEY, "colocation", "2026-05-14", "company_disclosure"),
    }:
        raise SystemExit("v63 operating-model boundary differs")

    workload_rows = connection.execute(
        f"""
        SELECT entities.stable_key, workload_observations.workload,
               workload_observations.as_of_date,
               workload_observations.method
        FROM workload_observations
        JOIN entities ON entities.id = workload_observations.entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        relevant,
    ).fetchall()
    if [tuple(row) for row in workload_rows] != [
        (
            CORE_PROJECT_KEY,
            "ai_specialized_unspecified",
            "2026-04-21",
            "company_disclosure",
        )
    ]:
        raise SystemExit("v63 workload boundary differs")

    iad5_rows = connection.execute(
        """
        SELECT metric, stage, unit, base, as_of_date
        FROM capacity_estimates
        JOIN entities ON entities.id = capacity_estimates.entity_id
        WHERE entities.stable_key = ?
        """,
        (DATABANK_IAD5_KEY,),
    ).fetchall()
    if [tuple(row) for row in iad5_rows] != [
        ("critical_it_mw", "planned", "MW", 72.0, "2026-05-14")
    ]:
        raise SystemExit("v63 changed the distinct IAD5 capacity boundary")


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
        raise SystemExit("fresh Epoch import result differs from v62")
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
    """Add the v63 last-observed carrier and bind it into the manifest."""

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
            raise SystemExit(f"fresh v63 CSV delta differs: {filename}: {actual}")

    before_entities = _rows_by_key(BASE_RELEASE / "entities.csv")
    after_entities = _rows_by_key(stage / "entities.csv")
    if set(after_entities) - set(before_entities) != ADDED_ENTITY_KEYS:
        raise SystemExit("v63 added entity set differs")
    if set(before_entities) - set(after_entities):
        raise SystemExit("v63 unexpectedly removed an entity identity")
    changed_common = {
        key
        for key in before_entities.keys() & after_entities.keys()
        if before_entities[key] != after_entities[key]
    }
    if changed_common:
        raise SystemExit("v63 unexpectedly changed a frozen-v62 entity row")
    for key, (status, observed) in STATUS_WINNERS.items():
        row = after_entities[key]
        if row["status"] != status or row["status_as_of"] != observed:
            raise SystemExit(f"v63 status winner differs: {key}")


def _freshness_class(age_days: int) -> str:
    if age_days <= 90:
        return "recent_0_90_days"
    if age_days <= 365:
        return "aging_91_365_days"
    return "stale_over_365_days"


def _validate_freshness(stage: Path) -> None:
    with (stage / FRESHNESS_FILENAME).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 419 or tuple(rows[0]) != FRESHNESS_FIELDS:
        raise SystemExit(f"fresh v63 freshness shape differs: {len(rows)}")
    if any(
        row["status_semantics"] != "last_observed"
        or row["current_status_classification"] != "unknown"
        or row["current_construction_claim"] != "false"
        for row in rows
    ):
        raise SystemExit("v63 freshness rows infer current status")
    by_key = {row["stable_key"]: row for row in rows}
    for key, (status, observed) in STATUS_WINNERS.items():
        row = by_key[key]
        if (
            row["last_observed_status"] != status
            or row["last_observed_status_as_of"] != observed
            or row["current_status_classification"] != "unknown"
            or row["current_construction_claim"] != "false"
        ):
            raise SystemExit(f"v63 freshness semantics differ: {key}")
    if any(
        "stt-johor" in row["stable_key"]
        or "pure-dc-ams01" in row["stable_key"]
        or "ecodatacenter-falun" in row["stable_key"]
        for row in rows
    ):
        raise SystemExit("an excluded or unseeded source leaked into v63 freshness")
    as_of_date = date.fromisoformat(AS_OF)
    classes = Counter()
    for row in rows:
        expected_age = as_of_date - date.fromisoformat(
            row["last_observed_status_as_of"]
        )
        if row["observation_age_days"] != str(expected_age.days):
            raise SystemExit("v63 freshness age differs")
        expected_class = _freshness_class(expected_age.days)
        if row["freshness_class"] != expected_class:
            raise SystemExit("v63 freshness class differs")
        classes[expected_class] += 1
    if classes != {
        "recent_0_90_days": 215,
        "aging_91_365_days": 177,
        "stale_over_365_days": 27,
    }:
        raise SystemExit(f"v63 freshness distribution differs: {classes}")


def _validate_release_facts(stage: Path) -> None:
    summary = json.loads((stage / "summary.json").read_text(encoding="utf-8"))
    expected = {
        "campuses_total": 393,
        "campuses_with_coordinates": 123,
        "capacity_estimates_current": 506,
        "construction_pipeline_records": 377,
        "construction_source_signals": 284,
        "entities_total": 737,
        "entities_with_coordinates": 173,
        "evidence_total": 557,
        "lifecycle_observations_current": 419,
        "projects_total": 344,
        "recorded_at": RECORDED_AT,
    }
    actual = {key: summary.get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"fresh v63 summary facts differ: {actual}")
    if summary["capacity_estimates_by_metric"].get("critical_it_mw") != 248:
        raise SystemExit("fresh v63 critical-IT row count differs")
    if summary["capacity_estimates_by_metric"].get("grid_connection_mw") != 22:
        raise SystemExit("fresh v63 grid-connection row count differs")
    if summary["capacity_estimates_by_stage"].get("planned") != 139:
        raise SystemExit("fresh v63 planned-capacity row count differs")
    if summary["capacity_estimates_by_stage"].get("contracted") != 18:
        raise SystemExit("fresh v63 contracted-capacity row count differs")
    if summary["entities_by_status"].get("under_construction") != 272:
        raise SystemExit("fresh v63 under-construction observation count differs")
    if summary["entities_by_status"].get("shell") != 27:
        raise SystemExit("fresh v63 shell observation count differs")

    manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    expected_manifest = {
        "entities": 737,
        "evidence_records": 452,
        "capacity_estimates": 506,
        "construction_pipeline_records": 377,
        "construction_source_signals": 284,
        "resolution_candidates": 5,
        "lifecycle_freshness_records": 419,
        "lifecycle_status_semantics": "last_observed",
        "current_status_inferred": False,
    }
    actual_manifest = {key: manifest.get(key) for key in expected_manifest}
    if actual_manifest != expected_manifest:
        raise SystemExit(f"fresh v63 manifest facts differ: {actual_manifest}")
    base_manifest = json.loads(
        (BASE_RELEASE / "manifest.json").read_text(encoding="utf-8")
    )
    if set(manifest["source_families"]) - set(base_manifest["source_families"]) != (
        NEW_SOURCE_FAMILIES
    ):
        raise SystemExit("fresh v63 source-family delta differs")
    if set(base_manifest["source_families"]) - set(manifest["source_families"]):
        raise SystemExit("fresh v63 removed a source family")
    if len(manifest["source_families"]) != 246:
        raise SystemExit("fresh v63 source-family count differs")
    if len(list(stage.iterdir())) != 14:
        raise SystemExit("fresh v63 release must contain exactly 14 files")
    _validate_freshness(stage)


def build_open_seed_v63() -> dict[str, object]:
    """Build and freeze v63 exactly once, refusing every publication collision."""

    with publication_lock():
        if DEFINITION.exists() or DEFINITION.is_symlink():
            raise SystemExit(
                f"definition already exists; refusing overwrite: {DEFINITION}"
            )
        if RELEASE.exists() or RELEASE.is_symlink():
            raise SystemExit(f"release already exists; refusing overwrite: {RELEASE}")
        if sha256(BASE_DEFINITION) != BASE_DEFINITION_SHA256:
            raise SystemExit("accepted v62 definition hash differs")
        if sha256(BASE_RELEASE / "manifest.json") != BASE_MANIFEST_SHA256:
            raise SystemExit("accepted v62 manifest hash differs")
        if tree_digest(BASE_RELEASE) != BASE_TREE_SHA256:
            raise SystemExit("accepted v62 release tree differs")

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
                prefix="open-seed-v63-db-", dir=staging_root
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
            validate_open_seed_release_v8(definition_stage, release_stage)
            promote_noreplace(release_stage, RELEASE)
            published_release = True
            promote_noreplace(definition_stage, DEFINITION)
            validate_open_seed_release_v8(DEFINITION, RELEASE)
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
    print(json.dumps(build_open_seed_v63(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
