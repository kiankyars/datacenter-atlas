"""Build and freeze official open seed v59 as the exact v58 successor.

V59 stays on the 2026-07-20 local research day.  It replaces five curated
records with coordinate-bearing successors and adds seven current official
records.  The validated Pure AMS01 record is pending because its entity
snapshots belong to the next local release day.  Stale STT Johor and the
historical-build tranche remain unselected.
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
from .open_seed_release_v4 import (
    ADDITION_PINS,
    AS_OF,
    HISTORICAL_EXCLUSIONS,
    PENDING_NEXT_DAY_EXCLUSIONS,
    RECORDED_AT,
    RELEASE_ID,
    REPLACEMENT_PINS,
    STALE_EXCLUSIONS,
    V11_RECORDED_AT,
    validate_open_seed_release_v4,
)
from .open_seed_v56 import (
    canonical_json,
    discard_release_stage,
    promote_noreplace,
    sha256,
    tree_digest,
)
from .publication_release import build_release_documents
from .service import summarize, validate_database


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v58.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v58"
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v59.json"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v59.lock"

BASE_DEFINITION_SHA256 = (
    "76b9200c892c62a579007f7024a3802019c8b06ad34e0dbbd42e5529fb391a74"
)
BASE_MANIFEST_SHA256 = (
    "52261833ac75e2153d4298352a517a0beecb4938f4098ca0f280da3cf367d83e"
)
BASE_TREE_SHA256 = "6534726c7011dcf3af9664f4bd796509a4535cfbca75d507aa3ffea2a227bc0f"

FRESHNESS_FILENAME = "lifecycle_freshness.csv"
FRESHNESS_FIELDS = (
    "entity_id",
    "entity_kind",
    "stable_key",
    "name",
    "country",
    "last_observed_status",
    "last_observed_status_as_of",
    "last_observed_status_method",
    "last_observed_status_evidence_id",
    "observation_age_days",
    "freshness_class",
    "status_semantics",
    "current_status_classification",
    "current_construction_claim",
)
FRESHNESS_README = (
    "`lifecycle_freshness.csv` treats every published lifecycle value as a "
    "last-observed status, reports its age on the release date, and makes no "
    "current-construction inference. Its 0–90, 91–365, and over-365-day bands "
    "are review queues, not evidence that a status persisted. "
    "`current_status_classification` therefore remains `unknown` and "
    "`current_construction_claim` remains `false` for every row. The validated "
    "Pure AMS01 record is pending the next local release day; stale STT Johor "
    "and the historical-build tranche are not selected."
)

ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:kazakhstan-data-center-valley-ekibastuz",
        "curated:kazakhstan-data-center-valley-ekibastuz:initial-campus-development",
        "curated:vantage-va4-fredericksburg-campus",
        "curated:vantage-va4-fredericksburg-campus:initial-campus-development",
        "curated:stt-fairview-data-centre-campus",
        "curated:stt-fairview-data-centre-campus:stt-fairview-1",
        "curated:stt-cavite-data-centre-campus",
        "curated:stt-cavite-data-centre-campus:stt-cavite-2",
        "curated:kio-mex8-mexico-city-data-center",
        "curated:kio-mex8-mexico-city-data-center:current-development",
        "curated:google-saint-ghislain-data-center-campus",
        "curated:google-saint-ghislain-data-center-campus:seventh-building-expansion",
        "curated:scala-smextp01-tepotzotlan-data-center",
        "curated:scala-smextp01-tepotzotlan-data-center:smextp01",
    }
)
ADDED_PROJECT_KEYS = frozenset(
    key for key in ADDED_ENTITY_KEYS if ":" in key.removeprefix("curated:")
)
COORDINATE_MUTATED_KEYS = frozenset(
    {
        "curated:verne-mantsala-data-center-campus",
        "curated:penzance-chantilly-premier-data-center",
        "curated:t5-chicago-iii-northlake-data-center:current-facility-build",
        "curated:cra-prague-gateway-data-center-campus",
        "curated:maincubes-fra03-schwalbach-data-center",
    }
)
COORDINATE_CONTRACT = {
    "curated:verne-mantsala-data-center-campus": (
        60.63527854345244,
        25.286117693746803,
        "authoritative_site_plan",
    ),
    "curated:penzance-chantilly-premier-data-center": (
        38.90287453965922,
        -77.46593013343211,
        "authoritative_site_plan",
    ),
    "curated:t5-chicago-iii-northlake-data-center:current-facility-build": (
        41.9342994235141,
        -87.91569501443621,
        "authoritative_address_geocode",
    ),
    "curated:cra-prague-gateway-data-center-campus": (
        49.948186441032426,
        14.36784629256487,
        "authoritative_site_plan",
    ),
    "curated:maincubes-fra03-schwalbach-data-center": (
        50.16092256214182,
        8.53631666671276,
        "authoritative_address_geocode",
    ),
    "curated:vantage-va4-fredericksburg-campus": (
        38.309875,
        -77.466316,
        "authoritative_site_plan",
    ),
}
LIFECYCLE_CONTRACT = {
    (
        "curated:kazakhstan-data-center-valley-ekibastuz:initial-campus-development",
        "site_preparation",
        "2026-05-25",
    ),
    (
        "curated:kazakhstan-data-center-valley-ekibastuz:initial-campus-development",
        "under_construction",
        "2026-07-01",
    ),
    (
        "curated:vantage-va4-fredericksburg-campus:initial-campus-development",
        "under_construction",
        "2025-11-06",
    ),
    (
        "curated:stt-fairview-data-centre-campus:stt-fairview-1",
        "expansion",
        "2026-03-31",
    ),
    (
        "curated:stt-cavite-data-centre-campus:stt-cavite-2",
        "operational",
        "2026-03-31",
    ),
    (
        "curated:kio-mex8-mexico-city-data-center:current-development",
        "under_construction",
        "2026-03-09",
    ),
    (
        "curated:google-saint-ghislain-data-center-campus:seventh-building-expansion",
        "under_construction",
        "2025-10-08",
    ),
    (
        "curated:google-saint-ghislain-data-center-campus:seventh-building-expansion",
        "expansion",
        "2026-05-06",
    ),
    (
        "curated:scala-smextp01-tepotzotlan-data-center:smextp01",
        "operational",
        "2026-07-20",
    ),
}
CAPACITY_CONTRACT = {
    "curated:vantage-va4-fredericksburg-campus": (
        "critical_it_mw",
        "planned",
        "MW",
        192.0,
        "2026-07-20",
    ),
    "curated:stt-fairview-data-centre-campus": (
        "critical_it_mw",
        "planned",
        "MW",
        124.0,
        "2026-07-20",
    ),
    "curated:stt-fairview-data-centre-campus:stt-fairview-1": (
        "critical_it_mw",
        "planned",
        "MW",
        28.0,
        "2026-07-20",
    ),
    "curated:stt-cavite-data-centre-campus:stt-cavite-2": (
        "critical_it_mw",
        "planned",
        "MW",
        6.0,
        "2026-07-20",
    ),
    "curated:scala-smextp01-tepotzotlan-data-center:smextp01": (
        "critical_it_mw",
        "design",
        "MW",
        5.1,
        "2026-07-20",
    ),
}

# Common, added, added hash, removed, removed hash against frozen v58.
CSV_DELTA_CONTRACT = {
    "entities.csv": (
        680,
        19,
        "ab6f897b031615ddb9e8f2aeb632eb98b62d82276fafdf811ada25fc962e93b7",
        5,
        "e2a3488cdbbd83ea4e00d4f52885071fcebd4d118ead9438cc908fb51f8e8454",
    ),
    "evidence.csv": (
        400,
        18,
        "51d10f709bf14a197356dc196593157f29972ddbec6ee2e1172f28560d682585",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "capacity_estimates.csv": (
        486,
        5,
        "bf3e91a521fcff13cd470b850f8e335adc137a46e5289385111e02dcf9508633",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_pipeline.csv": (
        356,
        6,
        "4794ab3ac3aebe7b37443127e371a9a6c5ebd37d7c337df54eb1f8cff13921b9",
        1,
        "437af8c08f829bd12940a99a47a251577135979e053faf35c9577cf9a9bc27f1",
    ),
    "construction_source_signals.csv": (
        262,
        6,
        "7055c4b8a57d62608f4dd6916bad9ebfc778a8df1b6c8f5fabb5aa8f5f9cacb2",
        1,
        "18d6ac2a2ddf4d853d3bb79a308d976aa282f9d188e7ca28d5694e7512b7efca",
    ),
    "resolution_candidates.csv": (
        4,
        1,
        "c870c8d87a00ad94402c24ebfed3c53f0fafae380035fef4a354e17738af745b",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
}


@contextmanager
def publication_lock() -> Iterator[None]:
    """Hold an exclusive v59 publication lock without replacing any file."""

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


def freshness_contract() -> dict[str, Any]:
    """Return the exact non-currentness and input-exclusion contract."""

    return {
        "current_construction_inferred": False,
        "current_status_classification": "unknown",
        "historical_inputs_excluded": sorted(HISTORICAL_EXCLUSIONS),
        "lifecycle_status_semantics": "last_observed",
        "next_local_day_inputs_pending": sorted(PENDING_NEXT_DAY_EXCLUSIONS),
        "recent_observation_max_age_days": 90,
        "stale_input_max_age_days": 365,
        "stale_inputs_excluded": sorted(STALE_EXCLUSIONS),
    }


def selected_inputs(base: Mapping[str, Any]) -> tuple[list[dict[str, str]], list[Path]]:
    """Return the exact five-replacement, seven-addition v58 successor."""

    if base.get("release_id") != "2026-07-20-open-seed-v58":
        raise SystemExit("v59 base must be exactly frozen v58")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 327:
        raise SystemExit("frozen v58 curated inventory differs")
    pins: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise SystemExit("frozen v58 curated row is invalid")
        path, digest = row["path"], row["sha256"]
        if path in pins or not isinstance(path, str) or not isinstance(digest, str):
            raise SystemExit("frozen v58 curated inventory is invalid")
        pins[path] = digest
    for predecessor, (successor, digest) in REPLACEMENT_PINS.items():
        if predecessor not in pins or successor in pins:
            raise SystemExit("coordinate replacement boundary differs")
        del pins[predecessor]
        pins[successor] = digest
    for path, digest in ADDITION_PINS.items():
        if path in pins:
            raise SystemExit("a v59 addition already occurs in v58")
        pins[path] = digest
    excluded = STALE_EXCLUSIONS | HISTORICAL_EXCLUSIONS | PENDING_NEXT_DAY_EXCLUSIONS
    if excluded & set(pins):
        raise SystemExit("an excluded v59 source was selected")
    if len(pins) != 334:
        raise SystemExit(f"expected 334 unique v59 inputs, found {len(pins)}")
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
        "entities": 699,
        "evidence": 512,
        "lifecycle_observations": 406,
        "capacity_estimates": 492,
        "entity_snapshots": 718,
        "operating_model_observations": 49,
        "workload_observations": 122,
    }
    if counts != expected:
        raise SystemExit(f"fresh v59 database projection differs: {counts}")

    placeholders = ",".join("?" for _ in ADDED_ENTITY_KEYS)
    entity_rows = connection.execute(
        f"SELECT stable_key, kind FROM entities WHERE stable_key IN ({placeholders})",
        tuple(sorted(ADDED_ENTITY_KEYS)),
    ).fetchall()
    if {row[0] for row in entity_rows} != ADDED_ENTITY_KEYS:
        raise SystemExit("v59 added entity identity set differs")
    if {row[0] for row in entity_rows if row[1] == "project"} != ADDED_PROJECT_KEYS:
        raise SystemExit("v59 added project identity set differs")

    lifecycle_rows = connection.execute(
        f"""
        SELECT entities.stable_key, lifecycle_observations.status,
               lifecycle_observations.as_of_date
        FROM lifecycle_observations
        JOIN entities ON entities.id = lifecycle_observations.entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        tuple(sorted(ADDED_ENTITY_KEYS)),
    ).fetchall()
    if {(row[0], row[1], row[2]) for row in lifecycle_rows} != LIFECYCLE_CONTRACT:
        raise SystemExit("v59 lifecycle delta differs")

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
        raise SystemExit(f"v59 typed capacity delta differs: {actual_capacity}")

    coordinate_keys = tuple(sorted(COORDINATE_CONTRACT))
    coordinate_placeholders = ",".join("?" for _ in coordinate_keys)
    coordinate_rows = connection.execute(
        f"""
        WITH ranked AS (
            SELECT entities.stable_key, entity_snapshots.latitude,
                   entity_snapshots.longitude, entity_snapshots.method,
                   ROW_NUMBER() OVER (
                       PARTITION BY entities.id
                       ORDER BY entity_snapshots.as_of_date DESC,
                                entity_snapshots.recorded_at DESC,
                                entity_snapshots.id DESC
                   ) AS rank
            FROM entity_snapshots
            JOIN entities ON entities.id = entity_snapshots.entity_id
            WHERE entities.stable_key IN ({coordinate_placeholders})
              AND entity_snapshots.as_of_date <= ?
        )
        SELECT stable_key, latitude, longitude, method
        FROM ranked WHERE rank = 1
        """,
        (*coordinate_keys, AS_OF),
    ).fetchall()
    actual_coordinates = {
        row[0]: (row[1], row[2], row[3]) for row in coordinate_rows
    }
    if actual_coordinates != COORDINATE_CONTRACT:
        raise SystemExit(f"v59 coordinate contract differs: {actual_coordinates}")


def _freshness_class(age_days: int) -> str:
    if age_days <= 90:
        return "recent_0_90_days"
    if age_days <= 365:
        return "aging_91_365_days"
    return "stale_over_365_days"


def build_freshness_csv(entities_csv: str, *, as_of: str) -> str:
    """Encode last-observed lifecycle ages without inferring current status."""

    as_of_date = date.fromisoformat(as_of)
    rows: list[dict[str, str]] = []
    for entity in csv.DictReader(io.StringIO(entities_csv)):
        status = entity["status"]
        if not status:
            continue
        observed_text = entity["status_as_of"]
        if not observed_text:
            raise RuntimeError("published lifecycle status lacks status_as_of")
        age_days = (as_of_date - date.fromisoformat(observed_text)).days
        if age_days < 0:
            raise RuntimeError("future lifecycle status entered freshness output")
        rows.append(
            {
                "entity_id": entity["entity_id"],
                "entity_kind": entity["entity_kind"],
                "stable_key": entity["stable_key"],
                "name": entity["name"],
                "country": entity["country"],
                "last_observed_status": status,
                "last_observed_status_as_of": observed_text,
                "last_observed_status_method": entity["status_method"],
                "last_observed_status_evidence_id": entity["status_evidence_id"],
                "observation_age_days": str(age_days),
                "freshness_class": _freshness_class(age_days),
                "status_semantics": "last_observed",
                "current_status_classification": "unknown",
                "current_construction_claim": "false",
            }
        )
    rows.sort(key=lambda row: (row["stable_key"], row["entity_id"]))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FRESHNESS_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def augment_release_documents(
    documents: Mapping[str, str], *, as_of: str
) -> dict[str, str]:
    """Add the v59 freshness carrier and bind it into the manifest."""

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
            raise SystemExit(f"fresh v59 CSV delta differs: {filename}: {actual}")

    before_entities = _rows_by_key(BASE_RELEASE / "entities.csv")
    after_entities = _rows_by_key(stage / "entities.csv")
    changed_common = {
        key
        for key in before_entities.keys() & after_entities.keys()
        if before_entities[key] != after_entities[key]
    }
    if changed_common != COORDINATE_MUTATED_KEYS:
        raise SystemExit(
            "v59 common entity churn is not exactly the five coordinate successors"
        )
    if any(key.startswith("epoch-ai:") for key in changed_common):
        raise SystemExit("v59 unexpectedly rolled an Epoch entity")
    if set(after_entities) - set(before_entities) != ADDED_ENTITY_KEYS:
        raise SystemExit("v59 added entity set differs")

    resolution_before = _csv_counter(BASE_RELEASE / "resolution_candidates.csv")
    resolution_after = _csv_counter(stage / "resolution_candidates.csv")
    added_resolution = [
        dict(row) for row in (resolution_after - resolution_before).elements()
    ]
    if len(added_resolution) != 1:
        raise SystemExit("v59 resolution-candidate delta differs")
    candidate = added_resolution[0]
    if {
        candidate["left_name"],
        candidate["right_name"],
    } != {
        "Menlo Digital MD-VA1 Herndon Data Center",
        "Penzance Chantilly Premier Data Center",
    } or (
        candidate["relationship_suggestion"] != "nearby_only"
        or candidate["distance_m"] != "4503.543"
    ):
        raise SystemExit("v59 advisory Penzance/Menlo candidate differs")


def _validate_freshness(stage: Path) -> None:
    with (stage / FRESHNESS_FILENAME).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 399:
        raise SystemExit(f"fresh v59 freshness row count differs: {len(rows)}")
    if any(
        row["status_semantics"] != "last_observed"
        or row["current_status_classification"] != "unknown"
        or row["current_construction_claim"] != "false"
        for row in rows
    ):
        raise SystemExit("v59 freshness rows infer current status")
    if any(
        "stt-johor" in row["stable_key"]
        or "pure-dc-ams01" in row["stable_key"]
        for row in rows
    ):
        raise SystemExit("an excluded source leaked into v59 freshness output")
    as_of_date = date.fromisoformat(AS_OF)
    for row in rows:
        expected_age = (
            as_of_date - date.fromisoformat(row["last_observed_status_as_of"])
        ).days
        if row["observation_age_days"] != str(expected_age):
            raise SystemExit("v59 freshness age differs")
        if row["freshness_class"] != _freshness_class(expected_age):
            raise SystemExit("v59 freshness class differs")


def _validate_release_facts(stage: Path) -> None:
    summary = json.loads((stage / "summary.json").read_text(encoding="utf-8"))
    expected = {
        "campuses_total": 375,
        "campuses_with_coordinates": 122,
        "capacity_estimates_current": 491,
        "construction_pipeline_records": 362,
        "construction_source_signals": 268,
        "entities_total": 699,
        "entities_with_coordinates": 170,
        "evidence_total": 512,
        "lifecycle_observations_current": 399,
        "projects_total": 324,
        "recorded_at": RECORDED_AT,
    }
    actual = {key: summary.get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"fresh v59 summary facts differ: {actual}")
    if summary["capacity_estimates_by_metric"].get("critical_it_mw") != 235:
        raise SystemExit("fresh v59 critical-IT row count differs")
    if summary["capacity_estimates_by_stage"].get("planned") != 127:
        raise SystemExit("fresh v59 planned-capacity row count differs")
    if summary["capacity_estimates_by_stage"].get("design") != 7:
        raise SystemExit("fresh v59 design-capacity row count differs")
    if summary["entities_by_status"].get("under_construction") != 261:
        raise SystemExit("fresh v59 under-construction observation count differs")

    manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    expected_manifest = {
        "entities": 699,
        "evidence_records": 418,
        "capacity_estimates": 491,
        "construction_pipeline_records": 362,
        "construction_source_signals": 268,
        "resolution_candidates": 5,
        "lifecycle_freshness_records": 399,
        "lifecycle_status_semantics": "last_observed",
        "current_status_inferred": False,
    }
    actual_manifest = {key: manifest.get(key) for key in expected_manifest}
    if actual_manifest != expected_manifest:
        raise SystemExit(f"fresh v59 manifest facts differ: {actual_manifest}")
    if len(manifest["source_families"]) != 227:
        raise SystemExit("fresh v59 source-family count differs")
    if len(list(stage.iterdir())) != 14:
        raise SystemExit("fresh v59 release must contain exactly 14 files")
    _validate_freshness(stage)


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
        raise SystemExit("fresh Epoch import result differs from v58")
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


def build_open_seed_v59() -> dict[str, object]:
    """Build and freeze v59 exactly once, refusing every publication collision."""

    with publication_lock():
        if DEFINITION.exists() or DEFINITION.is_symlink():
            raise SystemExit(f"definition already exists; refusing overwrite: {DEFINITION}")
        if RELEASE.exists() or RELEASE.is_symlink():
            raise SystemExit(f"release already exists; refusing overwrite: {RELEASE}")
        if sha256(BASE_DEFINITION) != BASE_DEFINITION_SHA256:
            raise SystemExit("accepted v58 definition hash differs")
        if sha256(BASE_RELEASE / "manifest.json") != BASE_MANIFEST_SHA256:
            raise SystemExit("accepted v58 manifest hash differs")
        if tree_digest(BASE_RELEASE) != BASE_TREE_SHA256:
            raise SystemExit("accepted v58 release tree differs")

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
                prefix="open-seed-v59-db-", dir=staging_root
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
            validate_open_seed_release_v4(definition_stage, release_stage)
            promote_noreplace(release_stage, RELEASE)
            published_release = True
            promote_noreplace(definition_stage, DEFINITION)
            validate_open_seed_release_v4(DEFINITION, RELEASE)
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
    print(json.dumps(build_open_seed_v59(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
