"""Build and freeze official open seed v60 as the exact v59 successor.

V60 remains on the 2026-07-20 local research day.  It adds five current
official Israel records and eight audited historical-build records, and it
replaces the Bahrain construction-only record with a successor that preserves
the 2024 construction observation and records the 2025 operational update.
Historical lifecycle values remain last-observed facts, never current-status
inferences.
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
from .open_seed_release_v5 import (
    ADDITION_PINS,
    AS_OF,
    PENDING_NEXT_DAY_EXCLUSIONS,
    RECORDED_AT,
    RELEASE_ID,
    REPLACEMENT_PINS,
    STALE_EXCLUSIONS,
    V11_RECORDED_AT,
    freshness_contract,
    validate_open_seed_release_v5,
)
from .open_seed_v56 import (
    canonical_json,
    discard_release_stage,
    promote_noreplace,
    sha256,
    tree_digest,
)
from .open_seed_v59 import FRESHNESS_FIELDS, FRESHNESS_FILENAME, build_freshness_csv
from .publication_release import build_release_documents
from .service import summarize, validate_database


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v59.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v59"
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v60.json"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v60.lock"

BASE_DEFINITION_SHA256 = (
    "3f48bd7bcc3087207fb0993bfc3050bc3c3a35930c125bce2c6aba635bc5e03f"
)
BASE_MANIFEST_SHA256 = (
    "0f9214e65a851f81debd87a4e2c57ddd2146f793677707695ed2a01bcb8d88dd"
)
BASE_TREE_SHA256 = "53cb173fb0e07b8dba8f9bb974cc533b38ba006590583725baf122cb8ba8d636"

FRESHNESS_README = (
    "`lifecycle_freshness.csv` treats every published lifecycle value as a "
    "last-observed status, reports its age on the release date, and makes no "
    "current-construction inference. Its 0–90, 91–365, and over-365-day bands "
    "are review queues, not evidence that a status persisted. "
    "`current_status_classification` therefore remains `unknown` and "
    "`current_construction_claim` remains `false` for every row. The eight "
    "historical-build sources preserve physical history; later operational "
    "updates win where present, while old starts and top-outs without later "
    "physical evidence remain current-status unknown. The validated Pure "
    "AMS01 record remains pending the next local release day and stale STT "
    "Johor remains unselected."
)

ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:africa-data-centres-jhb2-samrand-campus",
        "curated:africa-data-centres-jhb2-samrand-campus:2022-phase-1-expansion",
        "curated:africa-data-centres-sameer-nairobi-campus",
        "curated:africa-data-centres-sameer-nairobi-campus:additional-facility-expansion",
        "curated:airtrunk-tok2-west-tokyo-data-centre",
        "curated:airtrunk-tok2-west-tokyo-data-centre:initial-build",
        "curated:cloudhq-gru-paulinia-campus",
        "curated:cloudhq-gru-paulinia-campus:phase-1",
        "curated:israel-medone-kfar-yona-campus",
        "curated:israel-medone-kfar-yona-campus:ky1",
        "curated:israel-mega-dc-mdcil1-modiin-site",
        "curated:israel-mega-dc-mdcil1-modiin-site:phase-b",
        "curated:israel-mega-dc-mdcil2-masmiyya-site",
        "curated:israel-mega-dc-mdcil2-masmiyya-site:phase-a",
        "curated:israel-mega-dc-mdcil4-beit-shemesh-site",
        "curated:israel-mega-dc-mdcil4-beit-shemesh-site:phase-a",
        "curated:israel-ned-levinstein-alfa-netanya-campus",
        "curated:israel-ned-levinstein-alfa-netanya-campus:phase-a",
        "curated:raxio-civ1-abidjan-data-centre",
        "curated:raxio-civ1-abidjan-data-centre:initial-build",
        "curated:tm-global-klang-valley-data-centre-cyberjaya",
        "curated:tm-global-klang-valley-data-centre-cyberjaya:block-2",
        "curated:wingu-addis-ababa-hyperscale-data-centre-park",
        "curated:wingu-addis-ababa-hyperscale-data-centre-park:initial-development",
        "curated:zdata-gp3-johor-data-center",
        "curated:zdata-gp3-johor-data-center:building-1",
    }
)
ADDED_PROJECT_KEYS = frozenset(
    {
        "curated:africa-data-centres-jhb2-samrand-campus:2022-phase-1-expansion",
        "curated:africa-data-centres-sameer-nairobi-campus:additional-facility-expansion",
        "curated:airtrunk-tok2-west-tokyo-data-centre:initial-build",
        "curated:cloudhq-gru-paulinia-campus:phase-1",
        "curated:israel-medone-kfar-yona-campus:ky1",
        "curated:israel-mega-dc-mdcil1-modiin-site:phase-b",
        "curated:israel-mega-dc-mdcil2-masmiyya-site:phase-a",
        "curated:israel-mega-dc-mdcil4-beit-shemesh-site:phase-a",
        "curated:israel-ned-levinstein-alfa-netanya-campus:phase-a",
        "curated:raxio-civ1-abidjan-data-centre:initial-build",
        "curated:tm-global-klang-valley-data-centre-cyberjaya:block-2",
        "curated:wingu-addis-ababa-hyperscale-data-centre-park:initial-development",
        "curated:zdata-gp3-johor-data-center:building-1",
    }
)
MUTATED_ENTITY_KEYS = frozenset(
    {
        "curated:stc-bahrain-data-center",
        "curated:stc-bahrain-data-center:facility-build",
    }
)

LIFECYCLE_CONTRACT = {
    ("curated:africa-data-centres-jhb2-samrand-campus:2022-phase-1-expansion", "under_construction", "2022-08-30"),
    ("curated:africa-data-centres-sameer-nairobi-campus:additional-facility-expansion", "under_construction", "2023-01-19"),
    ("curated:airtrunk-tok2-west-tokyo-data-centre:initial-build", "under_construction", "2022-11-17"),
    ("curated:airtrunk-tok2-west-tokyo-data-centre:initial-build", "operational", "2024-05-31"),
    ("curated:cloudhq-gru-paulinia-campus:phase-1", "under_construction", "2023-03-04"),
    ("curated:israel-medone-kfar-yona-campus:ky1", "under_construction", "2026-02-24"),
    ("curated:israel-mega-dc-mdcil1-modiin-site:phase-b", "under_construction", "2026-02-26"),
    ("curated:israel-mega-dc-mdcil1-modiin-site:phase-b", "under_construction", "2026-05-19"),
    ("curated:israel-mega-dc-mdcil2-masmiyya-site:phase-a", "under_construction", "2026-02-26"),
    ("curated:israel-mega-dc-mdcil2-masmiyya-site:phase-a", "under_construction", "2026-05-19"),
    ("curated:israel-mega-dc-mdcil4-beit-shemesh-site:phase-a", "under_construction", "2026-02-26"),
    ("curated:israel-mega-dc-mdcil4-beit-shemesh-site:phase-a", "under_construction", "2026-05-19"),
    ("curated:israel-ned-levinstein-alfa-netanya-campus:phase-a", "under_construction", "2026-03-01"),
    ("curated:raxio-civ1-abidjan-data-centre:initial-build", "under_construction", "2022-11-07"),
    ("curated:raxio-civ1-abidjan-data-centre:initial-build", "operational", "2024-09-24"),
    ("curated:stc-bahrain-data-center:facility-build", "under_construction", "2024-12-31"),
    ("curated:stc-bahrain-data-center:facility-build", "operational", "2025-12-31"),
    ("curated:tm-global-klang-valley-data-centre-cyberjaya:block-2", "shell", "2025-05-30"),
    ("curated:wingu-addis-ababa-hyperscale-data-centre-park:initial-development", "under_construction", "2022-01-14"),
    ("curated:wingu-addis-ababa-hyperscale-data-centre-park:initial-development", "operational", "2023-06-13"),
    ("curated:zdata-gp3-johor-data-center:building-1", "shell", "2025-07-08"),
}

CAPACITY_CONTRACT = {
    "curated:africa-data-centres-jhb2-samrand-campus:2022-phase-1-expansion": ("critical_it_mw", "planned", "MW", 20.0, 20.0, 20.0, "2022-08-30"),
    "curated:africa-data-centres-sameer-nairobi-campus:additional-facility-expansion": ("critical_it_mw", "planned", "MW", 5.0, 5.0, 5.0, "2023-01-19"),
    "curated:cloudhq-gru-paulinia-campus": ("critical_it_mw", "planned", "MW", 288.0, 288.0, 288.0, "2026-07-20"),
    "curated:israel-medone-kfar-yona-campus:ky1": ("critical_it_mw", "planned", "MW", 10.5, 10.5, 10.5, "2026-07-20"),
    "curated:israel-mega-dc-mdcil1-modiin-site:phase-b": ("critical_it_mw", "planned", "MW", 9.0, 9.0, 9.0, "2026-05-19"),
    "curated:israel-mega-dc-mdcil2-masmiyya-site:phase-a": ("critical_it_mw", "planned", "MW", 40.0, 40.0, 40.0, "2026-05-19"),
    "curated:israel-mega-dc-mdcil4-beit-shemesh-site:phase-a": ("critical_it_mw", "planned", "MW", 60.0, 60.0, 60.0, "2026-05-19"),
    "curated:israel-ned-levinstein-alfa-netanya-campus:phase-a": ("critical_it_mw", "planned", "MW", 18.0, 18.0, 21.0, "2026-03-01"),
    "curated:raxio-civ1-abidjan-data-centre:initial-build": ("critical_it_mw", "planned", "MW", 3.0, 3.0, 3.0, "2022-11-07"),
}

OPERATIONAL_WINNERS = {
    "curated:airtrunk-tok2-west-tokyo-data-centre:initial-build": "2024-05-31",
    "curated:raxio-civ1-abidjan-data-centre:initial-build": "2024-09-24",
    "curated:stc-bahrain-data-center:facility-build": "2025-12-31",
    "curated:wingu-addis-ababa-hyperscale-data-centre-park:initial-development": "2023-06-13",
}
HISTORICAL_UNRESOLVED_KEYS = frozenset(
    {
        "curated:africa-data-centres-jhb2-samrand-campus:2022-phase-1-expansion",
        "curated:africa-data-centres-sameer-nairobi-campus:additional-facility-expansion",
        "curated:cloudhq-gru-paulinia-campus:phase-1",
        "curated:tm-global-klang-valley-data-centre-cyberjaya:block-2",
        "curated:zdata-gp3-johor-data-center:building-1",
    }
)

CSV_DELTA_CONTRACT = {
    "entities.csv": (697, 28, "85b864559ce13814bd48573be0d2b24ef4e968e8c5bb37ec83fedc3cf235891f", 2, "aa05328ee0b6e51d91798157ca8b038b1298144e73e0bd3eb1090f885609c5d0"),
    "evidence.csv": (418, 21, "13bde6e4484e77c09c0863ef8aa419de27df52dcd221bcf87a68ccfa0f79c893", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
    "capacity_estimates.csv": (491, 9, "f047fabf6a8d1e42b6f2e6d2828f4497e9117beb5823b3750879821242a293a5", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
    "construction_pipeline.csv": (361, 10, "f50a43d444811469339972c7b11bd33a2627149b12b7a1e910272e3d458396b4", 1, "08e3f8edb7d7c434c384695b39ee36102aeb0376d7bff9f0b8429678fef28d03"),
    "construction_source_signals.csv": (267, 11, "21346456d284a9aaff16b344e1d399e40131c063993f7bdb21b96946d83b0304", 1, "53744bec830a011fd2846dba8cfe124075bce0d160381ca6fbdf92bd173e3911"),
    "resolution_candidates.csv": (5, 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
}

NEW_SOURCE_FAMILIES = {
    "africa_data_centres_news",
    "airtrunk_sustainability_report",
    "cloudhq_campus_page",
    "cscec_corporate_news",
    "linkedin_public_post",
    "medone_articles",
    "medone_facility_pages",
    "raxio_group_news",
    "stc_annual_reports",
    "tase_maya_issuer_filings",
    "tm_global_news",
    "wingu_africa_news",
}


@contextmanager
def publication_lock() -> Iterator[None]:
    """Hold an exclusive v60 publication lock without replacing any file."""

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
    if relative not in ADDITION_PINS and relative not in {
        successor for successor, _ in REPLACEMENT_PINS.values()
    }:
        return
    if document.get("schema_version") != "1.1":
        raise SystemExit(f"v60 successor source must use schema 1.1: {relative}")
    campus = document.get("campus")
    project = document.get("project")
    if not isinstance(campus, dict) or not isinstance(project, dict):
        raise SystemExit(f"v60 source must contain one campus and one project: {relative}")
    if project["stable_key"] not in MUTATED_ENTITY_KEYS | ADDED_PROJECT_KEYS:
        raise SystemExit(f"v60 project identity differs: {relative}")
    if not project["stable_key"].startswith(campus["stable_key"] + ":"):
        raise SystemExit(f"v60 phase does not nest under its named campus: {relative}")
    for entity in (campus, project):
        if entity.get("roles") != {}:
            raise SystemExit(f"v60 source inferred a role: {relative}")
        if entity.get("coordinates") is not None or entity.get("geometry") is not None:
            raise SystemExit(f"v60 source invented geometry: {relative}")
    for capacity in document.get("capacities", []):
        if capacity.get("metric") != "critical_it_mw" or capacity.get("unit") != "MW":
            raise SystemExit(f"v60 source normalized an unsupported capacity: {relative}")


def selected_inputs(base: Mapping[str, Any]) -> tuple[list[dict[str, str]], list[Path]]:
    """Return the exact one-replacement, thirteen-addition v59 successor."""

    if base.get("release_id") != "2026-07-20-open-seed-v59":
        raise SystemExit("v60 base must be exactly frozen v59")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 334:
        raise SystemExit("frozen v59 curated inventory differs")
    pins: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise SystemExit("frozen v59 curated row is invalid")
        path, digest = row["path"], row["sha256"]
        if path in pins or not isinstance(path, str) or not isinstance(digest, str):
            raise SystemExit("frozen v59 curated inventory is invalid")
        pins[path] = digest
    for predecessor, (successor, digest) in REPLACEMENT_PINS.items():
        if predecessor not in pins or successor in pins:
            raise SystemExit("Bahrain replacement boundary differs")
        del pins[predecessor]
        pins[successor] = digest
    for path, digest in ADDITION_PINS.items():
        if path in pins:
            raise SystemExit("a v60 addition already occurs in v59")
        pins[path] = digest
    excluded = STALE_EXCLUSIONS | PENDING_NEXT_DAY_EXCLUSIONS
    if excluded & set(pins):
        raise SystemExit("an excluded v60 source was selected")
    if len(pins) != 347:
        raise SystemExit(f"expected 347 unique v60 inputs, found {len(pins)}")

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
        "entities": 725,
        "evidence": 540,
        "lifecycle_observations": 426,
        "capacity_estimates": 501,
        "entity_snapshots": 744,
        "operating_model_observations": 50,
        "workload_observations": 122,
    }
    if counts != expected:
        raise SystemExit(f"fresh v60 database projection differs: {counts}")

    relevant = tuple(sorted(ADDED_ENTITY_KEYS | MUTATED_ENTITY_KEYS))
    placeholders = ",".join("?" for _ in relevant)
    entity_rows = connection.execute(
        f"SELECT stable_key, kind FROM entities WHERE stable_key IN ({placeholders})",
        relevant,
    ).fetchall()
    if {row[0] for row in entity_rows} != ADDED_ENTITY_KEYS | MUTATED_ENTITY_KEYS:
        raise SystemExit("v60 entity identity set differs")
    if {row[0] for row in entity_rows if row[1] == "project"} != (
        ADDED_PROJECT_KEYS | {"curated:stc-bahrain-data-center:facility-build"}
    ):
        raise SystemExit("v60 project identity set differs")

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
        key: key.rsplit(":", 1)[0]
        for key in ADDED_PROJECT_KEYS
    } | {"curated:stc-bahrain-data-center:facility-build": "curated:stc-bahrain-data-center"}
    if {row[0]: row[1] for row in target_rows} != expected_targets:
        raise SystemExit("v60 project-to-campus nesting differs")

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
        raise SystemExit("v60 lifecycle delta differs")

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
        raise SystemExit(f"v60 typed capacity delta differs: {actual_capacity}")

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
        raise SystemExit("v60 added or replacement records gained invented geometry")


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
        raise SystemExit("fresh Epoch import result differs from v59")
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
    """Add the v60 last-observed carrier and bind it into the manifest."""

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
            raise SystemExit(f"fresh v60 CSV delta differs: {filename}: {actual}")

    before_entities = _rows_by_key(BASE_RELEASE / "entities.csv")
    after_entities = _rows_by_key(stage / "entities.csv")
    if set(after_entities) - set(before_entities) != ADDED_ENTITY_KEYS:
        raise SystemExit("v60 added entity set differs")
    if set(before_entities) - set(after_entities):
        raise SystemExit("v60 unexpectedly removed an entity identity")
    changed_common = {
        key
        for key in before_entities.keys() & after_entities.keys()
        if before_entities[key] != after_entities[key]
    }
    if changed_common != MUTATED_ENTITY_KEYS:
        raise SystemExit("v60 common entity churn is not exactly Bahrain")
    for key, observed in OPERATIONAL_WINNERS.items():
        row = after_entities[key]
        if row["status"] != "operational" or row["status_as_of"] != observed:
            raise SystemExit(f"later operational correction did not win: {key}")


def _freshness_class(age_days: int) -> str:
    if age_days <= 90:
        return "recent_0_90_days"
    if age_days <= 365:
        return "aging_91_365_days"
    return "stale_over_365_days"


def _validate_freshness(stage: Path) -> None:
    with (stage / FRESHNESS_FILENAME).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 412 or tuple(rows[0]) != FRESHNESS_FIELDS:
        raise SystemExit(f"fresh v60 freshness shape differs: {len(rows)}")
    if any(
        row["status_semantics"] != "last_observed"
        or row["current_status_classification"] != "unknown"
        or row["current_construction_claim"] != "false"
        for row in rows
    ):
        raise SystemExit("v60 freshness rows infer current status")
    by_key = {row["stable_key"]: row for row in rows}
    if not HISTORICAL_UNRESOLVED_KEYS <= set(by_key):
        raise SystemExit("v60 historical unresolved rows are missing")
    for key in HISTORICAL_UNRESOLVED_KEYS:
        if (
            by_key[key]["current_status_classification"] != "unknown"
            or by_key[key]["current_construction_claim"] != "false"
        ):
            raise SystemExit(f"historical start became a current claim: {key}")
    if any(
        "stt-johor" in row["stable_key"] or "pure-dc-ams01" in row["stable_key"]
        for row in rows
    ):
        raise SystemExit("an excluded source leaked into v60 freshness output")
    as_of_date = date.fromisoformat(AS_OF)
    classes = Counter()
    for row in rows:
        expected_age = as_of_date - date.fromisoformat(row["last_observed_status_as_of"])
        if row["observation_age_days"] != str(expected_age.days):
            raise SystemExit("v60 freshness age differs")
        expected_class = _freshness_class(expected_age.days)
        if row["freshness_class"] != expected_class:
            raise SystemExit("v60 freshness class differs")
        classes[expected_class] += 1
    if classes != {
        "recent_0_90_days": 211,
        "aging_91_365_days": 174,
        "stale_over_365_days": 27,
    }:
        raise SystemExit(f"v60 freshness distribution differs: {classes}")


def _validate_release_facts(stage: Path) -> None:
    summary = json.loads((stage / "summary.json").read_text(encoding="utf-8"))
    expected = {
        "campuses_total": 388,
        "campuses_with_coordinates": 122,
        "capacity_estimates_current": 500,
        "construction_pipeline_records": 371,
        "construction_source_signals": 278,
        "entities_total": 725,
        "entities_with_coordinates": 170,
        "evidence_total": 540,
        "lifecycle_observations_current": 412,
        "projects_total": 337,
        "recorded_at": RECORDED_AT,
    }
    actual = {key: summary.get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"fresh v60 summary facts differ: {actual}")
    if summary["capacity_estimates_by_metric"].get("critical_it_mw") != 244:
        raise SystemExit("fresh v60 critical-IT row count differs")
    if summary["capacity_estimates_by_stage"].get("planned") != 136:
        raise SystemExit("fresh v60 planned-capacity row count differs")
    if summary["entities_by_status"].get("under_construction") != 268:
        raise SystemExit("fresh v60 under-construction observation count differs")

    manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    expected_manifest = {
        "entities": 725,
        "evidence_records": 439,
        "capacity_estimates": 500,
        "construction_pipeline_records": 371,
        "construction_source_signals": 278,
        "resolution_candidates": 5,
        "lifecycle_freshness_records": 412,
        "lifecycle_status_semantics": "last_observed",
        "current_status_inferred": False,
    }
    actual_manifest = {key: manifest.get(key) for key in expected_manifest}
    if actual_manifest != expected_manifest:
        raise SystemExit(f"fresh v60 manifest facts differ: {actual_manifest}")
    base_manifest = json.loads(
        (BASE_RELEASE / "manifest.json").read_text(encoding="utf-8")
    )
    if set(manifest["source_families"]) - set(base_manifest["source_families"]) != (
        NEW_SOURCE_FAMILIES
    ):
        raise SystemExit("fresh v60 source-family delta differs")
    if set(base_manifest["source_families"]) - set(manifest["source_families"]):
        raise SystemExit("fresh v60 removed a source family")
    if len(manifest["source_families"]) != 239:
        raise SystemExit("fresh v60 source-family count differs")
    if len(list(stage.iterdir())) != 14:
        raise SystemExit("fresh v60 release must contain exactly 14 files")
    _validate_freshness(stage)


def build_open_seed_v60() -> dict[str, object]:
    """Build and freeze v60 exactly once, refusing every publication collision."""

    with publication_lock():
        if DEFINITION.exists() or DEFINITION.is_symlink():
            raise SystemExit(f"definition already exists; refusing overwrite: {DEFINITION}")
        if RELEASE.exists() or RELEASE.is_symlink():
            raise SystemExit(f"release already exists; refusing overwrite: {RELEASE}")
        if sha256(BASE_DEFINITION) != BASE_DEFINITION_SHA256:
            raise SystemExit("accepted v59 definition hash differs")
        if sha256(BASE_RELEASE / "manifest.json") != BASE_MANIFEST_SHA256:
            raise SystemExit("accepted v59 manifest hash differs")
        if tree_digest(BASE_RELEASE) != BASE_TREE_SHA256:
            raise SystemExit("accepted v59 release tree differs")

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
                prefix="open-seed-v60-db-", dir=staging_root
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
            validate_open_seed_release_v5(definition_stage, release_stage)
            promote_noreplace(release_stage, RELEASE)
            published_release = True
            promote_noreplace(definition_stage, DEFINITION)
            validate_open_seed_release_v5(DEFINITION, RELEASE)
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
    print(json.dumps(build_open_seed_v60(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
