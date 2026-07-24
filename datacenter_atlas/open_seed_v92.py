"""Build open seed v92 as the strict five-source append successor to v91."""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import csv
from datetime import UTC, datetime, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping

from . import aws_official_clinton_adaptive_reuse_current_build_gap_20260722 as aws
from . import coreweave_official_lancaster_current_build_gap_20260722 as coreweave
from . import open_seed_v69 as v69
from . import open_seed_v70 as v70
from . import open_seed_v85 as v85
from . import open_seed_v91 as v91
from . import sabey_official_current_build_gap_20260722 as sabey
from . import vantage_official_reno_nv1_current_build_gap_20260722 as vantage
from .publication_release import build_release_documents
from .service import _current_rows


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v91.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v91"
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v92.json"
RELEASE_ID = "2026-07-21-open-seed-v92"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v92.lock"
AS_OF = "2026-07-22"

BASE_RECORDED_AT = "2026-07-22T01:33:29Z"
BASE_DEFINITION_PIN = (
    108_188,
    "e1a1c657c88468233dc72e66012ec1f56afd69a599f129c5fcc64f20bdf3038a",
)
BASE_MANIFEST_PIN = (
    15_954,
    "8be929e9f24b0bb1d11a318cfd67d8c4e538f2979db9468ecd359cb36afb45f9",
)
BASE_TREE_SHA256 = "9c89ab93baf5a13965db764a376affe231186df6a5cbc2758fd9ad95a85a5a5e"
BASE_ENTITIES_PIN = (
    1_018_118,
    "b1f07223ff1a61e64670aaf23bc9b3a7ee5834c2131e031a59401b404acebe75",
)

OFFICIAL_SPECS = {
    "coreweave": {
        "module": coreweave,
        "recorded_at": "2026-07-22T01:33:50Z",
        "manifest_pin": (
            1_826,
            "728bbcee77a6892af5960f9a0d035098907ef63a6fef8caee3bd8f7dc443f78c",
        ),
        "logical_tree": "066c1769a662c81e832074fded25f5315cb85eb25d35f2168b9eabda4614a5fd",
        "physical_tree": "6c2067eea11d851b714d4c913e5c5d069fe89110015a55da77cd25f9725e130b",
        "source_count": 1,
    },
    "vantage": {
        "module": vantage,
        "recorded_at": "2026-07-22T01:38:40Z",
        "manifest_pin": (
            1_822,
            "7ea31f22e24fee8f919416a860d7be7f7aa36bae172dd378acc2f201edcb60e5",
        ),
        "logical_tree": "76103b52b0d246a9eb683f6969c97a40b6d07d5cdb447c54f7808b874ce46273",
        "physical_tree": "53f0f4246775f8840aa29e85435147e78f1a41e245c36b796572a11b2918d277",
        "source_count": 1,
    },
    "sabey": {
        "module": sabey,
        "recorded_at": "2026-07-22T01:40:44Z",
        "manifest_pin": (
            1_744,
            "eaebecd7921931ca24c9703a004b27a1f5505dfc753870333d3359407331aa29",
        ),
        "logical_tree": "fac16ebf21441401c2346bcc53da6f7981a29244032ef454c3e87fc79fcd828d",
        "physical_tree": "002cfb5bd87de5306f3c0317a16ea04b04af5a1cac1f7c1974f9fb250cc974b6",
        "source_count": 2,
    },
    "aws": {
        "module": aws,
        "recorded_at": "2026-07-22T01:45:03Z",
        "manifest_pin": (
            1_832,
            "dc04162f560a0b89eb5ca220262aedf97c20b68a8d93d7ed7bf1def49401ab0a",
        ),
        "logical_tree": "a5be1637b1eca0d433d0a43edc1b4c21b914dc4b28cc7d34311d405735a19b76",
        "physical_tree": "8dcc9fe4b9f5221b2ac240d21b859c650c8598365e2b90c2af5113ecb7d9ecc4",
        "source_count": 1,
    },
}

ADDITION_ORDER = (
    "sources/curated-official-2026-07-22-coreweave-chirisa-lancaster-greenfield-adaptive-reuse-current-build.json",
    "sources/curated-official-2026-07-22-vantage-nv1-reno-nv12-current-build.json",
    "sources/curated-official-2026-07-22-sabey-ashburn-building-a-current-build.json",
    "sources/curated-official-2026-07-22-sabey-austin-round-rock-building-b-current-build.json",
    "sources/curated-official-2026-07-22-aws-clinton-former-delphi-adaptive-reuse-current-build.json",
)
ADDITION_PINS = {
    ADDITION_ORDER[0]: (
        14_824,
        "b95aef23cf7eb244a9c137d9dfc814ed6aea59a36c04aa1016f95f0751f6ac72",
    ),
    ADDITION_ORDER[1]: (
        13_698,
        "4f1f9df373338d896c785e7b7485134bce6c35cf934f2c33985e7b250f6d0bc2",
    ),
    ADDITION_ORDER[2]: (
        6_948,
        "85410db525cb1c7cd1c667847c2c5b01e024f86b72c7a435db0af8967dacba5d",
    ),
    ADDITION_ORDER[3]: (
        12_030,
        "42ca5504fad0d0f8d1cc38ffacd7133fa8b378377a5dde704eb2e04831d8704f",
    ),
    ADDITION_ORDER[4]: (
        13_957,
        "bf3254807325b7cbdfa1e5ef6a191698463e1fe794a5236c2d76ede7af9cd756",
    ),
}

SOURCE_MODULES = {
    ADDITION_ORDER[0]: coreweave,
    ADDITION_ORDER[1]: vantage,
    ADDITION_ORDER[2]: sabey,
    ADDITION_ORDER[3]: sabey,
    ADDITION_ORDER[4]: aws,
}

ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:coreweave-chirisa-lancaster-greenfield-road-campus",
        "curated:coreweave-chirisa-lancaster-greenfield-road-campus:phase-1-adaptive-reuse",
        "curated:vantage-nv1-reno-storey-county-campus",
        "curated:vantage-nv1-reno-storey-county-campus:nv12-current-build",
        "curated:sabey-sdc-ashburn-campus",
        "curated:sabey-sdc-ashburn-campus:building-a-current-build",
        "curated:sabey-sdc-austin-round-rock-campus",
        "curated:sabey-sdc-austin-round-rock-campus:building-b-current-build",
        "curated:aws-clinton-former-delphi-adaptive-reuse-campus",
        "curated:aws-clinton-former-delphi-adaptive-reuse-campus:existing-building-retrofit",
    }
)
ADDED_PROJECT_KEYS = frozenset(
    key for key in ADDED_ENTITY_KEYS if ":" in key.removeprefix("curated:")
)
ADDED_EVIDENCE_KEYS = frozenset(
    {
        "lancaster-city-two-data-center-sites-observed-2026-07-22",
        "lancaster-city-greenfield-phase1-harrisburg-boundary-observed-2026-07-22",
        "chirisa-lancaster-east-lpe01-in-construction-observed-2026-07-22",
        "coreweave-pennsylvania-flagship-groundbreaking-2025-12-31",
        "coreweave-lancaster-project-context-2025-07-15",
        "mccarthy-vantage-nv12-topped-out-2026-01-22",
        "mccarthy-vantage-nv1-construction-narrative-2025-10-27",
        "vantage-reno-nv1-campus-page-observed-2026-07-22",
        "vantage-reno-nv1-datasheet-observed-2026-07-22",
        "sabey-ashburn-building-a-construction-start-2025-06-25",
        "sabey-ashburn-location-observed-2026-07-22",
        "sabey-austin-building-b-construction-start-2025-07-29",
        "sabey-austin-building-b-progress-2025-09-29",
        "sabey-austin-building-b-progress-2026-02-17",
        "sabey-austin-building-b-shell-update-2026-06-16",
        "city-clinton-industrial-building-rehabilitation-begun-2026-03-03",
        "city-clinton-aws-former-delphi-adaptive-reuse-2026-06-09",
        "amazon-clinton-former-delphi-liveblog-item-2026-06-09",
        "amazon-mississippi-investment-context-2026-04-09",
    }
)
ADDED_EXPORTED_EVIDENCE_KEYS = frozenset(
    {
        "chirisa-lancaster-east-lpe01-in-construction-observed-2026-07-22",
        "mccarthy-vantage-nv12-topped-out-2026-01-22",
        "sabey-ashburn-building-a-construction-start-2025-06-25",
        "sabey-austin-building-b-shell-update-2026-06-16",
        "city-clinton-industrial-building-rehabilitation-begun-2026-03-03",
        "city-clinton-aws-former-delphi-adaptive-reuse-2026-06-09",
    }
)
ADDED_SIGNAL_EVIDENCE_KEYS = frozenset(
    {
        "chirisa-lancaster-east-lpe01-in-construction-observed-2026-07-22",
        "mccarthy-vantage-nv12-topped-out-2026-01-22",
        "sabey-ashburn-building-a-construction-start-2025-06-25",
        "sabey-austin-building-b-shell-update-2026-06-16",
        "city-clinton-industrial-building-rehabilitation-begun-2026-03-03",
    }
)
LIFECYCLE_CONTRACT = frozenset(
    {
        (
            "curated:coreweave-chirisa-lancaster-greenfield-road-campus:phase-1-adaptive-reuse",
            "under_construction",
            "2026-07-22",
            "authoritative_physical_status_update",
        ),
        (
            "curated:vantage-nv1-reno-storey-county-campus:nv12-current-build",
            "shell",
            "2026-01-22",
            "authoritative_physical_status_update",
        ),
        (
            "curated:sabey-sdc-ashburn-campus:building-a-current-build",
            "under_construction",
            "2025-06-25",
            "authoritative_construction_start",
        ),
        (
            "curated:sabey-sdc-austin-round-rock-campus:building-b-current-build",
            "under_construction",
            "2025-07-29",
            "authoritative_construction_start",
        ),
        (
            "curated:sabey-sdc-austin-round-rock-campus:building-b-current-build",
            "shell",
            "2026-06-16",
            "authoritative_physical_status_update",
        ),
        (
            "curated:aws-clinton-former-delphi-adaptive-reuse-campus:existing-building-retrofit",
            "under_construction",
            "2026-03-03",
            "authoritative_physical_status_update",
        ),
    }
)
CAPACITY_CONTRACT = frozenset(
    {
        (
            "curated:vantage-nv1-reno-storey-county-campus:nv12-current-build",
            "critical_it_mw",
            "planned",
            "MW",
            64.0,
            "2026-01-22",
            "reported",
        )
    }
)

FRESHNESS_README = """
Open seed v92 is the exact append-only accepted-v91 successor with only five
frozen curated records appended at input indices 480 through 484: CoreWeave
Lancaster, Vantage NV12, Sabey Ashburn Building A, Sabey Austin Building B,
and AWS Clinton's former-Delphi retrofit. Four frozen official-source artifact
manifests and their logical and physical trees are pinned by the v92 builder.

The append creates ten v91-new entities: five campuses and five projects.
Public contract-v4 rows preserve the accepted v91 projection byte-for-byte
where their stable IDs or keys are unchanged; the ten new rows carry no
coordinate or geometry. This prevents the one-day as-of advance from silently
surfacing unrelated future-effective coordinates already present in a v91
input. Derived v91 freshness rows likewise remain frozen, while five new
project freshness rows are computed at the v92 as-of date.

The curated database delta is 19 evidence records and six lifecycle
observations. Public projection is intentionally smaller: `evidence.csv`
adds only six evidence records referenced by exported current claims;
`lifecycle_freshness.csv` adds five latest-per-project rows because Austin's
construction-start and shell observations are retained as history but project
to one latest shell row; and `construction_source_signals.csv` adds five
current status-evidence groups. This projection is not evidence loss.

Vantage NV12 contributes the only new capacity row: exactly 64 MW planned
critical IT. No energy, PUE, WUE, operating model, workload, facility type,
standardized role, coordinate, geometry, satellite, aerial, map-click, or
computer-vision assertion is added. Every appended status is a dated
last-observed fact; `current_status_classification` is `unknown` and
`current_construction_claim` is `false`.
""".strip()


class OpenSeedV92Error(RuntimeError):
    """Raised when a v92 lineage, claim, or publication guard fails closed."""


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
        raise OpenSeedV92Error(f"expected ordinary JSON file: {path}")
    if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
        raise OpenSeedV92Error(f"file mode differs: {path}")
    raw = path.read_bytes()
    document = json.loads(raw)
    if raw != _canonical(document, sort_keys=sort_keys):
        raise OpenSeedV92Error(f"JSON is not canonical: {path}")
    return raw, document


def _validate_official_artifact() -> dict[str, dict[str, Any]]:
    records_by_path: dict[str, dict[str, Any]] = {}
    for label, spec in OFFICIAL_SPECS.items():
        module = spec["module"]
        artifact = ROOT / "source_artifacts" / module.ARTIFACT_ID
        try:
            manifest = module.validate_artifact(artifact)
            module._validate_source_collisions()
        except RuntimeError as error:
            raise OpenSeedV92Error(
                f"{label} official artifact invalid: {error}"
            ) from error
        manifest_raw = (artifact / "manifest.json").read_bytes()
        if (
            (len(manifest_raw), _sha256(manifest_raw)) != spec["manifest_pin"]
            or manifest.get("recorded_at") != spec["recorded_at"]
            or manifest.get("tree_sha256") != spec["logical_tree"]
            or v69.tree_digest(artifact) != spec["physical_tree"]
            or manifest.get("curated_source_records") != spec["source_count"]
            or manifest.get("seed_eligible_source_records") != spec["source_count"]
            or manifest.get("open_seed_successor_created") is not False
            or manifest.get("release_integration") != "none"
        ):
            raise OpenSeedV92Error(f"{label} official artifact pin differs")
        snapshot = json.loads(
            (artifact / "source-snapshot.json").read_text(encoding="utf-8")
        )
        for record in snapshot.get("source_records", []):
            path = record.get("path")
            if not isinstance(path, str) or path in records_by_path:
                raise OpenSeedV92Error("official artifact source inventory overlaps")
            records_by_path[path] = record

    if tuple(records_by_path) != ADDITION_ORDER:
        raise OpenSeedV92Error("official artifact source order differs")
    documents: dict[str, dict[str, Any]] = {}
    for relative in ADDITION_ORDER:
        path = ROOT / relative
        raw, document = _read_json(path, mode=0o444)
        record = records_by_path[relative]
        pin = ADDITION_PINS[relative]
        module = SOURCE_MODULES[relative]
        expected = module.expected_source_documents()[path.name]
        if (
            (len(raw), _sha256(raw)) != pin
            or (record.get("bytes"), record.get("sha256")) != pin
            or raw != module._canonical(expected)
        ):
            raise OpenSeedV92Error(f"v92 source pin differs: {relative}")
        documents[relative] = document

    stable_keys = {
        document[entity]["stable_key"]
        for document in documents.values()
        for entity in ("campus", "project")
    }
    lifecycle = {
        (
            document[row["entity"]]["stable_key"],
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
            float(row["base"]),
            row["as_of_date"],
            row["method"],
        )
        for document in documents.values()
        for row in document["capacities"]
    }
    evidence_keys = {
        row["key"]
        for document in documents.values()
        for row in document["evidence"]
    }
    if (
        stable_keys != ADDED_ENTITY_KEYS
        or lifecycle != LIFECYCLE_CONTRACT
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
        raise OpenSeedV92Error("official current-build normalized claim contract differs")
    if any(
        row["metric"] in {"annual_energy_mwh", "pue", "wue"}
        for document in documents.values()
        for row in document["capacities"]
    ):
        raise OpenSeedV92Error("v92 source adds energy or efficiency capacity")
    return documents


def _base_paths(base: Mapping[str, Any]) -> list[Path]:
    paths = []
    for row in base["curated_inputs"]:
        path = ROOT / row["path"]
        if path.is_symlink() or not path.is_file() or v69.sha256(path) != row["sha256"]:
            raise OpenSeedV92Error(f"accepted v91 input pin differs: {row['path']}")
        paths.append(path)
    return paths


def selected_inputs(
    base: Mapping[str, Any],
    *,
    recorded_at: str,
    validation_wall_clock: datetime | None = None,
) -> tuple[list[dict[str, str]], list[Path]]:
    if base.get("release_id") != v91.RELEASE_ID:
        raise OpenSeedV92Error("v92 base must be exactly accepted v91")
    rows = base.get("curated_inputs")
    if (
        not isinstance(rows, list)
        or len(rows) != 480
        or any(
            not isinstance(row, dict) or set(row) != {"path", "sha256"}
            for row in rows
        )
    ):
        raise OpenSeedV92Error("accepted v91 curated inventory differs")
    documents = _validate_official_artifact()
    target = v70.parse_utc(recorded_at, label="v92 recorded_at")
    wall = validation_wall_clock or datetime.now(UTC)
    if (
        wall.tzinfo is None
        or target > wall.astimezone(UTC)
        or any(
            v70.parse_utc(spec["recorded_at"], label=f"{label} recorded_at")
            > target
            for label, spec in OFFICIAL_SPECS.items()
        )
    ):
        raise OpenSeedV92Error("v92 publication time precedes an input")

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
        raise OpenSeedV92Error("v92 evidence append collides with accepted v91")
    base_stable = {
        row["stable_key"] for row in _csv_rows(BASE_RELEASE / "entities.csv")
    }
    if base_stable & ADDED_ENTITY_KEYS:
        raise OpenSeedV92Error("v92 stable-key append collides with accepted v91")

    selected = [dict(row) for row in rows]
    for relative in ADDITION_ORDER:
        selected.append({"path": relative, "sha256": ADDITION_PINS[relative][1]})
        paths.append(ROOT / relative)
    if (
        selected[:480] != rows
        or [row["path"] for row in selected[480:]] != list(ADDITION_ORDER)
        or tuple(documents) != ADDITION_ORDER
        or len(selected) != 485
        or len({row["path"] for row in selected}) != 485
    ):
        raise OpenSeedV92Error("v92 did not append exactly five ordered inputs")
    for relative, document in documents.items():
        for index, evidence in enumerate(document["evidence"]):
            retrieved = v70.parse_utc(
                evidence["retrieved_at"],
                label=f"{relative} evidence[{index}].retrieved_at",
            )
            if retrieved > target or retrieved > wall.astimezone(UTC):
                raise OpenSeedV92Error("v92 selected evidence is future-dated")
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
        "official_manifests": {
            label: (
                (
                    ROOT
                    / "source_artifacts"
                    / spec["module"].ARTIFACT_ID
                    / "manifest.json"
                ).stat().st_size,
                v69.sha256(
                    ROOT
                    / "source_artifacts"
                    / spec["module"].ARTIFACT_ID
                    / "manifest.json"
                ),
            )
            for label, spec in OFFICIAL_SPECS.items()
        },
        "official_trees": {
            label: v69.tree_digest(
                ROOT / "source_artifacts" / spec["module"].ARTIFACT_ID
            )
            for label, spec in OFFICIAL_SPECS.items()
        },
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
        "entities": 988,
        "entity_snapshots": 1_011,
        "evidence": 817,
        "lifecycle_observations": 571,
        "capacity_estimates": 559,
        "operating_model_observations": 73,
        "workload_observations": 135,
    }
    actual_counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in expected_counts
    }
    if actual_counts != expected_counts:
        raise OpenSeedV92Error(f"v92 database counts differ: {actual_counts}")
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v92-base-", dir="/private/tmp"
    ) as temporary:
        prior = v69._populate_database(
            base,
            _base_paths(base),
            Path(temporary) / "v91.sqlite",
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
                    raise OpenSeedV92Error(f"v92 changed a v91 database row: {table}")
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
                raise OpenSeedV92Error("v92 database identity delta differs")
            before_evidence = set(v70._evidence_by_key(prior))
            after_evidence = set(v70._evidence_by_key(connection))
            if (
                after_evidence - before_evidence != ADDED_EVIDENCE_KEYS
                or before_evidence - after_evidence
            ):
                raise OpenSeedV92Error("v92 database evidence delta differs")
        finally:
            prior.close()

    project_targets = {
        row["project_key"]: row["campus_key"]
        for row in connection.execute(
            """
            SELECT project.stable_key AS project_key,
                   target.stable_key AS campus_key
            FROM projects
            JOIN entities project ON project.id=projects.entity_id
            JOIN entities target ON target.id=projects.target_entity_id
            """
        )
        if row["project_key"] in ADDED_PROJECT_KEYS
    }
    expected_targets = {
        document["project"]["stable_key"]: document["campus"]["stable_key"]
        for document in _validate_official_artifact().values()
    }
    if project_targets != expected_targets:
        raise OpenSeedV92Error("v92 project/campus boundaries differ")

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
    capacity_keys = tuple(sorted(ADDED_ENTITY_KEYS))
    capacity_placeholders = ",".join("?" for _ in capacity_keys)
    evidence_keys = tuple(sorted(ADDED_EVIDENCE_KEYS))
    evidence_placeholders = ",".join("?" for _ in evidence_keys)
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
                  '$.curated_record_key') IN ({evidence_placeholders})
            """,
            (*capacity_keys, *evidence_keys),
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
        or len(snapshots) != 10
        or any(
            row[1] is not None or row[2] is not None or row[3] not in {None, "null"}
            for row in snapshots
        )
        or any(row[1] != "critical_it_mw" for row in capacities)
        or any(row[2] != "planned" for row in capacities)
    ):
        raise OpenSeedV92Error("v92 imported claim contract differs")

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
        or not {row["kind"] for row in evidence_rows.values()}
        <= {"company_disclosure", "government_record"}
    ):
        raise OpenSeedV92Error("v92 imported evidence classification differs")

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
        raise OpenSeedV92Error("v92 internal as-of coordinate coverage differs")


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


def _csv_text(template: str, rows: list[dict[str, str]]) -> str:
    reader = csv.DictReader(io.StringIO(template))
    fields = reader.fieldnames
    if fields is None:
        raise OpenSeedV92Error("CSV template lacks a header")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _append_only_csv(
    output: dict[str, str],
    filename: str,
    *,
    key: str,
    expected_base: int,
    expected_added: int,
) -> None:
    base_rows = _csv_rows(BASE_RELEASE / filename)
    current_rows = list(csv.DictReader(io.StringIO(output[filename])))
    if len(base_rows) != expected_base:
        raise OpenSeedV92Error(f"v91 {filename} baseline count differs")
    base_keys = {row[key] for row in base_rows}
    if len(base_keys) != len(base_rows) or not base_keys <= {
        row[key] for row in current_rows
    }:
        raise OpenSeedV92Error(f"v92 {filename} baseline identity differs")
    added = [row for row in current_rows if row[key] not in base_keys]
    if len(added) != expected_added or len({row[key] for row in added}) != len(added):
        raise OpenSeedV92Error(f"v92 {filename} append count differs")
    output[filename] = _csv_text(output[filename], [*base_rows, *added])


def _append_only_projection(output: dict[str, str]) -> None:
    _append_only_csv(
        output,
        "entities.csv",
        key="stable_key",
        expected_base=978,
        expected_added=10,
    )
    _append_only_csv(
        output,
        "evidence.csv",
        key="evidence_id",
        expected_base=639,
        expected_added=6,
    )
    _append_only_csv(
        output,
        "construction_pipeline.csv",
        key="stable_key",
        expected_base=496,
        expected_added=5,
    )
    _append_only_csv(
        output,
        "construction_source_signals.csv",
        key="source_observation_evidence_id",
        expected_base=395,
        expected_added=5,
    )
    _append_only_csv(
        output,
        "lifecycle_freshness.csv",
        key="stable_key",
        expected_base=545,
        expected_added=5,
    )

    entity_rows = list(csv.DictReader(io.StringIO(output["entities.csv"])))
    new_entity_ids = {
        row["entity_id"] for row in entity_rows if row["stable_key"] in ADDED_ENTITY_KEYS
    }
    base_capacity = _csv_rows(BASE_RELEASE / "capacity_estimates.csv")
    raw_capacity = list(csv.DictReader(io.StringIO(output["capacity_estimates.csv"])))
    added_capacity = [
        row for row in raw_capacity if row["entity_id"] in new_entity_ids
    ]
    if len(base_capacity) != 557 or len(added_capacity) != 1:
        raise OpenSeedV92Error("v92 capacity append count differs")
    output["capacity_estimates.csv"] = _csv_text(
        output["capacity_estimates.csv"], [*base_capacity, *added_capacity]
    )

    base_geojson = json.loads((BASE_RELEASE / "atlas.geojson").read_text())
    current_geojson = json.loads(output["atlas.geojson"])
    new_features = [
        feature
        for feature in current_geojson["features"]
        if feature["properties"]["stable_key"] in ADDED_ENTITY_KEYS
    ]
    if len(base_geojson["features"]) != 978 or len(new_features) != 10 or any(
        feature.get("geometry") is not None
        or feature["properties"].get("latitude") is not None
        or feature["properties"].get("longitude") is not None
        for feature in new_features
    ):
        raise OpenSeedV92Error("v92 GeoJSON append boundary differs")
    current_geojson["features"] = [*base_geojson["features"], *new_features]
    output["atlas.geojson"] = (
        json.dumps(current_geojson, indent=2, sort_keys=True, ensure_ascii=False)
        + "\n"
    )

    base_sources = json.loads(
        (BASE_RELEASE / "source_inputs.json").read_text(encoding="utf-8")
    )["sources"]
    current_sources = json.loads(output["source_inputs.json"])["sources"]
    base_canonical = {
        json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        for row in base_sources
    }
    added_sources = [
        row
        for row in current_sources
        if json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        not in base_canonical
    ]
    if len(base_sources) != 566 or len(added_sources) != 6:
        raise OpenSeedV92Error("v92 source-input projection differs")
    output["source_inputs.json"] = (
        json.dumps(
            {"sources": [*base_sources, *added_sources]},
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )

    summary = json.loads(output["summary.json"])
    summary["entities_with_coordinates"] = 213
    summary["campuses_with_coordinates"] = 141
    summary["append_projection"] = {
        "base_release_id": v91.RELEASE_ID,
        "base_rows_frozen": True,
        "internal_database_delta": {
            "entities": 10,
            "evidence": 19,
            "lifecycle_observations": 6,
            "capacity_estimates": 1,
        },
        "public_release_delta": {
            "entities": 10,
            "evidence": 6,
            "lifecycle_freshness": 5,
            "capacity_estimates": 1,
            "construction_pipeline": 5,
            "construction_source_signals": 5,
        },
        "projection_explanation": "Public claim evidence includes only evidence referenced by exported current fields; Austin start and shell remain two internal lifecycle observations but one latest freshness row; construction signals group current pipeline rows by status evidence.",
        "unrelated_future_effective_base_coordinates_published": False,
    }
    output["summary.json"] = _canonical(summary, sort_keys=True).decode()


def _augment_release(documents: Mapping[str, str]) -> dict[str, str]:
    previous_as_of = v85.AS_OF
    try:
        v85.AS_OF = AS_OF
        output = v91._augment_release(documents)
    finally:
        v85.AS_OF = previous_as_of
    _append_only_projection(output)
    output["README.md"] = (
        output["README.md"].rstrip() + "\n\n" + FRESHNESS_README + "\n"
    )
    manifest = json.loads(output["manifest.json"])
    manifest.update(
        {
            "as_of": AS_OF,
            "entities": 988,
            "entities_by_kind": {"campus": 513, "project": 475},
            "capacity_estimates": 558,
            "construction_pipeline_records": 501,
            "construction_source_signals": 400,
            "evidence_records": 645,
            "lifecycle_freshness_records": 550,
            "append_only_base_release": v91.RELEASE_ID,
            "base_rows_frozen": True,
            "internal_database_delta": {
                "entities": 10,
                "evidence": 19,
                "lifecycle_observations": 6,
                "capacity_estimates": 1,
            },
            "public_release_delta": {
                "entities": 10,
                "evidence": 6,
                "lifecycle_freshness": 5,
                "capacity_estimates": 1,
                "construction_pipeline": 5,
                "construction_source_signals": 5,
            },
        }
    )
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
            raise OpenSeedV92Error("precreated v92 release stage must be empty")
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


def _entity_csv_record(path: Path, stable_key: str) -> bytes:
    marker = f",{stable_key},".encode()
    matches = [line for line in path.read_bytes().splitlines(keepends=True) if marker in line]
    if len(matches) != 1:
        raise OpenSeedV92Error(f"entity CSV record lookup differs: {stable_key}")
    return matches[0]


PUBLIC_CSV_DELTA = {
    "entities.csv": (978, 10),
    "evidence.csv": (639, 6),
    "capacity_estimates.csv": (557, 1),
    "construction_pipeline.csv": (496, 5),
    "construction_source_signals.csv": (395, 5),
    "lifecycle_freshness.csv": (545, 5),
}


def _validate_public_delta(stage: Path) -> None:
    for filename, (base_count, added_count) in PUBLIC_CSV_DELTA.items():
        base_lines = Counter(
            (BASE_RELEASE / filename).read_bytes().splitlines(keepends=True)[1:]
        )
        stage_lines = Counter(
            (stage / filename).read_bytes().splitlines(keepends=True)[1:]
        )
        if (
            sum(base_lines.values()) != base_count
            or not base_lines <= stage_lines
            or sum((stage_lines - base_lines).values()) != added_count
            or sum((base_lines - stage_lines).values()) != 0
        ):
            raise OpenSeedV92Error(f"v92 append-only CSV delta differs: {filename}")

    montgomery = "epoch-ai:data-center:dec73855-d62c-5f35-bd1a-3b1f00b20bec"
    if _entity_csv_record(stage / "entities.csv", montgomery) != _entity_csv_record(
        BASE_RELEASE / "entities.csv", montgomery
    ):
        raise OpenSeedV92Error("v92 altered the v91 Montgomery campus CSV record")


def _validate_release_facts(stage: Path, *, recorded_at: str) -> None:
    if stage.is_symlink() or not stage.is_dir():
        raise OpenSeedV92Error("v92 release is not an ordinary directory")
    entries = {path.name: path for path in stage.iterdir()}
    if len(entries) != 14 or any(
        path.is_symlink() or not path.is_file() for path in entries.values()
    ):
        raise OpenSeedV92Error("v92 release file inventory differs")
    _raw, manifest = _read_json(stage / "manifest.json", sort_keys=True)
    if (
        manifest.get("as_of") != AS_OF
        or manifest.get("recorded_at") != recorded_at
        or manifest.get("publication_contract_version") != 4
        or manifest.get("entities") != 988
        or manifest.get("entities_by_kind")
        != {"campus": 513, "project": 475}
        or manifest.get("evidence_records") != 645
        or manifest.get("lifecycle_freshness_records") != 550
        or manifest.get("capacity_estimates") != 558
        or manifest.get("construction_pipeline_records") != 501
        or manifest.get("construction_source_signals") != 400
        or manifest.get("append_only_base_release") != v91.RELEASE_ID
        or manifest.get("base_rows_frozen") is not True
        or set(entries) != set(manifest["files"]) | {"manifest.json"}
    ):
        raise OpenSeedV92Error("v92 manifest release facts differ")
    for filename, pin in manifest["files"].items():
        raw = entries[filename].read_bytes()
        if (len(raw), _sha256(raw)) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV92Error(f"v92 release pin differs: {filename}")
    _validate_public_delta(stage)

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
        or len(sources) != 572
        or set(added_source_inputs) != ADDED_EXPORTED_EVIDENCE_KEYS
        or any(
            row.get("license") != "all-rights-reserved"
            for row in added_source_inputs.values()
        )
    ):
        raise OpenSeedV92Error("v92 source-input inventory differs")

    relevant_keys = ADDED_ENTITY_KEYS
    entities = {
        row["stable_key"]: row
        for row in _csv_rows(stage / "entities.csv")
        if row["stable_key"] in relevant_keys
    }
    if set(entities) != relevant_keys:
        raise OpenSeedV92Error("v92 relevant entity export differs")
    expected_country = dict.fromkeys(ADDED_ENTITY_KEYS, "United States")
    for key in ADDED_ENTITY_KEYS:
        row = entities[key]
        if (
            row["latitude"]
            or row["longitude"]
            or row["geometry_json"] not in {"", "null"}
            or row["country"] != expected_country[key]
            or any(row[field] for field in ("owner", "operator", "users", "tenants", "customers"))
            or row["operating_model"]
            or json.loads(row["workloads_json"]) != []
        ):
            raise OpenSeedV92Error(f"v92 added entity scope differs: {key}")

    vantage_key = (
        "curated:vantage-nv1-reno-storey-county-campus:nv12-current-build"
    )
    for key, row in entities.items():
        capacities = json.loads(row["capacity_estimates_json"])
        if key == vantage_key:
            if (
                len(capacities) != 1
                or capacities[0]["metric"] != "critical_it_mw"
                or capacities[0]["stage"] != "planned"
                or capacities[0]["unit"] != "MW"
                or capacities[0]["base"] != 64.0
            ):
                raise OpenSeedV92Error("v92 Vantage public capacity differs")
        elif capacities:
            raise OpenSeedV92Error(f"v92 unexpected added capacity: {key}")

    expected_status = {
        key: ("", "") for key in ADDED_ENTITY_KEYS - ADDED_PROJECT_KEYS
    } | {
        "curated:coreweave-chirisa-lancaster-greenfield-road-campus:phase-1-adaptive-reuse": (
            "under_construction",
            "2026-07-22",
        ),
        "curated:vantage-nv1-reno-storey-county-campus:nv12-current-build": (
            "shell",
            "2026-01-22",
        ),
        "curated:sabey-sdc-ashburn-campus:building-a-current-build": (
            "under_construction",
            "2025-06-25",
        ),
        "curated:sabey-sdc-austin-round-rock-campus:building-b-current-build": (
            "shell",
            "2026-06-16",
        ),
        "curated:aws-clinton-former-delphi-adaptive-reuse-campus:existing-building-retrofit": (
            "under_construction",
            "2026-03-03",
        ),
    }
    if {
        key: (entities[key]["status"], entities[key]["status_as_of"])
        for key in ADDED_ENTITY_KEYS
    } != expected_status:
        raise OpenSeedV92Error("v92 exported lifecycle facts differ")

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
        raise OpenSeedV92Error("v92 freshness boundary differs")
    pipeline = {
        row["stable_key"]
        for row in _csv_rows(stage / "construction_pipeline.csv")
        if row["stable_key"] in ADDED_PROJECT_KEYS
    }
    if pipeline != ADDED_PROJECT_KEYS:
        raise OpenSeedV92Error("v92 construction-pipeline delta differs")
    added_signals = [
        row
        for row in _csv_rows(stage / "construction_source_signals.csv")
        if row["representative_stable_key"] in ADDED_PROJECT_KEYS
    ]
    if (
        len(added_signals) != 5
        or {row["representative_stable_key"] for row in added_signals}
        != ADDED_PROJECT_KEYS
        or any(
            row["representative_latitude"] or row["representative_longitude"]
            for row in added_signals
        )
    ):
        raise OpenSeedV92Error("v92 construction-source-signal delta differs")

    summary = json.loads((stage / "summary.json").read_text(encoding="utf-8"))
    projection = summary.get("append_projection")
    if (
        summary.get("entities_total") != 988
        or summary.get("campuses_total") != 513
        or summary.get("projects_total") != 475
        or summary.get("evidence_total") != 817
        or summary.get("lifecycle_observations_current") != 550
        or summary.get("capacity_estimates_current") != 558
        or summary.get("construction_pipeline_records") != 501
        or summary.get("construction_source_signals") != 400
        or summary.get("entities_with_coordinates") != 213
        or summary.get("campuses_with_coordinates") != 141
        or not isinstance(projection, dict)
        or projection.get("internal_database_delta")
        != {
            "entities": 10,
            "evidence": 19,
            "lifecycle_observations": 6,
            "capacity_estimates": 1,
        }
        or projection.get("public_release_delta")
        != {
            "entities": 10,
            "evidence": 6,
            "lifecycle_freshness": 5,
            "capacity_estimates": 1,
            "construction_pipeline": 5,
            "construction_source_signals": 5,
        }
    ):
        raise OpenSeedV92Error("v92 summary projection contract differs")

    new_features = [
        feature
        for feature in json.loads((stage / "atlas.geojson").read_text())["features"]
        if feature["properties"]["stable_key"] in ADDED_ENTITY_KEYS
    ]
    if len(new_features) != 10 or any(
        feature.get("geometry") is not None for feature in new_features
    ):
        raise OpenSeedV92Error("v92 public geometry append differs")
    readme = (stage / "README.md").read_text(encoding="utf-8")
    for marker in (
        "Open seed v92 is the exact append-only accepted-v91 successor",
        "The curated database delta is 19 evidence records and six lifecycle",
        "Public projection is intentionally smaller",
        "Vantage NV12 contributes the only new capacity row",
        "current_status_classification` is `unknown`",
        "current_construction_claim` is `false`",
    ):
        if marker not in readme:
            raise OpenSeedV92Error(f"v92 README guardrail differs: {marker}")


def _validate_definition(
    document: Mapping[str, Any],
    base: Mapping[str, Any],
    *,
    validation_wall_clock: datetime,
) -> str:
    if set(document) != set(base) or document.get("release_id") != RELEASE_ID:
        raise OpenSeedV92Error("v92 definition identity or schema differs")
    build = document.get("build")
    if not isinstance(build, dict) or set(build) != {"as_of", "recorded_at"}:
        raise OpenSeedV92Error("v92 definition build carrier differs")
    if build["as_of"] != AS_OF:
        raise OpenSeedV92Error("v92 as_of differs")
    expected_summary = document.get("expected_summary")
    if not isinstance(expected_summary, dict) or set(expected_summary) != set(
        base["expected_summary"]
    ):
        raise OpenSeedV92Error("v92 expected-summary key contract differs")
    recorded = v70.parse_utc(build["recorded_at"], label="v92 recorded_at")
    if (
        validation_wall_clock.tzinfo is None
        or recorded > validation_wall_clock.astimezone(UTC)
    ):
        raise OpenSeedV92Error("v92 recorded_at is later than validation wall clock")
    for key in (
        "epoch_capture",
        "expected_epoch_result",
        "freshness_contract",
        "publication_contract_version",
        "schema_version",
        "scope",
    ):
        if document.get(key) != base.get(key):
            raise OpenSeedV92Error(f"v92 inherited definition field differs: {key}")
    return build["recorded_at"]


def _validate_publication_times(
    definition: Path,
    release: Path,
    *,
    recorded_at: str,
    require_live: bool,
) -> None:
    target = v70.parse_utc(recorded_at, label="v92 recorded_at")
    for path in (definition, release, *release.iterdir()):
        metadata = path.stat(follow_symlinks=False)
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV92Error(f"v92 staged inode post-dates recorded_at: {path.name}")
    if require_live:
        if datetime.now(UTC) < target:
            raise OpenSeedV92Error("v92 recorded_at is not live")
        for path in (definition, release, *release.iterdir()):
            if path.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
                raise OpenSeedV92Error(
                    f"v92 final inode ctime predates recorded_at: {path.name}"
                )


def _validate_guard(guard: Mapping[str, Any]) -> None:
    base_files = list(BASE_RELEASE.iterdir()) if BASE_RELEASE.is_dir() else []
    if (
        v91.DEFINITION != BASE_DEFINITION
        or v91.RELEASE != BASE_RELEASE
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
        raise OpenSeedV92Error("accepted v91 base pin differs")
    expected_manifests = {
        label: spec["manifest_pin"] for label, spec in OFFICIAL_SPECS.items()
    }
    expected_trees = {
        label: spec["physical_tree"] for label, spec in OFFICIAL_SPECS.items()
    }
    if guard["official_manifests"] != expected_manifests or guard[
        "official_trees"
    ] != expected_trees or guard["additions"] != ADDITION_PINS:
        raise OpenSeedV92Error("v92 official-source pin differs")


def validate_open_seed_v92(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
    require_live: bool = True,
) -> dict[str, Any]:
    if replay_count != 2:
        raise OpenSeedV92Error("v92 requires exactly two offline replays")
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
        raise OpenSeedV92Error("v92 selected input inventory differs")
    if release_path.is_symlink() or not release_path.is_dir():
        raise OpenSeedV92Error("v92 release must be an ordinary directory")
    if require_frozen and stat.S_IMODE(release_path.stat().st_mode) != 0o555:
        raise OpenSeedV92Error("v92 release root is not frozen")
    release_files = {path.name: path for path in release_path.iterdir()}
    if any(path.is_symlink() or not path.is_file() for path in release_files.values()):
        raise OpenSeedV92Error("v92 release contains a non-file")
    if require_frozen and any(
        stat.S_IMODE(path.stat().st_mode) != 0o444
        for path in release_files.values()
    ):
        raise OpenSeedV92Error("v92 release file is not frozen")
    manifest_raw, manifest = _read_json(
        release_path / "manifest.json", mode=0o444, sort_keys=True
    )
    if _sha256(manifest_raw) != definition["expected_release"].get(
        "manifest_sha256"
    ):
        raise OpenSeedV92Error("v92 manifest hash differs")
    expected_release = {
        key: value
        for key, value in definition["expected_release"].items()
        if key != "manifest_sha256"
    }
    if {key: value for key, value in manifest.items() if key != "files"} != expected_release:
        raise OpenSeedV92Error("v92 expected release facts differ")
    if set(release_files) != set(manifest["files"]) | {"manifest.json"}:
        raise OpenSeedV92Error("v92 release file inventory differs")
    for filename, pin in manifest["files"].items():
        raw = (release_path / filename).read_bytes()
        if (len(raw), _sha256(raw)) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV92Error(f"v92 release pin differs: {filename}")
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
        raise OpenSeedV92Error("v92 expected summary differs")

    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v92-replay-{replay + 1}-", dir="/private/tmp"
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
                raise OpenSeedV92Error("v92 replay file inventory differs")
            for filename, frozen in release_files.items():
                if (replay_release / filename).read_bytes() != frozen.read_bytes():
                    raise OpenSeedV92Error(f"v92 offline replay differs: {filename}")
    if _guard_state() != guard:
        raise OpenSeedV92Error("v92 validation mutated accepted inputs")
    return manifest


def _path_identity(path: Path, *, directory: bool) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    expected = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if not expected:
        raise OpenSeedV92Error(f"v92 stage type differs: {path}")
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
        raise OpenSeedV92Error("v92 release stage root identity changed")
    if _release_identities(root) != dict(members):
        raise OpenSeedV92Error("v92 release stage member identity changed")


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
        raise OpenSeedV92Error("refusing substituted v92 definition cleanup")
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
        raise OpenSeedV92Error("active v92 publication lock exists") from error
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
                raise OpenSeedV92Error("refusing substituted v92 lock cleanup")
            PUBLICATION_LOCK.unlink()


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _refresh_publication_ctimes(definition: Path, release: Path) -> None:
    definition.chmod(0o400)
    definition.chmod(0o444)
    _fsync(definition)
    release.chmod(0o500)
    for path in release.iterdir():
        path.chmod(0o400)
        path.chmod(0o444)
        _fsync(path)
    release.chmod(0o555)
    _fsync(release)


def _require_absent(label: str) -> None:
    if DEFINITION.exists() or DEFINITION.is_symlink():
        raise OpenSeedV92Error(f"{label} v92 definition collision")
    if RELEASE.exists() or RELEASE.is_symlink():
        raise OpenSeedV92Error(f"{label} v92 release collision")


def _rollback_release(release_identity: tuple[int, int], release_stage: Path) -> None:
    if _path_identity(RELEASE, directory=True) != release_identity:
        raise OpenSeedV92Error("refusing rollback of substituted v92 release")
    if release_stage.exists() or release_stage.is_symlink():
        raise OpenSeedV92Error("v92 release rollback stage is occupied")
    v69.promote_noreplace(RELEASE, release_stage)


def _rollback_definition(
    definition_identity: tuple[int, int], definition_stage: Path
) -> None:
    if _path_identity(DEFINITION, directory=False) != definition_identity:
        raise OpenSeedV92Error("refusing rollback of substituted v92 definition")
    if definition_stage.exists() or definition_stage.is_symlink():
        raise OpenSeedV92Error("v92 definition rollback stage is occupied")
    v69.promote_noreplace(DEFINITION, definition_stage)


def build_open_seed_v92(recorded_at: str | None = None) -> dict[str, Any]:
    """Build and atomically publish the five-source v91 successor."""

    if (DEFINITION.exists() or DEFINITION.is_symlink()) and (
        RELEASE.exists() or RELEASE.is_symlink()
    ):
        manifest = validate_open_seed_v92()
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
        raise OpenSeedV92Error("partial v92 final-path collision")

    guard = _guard_state()
    _validate_guard(guard)
    target = (
        v70.parse_utc(recorded_at, label="v92 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=90)
    )
    if datetime.now(UTC) >= target:
        raise OpenSeedV92Error("v92 recorded_at must be future before staging")
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
                prefix="open-seed-v92-db-", dir="/private/tmp"
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
                finally:
                    connection.close()
            _validate_release_facts(release_stage, recorded_at=recorded_at)
            summary = json.loads(
                (release_stage / "summary.json").read_text(encoding="utf-8")
            )
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
                raise OpenSeedV92Error("v92 definition stage identity changed")
            _assert_release_identities(
                release_stage, release_identity, release_members
            )
            if (
                definition_stage.read_bytes() != frozen_definition
                or v69.tree_digest(release_stage) != frozen_tree
            ):
                raise OpenSeedV92Error("v92 private stage changed while waiting")
            _refresh_publication_ctimes(definition_stage, release_stage)
            _assert_release_identities(
                release_stage, release_identity, release_members
            )
            if (
                definition_stage.read_bytes() != frozen_definition
                or v69.tree_digest(release_stage) != frozen_tree
            ):
                raise OpenSeedV92Error("v92 private bytes changed at publication")
            _validate_publication_times(
                definition_stage,
                release_stage,
                recorded_at=recorded_at,
                require_live=True,
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
                    error.add_note(f"v92 release rollback failed: {rollback_error}")
                raise
            try:
                manifest = validate_open_seed_v92(DEFINITION, RELEASE)
            except BaseException as error:
                rollback_errors = []
                try:
                    _rollback_definition(definition_identity, definition_stage)
                    published_definition = False
                except Exception as rollback_error:
                    rollback_errors.append(
                        f"v92 definition rollback failed: {rollback_error}"
                    )
                try:
                    _rollback_release(release_identity, release_stage)
                    published_release = False
                except Exception as rollback_error:
                    rollback_errors.append(
                        f"v92 release rollback failed: {rollback_error}"
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
        raise OpenSeedV92Error("v92 build mutated accepted inputs")
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
    print(json.dumps(build_open_seed_v92(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
