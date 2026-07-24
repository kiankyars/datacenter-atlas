"""Build and freeze official open seed v62 as the exact v61 successor.

V62 remains on the 2026-07-20 local research day. It adds only the finalized
Applied Digital Building 2 Phase 1 and DataBank IAD5 records. Lifecycle values
remain last-observed facts, never current-status inferences.
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
from .open_seed_release_v7 import (
    ADDITION_PINS,
    AS_OF,
    OUT_OF_SCOPE_EXCLUSIONS,
    PENDING_NEXT_DAY_EXCLUSIONS,
    RECORDED_AT,
    RELEASE_ID,
    STALE_EXCLUSIONS,
    V11_RECORDED_AT,
    freshness_contract,
    validate_open_seed_release_v7,
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
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v61.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v61"
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v62.json"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v62.lock"

BASE_DEFINITION_SHA256 = (
    "c407c73a069783ea75de8e3bc86bbfb8a15d71abb67de33e8ba3d3acc5a428e6"
)
BASE_MANIFEST_SHA256 = (
    "6388b58b043f43fa2cdc02af31504cf18cc2ec334e14f2f2075f52b15204fd14"
)
BASE_TREE_SHA256 = "de9a924113b5fae4ace596fdbd469f52a79646d0de677e7bcf17aedfa09693f2"

FRESHNESS_README = (
    "`lifecycle_freshness.csv` treats every published lifecycle value as a "
    "last-observed status, reports its age on the release date, and makes no "
    "current-construction inference. Its 0–90, 91–365, and over-365-day bands "
    "are review queues, not evidence that a status persisted. "
    "`current_status_classification` therefore remains `unknown` and "
    "`current_construction_claim` remains `false` for every row. The Applied "
    "Digital child records only the operational 75 MW Phase 1; the 150 MW "
    "parent remains a separate under-construction observation. DataBank IAD5 "
    "records planned 72 MW critical IT and a Virginia-government address "
    "point; the point is not a parcel, footprint, boundary, or site count. "
    "Pure AMS01 remains pending the next local release day."
)

ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:applied-digital-polaris-forge-1:second-150mw-facility:phase-1",
        "curated:databank-culpeper-campus",
        "curated:databank-culpeper-campus:iad5-current-build",
    }
)
ADDED_PROJECT_KEYS = frozenset(
    {
        "curated:applied-digital-polaris-forge-1:second-150mw-facility:phase-1",
        "curated:databank-culpeper-campus:iad5-current-build",
    }
)
MUTATED_ENTITY_KEYS = frozenset()
APPLIED_CAMPUS_KEY = "epoch-ai:data-center:ae2c8749-c97f-5512-a0ad-a40ed8df37ce"
APPLIED_PARENT_KEY = "curated:applied-digital-polaris-forge-1:second-150mw-facility"
APPLIED_PHASE_KEY = f"{APPLIED_PARENT_KEY}:phase-1"
DATABANK_CAMPUS_KEY = "curated:databank-culpeper-campus"
DATABANK_PROJECT_KEY = f"{DATABANK_CAMPUS_KEY}:iad5-current-build"

LIFECYCLE_CONTRACT = {
    (
        APPLIED_PHASE_KEY,
        "operational",
        "2026-07-01",
    ),
    (
        DATABANK_PROJECT_KEY,
        "under_construction",
        "2026-05-14",
    ),
}

CAPACITY_CONTRACT = {
    APPLIED_PHASE_KEY: (
        "critical_it_mw",
        "operational",
        "MW",
        75.0,
        75.0,
        75.0,
        "2026-07-01",
    ),
    DATABANK_PROJECT_KEY: (
        "critical_it_mw",
        "planned",
        "MW",
        72.0,
        72.0,
        72.0,
        "2026-05-14",
    ),
}
STATUS_WINNERS = {
    APPLIED_PHASE_KEY: ("operational", "2026-07-01"),
    DATABANK_PROJECT_KEY: ("under_construction", "2026-05-14"),
}

CSV_DELTA_CONTRACT = {
    "entities.csv": (727, 3, "45ef416336dc5b85baf2f86ecb99d6e82f9929ca2ad3c05c9572b7eaa1711499", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
    "evidence.csv": (440, 4, "afb65f8ad35f36eb7251754f265eee9ae1650a1a25ac3b6998ca4fd8ab5e17c8", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
    "capacity_estimates.csv": (500, 2, "d8c397266e0366fef691c82e739314b0c52b7bea17b8cd2d2bb21e173d993705", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
    "construction_pipeline.csv": (372, 1, "6ec868b074fa1e404f3bf6080623cb478fd64cb49b9b61b1f41e3e379f82a13c", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
    "construction_source_signals.csv": (279, 1, "5575df298d430ff1bbae21209b6de4600780447c08e55d46532dab812254c5b0", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
    "resolution_candidates.csv": (5, 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
}

NEW_SOURCE_FAMILIES = {
    "applied_digital_investor_relations_press_releases",
    "databank_official_linkedin",
    "virginia_dhcd_vati_applications",
}


@contextmanager
def publication_lock() -> Iterator[None]:
    """Hold an exclusive v62 publication lock without replacing any file."""

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
        raise SystemExit(f"v62 successor source must use schema 1.1: {relative}")
    campus = document.get("campus")
    project = document.get("project")
    if not isinstance(campus, dict) or not isinstance(project, dict):
        raise SystemExit(f"v62 source must contain one campus and one project: {relative}")
    project_key = project["stable_key"]
    if project_key not in ADDED_PROJECT_KEYS:
        raise SystemExit(f"v62 project identity differs: {relative}")
    if project_key == APPLIED_PHASE_KEY:
        if campus["stable_key"] != APPLIED_CAMPUS_KEY or not project_key.startswith(
            APPLIED_PARENT_KEY + ":"
        ):
            raise SystemExit(f"v62 Applied phase identity differs: {relative}")
        expected_roles = {
            "developer": ["Applied Digital"],
            "operator": ["Applied Digital"],
        }
        expected_coordinates = None
        expected_geometry = None
        expected_models = ["colocation"]
        expected_workloads = ["ai_specialized_unspecified"]
    else:
        if campus["stable_key"] != DATABANK_CAMPUS_KEY or not project_key.startswith(
            DATABANK_CAMPUS_KEY + ":"
        ):
            raise SystemExit(f"v62 DataBank identity differs: {relative}")
        expected_roles = {
            "developer": ["DataBank"],
            "operator": ["DataBank"],
        }
        expected_coordinates = {
            "latitude": 38.45185992,
            "longitude": -77.98378765,
        }
        expected_geometry = {
            "type": "Point",
            "coordinates": [-77.98378765, 38.45185992],
        }
        expected_models = ["colocation"]
        expected_workloads = []
    for entity in (campus, project):
        if entity.get("roles") != expected_roles:
            raise SystemExit(f"v62 source role boundary differs: {relative}")
        if entity.get("coordinates") != expected_coordinates:
            raise SystemExit(f"v62 source coordinate boundary differs: {relative}")
        if entity.get("geometry") != expected_geometry:
            raise SystemExit(f"v62 source geometry boundary differs: {relative}")
    if [row.get("value") for row in document.get("operating_models", [])] != (
        expected_models
    ):
        raise SystemExit(f"v62 operating-model boundary differs: {relative}")
    if [row.get("value") for row in document.get("workloads", [])] != (
        expected_workloads
    ):
        raise SystemExit(f"v62 workload boundary differs: {relative}")
    capacities = document.get("capacities", [])
    if len(capacities) != 1:
        raise SystemExit(f"v62 source must contain one typed capacity: {relative}")
    expected_capacity = CAPACITY_CONTRACT[project_key]
    capacity = capacities[0]
    actual_capacity = (
        capacity.get("metric"),
        capacity.get("stage"),
        capacity.get("unit"),
        float(capacity.get("low")),
        float(capacity.get("base")),
        float(capacity.get("high")),
        capacity.get("as_of_date"),
    )
    if actual_capacity != expected_capacity:
        raise SystemExit(f"v62 typed-capacity boundary differs: {relative}")


def selected_inputs(base: Mapping[str, Any]) -> tuple[list[dict[str, str]], list[Path]]:
    """Return the exact two-addition v61 successor."""

    if base.get("release_id") != "2026-07-20-open-seed-v61":
        raise SystemExit("v62 base must be exactly frozen v61")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 348:
        raise SystemExit("frozen v61 curated inventory differs")
    pins: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise SystemExit("frozen v61 curated row is invalid")
        path, digest = row["path"], row["sha256"]
        if path in pins or not isinstance(path, str) or not isinstance(digest, str):
            raise SystemExit("frozen v61 curated inventory is invalid")
        pins[path] = digest
    for path, digest in ADDITION_PINS.items():
        if path in pins:
            raise SystemExit("a v62 addition already occurs in v61")
        pins[path] = digest
    excluded = STALE_EXCLUSIONS | PENDING_NEXT_DAY_EXCLUSIONS | OUT_OF_SCOPE_EXCLUSIONS
    if excluded & set(pins):
        raise SystemExit("an excluded v62 source was selected")
    if len(pins) != 350:
        raise SystemExit(f"expected 350 unique v62 inputs, found {len(pins)}")

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
        "entities": 730,
        "evidence": 546,
        "lifecycle_observations": 430,
        "capacity_estimates": 503,
        "entity_snapshots": 750,
        "operating_model_observations": 53,
        "workload_observations": 123,
    }
    if counts != expected:
        raise SystemExit(f"fresh v62 database projection differs: {counts}")

    relevant = tuple(sorted(ADDED_ENTITY_KEYS | MUTATED_ENTITY_KEYS))
    placeholders = ",".join("?" for _ in relevant)
    entity_rows = connection.execute(
        f"SELECT stable_key, kind FROM entities WHERE stable_key IN ({placeholders})",
        relevant,
    ).fetchall()
    if {row[0] for row in entity_rows} != ADDED_ENTITY_KEYS:
        raise SystemExit("v62 entity identity set differs")
    if {row[0] for row in entity_rows if row[1] == "project"} != ADDED_PROJECT_KEYS:
        raise SystemExit("v62 project identity set differs")

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
        APPLIED_PHASE_KEY: APPLIED_CAMPUS_KEY,
        DATABANK_PROJECT_KEY: DATABANK_CAMPUS_KEY,
    }
    if {row[0]: row[1] for row in target_rows} != expected_targets:
        raise SystemExit("v62 project-to-campus nesting differs")

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
        raise SystemExit("v62 lifecycle delta differs")

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
        raise SystemExit(f"v62 typed capacity delta differs: {actual_capacity}")

    coordinate_count = connection.execute(
        f"""
        SELECT COUNT(*) FROM entity_snapshots
        JOIN entities ON entities.id = entity_snapshots.entity_id
        WHERE entities.stable_key IN ({placeholders})
          AND (latitude IS NOT NULL OR longitude IS NOT NULL OR geometry_json IS NOT NULL)
        """,
        relevant,
    ).fetchone()[0]
    if coordinate_count != 2:
        raise SystemExit("v62 coordinate-bearing entity count differs")

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
    if {row[0] for row in snapshot_rows} != ADDED_ENTITY_KEYS:
        raise SystemExit("v62 added snapshot identity set differs")
    expected_role_tags = {
        APPLIED_PHASE_KEY: {
            "role:developer": "Applied Digital",
            "role:operator": "Applied Digital",
        },
        DATABANK_CAMPUS_KEY: {
            "role:developer": "DataBank",
            "role:operator": "DataBank",
        },
        DATABANK_PROJECT_KEY: {
            "role:developer": "DataBank",
            "role:operator": "DataBank",
        },
    }
    for stable_key, latitude, longitude, geometry_json, tags_json in snapshot_rows:
        tags = json.loads(tags_json)
        if {key: value for key, value in tags.items() if key.startswith("role:")} != (
            expected_role_tags[stable_key]
        ):
            raise SystemExit(f"v62 role tag differs: {stable_key}")
        if stable_key == APPLIED_PHASE_KEY:
            if latitude is not None or longitude is not None or geometry_json is not None:
                raise SystemExit("v62 Applied phase gained invented geometry")
        elif (
            latitude != 38.45185992
            or longitude != -77.98378765
            or json.loads(geometry_json)
            != {
                "type": "Point",
                "coordinates": [-77.98378765, 38.45185992],
            }
        ):
            raise SystemExit(f"v62 DataBank address point differs: {stable_key}")

    model_rows = connection.execute(
        """
        SELECT entities.stable_key, operating_model_observations.operating_model,
               operating_model_observations.as_of_date,
               operating_model_observations.method
        FROM operating_model_observations
        JOIN entities ON entities.id = operating_model_observations.entity_id
        WHERE entities.stable_key IN (?, ?)
        """,
        (APPLIED_PHASE_KEY, DATABANK_PROJECT_KEY),
    ).fetchall()
    if {tuple(row) for row in model_rows} != {
        (APPLIED_PHASE_KEY, "colocation", "2026-07-01", "company_disclosure"),
        (DATABANK_PROJECT_KEY, "colocation", "2026-05-14", "company_disclosure"),
    }:
        raise SystemExit("v62 colocation observations differ")

    workload_rows = connection.execute(
        """
        SELECT entities.stable_key, workload_observations.workload,
               workload_observations.as_of_date
        FROM workload_observations
        JOIN entities ON entities.id = workload_observations.entity_id
        WHERE entities.stable_key IN (?, ?)
        """,
        (APPLIED_PHASE_KEY, DATABANK_PROJECT_KEY),
    ).fetchall()
    if [tuple(row) for row in workload_rows] != [
        (APPLIED_PHASE_KEY, "ai_specialized_unspecified", "2026-07-01")
    ]:
        raise SystemExit("v62 workload boundary differs")

    parent_rows = connection.execute(
        """
        SELECT lifecycle_observations.status, lifecycle_observations.as_of_date
        FROM lifecycle_observations
        JOIN entities ON entities.id = lifecycle_observations.entity_id
        WHERE entities.stable_key = ?
        ORDER BY lifecycle_observations.as_of_date
        """,
        (APPLIED_PARENT_KEY,),
    ).fetchall()
    if [tuple(row) for row in parent_rows] != [
        ("under_construction", "2026-04-08"),
    ]:
        raise SystemExit("v62 changed Applied 150 MW parent lifecycle history")


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
        raise SystemExit("fresh Epoch import result differs from v61")
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
    """Add the v62 last-observed carrier and bind it into the manifest."""

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
            raise SystemExit(f"fresh v62 CSV delta differs: {filename}: {actual}")

    before_entities = _rows_by_key(BASE_RELEASE / "entities.csv")
    after_entities = _rows_by_key(stage / "entities.csv")
    if set(after_entities) - set(before_entities) != ADDED_ENTITY_KEYS:
        raise SystemExit("v62 added entity set differs")
    if set(before_entities) - set(after_entities):
        raise SystemExit("v62 unexpectedly removed an entity identity")
    changed_common = {
        key
        for key in before_entities.keys() & after_entities.keys()
        if before_entities[key] != after_entities[key]
    }
    if changed_common:
        raise SystemExit("v62 unexpectedly changed a frozen-v61 entity row")
    if before_entities[APPLIED_PARENT_KEY] != after_entities[APPLIED_PARENT_KEY]:
        raise SystemExit("v62 changed the Applied 150 MW parent entity row")
    for key, (status, observed) in STATUS_WINNERS.items():
        row = after_entities[key]
        if row["status"] != status or row["status_as_of"] != observed:
            raise SystemExit(f"v62 status winner differs: {key}")


def _freshness_class(age_days: int) -> str:
    if age_days <= 90:
        return "recent_0_90_days"
    if age_days <= 365:
        return "aging_91_365_days"
    return "stale_over_365_days"


def _validate_freshness(stage: Path) -> None:
    with (stage / FRESHNESS_FILENAME).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 415 or tuple(rows[0]) != FRESHNESS_FIELDS:
        raise SystemExit(f"fresh v62 freshness shape differs: {len(rows)}")
    if any(
        row["status_semantics"] != "last_observed"
        or row["current_status_classification"] != "unknown"
        or row["current_construction_claim"] != "false"
        for row in rows
    ):
        raise SystemExit("v62 freshness rows infer current status")
    by_key = {row["stable_key"]: row for row in rows}
    for key, (status, observed) in STATUS_WINNERS.items():
        row = by_key[key]
        if (
            row["last_observed_status"] != status
            or row["last_observed_status_as_of"] != observed
            or row["current_status_classification"] != "unknown"
            or row["current_construction_claim"] != "false"
        ):
            raise SystemExit(f"v62 freshness semantics differ: {key}")
    if any(
        "stt-johor" in row["stable_key"]
        or "pure-dc-ams01" in row["stable_key"]
        for row in rows
    ):
        raise SystemExit("an excluded source leaked into v62 freshness output")
    as_of_date = date.fromisoformat(AS_OF)
    classes = Counter()
    for row in rows:
        expected_age = as_of_date - date.fromisoformat(row["last_observed_status_as_of"])
        if row["observation_age_days"] != str(expected_age.days):
            raise SystemExit("v62 freshness age differs")
        expected_class = _freshness_class(expected_age.days)
        if row["freshness_class"] != expected_class:
            raise SystemExit("v62 freshness class differs")
        classes[expected_class] += 1
    if classes != {
        "recent_0_90_days": 213,
        "aging_91_365_days": 175,
        "stale_over_365_days": 27,
    }:
        raise SystemExit(f"v62 freshness distribution differs: {classes}")


def _validate_release_facts(stage: Path) -> None:
    summary = json.loads((stage / "summary.json").read_text(encoding="utf-8"))
    expected = {
        "campuses_total": 390,
        "campuses_with_coordinates": 123,
        "capacity_estimates_current": 502,
        "construction_pipeline_records": 373,
        "construction_source_signals": 280,
        "entities_total": 730,
        "entities_with_coordinates": 172,
        "evidence_total": 546,
        "lifecycle_observations_current": 415,
        "projects_total": 340,
        "recorded_at": RECORDED_AT,
    }
    actual = {key: summary.get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"fresh v62 summary facts differ: {actual}")
    if summary["capacity_estimates_by_metric"].get("critical_it_mw") != 246:
        raise SystemExit("fresh v62 critical-IT row count differs")
    if summary["capacity_estimates_by_stage"].get("planned") != 137:
        raise SystemExit("fresh v62 planned-capacity row count differs")
    if summary["capacity_estimates_by_stage"].get("operational") != 171:
        raise SystemExit("fresh v62 operational-capacity row count differs")
    if summary["entities_by_status"].get("under_construction") != 269:
        raise SystemExit("fresh v62 under-construction observation count differs")
    if summary["entities_by_status"].get("commissioning") != 2:
        raise SystemExit("fresh v62 commissioning observation count differs")
    if summary["entities_by_status"].get("operational") != 42:
        raise SystemExit("fresh v62 operational observation count differs")

    manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    expected_manifest = {
        "entities": 730,
        "evidence_records": 444,
        "capacity_estimates": 502,
        "construction_pipeline_records": 373,
        "construction_source_signals": 280,
        "resolution_candidates": 5,
        "lifecycle_freshness_records": 415,
        "lifecycle_status_semantics": "last_observed",
        "current_status_inferred": False,
    }
    actual_manifest = {key: manifest.get(key) for key in expected_manifest}
    if actual_manifest != expected_manifest:
        raise SystemExit(f"fresh v62 manifest facts differ: {actual_manifest}")
    base_manifest = json.loads(
        (BASE_RELEASE / "manifest.json").read_text(encoding="utf-8")
    )
    if set(manifest["source_families"]) - set(base_manifest["source_families"]) != (
        NEW_SOURCE_FAMILIES
    ):
        raise SystemExit("fresh v62 source-family delta differs")
    if set(base_manifest["source_families"]) - set(manifest["source_families"]):
        raise SystemExit("fresh v62 removed a source family")
    if len(manifest["source_families"]) != 243:
        raise SystemExit("fresh v62 source-family count differs")
    if len(list(stage.iterdir())) != 14:
        raise SystemExit("fresh v62 release must contain exactly 14 files")
    _validate_freshness(stage)


def build_open_seed_v62() -> dict[str, object]:
    """Build and freeze v62 exactly once, refusing every publication collision."""

    with publication_lock():
        if DEFINITION.exists() or DEFINITION.is_symlink():
            raise SystemExit(f"definition already exists; refusing overwrite: {DEFINITION}")
        if RELEASE.exists() or RELEASE.is_symlink():
            raise SystemExit(f"release already exists; refusing overwrite: {RELEASE}")
        if sha256(BASE_DEFINITION) != BASE_DEFINITION_SHA256:
            raise SystemExit("accepted v61 definition hash differs")
        if sha256(BASE_RELEASE / "manifest.json") != BASE_MANIFEST_SHA256:
            raise SystemExit("accepted v61 manifest hash differs")
        if tree_digest(BASE_RELEASE) != BASE_TREE_SHA256:
            raise SystemExit("accepted v61 release tree differs")

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
                prefix="open-seed-v62-db-", dir=staging_root
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
            validate_open_seed_release_v7(definition_stage, release_stage)
            promote_noreplace(release_stage, RELEASE)
            published_release = True
            promote_noreplace(definition_stage, DEFINITION)
            validate_open_seed_release_v7(DEFINITION, RELEASE)
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
    print(json.dumps(build_open_seed_v62(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
