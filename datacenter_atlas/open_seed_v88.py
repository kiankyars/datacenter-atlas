"""Build open seed v88 as the strict five-source append successor to v87."""

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

from . import global_official_current_build_gap_20260721 as official
from . import open_seed_v69 as v69
from . import open_seed_v70 as v70
from . import open_seed_v87 as v87
from .publication_release import build_release_documents
from .service import _current_rows, summarize


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v87.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v87"
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v88.json"
RELEASE_ID = "2026-07-21-open-seed-v88"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v88.lock"
AS_OF = "2026-07-21"

BASE_RECORDED_AT = "2026-07-22T00:06:19Z"
BASE_DEFINITION_PIN = (
    103_031,
    "bf0ef1b6bbe9f4f7edb4525de89d487de1e03ed5eaaccc1a0e122e24d5c9bf08",
)
BASE_MANIFEST_PIN = (
    15_566,
    "6b2787e982049f1bcab139fce874880499c8610e2e71bb6bde091bcc101abf35",
)
BASE_TREE_SHA256 = "02be747070df5f998080ca7c54a94146649a54b84078850c4c31522ae05c6185"
BASE_ENTITIES_PIN = (
    984_920,
    "1d214eba7d0482dae402930cfa5eb1b6e26b3df6a60c27571670c0929c8f02dc",
)

OFFICIAL_ARTIFACT = (
    ROOT / "source_artifacts/global-official-current-build-gap-2026-07-21-v1"
)
OFFICIAL_RECORDED_AT = "2026-07-22T00:37:21Z"
OFFICIAL_MANIFEST_PIN = (
    1_786,
    "e51e8c683de9061e99943a858c8281b7752650432368098a5a9b10e3fbe5a42e",
)
OFFICIAL_MANIFEST_TREE_SHA256 = (
    "5f78e1dc4421ad3ae5767633432ad1c9dd2d379460662d1d29fa396c46cb30b2"
)
OFFICIAL_PHYSICAL_TREE_SHA256 = (
    "e23460e6c67c9faabc81f1f23ceceec2a584a5d84f716166a7f36a2a38039de5"
)

ADDITION_ORDER = tuple(f"sources/{name}" for name in official.SOURCE_FILENAMES)
ADDITION_PINS = {
    ADDITION_ORDER[0]: (
        10_941,
        "834ebc4650728afe565f02886cf81410ee40bb702ad33506edbcce8aeac041e1",
    ),
    ADDITION_ORDER[1]: (
        10_961,
        "c5ac34d490eda960826dfc9b2acb7f02b3406007960d40d29b1583525222a129",
    ),
    ADDITION_ORDER[2]: (
        6_493,
        "327a54c170b317d83b01e458e58e242e12191f6fa29326794fed678a6ae385a6",
    ),
    ADDITION_ORDER[3]: (
        4_317,
        "12068476421f5ffb15bc8115083f5ef189b066e7bc98e644ac6ed1207ddcf6fd",
    ),
    ADDITION_ORDER[4]: (
        4_842,
        "cbc2c60db95bf683b9e063d5952e60072189a171cde563527c24fb800d1323ba",
    ),
}

ADDED_ENTITY_KEYS = frozenset(
    {
        official.VINELAND_CAMPUS,
        official.VINELAND_PHASE_1,
        official.VINELAND_PHASE_2,
        official.DENTON_PROJECT,
        official.WEBSTER_CAMPUS,
        official.WEBSTER_PROJECT,
        official.ROWAN_CAMPUS,
        official.ROWAN_PROJECT,
    }
)
REUSED_ENTITY_KEYS = frozenset({official.DENTON_CAMPUS})
ADDED_PROJECT_KEYS = frozenset(
    {
        official.VINELAND_PHASE_1,
        official.VINELAND_PHASE_2,
        official.DENTON_PROJECT,
        official.WEBSTER_PROJECT,
        official.ROWAN_PROJECT,
    }
)
ADDED_EVIDENCE_KEYS = frozenset(
    {
        official.VINELAND_AGENDA_EVIDENCE,
        official.VINELAND_NEWSLETTER_EVIDENCE,
        official.NEBIUS_EVIDENCE,
        official.CORE_DENTON_EVIDENCE,
        official.WEBSTER_EVIDENCE,
        official.ROWAN_EVIDENCE,
    }
)
ADDED_EXPORTED_EVIDENCE_KEYS = frozenset(
    {
        official.VINELAND_AGENDA_EVIDENCE,
        official.CORE_DENTON_EVIDENCE,
        official.WEBSTER_EVIDENCE,
        official.ROWAN_EVIDENCE,
    }
)
LIFECYCLE_CONTRACT = frozenset(
    {
        (
            official.VINELAND_PHASE_1,
            "under_construction",
            "2026-03-23",
            "authoritative_physical_status_update",
        ),
        (
            official.VINELAND_PHASE_2,
            "under_construction",
            "2026-03-23",
            "authoritative_physical_status_update",
        ),
        (
            official.DENTON_PROJECT,
            "under_construction",
            "2026-04-21",
            "authoritative_physical_status_update",
        ),
        (
            official.WEBSTER_PROJECT,
            "under_construction",
            "2026-05-21",
            "authoritative_physical_status_update",
        ),
        (
            official.ROWAN_PROJECT,
            "under_construction",
            "2026-04-15",
            "authoritative_physical_status_update",
        ),
    }
)
CAPACITY_CONTRACT = frozenset(
    {
        (
            official.DENTON_PROJECT,
            "critical_it_mw",
            "design",
            "MW",
            262.0,
            "2026-04-21",
            "reported",
        ),
        (
            official.DENTON_CAMPUS,
            "grid_connection_mw",
            "contracted",
            "MW",
            394.0,
            "2026-04-21",
            "reported",
        ),
    }
)

FRESHNESS_README = f"""
Open seed v88 is the exact accepted v87 successor with only the five
seed-eligible records from `source_artifacts/{official.ARTIFACT_ID}` appended
at input indices 456 through 460. The artifact manifest is
`{OFFICIAL_MANIFEST_PIN[1]}`, logical tree is
`{OFFICIAL_MANIFEST_TREE_SHA256}`, and physical tree is
`{OFFICIAL_PHYSICAL_TREE_SHA256}`.

The append creates eight entities and reuses exactly one existing entity: the
v87 Denton campus at 8171 Jim Christal Road. It contributes five dated
under-construction project observations and exactly two typed capacity rows:
262 MW Denton project critical IT at design scope and approximately 394 MW
contracted grid connection at total-potential-campus scope. The approximate
132 MW operational Denton subset is neither normalized nor subtracted.

DataOne Vineland's 300 MW label remains future untyped whole-site metadata.
Palm Coast remains review-only as a cable landing station, and Fort Worth
District 7 remains review-only anonymous count evidence; neither creates a
seed input. No current-status extrapolation, Microsoft role, actual workload,
energy consumption, PUE, WUE, generation, coordinate, geometry, satellite,
or computer-vision assertion is added. Every appended status is a dated
last-observed fact; `current_status_classification` is `unknown` and
`current_construction_claim` is `false`.
""".strip()


class OpenSeedV88Error(RuntimeError):
    """Raised when a v88 lineage, claim, or publication guard fails closed."""


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
        raise OpenSeedV88Error(f"expected ordinary JSON file: {path}")
    if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
        raise OpenSeedV88Error(f"file mode differs: {path}")
    raw = path.read_bytes()
    document = json.loads(raw)
    if raw != _canonical(document, sort_keys=sort_keys):
        raise OpenSeedV88Error(f"JSON is not canonical: {path}")
    return raw, document


def _validate_official_artifact() -> dict[str, dict[str, Any]]:
    try:
        manifest = official.validate_artifact(OFFICIAL_ARTIFACT)
        official._validate_frozen_witnesses()
        official._validate_source_collisions()
    except official.OfficialCurrentBuildGapError as error:
        raise OpenSeedV88Error(f"official current-build artifact invalid: {error}") from error
    manifest_raw = (OFFICIAL_ARTIFACT / "manifest.json").read_bytes()
    if (
        (len(manifest_raw), _sha256(manifest_raw)) != OFFICIAL_MANIFEST_PIN
        or manifest.get("recorded_at") != OFFICIAL_RECORDED_AT
        or manifest.get("tree_sha256") != OFFICIAL_MANIFEST_TREE_SHA256
        or v69.tree_digest(OFFICIAL_ARTIFACT) != OFFICIAL_PHYSICAL_TREE_SHA256
        or manifest.get("candidate_assessments") != 6
        or manifest.get("curated_source_records") != 5
        or manifest.get("seed_eligible_candidates") != 4
        or manifest.get("review_only_candidates") != 2
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
    ):
        raise OpenSeedV88Error("official current-build artifact pin or boundary differs")
    snapshot = json.loads(
        (OFFICIAL_ARTIFACT / "source-snapshot.json").read_text(encoding="utf-8")
    )
    records = snapshot.get("source_records")
    if (
        not isinstance(records, list)
        or [row.get("path") for row in records] != list(ADDITION_ORDER)
        or snapshot.get("totals")
        != {
            "candidate_assessments": 6,
            "source_records": 5,
            "seed_eligible_candidates": 4,
            "seed_eligible_source_records": 5,
            "review_only_candidates": 2,
            "distinct_campuses_in_source_records": 4,
            "projects": 5,
            "distinct_entities_in_source_records": 9,
            "new_entities_against_v87": 8,
            "reused_exact_entities": 1,
            "source_document_entity_snapshots": 10,
            "unique_imported_entity_snapshots": 9,
            "unique_evidence_records": 6,
            "source_document_evidence_references": 9,
            "lifecycle_observations": 5,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 2,
            "coordinates_present": 0,
            "geometry_present": 0,
        }
    ):
        raise OpenSeedV88Error("official current-build source snapshot differs")

    documents: dict[str, dict[str, Any]] = {}
    for relative, record in zip(ADDITION_ORDER, records, strict=True):
        path = ROOT / relative
        raw, document = _read_json(path, mode=0o444)
        if (len(raw), _sha256(raw)) != ADDITION_PINS[relative] or (
            record.get("bytes"),
            record.get("sha256"),
        ) != ADDITION_PINS[relative]:
            raise OpenSeedV88Error(f"v88 source pin differs: {relative}")
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
    evidence_keys = {
        row["key"] for document in documents.values() for row in document["evidence"]
    }
    if (
        lifecycle != LIFECYCLE_CONTRACT
        or capacities != CAPACITY_CONTRACT
        or evidence_keys != ADDED_EVIDENCE_KEYS
        or any(document["operating_models"] for document in documents.values())
        or any(document["workloads"] for document in documents.values())
        or any(
            document[entity]["roles"]
            for document in documents.values()
            for entity in ("campus", "project")
        )
        or any(
            document[entity][field] is not None
            for document in documents.values()
            for entity in ("campus", "project")
            for field in ("coordinates", "geometry")
        )
    ):
        raise OpenSeedV88Error("official current-build normalized claim contract differs")
    return documents


def _base_paths(base: Mapping[str, Any]) -> list[Path]:
    paths = []
    for row in base["curated_inputs"]:
        path = ROOT / row["path"]
        if path.is_symlink() or not path.is_file() or v69.sha256(path) != row["sha256"]:
            raise OpenSeedV88Error(f"accepted v87 input pin differs: {row['path']}")
        paths.append(path)
    return paths


def selected_inputs(
    base: Mapping[str, Any],
    *,
    recorded_at: str,
    validation_wall_clock: datetime | None = None,
) -> tuple[list[dict[str, str]], list[Path]]:
    if base.get("release_id") != v87.RELEASE_ID:
        raise OpenSeedV88Error("v88 base must be exactly accepted v87")
    rows = base.get("curated_inputs")
    if (
        not isinstance(rows, list)
        or len(rows) != 456
        or any(
            not isinstance(row, dict) or set(row) != {"path", "sha256"}
            for row in rows
        )
    ):
        raise OpenSeedV88Error("accepted v87 curated inventory differs")
    documents = _validate_official_artifact()
    target = v70.parse_utc(recorded_at, label="v88 recorded_at")
    wall = validation_wall_clock or datetime.now(UTC)
    if (
        wall.tzinfo is None
        or target > wall.astimezone(UTC)
        or v70.parse_utc(OFFICIAL_RECORDED_AT, label="official recorded_at") > target
    ):
        raise OpenSeedV88Error("v88 publication time precedes an input")

    paths = _base_paths(base)
    base_evidence: set[str] = set()
    for path in paths:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        base_evidence.update(
            row["key"]
            for row in document.get("evidence", [])
            if isinstance(row, dict) and isinstance(row.get("key"), str)
        )
    if base_evidence & ADDED_EVIDENCE_KEYS:
        raise OpenSeedV88Error("v88 evidence append collides with accepted v87")
    collision = official._base_collision_witness(documents)
    if collision.get("exact_stable_key_collisions") != [official.DENTON_CAMPUS]:
        raise OpenSeedV88Error("v88 Denton collision resolution differs")

    selected = [dict(row) for row in rows]
    for relative in ADDITION_ORDER:
        selected.append({"path": relative, "sha256": ADDITION_PINS[relative][1]})
        paths.append(ROOT / relative)
    if (
        selected[:456] != rows
        or [row["path"] for row in selected[456:]] != list(ADDITION_ORDER)
        or tuple(documents) != ADDITION_ORDER
        or len(selected) != 461
        or len({row["path"] for row in selected}) != 461
    ):
        raise OpenSeedV88Error("v88 did not append exactly five ordered inputs")
    for relative, document in documents.items():
        for index, evidence in enumerate(document["evidence"]):
            retrieved = v70.parse_utc(
                evidence["retrieved_at"],
                label=f"{relative} evidence[{index}].retrieved_at",
            )
            if retrieved > target or retrieved > wall.astimezone(UTC):
                raise OpenSeedV88Error("v88 selected evidence is future-dated")
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
        "entities": 941,
        "entity_snapshots": 963,
        "evidence": 775,
        "lifecycle_observations": 546,
        "capacity_estimates": 558,
        "operating_model_observations": 73,
        "workload_observations": 135,
    }
    actual_counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in expected_counts
    }
    if actual_counts != expected_counts:
        raise OpenSeedV88Error(f"v88 database counts differ: {actual_counts}")
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v88-base-", dir="/private/tmp"
    ) as temporary:
        prior = v69._populate_database(
            base,
            _base_paths(base),
            Path(temporary) / "v87.sqlite",
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
                    raise OpenSeedV88Error(f"v88 changed a v87 database row: {table}")
            before_entities = {
                row[0] for row in prior.execute("SELECT stable_key FROM entities")
            }
            after_entities = {
                row[0] for row in connection.execute("SELECT stable_key FROM entities")
            }
            if (
                after_entities - before_entities != ADDED_ENTITY_KEYS
                or before_entities - after_entities
                or official.DENTON_CAMPUS not in before_entities
            ):
                raise OpenSeedV88Error("v88 database identity delta differs")
            before_evidence = set(v70._evidence_by_key(prior))
            after_evidence = set(v70._evidence_by_key(connection))
            if (
                after_evidence - before_evidence != ADDED_EVIDENCE_KEYS
                or before_evidence - after_evidence
            ):
                raise OpenSeedV88Error("v88 database evidence delta differs")
        finally:
            prior.close()

    denton_project = connection.execute(
        """
        SELECT projects.target_entity_id, target.stable_key
        FROM projects
        JOIN entities project ON project.id=projects.entity_id
        JOIN entities target ON target.id=projects.target_entity_id
        WHERE project.stable_key=?
        """,
        (official.DENTON_PROJECT,),
    ).fetchone()
    if denton_project is None or denton_project["stable_key"] != official.DENTON_CAMPUS:
        raise OpenSeedV88Error("v88 Denton project is not bound to the exact v87 campus")

    project_keys = tuple(sorted(ADDED_PROJECT_KEYS))
    project_placeholders = ",".join("?" for _ in project_keys)
    lifecycle = {
        tuple(row)
        for row in connection.execute(
            f"""
            SELECT entities.stable_key, status, as_of_date,
                   lifecycle_observations.method
            FROM lifecycle_observations
            JOIN entities ON entities.id=entity_id
            WHERE entities.stable_key IN ({project_placeholders})
            """,
            project_keys,
        )
    }
    capacity_keys = tuple(sorted(ADDED_ENTITY_KEYS | REUSED_ENTITY_KEYS))
    capacity_placeholders = ",".join("?" for _ in capacity_keys)
    capacities = {
        tuple(row)
        for row in connection.execute(
            f"""
            SELECT entities.stable_key, metric, stage, unit, base, as_of_date,
                   capacity_estimates.method
            FROM capacity_estimates
            JOIN entities ON entities.id=entity_id
            JOIN evidence ON evidence.id=capacity_estimates.evidence_id
            WHERE entities.stable_key IN ({capacity_placeholders})
              AND json_extract(evidence.metadata_json,
                  '$.curated_record_key') IN (?, ?, ?, ?, ?, ?)
            """,
            (*capacity_keys, *sorted(ADDED_EVIDENCE_KEYS)),
        )
    }
    models = connection.execute(
        f"""
        SELECT COUNT(*) FROM operating_model_observations
        JOIN entities ON entities.id=entity_id
        WHERE entities.stable_key IN ({project_placeholders})
        """,
        project_keys,
    ).fetchone()[0]
    workloads = connection.execute(
        f"""
        SELECT COUNT(*) FROM workload_observations
        JOIN entities ON entities.id=entity_id
        WHERE entities.stable_key IN ({project_placeholders})
        """,
        project_keys,
    ).fetchone()[0]
    snapshots = list(
        connection.execute(
            f"""
            SELECT entities.stable_key, latitude, longitude, geometry_json
            FROM entity_snapshots
            JOIN entities ON entities.id=entity_id
            WHERE entities.stable_key IN ({','.join('?' for _ in ADDED_ENTITY_KEYS)})
            """,
            tuple(sorted(ADDED_ENTITY_KEYS)),
        )
    )
    if (
        lifecycle != LIFECYCLE_CONTRACT
        or capacities != CAPACITY_CONTRACT
        or models
        or workloads
        or len(snapshots) != 8
        or any(
            row[1] is not None or row[2] is not None or row[3] not in {None, "null"}
            for row in snapshots
        )
        or any(row[2] == "operational" for row in capacities)
    ):
        raise OpenSeedV88Error("v88 imported claim contract differs")

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
        or {row["kind"] for row in evidence_rows.values()}
        != {"government_record", "company_disclosure"}
        or {row["source_family"] for row in evidence_rows.values()}
        != {
            "vineland_planning_board",
            "city_of_vineland_newsletter",
            "nebius_blog",
            "sec_edgar_core_scientific_exhibit",
            "webster_county_commission",
            "maryland_permitting_council",
        }
    ):
        raise OpenSeedV88Error("v88 imported evidence classification differs")

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
        raise OpenSeedV88Error("v88 coordinate coverage changed")


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
    output = v87._augment_release(documents)
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
            raise OpenSeedV88Error("precreated v88 release stage must be empty")
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
        raise OpenSeedV88Error("v88 release is not an ordinary directory")
    entries = {path.name: path for path in stage.iterdir()}
    if len(entries) != 14 or any(
        path.is_symlink() or not path.is_file() for path in entries.values()
    ):
        raise OpenSeedV88Error("v88 release file inventory differs")
    _raw, manifest = _read_json(stage / "manifest.json", sort_keys=True)
    if (
        manifest.get("as_of") != AS_OF
        or manifest.get("recorded_at") != recorded_at
        or manifest.get("publication_contract_version") != 4
        or set(entries) != set(manifest["files"]) | {"manifest.json"}
    ):
        raise OpenSeedV88Error("v88 manifest release facts differ")
    for filename, pin in manifest["files"].items():
        raw = entries[filename].read_bytes()
        if (len(raw), _sha256(raw)) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV88Error(f"v88 release pin differs: {filename}")

    source_inputs = json.loads((stage / "source_inputs.json").read_text())
    sources = source_inputs.get("sources")
    added_source_inputs = {
        row.get("provenance", {}).get("curated_record_key"): row
        for row in sources or []
        if row.get("provenance", {}).get("curated_record_key")
        in ADDED_EXPORTED_EVIDENCE_KEYS
    }
    if (
        not isinstance(sources, list)
        or len(sources) != 548
        or set(added_source_inputs) != ADDED_EXPORTED_EVIDENCE_KEYS
        or any(
            row.get("license") != "all-rights-reserved"
            for row in added_source_inputs.values()
        )
    ):
        raise OpenSeedV88Error("v88 source-input inventory differs")

    relevant_keys = ADDED_ENTITY_KEYS | REUSED_ENTITY_KEYS
    entities = {
        row["stable_key"]: row
        for row in _csv_rows(stage / "entities.csv")
        if row["stable_key"] in relevant_keys
    }
    if set(entities) != relevant_keys:
        raise OpenSeedV88Error("v88 relevant entity export differs")
    for key in ADDED_ENTITY_KEYS:
        row = entities[key]
        if (
            row["latitude"]
            or row["longitude"]
            or row["geometry_json"] not in {"", "null"}
            or row["country"] != "United States"
            or any(row[field] for field in ("owner", "operator", "users", "tenants", "customers"))
        ):
            raise OpenSeedV88Error(f"v88 added entity scope differs: {key}")
    denton = entities[official.DENTON_CAMPUS]
    if (
        denton["name"] != "CoreWeave Denton TX"
        or denton["status"] != "operational"
        or denton["status_as_of"] != "2026-07-20"
        or not denton["latitude"]
        or not denton["longitude"]
    ):
        raise OpenSeedV88Error("v88 altered the later v87 Denton campus snapshot")

    expected_status = {
        official.VINELAND_CAMPUS: ("", ""),
        official.VINELAND_PHASE_1: ("under_construction", "2026-03-23"),
        official.VINELAND_PHASE_2: ("under_construction", "2026-03-23"),
        official.DENTON_PROJECT: ("under_construction", "2026-04-21"),
        official.WEBSTER_CAMPUS: ("", ""),
        official.WEBSTER_PROJECT: ("under_construction", "2026-05-21"),
        official.ROWAN_CAMPUS: ("", ""),
        official.ROWAN_PROJECT: ("under_construction", "2026-04-15"),
    }
    if {
        key: (entities[key]["status"], entities[key]["status_as_of"])
        for key in ADDED_ENTITY_KEYS
    } != expected_status:
        raise OpenSeedV88Error("v88 exported lifecycle facts differ")

    project_capacities = json.loads(
        entities[official.DENTON_PROJECT]["capacity_estimates_json"]
    )
    if len(project_capacities) != 1 or (
        project_capacities[0]["metric"],
        project_capacities[0]["stage"],
        project_capacities[0]["unit"],
        project_capacities[0]["base"],
    ) != ("critical_it_mw", "design", "MW", 262.0):
        raise OpenSeedV88Error("v88 Denton project capacity differs")
    campus_capacities = json.loads(denton["capacity_estimates_json"])
    grid = [
        row
        for row in campus_capacities
        if row["metric"] == "grid_connection_mw"
        and row["stage"] == "contracted"
        and row["as_of_date"] == "2026-04-21"
    ]
    if len(grid) != 1 or grid[0]["base"] != 394.0 or any(
        row["base"] == 132.0 and row["stage"] == "operational"
        for row in campus_capacities
    ):
        raise OpenSeedV88Error("v88 Denton campus capacity boundary differs")

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
        raise OpenSeedV88Error("v88 freshness boundary differs")
    pipeline = {
        row["stable_key"]
        for row in _csv_rows(stage / "construction_pipeline.csv")
        if row["stable_key"] in ADDED_PROJECT_KEYS
    }
    if pipeline != ADDED_PROJECT_KEYS:
        raise OpenSeedV88Error("v88 construction-pipeline delta differs")
    readme = (stage / "README.md").read_text(encoding="utf-8")
    for marker in (
        "Open seed v88 is the exact accepted v87 successor",
        "Palm Coast remains review-only as a cable landing station",
        "current_status_classification` is `unknown`",
        "current_construction_claim` is `false`",
    ):
        if marker not in readme:
            raise OpenSeedV88Error(f"v88 README guardrail differs: {marker}")


def _validate_definition(
    document: Mapping[str, Any],
    base: Mapping[str, Any],
    *,
    validation_wall_clock: datetime,
) -> str:
    if set(document) != set(base) or document.get("release_id") != RELEASE_ID:
        raise OpenSeedV88Error("v88 definition identity or schema differs")
    build = document.get("build")
    if not isinstance(build, dict) or set(build) != {"as_of", "recorded_at"}:
        raise OpenSeedV88Error("v88 definition build carrier differs")
    if build["as_of"] != AS_OF:
        raise OpenSeedV88Error("v88 as_of differs")
    expected_summary = document.get("expected_summary")
    if not isinstance(expected_summary, dict) or set(expected_summary) != set(
        base["expected_summary"]
    ):
        raise OpenSeedV88Error("v88 expected-summary key contract differs")
    recorded = v70.parse_utc(build["recorded_at"], label="v88 recorded_at")
    if (
        validation_wall_clock.tzinfo is None
        or recorded > validation_wall_clock.astimezone(UTC)
    ):
        raise OpenSeedV88Error("v88 recorded_at is later than validation wall clock")
    for key in (
        "epoch_capture",
        "expected_epoch_result",
        "freshness_contract",
        "publication_contract_version",
        "schema_version",
        "scope",
    ):
        if document.get(key) != base.get(key):
            raise OpenSeedV88Error(f"v88 inherited definition field differs: {key}")
    return build["recorded_at"]


def _validate_publication_times(
    definition: Path,
    release: Path,
    *,
    recorded_at: str,
    require_live: bool,
) -> None:
    target = v70.parse_utc(recorded_at, label="v88 recorded_at")
    for path in (definition, release, *release.iterdir()):
        metadata = path.stat(follow_symlinks=False)
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV88Error(f"v88 staged inode post-dates recorded_at: {path.name}")
    if require_live:
        if datetime.now(UTC) < target:
            raise OpenSeedV88Error("v88 recorded_at is not live")
        for path in (definition, release):
            if path.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
                raise OpenSeedV88Error(
                    f"v88 final root ctime predates recorded_at: {path.name}"
                )


def _validate_guard(guard: Mapping[str, Any]) -> None:
    base_files = list(BASE_RELEASE.iterdir()) if BASE_RELEASE.is_dir() else []
    if (
        v87.DEFINITION != BASE_DEFINITION
        or v87.RELEASE != BASE_RELEASE
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
        raise OpenSeedV88Error("accepted v87 base pin differs")
    if (
        guard["official_manifest"] != OFFICIAL_MANIFEST_PIN
        or guard["official_tree"] != OFFICIAL_PHYSICAL_TREE_SHA256
        or guard["additions"] != ADDITION_PINS
    ):
        raise OpenSeedV88Error("v88 official-source pin differs")


def validate_open_seed_v88(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
    require_live: bool = True,
) -> dict[str, Any]:
    if replay_count != 2:
        raise OpenSeedV88Error("v88 requires exactly two offline replays")
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
        raise OpenSeedV88Error("v88 selected input inventory differs")
    if release_path.is_symlink() or not release_path.is_dir():
        raise OpenSeedV88Error("v88 release must be an ordinary directory")
    if require_frozen and stat.S_IMODE(release_path.stat().st_mode) != 0o555:
        raise OpenSeedV88Error("v88 release root is not frozen")
    release_files = {path.name: path for path in release_path.iterdir()}
    if any(path.is_symlink() or not path.is_file() for path in release_files.values()):
        raise OpenSeedV88Error("v88 release contains a non-file")
    if require_frozen and any(
        stat.S_IMODE(path.stat().st_mode) != 0o444
        for path in release_files.values()
    ):
        raise OpenSeedV88Error("v88 release file is not frozen")
    manifest_raw, manifest = _read_json(
        release_path / "manifest.json", mode=0o444, sort_keys=True
    )
    if _sha256(manifest_raw) != definition["expected_release"].get(
        "manifest_sha256"
    ):
        raise OpenSeedV88Error("v88 manifest hash differs")
    expected_release = {
        key: value
        for key, value in definition["expected_release"].items()
        if key != "manifest_sha256"
    }
    if {key: value for key, value in manifest.items() if key != "files"} != expected_release:
        raise OpenSeedV88Error("v88 expected release facts differ")
    if set(release_files) != set(manifest["files"]) | {"manifest.json"}:
        raise OpenSeedV88Error("v88 release file inventory differs")
    for filename, pin in manifest["files"].items():
        raw = (release_path / filename).read_bytes()
        if (len(raw), _sha256(raw)) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV88Error(f"v88 release pin differs: {filename}")
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
        raise OpenSeedV88Error("v88 expected summary differs")

    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v88-replay-{replay + 1}-", dir="/private/tmp"
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
                raise OpenSeedV88Error("v88 replay file inventory differs")
            for filename, frozen in release_files.items():
                if (replay_release / filename).read_bytes() != frozen.read_bytes():
                    raise OpenSeedV88Error(f"v88 offline replay differs: {filename}")
    if _guard_state() != guard:
        raise OpenSeedV88Error("v88 validation mutated accepted inputs")
    return manifest


def _path_identity(path: Path, *, directory: bool) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    expected = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if not expected:
        raise OpenSeedV88Error(f"v88 stage type differs: {path}")
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
        raise OpenSeedV88Error("v88 release stage root identity changed")
    if _release_identities(root) != dict(members):
        raise OpenSeedV88Error("v88 release stage member identity changed")


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
        raise OpenSeedV88Error("refusing substituted v88 definition cleanup")
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
        raise OpenSeedV88Error("active v88 publication lock exists") from error
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
                raise OpenSeedV88Error("refusing substituted v88 lock cleanup")
            PUBLICATION_LOCK.unlink()


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _require_absent(label: str) -> None:
    if DEFINITION.exists() or DEFINITION.is_symlink():
        raise OpenSeedV88Error(f"{label} v88 definition collision")
    if RELEASE.exists() or RELEASE.is_symlink():
        raise OpenSeedV88Error(f"{label} v88 release collision")


def _rollback_release(release_identity: tuple[int, int], release_stage: Path) -> None:
    if _path_identity(RELEASE, directory=True) != release_identity:
        raise OpenSeedV88Error("refusing rollback of substituted v88 release")
    if release_stage.exists() or release_stage.is_symlink():
        raise OpenSeedV88Error("v88 release rollback stage is occupied")
    v69.promote_noreplace(RELEASE, release_stage)


def _rollback_definition(
    definition_identity: tuple[int, int], definition_stage: Path
) -> None:
    if _path_identity(DEFINITION, directory=False) != definition_identity:
        raise OpenSeedV88Error("refusing rollback of substituted v88 definition")
    if definition_stage.exists() or definition_stage.is_symlink():
        raise OpenSeedV88Error("v88 definition rollback stage is occupied")
    v69.promote_noreplace(DEFINITION, definition_stage)


def build_open_seed_v88(recorded_at: str | None = None) -> dict[str, Any]:
    """Build and atomically publish the five-source v87 successor."""

    if (DEFINITION.exists() or DEFINITION.is_symlink()) and (
        RELEASE.exists() or RELEASE.is_symlink()
    ):
        manifest = validate_open_seed_v88()
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
        raise OpenSeedV88Error("partial v88 final-path collision")

    guard = _guard_state()
    _validate_guard(guard)
    target = (
        v70.parse_utc(recorded_at, label="v88 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise OpenSeedV88Error("v88 recorded_at must be future before staging")
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
                prefix="open-seed-v88-db-", dir="/private/tmp"
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
                raise OpenSeedV88Error("v88 definition stage identity changed")
            _assert_release_identities(
                release_stage, release_identity, release_members
            )
            if (
                definition_stage.read_bytes() != frozen_definition
                or v69.tree_digest(release_stage) != frozen_tree
            ):
                raise OpenSeedV88Error("v88 private stage changed while waiting")
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
                    error.add_note(f"v88 release rollback failed: {rollback_error}")
                raise
            try:
                manifest = validate_open_seed_v88(DEFINITION, RELEASE)
            except BaseException as error:
                rollback_errors = []
                try:
                    _rollback_definition(definition_identity, definition_stage)
                    published_definition = False
                except Exception as rollback_error:
                    rollback_errors.append(
                        f"v88 definition rollback failed: {rollback_error}"
                    )
                try:
                    _rollback_release(release_identity, release_stage)
                    published_release = False
                except Exception as rollback_error:
                    rollback_errors.append(
                        f"v88 release rollback failed: {rollback_error}"
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
        raise OpenSeedV88Error("v88 build mutated accepted inputs")
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
    print(json.dumps(build_open_seed_v88(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
