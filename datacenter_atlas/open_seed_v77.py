"""Build the strict ten-source append-only successor to open seed v76."""

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
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v76.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v76"
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v77.json"
RELEASE_ID = "2026-07-21-open-seed-v77"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v77.lock"
AS_OF = "2026-07-21"

BASE_RECORDED_AT = "2026-07-21T16:17:09Z"
BASE_DEFINITION_PIN = (
    90_539,
    "2b6169aab475acd240025894bc0b46307e2c4bb1c041e9a1f4a9ae9ea38ae6d2",
)
BASE_MANIFEST_SHA256 = (
    "6d176800502f59f268d6ef1040e6701dc1d14e4f21f2d3ecbe8ec86cb4cf917b"
)
BASE_TREE_SHA256 = "44205d093451d221aea9cbc467a316c97a05a0dea9e0c635660aa411ed9f14ec"

OFFICIAL_ARTIFACT = (
    ROOT
    / "source_artifacts/global-official-builds-china-gap-2026-07-21-v1"
)
OFFICIAL_RECORDED_AT = "2026-07-21T16:09:40Z"
OFFICIAL_MANIFEST_PIN = (
    1_781,
    "6de9a1a2e0b05a1b4523d45cc10a9cba8ecb36c3893243bb789f9687c26c6db8",
)
OFFICIAL_MANIFEST_TREE_SHA256 = (
    "b0afbf095f99e55d223924c61feefe8a991ffcb91df7280fa6ef1821d2acaa48"
)
OFFICIAL_PHYSICAL_TREE_SHA256 = (
    "3d102335bee0f6d34ac4b6c07e8801ce8b05ca15ab6396f9a07744eaf1b408fc"
)
OFFICIAL_SNAPSHOT_PIN = (
    10_494,
    "47a888270f1f25de13a20e561bb8fa4322178b703d7394f86597784409db6346",
)
OFFICIAL_ASSESSMENT_PIN = (
    9_172,
    "a0ab737c353aad62774aaf1160cb437aebfc9bb97bcda2e046a198ffc7318fa7",
)
OFFICIAL_RIGHTS_PIN = (
    1_390,
    "a72d59ff28ea4b676156aed1dc9c71a49d955e812927f9d1798962790abc4f1a",
)

ADDITION_ORDER = (
    "sources/curated-official-2026-07-21-runze-chongqing-phase-2-p6-current-build.json",
    "sources/curated-official-2026-07-21-china-telecom-guizhou-b5-b6-current-build.json",
    "sources/curated-official-2026-07-21-baoji-digital-building-mobile-dc-current-build.json",
    "sources/curated-official-2026-07-21-digital-qinghai-telecom-phase-2-current-build.json",
    "sources/curated-official-2026-07-21-mobile-plateau-haidong-phase-2-current-build.json",
    "sources/curated-official-2026-07-21-zhipu-iflytek-haidong-ai-base-current-build.json",
    "sources/curated-official-2026-07-21-haidong-training-inference-ai-current-build.json",
    "sources/curated-official-2026-07-21-wuhu-longteng-ai-park-current-build.json",
    "sources/curated-official-2026-07-21-china-telecom-tongling-dated-build.json",
    "sources/curated-official-2026-07-21-runze-hong-kong-sandy-ridge-current-build.json",
)
ADDITION_PINS = {
    ADDITION_ORDER[0]: (
        3_979,
        "c773e6639f7e313d67e64ab19f95a8b643dcabbe87b29e247d2cf3e04cbc6bc2",
    ),
    ADDITION_ORDER[1]: (
        4_143,
        "5a01059d9352a79cfd5fd46c686d339125c110d179ecbfe49d3eda740d0d8d14",
    ),
    ADDITION_ORDER[2]: (
        3_535,
        "4103dfebb86ee5b22d39a09874708129ec5985e568ad552d86c2f9d234bd27a5",
    ),
    ADDITION_ORDER[3]: (
        4_048,
        "3fc30fdb279d8b812b74ce1a719d3ca8a46aa804c139ddda14c42ab6ce3fcfe1",
    ),
    ADDITION_ORDER[4]: (
        3_998,
        "7db2d1cbeb6b81ceb0f62e5e826acff0df90d8810ccd9d267862ed1b7a93ff0d",
    ),
    ADDITION_ORDER[5]: (
        4_090,
        "211f3a87d4f3db27234759f3f5211639eae0487d69125837a89cd93971cc2788",
    ),
    ADDITION_ORDER[6]: (
        4_070,
        "6a4cc0a34924e083a5d1e68015577143b0de7040d407551f1d82d4414f543fb0",
    ),
    ADDITION_ORDER[7]: (
        3_998,
        "13b769290b17bbd0b2fb61587ff207cb9bbae5b82c2494de3ab4a66f5a6dc05c",
    ),
    ADDITION_ORDER[8]: (
        4_104,
        "4861bd60429a24577eef9bb89f51035f2306c0249f061389a9a75c64e495b5de",
    ),
    ADDITION_ORDER[9]: (
        6_054,
        "f16529810f7d6043f1eb46c93892bd75bc99f776c1df0d941d4debbbf1e18de4",
    ),
}
EXCLUDED_SOURCE_PATHS: frozenset[str] = frozenset()

ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:runze-southwest-international-information-port-chongqing",
        "curated:runze-southwest-international-information-port-chongqing:phase-2-p6-power-center-build",
        "curated:china-telecom-cloud-computing-guizhou-information-park",
        "curated:china-telecom-cloud-computing-guizhou-information-park:phase-2-1-b5-b6-data-center-build",
        "curated:baoji-digital-building-china-mobile-data-center",
        "curated:baoji-digital-building-china-mobile-data-center:main-structure-build",
        "curated:china-telecom-digital-qinghai-green-big-data-center",
        "curated:china-telecom-digital-qinghai-green-big-data-center:phase-2-build",
        "curated:china-mobile-plateau-big-data-center-haidong",
        "curated:china-mobile-plateau-big-data-center-haidong:phase-2-build",
        "curated:zhipu-iflytek-haidong-ai-computing-base",
        "curated:zhipu-iflytek-haidong-ai-computing-base:source-grid-load-storage-integrated-build",
        "curated:qinghai-haidong-training-inference-integrated-ai-center",
        "curated:qinghai-haidong-training-inference-integrated-ai-center:current-build",
        "curated:wuhu-longteng-ai-computing-internet-industrial-park",
        "curated:wuhu-longteng-ai-computing-internet-industrial-park:current-build",
        "curated:china-telecom-tongling-ai-computing-center",
        "curated:china-telecom-tongling-ai-computing-center:data-center-and-site-infrastructure-build",
        "curated:runze-hong-kong-sandy-ridge-data-facility-cluster",
        "curated:runze-hong-kong-sandy-ridge-data-facility-cluster:initial-build",
    }
)
ADDED_PROJECT_KEYS = frozenset(key for key in ADDED_ENTITY_KEYS if key.count(":") >= 2)
ADDED_EVIDENCE_KEYS = frozenset(
    {
        "china-runze-chongqing-phase2-p6-shell-2026-04-01",
        "china-telecom-guizhou-park-b5-b6-shell-by-2026-04-22",
        "china-baoji-digital-building-mobile-dc-build-2026-07-15",
        "china-telecom-digital-qinghai-phase2-build-2026-06-23",
        "china-mobile-plateau-haidong-phase2-build-2026-06-23",
        "china-zhipu-iflytek-haidong-ai-base-build-2026-06-23",
        "china-haidong-training-inference-ai-center-build-2026-06-23",
        "china-wuhu-longteng-ai-internet-park-build-2026-02-26",
        "china-telecom-tongling-rainwater-site-build-2026-02-07",
        "hong-kong-runze-sandy-ridge-build-start-2026-03-28",
        "hong-kong-runze-sandy-ridge-physical-build-2026-05-20",
    }
)
ADDED_SOURCE_FAMILIES = frozenset(
    {
        "chongqing_jiulongpo_government_updates",
        "cscec_project_updates",
        "baoji_jintai_district_updates",
        "haidong_government_project_updates",
        "wuhu_government_project_updates",
        "tongling_housing_authority_records",
        "hong_kong_government_news",
        "xinhua_hong_kong_reports",
    }
)
PROJECTED_SOURCE_FAMILIES = ADDED_SOURCE_FAMILIES - {
    "hong_kong_government_news"
}
LIFECYCLE_CONTRACT = frozenset(
    {
        (
            "curated:runze-southwest-international-information-port-chongqing:phase-2-p6-power-center-build",
            "shell",
            "2026-04-01",
            "authoritative_physical_status_update",
        ),
        (
            "curated:china-telecom-cloud-computing-guizhou-information-park:phase-2-1-b5-b6-data-center-build",
            "shell",
            "2026-04-22",
            "authoritative_physical_status_update",
        ),
        (
            "curated:baoji-digital-building-china-mobile-data-center:main-structure-build",
            "under_construction",
            "2026-07-15",
            "authoritative_physical_status_update",
        ),
        (
            "curated:china-telecom-digital-qinghai-green-big-data-center:phase-2-build",
            "under_construction",
            "2026-06-23",
            "authoritative_physical_status_update",
        ),
        (
            "curated:china-mobile-plateau-big-data-center-haidong:phase-2-build",
            "under_construction",
            "2026-06-23",
            "authoritative_physical_status_update",
        ),
        (
            "curated:zhipu-iflytek-haidong-ai-computing-base:source-grid-load-storage-integrated-build",
            "under_construction",
            "2026-06-23",
            "authoritative_physical_status_update",
        ),
        (
            "curated:qinghai-haidong-training-inference-integrated-ai-center:current-build",
            "under_construction",
            "2026-06-23",
            "authoritative_physical_status_update",
        ),
        (
            "curated:wuhu-longteng-ai-computing-internet-industrial-park:current-build",
            "under_construction",
            "2026-02-26",
            "authoritative_physical_status_update",
        ),
        (
            "curated:china-telecom-tongling-ai-computing-center:data-center-and-site-infrastructure-build",
            "under_construction",
            "2026-02-07",
            "authoritative_physical_status_update",
        ),
        (
            "curated:runze-hong-kong-sandy-ridge-data-facility-cluster:initial-build",
            "under_construction",
            "2026-03-28",
            "authoritative_construction_start",
        ),
        (
            "curated:runze-hong-kong-sandy-ridge-data-facility-cluster:initial-build",
            "under_construction",
            "2026-05-20",
            "physical_observation",
        ),
    }
)
CAPACITY_CONTRACT: frozenset[tuple[object, ...]] = frozenset()
OPERATING_MODEL_CONTRACT: frozenset[tuple[str, str, str]] = frozenset()

FRESHNESS_README = f"""
Open seed v77 is the exact accepted v76 successor with only the ten
seed-eligible source records from
`source_artifacts/global-official-builds-china-gap-2026-07-21-v1`
appended in frozen artifact order. It preserves all 406 v76 inputs, then
appends Runze Chongqing phase two/P-6, Guizhou B5/B6, Baoji, four separately
named Haidong builds, Wuhu Longteng, Tongling, and Runze Hong Kong Sandy Ridge
for 416 inputs total.
The frozen official-source manifest is `{OFFICIAL_MANIFEST_PIN[1]}` and its
physical tree is `{OFFICIAL_PHYSICAL_TREE_SHA256}`.

Changle remains review-only because direct publisher bytes were unavailable
and contributes no source or lifecycle record. Guizhou is governed solely by
the direct CSCEC body; the China Telecom HTTP 412 incident contributes no
claim. Shared Haidong evidence remains four separately named project records.
No capacity, coordinate, geometry, classification, workload, operating-model,
current load, consumption, annual energy, generation, PUE, type, tenant, or
current-status claim is inferred.

Lifecycle values remain dated last observations. `current_status_classification`
remains `unknown` and `current_construction_claim` remains `false`.
""".strip()


class OpenSeedV77Error(RuntimeError):
    """Raised when a v77 lineage, claim, or publication guard fails closed."""


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
        raise OpenSeedV77Error(f"expected ordinary JSON file: {path}")
    if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
        raise OpenSeedV77Error(f"file mode differs: {path}")
    raw = path.read_bytes()
    document = json.loads(raw)
    if raw != _canonical(document, sort_keys=sort_keys):
        raise OpenSeedV77Error(f"JSON is not canonical: {path}")
    return raw, document


def _validate_official_artifact() -> dict[str, Any]:
    artifact = OFFICIAL_ARTIFACT
    if (
        artifact.is_symlink()
        or not artifact.is_dir()
        or stat.S_IMODE(artifact.stat().st_mode) != 0o555
        or v69.tree_digest(artifact) != OFFICIAL_PHYSICAL_TREE_SHA256
    ):
        raise OpenSeedV77Error("official China-gap artifact is not exact and frozen")
    if any(
        path.is_symlink()
        or stat.S_IMODE(path.stat().st_mode) != (0o555 if path.is_dir() else 0o444)
        for path in artifact.rglob("*")
    ):
        raise OpenSeedV77Error("official artifact member mode differs")
    manifest_raw, manifest = _read_json(artifact / "manifest.json", mode=0o444)
    if (len(manifest_raw), _sha256(manifest_raw)) != OFFICIAL_MANIFEST_PIN:
        raise OpenSeedV77Error("official artifact manifest pin differs")
    if (
        manifest.get("recorded_at") != OFFICIAL_RECORDED_AT
        or manifest.get("tree_sha256") != OFFICIAL_MANIFEST_TREE_SHA256
        or manifest.get("candidate_assessments") != 11
        or manifest.get("curated_source_records") != 10
        or manifest.get("seed_eligible_source_records") != 10
        or manifest.get("review_only_candidates") != 1
        or manifest.get("technical_incident_groups") != 2
        or manifest.get("raw_capture_redistributed") is not False
        or manifest.get("raw_capture_directory_moved_intact_to_trash") is not True
        or manifest.get("transformed_web_text_used_for_claims") is not False
        or manifest.get("search_snippets_used_for_claims") is not False
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or manifest.get("downstream_product_integration") != "none"
    ):
        raise OpenSeedV77Error("official artifact boundary differs")
    listed = manifest.get("files")
    if not isinstance(listed, list):
        raise OpenSeedV77Error("official artifact inventory differs")
    actual = {
        path.relative_to(artifact).as_posix()
        for path in artifact.rglob("*")
        if path.is_file()
    }
    expected = {row["path"] for row in listed} | {"manifest.json", "manifest.sha256"}
    if actual != expected or manifest.get("closed_file_set") != sorted(expected):
        raise OpenSeedV77Error("official artifact is not a closed file set")
    for row in listed:
        raw = (artifact / row["path"]).read_bytes()
        if (len(raw), _sha256(raw)) != (row["bytes"], row["sha256"]):
            raise OpenSeedV77Error(f"official artifact file pin differs: {row['path']}")
    if _sha256(_canonical(listed)) != OFFICIAL_MANIFEST_TREE_SHA256:
        raise OpenSeedV77Error("official artifact manifest tree differs")
    if (artifact / "manifest.sha256").read_text() != (
        f"{OFFICIAL_MANIFEST_PIN[1]}  manifest.json\n"
    ):
        raise OpenSeedV77Error("official artifact sidecar differs")
    artifact_recorded = v70.parse_utc(
        OFFICIAL_RECORDED_AT, label="official recorded_at"
    )
    if (
        artifact_recorded > datetime.now(UTC)
        or artifact.stat().st_ctime + 1e-6 < artifact_recorded.timestamp()
    ):
        raise OpenSeedV77Error("official artifact publication time differs")

    snapshot_raw, snapshot = _read_json(artifact / "source-snapshot.json", mode=0o444)
    assessment_raw, assessment = _read_json(
        artifact / "candidate-assessment.json", mode=0o444
    )
    rights_raw, rights = _read_json(
        artifact / "rights-and-disposition.json", mode=0o444
    )
    if (len(snapshot_raw), _sha256(snapshot_raw)) != OFFICIAL_SNAPSHOT_PIN:
        raise OpenSeedV77Error("official source snapshot pin differs")
    if (len(assessment_raw), _sha256(assessment_raw)) != OFFICIAL_ASSESSMENT_PIN:
        raise OpenSeedV77Error("official assessment pin differs")
    if (len(rights_raw), _sha256(rights_raw)) != OFFICIAL_RIGHTS_PIN:
        raise OpenSeedV77Error("official rights pin differs")
    if (
        rights.get("raw_capture_redistributed") is not False
        or rights.get("artifact_is_hash_only") is not True
        or rights.get("temporary_capture_directory_moved_to_trash") is not True
        or rights.get("candidate_dispositions")
        != {
            "seed_eligible": 10,
            "review_only_no_direct_publisher_capture": 1,
        }
        or rights.get("technical_incident_groups") != 2
        or rights.get("transformed_web_text_used_for_claims") is not False
        or rights.get("search_snippets_used_for_claims") is not False
    ):
        raise OpenSeedV77Error("official source-rights boundary differs")
    return {"manifest": manifest, "snapshot": snapshot, "assessment": assessment}


def _validate_additions(
    recorded_at: str, *, validation_wall_clock: datetime | None = None
) -> dict[str, dict[str, Any]]:
    if tuple(ADDITION_PINS) != ADDITION_ORDER or len(ADDITION_PINS) != 10:
        raise OpenSeedV77Error("v77 requires exactly ten ordered additions")
    carrier = _validate_official_artifact()
    target = v70.parse_utc(recorded_at, label="v77 recorded_at")
    wall = validation_wall_clock or datetime.now(UTC)
    if wall.tzinfo is None or target > wall.astimezone(UTC):
        raise OpenSeedV77Error("v77 recorded_at is later than validation wall clock")
    if v70.parse_utc(OFFICIAL_RECORDED_AT, label="official recorded_at") > target:
        raise OpenSeedV77Error("official artifact post-dates v77")

    snapshot = carrier["snapshot"]
    records = snapshot.get("source_records")
    if (
        snapshot.get("recorded_at") != OFFICIAL_RECORDED_AT
        or not isinstance(records, list)
        or len(records) != 10
        or snapshot.get("totals", {}).get("source_records") != 10
        or snapshot.get("totals", {}).get("seed_eligible_source_records") != 10
        or snapshot.get("totals", {}).get("review_only_candidates") != 1
        or snapshot.get("totals", {}).get("distinct_campuses") != 10
        or snapshot.get("totals", {}).get("projects") != 10
        or snapshot.get("totals", {}).get("entity_snapshots") != 20
        or snapshot.get("totals", {}).get("unique_evidence_records") != 11
        or snapshot.get("totals", {}).get("lifecycle_observations") != 11
        or snapshot.get("totals", {}).get("operating_model_observations") != 0
        or snapshot.get("totals", {}).get("workload_observations") != 0
        or snapshot.get("totals", {}).get("capacity_estimates") != 0
        or snapshot.get("totals", {}).get("coordinates_present") != 0
        or snapshot.get("totals", {}).get("geometry_present") != 0
        or snapshot.get("integration", {}).get("open_seed_successor_created") is not False
        or snapshot.get("integration", {}).get("release_integration") != "none"
        or snapshot.get("integration", {}).get("downstream_product_integration")
        != "none"
        or snapshot.get("publication_contract")
        != {
            "version": 1,
            "all_source_and_artifact_bytes_staged_before_recorded_at": True,
            "final_paths_absent_before_recorded_at": True,
            "publication_waited_until_recorded_at": True,
            "no_replace_promotion": True,
            "identity_checked_rollback_on_late_collision": True,
            "final_root_ctime_not_before_recorded_at": True,
            "source_file_mode": "0644",
            "artifact_directory_mode": "0555",
            "artifact_file_mode": "0444",
        }
    ):
        raise OpenSeedV77Error("official source-snapshot boundary differs")
    record_by_path = {row.get("path"): row for row in records}
    if len(record_by_path) != 10 or tuple(row.get("path") for row in records) != ADDITION_ORDER:
        raise OpenSeedV77Error("official source-snapshot paths collide")
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
        raise OpenSeedV77Error("official seed-eligible source inventory differs")
    if set(record_by_path) != set(ADDITION_PINS):
        raise OpenSeedV77Error("China-gap seed source inventory differs")

    assessment = carrier["assessment"]
    candidates = {
        row.get("candidate_id"): row for row in assessment.get("candidates", [])
    }
    if (
        assessment.get("candidate_count") != 11
        or assessment.get("seed_eligible_count") != 10
        or assessment.get("review_only_count") != 1
        or candidates.get(
            "changle-airport-free-trade-zone-ai-computing-center", {}
        ).get("decision")
        != "review_only_no_direct_publisher_capture"
        or candidates.get(
            "changle-airport-free-trade-zone-ai-computing-center", {}
        ).get("seed_eligible")
        is not False
        or sum(row.get("seed_eligible") is True for row in candidates.values()) != 10
    ):
        raise OpenSeedV77Error("China-gap disposition boundary differs")

    documents: dict[str, dict[str, Any]] = {}
    entities: dict[str, dict[str, Any]] = {}
    evidence: dict[str, dict[str, Any]] = {}
    lifecycle: set[tuple[str, str, str, str]] = set()
    capacities: set[tuple[str, str, str, str, float, str, str]] = set()
    operating_models: set[tuple[str, str, str]] = set()
    for relative in ADDITION_ORDER:
        expected_pin = ADDITION_PINS[relative]
        source = ROOT / relative
        raw, document = _read_json(source, mode=0o644)
        metadata = source.stat(follow_symlinks=False)
        if (len(raw), _sha256(raw)) != expected_pin:
            raise OpenSeedV77Error(f"v77 source byte pin differs: {relative}")
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV77Error(f"v77 source post-dates publication: {relative}")
        if document.get("schema_version") != "1.1":
            raise OpenSeedV77Error(f"v77 source schema differs: {relative}")
        documents[relative] = document
        for row in document.get("evidence", []):
            key = row.get("key")
            if key in evidence:
                raise OpenSeedV77Error(f"v77 duplicate evidence key: {key}")
            retrieved = v70.parse_utc(
                row.get("retrieved_at"), label=f"{relative} evidence retrieved_at"
            )
            if retrieved > target or retrieved > wall.astimezone(UTC):
                raise OpenSeedV77Error("v77 source evidence is future-dated")
            row_metadata = row.get("metadata", {})
            if (
                row_metadata.get("capture_artifact_id") != OFFICIAL_ARTIFACT.name
                or row_metadata.get("content_hash_verification")
                != "fetched_bytes_sha256"
                or row.get("license") != "all-rights-reserved"
            ):
                raise OpenSeedV77Error(f"v77 evidence lineage differs: {key}")
            evidence[key] = row
        for entity_name in ("campus", "project"):
            row = document.get(entity_name)
            if not isinstance(row, dict) or row.get("stable_key") in entities:
                raise OpenSeedV77Error(f"v77 entity inventory differs: {relative}")
            if set(row) != {
                "address",
                "as_of_date",
                "confidence",
                "coordinates",
                "country",
                "evidence_key",
                "geometry",
                "method",
                "name",
                "roles",
                "stable_key",
            } or set(row.get("roles", {})) - {"contractor", "developer", "owner"}:
                raise OpenSeedV77Error(
                    f"v77 entity classification or role boundary differs: {relative}"
                )
            if row.get("coordinates") is not None or row.get("geometry") is not None:
                raise OpenSeedV77Error(f"v77 source gained coordinates: {relative}")
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
                raise OpenSeedV77Error("v77 source capacity range differs")
        for row in document.get("operating_models", []):
            operating_models.add(
                (
                    document[row["entity"]]["stable_key"],
                    row["value"],
                    row["as_of_date"],
                )
            )
        if document.get("workloads") != []:
            raise OpenSeedV77Error(f"v77 source gained a workload: {relative}")

    if set(entities) != ADDED_ENTITY_KEYS or set(evidence) != ADDED_EVIDENCE_KEYS:
        raise OpenSeedV77Error("v77 identity or evidence contract differs")
    if (
        lifecycle != LIFECYCLE_CONTRACT
        or capacities != CAPACITY_CONTRACT
        or operating_models != OPERATING_MODEL_CONTRACT
    ):
        raise OpenSeedV77Error("v77 lifecycle, capacity, or model contract differs")
    guizhou = documents[ADDITION_ORDER[1]]
    haidong = [documents[ADDITION_ORDER[index]] for index in range(3, 7)]
    hong_kong = documents[ADDITION_ORDER[9]]
    guizhou_metadata = guizhou["evidence"][0]["metadata"]
    if (
        any(document["capacities"] for document in documents.values())
        or any(document["operating_models"] for document in documents.values())
        or any(document["workloads"] for document in documents.values())
        or "HTTP 412" not in guizhou_metadata.get("china_telecom_capture_scope", "")
        or "governed solely by the direct CSCEC body"
        not in guizhou_metadata.get("china_telecom_capture_scope", "")
        or {document["evidence"][0]["content_hash"] for document in haidong}
        != {"0c6f983f91c9f2804287c2cbd8420c6006af2f500cb2b265aebb1d1a4bb2c9ba"}
        or len(
            {
                document["evidence"][0]["metadata"].get(
                    "exact_project_name_as_reported"
                )
                for document in haidong
            }
        )
        != 4
        or hong_kong["evidence"][0]["metadata"].get("area_and_cost_guardrail")
        is None
        or hong_kong["evidence"][1]["metadata"].get(
            "site_area_square_metres_as_reported"
        )
        != 110000
        or any("changle" in relative for relative in ADDITION_ORDER)
    ):
        raise OpenSeedV77Error("v77 China claim guardrail differs")
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
            raise OpenSeedV77Error(f"accepted v76 input pin differs: {row['path']}")
        paths.append(path)
    return paths


def selected_inputs(
    base: Mapping[str, Any],
    *,
    recorded_at: str,
    validation_wall_clock: datetime | None = None,
) -> tuple[list[dict[str, str]], list[Path]]:
    if base.get("release_id") != "2026-07-21-open-seed-v76":
        raise OpenSeedV77Error("v77 base must be exactly accepted v76")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 406:
        raise OpenSeedV77Error("accepted v76 curated inventory differs")
    if any(not isinstance(row, dict) or set(row) != {"path", "sha256"} for row in rows):
        raise OpenSeedV77Error("accepted v76 curated rows differ")
    base_names = [row["path"] for row in rows]
    if len(set(base_names)) != 406:
        raise OpenSeedV77Error("accepted v76 input paths collide")
    documents = _validate_additions(
        recorded_at, validation_wall_clock=validation_wall_clock
    )
    if set(base_names) & (set(ADDITION_PINS) | EXCLUDED_SOURCE_PATHS):
        raise OpenSeedV77Error("v76 already contains a China-gap source")

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
        raise OpenSeedV77Error("v77 addition collides with accepted v76 semantics")

    selected = [dict(row) for row in rows]
    for relative in ADDITION_ORDER:
        selected.append({"path": relative, "sha256": ADDITION_PINS[relative][1]})
        paths.append(ROOT / relative)
    if (
        selected[:406] != rows
        or [row["path"] for row in selected[406:]] != list(ADDITION_ORDER)
        or tuple(documents) != ADDITION_ORDER
        or len(selected) != 416
        or set(row["path"] for row in selected) & EXCLUDED_SOURCE_PATHS
    ):
        raise OpenSeedV77Error("v77 did not preserve v76 and append exactly ten inputs")
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
        "entities": 856,
        "evidence": 677,
        "entity_snapshots": 876,
        "lifecycle_observations": 501,
        "capacity_estimates": 535,
        "operating_model_observations": 60,
        "workload_observations": 128,
    }
    actual_counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in expected_counts
    }
    if actual_counts != expected_counts:
        raise OpenSeedV77Error(f"v77 database counts differ: {actual_counts}")
    with tempfile.TemporaryDirectory(prefix="open-seed-v77-base-", dir="/private/tmp") as td:
        prior = v69._populate_database(
            base, _base_paths(base), Path(td) / "v76.sqlite", recorded_at=recorded_at
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
                    raise OpenSeedV77Error(f"v77 changed a prior database row: {table}")
            before_keys = {row[0] for row in prior.execute("SELECT stable_key FROM entities")}
            after_keys = {row[0] for row in connection.execute("SELECT stable_key FROM entities")}
            if after_keys - before_keys != ADDED_ENTITY_KEYS or before_keys - after_keys:
                raise OpenSeedV77Error("v77 database identity delta differs")
            before_evidence = set(v70._evidence_by_key(prior))
            after_evidence = set(v70._evidence_by_key(connection))
            if (
                after_evidence - before_evidence != ADDED_EVIDENCE_KEYS
                or before_evidence - after_evidence
            ):
                raise OpenSeedV77Error("v77 database evidence delta differs")
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
        raise OpenSeedV77Error("v77 entity-kind contract differs")

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
        raise OpenSeedV77Error("v77 imported claim contract differs")
    if connection.execute(
        f"SELECT COUNT(*) FROM workload_observations WHERE entity_id IN "
        f"(SELECT id FROM entities WHERE stable_key IN ({placeholders}))",
        keys,
    ).fetchone()[0]:
        raise OpenSeedV77Error("v77 imported an unsupported workload")
    for stable_key, latitude, longitude, geometry in connection.execute(
        f"""
        SELECT entities.stable_key, latitude, longitude, geometry_json
        FROM entity_snapshots JOIN entities ON entities.id = entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        keys,
    ):
        if latitude is not None or longitude is not None or geometry not in {None, "null"}:
            raise OpenSeedV77Error(f"v77 imported unsupported coordinates: {stable_key}")


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
            raise OpenSeedV77Error("precreated v77 release stage must be empty")
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
    "entities.csv": (836, 20, 0),
    "evidence.csv": (535, 10, 0),
    "capacity_estimates.csv": (534, 0, 0),
    "construction_pipeline.csv": (429, 10, 0),
    "construction_source_signals.csv": (331, 10, 0),
    "resolution_candidates.csv": (7, 0, 0),
    "lifecycle_freshness.csv": (471, 10, 0),
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
            raise OpenSeedV77Error(
                f"v77 public CSV delta differs: {filename}: {actual}"
            )

    before_entities = {
        row["stable_key"]: row for row in _csv_rows(BASE_RELEASE / "entities.csv")
    }
    after_entities = {
        row["stable_key"]: row for row in _csv_rows(stage / "entities.csv")
    }
    if set(after_entities) - set(before_entities) != ADDED_ENTITY_KEYS:
        raise OpenSeedV77Error("v77 public identity delta differs")
    if set(before_entities) - set(after_entities) or any(
        after_entities[key] != row for key, row in before_entities.items()
    ):
        raise OpenSeedV77Error("v77 changed an accepted v76 public entity")
    for stable_key in ADDED_ENTITY_KEYS:
        row = after_entities[stable_key]
        if row["latitude"] or row["longitude"] or row["geometry_json"] != "null":
            raise OpenSeedV77Error("v77 public addition gained coordinates")
        if row.get("workloads_json") != "[]":
            raise OpenSeedV77Error("v77 public addition gained a workload")
        if row.get("capacity_estimates_json") != "[]":
            raise OpenSeedV77Error("v77 public addition gained capacity")

    before_evidence = {
        row["evidence_id"]: row for row in _csv_rows(BASE_RELEASE / "evidence.csv")
    }
    after_evidence = {
        row["evidence_id"]: row for row in _csv_rows(stage / "evidence.csv")
    }
    if set(before_evidence) - set(after_evidence) or any(
        after_evidence[key] != row for key, row in before_evidence.items()
    ):
        raise OpenSeedV77Error("v77 changed accepted v76 public evidence")
    added_evidence = [
        row for key, row in after_evidence.items() if key not in before_evidence
    ]
    if (
        len(added_evidence) != 10
        or {row["source_family"] for row in added_evidence}
        != PROJECTED_SOURCE_FAMILIES
        or {row["kind"] for row in added_evidence}
        != {"company_disclosure", "government_record"}
    ):
        raise OpenSeedV77Error("v77 public evidence projection differs")

    before_pipeline = {
        row["stable_key"]: row
        for row in _csv_rows(BASE_RELEASE / "construction_pipeline.csv")
    }
    after_pipeline = {
        row["stable_key"]: row
        for row in _csv_rows(stage / "construction_pipeline.csv")
    }
    if (
        set(after_pipeline) - set(before_pipeline) != ADDED_PROJECT_KEYS
        or set(before_pipeline) - set(after_pipeline)
        or any(after_pipeline[key] != row for key, row in before_pipeline.items())
    ):
        raise OpenSeedV77Error("v77 construction-pipeline delta differs")
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
        or len(added_signals) != 10
        or {row["representative_stable_key"] for row in added_signals}
        != ADDED_PROJECT_KEYS
        or any(
            row["representative_latitude"] or row["representative_longitude"]
            for row in added_signals
        )
    ):
        raise OpenSeedV77Error("v77 construction-signal delta differs")

    before_resolution = json.loads(
        (BASE_RELEASE / "resolution_candidates.json").read_text()
    )
    after_resolution = json.loads((stage / "resolution_candidates.json").read_text())
    if _normalize_timestamps(before_resolution, recorded_at) != _normalize_timestamps(
        after_resolution, recorded_at
    ):
        raise OpenSeedV77Error("v77 changed the resolution advisory")
    for filename in (
        "capacity_estimates.csv",
        "resolution_candidates.csv",
        "resolution_candidates.json",
    ):
        if (stage / filename).read_bytes() != (BASE_RELEASE / filename).read_bytes():
            raise OpenSeedV77Error(f"v77 changed invariant release file: {filename}")

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
    added_sources = [
        json.loads(row) for row in after_source_rows - before_source_rows
    ]
    if (
        before_source_rows - after_source_rows
        or len(added_sources) != 10
        or {row["source_family"] for row in added_sources}
        != PROJECTED_SOURCE_FAMILIES
    ):
        raise OpenSeedV77Error("v77 source-input projection differs")

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
        raise OpenSeedV77Error("v77 GeoJSON base preservation differs")
    if any(after_features[key]["geometry"] is not None for key in ADDED_ENTITY_KEYS):
        raise OpenSeedV77Error("v77 GeoJSON addition gained geometry")


def _validate_release_facts(stage: Path, *, recorded_at: str) -> None:
    summary = json.loads((stage / "summary.json").read_text())
    expected_summary = {
        "campuses_total": 450,
        "campuses_with_coordinates": 135,
        "capacity_estimates_current": 534,
        "construction_pipeline_records": 439,
        "construction_source_signals": 341,
        "entities_total": 856,
        "entities_with_coordinates": 198,
        "evidence_total": 677,
        "lifecycle_observations_current": 481,
        "projects_total": 406,
        "recorded_at": recorded_at,
    }
    if {key: summary.get(key) for key in expected_summary} != expected_summary:
        raise OpenSeedV77Error(
            f"v77 summary facts differ: "
            f"{ {key: summary.get(key) for key in expected_summary} }"
        )
    if (
        summary.get("entities_by_status", {}).get("under_construction") != 330
        or summary.get("entities_by_status", {}).get("shell") != 30
    ):
        raise OpenSeedV77Error("v77 last-observed status summary differs")
    if (
        summary.get("capacity_estimates_by_metric", {}).get("critical_it_mw") != 267
        or summary.get("capacity_estimates_by_metric", {}).get("pue") != 6
        or summary.get("capacity_estimates_by_stage", {}).get("planned") != 156
        or summary.get("capacity_estimates_by_stage", {}).get("design") != 18
    ):
        raise OpenSeedV77Error("v77 typed-capacity summary differs")
    expected_summary_document = json.loads(
        (BASE_RELEASE / "summary.json").read_text()
    )
    expected_summary_document.update(
        {
            "campuses_total": 450,
            "construction_pipeline_records": 439,
            "construction_source_signals": 341,
            "entities_total": 856,
            "evidence_total": 677,
            "lifecycle_observations_current": 481,
            "projects_total": 406,
            "recorded_at": recorded_at,
        }
    )
    expected_summary_document["country_assignment_counts"]["not_evaluated"] = 856
    expected_summary_document["country_source_claims_by_method"][
        "source_explicit_country_tag"
    ] = 856
    expected_summary_document["country_source_tag_fallbacks"] = 856
    expected_summary_document["entities_by_country"].update(
        {"China": 37, "Hong Kong": 10}
    )
    expected_summary_document["entities_by_kind"] = {"campus": 450, "project": 406}
    expected_summary_document["entities_by_status"].update(
        {"shell": 30, "under_construction": 330}
    )
    expected_summary_document["evidence_by_kind"].update(
        {"company_disclosure": 490, "government_record": 109}
    )
    if summary != expected_summary_document:
        raise OpenSeedV77Error("v77 full summary delta differs")

    manifest = json.loads((stage / "manifest.json").read_text())
    expected_manifest = {
        "entities": 856,
        "evidence_records": 545,
        "capacity_estimates": 534,
        "construction_pipeline_records": 439,
        "construction_source_signals": 341,
        "resolution_candidates": 7,
        "lifecycle_freshness_records": 481,
        "lifecycle_status_semantics": "last_observed",
        "current_status_inferred": False,
        "publication_contract_version": 4,
        "recorded_at": recorded_at,
    }
    if {key: manifest.get(key) for key in expected_manifest} != expected_manifest:
        raise OpenSeedV77Error("v77 release manifest facts differ")
    base_manifest = json.loads((BASE_RELEASE / "manifest.json").read_text())
    if (
        set(manifest["source_families"]) - set(base_manifest["source_families"])
        != PROJECTED_SOURCE_FAMILIES
        or set(base_manifest["source_families"]) - set(manifest["source_families"])
        or len(manifest["source_families"]) != 315
    ):
        raise OpenSeedV77Error("v77 public source-family delta differs")
    expected_manifest_document = {
        key: value for key, value in base_manifest.items() if key != "files"
    }
    expected_manifest_document.update(
        {
            "entities": 856,
            "entities_by_kind": {"campus": 450, "project": 406},
            "evidence_records": 545,
            "construction_pipeline_records": 439,
            "construction_source_signals": 341,
            "lifecycle_freshness_records": 481,
            "recorded_at": recorded_at,
            "source_families": sorted(
                set(base_manifest["source_families"])
                | PROJECTED_SOURCE_FAMILIES
            ),
        }
    )
    if (
        {key: value for key, value in manifest.items() if key != "files"}
        != expected_manifest_document
    ):
        raise OpenSeedV77Error("v77 full manifest delta differs")

    freshness = _csv_rows(stage / FRESHNESS_FILENAME)
    classes = Counter(row["freshness_class"] for row in freshness)
    by_key = {row["stable_key"]: row for row in freshness}
    if (
        len(freshness) != 481
        or tuple(freshness[0]) != FRESHNESS_FIELDS
        or classes
        != {
            "recent_0_90_days": 249,
            "aging_91_365_days": 200,
            "stale_over_365_days": 32,
        }
        or any(
            row["status_semantics"] != "last_observed"
            or row["current_status_classification"] != "unknown"
            or row["current_construction_claim"] != "false"
            for row in freshness
        )
    ):
        raise OpenSeedV77Error("v77 freshness/current-status boundary differs")
    expected_freshness = {
        "curated:runze-southwest-international-information-port-chongqing:phase-2-p6-power-center-build": (
            "shell",
            "2026-04-01",
            "aging_91_365_days",
        ),
        "curated:china-telecom-cloud-computing-guizhou-information-park:phase-2-1-b5-b6-data-center-build": (
            "shell",
            "2026-04-22",
            "recent_0_90_days",
        ),
        "curated:baoji-digital-building-china-mobile-data-center:main-structure-build": (
            "under_construction",
            "2026-07-15",
            "recent_0_90_days",
        ),
        "curated:china-telecom-digital-qinghai-green-big-data-center:phase-2-build": (
            "under_construction",
            "2026-06-23",
            "recent_0_90_days",
        ),
        "curated:china-mobile-plateau-big-data-center-haidong:phase-2-build": (
            "under_construction",
            "2026-06-23",
            "recent_0_90_days",
        ),
        "curated:zhipu-iflytek-haidong-ai-computing-base:source-grid-load-storage-integrated-build": (
            "under_construction",
            "2026-06-23",
            "recent_0_90_days",
        ),
        "curated:qinghai-haidong-training-inference-integrated-ai-center:current-build": (
            "under_construction",
            "2026-06-23",
            "recent_0_90_days",
        ),
        "curated:wuhu-longteng-ai-computing-internet-industrial-park:current-build": (
            "under_construction",
            "2026-02-26",
            "aging_91_365_days",
        ),
        "curated:china-telecom-tongling-ai-computing-center:data-center-and-site-infrastructure-build": (
            "under_construction",
            "2026-02-07",
            "aging_91_365_days",
        ),
        "curated:runze-hong-kong-sandy-ridge-data-facility-cluster:initial-build": (
            "under_construction",
            "2026-05-20",
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
            raise OpenSeedV77Error(f"v77 source freshness differs: {stable_key}")

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
        raise OpenSeedV77Error("v77 public capacity boundary differs")

    readme = (stage / "README.md").read_text()
    for marker in (
        OFFICIAL_MANIFEST_PIN[1],
        OFFICIAL_PHYSICAL_TREE_SHA256,
        "Changle remains review-only",
        "direct publisher bytes were unavailable",
        "governed solely by",
        "China Telecom HTTP 412 incident",
        "Shared Haidong evidence remains four separately named project records",
        "No capacity, coordinate, geometry, classification, workload",
        "current_status_classification`\nremains `unknown",
        "current_construction_claim` remains `false",
    ):
        if marker not in readme:
            raise OpenSeedV77Error(f"v77 README guardrail differs: {marker}")
    if len(list(stage.iterdir())) != 14:
        raise OpenSeedV77Error("v77 release file inventory count differs")


def _validate_definition(
    document: Mapping[str, Any],
    base: Mapping[str, Any],
    *,
    validation_wall_clock: datetime,
) -> str:
    if set(document) != set(base) or document.get("release_id") != RELEASE_ID:
        raise OpenSeedV77Error("v77 definition identity or schema differs")
    build = document.get("build")
    if not isinstance(build, dict) or set(build) != {"as_of", "recorded_at"}:
        raise OpenSeedV77Error("v77 definition build carrier differs")
    if build["as_of"] != AS_OF:
        raise OpenSeedV77Error("v77 as_of differs")
    recorded = v70.parse_utc(build["recorded_at"], label="v77 recorded_at")
    if (
        validation_wall_clock.tzinfo is None
        or recorded > validation_wall_clock.astimezone(UTC)
    ):
        raise OpenSeedV77Error("v77 recorded_at is later than validation wall clock")
    for key in (
        "epoch_capture",
        "expected_epoch_result",
        "freshness_contract",
        "publication_contract_version",
        "schema_version",
        "scope",
    ):
        if document.get(key) != base.get(key):
            raise OpenSeedV77Error(f"v77 inherited definition field differs: {key}")
    return build["recorded_at"]


def _validate_publication_times(
    definition: Path,
    release: Path,
    *,
    recorded_at: str,
    require_live: bool,
) -> None:
    target = v70.parse_utc(recorded_at, label="v77 recorded_at")
    for path in (definition, release, *release.iterdir()):
        metadata = path.stat(follow_symlinks=False)
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV77Error(f"v77 staged inode post-dates recorded_at: {path.name}")
    if require_live:
        if datetime.now(UTC) < target:
            raise OpenSeedV77Error("v77 recorded_at is not live")
        for path in (definition, release):
            if path.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
                raise OpenSeedV77Error(
                    f"v77 final root ctime predates recorded_at: {path.name}"
                )


def validate_open_seed_v77(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
    require_live: bool = True,
) -> dict[str, Any]:
    if replay_count != 2:
        raise OpenSeedV77Error("v77 requires exactly two offline replays")
    wall = validation_wall_clock or datetime.now(UTC)
    guard = _guard_state()
    if guard["base_definition"] != BASE_DEFINITION_PIN:
        raise OpenSeedV77Error("accepted v76 definition pin differs")
    if (
        guard["base_manifest"] != BASE_MANIFEST_SHA256
        or guard["base_tree"] != BASE_TREE_SHA256
    ):
        raise OpenSeedV77Error("accepted v76 release pin differs")
    if guard["official_manifest"] != OFFICIAL_MANIFEST_PIN:
        raise OpenSeedV77Error("official artifact manifest pin differs")
    base = json.loads(BASE_DEFINITION.read_text())
    definition_raw, definition = _read_json(
        definition_path, mode=0o444, sort_keys=True
    )
    recorded_at = _validate_definition(definition, base, validation_wall_clock=wall)
    selected, paths = selected_inputs(
        base, recorded_at=recorded_at, validation_wall_clock=wall
    )
    if definition.get("curated_inputs") != selected:
        raise OpenSeedV77Error("v77 selected input inventory differs")
    if release_path.is_symlink() or not release_path.is_dir():
        raise OpenSeedV77Error("v77 release must be an ordinary directory")
    if require_frozen and stat.S_IMODE(release_path.stat().st_mode) != 0o555:
        raise OpenSeedV77Error("v77 release root is not frozen")
    release_files = {path.name: path for path in release_path.iterdir()}
    if any(path.is_symlink() or not path.is_file() for path in release_files.values()):
        raise OpenSeedV77Error("v77 release contains a non-file")
    if require_frozen and any(
        stat.S_IMODE(path.stat().st_mode) != 0o444 for path in release_files.values()
    ):
        raise OpenSeedV77Error("v77 release file is not frozen")
    manifest_raw, manifest = _read_json(
        release_path / "manifest.json", mode=0o444, sort_keys=True
    )
    if _sha256(manifest_raw) != definition["expected_release"].get(
        "manifest_sha256"
    ):
        raise OpenSeedV77Error("v77 manifest hash differs")
    expected_release = {
        key: value
        for key, value in definition["expected_release"].items()
        if key != "manifest_sha256"
    }
    if {key: value for key, value in manifest.items() if key != "files"} != expected_release:
        raise OpenSeedV77Error("v77 expected release facts differ")
    if set(release_files) != set(manifest["files"]) | {"manifest.json"}:
        raise OpenSeedV77Error("v77 release file inventory differs")
    for filename, pin in manifest["files"].items():
        raw = (release_path / filename).read_bytes()
        if (len(raw), _sha256(raw)) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV77Error(f"v77 release pin differs: {filename}")
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
        raise OpenSeedV77Error("v77 expected summary differs")

    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v77-replay-{replay + 1}-", dir="/private/tmp"
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
                raise OpenSeedV77Error("v77 replay file inventory differs")
            for filename, frozen in release_files.items():
                if (replay_release / filename).read_bytes() != frozen.read_bytes():
                    raise OpenSeedV77Error(f"v77 offline replay differs: {filename}")
    if _guard_state() != guard:
        raise OpenSeedV77Error("v77 validation mutated accepted inputs")
    return manifest


def _path_identity(path: Path, *, directory: bool) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    expected = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if not expected:
        raise OpenSeedV77Error(f"v77 stage type differs: {path}")
    return metadata.st_dev, metadata.st_ino


def _release_identities(root: Path) -> dict[str, tuple[int, int]]:
    return {path.name: _path_identity(path, directory=False) for path in root.iterdir()}


def _assert_release_identities(
    root: Path,
    root_identity: tuple[int, int],
    members: Mapping[str, tuple[int, int]],
) -> None:
    if _path_identity(root, directory=True) != root_identity:
        raise OpenSeedV77Error("v77 release stage root identity changed")
    if _release_identities(root) != dict(members):
        raise OpenSeedV77Error("v77 release stage member identity changed")


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
        raise OpenSeedV77Error("refusing substituted v77 definition cleanup")
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
        raise OpenSeedV77Error("active v77 publication lock exists") from error
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
                raise OpenSeedV77Error("refusing substituted v77 lock cleanup")
            PUBLICATION_LOCK.unlink()


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _require_absent(label: str) -> None:
    if DEFINITION.exists() or DEFINITION.is_symlink():
        raise OpenSeedV77Error(f"{label} v77 definition collision")
    if RELEASE.exists() or RELEASE.is_symlink():
        raise OpenSeedV77Error(f"{label} v77 release collision")


def _rollback_release(release_identity: tuple[int, int], release_stage: Path) -> None:
    if _path_identity(RELEASE, directory=True) != release_identity:
        raise OpenSeedV77Error("refusing rollback of substituted v77 release")
    if release_stage.exists() or release_stage.is_symlink():
        raise OpenSeedV77Error("v77 release rollback stage is occupied")
    v69.promote_noreplace(RELEASE, release_stage)


def build_open_seed_v77(recorded_at: str | None = None) -> dict[str, Any]:
    """Build and atomically publish the ten-source v76 successor."""

    if (DEFINITION.exists() or DEFINITION.is_symlink()) and (
        RELEASE.exists() or RELEASE.is_symlink()
    ):
        manifest = validate_open_seed_v77()
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
        raise OpenSeedV77Error("partial v77 final-path collision")

    guard = _guard_state()
    if guard["base_definition"] != BASE_DEFINITION_PIN:
        raise OpenSeedV77Error("accepted v76 definition pin differs")
    if (
        guard["base_manifest"] != BASE_MANIFEST_SHA256
        or guard["base_tree"] != BASE_TREE_SHA256
    ):
        raise OpenSeedV77Error("accepted v76 release pin differs")
    target = (
        v70.parse_utc(recorded_at, label="v77 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise OpenSeedV77Error("v77 recorded_at must be future before staging")
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
                prefix="open-seed-v77-db-", dir="/private/tmp"
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
                raise OpenSeedV77Error("v77 definition stage identity changed")
            _assert_release_identities(
                release_stage, release_identity, release_members
            )
            if (
                definition_stage.read_bytes() != frozen_definition
                or v69.tree_digest(release_stage) != frozen_tree
            ):
                raise OpenSeedV77Error("v77 private stage changed while waiting")
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
                    error.add_note(f"v77 release rollback failed: {rollback_error}")
                raise
            manifest = validate_open_seed_v77(DEFINITION, RELEASE)
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
        raise OpenSeedV77Error("v77 build mutated accepted inputs")
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
    print(json.dumps(build_open_seed_v77(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
