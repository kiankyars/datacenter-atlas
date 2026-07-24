"""Build open seed v87 as the strict four-source append successor to v86."""

from __future__ import annotations

from contextlib import contextmanager
import csv
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping

from . import global_official_builds_us_operator_gap_20260721 as operator
from . import open_seed_v69 as v69
from . import open_seed_v70 as v70
from . import open_seed_v86 as v86
from .publication_release import build_release_documents
from .service import _current_rows, summarize


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v86.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v86"
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v87.json"
RELEASE_ID = "2026-07-21-open-seed-v87"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v87.lock"
AS_OF = "2026-07-21"

BASE_RECORDED_AT = "2026-07-21T20:19:16Z"
BASE_DEFINITION_PIN = (
    102_240,
    "2a2f0cded9e95efd2ab90cbde1d8ad11306b14f019f42cb14086fb80a63fb25d",
)
BASE_MANIFEST_PIN = (
    15_531,
    "5bc24a692e2d4fc793192f03bd23fa921e434661a0675e6612370d354cf11488",
)
BASE_TREE_SHA256 = "593fe37f16cc81bd6e2011c9b893251be4041dc54376ffec2f743a510fb4d4de"
BASE_ENTITIES_PIN = (
    978_587,
    "a32bca2890df0d6434024c451c93a23dd8f67169f6e81b8cf2bb22f0d9172b93",
)

OFFICIAL_ARTIFACT = (
    ROOT / "source_artifacts/global-official-builds-us-operator-gap-2026-07-21-v1"
)
OFFICIAL_RECORDED_AT = "2026-07-22T00:01:20Z"
OFFICIAL_MANIFEST_PIN = (
    1_704,
    "2f6c50c48cddf94cf82c2218e6c53857be744a0d1b9c78aeefb830becf24990e",
)
OFFICIAL_MANIFEST_TREE_SHA256 = (
    "bd2ce8f737cf919374783608fae3c2d5ad4698ea569fd78482c873e9ba2c64c5"
)
OFFICIAL_PHYSICAL_TREE_SHA256 = (
    "a3d16d54c370764b8eb4278a6dddf161717825ac3790f731308627301f5ed4c0"
)

ADDITION_ORDER = (
    "sources/curated-official-2026-07-21-riot-rockdale-amd-25mw-retrofit.json",
    "sources/curated-official-2026-07-21-riot-rockdale-amd-first-phase-operational-closure.json",
    "sources/curated-official-2026-07-21-databank-atl5-current-build.json",
    "sources/curated-official-2026-07-21-databank-atl6-current-build.json",
)
ADDITION_PINS = {
    ADDITION_ORDER[0]: (
        6_049,
        "da0c2da55005f36bb518ac6153a7aa8474f8d11a6d34348e27221423bbd42653",
    ),
    ADDITION_ORDER[1]: (
        8_922,
        "d0c749f1d5b8da22adb194cd84ef8a9a9ed6c3fd814fa87e95039999ec201cbc",
    ),
    ADDITION_ORDER[2]: (
        12_462,
        "7f12bee0ea8dc86222fb314df9fcd5e3e2eefccf36284b2ed09868649548656c",
    ),
    ADDITION_ORDER[3]: (
        12_430,
        "1ce9df5cf2293b7b609c621722e05909f3e6a0be369b8fa76c58f49cd873146a",
    ),
}

ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:riot-rockdale-site",
        "curated:riot-rockdale-site:amd-25mw-existing-building-retrofit",
        "curated:riot-rockdale-site:amd-lease-first-phase",
        "curated:databank-lithia-springs-campus",
        "curated:databank-lithia-springs-campus:atl5-current-build",
        "curated:databank-lithia-springs-campus:atl6-current-build",
    }
)
ADDED_PROJECT_KEYS = frozenset(
    key for key in ADDED_ENTITY_KEYS if key.count(":") >= 2
)
ADDED_EVIDENCE_KEYS = frozenset(
    {
        operator.RIOT_LEASE_EVIDENCE,
        operator.RIOT_FY_EVIDENCE,
        operator.DATABANK_CAMPUS_EVIDENCE,
        operator.DATABANK_SOCIAL_EVIDENCE,
        operator.DATABANK_ATL5_EVIDENCE,
        operator.DATABANK_ATL6_EVIDENCE,
    }
)

LIFECYCLE_CONTRACT = frozenset(
    {
        (
            "curated:riot-rockdale-site:amd-25mw-existing-building-retrofit",
            "under_construction",
            "2026-01-16",
            "authoritative_physical_status_update",
        ),
        (
            "curated:riot-rockdale-site:amd-lease-first-phase",
            "operational",
            "2026-01-31",
            "authoritative_status_update",
        ),
        (
            "curated:databank-lithia-springs-campus:atl5-current-build",
            "under_construction",
            "2026-05-07",
            "authoritative_physical_status_update",
        ),
        (
            "curated:databank-lithia-springs-campus:atl6-current-build",
            "under_construction",
            "2026-05-07",
            "authoritative_physical_status_update",
        ),
    }
)
CAPACITY_CONTRACT = frozenset(
    {
        (
            "curated:riot-rockdale-site:amd-25mw-existing-building-retrofit",
            "critical_it_mw",
            "planned",
            "MW",
            25.0,
            "2026-01-16",
            "reported",
        ),
        (
            "curated:databank-lithia-springs-campus:atl5-current-build",
            "critical_it_mw",
            "design",
            "MW",
            48.0,
            "2026-05-14",
            "reported",
        ),
        (
            "curated:databank-lithia-springs-campus:atl6-current-build",
            "critical_it_mw",
            "design",
            "MW",
            72.0,
            "2026-05-14",
            "reported",
        ),
    }
)
OPERATING_MODEL_CONTRACT = frozenset(
    {
        (
            "curated:databank-lithia-springs-campus:atl5-current-build",
            "colocation",
            "2026-05-14",
        ),
        (
            "curated:databank-lithia-springs-campus:atl6-current-build",
            "colocation",
            "2026-05-14",
        ),
    }
)

FRESHNESS_README = f"""
Open seed v87 is the exact accepted v86 successor with only the four
seed-eligible US operator-gap records from
`source_artifacts/{operator.ARTIFACT_ID}` appended in frozen artifact order at
input indices 452 through 455. The artifact manifest is
`{OFFICIAL_MANIFEST_PIN[1]}`, logical tree is
`{OFFICIAL_MANIFEST_TREE_SHA256}`, and physical tree is
`{OFFICIAL_PHYSICAL_TREE_SHA256}`.

The append contributes six coordinate-null entities, six unique official
company-disclosure evidence records, four dated lifecycle observations, two
DataBank colocation observations, and exactly three typed capacity rows. Riot's
existing-building retrofit receives 25 MW critical IT planned capacity; the
separate first AMD lease phase is operational by January 2026 but receives no
MW allocation. ATL5 and ATL6 receive 48 MW and 72 MW critical IT design
capacity respectively.

Riot's future 75 MW option, 100 MW right of first refusal, 200 MW potential
lease total, later 50 MW contracted figure, 700 MW site interconnection, and
Corsicana wording create no normalized claim. DataBank's 180 MW adjacent
substation and 120 MW campus total are not added as facility load or duplicate
capacity. No coordinate, geometry, current load, energy consumption, PUE, WUE,
generation, workload, installed hardware, customer, or current-status claim is
inferred. Every status remains a dated last-observed fact;
`current_status_classification` is `unknown` and
`current_construction_claim` is `false`.
""".strip()


class OpenSeedV87Error(RuntimeError):
    """Raised when a v87 lineage, claim, or publication guard fails closed."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any, *, sort_keys: bool = False) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=sort_keys, ensure_ascii=False) + "\n"
    ).encode()


def _read_json(
    path: Path, *, mode: int | None = None, sort_keys: bool = False
) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise OpenSeedV87Error(f"expected ordinary JSON file: {path}")
    if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
        raise OpenSeedV87Error(f"file mode differs: {path}")
    raw = path.read_bytes()
    document = json.loads(raw)
    if raw != _canonical(document, sort_keys=sort_keys):
        raise OpenSeedV87Error(f"JSON is not canonical: {path}")
    return raw, document


def _validate_official_artifact() -> dict[str, dict[str, Any]]:
    try:
        manifest = operator.validate_artifact(OFFICIAL_ARTIFACT)
        operator._validate_frozen_witnesses()
        operator._validate_source_collisions()
    except operator.USOperatorGapError as error:
        raise OpenSeedV87Error(f"US operator-gap artifact invalid: {error}") from error
    manifest_raw = (OFFICIAL_ARTIFACT / "manifest.json").read_bytes()
    if (
        (len(manifest_raw), _sha256(manifest_raw)) != OFFICIAL_MANIFEST_PIN
        or manifest.get("recorded_at") != OFFICIAL_RECORDED_AT
        or manifest.get("tree_sha256") != OFFICIAL_MANIFEST_TREE_SHA256
        or v69.tree_digest(OFFICIAL_ARTIFACT) != OFFICIAL_PHYSICAL_TREE_SHA256
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
    ):
        raise OpenSeedV87Error("US operator-gap artifact pin or boundary differs")
    snapshot = json.loads((OFFICIAL_ARTIFACT / "source-snapshot.json").read_text())
    records = snapshot.get("source_records")
    if (
        not isinstance(records, list)
        or [row.get("path") for row in records] != list(ADDITION_ORDER)
        or snapshot.get("totals")
        != {
            "candidate_assessments": 4,
            "source_records": 4,
            "seed_eligible_source_records": 4,
            "review_only_candidates": 0,
            "distinct_campuses": 2,
            "projects": 4,
            "distinct_entities": 6,
            "source_document_entity_snapshots": 8,
            "unique_evidence_records": 6,
            "source_document_evidence_references": 9,
            "lifecycle_observations": 4,
            "operating_model_observations": 2,
            "workload_observations": 0,
            "capacity_estimates": 3,
            "coordinates_present": 0,
            "geometry_present": 0,
        }
    ):
        raise OpenSeedV87Error("US operator-gap source snapshot differs")
    documents: dict[str, dict[str, Any]] = {}
    for relative, record in zip(ADDITION_ORDER, records, strict=True):
        path = ROOT / relative
        raw, document = _read_json(path, mode=0o444)
        if (len(raw), _sha256(raw)) != ADDITION_PINS[relative] or (
            record.get("bytes"),
            record.get("sha256"),
        ) != ADDITION_PINS[relative]:
            raise OpenSeedV87Error(f"v87 source pin differs: {relative}")
        documents[relative] = document

    lifecycle = {
        (
            document["project"]["stable_key"],
            row["value"],
            row["as_of_date"],
            row["method"],
        )
        for document in documents.values()
        for row in document["lifecycle"]
    }
    capacities = {
        (
            document[row["entity"]]["stable_key"],
            row["metric"],
            row["stage"],
            row["unit"],
            row["base"],
            row["as_of_date"],
            row["method"],
        )
        for document in documents.values()
        for row in document["capacities"]
    }
    models = {
        (
            document[row["entity"]]["stable_key"],
            row["value"],
            row["as_of_date"],
        )
        for document in documents.values()
        for row in document["operating_models"]
    }
    evidence_keys = {
        row["key"] for document in documents.values() for row in document["evidence"]
    }
    if (
        lifecycle != LIFECYCLE_CONTRACT
        or capacities != CAPACITY_CONTRACT
        or models != OPERATING_MODEL_CONTRACT
        or evidence_keys != ADDED_EVIDENCE_KEYS
        or any(document["workloads"] for document in documents.values())
        or any(
            document[entity][field] is not None
            for document in documents.values()
            for entity in ("campus", "project")
            for field in ("coordinates", "geometry")
        )
    ):
        raise OpenSeedV87Error("US operator-gap normalized claim contract differs")
    return documents


def _base_paths(base: Mapping[str, Any]) -> list[Path]:
    paths = []
    for row in base["curated_inputs"]:
        path = ROOT / row["path"]
        if path.is_symlink() or not path.is_file() or v69.sha256(path) != row["sha256"]:
            raise OpenSeedV87Error(f"accepted v86 input pin differs: {row['path']}")
        paths.append(path)
    return paths


def selected_inputs(
    base: Mapping[str, Any],
    *,
    recorded_at: str,
    validation_wall_clock: datetime | None = None,
) -> tuple[list[dict[str, str]], list[Path]]:
    if base.get("release_id") != v86.RELEASE_ID:
        raise OpenSeedV87Error("v87 base must be exactly accepted v86")
    rows = base.get("curated_inputs")
    if (
        not isinstance(rows, list)
        or len(rows) != 452
        or any(
            not isinstance(row, dict) or set(row) != {"path", "sha256"}
            for row in rows
        )
    ):
        raise OpenSeedV87Error("accepted v86 curated inventory differs")
    documents = _validate_official_artifact()
    target = v70.parse_utc(recorded_at, label="v87 recorded_at")
    wall = validation_wall_clock or datetime.now(UTC)
    if (
        wall.tzinfo is None
        or target > wall.astimezone(UTC)
        or v70.parse_utc(OFFICIAL_RECORDED_AT, label="official recorded_at") > target
    ):
        raise OpenSeedV87Error("v87 publication time precedes an input")

    paths = _base_paths(base)
    base_stable: set[str] = set()
    base_evidence: set[str] = set()
    for path in paths:
        document = json.loads(path.read_text())
        for name in ("campus", "facility", "building", "project"):
            row = document.get(name)
            if isinstance(row, dict) and isinstance(row.get("stable_key"), str):
                base_stable.add(row["stable_key"])
        base_evidence.update(
            row["key"]
            for row in document.get("evidence", [])
            if isinstance(row, dict) and isinstance(row.get("key"), str)
        )
    if base_stable & ADDED_ENTITY_KEYS or base_evidence & ADDED_EVIDENCE_KEYS:
        raise OpenSeedV87Error("v87 append collides with accepted v86 semantics")

    selected = [dict(row) for row in rows]
    for relative in ADDITION_ORDER:
        selected.append({"path": relative, "sha256": ADDITION_PINS[relative][1]})
        paths.append(ROOT / relative)
    if (
        selected[:452] != rows
        or [row["path"] for row in selected[452:]] != list(ADDITION_ORDER)
        or tuple(documents) != ADDITION_ORDER
        or len(selected) != 456
        or len({row["path"] for row in selected}) != 456
    ):
        raise OpenSeedV87Error("v87 did not append exactly four ordered inputs")
    for relative, document in documents.items():
        for index, evidence in enumerate(document["evidence"]):
            retrieved = v70.parse_utc(
                evidence["retrieved_at"],
                label=f"{relative} evidence[{index}].retrieved_at",
            )
            if retrieved > target or retrieved > wall.astimezone(UTC):
                raise OpenSeedV87Error("v87 selected evidence is future-dated")
    return selected, paths


def _guard_state() -> dict[str, Any]:
    _validate_official_artifact()
    return {
        "base_definition": (
            BASE_DEFINITION.stat().st_size,
            v69.sha256(BASE_DEFINITION),
        ),
        "base_manifest": (
            (BASE_RELEASE / "manifest.json").stat().st_size,
            v69.sha256(BASE_RELEASE / "manifest.json"),
        ),
        "base_tree": v69.tree_digest(BASE_RELEASE),
        "base_entities": (
            (BASE_RELEASE / "entities.csv").stat().st_size,
            v69.sha256(BASE_RELEASE / "entities.csv"),
        ),
        "official_manifest": (
            (OFFICIAL_ARTIFACT / "manifest.json").stat().st_size,
            v69.sha256(OFFICIAL_ARTIFACT / "manifest.json"),
        ),
        "official_tree": v69.tree_digest(OFFICIAL_ARTIFACT),
        "additions": {
            relative: ((ROOT / relative).stat().st_size, v69.sha256(ROOT / relative))
            for relative in ADDITION_ORDER
        },
    }


def _table_state(connection: sqlite3.Connection, table: str) -> set[tuple[Any, ...]]:
    return {tuple(row) for row in connection.execute(f"SELECT * FROM {table}")}


def _validate_database_contract(
    connection: sqlite3.Connection,
    base: Mapping[str, Any],
    *,
    recorded_at: str,
) -> None:
    expected_counts = {
        "entities": 933,
        "entity_snapshots": 954,
        "evidence": 769,
        "lifecycle_observations": 541,
        "capacity_estimates": 556,
        "operating_model_observations": 73,
        "workload_observations": 135,
    }
    actual_counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in expected_counts
    }
    if actual_counts != expected_counts:
        raise OpenSeedV87Error(f"v87 database counts differ: {actual_counts}")
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v87-base-", dir="/private/tmp"
    ) as temporary:
        prior = v69._populate_database(
            base,
            _base_paths(base),
            Path(temporary) / "v86.sqlite",
            recorded_at=recorded_at,
        )
        try:
            for table in (
                "entities",
                "evidence",
                "campuses",
                "facilities",
                "buildings",
                "projects",
                "administrative_assignments",
                "entity_snapshots",
                "lifecycle_observations",
                "operating_model_observations",
                "workload_observations",
                "capacity_estimates",
            ):
                if not _table_state(prior, table) <= _table_state(connection, table):
                    raise OpenSeedV87Error(f"v87 changed a v86 database row: {table}")
            before_entities = {
                row[0] for row in prior.execute("SELECT stable_key FROM entities")
            }
            after_entities = {
                row[0] for row in connection.execute("SELECT stable_key FROM entities")
            }
            if (
                after_entities - before_entities != ADDED_ENTITY_KEYS
                or before_entities - after_entities
            ):
                raise OpenSeedV87Error("v87 database identity delta differs")
            before_evidence = set(v70._evidence_by_key(prior))
            after_evidence = set(v70._evidence_by_key(connection))
            if (
                after_evidence - before_evidence != ADDED_EVIDENCE_KEYS
                or before_evidence - after_evidence
            ):
                raise OpenSeedV87Error("v87 database evidence delta differs")
        finally:
            prior.close()

    keys = tuple(sorted(ADDED_ENTITY_KEYS))
    placeholders = ",".join("?" for _ in keys)
    lifecycle = {
        tuple(row)
        for row in connection.execute(
            f"""
            SELECT entities.stable_key, status, as_of_date,
                   lifecycle_observations.method
            FROM lifecycle_observations
            JOIN entities ON entities.id=entity_id
            WHERE entities.stable_key IN ({placeholders})
            """,
            keys,
        )
    }
    capacities = {
        tuple(row)
        for row in connection.execute(
            f"""
            SELECT entities.stable_key, metric, stage, unit, base, as_of_date,
                   capacity_estimates.method
            FROM capacity_estimates
            JOIN entities ON entities.id=entity_id
            WHERE entities.stable_key IN ({placeholders})
            """,
            keys,
        )
    }
    models = {
        tuple(row)
        for row in connection.execute(
            f"""
            SELECT entities.stable_key, operating_model, as_of_date
            FROM operating_model_observations
            JOIN entities ON entities.id=entity_id
            WHERE entities.stable_key IN ({placeholders})
            """,
            keys,
        )
    }
    workloads = connection.execute(
        f"""
        SELECT COUNT(*) FROM workload_observations
        JOIN entities ON entities.id=entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        keys,
    ).fetchone()[0]
    snapshots = list(
        connection.execute(
            f"""
            SELECT entities.stable_key, latitude, longitude, geometry_json
            FROM entity_snapshots
            JOIN entities ON entities.id=entity_id
            WHERE entities.stable_key IN ({placeholders})
            """,
            keys,
        )
    )
    if (
        lifecycle != LIFECYCLE_CONTRACT
        or capacities != CAPACITY_CONTRACT
        or models != OPERATING_MODEL_CONTRACT
        or workloads
        or len(snapshots) != 6
        or any(
            row[1] is not None or row[2] is not None or row[3] not in {None, "null"}
            for row in snapshots
        )
        or any(row[2] == "operational" for row in capacities)
    ):
        raise OpenSeedV87Error("v87 imported claim contract differs")

    evidence_rows = {
        json.loads(row["metadata_json"] or "{}").get("curated_record_key"): row
        for row in connection.execute(
            "SELECT kind, source_family, metadata_json FROM evidence"
        )
        if json.loads(row["metadata_json"] or "{}").get("curated_record_key")
        in ADDED_EVIDENCE_KEYS
    }
    if (
        set(evidence_rows) != ADDED_EVIDENCE_KEYS
        or any(row["kind"] != "company_disclosure" for row in evidence_rows.values())
        or {row["source_family"] for row in evidence_rows.values()}
        != {
            "riot_platforms_company_news",
            "databank_facility_pages",
            "databank_official_linkedin",
        }
    ):
        raise OpenSeedV87Error("v87 imported evidence classification differs")
    current = _current_rows(
        connection, "entity_snapshots", as_of=AS_OF, recorded_at=recorded_at
    )
    kinds = {
        row["id"]: row["kind"]
        for row in connection.execute("SELECT id, kind FROM entities")
    }
    located = [
        row
        for row in current
        if row["latitude"] is not None and row["longitude"] is not None
    ]
    if (
        len(located) != 213
        or sum(kinds[row["entity_id"]] == "campus" for row in located) != 141
    ):
        raise OpenSeedV87Error("v87 coordinate coverage changed")


def _build_database(
    base: Mapping[str, Any],
    paths: list[Path],
    sqlite_path: Path,
    *,
    recorded_at: str,
) -> sqlite3.Connection:
    connection = v69._populate_database(
        base, paths, sqlite_path, recorded_at=recorded_at
    )
    try:
        _validate_database_contract(connection, base, recorded_at=recorded_at)
        return connection
    except Exception:
        connection.close()
        raise


def _augment_release(documents: Mapping[str, str]) -> dict[str, str]:
    output = v86._augment_release(documents)
    output["README.md"] = (
        output["README.md"].rstrip() + "\n\n" + FRESHNESS_README + "\n"
    )
    manifest = json.loads(output["manifest.json"])
    for filename, text in output.items():
        if filename == "manifest.json":
            continue
        manifest["files"][filename] = {
            "bytes": len(text.encode()),
            "sha256": _sha256(text.encode()),
        }
    output["manifest.json"] = _canonical(manifest, sort_keys=True).decode()
    return output


def _write_release(
    connection: sqlite3.Connection,
    output: Path,
    *,
    recorded_at: str,
    precreated: bool = False,
) -> None:
    if precreated:
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise OpenSeedV87Error("precreated v87 release stage must be empty")
    else:
        output.mkdir(parents=True, exist_ok=False)
    documents = build_release_documents(
        connection,
        as_of=AS_OF,
        recorded_at=recorded_at,
        publication_contract_version=4,
    )
    for filename, text in _augment_release(documents).items():
        path = output / filename
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(text.encode())
            stream.flush()
            os.fsync(stream.fileno())


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _validate_release_facts(stage: Path, *, recorded_at: str) -> None:
    if stage.is_symlink() or not stage.is_dir():
        raise OpenSeedV87Error("v87 release is not an ordinary directory")
    entries = {path.name: path for path in stage.iterdir()}
    if len(entries) != 14 or any(path.is_symlink() or not path.is_file() for path in entries.values()):
        raise OpenSeedV87Error("v87 release file inventory differs")
    _raw, manifest = _read_json(stage / "manifest.json", sort_keys=True)
    if (
        manifest.get("as_of") != AS_OF
        or manifest.get("recorded_at") != recorded_at
        or manifest.get("publication_contract_version") != 4
        or set(entries) != set(manifest["files"]) | {"manifest.json"}
    ):
        raise OpenSeedV87Error("v87 manifest release facts differ")
    for filename, pin in manifest["files"].items():
        raw = entries[filename].read_bytes()
        if (len(raw), _sha256(raw)) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV87Error(f"v87 release pin differs: {filename}")

    source_inputs = json.loads((stage / "source_inputs.json").read_text())
    sources = source_inputs.get("sources")
    added_source_inputs = {
        row.get("provenance", {}).get("curated_record_key"): row
        for row in sources or []
        if row.get("provenance", {}).get("curated_record_key")
        in ADDED_EVIDENCE_KEYS
    }
    if (
        not isinstance(sources, list)
        or len(sources) != 544
        or set(added_source_inputs) != ADDED_EVIDENCE_KEYS
        or any(
            row.get("license") != "all-rights-reserved"
            for row in added_source_inputs.values()
        )
    ):
        raise OpenSeedV87Error("v87 source-input inventory differs")

    entities = {
        row["stable_key"]: row
        for row in _csv_rows(stage / "entities.csv")
        if row["stable_key"] in ADDED_ENTITY_KEYS
    }
    if set(entities) != ADDED_ENTITY_KEYS:
        raise OpenSeedV87Error("v87 added entity export differs")
    if any(
        row["latitude"]
        or row["longitude"]
        or row["geometry_json"] not in {"", "null"}
        or row["country"] != "United States"
        for row in entities.values()
    ):
        raise OpenSeedV87Error("v87 added entity placement differs")
    expected_status = {
        "curated:riot-rockdale-site": ("", ""),
        "curated:databank-lithia-springs-campus": ("", ""),
        "curated:riot-rockdale-site:amd-25mw-existing-building-retrofit": (
            "under_construction",
            "2026-01-16",
        ),
        "curated:riot-rockdale-site:amd-lease-first-phase": (
            "operational",
            "2026-01-31",
        ),
        "curated:databank-lithia-springs-campus:atl5-current-build": (
            "under_construction",
            "2026-05-07",
        ),
        "curated:databank-lithia-springs-campus:atl6-current-build": (
            "under_construction",
            "2026-05-07",
        ),
    }
    if {
        key: (row["status"], row["status_as_of"]) for key, row in entities.items()
    } != expected_status:
        raise OpenSeedV87Error("v87 exported lifecycle facts differ")
    if (
        entities[
            "curated:riot-rockdale-site:amd-lease-first-phase"
        ]["capacity_estimates_json"]
        != "[]"
    ):
        raise OpenSeedV87Error("first operational phase inherited unsupported MW")

    expected_capacity = {
        "curated:riot-rockdale-site:amd-25mw-existing-building-retrofit": (
            "planned",
            25.0,
        ),
        "curated:databank-lithia-springs-campus:atl5-current-build": (
            "design",
            48.0,
        ),
        "curated:databank-lithia-springs-campus:atl6-current-build": (
            "design",
            72.0,
        ),
    }
    for key, contract in expected_capacity.items():
        rows = json.loads(entities[key]["capacity_estimates_json"])
        if len(rows) != 1 or (
            rows[0]["metric"],
            rows[0]["stage"],
            rows[0]["unit"],
            rows[0]["base"],
        ) != ("critical_it_mw", contract[0], "MW", contract[1]):
            raise OpenSeedV87Error(f"v87 exported capacity differs: {key}")
    for key in (
        "curated:databank-lithia-springs-campus:atl5-current-build",
        "curated:databank-lithia-springs-campus:atl6-current-build",
    ):
        if entities[key]["operating_model"] != "colocation":
            raise OpenSeedV87Error("v87 DataBank colocation export differs")
    for key in (
        "curated:riot-rockdale-site:amd-25mw-existing-building-retrofit",
        "curated:riot-rockdale-site:amd-lease-first-phase",
    ):
        if (
            entities[key]["operator"] != "Riot Platforms, Inc."
            or entities[key]["tenants"] != "Advanced Micro Devices, Inc."
        ):
            raise OpenSeedV87Error("v87 Riot role export differs")

    freshness = {
        row["stable_key"]: row
        for row in _csv_rows(stage / "lifecycle_freshness.csv")
        if row["stable_key"] in ADDED_PROJECT_KEYS
    }
    if set(freshness) != ADDED_PROJECT_KEYS or any(
        row["status_semantics"] != "last_observed"
        or row["current_status_classification"] != "unknown"
        or row["current_construction_claim"] != "false"
        for row in freshness.values()
    ):
        raise OpenSeedV87Error("v87 freshness boundary differs")
    pipeline = {
        row["stable_key"]
        for row in _csv_rows(stage / "construction_pipeline.csv")
        if row["stable_key"] in ADDED_PROJECT_KEYS
    }
    if pipeline != {
        "curated:riot-rockdale-site:amd-25mw-existing-building-retrofit",
        "curated:databank-lithia-springs-campus:atl5-current-build",
        "curated:databank-lithia-springs-campus:atl6-current-build",
    }:
        raise OpenSeedV87Error("v87 construction-pipeline delta differs")
    readme = (stage / "README.md").read_text(encoding="utf-8")
    for marker in (
        "Open seed v87 is the exact accepted v86 successor",
        "separate first AMD lease phase is operational by January 2026 but receives no",
        "current_status_classification` is `unknown`",
        "current_construction_claim` is `false`",
    ):
        if marker not in readme:
            raise OpenSeedV87Error(f"v87 README guardrail differs: {marker}")


def _validate_definition(
    document: Mapping[str, Any],
    base: Mapping[str, Any],
    *,
    validation_wall_clock: datetime,
) -> str:
    if set(document) != set(base) or document.get("release_id") != RELEASE_ID:
        raise OpenSeedV87Error("v87 definition identity or schema differs")
    build = document.get("build")
    if not isinstance(build, dict) or set(build) != {"as_of", "recorded_at"}:
        raise OpenSeedV87Error("v87 definition build carrier differs")
    if build["as_of"] != AS_OF:
        raise OpenSeedV87Error("v87 as_of differs")
    expected_summary = document.get("expected_summary")
    if not isinstance(expected_summary, dict) or set(expected_summary) != set(
        base["expected_summary"]
    ):
        raise OpenSeedV87Error("v87 expected-summary key contract differs")
    recorded = v70.parse_utc(build["recorded_at"], label="v87 recorded_at")
    if (
        validation_wall_clock.tzinfo is None
        or recorded > validation_wall_clock.astimezone(UTC)
    ):
        raise OpenSeedV87Error("v87 recorded_at is later than validation wall clock")
    for key in (
        "epoch_capture",
        "expected_epoch_result",
        "freshness_contract",
        "publication_contract_version",
        "schema_version",
        "scope",
    ):
        if document.get(key) != base.get(key):
            raise OpenSeedV87Error(f"v87 inherited definition field differs: {key}")
    return build["recorded_at"]


def _validate_publication_times(
    definition: Path,
    release: Path,
    *,
    recorded_at: str,
    require_live: bool,
) -> None:
    target = v70.parse_utc(recorded_at, label="v87 recorded_at")
    for path in (definition, release, *release.iterdir()):
        metadata = path.stat(follow_symlinks=False)
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV87Error(f"v87 staged inode post-dates recorded_at: {path.name}")
    if require_live:
        if datetime.now(UTC) < target:
            raise OpenSeedV87Error("v87 recorded_at is not live")
        for path in (definition, release):
            if path.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
                raise OpenSeedV87Error(
                    f"v87 final root ctime predates recorded_at: {path.name}"
                )


def _validate_guard(guard: Mapping[str, Any]) -> None:
    base_files = list(BASE_RELEASE.iterdir()) if BASE_RELEASE.is_dir() else []
    if (
        v86.DEFINITION != BASE_DEFINITION
        or v86.RELEASE != BASE_RELEASE
        or BASE_DEFINITION.is_symlink()
        or not BASE_DEFINITION.is_file()
        or stat.S_IMODE(BASE_DEFINITION.stat().st_mode) != 0o444
        or BASE_RELEASE.is_symlink()
        or not BASE_RELEASE.is_dir()
        or stat.S_IMODE(BASE_RELEASE.stat().st_mode) != 0o555
        or not base_files
        or any(
            path.is_symlink()
            or not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != 0o444
            for path in base_files
        )
        or guard["base_definition"] != BASE_DEFINITION_PIN
        or guard["base_manifest"] != BASE_MANIFEST_PIN
        or guard["base_tree"] != BASE_TREE_SHA256
        or guard["base_entities"] != BASE_ENTITIES_PIN
    ):
        raise OpenSeedV87Error("accepted v86 base pin differs")
    if (
        guard["official_manifest"] != OFFICIAL_MANIFEST_PIN
        or guard["official_tree"] != OFFICIAL_PHYSICAL_TREE_SHA256
        or guard["additions"] != ADDITION_PINS
    ):
        raise OpenSeedV87Error("v87 official-source pin differs")


def validate_open_seed_v87(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
    require_live: bool = True,
) -> dict[str, Any]:
    if replay_count != 2:
        raise OpenSeedV87Error("v87 requires exactly two offline replays")
    wall = validation_wall_clock or datetime.now(UTC)
    guard = _guard_state()
    _validate_guard(guard)
    base = json.loads(BASE_DEFINITION.read_text())
    _definition_raw, definition = _read_json(
        definition_path, mode=0o444, sort_keys=True
    )
    recorded_at = _validate_definition(definition, base, validation_wall_clock=wall)
    selected, paths = selected_inputs(
        base, recorded_at=recorded_at, validation_wall_clock=wall
    )
    if definition.get("curated_inputs") != selected:
        raise OpenSeedV87Error("v87 selected input inventory differs")
    if release_path.is_symlink() or not release_path.is_dir():
        raise OpenSeedV87Error("v87 release must be an ordinary directory")
    if require_frozen and stat.S_IMODE(release_path.stat().st_mode) != 0o555:
        raise OpenSeedV87Error("v87 release root is not frozen")
    release_files = {path.name: path for path in release_path.iterdir()}
    if any(path.is_symlink() or not path.is_file() for path in release_files.values()):
        raise OpenSeedV87Error("v87 release contains a non-file")
    if require_frozen and any(
        stat.S_IMODE(path.stat().st_mode) != 0o444
        for path in release_files.values()
    ):
        raise OpenSeedV87Error("v87 release file is not frozen")
    manifest_raw, manifest = _read_json(
        release_path / "manifest.json", mode=0o444, sort_keys=True
    )
    if _sha256(manifest_raw) != definition["expected_release"].get(
        "manifest_sha256"
    ):
        raise OpenSeedV87Error("v87 manifest hash differs")
    expected_release = {
        key: value
        for key, value in definition["expected_release"].items()
        if key != "manifest_sha256"
    }
    if {key: value for key, value in manifest.items() if key != "files"} != expected_release:
        raise OpenSeedV87Error("v87 expected release facts differ")
    if set(release_files) != set(manifest["files"]) | {"manifest.json"}:
        raise OpenSeedV87Error("v87 release file inventory differs")
    for filename, pin in manifest["files"].items():
        raw = (release_path / filename).read_bytes()
        if (len(raw), _sha256(raw)) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV87Error(f"v87 release pin differs: {filename}")
    _validate_publication_times(
        definition_path,
        release_path,
        recorded_at=recorded_at,
        require_live=require_live,
    )
    _validate_release_facts(release_path, recorded_at=recorded_at)
    summary = json.loads((release_path / "summary.json").read_text())
    if {key: summary[key] for key in definition["expected_summary"]} != definition[
        "expected_summary"
    ]:
        raise OpenSeedV87Error("v87 expected summary differs")

    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v87-replay-{replay + 1}-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            connection = _build_database(
                base, paths, root / "atlas.sqlite", recorded_at=recorded_at
            )
            try:
                replay_release = root / "release"
                _write_release(connection, replay_release, recorded_at=recorded_at)
            finally:
                connection.close()
            _validate_release_facts(replay_release, recorded_at=recorded_at)
            if {path.name for path in replay_release.iterdir()} != set(release_files):
                raise OpenSeedV87Error("v87 replay file inventory differs")
            for filename, frozen in release_files.items():
                if (replay_release / filename).read_bytes() != frozen.read_bytes():
                    raise OpenSeedV87Error(f"v87 offline replay differs: {filename}")
    if _guard_state() != guard:
        raise OpenSeedV87Error("v87 validation mutated accepted inputs")
    return manifest


def _path_identity(path: Path, *, directory: bool) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    expected = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if not expected:
        raise OpenSeedV87Error(f"v87 stage type differs: {path}")
    return metadata.st_dev, metadata.st_ino


def _release_identities(root: Path) -> dict[str, tuple[int, int]]:
    return {
        path.name: _path_identity(path, directory=False) for path in root.iterdir()
    }


def _assert_release_identities(
    root: Path,
    root_identity: tuple[int, int],
    members: Mapping[str, tuple[int, int]],
) -> None:
    if _path_identity(root, directory=True) != root_identity:
        raise OpenSeedV87Error("v87 release stage root identity changed")
    if _release_identities(root) != dict(members):
        raise OpenSeedV87Error("v87 release stage member identity changed")


def _discard_release_stage(
    root: Path,
    root_identity: tuple[int, int],
    members: Mapping[str, tuple[int, int]],
) -> None:
    if not root.exists() and not root.is_symlink():
        return
    _assert_release_identities(root, root_identity, members)
    root.chmod(0o700)
    for path in root.iterdir():
        path.chmod(0o600)
        path.unlink()
    root.rmdir()


def _discard_file_stage(path: Path, identity: tuple[int, int]) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if _path_identity(path, directory=False) != identity:
        raise OpenSeedV87Error("refusing substituted v87 definition cleanup")
    path.chmod(0o600)
    path.unlink()


def _fsync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise OpenSeedV87Error("active v87 publication lock exists") from error
    os.write(descriptor, f"pid={os.getpid()}\n".encode())
    os.fsync(descriptor)
    metadata = os.fstat(descriptor)
    identity = (metadata.st_dev, metadata.st_ino)
    try:
        yield
    finally:
        os.close(descriptor)
        try:
            current = PUBLICATION_LOCK.stat(follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISREG(current.st_mode) or (
                current.st_dev,
                current.st_ino,
            ) != identity:
                raise OpenSeedV87Error("refusing substituted v87 lock cleanup")
            PUBLICATION_LOCK.unlink()


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _require_absent(label: str) -> None:
    if DEFINITION.exists() or DEFINITION.is_symlink():
        raise OpenSeedV87Error(f"{label} v87 definition collision")
    if RELEASE.exists() or RELEASE.is_symlink():
        raise OpenSeedV87Error(f"{label} v87 release collision")


def _rollback_release(release_identity: tuple[int, int], release_stage: Path) -> None:
    if _path_identity(RELEASE, directory=True) != release_identity:
        raise OpenSeedV87Error("refusing rollback of substituted v87 release")
    if release_stage.exists() or release_stage.is_symlink():
        raise OpenSeedV87Error("v87 release rollback stage is occupied")
    v69.promote_noreplace(RELEASE, release_stage)


def _rollback_definition(
    definition_identity: tuple[int, int], definition_stage: Path
) -> None:
    if _path_identity(DEFINITION, directory=False) != definition_identity:
        raise OpenSeedV87Error("refusing rollback of substituted v87 definition")
    if definition_stage.exists() or definition_stage.is_symlink():
        raise OpenSeedV87Error("v87 definition rollback stage is occupied")
    v69.promote_noreplace(DEFINITION, definition_stage)


def build_open_seed_v87(recorded_at: str | None = None) -> dict[str, Any]:
    """Build and atomically publish the four-source v86 successor."""

    if (DEFINITION.exists() or DEFINITION.is_symlink()) and (
        RELEASE.exists() or RELEASE.is_symlink()
    ):
        manifest = validate_open_seed_v87()
        return {
            "definition": str(DEFINITION),
            "definition_sha256": v69.sha256(DEFINITION),
            "manifest_sha256": v69.sha256(RELEASE / "manifest.json"),
            "recorded_at": manifest["recorded_at"],
            "release": str(RELEASE),
            "release_tree_sha256": v69.tree_digest(RELEASE),
            "status": "existing-identical",
        }
    if (
        DEFINITION.exists()
        or DEFINITION.is_symlink()
        or RELEASE.exists()
        or RELEASE.is_symlink()
    ):
        raise OpenSeedV87Error("partial v87 final-path collision")

    guard = _guard_state()
    _validate_guard(guard)
    target = (
        v70.parse_utc(recorded_at, label="v87 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise OpenSeedV87Error("v87 recorded_at must be future before staging")
    recorded_at = target.isoformat(timespec="seconds").replace("+00:00", "Z")

    with _publication_lock():
        _require_absent("initial")
        release_stage = Path(
            tempfile.mkdtemp(prefix=f".{RELEASE.name}.", dir=RELEASE.parent)
        )
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{DEFINITION.name}.", suffix=".stage", dir=DEFINITION.parent
        )
        definition_stage = Path(temporary)
        definition_identity = _path_identity(definition_stage, directory=False)
        release_identity = _path_identity(release_stage, directory=True)
        release_members: dict[str, tuple[int, int]] = {}
        published_release = False
        published_definition = False
        try:
            os.close(descriptor)
            base = json.loads(BASE_DEFINITION.read_text())
            input_rows, paths = selected_inputs(
                base, recorded_at=recorded_at, validation_wall_clock=target
            )
            with tempfile.TemporaryDirectory(
                prefix="open-seed-v87-db-", dir="/private/tmp"
            ) as temporary_database:
                connection = _build_database(
                    base,
                    paths,
                    Path(temporary_database) / "atlas.sqlite",
                    recorded_at=recorded_at,
                )
                try:
                    _write_release(
                        connection,
                        release_stage,
                        recorded_at=recorded_at,
                        precreated=True,
                    )
                    summary = summarize(
                        connection, as_of=AS_OF, recorded_at=recorded_at
                    )
                finally:
                    connection.close()
            _validate_release_facts(release_stage, recorded_at=recorded_at)
            manifest_raw = (release_stage / "manifest.json").read_bytes()
            manifest = json.loads(manifest_raw)
            expected_release = {
                key: value for key, value in manifest.items() if key != "files"
            }
            expected_release["manifest_sha256"] = _sha256(manifest_raw)
            definition = dict(base)
            definition["build"] = {"as_of": AS_OF, "recorded_at": recorded_at}
            definition["curated_inputs"] = input_rows
            definition["expected_release"] = expected_release
            definition["expected_summary"] = {
                key: summary[key] for key in base["expected_summary"]
            }
            definition["release_id"] = RELEASE_ID
            with definition_stage.open("r+b") as stream:
                stream.write(_canonical(definition, sort_keys=True))
                stream.truncate()
                stream.flush()
                os.fsync(stream.fileno())
            definition_stage.chmod(0o444)
            _fsync(definition_stage)
            for path in release_stage.iterdir():
                path.chmod(0o444)
                _fsync(path)
            release_stage.chmod(0o555)
            _fsync(release_stage)
            release_members = _release_identities(release_stage)
            _validate_publication_times(
                definition_stage,
                release_stage,
                recorded_at=recorded_at,
                require_live=False,
            )
            _require_absent("pre-wait")
            frozen_definition = definition_stage.read_bytes()
            frozen_tree = v69.tree_digest(release_stage)
            _wait_until(target)
            _require_absent("late")
            if _path_identity(definition_stage, directory=False) != definition_identity:
                raise OpenSeedV87Error("v87 definition stage identity changed")
            _assert_release_identities(
                release_stage, release_identity, release_members
            )
            if (
                definition_stage.read_bytes() != frozen_definition
                or v69.tree_digest(release_stage) != frozen_tree
            ):
                raise OpenSeedV87Error("v87 private stage changed while waiting")
            _validate_publication_times(
                definition_stage,
                release_stage,
                recorded_at=recorded_at,
                require_live=False,
            )
            v69.promote_noreplace(release_stage, RELEASE)
            published_release = True
            try:
                v69.promote_noreplace(definition_stage, DEFINITION)
                published_definition = True
            except BaseException as error:
                try:
                    _rollback_release(release_identity, release_stage)
                    published_release = False
                except Exception as rollback_error:
                    error.add_note(f"v87 release rollback failed: {rollback_error}")
                raise
            try:
                manifest = validate_open_seed_v87(DEFINITION, RELEASE)
            except BaseException as error:
                rollback_errors = []
                try:
                    _rollback_definition(definition_identity, definition_stage)
                    published_definition = False
                except Exception as rollback_error:
                    rollback_errors.append(
                        f"v87 definition rollback failed: {rollback_error}"
                    )
                try:
                    _rollback_release(release_identity, release_stage)
                    published_release = False
                except Exception as rollback_error:
                    rollback_errors.append(
                        f"v87 release rollback failed: {rollback_error}"
                    )
                for note in rollback_errors:
                    error.add_note(note)
                raise
        finally:
            if not published_release and release_stage.exists():
                if release_members:
                    _discard_release_stage(
                        release_stage, release_identity, release_members
                    )
                else:
                    shutil.rmtree(release_stage)
            if not published_definition and definition_stage.exists():
                _discard_file_stage(definition_stage, definition_identity)
    if _guard_state() != guard:
        raise OpenSeedV87Error("v87 build mutated accepted inputs")
    return {
        "definition": str(DEFINITION),
        "definition_sha256": v69.sha256(DEFINITION),
        "manifest_sha256": v69.sha256(RELEASE / "manifest.json"),
        "recorded_at": manifest["recorded_at"],
        "release": str(RELEASE),
        "release_tree_sha256": v69.tree_digest(RELEASE),
        "status": "published",
    }


def main() -> int:
    print(json.dumps(build_open_seed_v87(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
