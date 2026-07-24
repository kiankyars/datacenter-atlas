"""Build open seed v86 as the strict five-source append successor to v85."""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import copy
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

from . import global_official_builds_operator_social_next_tranche_20260721 as operator
from . import open_seed_v69 as v69
from . import open_seed_v70 as v70
from . import open_seed_v85 as v85
from .open_seed_v61 import FRESHNESS_FIELDS, FRESHNESS_FILENAME
from .publication_release import build_release_documents
from .service import _current_rows, summarize


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v85.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v85"
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v86.json"
RELEASE_ID = "2026-07-21-open-seed-v86"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v86.lock"
AS_OF = "2026-07-21"

BASE_RECORDED_AT = "2026-07-21T20:00:55Z"
BASE_DEFINITION_PIN = (
    101_105,
    "e61641a6364e86f011f31b8a81e2fbc53979cdf80ada219fc1538ade99b22b1b",
)
BASE_MANIFEST_PIN = (
    15_331,
    "fc89a45fcc9a7ce00c1d523b124cb3253d9de52f7ff11faad32f8ba42e6934c8",
)
BASE_TREE_SHA256 = "010075fac16363fa61845f7b10fef4db09442ffefc46a5b90002fec11e922900"
BASE_ENTITIES_PIN = (
    970_598,
    "1ba3646193915e568eaea72fb14b16ba101d2a238cc2f67d9470bd7a2b225d7e",
)

OFFICIAL_ARTIFACT = (
    ROOT
    / "source_artifacts/"
    "global-official-builds-operator-social-next-tranche-2026-07-21-v1"
)
OFFICIAL_RECORDED_AT = "2026-07-21T19:50:53Z"
OFFICIAL_MANIFEST_PIN = (
    1_755,
    "a6d20ce2f8a0eb16c86242f80d15f92addd328f4b04c9d2b5f7bb6d80abf19ff",
)
OFFICIAL_MANIFEST_TREE_SHA256 = (
    "bcd9197aeedf2a6665b4b88c957a9c807066f914177fcc8792655c492ea659e2"
)
OFFICIAL_PHYSICAL_TREE_SHA256 = (
    "62ae7fa0fec98922068cadbb90af5dd26f3822ef85fe64f1ab222bfa569dbb2f"
)

ADDITION_ORDER = (
    "sources/curated-official-2026-07-21-stack-johor-first-120mw-current-build.json",
    "sources/curated-official-2026-07-21-echelon-dub20-current-build.json",
    "sources/curated-official-2026-07-21-echelon-dub40-current-build.json",
    "sources/curated-official-2026-07-21-odata-sp04-phase2-current-build.json",
    "sources/curated-official-2026-07-21-multidc-shoham-current-build.json",
)
ADDITION_PINS = {
    ADDITION_ORDER[0]: (
        6_005,
        "171f44843154f28dc72ad3bcd1f066ec3becd5c36cb99c818716c82ab61883cc",
    ),
    ADDITION_ORDER[1]: (
        5_601,
        "dd307d2df9ec64ddae59877e330dbaea97b43d604f8674500507395fdeaf79b7",
    ),
    ADDITION_ORDER[2]: (
        3_603,
        "c3a7907e8708e2bb14c04b81fe7a23b79e02cca047328ab656cff2e4eac66810",
    ),
    ADDITION_ORDER[3]: (
        6_424,
        "e738abaae7e2263c2a3d73d0ac2517c714ce870821790f8729ba972e8844533d",
    ),
    ADDITION_ORDER[4]: (
        6_372,
        "c9a0b9cbb83efaf7ada906054c67b3997b6d02b8c72c8203b9849e34918a8d16",
    ),
}

ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:stack-johor-iskandar-puteri-campus",
        "curated:stack-johor-iskandar-puteri-campus:first-building-current-build",
        "curated:echelon-dub20-arklow-campus",
        "curated:echelon-dub20-arklow-campus:current-build",
        "curated:echelon-dub40-dublin-campus",
        "curated:echelon-dub40-dublin-campus:current-build",
        "curated:odata-dc-sp04-osasco-campus",
        "curated:odata-dc-sp04-osasco-campus:phase-2-expansion",
        "curated:multidc-shoham-campus",
        "curated:multidc-shoham-campus:current-build",
    }
)
ADDED_PROJECT_KEYS = frozenset(key for key in ADDED_ENTITY_KEYS if key.count(":") >= 2)
ADDED_EVIDENCE_KEYS = frozenset(
    {
        "stack-johor-campus-design-captured-2026-07-21",
        "stack-johor-first-building-progress-captured-2026-07-21",
        "echelon-dub20-construction-underway-captured-2026-07-21",
        "echelon-dub20-site-work-captured-2026-07-21",
        "echelon-dub40-structural-progress-captured-2026-07-21",
        "odata-sp04-phase2-site-mobilization-captured-2026-07-21",
        "odata-sp04-current-facility-specification-captured-2026-07-21",
        "multidc-shoham-construction-progress-captured-2026-07-21",
        "multidc-shoham-geva-project-scope-captured-2026-07-21",
    }
)
OMITTED_PUBLIC_EVIDENCE_KEY = "echelon-dub20-site-work-captured-2026-07-21"
PUBLIC_ADDED_EVIDENCE_KEYS = ADDED_EVIDENCE_KEYS - {OMITTED_PUBLIC_EVIDENCE_KEY}
ALL_ADDITION_SOURCE_FAMILIES = frozenset(
    {
        "stack_infrastructure_press_releases",
        "stack_infrastructure_linkedin_company_posts",
        "echelon_data_centres_company_news",
        "echelon_data_centres_linkedin_company_posts",
        "odata_linkedin_company_posts",
        "odata_current_facility_pages",
        "multidc_linkedin_company_posts",
        "geva_current_project_pages",
    }
)
NET_NEW_SOURCE_FAMILIES = frozenset(
    {
        "echelon_data_centres_company_news",
        "echelon_data_centres_linkedin_company_posts",
        "odata_linkedin_company_posts",
        "multidc_linkedin_company_posts",
        "geva_current_project_pages",
    }
)

LIFECYCLE_CONTRACT = frozenset(
    {
        (
            "curated:stack-johor-iskandar-puteri-campus:first-building-current-build",
            "under_construction",
            "2026-01-27",
            "authoritative_physical_status_update",
        ),
        (
            "curated:echelon-dub20-arklow-campus:current-build",
            "under_construction",
            "2026-03-27",
            "authoritative_physical_status_update",
        ),
        (
            "curated:echelon-dub40-dublin-campus:current-build",
            "shell",
            "2026-01-14",
            "authoritative_physical_status_update",
        ),
        (
            "curated:odata-dc-sp04-osasco-campus:phase-2-expansion",
            "under_construction",
            "2026-06-18",
            "authoritative_physical_status_update",
        ),
        (
            "curated:multidc-shoham-campus:current-build",
            "under_construction",
            "2026-06-03",
            "authoritative_physical_status_update",
        ),
    }
)
LIFECYCLE_EVIDENCE_CONTRACT = {
    "curated:stack-johor-iskandar-puteri-campus:first-building-current-build": (
        "stack-johor-first-building-progress-captured-2026-07-21",
        "stack_infrastructure_linkedin_company_posts",
    ),
    "curated:echelon-dub20-arklow-campus:current-build": (
        "echelon-dub20-construction-underway-captured-2026-07-21",
        "echelon_data_centres_company_news",
    ),
    "curated:echelon-dub40-dublin-campus:current-build": (
        "echelon-dub40-structural-progress-captured-2026-07-21",
        "echelon_data_centres_linkedin_company_posts",
    ),
    "curated:odata-dc-sp04-osasco-campus:phase-2-expansion": (
        "odata-sp04-phase2-site-mobilization-captured-2026-07-21",
        "odata_linkedin_company_posts",
    ),
    "curated:multidc-shoham-campus:current-build": (
        "multidc-shoham-construction-progress-captured-2026-07-21",
        "multidc_linkedin_company_posts",
    ),
}
CAPACITY_CONTRACT = frozenset(
    {
        (
            "curated:odata-dc-sp04-osasco-campus",
            "critical_it_mw",
            "design",
            "MW",
            48.0,
            "2026-06-18",
            "reported",
        ),
        (
            "curated:multidc-shoham-campus",
            "critical_it_mw",
            "design",
            "MW",
            30.0,
            "2026-06-03",
            "reported",
        ),
    }
)
FRESHNESS_CONTRACT = {
    "curated:odata-dc-sp04-osasco-campus:phase-2-expansion": (
        "under_construction",
        "2026-06-18",
        "recent_0_90_days",
        "33",
    ),
    "curated:multidc-shoham-campus:current-build": (
        "under_construction",
        "2026-06-03",
        "recent_0_90_days",
        "48",
    ),
    "curated:echelon-dub20-arklow-campus:current-build": (
        "under_construction",
        "2026-03-27",
        "aging_91_365_days",
        "116",
    ),
    "curated:stack-johor-iskandar-puteri-campus:first-building-current-build": (
        "under_construction",
        "2026-01-27",
        "aging_91_365_days",
        "175",
    ),
    "curated:echelon-dub40-dublin-campus:current-build": (
        "shell",
        "2026-01-14",
        "aging_91_365_days",
        "188",
    ),
}

ENTITY_IDS = {
    "curated:stack-johor-iskandar-puteri-campus": "a2f8d3a3-8173-538e-8ef1-0019d838b72b",
    "curated:stack-johor-iskandar-puteri-campus:first-building-current-build": "9fcb8bf2-26aa-5bfe-a9cc-9a7942033464",
    "curated:echelon-dub20-arklow-campus": "f0d89ffb-b0c1-5c52-924f-515a330e8b08",
    "curated:echelon-dub20-arklow-campus:current-build": "bad745b8-d601-5b71-9ef5-114b6fdad6a3",
    "curated:echelon-dub40-dublin-campus": "db487f5a-4299-5b36-98e0-21e738226c36",
    "curated:echelon-dub40-dublin-campus:current-build": "2b7caba9-326b-5c7d-86eb-86da01d91f1e",
    "curated:odata-dc-sp04-osasco-campus": "38a11373-73b7-50fb-9798-a06826efa6ac",
    "curated:odata-dc-sp04-osasco-campus:phase-2-expansion": "c160d8d5-7572-53c2-8051-cd7990b1f771",
    "curated:multidc-shoham-campus": "ca11a489-a94e-536c-bccb-e46f0a121d98",
    "curated:multidc-shoham-campus:current-build": "0940c2a1-ed83-5dc8-9f89-54732c4c82b2",
}
EXPECTED_OPERATORS = {
    stable_key: (
        "STACK Infrastructure"
        if "stack-johor" in stable_key
        else "Echelon Data Centres"
        if "echelon" in stable_key
        else "ODATA"
        if "odata" in stable_key
        else "MultiDC"
    )
    for stable_key in ADDED_ENTITY_KEYS
}

PROTECTED_INDEX_PINS = {
    index: pin
    for index, pin in {
        **v85.UNCHANGED_INDEX_PINS,
        **{
            row.index: (row.successor_path, row.successor_sha256)
            for row in v85.REPLACEMENTS
        },
    }.items()
}

FRESHNESS_README = f"""
Open seed v86 is the exact accepted v85 successor with only the five
seed-eligible operator/developer records from
`source_artifacts/global-official-builds-operator-social-next-tranche-2026-07-21-v1`
appended in frozen artifact order at input indices 447 through 451. The
artifact manifest is `{OFFICIAL_MANIFEST_PIN[1]}`, logical tree is
`{OFFICIAL_MANIFEST_TREE_SHA256}`, and physical tree is
`{OFFICIAL_PHYSICAL_TREE_SHA256}`.

The append contributes ten coordinate-null entities, nine company-disclosure
evidence records, five dated lifecycle observations, and exactly two typed
capacity rows: ODATA SP04 campus 48 MW critical IT design and MultiDC Shoham
campus 30 MW critical IT design. STACK's 120/220/300 MW wording, ODATA Phase 2
24 MW wording, and MultiDC/Geva MVA labels remain non-normalized narrative.
The earlier uncaptured SP04 LinkedIn candidate remains review-only in its prior
artifact; the new credential-free captured body resolves that source gap
without mutating the earlier artifact.

No coordinates, geometry, PUE, energy consumption, generation, current load,
operating-model, workload, owner, tenant, or current-status claim is inferred.
The v85 ATH04 geometry-only representative-point suppression and curated
resolution advisories remain unchanged. Every lifecycle value remains a dated
last-observed fact; `current_status_classification` remains `unknown` and
`current_construction_claim` remains `false`.
""".strip()


class OpenSeedV86Error(RuntimeError):
    """Raised when a v86 lineage, claim, or publication guard fails closed."""


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
        raise OpenSeedV86Error(f"expected ordinary JSON file: {path}")
    if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
        raise OpenSeedV86Error(f"file mode differs: {path}")
    raw = path.read_bytes()
    document = json.loads(raw)
    if raw != _canonical(document, sort_keys=sort_keys):
        raise OpenSeedV86Error(f"JSON is not canonical: {path}")
    return raw, document


def _validate_official_artifact() -> dict[str, dict[str, Any]]:
    try:
        manifest = operator.validate_artifact(OFFICIAL_ARTIFACT)
        operator._validate_frozen_witnesses()
        operator._validate_source_collisions()
    except operator.OfficialOperatorSocialError as error:
        raise OpenSeedV86Error(f"operator-social artifact invalid: {error}") from error
    manifest_raw = (OFFICIAL_ARTIFACT / "manifest.json").read_bytes()
    if (
        (len(manifest_raw), _sha256(manifest_raw)) != OFFICIAL_MANIFEST_PIN
        or manifest.get("recorded_at") != OFFICIAL_RECORDED_AT
        or manifest.get("tree_sha256") != OFFICIAL_MANIFEST_TREE_SHA256
        or v69.tree_digest(OFFICIAL_ARTIFACT) != OFFICIAL_PHYSICAL_TREE_SHA256
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
    ):
        raise OpenSeedV86Error("operator-social artifact pin or boundary differs")
    snapshot = json.loads((OFFICIAL_ARTIFACT / "source-snapshot.json").read_text())
    prior = snapshot.get("prior_review_only_resolution", {})
    if prior != {
        "artifact_id": "global-official-builds-next-tranche-2026-07-21-v1",
        "candidate_id": "odata-sp04-phase-2",
        "prior_decision": "review_only_uncaptured_official_linkedin",
        "prior_artifact_mutated": False,
        "resolution": "credential_free_public_embed_body_captured_and_hash_bound",
    }:
        raise OpenSeedV86Error("prior SP04 review-only resolution differs")
    records = snapshot.get("source_records")
    if (
        not isinstance(records, list)
        or [row.get("path") for row in records] != list(ADDITION_ORDER)
        or snapshot.get("totals")
        != {
            "candidate_assessments": 5,
            "capacity_estimates": 2,
            "coordinates_present": 0,
            "distinct_campuses": 5,
            "entity_snapshots": 10,
            "geometry_present": 0,
            "lifecycle_observations": 5,
            "operating_model_observations": 0,
            "placement_observations": 0,
            "projects": 5,
            "review_only_candidates": 0,
            "seed_eligible_source_records": 5,
            "source_records": 5,
            "unique_evidence_records": 9,
            "workload_observations": 0,
        }
    ):
        raise OpenSeedV86Error("operator-social source snapshot differs")
    documents: dict[str, dict[str, Any]] = {}
    for relative, record in zip(ADDITION_ORDER, records, strict=True):
        path = ROOT / relative
        raw, document = _read_json(path, mode=0o444)
        if (len(raw), _sha256(raw)) != ADDITION_PINS[relative] or (
            record.get("bytes"), record.get("sha256")
        ) != ADDITION_PINS[relative]:
            raise OpenSeedV86Error(f"v86 source pin differs: {relative}")
        documents[relative] = document

    evidence = {
        row["key"]: row
        for document in documents.values()
        for row in document["evidence"]
    }
    entities = {
        document[name]["stable_key"]: document[name]
        for document in documents.values()
        for name in ("campus", "project")
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
    if (
        set(evidence) != ADDED_EVIDENCE_KEYS
        or {row["source_family"] for row in evidence.values()}
        != ALL_ADDITION_SOURCE_FAMILIES
        or any(row["kind"] != "company_disclosure" for row in evidence.values())
        or set(entities) != ADDED_ENTITY_KEYS
        or lifecycle != LIFECYCLE_CONTRACT
        or capacities != CAPACITY_CONTRACT
        or any(
            entity[field] is not None
            for entity in entities.values()
            for field in ("coordinates", "geometry")
        )
        or any(
            document[section]
            for document in documents.values()
            for section in ("operating_models", "workloads")
        )
    ):
        raise OpenSeedV86Error("v86 source claim contract differs")
    assessment = json.loads(
        (OFFICIAL_ARTIFACT / "candidate-assessment.json").read_text()
    )
    withheld = {
        value
        for row in assessment.get("candidates", [])
        for value in row.get("withheld_non_normalized_power_labels", [])
    }
    if withheld != {
        "120MW building",
        "220MW campus",
        "300MW substation",
        "Phase 2 24 MW wording",
        "32MVA+32MVA",
        "16MVA",
        "150MVA",
    }:
        raise OpenSeedV86Error("v86 withheld power-label boundary differs")
    return documents


def _base_paths(base: Mapping[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for row in base["curated_inputs"]:
        path = ROOT / row["path"]
        if path.is_symlink() or not path.is_file() or v69.sha256(path) != row["sha256"]:
            raise OpenSeedV86Error(f"accepted v85 input pin differs: {row['path']}")
        paths.append(path)
    return paths


def selected_inputs(
    base: Mapping[str, Any],
    *,
    recorded_at: str,
    validation_wall_clock: datetime | None = None,
) -> tuple[list[dict[str, str]], list[Path]]:
    if base.get("release_id") != v85.RELEASE_ID:
        raise OpenSeedV86Error("v86 base must be exactly accepted v85")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 447:
        raise OpenSeedV86Error("accepted v85 curated inventory differs")
    if any(not isinstance(row, dict) or set(row) != {"path", "sha256"} for row in rows):
        raise OpenSeedV86Error("accepted v85 curated rows differ")
    documents = _validate_official_artifact()
    target = v70.parse_utc(recorded_at, label="v86 recorded_at")
    wall = validation_wall_clock or datetime.now(UTC)
    if (
        wall.tzinfo is None
        or target > wall.astimezone(UTC)
        or v70.parse_utc(OFFICIAL_RECORDED_AT, label="official recorded_at") > target
    ):
        raise OpenSeedV86Error("v86 publication time precedes an input")

    paths = _base_paths(base)
    base_stable_keys: set[str] = set()
    base_evidence_keys: set[str] = set()
    for path in paths:
        document = json.loads(path.read_text())
        for name in ("campus", "facility", "building", "project"):
            row = document.get(name)
            if isinstance(row, dict) and isinstance(row.get("stable_key"), str):
                base_stable_keys.add(row["stable_key"])
        base_evidence_keys.update(
            row["key"]
            for row in document.get("evidence", [])
            if isinstance(row, dict) and isinstance(row.get("key"), str)
        )
    if base_stable_keys & ADDED_ENTITY_KEYS or base_evidence_keys & ADDED_EVIDENCE_KEYS:
        raise OpenSeedV86Error("v86 append collides with accepted v85 semantics")

    selected = [dict(row) for row in rows]
    for relative in ADDITION_ORDER:
        selected.append({"path": relative, "sha256": ADDITION_PINS[relative][1]})
        paths.append(ROOT / relative)
    if (
        selected[:447] != rows
        or [row["path"] for row in selected[447:]] != list(ADDITION_ORDER)
        or tuple(documents) != ADDITION_ORDER
        or len(selected) != 452
        or len({row["path"] for row in selected}) != 452
    ):
        raise OpenSeedV86Error("v86 did not append exactly five ordered inputs")
    for index, expected in PROTECTED_INDEX_PINS.items():
        if (selected[index]["path"], selected[index]["sha256"]) != expected:
            raise OpenSeedV86Error(f"v86 changed protected coordinate index {index}")
    for relative, document in documents.items():
        for index, evidence in enumerate(document["evidence"]):
            retrieved = v70.parse_utc(
                evidence["retrieved_at"],
                label=f"{relative} evidence[{index}].retrieved_at",
            )
            if retrieved > target or retrieved > wall.astimezone(UTC):
                raise OpenSeedV86Error("v86 selected evidence is future-dated")
    return selected, paths


def _guard_state() -> dict[str, Any]:
    _validate_official_artifact()
    base = json.loads(BASE_DEFINITION.read_text())
    return {
        "base_definition": (BASE_DEFINITION.stat().st_size, v69.sha256(BASE_DEFINITION)),
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
        "protected_indices": {
            index: (
                base["curated_inputs"][index]["path"],
                base["curated_inputs"][index]["sha256"],
            )
            for index in PROTECTED_INDEX_PINS
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
        "entities": 927,
        "entity_snapshots": 948,
        "evidence": 763,
        "lifecycle_observations": 537,
        "capacity_estimates": 553,
        "operating_model_observations": 71,
        "workload_observations": 135,
    }
    actual_counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in expected_counts
    }
    if actual_counts != expected_counts:
        raise OpenSeedV86Error(f"v86 database counts differ: {actual_counts}")
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v86-base-", dir="/private/tmp"
    ) as temporary:
        prior = v69._populate_database(
            base,
            _base_paths(base),
            Path(temporary) / "v85.sqlite",
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
                    raise OpenSeedV86Error(f"v86 changed a v85 database row: {table}")
            before_entities = {row[0] for row in prior.execute("SELECT stable_key FROM entities")}
            after_entities = {row[0] for row in connection.execute("SELECT stable_key FROM entities")}
            if after_entities - before_entities != ADDED_ENTITY_KEYS or before_entities - after_entities:
                raise OpenSeedV86Error("v86 database identity delta differs")
            before_evidence = set(v70._evidence_by_key(prior))
            after_evidence = set(v70._evidence_by_key(connection))
            if (
                after_evidence - before_evidence != ADDED_EVIDENCE_KEYS
                or before_evidence - after_evidence
            ):
                raise OpenSeedV86Error("v86 database evidence delta differs")
        finally:
            prior.close()

    keys = tuple(sorted(ADDED_ENTITY_KEYS))
    placeholders = ",".join("?" for _ in keys)
    lifecycle_rows = list(
        connection.execute(
            f"""
            SELECT entities.stable_key, status, as_of_date,
                   lifecycle_observations.method,
                   lifecycle_observations.confidence,
                   lifecycle_observations.notes,
                   lifecycle_observations.valid_to_date,
                   evidence.metadata_json
            FROM lifecycle_observations
            JOIN entities ON entities.id = entity_id
            JOIN evidence ON evidence.id = evidence_id
            WHERE entities.stable_key IN ({placeholders})
            """,
            keys,
        )
    )
    lifecycle = {tuple(row[:4]) for row in lifecycle_rows}
    capacities = {
        tuple(row)
        for row in connection.execute(
            f"""
            SELECT entities.stable_key, metric, stage, unit, base, as_of_date,
                   capacity_estimates.method
            FROM capacity_estimates
            JOIN entities ON entities.id = entity_id
            WHERE entities.stable_key IN ({placeholders})
            """,
            keys,
        )
    }
    models = connection.execute(
        f"""
        SELECT COUNT(*) FROM operating_model_observations
        JOIN entities ON entities.id = entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        keys,
    ).fetchone()[0]
    workloads = connection.execute(
        f"""
        SELECT COUNT(*) FROM workload_observations
        JOIN entities ON entities.id = entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        keys,
    ).fetchone()[0]
    snapshots = list(
        connection.execute(
            f"""
            SELECT entities.stable_key, latitude, longitude, geometry_json,
                   tags_json
            FROM entity_snapshots
            JOIN entities ON entities.id = entity_id
            WHERE entities.stable_key IN ({placeholders})
            """,
            keys,
        )
    )
    if (
        lifecycle != LIFECYCLE_CONTRACT
        or {
            row[0]: (
                json.loads(row[7] or "{}").get("curated_record_key"),
                row[4],
                row[5],
                row[6],
            )
            for row in lifecycle_rows
        }
        != {
            stable_key: (evidence_key, 0.99, None, None)
            for stable_key, (evidence_key, _family) in (
                LIFECYCLE_EVIDENCE_CONTRACT.items()
            )
        }
        or capacities != CAPACITY_CONTRACT
        or models
        or workloads
        or len(snapshots) != 10
        or any(
            row[1] is not None or row[2] is not None or row[3] not in {None, "null"}
            for row in snapshots
        )
    ):
        raise OpenSeedV86Error("v86 imported claim contract differs")
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
        != ALL_ADDITION_SOURCE_FAMILIES
    ):
        raise OpenSeedV86Error("v86 imported evidence classification differs")
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
        raise OpenSeedV86Error("v86 coordinate coverage changed")


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
    output = v85._augment_release(documents)
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
            raise OpenSeedV86Error("precreated v86 release stage must be empty")
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


CSV_DELTA_COUNT_CONTRACT = {
    "entities.csv": (917, 10, 0),
    "evidence.csv": (603, 8, 0),
    "capacity_estimates.csv": (550, 2, 0),
    "construction_pipeline.csv": (464, 5, 0),
    "construction_source_signals.csv": (366, 5, 0),
    "lifecycle_freshness.csv": (512, 5, 0),
    "resolution_candidates.csv": (9, 0, 0),
}


def _validate_release_delta(stage: Path, *, recorded_at: str) -> None:
    timestamps = {BASE_RECORDED_AT, recorded_at}
    for filename, expected in CSV_DELTA_COUNT_CONTRACT.items():
        before = _csv_counter(BASE_RELEASE / filename, recorded_at_values=timestamps)
        after = _csv_counter(stage / filename, recorded_at_values=timestamps)
        common = before & after
        actual = (
            sum(common.values()),
            sum((after - common).values()),
            sum((before - common).values()),
        )
        if actual != expected:
            raise OpenSeedV86Error(
                f"v86 public CSV delta differs: {filename}: {actual}"
            )

    before_entities = {
        row["stable_key"]: row for row in _csv_rows(BASE_RELEASE / "entities.csv")
    }
    after_entities = {
        row["stable_key"]: row for row in _csv_rows(stage / "entities.csv")
    }
    if (
        set(after_entities) - set(before_entities) != ADDED_ENTITY_KEYS
        or set(before_entities) - set(after_entities)
        or any(after_entities[key] != row for key, row in before_entities.items())
        or len(after_entities) != 927
    ):
        raise OpenSeedV86Error("v86 public entity append differs")
    expected_capacity_by_key = {
        stable_key: (metric, stage_name, unit, base, as_of_date, method)
        for (
            stable_key,
            metric,
            stage_name,
            unit,
            base,
            as_of_date,
            method,
        ) in CAPACITY_CONTRACT
    }
    for stable_key in ADDED_ENTITY_KEYS:
        row = after_entities[stable_key]
        capacities = json.loads(row["capacity_estimates_json"])
        expected_capacity = expected_capacity_by_key.get(stable_key)
        if (
            row["entity_id"] != ENTITY_IDS[stable_key]
            or row["latitude"]
            or row["longitude"]
            or row["geometry_json"] != "null"
            or row["owner"]
            or row["operator"] != EXPECTED_OPERATORS[stable_key]
            or row["operating_model"]
            or json.loads(row["workloads_json"])
        ):
            raise OpenSeedV86Error(f"v86 public entity boundary differs: {stable_key}")
        if expected_capacity is None:
            if capacities:
                raise OpenSeedV86Error(f"v86 entity gained capacity: {stable_key}")
        elif (
            len(capacities) != 1
            or (
                capacities[0]["metric"],
                capacities[0]["stage"],
                capacities[0]["unit"],
                capacities[0]["base"],
                capacities[0]["as_of_date"],
                capacities[0]["method"],
            )
            != expected_capacity
        ):
            raise OpenSeedV86Error(f"v86 typed capacity differs: {stable_key}")

    before_evidence = {
        row["evidence_id"]: row for row in _csv_rows(BASE_RELEASE / "evidence.csv")
    }
    after_evidence = {
        row["evidence_id"]: row for row in _csv_rows(stage / "evidence.csv")
    }
    added_evidence = [
        row for key, row in after_evidence.items() if key not in before_evidence
    ]
    if (
        set(before_evidence) - set(after_evidence)
        or any(after_evidence[key] != row for key, row in before_evidence.items())
        or len(added_evidence) != 8
        or any(row["kind"] != "company_disclosure" for row in added_evidence)
        or Counter(row["source_family"] for row in added_evidence)
        != Counter(ALL_ADDITION_SOURCE_FAMILIES)
    ):
        raise OpenSeedV86Error("v86 public evidence projection differs")
    lifecycle_evidence = {
        family: row
        for row in added_evidence
        for family in (row["source_family"],)
        if family
        in {value[1] for value in LIFECYCLE_EVIDENCE_CONTRACT.values()}
    }
    if set(lifecycle_evidence) != {
        value[1] for value in LIFECYCLE_EVIDENCE_CONTRACT.values()
    }:
        raise OpenSeedV86Error("v86 lifecycle evidence projection differs")

    before_capacity = {
        tuple(row.items()) for row in _csv_rows(BASE_RELEASE / "capacity_estimates.csv")
    }
    after_capacity_rows = _csv_rows(stage / "capacity_estimates.csv")
    after_capacity = {tuple(row.items()) for row in after_capacity_rows}
    added_capacity = [
        row for row in after_capacity_rows if tuple(row.items()) not in before_capacity
    ]
    id_to_key = {entity_id: stable_key for stable_key, entity_id in ENTITY_IDS.items()}
    projected_capacity = {
        (
            id_to_key[row["entity_id"]],
            row["metric"],
            row["stage"],
            row["unit"],
            float(row["base"]),
            row["as_of_date"],
            row["method"],
        )
        for row in added_capacity
    }
    if (
        before_capacity - after_capacity
        or len(added_capacity) != 2
        or projected_capacity != CAPACITY_CONTRACT
        or any(
            not (float(row["low"]) == float(row["base"]) == float(row["high"]))
            for row in added_capacity
        )
    ):
        raise OpenSeedV86Error("v86 public capacity append differs")

    before_pipeline = {
        row["stable_key"]: row
        for row in _csv_rows(BASE_RELEASE / "construction_pipeline.csv")
    }
    after_pipeline = {
        row["stable_key"]: row
        for row in _csv_rows(stage / "construction_pipeline.csv")
    }
    added_pipeline = [
        row for key, row in after_pipeline.items() if key not in before_pipeline
    ]
    if (
        set(before_pipeline) - set(after_pipeline)
        or any(after_pipeline[key] != row for key, row in before_pipeline.items())
        or {row["stable_key"] for row in added_pipeline} != ADDED_PROJECT_KEYS
        or len(added_pipeline) != 5
        or any(
            row["latitude"]
            or row["longitude"]
            or row["geometry_json"] != "null"
            or json.loads(row["capacity_estimates_json"])
            or json.loads(row["workloads_json"])
            for row in added_pipeline
        )
    ):
        raise OpenSeedV86Error("v86 construction-pipeline append differs")
    lifecycle_by_key = {row[0]: row[1:] for row in LIFECYCLE_CONTRACT}
    pipeline_by_key = {row["stable_key"]: row for row in added_pipeline}
    for stable_key, row in pipeline_by_key.items():
        status, as_of_date, method = lifecycle_by_key[stable_key]
        _evidence_key, family = LIFECYCLE_EVIDENCE_CONTRACT[stable_key]
        evidence = lifecycle_evidence[family]
        actual = (
            row["entity_id"],
            row["entity_kind"],
            row["status"],
            row["status_as_of"],
            row["status_method"],
            row["status_confidence"],
            row["status_evidence_id"],
            row["snapshot_as_of"],
            row["snapshot_confidence"],
            row["snapshot_evidence_id"],
            row["source_license"],
            row["source_publisher"],
            row["source_retrieved_at"],
            row["source_url"],
        )
        expected = (
            ENTITY_IDS[stable_key],
            "project",
            status,
            as_of_date,
            method,
            "0.99",
            evidence["evidence_id"],
            as_of_date,
            "0.99",
            evidence["evidence_id"],
            evidence["license"],
            evidence["publisher"],
            evidence["retrieved_at"],
            evidence["source_url"],
        )
        if actual != expected:
            raise OpenSeedV86Error(
                f"v86 construction-pipeline lifecycle differs: {stable_key}"
            )

    before_signals = {
        row["source_observation_evidence_id"]: row
        for row in _csv_rows(BASE_RELEASE / "construction_source_signals.csv")
    }
    after_signals = {
        row["source_observation_evidence_id"]: row
        for row in _csv_rows(stage / "construction_source_signals.csv")
    }
    added_signals = [
        row for key, row in after_signals.items() if key not in before_signals
    ]
    if (
        set(before_signals) - set(after_signals)
        or any(after_signals[key] != row for key, row in before_signals.items())
        or len(added_signals) != 5
        or {row["representative_stable_key"] for row in added_signals}
        != ADDED_PROJECT_KEYS
        or any(
            row["representative_latitude"] or row["representative_longitude"]
            for row in added_signals
        )
    ):
        raise OpenSeedV86Error("v86 construction-signal append differs")
    for row in added_signals:
        stable_key = row["representative_stable_key"]
        status, as_of_date, method = lifecycle_by_key[stable_key]
        _evidence_key, family = LIFECYCLE_EVIDENCE_CONTRACT[stable_key]
        evidence = lifecycle_evidence[family]
        pipeline = pipeline_by_key[stable_key]
        affected = json.loads(row["affected_entities_json"])
        expected_affected = [
            {
                "entity_id": ENTITY_IDS[stable_key],
                "entity_kind": "project",
                "name": pipeline["name"],
                "stable_key": stable_key,
                "status": status,
                "status_as_of": as_of_date,
                "status_method": method,
            }
        ]
        actual = (
            row["affected_entity_count"],
            row["representative_entity_id"],
            row["representative_entity_kind"],
            row["representative_status"],
            row["representative_status_as_of"],
            row["representative_status_method"],
            row["representative_status_confidence"],
            row["source_attribution"],
            row["source_content_hash"],
            row["source_family"],
            row["source_kind"],
            row["source_license"],
            row["source_observation_evidence_id"],
            row["source_published_at"],
            row["source_publisher"],
            row["source_retrieved_at"],
            row["source_title"],
            row["source_url"],
        )
        expected = (
            "1",
            ENTITY_IDS[stable_key],
            "project",
            status,
            as_of_date,
            method,
            "0.99",
            evidence["attribution"],
            evidence["content_hash"],
            family,
            "company_disclosure",
            evidence["license"],
            evidence["evidence_id"],
            evidence["published_at"],
            evidence["publisher"],
            evidence["retrieved_at"],
            evidence["title"],
            evidence["source_url"],
        )
        if affected != expected_affected or actual != expected:
            raise OpenSeedV86Error(
                f"v86 construction-signal semantics differ: {stable_key}"
            )

    before_freshness = {
        row["stable_key"]: row
        for row in _csv_rows(BASE_RELEASE / FRESHNESS_FILENAME)
    }
    after_freshness = {
        row["stable_key"]: row for row in _csv_rows(stage / FRESHNESS_FILENAME)
    }
    added_freshness = {
        key: row for key, row in after_freshness.items() if key not in before_freshness
    }
    if (
        set(before_freshness) - set(after_freshness)
        or any(after_freshness[key] != row for key, row in before_freshness.items())
        or set(added_freshness) != ADDED_PROJECT_KEYS
    ):
        raise OpenSeedV86Error("v86 lifecycle-freshness append differs")
    for stable_key, expected in FRESHNESS_CONTRACT.items():
        row = added_freshness[stable_key]
        actual = (
            row["last_observed_status"],
            row["last_observed_status_as_of"],
            row["freshness_class"],
            row["observation_age_days"],
        )
        if actual != expected:
            raise OpenSeedV86Error(f"v86 freshness differs: {stable_key}")

    for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
        if (stage / filename).read_bytes() != (BASE_RELEASE / filename).read_bytes():
            raise OpenSeedV86Error(f"v86 changed invariant resolution: {filename}")

    before_sources = json.loads(
        (BASE_RELEASE / "source_inputs.json").read_text()
    )["sources"]
    after_sources = json.loads((stage / "source_inputs.json").read_text())["sources"]
    before_source_rows = {
        json.dumps(row, sort_keys=True, ensure_ascii=False) for row in before_sources
    }
    after_source_rows = {
        json.dumps(row, sort_keys=True, ensure_ascii=False) for row in after_sources
    }
    added_sources = [json.loads(row) for row in after_source_rows - before_source_rows]
    if (
        before_source_rows - after_source_rows
        or len(after_sources) != 538
        or len(added_sources) != 8
        or {
            row.get("provenance", {}).get("curated_record_key")
            for row in added_sources
        }
        != PUBLIC_ADDED_EVIDENCE_KEYS
        or any(
            row.get("provenance", {}).get("content_hash_verification")
            != "fetched_bytes_sha256"
            for row in added_sources
        )
    ):
        raise OpenSeedV86Error("v86 public source-input append differs")

    before_atlas = json.loads((BASE_RELEASE / "atlas.geojson").read_text())
    after_atlas = json.loads((stage / "atlas.geojson").read_text())
    before_features = {
        row["properties"]["stable_key"]: row for row in before_atlas["features"]
    }
    after_features = {
        row["properties"]["stable_key"]: row for row in after_atlas["features"]
    }
    added_features = {
        key: row for key, row in after_features.items() if key not in before_features
    }
    geometry_types = Counter(
        row["geometry"]["type"]
        for row in after_features.values()
        if row["geometry"] is not None
    )
    if (
        set(before_features) - set(after_features)
        or any(after_features[key] != row for key, row in before_features.items())
        or set(added_features) != ADDED_ENTITY_KEYS
        or any(
            row["geometry"] is not None
            or row["properties"]["latitude"] is not None
            or row["properties"]["longitude"] is not None
            for row in added_features.values()
        )
        or geometry_types != {"Point": 133, "Polygon": 81, "MultiPolygon": 1}
    ):
        raise OpenSeedV86Error("v86 GeoJSON append or geometry partition differs")


def _validate_release_facts(stage: Path, *, recorded_at: str) -> None:
    base_summary = json.loads((BASE_RELEASE / "summary.json").read_text())
    expected_summary = copy.deepcopy(base_summary)
    expected_summary.update(
        {
            "campuses_total": 485,
            "capacity_estimates_current": 552,
            "construction_pipeline_records": 469,
            "construction_source_signals": 371,
            "entities_total": 927,
            "evidence_total": 763,
            "lifecycle_observations_current": 517,
            "projects_total": 442,
            "recorded_at": recorded_at,
        }
    )
    expected_summary["entities_by_kind"] = {"campus": 485, "project": 442}
    expected_summary["country_assignment_counts"]["not_evaluated"] = 927
    expected_summary["country_source_claims_by_method"][
        "source_explicit_country_tag"
    ] = 927
    expected_summary["country_source_tag_fallbacks"] = 927
    expected_summary["entities_by_country"].update(
        {"Brazil": 45, "Ireland": 8, "Israel": 12, "Malaysia": 32}
    )
    expected_summary["entities_by_status"].update(
        {"shell": 33, "under_construction": 356}
    )
    expected_summary["evidence_by_kind"]["company_disclosure"] = 566
    expected_summary["capacity_estimates_by_metric"]["critical_it_mw"] = 280
    expected_summary["capacity_estimates_by_stage"]["design"] = 30
    summary = json.loads((stage / "summary.json").read_text())
    if summary != expected_summary:
        raise OpenSeedV86Error("v86 full summary delta differs")

    base_manifest = json.loads((BASE_RELEASE / "manifest.json").read_text())
    manifest = json.loads((stage / "manifest.json").read_text())
    expected_manifest = {
        key: copy.deepcopy(value)
        for key, value in base_manifest.items()
        if key != "files"
    }
    expected_manifest.update(
        {
            "capacity_estimates": 552,
            "construction_pipeline_records": 469,
            "construction_source_signals": 371,
            "entities": 927,
            "entities_by_kind": {"campus": 485, "project": 442},
            "evidence_records": 611,
            "lifecycle_freshness_records": 517,
            "recorded_at": recorded_at,
            "source_families": sorted(
                set(base_manifest["source_families"]) | NET_NEW_SOURCE_FAMILIES
            ),
        }
    )
    if (
        {key: value for key, value in manifest.items() if key != "files"}
        != expected_manifest
        or len(manifest.get("source_families", [])) != 366
        or manifest.get("geometry_only_representative_point_inferred") is not False
        or manifest.get("resolution_candidates") != 9
    ):
        raise OpenSeedV86Error("v86 full manifest delta differs")

    freshness = _csv_rows(stage / FRESHNESS_FILENAME)
    classes = Counter(row["freshness_class"] for row in freshness)
    if (
        len(freshness) != 517
        or tuple(freshness[0]) != FRESHNESS_FIELDS
        or classes
        != {
            "recent_0_90_days": 270,
            "aging_91_365_days": 214,
            "stale_over_365_days": 33,
        }
        or any(
            row["status_semantics"] != "last_observed"
            or row["current_status_classification"] != "unknown"
            or row["current_construction_claim"] != "false"
            for row in freshness
        )
    ):
        raise OpenSeedV86Error("v86 freshness/current-status boundary differs")

    entities = _csv_rows(stage / "entities.csv")
    if (
        sum(bool(row["latitude"] and row["longitude"]) for row in entities) != 213
        or any(
            row["latitude"] or row["longitude"]
            for row in entities
            if row["stable_key"] in v85.ATH04_KEYS
        )
    ):
        raise OpenSeedV86Error("v86 coordinate or ATH04 projection differs")
    readme = (stage / "README.md").read_text()
    for marker in (
        OFFICIAL_MANIFEST_PIN[1],
        OFFICIAL_MANIFEST_TREE_SHA256,
        OFFICIAL_PHYSICAL_TREE_SHA256,
        "appended in frozen artifact order at input indices 447 through 451",
        "ODATA SP04 campus 48 MW critical IT design and MultiDC Shoham",
        "STACK's 120/220/300 MW wording",
        "earlier uncaptured SP04 LinkedIn candidate remains review-only",
        "ATH04 geometry-only representative-point suppression",
        "current_status_classification` remains `unknown",
        "current_construction_claim` remains `false",
    ):
        if marker not in readme:
            raise OpenSeedV86Error(f"v86 README guardrail differs: {marker}")
    if len(list(stage.iterdir())) != 14:
        raise OpenSeedV86Error("v86 release file inventory count differs")


def _validate_definition(
    document: Mapping[str, Any],
    base: Mapping[str, Any],
    *,
    validation_wall_clock: datetime,
) -> str:
    if set(document) != set(base) or document.get("release_id") != RELEASE_ID:
        raise OpenSeedV86Error("v86 definition identity or schema differs")
    build = document.get("build")
    if not isinstance(build, dict) or set(build) != {"as_of", "recorded_at"}:
        raise OpenSeedV86Error("v86 definition build carrier differs")
    if build["as_of"] != AS_OF:
        raise OpenSeedV86Error("v86 as_of differs")
    expected_summary = document.get("expected_summary")
    if not isinstance(expected_summary, dict) or set(expected_summary) != set(
        base["expected_summary"]
    ):
        raise OpenSeedV86Error("v86 expected-summary key contract differs")
    recorded = v70.parse_utc(build["recorded_at"], label="v86 recorded_at")
    if (
        validation_wall_clock.tzinfo is None
        or recorded > validation_wall_clock.astimezone(UTC)
    ):
        raise OpenSeedV86Error("v86 recorded_at is later than validation wall clock")
    for key in (
        "epoch_capture",
        "expected_epoch_result",
        "freshness_contract",
        "publication_contract_version",
        "schema_version",
        "scope",
    ):
        if document.get(key) != base.get(key):
            raise OpenSeedV86Error(f"v86 inherited definition field differs: {key}")
    return build["recorded_at"]


def _validate_publication_times(
    definition: Path,
    release: Path,
    *,
    recorded_at: str,
    require_live: bool,
) -> None:
    target = v70.parse_utc(recorded_at, label="v86 recorded_at")
    for path in (definition, release, *release.iterdir()):
        metadata = path.stat(follow_symlinks=False)
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV86Error(f"v86 staged inode post-dates recorded_at: {path.name}")
    if require_live:
        if datetime.now(UTC) < target:
            raise OpenSeedV86Error("v86 recorded_at is not live")
        for path in (definition, release):
            if path.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
                raise OpenSeedV86Error(
                    f"v86 final root ctime predates recorded_at: {path.name}"
                )


def _validate_guard(guard: Mapping[str, Any]) -> None:
    base_files = list(BASE_RELEASE.iterdir()) if BASE_RELEASE.is_dir() else []
    if (
        v85.DEFINITION != BASE_DEFINITION
        or v85.RELEASE != BASE_RELEASE
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
        raise OpenSeedV86Error("accepted v85 base pin differs")
    if (
        guard["official_manifest"] != OFFICIAL_MANIFEST_PIN
        or guard["official_tree"] != OFFICIAL_PHYSICAL_TREE_SHA256
        or guard["additions"] != ADDITION_PINS
        or guard["protected_indices"] != PROTECTED_INDEX_PINS
    ):
        raise OpenSeedV86Error("v86 official-source or protected-index pin differs")


def validate_open_seed_v86(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
    require_live: bool = True,
) -> dict[str, Any]:
    if replay_count != 2:
        raise OpenSeedV86Error("v86 requires exactly two offline replays")
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
        raise OpenSeedV86Error("v86 selected input inventory differs")
    if release_path.is_symlink() or not release_path.is_dir():
        raise OpenSeedV86Error("v86 release must be an ordinary directory")
    if require_frozen and stat.S_IMODE(release_path.stat().st_mode) != 0o555:
        raise OpenSeedV86Error("v86 release root is not frozen")
    release_files = {path.name: path for path in release_path.iterdir()}
    if any(path.is_symlink() or not path.is_file() for path in release_files.values()):
        raise OpenSeedV86Error("v86 release contains a non-file")
    if require_frozen and any(
        stat.S_IMODE(path.stat().st_mode) != 0o444
        for path in release_files.values()
    ):
        raise OpenSeedV86Error("v86 release file is not frozen")
    manifest_raw, manifest = _read_json(
        release_path / "manifest.json", mode=0o444, sort_keys=True
    )
    if _sha256(manifest_raw) != definition["expected_release"].get(
        "manifest_sha256"
    ):
        raise OpenSeedV86Error("v86 manifest hash differs")
    expected_release = {
        key: value
        for key, value in definition["expected_release"].items()
        if key != "manifest_sha256"
    }
    if {key: value for key, value in manifest.items() if key != "files"} != expected_release:
        raise OpenSeedV86Error("v86 expected release facts differ")
    if set(release_files) != set(manifest["files"]) | {"manifest.json"}:
        raise OpenSeedV86Error("v86 release file inventory differs")
    for filename, pin in manifest["files"].items():
        raw = (release_path / filename).read_bytes()
        if (len(raw), _sha256(raw)) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV86Error(f"v86 release pin differs: {filename}")
    _validate_publication_times(
        definition_path,
        release_path,
        recorded_at=recorded_at,
        require_live=require_live,
    )
    _validate_release_delta(release_path, recorded_at=recorded_at)
    _validate_release_facts(release_path, recorded_at=recorded_at)
    summary = json.loads((release_path / "summary.json").read_text())
    if {key: summary[key] for key in definition["expected_summary"]} != definition[
        "expected_summary"
    ]:
        raise OpenSeedV86Error("v86 expected summary differs")

    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v86-replay-{replay + 1}-", dir="/private/tmp"
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
            _validate_release_delta(replay_release, recorded_at=recorded_at)
            _validate_release_facts(replay_release, recorded_at=recorded_at)
            if {path.name for path in replay_release.iterdir()} != set(release_files):
                raise OpenSeedV86Error("v86 replay file inventory differs")
            for filename, frozen in release_files.items():
                if (replay_release / filename).read_bytes() != frozen.read_bytes():
                    raise OpenSeedV86Error(f"v86 offline replay differs: {filename}")
    if _guard_state() != guard:
        raise OpenSeedV86Error("v86 validation mutated accepted inputs")
    return manifest


def _path_identity(path: Path, *, directory: bool) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    expected = (
        stat.S_ISDIR(metadata.st_mode)
        if directory
        else stat.S_ISREG(metadata.st_mode)
    )
    if not expected:
        raise OpenSeedV86Error(f"v86 stage type differs: {path}")
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
        raise OpenSeedV86Error("v86 release stage root identity changed")
    if _release_identities(root) != dict(members):
        raise OpenSeedV86Error("v86 release stage member identity changed")


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
        raise OpenSeedV86Error("refusing substituted v86 definition cleanup")
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
        raise OpenSeedV86Error("active v86 publication lock exists") from error
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
                raise OpenSeedV86Error("refusing substituted v86 lock cleanup")
            PUBLICATION_LOCK.unlink()


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _require_absent(label: str) -> None:
    if DEFINITION.exists() or DEFINITION.is_symlink():
        raise OpenSeedV86Error(f"{label} v86 definition collision")
    if RELEASE.exists() or RELEASE.is_symlink():
        raise OpenSeedV86Error(f"{label} v86 release collision")


def _rollback_release(release_identity: tuple[int, int], release_stage: Path) -> None:
    if _path_identity(RELEASE, directory=True) != release_identity:
        raise OpenSeedV86Error("refusing rollback of substituted v86 release")
    if release_stage.exists() or release_stage.is_symlink():
        raise OpenSeedV86Error("v86 release rollback stage is occupied")
    v69.promote_noreplace(RELEASE, release_stage)


def _rollback_definition(
    definition_identity: tuple[int, int], definition_stage: Path
) -> None:
    if _path_identity(DEFINITION, directory=False) != definition_identity:
        raise OpenSeedV86Error("refusing rollback of substituted v86 definition")
    if definition_stage.exists() or definition_stage.is_symlink():
        raise OpenSeedV86Error("v86 definition rollback stage is occupied")
    v69.promote_noreplace(DEFINITION, definition_stage)


def build_open_seed_v86(recorded_at: str | None = None) -> dict[str, Any]:
    """Build and atomically publish the five-source v85 successor."""

    if (DEFINITION.exists() or DEFINITION.is_symlink()) and (
        RELEASE.exists() or RELEASE.is_symlink()
    ):
        manifest = validate_open_seed_v86()
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
        raise OpenSeedV86Error("partial v86 final-path collision")

    guard = _guard_state()
    _validate_guard(guard)
    target = (
        v70.parse_utc(recorded_at, label="v86 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise OpenSeedV86Error("v86 recorded_at must be future before staging")
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
                prefix="open-seed-v86-db-", dir="/private/tmp"
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
            _validate_release_delta(release_stage, recorded_at=recorded_at)
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
                raise OpenSeedV86Error("v86 definition stage identity changed")
            _assert_release_identities(
                release_stage, release_identity, release_members
            )
            if (
                definition_stage.read_bytes() != frozen_definition
                or v69.tree_digest(release_stage) != frozen_tree
            ):
                raise OpenSeedV86Error("v86 private stage changed while waiting")
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
                    error.add_note(f"v86 release rollback failed: {rollback_error}")
                raise
            try:
                manifest = validate_open_seed_v86(DEFINITION, RELEASE)
            except BaseException as error:
                rollback_errors: list[str] = []
                try:
                    _rollback_definition(definition_identity, definition_stage)
                    published_definition = False
                except Exception as rollback_error:
                    rollback_errors.append(
                        f"v86 definition rollback failed: {rollback_error}"
                    )
                try:
                    _rollback_release(release_identity, release_stage)
                    published_release = False
                except Exception as rollback_error:
                    rollback_errors.append(
                        f"v86 release rollback failed: {rollback_error}"
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
        raise OpenSeedV86Error("v86 build mutated accepted inputs")
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
    print(json.dumps(build_open_seed_v86(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
