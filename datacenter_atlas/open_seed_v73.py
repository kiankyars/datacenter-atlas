"""Build the strict four-source official-build successor to open seed v72."""

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

from . import open_seed_v69 as v69
from . import open_seed_v70 as v70
from .open_seed_v61 import FRESHNESS_FIELDS, FRESHNESS_FILENAME, build_freshness_csv
from .publication_release import build_release_documents
from .service import summarize


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v72.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v72"
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v73.json"
RELEASE_ID = "2026-07-21-open-seed-v73"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v73.lock"
AS_OF = "2026-07-21"

BASE_RECORDED_AT = "2026-07-21T13:06:15Z"
BASE_DEFINITION_PIN = (
    87_104,
    "33fa28074d38ad00810be9717fac2a12ac04b68c9309254ce8bc5bdfc32b7c2a",
)
BASE_MANIFEST_SHA256 = (
    "114b79b4ce95457ec772a5d96d0fb385433b15e8ccd7668a9289aede2cad1801"
)
BASE_TREE_SHA256 = "0cbd0a804cf7085a09a55cc9a6d83d78470d4b4ccfd12f3e3dbbb69ba09303e3"

OFFICIAL_ARTIFACT = (
    ROOT / "source_artifacts/global-official-builds-six-candidate-2026-07-21-v1"
)
OFFICIAL_RECORDED_AT = "2026-07-21T13:06:52Z"
OFFICIAL_MANIFEST_PIN = (
    1_727,
    "20b0788dba18402cf1b6bb8874ec6cd66f86000ff85f620c7e0167bf7e1894cd",
)
OFFICIAL_MANIFEST_TREE_SHA256 = (
    "1269fe1d094178118312515967757cbd48c2f2cf035a2bca3db1894ab00c1454"
)
OFFICIAL_PHYSICAL_TREE_SHA256 = (
    "1562710dfd1ea030e39a83636acc322ba1ec37fd67a3e857ecce54944b67e0a0"
)
OFFICIAL_SNAPSHOT_PIN = (
    6_274,
    "1a6020ca7d8a07918af5397907abd90c14154f9e154427809177fa2f63a10ee4",
)
OFFICIAL_ASSESSMENT_PIN = (
    2_756,
    "1d578e8e54087c378c6239f2491661583a6aaaa108226e8e983b3e63cc5e7e13",
)
OFFICIAL_RIGHTS_PIN = (
    1_343,
    "72f73a89d19aceaae15048494efadc3664b4aca6d46d6c9b860db13954259a23",
)

ADDITION_PINS = {
    "sources/curated-official-2026-07-21-akashi-astana-phase-1-current-build.json": (
        8_057,
        "7f93487075c06e359c8f41c264633393b64b731c4f5d89b4a804dc5476db2543",
    ),
    "sources/curated-official-2026-07-21-bichuten-chovar-current-build.json": (
        5_339,
        "6c7b84b59da58cd5bcce44bff041578b22a243279db9e836bb6ce54c610ce1eb",
    ),
    "sources/curated-official-2026-07-21-icatec-ica-current-build.json": (
        7_745,
        "8a87e5271914fc351ff01576661e9e5f315ab783489c44cf75144c03451fa4e6",
    ),
    "sources/curated-official-2026-07-21-lvrtc-pozitrons-kurzeme-current-build.json": (
        8_203,
        "8653286bdfc853918125e1294483e9175a339cc44705422d68a9bd4709d27d9b",
    ),
}

EXCLUDED_SOURCE_PATHS = frozenset(
    {
        "sources/curated-official-2026-07-21-cmc-creative-space-hanoi-phase-2-historical.json",
        "sources/curated-official-2026-07-21-bolivia-fiscalia-sucre-data-center.json",
    }
)
ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:akashi-astana-data-center-campus",
        "curated:akashi-astana-data-center-campus:phase-1-current-build",
        "curated:bichuten-chovar-data-center",
        "curated:bichuten-chovar-data-center:initial-container-build",
        "curated:icatec-ica-digital-transformation-data-center",
        "curated:icatec-ica-digital-transformation-data-center:four-storey-technology-center-build",
        "curated:lvrtc-pozitrons-kurzeme-data-center",
        "curated:lvrtc-pozitrons-kurzeme-data-center:phase-1-current-build",
    }
)
ADDED_PROJECT_KEYS = frozenset(key for key in ADDED_ENTITY_KEYS if key.count(":") >= 2)
ADDED_EVIDENCE_KEYS = frozenset(
    {
        "kazakhstan-akashi-astana-about-page-captured-2026-07-21",
        "kazakhstan-akashi-astana-current-progress-captured-2026-07-21",
        "latvia-lvrtc-pozitrons-progress-through-2026-06-30-captured-2026-07-21",
        "latvia-lvrtc-pozitrons-project-page-captured-2026-07-21",
        "nepal-bichuten-chovar-care-rating-april-2026-captured-2026-07-21",
        "peru-icatec-construction-progress-2026-04-07-captured-2026-07-21",
        "peru-icatec-structural-progress-2026-02-12-captured-2026-07-21",
    }
)
ADDED_SOURCE_FAMILIES = frozenset(
    {
        "akashi_data_center_project_pages",
        "care_ratings_nepal_releases",
        "lvrtc_pozitrons_project_pages",
        "peru_gob_pe_region_ica_news",
    }
)
LIFECYCLE_CONTRACT = frozenset(
    {
        (
            "curated:akashi-astana-data-center-campus:phase-1-current-build",
            "under_construction",
            "2026-07-21",
            "authoritative_physical_status_update",
        ),
        (
            "curated:bichuten-chovar-data-center:initial-container-build",
            "under_construction",
            "2026-03-31",
            "authoritative_physical_status_update",
        ),
        (
            "curated:icatec-ica-digital-transformation-data-center:four-storey-technology-center-build",
            "foundations",
            "2026-02-12",
            "authoritative_physical_status_update",
        ),
        (
            "curated:icatec-ica-digital-transformation-data-center:four-storey-technology-center-build",
            "under_construction",
            "2026-04-07",
            "authoritative_physical_status_update",
        ),
        (
            "curated:lvrtc-pozitrons-kurzeme-data-center:phase-1-current-build",
            "under_construction",
            "2026-06-30",
            "authoritative_physical_status_update",
        ),
    }
)
CAPACITY_CONTRACT = frozenset(
    {
        (
            "curated:akashi-astana-data-center-campus:phase-1-current-build",
            "critical_it_mw",
            "planned",
            "MW",
            5.28,
            "2026-07-21",
            "reported",
        ),
        (
            "curated:lvrtc-pozitrons-kurzeme-data-center:phase-1-current-build",
            "pue",
            "design",
            "ratio",
            1.4,
            "2026-07-02",
            "reported",
        ),
    }
)
OPERATING_MODEL_CONTRACT = frozenset(
    {
        (
            "curated:akashi-astana-data-center-campus:phase-1-current-build",
            "colocation",
            "2026-07-21",
        ),
        (
            "curated:bichuten-chovar-data-center:initial-container-build",
            "colocation",
            "2026-03-31",
        ),
        (
            "curated:lvrtc-pozitrons-kurzeme-data-center:phase-1-current-build",
            "colocation",
            "2026-07-02",
        ),
    }
)

FRESHNESS_README = f"""
Open seed v73 is the exact accepted v72 successor with only the four
seed-eligible source records from
`source_artifacts/global-official-builds-six-candidate-2026-07-21-v1`
appended. It preserves all 393 v72 inputs, then appends LVRTC Pozitrons,
Akashi Astana phase 1, Bichuten Chovar, and ICATEC Ica for 397 inputs total.
The frozen official-source manifest is `{OFFICIAL_MANIFEST_PIN[1]}` and its
physical tree is `{OFFICIAL_PHYSICAL_TREE_SHA256}`.

CMC Creative Space Hanoi remains historical-only and Bolivia remains
review-only without a captured source body; neither is selected. Akashi adds
only source-typed planned phase-1 critical IT load of 5.28 MW. Its dynamic
site-power ticker and untyped 100 MW dedicated-power statement are excluded.
Bichuten's unallocated 120 kW across two sites is excluded. LVRTC adds only
design PUE 1.4. No coordinate, geometry, workload, tenant, customer, user,
current load, consumption, annual energy, generation, or current-status claim
is inferred.

Lifecycle values remain dated last observations. `current_status_classification`
remains `unknown` and `current_construction_claim` remains `false`; even the
retrieval-day Akashi observation is not projected beyond its evidence date.
""".strip()


class OpenSeedV73Error(RuntimeError):
    """Raised when a v73 lineage, claim, or publication guard fails closed."""


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
        raise OpenSeedV73Error(f"expected ordinary JSON file: {path}")
    if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
        raise OpenSeedV73Error(f"file mode differs: {path}")
    raw = path.read_bytes()
    document = json.loads(raw)
    if raw != _canonical(document, sort_keys=sort_keys):
        raise OpenSeedV73Error(f"JSON is not canonical: {path}")
    return raw, document


def _validate_official_artifact() -> dict[str, Any]:
    artifact = OFFICIAL_ARTIFACT
    if (
        artifact.is_symlink()
        or not artifact.is_dir()
        or stat.S_IMODE(artifact.stat().st_mode) != 0o555
        or v69.tree_digest(artifact) != OFFICIAL_PHYSICAL_TREE_SHA256
    ):
        raise OpenSeedV73Error("official six-candidate artifact is not exact and frozen")
    if any(
        path.is_symlink()
        or stat.S_IMODE(path.stat().st_mode) != (0o555 if path.is_dir() else 0o444)
        for path in artifact.rglob("*")
    ):
        raise OpenSeedV73Error("official artifact member mode differs")
    manifest_raw, manifest = _read_json(artifact / "manifest.json", mode=0o444)
    if (len(manifest_raw), _sha256(manifest_raw)) != OFFICIAL_MANIFEST_PIN:
        raise OpenSeedV73Error("official artifact manifest pin differs")
    if (
        manifest.get("recorded_at") != OFFICIAL_RECORDED_AT
        or manifest.get("tree_sha256") != OFFICIAL_MANIFEST_TREE_SHA256
        or manifest.get("candidate_assessments") != 6
        or manifest.get("curated_source_records") != 5
        or manifest.get("seed_eligible_source_records") != 4
        or manifest.get("historical_only_source_records") != 1
        or manifest.get("review_only_candidates") != 1
        or manifest.get("raw_capture_redistributed") is not False
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or manifest.get("downstream_product_integration") != "none"
    ):
        raise OpenSeedV73Error("official artifact boundary differs")
    listed = manifest.get("files")
    if not isinstance(listed, list):
        raise OpenSeedV73Error("official artifact inventory differs")
    actual = {
        path.relative_to(artifact).as_posix()
        for path in artifact.rglob("*")
        if path.is_file()
    }
    expected = {row["path"] for row in listed} | {"manifest.json", "manifest.sha256"}
    if actual != expected or manifest.get("closed_file_set") != sorted(expected):
        raise OpenSeedV73Error("official artifact is not a closed file set")
    for row in listed:
        raw = (artifact / row["path"]).read_bytes()
        if (len(raw), _sha256(raw)) != (row["bytes"], row["sha256"]):
            raise OpenSeedV73Error(f"official artifact file pin differs: {row['path']}")
    if _sha256(_canonical(listed)) != OFFICIAL_MANIFEST_TREE_SHA256:
        raise OpenSeedV73Error("official artifact manifest tree differs")
    if (artifact / "manifest.sha256").read_text() != (
        f"{OFFICIAL_MANIFEST_PIN[1]}  manifest.json\n"
    ):
        raise OpenSeedV73Error("official artifact sidecar differs")

    snapshot_raw, snapshot = _read_json(artifact / "source-snapshot.json", mode=0o444)
    assessment_raw, assessment = _read_json(
        artifact / "candidate-assessment.json", mode=0o444
    )
    rights_raw, rights = _read_json(
        artifact / "rights-and-disposition.json", mode=0o444
    )
    if (len(snapshot_raw), _sha256(snapshot_raw)) != OFFICIAL_SNAPSHOT_PIN:
        raise OpenSeedV73Error("official source snapshot pin differs")
    if (len(assessment_raw), _sha256(assessment_raw)) != OFFICIAL_ASSESSMENT_PIN:
        raise OpenSeedV73Error("official assessment pin differs")
    if (len(rights_raw), _sha256(rights_raw)) != OFFICIAL_RIGHTS_PIN:
        raise OpenSeedV73Error("official rights pin differs")
    if (
        rights.get("raw_capture_redistributed") is not False
        or rights.get("artifact_is_hash_only") is not True
        or rights.get("temporary_capture_directory_moved_to_trash") is not True
        or rights.get("candidate_dispositions")
        != {
            "seed_eligible": 4,
            "historical_only": 1,
            "review_only_no_direct_capture": 1,
        }
    ):
        raise OpenSeedV73Error("official source-rights boundary differs")
    return {"manifest": manifest, "snapshot": snapshot, "assessment": assessment}


def _validate_additions(
    recorded_at: str, *, validation_wall_clock: datetime | None = None
) -> dict[str, dict[str, Any]]:
    if tuple(ADDITION_PINS) != tuple(sorted(ADDITION_PINS)) or len(ADDITION_PINS) != 4:
        raise OpenSeedV73Error("v73 requires exactly four canonical additions")
    carrier = _validate_official_artifact()
    target = v70.parse_utc(recorded_at, label="v73 recorded_at")
    wall = validation_wall_clock or datetime.now(UTC)
    if wall.tzinfo is None or target > wall.astimezone(UTC):
        raise OpenSeedV73Error("v73 recorded_at is later than validation wall clock")
    if v70.parse_utc(OFFICIAL_RECORDED_AT, label="official recorded_at") > target:
        raise OpenSeedV73Error("official artifact post-dates v73")

    snapshot = carrier["snapshot"]
    records = snapshot.get("source_records")
    if (
        snapshot.get("recorded_at") != OFFICIAL_RECORDED_AT
        or not isinstance(records, list)
        or len(records) != 5
        or snapshot.get("totals", {}).get("seed_eligible_source_records") != 4
        or snapshot.get("totals", {}).get("historical_only_source_records") != 1
        or snapshot.get("integration", {}).get("open_seed_successor_created") is not False
        or snapshot.get("integration", {}).get("reason")
        != "coordinate_v72_lane_has_priority"
        or snapshot.get("integration", {}).get("release_integration") != "none"
        or snapshot.get("integration", {}).get("downstream_product_integration")
        != "none"
    ):
        raise OpenSeedV73Error("official source-snapshot boundary differs")
    record_by_path = {row.get("path"): row for row in records}
    if len(record_by_path) != 5:
        raise OpenSeedV73Error("official source-snapshot paths collide")
    accepted_records = {
        path: row for path, row in record_by_path.items() if row.get("seed_eligible") is True
    }
    expected_records = {
        path: (pin[0], pin[1]) for path, pin in ADDITION_PINS.items()
    }
    if {
        path: (row.get("bytes"), row.get("sha256"))
        for path, row in accepted_records.items()
    } != expected_records or any(row.get("seeded") is not False for row in records):
        raise OpenSeedV73Error("official seed-eligible source inventory differs")
    cmc_path = next(
        path for path in EXCLUDED_SOURCE_PATHS if "cmc-creative-space" in path
    )
    if (
        set(record_by_path) != set(ADDITION_PINS) | {cmc_path}
        or record_by_path[cmc_path].get("disposition")
        != "historical_only_current_status_unknown"
        or record_by_path[cmc_path].get("seed_eligible") is not False
    ):
        raise OpenSeedV73Error("CMC historical-only exclusion differs")

    assessment = carrier["assessment"]
    candidates = {
        row.get("candidate_id"): row for row in assessment.get("candidates", [])
    }
    if (
        assessment.get("candidate_count") != 6
        or assessment.get("seed_eligible_count") != 4
        or assessment.get("historical_only_count") != 1
        or assessment.get("review_only_count") != 1
        or candidates.get("cmc-creative-space-hanoi-phase-2", {}).get("decision")
        != "historical_only_current_status_unknown"
        or candidates.get("bolivia-fiscalia-sucre-data-center", {}).get("decision")
        != "review_only_no_direct_capture"
        or candidates.get("bolivia-fiscalia-sucre-data-center", {}).get(
            "source_record_created"
        )
        is not False
        or candidates.get("bolivia-fiscalia-sucre-data-center", {}).get(
            "browser_context_not_evidence", {}
        ).get("used_for_normalized_claims")
        is not False
    ):
        raise OpenSeedV73Error("six-candidate disposition boundary differs")

    documents: dict[str, dict[str, Any]] = {}
    entities: dict[str, dict[str, Any]] = {}
    evidence: dict[str, dict[str, Any]] = {}
    lifecycle: set[tuple[str, str, str, str]] = set()
    capacities: set[tuple[str, str, str, str, float, str, str]] = set()
    operating_models: set[tuple[str, str, str]] = set()
    for relative, expected_pin in ADDITION_PINS.items():
        source = ROOT / relative
        raw, document = _read_json(source, mode=0o644)
        metadata = source.stat(follow_symlinks=False)
        if (len(raw), _sha256(raw)) != expected_pin:
            raise OpenSeedV73Error(f"v73 source byte pin differs: {relative}")
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV73Error(f"v73 source post-dates publication: {relative}")
        if document.get("schema_version") != "1.1":
            raise OpenSeedV73Error(f"v73 source schema differs: {relative}")
        documents[relative] = document
        for row in document.get("evidence", []):
            key = row.get("key")
            if key in evidence:
                raise OpenSeedV73Error(f"v73 duplicate evidence key: {key}")
            retrieved = v70.parse_utc(
                row.get("retrieved_at"), label=f"{relative} evidence retrieved_at"
            )
            if retrieved > target or retrieved > wall.astimezone(UTC):
                raise OpenSeedV73Error("v73 source evidence is future-dated")
            row_metadata = row.get("metadata", {})
            if (
                row_metadata.get("capture_artifact_id") != OFFICIAL_ARTIFACT.name
                or row_metadata.get("content_hash_verification")
                != "fetched_bytes_sha256"
                or row.get("license") != "all-rights-reserved"
            ):
                raise OpenSeedV73Error(f"v73 evidence lineage differs: {key}")
            evidence[key] = row
        for entity_name in ("campus", "project"):
            row = document.get(entity_name)
            if not isinstance(row, dict) or row.get("stable_key") in entities:
                raise OpenSeedV73Error(f"v73 entity inventory differs: {relative}")
            if row.get("coordinates") is not None or row.get("geometry") is not None:
                raise OpenSeedV73Error(f"v73 source gained coordinates: {relative}")
            entities[row["stable_key"]] = row
        for row in document.get("lifecycle", []):
            lifecycle.add(
                (
                    document[row["entity"]]["stable_key"],
                    row["value"],
                    row["as_of_date"],
                    row["method"],
                )
            )
        for row in document.get("capacities", []):
            capacities.add(
                (
                    document[row["entity"]]["stable_key"],
                    row["metric"],
                    row["stage"],
                    row["unit"],
                    float(row["base"]),
                    row["as_of_date"],
                    row["method"],
                )
            )
            if not float(row["low"]) == float(row["base"]) == float(row["high"]):
                raise OpenSeedV73Error("v73 source capacity range differs")
        for row in document.get("operating_models", []):
            operating_models.add(
                (
                    document[row["entity"]]["stable_key"],
                    row["value"],
                    row["as_of_date"],
                )
            )
        if document.get("workloads") != []:
            raise OpenSeedV73Error(f"v73 source gained a workload: {relative}")

    if set(entities) != ADDED_ENTITY_KEYS or set(evidence) != ADDED_EVIDENCE_KEYS:
        raise OpenSeedV73Error("v73 identity or evidence contract differs")
    if (
        lifecycle != LIFECYCLE_CONTRACT
        or capacities != CAPACITY_CONTRACT
        or operating_models != OPERATING_MODEL_CONTRACT
    ):
        raise OpenSeedV73Error("v73 lifecycle, capacity, or model contract differs")
    bichuten = documents[
        "sources/curated-official-2026-07-21-bichuten-chovar-current-build.json"
    ]
    akashi = documents[
        "sources/curated-official-2026-07-21-akashi-astana-phase-1-current-build.json"
    ]
    if bichuten["capacities"] != [] or [
        (row["metric"], row["stage"], row["unit"], row["base"])
        for row in akashi["capacities"]
    ] != [("critical_it_mw", "planned", "MW", 5.28)]:
        raise OpenSeedV73Error("v73 Bichuten or Akashi typed-capacity boundary differs")
    akashi_metadata = {
        row["key"]: row.get("metadata", {}) for row in akashi["evidence"]
    }
    if (
        akashi_metadata[
            "kazakhstan-akashi-astana-about-page-captured-2026-07-21"
        ].get("dedicated_power_dimension")
        != "not sufficiently typed"
        or "dynamic and excluded"
        not in akashi_metadata[
            "kazakhstan-akashi-astana-current-progress-captured-2026-07-21"
        ].get("capacity_scope", "")
        or "no Chovar capacity is normalized"
        not in bichuten["evidence"][0].get("metadata", {}).get(
            "capacity_guardrail", ""
        )
    ):
        raise OpenSeedV73Error("v73 explicit excluded-capacity guardrail differs")
    return documents


def _base_paths(base: Mapping[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for row in base["curated_inputs"]:
        path = ROOT / row["path"]
        if (
            path.is_symlink()
            or not path.is_file()
            or not stat.S_ISREG(path.stat().st_mode)
            or v69.sha256(path) != row["sha256"]
        ):
            raise OpenSeedV73Error(f"accepted v72 input pin differs: {row['path']}")
        paths.append(path)
    return paths


def selected_inputs(
    base: Mapping[str, Any],
    *,
    recorded_at: str,
    validation_wall_clock: datetime | None = None,
) -> tuple[list[dict[str, str]], list[Path]]:
    if base.get("release_id") != "2026-07-21-open-seed-v72":
        raise OpenSeedV73Error("v73 base must be exactly accepted v72")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 393:
        raise OpenSeedV73Error("accepted v72 curated inventory differs")
    if any(not isinstance(row, dict) or set(row) != {"path", "sha256"} for row in rows):
        raise OpenSeedV73Error("accepted v72 curated rows differ")
    base_names = [row["path"] for row in rows]
    if len(set(base_names)) != 393:
        raise OpenSeedV73Error("accepted v72 input paths collide")
    documents = _validate_additions(
        recorded_at, validation_wall_clock=validation_wall_clock
    )
    if set(base_names) & (set(ADDITION_PINS) | EXCLUDED_SOURCE_PATHS):
        raise OpenSeedV73Error("v72 already contains a six-candidate source")

    paths = _base_paths(base)
    base_entity_keys: set[str] = set()
    base_evidence_keys: set[str] = set()
    for path in paths:
        document = json.loads(path.read_text())
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
        raise OpenSeedV73Error("v73 addition collides with accepted v72 semantics")

    selected = [dict(row) for row in rows]
    for relative in sorted(ADDITION_PINS):
        selected.append({"path": relative, "sha256": ADDITION_PINS[relative][1]})
        paths.append(ROOT / relative)
    if (
        selected[:393] != rows
        or [row["path"] for row in selected[393:]] != sorted(documents)
        or len(selected) != 397
        or set(row["path"] for row in selected) & EXCLUDED_SOURCE_PATHS
    ):
        raise OpenSeedV73Error("v73 did not preserve v72 and append exactly four inputs")
    return selected, paths


def _guard_state() -> dict[str, Any]:
    _validate_official_artifact()
    return {
        "base_definition": (BASE_DEFINITION.stat().st_size, v69.sha256(BASE_DEFINITION)),
        "base_manifest": v69.sha256(BASE_RELEASE / "manifest.json"),
        "base_tree": v69.tree_digest(BASE_RELEASE),
        "official_manifest": (
            (OFFICIAL_ARTIFACT / "manifest.json").stat().st_size,
            v69.sha256(OFFICIAL_ARTIFACT / "manifest.json"),
        ),
        "official_tree": v69.tree_digest(OFFICIAL_ARTIFACT),
        "additions": {
            relative: ((ROOT / relative).stat().st_size, v69.sha256(ROOT / relative))
            for relative in ADDITION_PINS
        },
        "excluded": {
            relative: (
                ((ROOT / relative).stat().st_size, v69.sha256(ROOT / relative))
                if (ROOT / relative).is_file()
                else None
            )
            for relative in EXCLUDED_SOURCE_PATHS
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
        "entities": 818,
        "evidence": 643,
        "entity_snapshots": 838,
        "lifecycle_observations": 479,
        "capacity_estimates": 535,
        "operating_model_observations": 59,
        "workload_observations": 128,
    }
    actual_counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in expected_counts
    }
    if actual_counts != expected_counts:
        raise OpenSeedV73Error(f"v73 database counts differ: {actual_counts}")
    with tempfile.TemporaryDirectory(prefix="open-seed-v73-base-", dir="/private/tmp") as td:
        prior = v69._populate_database(
            base, _base_paths(base), Path(td) / "v72.sqlite", recorded_at=recorded_at
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
                    raise OpenSeedV73Error(f"v73 changed a prior database row: {table}")
            before_keys = {row[0] for row in prior.execute("SELECT stable_key FROM entities")}
            after_keys = {row[0] for row in connection.execute("SELECT stable_key FROM entities")}
            if after_keys - before_keys != ADDED_ENTITY_KEYS or before_keys - after_keys:
                raise OpenSeedV73Error("v73 database identity delta differs")
            before_evidence = set(v70._evidence_by_key(prior))
            after_evidence = set(v70._evidence_by_key(connection))
            if (
                after_evidence - before_evidence != ADDED_EVIDENCE_KEYS
                or before_evidence - after_evidence
            ):
                raise OpenSeedV73Error("v73 database evidence delta differs")
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
        raise OpenSeedV73Error("v73 entity-kind contract differs")

    lifecycle = {
        tuple(row)
        for row in connection.execute(
            f"""
            SELECT entities.stable_key, status, as_of_date, lifecycle_observations.method
            FROM lifecycle_observations
            JOIN entities ON entities.id = entity_id
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
            JOIN entities ON entities.id = entity_id
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
            JOIN entities ON entities.id = entity_id
            WHERE entities.stable_key IN ({placeholders})
            """,
            keys,
        )
    }
    if (
        lifecycle != LIFECYCLE_CONTRACT
        or capacities != CAPACITY_CONTRACT
        or models != OPERATING_MODEL_CONTRACT
    ):
        raise OpenSeedV73Error("v73 imported claim contract differs")
    if connection.execute(
        f"SELECT COUNT(*) FROM workload_observations WHERE entity_id IN "
        f"(SELECT id FROM entities WHERE stable_key IN ({placeholders}))",
        keys,
    ).fetchone()[0]:
        raise OpenSeedV73Error("v73 imported an unsupported workload")
    for stable_key, latitude, longitude, geometry in connection.execute(
        f"""
        SELECT entities.stable_key, latitude, longitude, geometry_json
        FROM entity_snapshots JOIN entities ON entities.id = entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        keys,
    ):
        if latitude is not None or longitude is not None or geometry not in {None, "null"}:
            raise OpenSeedV73Error(f"v73 imported unsupported coordinates: {stable_key}")


def _build_database(
    base: Mapping[str, Any],
    paths: list[Path],
    sqlite_path: Path,
    *,
    recorded_at: str,
) -> sqlite3.Connection:
    connection = v69._populate_database(base, paths, sqlite_path, recorded_at=recorded_at)
    try:
        _validate_database_contract(connection, base, recorded_at=recorded_at)
        return connection
    except Exception:
        connection.close()
        raise


def _augment_release(documents: Mapping[str, str]) -> dict[str, str]:
    output = dict(documents)
    freshness = build_freshness_csv(output["entities.csv"], as_of=AS_OF)
    output[FRESHNESS_FILENAME] = freshness
    output["README.md"] = output["README.md"].rstrip() + "\n\n" + FRESHNESS_README + "\n"
    manifest = json.loads(output["manifest.json"])
    manifest["files"]["README.md"] = {
        "bytes": len(output["README.md"].encode()),
        "sha256": _sha256(output["README.md"].encode()),
    }
    manifest["files"][FRESHNESS_FILENAME] = {
        "bytes": len(freshness.encode()),
        "sha256": _sha256(freshness.encode()),
    }
    manifest["current_status_inferred"] = False
    manifest["lifecycle_freshness_records"] = len(
        list(csv.DictReader(io.StringIO(freshness)))
    )
    manifest["lifecycle_status_semantics"] = "last_observed"
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
            raise OpenSeedV73Error("precreated v73 release stage must be empty")
    else:
        output.mkdir(parents=True, exist_ok=False)
    documents = build_release_documents(
        connection,
        as_of=AS_OF,
        recorded_at=recorded_at,
        publication_contract_version=4,
    )
    for filename, content in _augment_release(documents).items():
        path = output / filename
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content.encode())
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


CSV_DELTA_COUNT_CONTRACT = {
    "entities.csv": (810, 8, 0),
    "evidence.csv": (514, 6, 0),
    "capacity_estimates.csv": (532, 2, 0),
    "construction_pipeline.csv": (416, 4, 0),
    "construction_source_signals.csv": (318, 4, 0),
    "resolution_candidates.csv": (7, 0, 0),
    "lifecycle_freshness.csv": (458, 4, 0),
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
            raise OpenSeedV73Error(
                f"v73 public CSV delta differs: {filename}: {actual}"
            )

    before_entities = {
        row["stable_key"]: row for row in _csv_rows(BASE_RELEASE / "entities.csv")
    }
    after_entities = {
        row["stable_key"]: row for row in _csv_rows(stage / "entities.csv")
    }
    if set(after_entities) - set(before_entities) != ADDED_ENTITY_KEYS:
        raise OpenSeedV73Error("v73 public identity delta differs")
    if set(before_entities) - set(after_entities) or any(
        after_entities[key] != row for key, row in before_entities.items()
    ):
        raise OpenSeedV73Error("v73 changed an accepted v72 public entity")
    for stable_key in ADDED_ENTITY_KEYS:
        row = after_entities[stable_key]
        if row["latitude"] or row["longitude"] or row["geometry_json"] != "null":
            raise OpenSeedV73Error("v73 public addition gained coordinates")
        if row.get("workloads_json") != "[]":
            raise OpenSeedV73Error("v73 public addition gained a workload")

    before_evidence = {
        row["evidence_id"]: row for row in _csv_rows(BASE_RELEASE / "evidence.csv")
    }
    after_evidence = {
        row["evidence_id"]: row for row in _csv_rows(stage / "evidence.csv")
    }
    if set(before_evidence) - set(after_evidence) or any(
        after_evidence[key] != row for key, row in before_evidence.items()
    ):
        raise OpenSeedV73Error("v73 changed accepted v72 public evidence")
    added_evidence = [
        row for key, row in after_evidence.items() if key not in before_evidence
    ]
    if (
        len(added_evidence) != 6
        or {row["source_family"] for row in added_evidence} != ADDED_SOURCE_FAMILIES
        or {row["kind"] for row in added_evidence}
        != {"company_disclosure", "government_record"}
    ):
        raise OpenSeedV73Error("v73 public evidence projection differs")

    before_resolution = json.loads(
        (BASE_RELEASE / "resolution_candidates.json").read_text()
    )
    after_resolution = json.loads((stage / "resolution_candidates.json").read_text())
    if _normalize_timestamps(before_resolution, recorded_at) != _normalize_timestamps(
        after_resolution, recorded_at
    ):
        raise OpenSeedV73Error("v73 changed the resolution advisory")

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
        raise OpenSeedV73Error("v73 GeoJSON base preservation differs")
    if any(after_features[key]["geometry"] is not None for key in ADDED_ENTITY_KEYS):
        raise OpenSeedV73Error("v73 GeoJSON addition gained geometry")


def _validate_release_facts(stage: Path, *, recorded_at: str) -> None:
    summary = json.loads((stage / "summary.json").read_text())
    expected_summary = {
        "campuses_total": 431,
        "campuses_with_coordinates": 132,
        "capacity_estimates_current": 534,
        "construction_pipeline_records": 420,
        "construction_source_signals": 322,
        "entities_total": 818,
        "entities_with_coordinates": 192,
        "evidence_total": 643,
        "lifecycle_observations_current": 462,
        "projects_total": 387,
        "recorded_at": recorded_at,
    }
    if {key: summary.get(key) for key in expected_summary} != expected_summary:
        raise OpenSeedV73Error(
            f"v73 summary facts differ: "
            f"{ {key: summary.get(key) for key in expected_summary} }"
        )
    if summary.get("entities_by_status", {}).get("under_construction") != 313:
        raise OpenSeedV73Error("v73 last-observed status summary differs")
    if (
        summary.get("capacity_estimates_by_metric", {}).get("critical_it_mw") != 267
        or summary.get("capacity_estimates_by_metric", {}).get("pue") != 6
        or summary.get("capacity_estimates_by_stage", {}).get("planned") != 156
        or summary.get("capacity_estimates_by_stage", {}).get("design") != 18
    ):
        raise OpenSeedV73Error("v73 typed-capacity summary differs")

    manifest = json.loads((stage / "manifest.json").read_text())
    expected_manifest = {
        "entities": 818,
        "evidence_records": 520,
        "capacity_estimates": 534,
        "construction_pipeline_records": 420,
        "construction_source_signals": 322,
        "resolution_candidates": 7,
        "lifecycle_freshness_records": 462,
        "lifecycle_status_semantics": "last_observed",
        "current_status_inferred": False,
        "publication_contract_version": 4,
        "recorded_at": recorded_at,
    }
    if {key: manifest.get(key) for key in expected_manifest} != expected_manifest:
        raise OpenSeedV73Error("v73 release manifest facts differ")
    base_manifest = json.loads((BASE_RELEASE / "manifest.json").read_text())
    if (
        set(manifest["source_families"]) - set(base_manifest["source_families"])
        != ADDED_SOURCE_FAMILIES
        or set(base_manifest["source_families"]) - set(manifest["source_families"])
        or len(manifest["source_families"]) != 294
    ):
        raise OpenSeedV73Error("v73 public source-family delta differs")

    freshness = _csv_rows(stage / FRESHNESS_FILENAME)
    classes = Counter(row["freshness_class"] for row in freshness)
    by_key = {row["stable_key"]: row for row in freshness}
    if (
        len(freshness) != 462
        or tuple(freshness[0]) != FRESHNESS_FIELDS
        or classes
        != {
            "recent_0_90_days": 238,
            "aging_91_365_days": 194,
            "stale_over_365_days": 30,
        }
        or any(
            row["status_semantics"] != "last_observed"
            or row["current_status_classification"] != "unknown"
            or row["current_construction_claim"] != "false"
            for row in freshness
        )
    ):
        raise OpenSeedV73Error("v73 freshness/current-status boundary differs")
    expected_freshness = {
        "curated:akashi-astana-data-center-campus:phase-1-current-build": (
            "under_construction",
            "2026-07-21",
            "recent_0_90_days",
        ),
        "curated:bichuten-chovar-data-center:initial-container-build": (
            "under_construction",
            "2026-03-31",
            "aging_91_365_days",
        ),
        "curated:icatec-ica-digital-transformation-data-center:four-storey-technology-center-build": (
            "under_construction",
            "2026-04-07",
            "aging_91_365_days",
        ),
        "curated:lvrtc-pozitrons-kurzeme-data-center:phase-1-current-build": (
            "under_construction",
            "2026-06-30",
            "recent_0_90_days",
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
            raise OpenSeedV73Error(f"v73 source freshness differs: {stable_key}")

    added_entity_ids = {
        row["entity_id"]
        for row in _csv_rows(stage / "entities.csv")
        if row["stable_key"] in ADDED_ENTITY_KEYS
    }
    capacity_rows = [
        row
        for row in _csv_rows(stage / "capacity_estimates.csv")
        if row["entity_id"] in added_entity_ids
    ]
    projected_capacities = {
        (
            next(
                entity["stable_key"]
                for entity in _csv_rows(stage / "entities.csv")
                if entity["entity_id"] == row["entity_id"]
            ),
            row["metric"],
            row["stage"],
            row["unit"],
            float(row["base"]),
        )
        for row in capacity_rows
    }
    if projected_capacities != {
        (key, metric, stage_name, unit, base)
        for key, metric, stage_name, unit, base, _, _ in CAPACITY_CONTRACT
    }:
        raise OpenSeedV73Error("v73 public capacity boundary differs")

    readme = (stage / "README.md").read_text()
    for marker in (
        OFFICIAL_MANIFEST_PIN[1],
        OFFICIAL_PHYSICAL_TREE_SHA256,
        "CMC Creative Space Hanoi remains historical-only",
        "Bolivia remains",
        "5.28 MW",
        "untyped 100 MW",
        "120 kW",
        "No coordinate",
        "current_status_classification`\nremains `unknown",
        "current_construction_claim` remains `false",
    ):
        if marker not in readme:
            raise OpenSeedV73Error(f"v73 README guardrail differs: {marker}")
    if len(list(stage.iterdir())) != 14:
        raise OpenSeedV73Error("v73 release file inventory count differs")


def _validate_definition(
    document: Mapping[str, Any],
    base: Mapping[str, Any],
    *,
    validation_wall_clock: datetime,
) -> str:
    if set(document) != set(base) or document.get("release_id") != RELEASE_ID:
        raise OpenSeedV73Error("v73 definition identity or schema differs")
    build = document.get("build")
    if not isinstance(build, dict) or set(build) != {"as_of", "recorded_at"}:
        raise OpenSeedV73Error("v73 definition build carrier differs")
    if build["as_of"] != AS_OF:
        raise OpenSeedV73Error("v73 as_of differs")
    recorded = v70.parse_utc(build["recorded_at"], label="v73 recorded_at")
    if (
        validation_wall_clock.tzinfo is None
        or recorded > validation_wall_clock.astimezone(UTC)
    ):
        raise OpenSeedV73Error("v73 recorded_at is later than validation wall clock")
    for key in (
        "epoch_capture",
        "expected_epoch_result",
        "freshness_contract",
        "publication_contract_version",
        "schema_version",
        "scope",
    ):
        if document.get(key) != base.get(key):
            raise OpenSeedV73Error(f"v73 inherited definition field differs: {key}")
    return build["recorded_at"]


def _validate_publication_times(
    definition: Path,
    release: Path,
    *,
    recorded_at: str,
    require_live: bool,
) -> None:
    target = v70.parse_utc(recorded_at, label="v73 recorded_at")
    for path in (definition, release, *release.iterdir()):
        metadata = path.stat(follow_symlinks=False)
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV73Error(f"v73 staged inode post-dates recorded_at: {path.name}")
    if require_live:
        if datetime.now(UTC) < target:
            raise OpenSeedV73Error("v73 recorded_at is not live")
        for path in (definition, release):
            if path.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
                raise OpenSeedV73Error(
                    f"v73 final root ctime predates recorded_at: {path.name}"
                )


def validate_open_seed_v73(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
    require_live: bool = True,
) -> dict[str, Any]:
    if replay_count != 2:
        raise OpenSeedV73Error("v73 requires exactly two offline replays")
    wall = validation_wall_clock or datetime.now(UTC)
    guard = _guard_state()
    if guard["base_definition"] != BASE_DEFINITION_PIN:
        raise OpenSeedV73Error("accepted v72 definition pin differs")
    if (
        guard["base_manifest"] != BASE_MANIFEST_SHA256
        or guard["base_tree"] != BASE_TREE_SHA256
    ):
        raise OpenSeedV73Error("accepted v72 release pin differs")
    if guard["official_manifest"] != OFFICIAL_MANIFEST_PIN:
        raise OpenSeedV73Error("official artifact manifest pin differs")
    base = json.loads(BASE_DEFINITION.read_text())
    definition_raw, definition = _read_json(
        definition_path, mode=0o444, sort_keys=True
    )
    recorded_at = _validate_definition(definition, base, validation_wall_clock=wall)
    selected, paths = selected_inputs(
        base, recorded_at=recorded_at, validation_wall_clock=wall
    )
    if definition.get("curated_inputs") != selected:
        raise OpenSeedV73Error("v73 selected input inventory differs")
    if release_path.is_symlink() or not release_path.is_dir():
        raise OpenSeedV73Error("v73 release must be an ordinary directory")
    if require_frozen and stat.S_IMODE(release_path.stat().st_mode) != 0o555:
        raise OpenSeedV73Error("v73 release root is not frozen")
    release_files = {path.name: path for path in release_path.iterdir()}
    if any(path.is_symlink() or not path.is_file() for path in release_files.values()):
        raise OpenSeedV73Error("v73 release contains a non-file")
    if require_frozen and any(
        stat.S_IMODE(path.stat().st_mode) != 0o444 for path in release_files.values()
    ):
        raise OpenSeedV73Error("v73 release file is not frozen")
    manifest_raw, manifest = _read_json(
        release_path / "manifest.json", mode=0o444, sort_keys=True
    )
    if _sha256(manifest_raw) != definition["expected_release"].get(
        "manifest_sha256"
    ):
        raise OpenSeedV73Error("v73 manifest hash differs")
    expected_release = {
        key: value
        for key, value in definition["expected_release"].items()
        if key != "manifest_sha256"
    }
    if {key: value for key, value in manifest.items() if key != "files"} != expected_release:
        raise OpenSeedV73Error("v73 expected release facts differ")
    if set(release_files) != set(manifest["files"]) | {"manifest.json"}:
        raise OpenSeedV73Error("v73 release file inventory differs")
    for filename, pin in manifest["files"].items():
        raw = (release_path / filename).read_bytes()
        if (len(raw), _sha256(raw)) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV73Error(f"v73 release pin differs: {filename}")
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
        raise OpenSeedV73Error("v73 expected summary differs")

    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v73-replay-{replay + 1}-", dir="/private/tmp"
        ) as td:
            root = Path(td)
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
                raise OpenSeedV73Error("v73 replay file inventory differs")
            for filename, frozen in release_files.items():
                if (replay_release / filename).read_bytes() != frozen.read_bytes():
                    raise OpenSeedV73Error(f"v73 offline replay differs: {filename}")
    if _guard_state() != guard:
        raise OpenSeedV73Error("v73 validation mutated accepted inputs")
    return manifest


def _path_identity(path: Path, *, directory: bool) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    expected = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if not expected:
        raise OpenSeedV73Error(f"v73 stage type differs: {path}")
    return metadata.st_dev, metadata.st_ino


def _release_identities(root: Path) -> dict[str, tuple[int, int]]:
    return {path.name: _path_identity(path, directory=False) for path in root.iterdir()}


def _assert_release_identities(
    root: Path,
    root_identity: tuple[int, int],
    members: Mapping[str, tuple[int, int]],
) -> None:
    if _path_identity(root, directory=True) != root_identity:
        raise OpenSeedV73Error("v73 release stage root identity changed")
    if _release_identities(root) != dict(members):
        raise OpenSeedV73Error("v73 release stage member identity changed")


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
        raise OpenSeedV73Error("refusing substituted v73 definition cleanup")
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
        raise OpenSeedV73Error("active v73 publication lock exists") from error
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
                raise OpenSeedV73Error("refusing substituted v73 lock cleanup")
            PUBLICATION_LOCK.unlink()


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _require_absent(label: str) -> None:
    if DEFINITION.exists() or DEFINITION.is_symlink():
        raise OpenSeedV73Error(f"{label} v73 definition collision")
    if RELEASE.exists() or RELEASE.is_symlink():
        raise OpenSeedV73Error(f"{label} v73 release collision")


def _rollback_release(release_identity: tuple[int, int], release_stage: Path) -> None:
    if _path_identity(RELEASE, directory=True) != release_identity:
        raise OpenSeedV73Error("refusing rollback of substituted v73 release")
    if release_stage.exists() or release_stage.is_symlink():
        raise OpenSeedV73Error("v73 release rollback stage is occupied")
    v69.promote_noreplace(RELEASE, release_stage)


def build_open_seed_v73(recorded_at: str | None = None) -> dict[str, Any]:
    """Build and atomically publish the four-source official-build successor."""

    if (DEFINITION.exists() or DEFINITION.is_symlink()) and (
        RELEASE.exists() or RELEASE.is_symlink()
    ):
        manifest = validate_open_seed_v73()
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
        raise OpenSeedV73Error("partial v73 final-path collision")

    guard = _guard_state()
    if guard["base_definition"] != BASE_DEFINITION_PIN:
        raise OpenSeedV73Error("accepted v72 definition pin differs")
    if (
        guard["base_manifest"] != BASE_MANIFEST_SHA256
        or guard["base_tree"] != BASE_TREE_SHA256
    ):
        raise OpenSeedV73Error("accepted v72 release pin differs")
    target = (
        v70.parse_utc(recorded_at, label="v73 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise OpenSeedV73Error("v73 recorded_at must be future before staging")
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
                prefix="open-seed-v73-db-", dir="/private/tmp"
            ) as td:
                connection = _build_database(
                    base, paths, Path(td) / "atlas.sqlite", recorded_at=recorded_at
                )
                try:
                    _write_release(
                        connection,
                        release_stage,
                        recorded_at=recorded_at,
                        precreated=True,
                    )
                    summary = summarize(connection, as_of=AS_OF, recorded_at=recorded_at)
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
                raise OpenSeedV73Error("v73 definition stage identity changed")
            _assert_release_identities(
                release_stage, release_identity, release_members
            )
            if (
                definition_stage.read_bytes() != frozen_definition
                or v69.tree_digest(release_stage) != frozen_tree
            ):
                raise OpenSeedV73Error("v73 private stage changed while waiting")
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
                    error.add_note(f"v73 release rollback failed: {rollback_error}")
                raise
            manifest = validate_open_seed_v73(DEFINITION, RELEASE)
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
        raise OpenSeedV73Error("v73 build mutated accepted inputs")
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
    print(json.dumps(build_open_seed_v73(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
