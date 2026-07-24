"""Build open seed v71 as the regional-source successor to accepted v70."""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
from typing import Any, Iterator, Mapping

from . import open_seed_v69 as v69
from . import open_seed_v70 as v70
from .open_seed_v61 import FRESHNESS_FIELDS, FRESHNESS_FILENAME, build_freshness_csv
from .publication_release import build_release_documents
from .service import summarize


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v70.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v70"
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v71.json"
RELEASE_ID = "2026-07-21-open-seed-v71"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v71.lock"

AS_OF = "2026-07-21"
BASE_RECORDED_AT = "2026-07-21T10:12:57Z"
BASE_DEFINITION_SHA256 = (
    "88cb1163b0a4c2dafc5c09a19a1a5dbc24bd73ab6d3069e78411041eb5f58441"
)
BASE_MANIFEST_SHA256 = (
    "56ec8c0ba5eff23ebc259326041de037bd656f6fa40bf878319dcfd03543d2ca"
)
BASE_TREE_SHA256 = "740526d433a3970071fc5d91129982804796cb2ba6de6d0c3036e06a60f94656"

REGIONAL_ARTIFACT = (
    ROOT / "source_artifacts/europe-latam-official-discovery-2026-07-21-v2"
)
REGIONAL_MANIFEST_SHA256 = (
    "8e5eb78bd273bdbe9521ba7ef52f60bb9b4eab89d8d208c9fef6569aecba313c"
)
REGIONAL_MANIFEST_TREE_SHA256 = (
    "6fc8f066f748047d0b8de6d590ced9d7ab43537d9d0956f25df8cf0694db80a7"
)
REGIONAL_PHYSICAL_TREE_SHA256 = (
    "3f0af347eae593b9f60df765910be4d6523efc0c66b2b59cd7a201b5cb49fa32"
)
REGIONAL_RECORDED_AT = "2026-07-21T10:02:31Z"

TEMPORAL_INCIDENT = (
    ROOT
    / "source_artifacts/europe-latam-official-discovery-temporal-incident-"
    "2026-07-21-v1"
)
TEMPORAL_INCIDENT_MANIFEST_SHA256 = (
    "d0f30bad34c57b0336816294306852e595ad08e1090ff1f1e25912efb8633a2a"
)
TEMPORAL_INCIDENT_MANIFEST_TREE_SHA256 = (
    "39553dc9fe7db375fd65970cdf5cbb537ea37172639b8cdf6d05bd7051045412"
)
TEMPORAL_INCIDENT_PHYSICAL_TREE_SHA256 = (
    "ba9ee8e249abfb19e4496c9e19ab264af839014d722ba7875b4e7176cebda8be"
)

REJECTED_V1_ARTIFACT = (
    ROOT / "source_artifacts/europe-latam-official-discovery-2026-07-21-v1"
)
REJECTED_V1_MANIFEST_SHA256 = (
    "af62e982f6cc4522a87e3717b0a7ae86ef19d3cc0616af393a83de4921093cdc"
)
REJECTED_V1_MANIFEST_TREE_SHA256 = (
    "c70516122a56cb8fa7e0beec7a67d851c6ec384a7d3329aa685464ff54f57496"
)
REJECTED_V1_PHYSICAL_TREE_SHA256 = (
    "4f3fa8d9aaa79d0c30b858df9d33fb0a51c0653e63638f498161a1fb28d8c53c"
)
REJECTED_V1_SOURCE_PINS = {
    "sources/curated-official-2026-07-21-arnes-maribor-construction-start.json": (
        8_971,
        "24be5cec5cdb1df39a4287a65e39f41053bc40976a06fa77fa45be3a717d6dac",
    ),
    "sources/curated-official-2026-07-21-kio-second-guatemala-construction-start.json": (
        7_862,
        "5265afc6c6c3ed8947eee54de73f31328accd1badf513500b39acf65278bad4f",
    ),
}

ADDITION_PINS = {
    "sources/curated-official-2026-07-21-arnes-maribor-construction-start-v2.json": (
        10_571,
        "672db6db061157f19c55691cf5ce84668a149d1f7bc5be6dcb8607c4e901e52b",
    ),
    "sources/curated-official-2026-07-21-kio-second-guatemala-construction-start-v2.json": (
        8_402,
        "10e17a3fb0619031a124dc3f58800b3b51c6a43671b071a4f5363d4558eb95fc",
    ),
}

ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:arnes-maribor-data-center-site",
        "curated:arnes-maribor-data-center-site:source-scoped-development",
        "curated:kio-tec-guatemala-campus",
        "curated:kio-tec-guatemala-campus:second-data-center",
    }
)
ADDED_PROJECT_KEYS = frozenset(
    {
        "curated:arnes-maribor-data-center-site:source-scoped-development",
        "curated:kio-tec-guatemala-campus:second-data-center",
    }
)
ADDED_EVIDENCE_KEYS = frozenset(
    {
        "slovenia-arnes-maribor-construction-start-2025-05-06-captured-2026-07-21",
        "slovenia-arnes-maribor-current-project-page-captured-2026-07-21",
        "guatemala-kio-second-data-center-construction-start-2025-09-25-captured-2026-07-21",
    }
)
PUBLIC_EVIDENCE_FAMILIES = {
    "kio_data_centers_newsroom",
    "slovenia_government_news",
}
LIFECYCLE_CONTRACT = {
    (
        "curated:arnes-maribor-data-center-site:source-scoped-development",
        "under_construction",
        "2025-05-06",
        "authoritative_construction_start",
    ),
    (
        "curated:kio-tec-guatemala-campus:second-data-center",
        "under_construction",
        "2025-09-25",
        "authoritative_construction_start",
    ),
}
CAPACITY_CONTRACT = {
    (
        "curated:kio-tec-guatemala-campus:second-data-center",
        "critical_it_mw",
        "design",
        "MW",
        2.0,
        "2025-09-25",
        "reported",
    ),
    (
        "curated:kio-tec-guatemala-campus:second-data-center",
        "pue",
        "design",
        "ratio",
        1.5,
        "2025-09-25",
        "reported",
    ),
}
CSV_DELTA_COUNT_CONTRACT = {
    "entities.csv": (806, 4, 0),
    "evidence.csv": (510, 2, 0),
    "capacity_estimates.csv": (530, 2, 0),
    "construction_pipeline.csv": (414, 2, 0),
    "construction_source_signals.csv": (316, 2, 0),
    "resolution_candidates.csv": (6, 0, 0),
    "lifecycle_freshness.csv": (456, 2, 0),
}

FRESHNESS_README = f"""
Open seed v71 is the exact accepted v70 successor with two schema-1.1 curated
official sources appended from
`source_artifacts/europe-latam-official-discovery-2026-07-21-v2`. It preserves
all 391 v70 inputs, including the three coordinate-only replacements, then
appends the Arnes Maribor and KIO second-Guatemala records for 393 inputs total.
The additions create exactly two campuses, two explicitly parented projects,
three evidence records, two lifecycle observations, and two typed design
capacity rows. They add no coordinates, geometry, workload, operating-model,
tenant, customer, user, current-load, generation, annual-energy, or current
construction claim.

The Arnes lifecycle value is the dated 2025-05-06 construction-start
observation. The KIO lifecycle value is the dated 2025-09-25 construction-start
observation; its 2 MW value is design critical IT capacity and its 1.5 value is
design PUE. Neither is installed, energized, measured, operational, or current.
The source calls the KIO project its second Guatemala data center but does not
name it GTM2, so no GTM2 alias is emitted. Every lifecycle value remains
last-observed: `current_status_classification` remains `unknown` and
`current_construction_claim` remains `false` for every freshness row.

The accepted corrective wrapper manifest is `{REGIONAL_MANIFEST_SHA256}` and
its physical tree is `{REGIONAL_PHYSICAL_TREE_SHA256}`. The preserved v1
wrapper and v1 source files are permanently nonaccepted under temporal incident
manifest `{TEMPORAL_INCIDENT_MANIFEST_SHA256}` and are not selected inputs.
Passage of wall-clock time does not retroactively validate them.
""".strip()


@contextmanager
def publication_lock() -> Iterator[None]:
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


def _load_canonical(path: Path) -> tuple[bytes, dict[str, Any]]:
    if not path.is_file() or path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"source must be an ordinary file: {path}")
    raw = path.read_bytes()
    document = json.loads(raw)
    if raw != (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode():
        raise ValueError(f"source JSON is not canonical: {path}")
    return raw, document


def _validate_lineage() -> dict[str, str]:
    regional = v70._validate_closed_artifact(
        REGIONAL_ARTIFACT,
        manifest_sha256=REGIONAL_MANIFEST_SHA256,
        manifest_tree_sha256=REGIONAL_MANIFEST_TREE_SHA256,
        physical_tree_sha256=REGIONAL_PHYSICAL_TREE_SHA256,
        expected_recorded_at=REGIONAL_RECORDED_AT,
    )
    incident = v70._validate_closed_artifact(
        TEMPORAL_INCIDENT,
        manifest_sha256=TEMPORAL_INCIDENT_MANIFEST_SHA256,
        manifest_tree_sha256=TEMPORAL_INCIDENT_MANIFEST_TREE_SHA256,
        physical_tree_sha256=TEMPORAL_INCIDENT_PHYSICAL_TREE_SHA256,
        expected_recorded_at=REGIONAL_RECORDED_AT,
    )
    rejected = v70._validate_closed_artifact(
        REJECTED_V1_ARTIFACT,
        manifest_sha256=REJECTED_V1_MANIFEST_SHA256,
        manifest_tree_sha256=REJECTED_V1_MANIFEST_TREE_SHA256,
        physical_tree_sha256=REJECTED_V1_PHYSICAL_TREE_SHA256,
        expected_recorded_at="2026-07-21T09:54:12Z",
    )

    if (
        regional.get("acceptance_status") != "accepted_temporal_successor"
        or regional.get("open_seed_integration") != "none"
        or regional.get("release_integration") != "none"
        or regional.get("raw_capture_redistributed") is not False
        or regional.get("curated_source_records") != 2
    ):
        raise ValueError("regional corrective-wrapper boundary differs")
    predecessor = regional.get("supersedes_non_accepted_origin", {})
    if predecessor != {
        "artifact_id": "europe-latam-official-discovery-2026-07-21-v1",
        "manifest_sha256": REJECTED_V1_MANIFEST_SHA256,
        "physical_tree_sha256": REJECTED_V1_PHYSICAL_TREE_SHA256,
        "incident_id": TEMPORAL_INCIDENT.name,
        "incident_manifest_sha256": TEMPORAL_INCIDENT_MANIFEST_SHA256,
        "incident_tree_sha256": TEMPORAL_INCIDENT_PHYSICAL_TREE_SHA256,
    }:
        raise ValueError("regional v2-to-v1 supersession mapping differs")

    incident_document = json.loads((TEMPORAL_INCIDENT / "incident.json").read_text())
    subjects = {row["path"]: row for row in incident_document.get("subjects", [])}
    expected_subjects = {
        REJECTED_V1_ARTIFACT.relative_to(ROOT).as_posix(),
        *REJECTED_V1_SOURCE_PINS,
    }
    if set(subjects) != expected_subjects or any(
        row.get("acceptance_status") != "non_accepted"
        or row.get("disposition") != "rejected_preserved"
        for row in subjects.values()
    ):
        raise ValueError("regional v1 non-acceptance incident differs")
    if (
        incident.get("acceptance_status") != "accepted_technical_incident_record"
        or incident.get("release_integration") != "none"
        or rejected.get("artifact_id")
        != "europe-latam-official-discovery-2026-07-21-v1"
    ):
        raise ValueError("regional temporal-incident boundary differs")

    for relative, expected in REJECTED_V1_SOURCE_PINS.items():
        source = ROOT / relative
        actual = (source.stat().st_size, v69.sha256(source))
        subject = subjects[relative]
        if actual != expected or actual != (subject.get("bytes"), subject.get("sha256")):
            raise ValueError(f"rejected regional v1 source pin differs: {relative}")

    snapshot = json.loads((REGIONAL_ARTIFACT / "source-snapshot.json").read_text())
    records = snapshot.get("source_records")
    if (
        snapshot.get("recorded_at") != REGIONAL_RECORDED_AT
        or snapshot.get("open_seed_integration") != "none"
        or not isinstance(records, list)
        or len(records) != 2
    ):
        raise ValueError("regional v2 source snapshot differs")
    record_pins = {
        row["path"]: (row.get("bytes"), row.get("sha256")) for row in records
    }
    if record_pins != ADDITION_PINS or any(row.get("seeded") is not False for row in records):
        raise ValueError("regional v2 source inventory differs")
    return {
        "regional_manifest_sha256": REGIONAL_MANIFEST_SHA256,
        "regional_tree_sha256": REGIONAL_PHYSICAL_TREE_SHA256,
        "incident_manifest_sha256": TEMPORAL_INCIDENT_MANIFEST_SHA256,
        "incident_tree_sha256": TEMPORAL_INCIDENT_PHYSICAL_TREE_SHA256,
        "rejected_v1_manifest_sha256": REJECTED_V1_MANIFEST_SHA256,
        "rejected_v1_tree_sha256": REJECTED_V1_PHYSICAL_TREE_SHA256,
    }


def _validate_additions(
    recorded_at: str, *, validation_wall_clock: datetime | None = None
) -> dict[str, dict[str, Any]]:
    if tuple(ADDITION_PINS) != tuple(sorted(ADDITION_PINS)) or len(ADDITION_PINS) != 2:
        raise ValueError("v71 requires exactly two canonical additions")
    _validate_lineage()
    recorded = v70.parse_utc(recorded_at, label="v71 recorded_at")
    wall_clock = validation_wall_clock or datetime.now(timezone.utc)
    if wall_clock.tzinfo is None:
        raise ValueError("validation wall clock must include a timezone")
    if recorded > wall_clock.astimezone(timezone.utc):
        raise ValueError("v71 recorded_at is later than validation wall clock")

    documents: dict[str, dict[str, Any]] = {}
    entities: dict[str, dict[str, Any]] = {}
    evidence: dict[str, dict[str, Any]] = {}
    lifecycle: set[tuple[str, str, str, str]] = set()
    capacities: set[tuple[str, str, str, str, float, str, str]] = set()
    models = 0
    workloads = 0
    for relative, expected in ADDITION_PINS.items():
        source = ROOT / relative
        raw, document = _load_canonical(source)
        if (
            (len(raw), hashlib.sha256(raw).hexdigest()) != expected
            or stat.S_IMODE(source.stat().st_mode) != 0o644
        ):
            raise ValueError(f"v71 addition byte pin or mode differs: {relative}")
        source_birth = datetime.fromtimestamp(source.stat().st_birthtime, timezone.utc)
        if source_birth > recorded:
            raise ValueError(f"v71 addition was born after recorded_at: {relative}")
        if document.get("schema_version") != "1.1":
            raise ValueError(f"v71 addition schema differs: {relative}")
        documents[relative] = document

        for row in document.get("evidence", []):
            if row["key"] in evidence:
                raise ValueError(f"v71 duplicate evidence key: {row['key']}")
            if v70.parse_utc(row["retrieved_at"], label="evidence retrieved_at") > recorded:
                raise ValueError(f"v71 evidence is newer than publication: {relative}")
            metadata = row.get("metadata", {})
            if (
                metadata.get("capture_artifact_id") != REGIONAL_ARTIFACT.name
                or metadata.get("supersedes_non_accepted_source_path")
                not in REJECTED_V1_SOURCE_PINS
                or metadata.get("server_http_date_used_as_retrieved_at") is not False
            ):
                raise ValueError(f"v71 evidence corrective lineage differs: {relative}")
            evidence[row["key"]] = row

        for entity_name in ("campus", "project"):
            row = document[entity_name]
            if row["stable_key"] in entities:
                raise ValueError(f"v71 duplicate entity key: {row['stable_key']}")
            if row.get("coordinates") is not None or row.get("geometry") is not None:
                raise ValueError(f"v71 regional source gained coordinates: {relative}")
            entities[row["stable_key"]] = row
        for row in document.get("lifecycle", []):
            stable_key = document[row["entity"]]["stable_key"]
            lifecycle.add(
                (stable_key, row["value"], row["as_of_date"], row["method"])
            )
        for row in document.get("capacities", []):
            stable_key = document[row["entity"]]["stable_key"]
            capacities.add(
                (
                    stable_key,
                    row["metric"],
                    row["stage"],
                    row["unit"],
                    float(row["base"]),
                    row["as_of_date"],
                    row["method"],
                )
            )
        models += len(document.get("operating_models", []))
        workloads += len(document.get("workloads", []))

    if set(entities) != ADDED_ENTITY_KEYS or set(evidence) != ADDED_EVIDENCE_KEYS:
        raise ValueError("v71 regional identity or evidence set differs")
    if lifecycle != LIFECYCLE_CONTRACT or capacities != CAPACITY_CONTRACT:
        raise ValueError("v71 regional lifecycle or capacity contract differs")
    if models or workloads:
        raise ValueError("v71 regional additions gained classification rows")

    arnes_roles = {
        key: row.get("roles") for key, row in entities.items() if key.startswith("curated:arnes")
    }
    if set(map(json.dumps, arnes_roles.values())) != {
        json.dumps(
            {"operator": ["Academic and Research Network of Slovenia (Arnes)"]}
        )
    }:
        raise ValueError("v71 Arnes role contract differs")
    if any(
        row.get("roles") for key, row in entities.items() if key.startswith("curated:kio")
    ):
        raise ValueError("v71 KIO source gained an unsupported role")
    entity_text = json.dumps(entities, sort_keys=True).casefold()
    if "gtm2" in entity_text:
        raise ValueError("v71 regional entities gained an unsupported GTM2 alias")
    return documents


def _base_paths(base: Mapping[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for row in base["curated_inputs"]:
        source = ROOT / row["path"]
        if (
            not source.is_file()
            or source.is_symlink()
            or not stat.S_ISREG(source.stat().st_mode)
            or v69.sha256(source) != row["sha256"]
        ):
            raise ValueError(f"accepted v70 input pin differs: {row['path']}")
        paths.append(source)
    return paths


def selected_inputs(
    base: Mapping[str, Any],
    *,
    recorded_at: str,
    validation_wall_clock: datetime | None = None,
) -> tuple[list[dict[str, str]], list[Path]]:
    if base.get("release_id") != "2026-07-21-open-seed-v70":
        raise ValueError("v71 base must be exactly accepted v70")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 391:
        raise ValueError("accepted v70 curated inventory differs")
    base_paths = [row.get("path") for row in rows]
    if len(set(base_paths)) != 391 or any(
        not isinstance(row, dict) or set(row) != {"path", "sha256"} for row in rows
    ):
        raise ValueError("accepted v70 curated rows differ")
    documents = _validate_additions(
        recorded_at, validation_wall_clock=validation_wall_clock
    )
    if set(base_paths) & (set(ADDITION_PINS) | set(REJECTED_V1_SOURCE_PINS)):
        raise ValueError("v70 already contains accepted or rejected regional sources")

    base_entity_keys: set[str] = set()
    base_evidence_keys: set[str] = set()
    paths = _base_paths(base)
    for source in paths:
        document = json.loads(source.read_text(encoding="utf-8"))
        for name in ("campus", "facility", "building", "project"):
            entity = document.get(name)
            if isinstance(entity, dict) and isinstance(entity.get("stable_key"), str):
                base_entity_keys.add(entity["stable_key"])
        base_evidence_keys.update(
            row["key"]
            for row in document.get("evidence", [])
            if isinstance(row, dict) and isinstance(row.get("key"), str)
        )
    if base_entity_keys & ADDED_ENTITY_KEYS or base_evidence_keys & ADDED_EVIDENCE_KEYS:
        raise ValueError("v71 regional source collides with accepted v70 semantics")

    selected = [dict(row) for row in rows]
    for relative in sorted(ADDITION_PINS):
        selected.append({"path": relative, "sha256": ADDITION_PINS[relative][1]})
        paths.append(ROOT / relative)
    if (
        selected[:391] != rows
        or [row["path"] for row in selected[391:]] != sorted(documents)
        or len(selected) != 393
    ):
        raise ValueError("v71 did not preserve v70 and canonically append inputs")
    return selected, paths


def _guard_state() -> dict[str, Any]:
    lineage = _validate_lineage()
    additions = {
        relative: ((ROOT / relative).stat().st_size, v69.sha256(ROOT / relative))
        for relative in ADDITION_PINS
    }
    rejected = {
        relative: ((ROOT / relative).stat().st_size, v69.sha256(ROOT / relative))
        for relative in REJECTED_V1_SOURCE_PINS
    }
    return {
        "base_definition": v69.sha256(BASE_DEFINITION),
        "base_manifest": v69.sha256(BASE_RELEASE / "manifest.json"),
        "base_tree": v69.tree_digest(BASE_RELEASE),
        "lineage": lineage,
        "additions": additions,
        "rejected_sources": rejected,
    }


def _table_state(
    connection: sqlite3.Connection, table: str
) -> set[tuple[Any, ...]]:
    return {tuple(row) for row in connection.execute(f"SELECT * FROM {table}")}


def _validate_database_contract(
    connection: sqlite3.Connection,
    base: Mapping[str, Any],
    *,
    recorded_at: str,
) -> None:
    expected_counts = {
        "entities": 810,
        "evidence": 634,
        "entity_snapshots": 830,
        "lifecycle_observations": 474,
        "capacity_estimates": 533,
        "operating_model_observations": 56,
        "workload_observations": 128,
    }
    actual_counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in expected_counts
    }
    if actual_counts != expected_counts:
        raise ValueError(f"v71 database counts differ: {actual_counts}")

    with tempfile.TemporaryDirectory(
        prefix="open-seed-v71-base-", dir="/private/tmp"
    ) as temporary:
        prior = v69._populate_database(
            base,
            _base_paths(base),
            Path(temporary) / "v70.sqlite",
            recorded_at=recorded_at,
        )
        try:
            tables = (
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
            )
            for table in tables:
                if not _table_state(prior, table) <= _table_state(connection, table):
                    raise ValueError(f"v71 changed a prior database row: {table}")
            before_keys = {row[0] for row in prior.execute("SELECT stable_key FROM entities")}
            after_keys = {row[0] for row in connection.execute("SELECT stable_key FROM entities")}
            if after_keys - before_keys != ADDED_ENTITY_KEYS or before_keys - after_keys:
                raise ValueError("v71 database identity delta differs")
            before_evidence = set(v70._evidence_by_key(prior))
            after_evidence = set(v70._evidence_by_key(connection))
            if after_evidence - before_evidence != ADDED_EVIDENCE_KEYS or before_evidence - after_evidence:
                raise ValueError("v71 database evidence delta differs")
        finally:
            prior.close()

    keys = tuple(sorted(ADDED_ENTITY_KEYS))
    placeholders = ",".join("?" for _ in keys)
    kinds = {
        tuple(row)
        for row in connection.execute(
            f"SELECT stable_key, kind FROM entities WHERE stable_key IN ({placeholders})",
            keys,
        )
    }
    if {key for key, _ in kinds} != ADDED_ENTITY_KEYS or {
        key for key, kind in kinds if kind == "project"
    } != ADDED_PROJECT_KEYS:
        raise ValueError("v71 regional entity-kind contract differs")

    lifecycle = {
        tuple(row)
        for row in connection.execute(
            f"""
            SELECT entities.stable_key, status, as_of_date, method
            FROM lifecycle_observations JOIN entities ON entities.id = entity_id
            WHERE entities.stable_key IN ({placeholders})
            """,
            keys,
        )
    }
    capacities = {
        tuple(row)
        for row in connection.execute(
            f"""
            SELECT entities.stable_key, metric, stage, unit, base, as_of_date, method
            FROM capacity_estimates JOIN entities ON entities.id = entity_id
            WHERE entities.stable_key IN ({placeholders})
            """,
            keys,
        )
    }
    if lifecycle != LIFECYCLE_CONTRACT or capacities != CAPACITY_CONTRACT:
        raise ValueError("v71 database lifecycle or capacity delta differs")
    for table in ("operating_model_observations", "workload_observations"):
        count = connection.execute(
            f"SELECT COUNT(*) FROM {table} JOIN entities ON entities.id = entity_id "
            f"WHERE entities.stable_key IN ({placeholders})",
            keys,
        ).fetchone()[0]
        if count:
            raise ValueError(f"v71 regional entities gained rows in {table}")

    snapshots = connection.execute(
        f"""
        SELECT entities.stable_key, name, latitude, longitude, geometry_json, tags_json
        FROM entity_snapshots JOIN entities ON entities.id = entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        keys,
    ).fetchall()
    if len(snapshots) != 4 or any(
        row[2] is not None or row[3] is not None or row[4] is not None for row in snapshots
    ):
        raise ValueError("v71 regional coordinate-free snapshot contract differs")
    for stable_key, name, _, _, _, tags_json in snapshots:
        tags = json.loads(tags_json)
        if stable_key.startswith("curated:arnes"):
            if set(tags) - {
                "address",
                "country",
                "role:operator",
                "source_dataset",
            } or tags.get("role:operator") != (
                "Academic and Research Network of Slovenia (Arnes)"
            ):
                raise ValueError("v71 Arnes normalized role contract differs")
        elif any(key.startswith("role:") for key in tags):
            raise ValueError("v71 KIO normalized roles differ")
        if "gtm2" in f"{stable_key} {name} {tags_json}".casefold():
            raise ValueError("v71 database gained an unsupported GTM2 alias")


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


def augment_release_documents(
    documents: Mapping[str, str], *, as_of: str
) -> dict[str, str]:
    output = dict(documents)
    if FRESHNESS_FILENAME in output:
        raise RuntimeError("freshness filename already exists")
    freshness = build_freshness_csv(output["entities.csv"], as_of=as_of)
    output[FRESHNESS_FILENAME] = freshness
    readme = output["README.md"].rstrip() + "\n\n" + FRESHNESS_README + "\n"
    output["README.md"] = readme
    manifest = json.loads(output["manifest.json"])
    manifest["files"]["README.md"] = {
        "bytes": len(readme.encode()),
        "sha256": hashlib.sha256(readme.encode()).hexdigest(),
    }
    manifest["files"][FRESHNESS_FILENAME] = {
        "bytes": len(freshness.encode()),
        "sha256": hashlib.sha256(freshness.encode()).hexdigest(),
    }
    freshness_rows = list(csv.DictReader(io.StringIO(freshness)))
    manifest["current_status_inferred"] = False
    manifest["lifecycle_freshness_records"] = len(freshness_rows)
    manifest["lifecycle_status_semantics"] = "last_observed"
    output["manifest.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    return output


def _write_release(
    connection: sqlite3.Connection,
    output: Path,
    *,
    recorded_at: str,
    precreated: bool = False,
) -> None:
    if precreated:
        if not output.is_dir() or output.is_symlink() or any(output.iterdir()):
            raise ValueError("precreated v71 release stage must be empty")
    else:
        output.mkdir(parents=True, exist_ok=False)
    documents = build_release_documents(
        connection,
        as_of=AS_OF,
        recorded_at=recorded_at,
        publication_contract_version=4,
    )
    for filename, text in augment_release_documents(documents, as_of=AS_OF).items():
        (output / filename).write_text(text, encoding="utf-8")


def _csv_counter(
    path: Path, *, recorded_at_values: set[str]
) -> Counter[tuple[tuple[str, str], ...]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return Counter(
            tuple(
                (
                    key,
                    "<recorded-at>" if value in recorded_at_values else value,
                )
                for key, value in row.items()
            )
            for row in csv.DictReader(stream)
        )


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _normalize_timestamps(value: Any, recorded_at: str) -> Any:
    if isinstance(value, dict):
        return {
            key: _normalize_timestamps(item, recorded_at) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_normalize_timestamps(item, recorded_at) for item in value]
    if value in {BASE_RECORDED_AT, recorded_at}:
        return "<recorded-at>"
    return value


def _validate_release_delta(stage: Path, *, recorded_at: str) -> None:
    timestamps = {BASE_RECORDED_AT, recorded_at}
    for filename, expected in CSV_DELTA_COUNT_CONTRACT.items():
        before = _csv_counter(
            BASE_RELEASE / filename, recorded_at_values=timestamps
        )
        after = _csv_counter(stage / filename, recorded_at_values=timestamps)
        common = before & after
        actual = (
            sum(common.values()),
            sum((after - common).values()),
            sum((before - common).values()),
        )
        if actual != expected:
            raise ValueError(f"v71 public CSV delta differs: {filename}: {actual}")

    before_entities = {
        row["stable_key"]: row for row in _csv_rows(BASE_RELEASE / "entities.csv")
    }
    after_entities = {
        row["stable_key"]: row for row in _csv_rows(stage / "entities.csv")
    }
    if set(after_entities) - set(before_entities) != ADDED_ENTITY_KEYS:
        raise ValueError("v71 public identity delta differs")
    if set(before_entities) - set(after_entities) or any(
        after_entities[key] != row for key, row in before_entities.items()
    ):
        raise ValueError("v71 changed an accepted v70 public entity row")
    for stable_key in ADDED_ENTITY_KEYS:
        row = after_entities[stable_key]
        if row["latitude"] or row["longitude"] or row["geometry_json"] != "null":
            raise ValueError("v71 regional public entity gained coordinates")
        if "gtm2" in json.dumps(row, sort_keys=True).casefold():
            raise ValueError("v71 public entity gained an unsupported GTM2 alias")

    before_evidence = {
        row["evidence_id"]: row for row in _csv_rows(BASE_RELEASE / "evidence.csv")
    }
    after_evidence = {
        row["evidence_id"]: row for row in _csv_rows(stage / "evidence.csv")
    }
    if set(before_evidence) - set(after_evidence) or any(
        after_evidence[key] != row for key, row in before_evidence.items()
    ):
        raise ValueError("v71 changed accepted v70 public evidence")
    added_evidence = [
        row for key, row in after_evidence.items() if key not in before_evidence
    ]
    if (
        len(added_evidence) != 2
        or {row["source_family"] for row in added_evidence}
        != PUBLIC_EVIDENCE_FAMILIES
        or {row["kind"] for row in added_evidence}
        != {"government_record", "company_disclosure"}
    ):
        raise ValueError("v71 public evidence projection differs")

    before_resolution = json.loads(
        (BASE_RELEASE / "resolution_candidates.json").read_text()
    )
    after_resolution = json.loads((stage / "resolution_candidates.json").read_text())
    if _normalize_timestamps(before_resolution, recorded_at) != _normalize_timestamps(
        after_resolution, recorded_at
    ):
        raise ValueError("v71 changed the resolution advisory")

    before_atlas = json.loads((BASE_RELEASE / "atlas.geojson").read_text())
    after_atlas = json.loads((stage / "atlas.geojson").read_text())
    before_features = {
        row["properties"]["stable_key"]: row for row in before_atlas["features"]
    }
    after_features = {
        row["properties"]["stable_key"]: row for row in after_atlas["features"]
    }
    if set(after_features) - set(before_features) != ADDED_ENTITY_KEYS or any(
        after_features[key] != row for key, row in before_features.items()
    ):
        raise ValueError("v71 GeoJSON base preservation differs")
    if any(after_features[key]["geometry"] is not None for key in ADDED_ENTITY_KEYS):
        raise ValueError("v71 regional GeoJSON feature gained geometry")


def _validate_release_facts(stage: Path, *, recorded_at: str) -> None:
    summary = json.loads((stage / "summary.json").read_text())
    expected_summary = {
        "campuses_total": 427,
        "campuses_with_coordinates": 131,
        "capacity_estimates_current": 532,
        "construction_pipeline_records": 416,
        "construction_source_signals": 318,
        "entities_total": 810,
        "entities_with_coordinates": 189,
        "evidence_total": 634,
        "lifecycle_observations_current": 458,
        "projects_total": 383,
        "recorded_at": recorded_at,
    }
    if {key: summary.get(key) for key in expected_summary} != expected_summary:
        raise ValueError("v71 summary facts differ")
    if summary.get("entities_by_status", {}).get("under_construction") != 309:
        raise ValueError("v71 last-observed status summary differs")
    if (
        summary.get("capacity_estimates_by_metric", {}).get("critical_it_mw") != 266
        or summary.get("capacity_estimates_by_metric", {}).get("pue") != 5
        or summary.get("capacity_estimates_by_stage", {}).get("design") != 17
    ):
        raise ValueError("v71 capacity summary differs")

    manifest = json.loads((stage / "manifest.json").read_text())
    expected_manifest = {
        "entities": 810,
        "evidence_records": 512,
        "capacity_estimates": 532,
        "construction_pipeline_records": 416,
        "construction_source_signals": 318,
        "resolution_candidates": 6,
        "lifecycle_freshness_records": 458,
        "lifecycle_status_semantics": "last_observed",
        "current_status_inferred": False,
        "recorded_at": recorded_at,
    }
    if {key: manifest.get(key) for key in expected_manifest} != expected_manifest:
        raise ValueError("v71 manifest facts differ")
    base_manifest = json.loads((BASE_RELEASE / "manifest.json").read_text())
    if (
        set(manifest["source_families"]) - set(base_manifest["source_families"])
        != PUBLIC_EVIDENCE_FAMILIES
        or set(base_manifest["source_families"]) - set(manifest["source_families"])
        or len(manifest["source_families"]) != 288
    ):
        raise ValueError("v71 public source-family delta differs")

    freshness = _csv_rows(stage / FRESHNESS_FILENAME)
    classes = Counter(row["freshness_class"] for row in freshness)
    by_key = {row["stable_key"]: row for row in freshness}
    if (
        len(freshness) != 458
        or tuple(freshness[0]) != FRESHNESS_FIELDS
        or classes
        != {
            "recent_0_90_days": 236,
            "aging_91_365_days": 192,
            "stale_over_365_days": 30,
        }
        or any(
            row["status_semantics"] != "last_observed"
            or row["current_status_classification"] != "unknown"
            or row["current_construction_claim"] != "false"
            for row in freshness
        )
    ):
        raise ValueError("v71 freshness/current-status boundary differs")
    expected_freshness = {
        "curated:arnes-maribor-data-center-site:source-scoped-development": (
            "under_construction",
            "2025-05-06",
            "stale_over_365_days",
        ),
        "curated:kio-tec-guatemala-campus:second-data-center": (
            "under_construction",
            "2025-09-25",
            "aging_91_365_days",
        ),
    }
    for stable_key, expected in expected_freshness.items():
        row = by_key[stable_key]
        actual = (
            row["last_observed_status"],
            row["last_observed_status_as_of"],
            row["freshness_class"],
        )
        if actual != expected:
            raise ValueError(f"v71 regional freshness differs: {stable_key}")

    readme = (stage / "README.md").read_text()
    for marker in (
        REGIONAL_MANIFEST_SHA256,
        REGIONAL_PHYSICAL_TREE_SHA256,
        TEMPORAL_INCIDENT_MANIFEST_SHA256,
        "no GTM2 alias is emitted",
        "current_status_classification` remains `unknown",
        "current_construction_claim` remains `false",
        "does not retroactively validate",
    ):
        if marker not in readme:
            raise ValueError("v71 README lineage or guardrail differs")
    if len(list(stage.iterdir())) != 14:
        raise ValueError("v71 release file inventory count differs")


def _validate_definition(
    document: Mapping[str, Any],
    base: Mapping[str, Any],
    *,
    validation_wall_clock: datetime,
) -> str:
    if set(document) != set(base):
        raise ValueError("v71 definition schema differs from v70")
    if document.get("release_id") != RELEASE_ID:
        raise ValueError("v71 release_id differs")
    build = document.get("build")
    if not isinstance(build, dict) or set(build) != {"as_of", "recorded_at"}:
        raise ValueError("v71 build carrier differs")
    if build.get("as_of") != AS_OF:
        raise ValueError("v71 as_of differs")
    recorded = v70.parse_utc(build.get("recorded_at"), label="v71 recorded_at")
    if validation_wall_clock.tzinfo is None:
        raise ValueError("validation wall clock must include a timezone")
    if recorded > validation_wall_clock.astimezone(timezone.utc):
        raise ValueError("v71 recorded_at is later than validation wall clock")
    for key in (
        "epoch_capture",
        "expected_epoch_result",
        "freshness_contract",
        "publication_contract_version",
        "schema_version",
        "scope",
    ):
        if document.get(key) != base.get(key):
            raise ValueError(f"v71 inherited definition field differs: {key}")
    return build["recorded_at"]


def _ordinary_file(path: Path, label: str) -> bytes:
    if not path.is_file() or path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"{label} must be an ordinary file")
    return path.read_bytes()


def _validate_publication_times(
    definition_path: Path, release_path: Path, *, recorded_at: str
) -> None:
    recorded = v70.parse_utc(recorded_at, label="v71 recorded_at").timestamp()
    for item in (definition_path, release_path, *release_path.iterdir()):
        status = item.stat()
        if status.st_birthtime > recorded + 0.000_001:
            raise ValueError(f"v71 artifact was born after recorded_at: {item.name}")
        if status.st_mtime > recorded + 0.000_001:
            raise ValueError(f"v71 artifact mtime is after recorded_at: {item.name}")


def validate_open_seed_v71(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
) -> dict[str, Any]:
    if replay_count != 2:
        raise ValueError("v71 requires exactly two offline replays")
    wall_clock = validation_wall_clock or datetime.now(timezone.utc)
    guard = _guard_state()
    if (
        guard["base_definition"] != BASE_DEFINITION_SHA256
        or guard["base_manifest"] != BASE_MANIFEST_SHA256
        or guard["base_tree"] != BASE_TREE_SHA256
    ):
        raise ValueError("accepted v70 base pin differs")
    base = json.loads(_ordinary_file(BASE_DEFINITION, "v70 definition"))
    definition_raw = _ordinary_file(definition_path, "v71 definition")
    document = json.loads(definition_raw)
    if definition_raw != v69.canonical_json(document):
        raise ValueError("v71 definition JSON is not canonical")
    recorded_at = _validate_definition(
        document, base, validation_wall_clock=wall_clock
    )
    selected, paths = selected_inputs(
        base, recorded_at=recorded_at, validation_wall_clock=wall_clock
    )
    if document.get("curated_inputs") != selected:
        raise ValueError("v71 selected input inventory differs")

    if not release_path.is_dir() or release_path.is_symlink():
        raise ValueError("v71 release must be an ordinary directory")
    if require_frozen and stat.S_IMODE(release_path.stat().st_mode) != 0o555:
        raise ValueError("v71 release directory mode must be 0555")
    release_files = {item.name: item for item in release_path.iterdir()}
    if any(item.is_symlink() or not item.is_file() for item in release_files.values()):
        raise ValueError("v71 release contains a symlink or non-file")
    if require_frozen and any(
        stat.S_IMODE(item.stat().st_mode) != 0o444 for item in release_files.values()
    ):
        raise ValueError("v71 release file mode must be 0444")

    manifest_raw = _ordinary_file(release_path / "manifest.json", "v71 manifest")
    manifest = json.loads(manifest_raw)
    if hashlib.sha256(manifest_raw).hexdigest() != document["expected_release"].get(
        "manifest_sha256"
    ):
        raise ValueError("v71 manifest hash differs")
    expected_release = {
        key: value
        for key, value in document["expected_release"].items()
        if key != "manifest_sha256"
    }
    if {key: value for key, value in manifest.items() if key != "files"} != expected_release:
        raise ValueError("v71 expected release facts differ")
    if set(release_files) != set(manifest["files"]) | {"manifest.json"}:
        raise ValueError("v71 release file inventory differs")
    for filename, pin in manifest["files"].items():
        payload = _ordinary_file(release_path / filename, filename)
        if (len(payload), hashlib.sha256(payload).hexdigest()) != (
            pin["bytes"],
            pin["sha256"],
        ):
            raise ValueError(f"v71 release file pin differs: {filename}")
    _validate_publication_times(
        definition_path, release_path, recorded_at=recorded_at
    )
    _validate_release_delta(release_path, recorded_at=recorded_at)
    _validate_release_facts(release_path, recorded_at=recorded_at)
    summary = json.loads((release_path / "summary.json").read_text())
    if {key: summary[key] for key in document["expected_summary"]} != document[
        "expected_summary"
    ]:
        raise ValueError("v71 expected summary differs")

    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v71-replay-{replay + 1}-", dir="/private/tmp"
        ) as temporary:
            temporary_root = Path(temporary)
            connection = _build_database(
                base,
                paths,
                temporary_root / "atlas.sqlite",
                recorded_at=recorded_at,
            )
            try:
                replay_release = temporary_root / "release"
                _write_release(connection, replay_release, recorded_at=recorded_at)
            finally:
                connection.close()
            _validate_release_delta(replay_release, recorded_at=recorded_at)
            _validate_release_facts(replay_release, recorded_at=recorded_at)
            if {item.name for item in replay_release.iterdir()} != set(release_files):
                raise ValueError("v71 replay file inventory differs")
            for filename, frozen in release_files.items():
                if (replay_release / filename).read_bytes() != frozen.read_bytes():
                    raise ValueError(f"v71 offline replay differs: {filename}")
    if _guard_state() != guard:
        raise ValueError("v71 validation mutated accepted inputs")
    return manifest


def build_open_seed_v71() -> dict[str, Any]:
    guard = _guard_state()
    with publication_lock():
        if DEFINITION.exists() or DEFINITION.is_symlink():
            raise SystemExit(f"definition already exists; refusing overwrite: {DEFINITION}")
        if RELEASE.exists() or RELEASE.is_symlink():
            raise SystemExit(f"release already exists; refusing overwrite: {RELEASE}")
        if (
            guard["base_definition"] != BASE_DEFINITION_SHA256
            or guard["base_manifest"] != BASE_MANIFEST_SHA256
            or guard["base_tree"] != BASE_TREE_SHA256
        ):
            raise SystemExit("accepted v70 base pin differs")

        release_stage = Path(
            tempfile.mkdtemp(prefix=f".{RELEASE.name}.", dir=RELEASE.parent)
        )
        definition_stage = DEFINITION.parent / f".{DEFINITION.name}.{os.getpid()}.tmp"
        try:
            descriptor = os.open(
                definition_stage, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
        except FileExistsError as error:
            v69.discard_release_stage(release_stage)
            raise SystemExit(f"definition stage collision: {definition_stage}") from error
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

        published_release = False
        try:
            recorded_at = v70._planned_publication_time(lead_seconds=30)
            planned_wall = v70.parse_utc(recorded_at, label="v71 recorded_at")
            base = json.loads(BASE_DEFINITION.read_text())
            input_rows, paths = selected_inputs(
                base,
                recorded_at=recorded_at,
                validation_wall_clock=planned_wall,
            )
            staging_root = ROOT / ".staging"
            staging_root.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix="open-seed-v71-db-", dir=staging_root
            ) as temporary:
                connection = _build_database(
                    base,
                    paths,
                    Path(temporary) / "atlas.sqlite",
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
            _validate_release_delta(release_stage, recorded_at=recorded_at)
            _validate_release_facts(release_stage, recorded_at=recorded_at)
            manifest_raw = (release_stage / "manifest.json").read_bytes()
            manifest = json.loads(manifest_raw)
            expected_release = {
                key: value for key, value in manifest.items() if key != "files"
            }
            expected_release["manifest_sha256"] = hashlib.sha256(
                manifest_raw
            ).hexdigest()
            definition = dict(base)
            definition["build"] = {"as_of": AS_OF, "recorded_at": recorded_at}
            definition["curated_inputs"] = input_rows
            definition["expected_release"] = expected_release
            definition["expected_summary"] = {
                key: summary[key] for key in base["expected_summary"]
            }
            definition["release_id"] = RELEASE_ID
            with definition_stage.open("r+b") as stream:
                stream.write(v69.canonical_json(definition))
                stream.truncate()
                stream.flush()
                os.fsync(stream.fileno())
            definition_stage.chmod(0o644)
            for output in release_stage.iterdir():
                output.chmod(0o444)
            release_stage.chmod(0o555)
            target = v70.parse_utc(
                recorded_at, label="v71 recorded_at"
            ).timestamp()
            if v70._max_stage_time((definition_stage, release_stage)) > target + 0.000_001:
                raise SystemExit("v71 staging exceeded its planned publication timestamp")
            v70._wait_until(recorded_at)
            validate_open_seed_v71(definition_stage, release_stage)
            v69.promote_noreplace(release_stage, RELEASE)
            published_release = True
            v69.promote_noreplace(definition_stage, DEFINITION)
            validate_open_seed_v71(DEFINITION, RELEASE)
        finally:
            if not published_release:
                v69.discard_release_stage(release_stage)
            try:
                definition_stage.unlink()
            except FileNotFoundError:
                pass
    if _guard_state() != guard:
        raise SystemExit("v71 build mutated accepted inputs")
    manifest = json.loads((RELEASE / "manifest.json").read_text())
    return {
        "definition": str(DEFINITION),
        "definition_sha256": v69.sha256(DEFINITION),
        "manifest_sha256": v69.sha256(RELEASE / "manifest.json"),
        "recorded_at": manifest["recorded_at"],
        "release": str(RELEASE),
        "release_tree_sha256": v69.tree_digest(RELEASE),
        **{
            key: value
            for key, value in manifest.items()
            if key not in {"files", "source_families"}
        },
        "source_families": len(manifest["source_families"]),
    }


def main() -> int:
    print(json.dumps(build_open_seed_v71(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
