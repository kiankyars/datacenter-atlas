"""Build the strict five-source append-only successor to open seed v81."""

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
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v81.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v81"
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v82.json"
RELEASE_ID = "2026-07-21-open-seed-v82"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v82.lock"
AS_OF = "2026-07-21"

BASE_RECORDED_AT = "2026-07-21T17:13:30Z"
BASE_DEFINITION_PIN = (
    95_875,
    "f71ed7a189b6ba54d10bbed3353fb0baf680061bb3838771bbfd21fe4e6f066e",
)
BASE_MANIFEST_SHA256 = (
    "015c1758d9d6a44faf921fc4402dd5653c02dd96bb6a46ab3164aa83d183938d"
)
BASE_TREE_SHA256 = "50d98a2696119d722facbe3e0d017195b3251a147f0349f8ce96563c2fa84685"
BASE_ENTITIES_PIN = (
    936_051,
    "d36809beb711f4a3f739cb596e5c66995f692666df7136b89190ae7d7b786d25",
)

OFFICIAL_ARTIFACT = (
    ROOT
    / "source_artifacts/global-official-builds-cee-gap-2026-07-21-v1"
)
OFFICIAL_RECORDED_AT = "2026-07-21T17:18:25Z"
OFFICIAL_MANIFEST_PIN = (
    1_744,
    "13ffdc16826e4fc1caf75b3b9c97fe8f2176193247512992254bd8ae114bc4f9",
)
OFFICIAL_MANIFEST_TREE_SHA256 = (
    "cdbb23055c9380ae7d1e64048529e4476e4f222afe6d599c09c1f9dcb78fa14d"
)
OFFICIAL_PHYSICAL_TREE_SHA256 = (
    "e23ecade126ad455d9b2819b614c7b45574f099c419f73cf3457adbb7091e91e"
)
OFFICIAL_SNAPSHOT_PIN = (
    7_404,
    "39406b88e03e9e30d9bd91f9aeb979e16a6945cd561da63f45ec3a3021d37c70",
)
OFFICIAL_ASSESSMENT_PIN = (
    10_003,
    "0a5890b11b5b9b59bd353a1cbe9390941f36079cafa65f72351e700421e0dafd",
)
OFFICIAL_RIGHTS_PIN = (
    1_586,
    "d8bcb4d4769db10cd79a4ece47363e384305e7f654b243cfc117188d6015d1ea",
)

ADDITION_ORDER = (
    "sources/curated-official-2026-07-21-microsoft-ath04-spata-current-build.json",
    "sources/curated-official-2026-07-21-tet-dc7-salaspils-phase1-current-build.json",
    "sources/curated-official-2026-07-21-ten-brinke-spata-current-build.json",
    "sources/curated-official-2026-07-21-ast-janciems-shell-fit-out.json",
    "sources/curated-official-2026-07-21-serbia-state-dc-kragujevac-modules-3-4-operational.json",
)
ADDITION_PINS = {
    ADDITION_ORDER[0]: (
        8_386,
        "4368d6b67766cfdcddeeaf30cf7e70f4e82d1094ea8616952b0fa7a85bdc9c97",
    ),
    ADDITION_ORDER[1]: (
        6_455,
        "1ec21ecde6660e3ff62b469693fe277998b85fc892127ca15d9612981381a65f",
    ),
    ADDITION_ORDER[2]: (
        7_835,
        "feb7d0fb6fc9ef7da9fe06ab16177a75247b3220ffeba6572cf8dccebd61bed4",
    ),
    ADDITION_ORDER[3]: (
        4_296,
        "02b9f7c85d1a22ff4b290c01954adce2909295fd33517993496f4221fc61f206",
    ),
    ADDITION_ORDER[4]: (
        6_280,
        "36cccf1eaa107e1581879722438ca1f22e5c371ae77cbaeb8d0a9bc76b5d38f2",
    ),
}
EXCLUDED_ORDER: tuple[str, ...] = ()
EXCLUDED_SOURCE_PATHS = frozenset(EXCLUDED_ORDER)
EXCLUDED_SOURCE_PINS: dict[str, tuple[int, str]] = {}
REVIEW_ONLY_CANDIDATE_IDS = frozenset(
    {
        "data4-jawczyce",
        "atman-waw3",
        "wbs-lublewo-choczewo",
        "vantage-poland-current-build-screen",
        "clusterpower-romania",
        "hungary-unnamed-relative-expansion",
        "slovakia-bounded-screen",
        "pantheon-croatia",
        "radomir-bulgaria-nis-serbia",
        "ppc-kozani",
        "cyprus-regulatory-screen",
        "ixcellerate-mos7",
        "ixcellerate-mos11",
        "sunly-risti",
        "cra-prague",
        "pozitrons",
        "telia-vilnius",
        "data4-ath1",
        "arnes-maribor",
    }
)

ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:microsoft-ath04-spata-data-center",
        "curated:microsoft-ath04-spata-data-center:active-construction",
        "curated:tet-dc7-salaspils-data-center",
        "curated:tet-dc7-salaspils-data-center:phase-1-current-build",
        "curated:ten-brinke-spata-data-center",
        "curated:ten-brinke-spata-data-center:active-construction",
        "curated:ast-janciems-dispatcher-control-data-center",
        "curated:ast-janciems-dispatcher-control-data-center:fit-out-after-building-completion",
        "curated:serbia-state-data-center-kragujevac",
        "curated:serbia-state-data-center-kragujevac:modules-3-4-commissioned-2026",
    }
)
ADDED_PROJECT_KEYS = frozenset(key for key in ADDED_ENTITY_KEYS if key.count(":") >= 2)
ADDED_PIPELINE_PROJECT_KEYS = ADDED_PROJECT_KEYS - {
    "curated:serbia-state-data-center-kragujevac:modules-3-4-commissioned-2026"
}
ADDED_EVIDENCE_KEYS = frozenset(
    {
        "microsoft-ath04-renco-q1-2026-backlog-captured-2026-07-21",
        "microsoft-ath04-gek-terna-project-page-captured-2026-07-21",
        "microsoft-ath04-renco-project-page-captured-2026-07-21",
        "tet-dc7-citrus-project-page-captured-2026-07-21",
        "tet-dc7-enersense-salaspils-status-captured-2026-07-21",
        "ten-brinke-spata-current-project-captured-2026-07-21",
        "ppc-spata-current-development-indexed-2026-07-21",
        "ppc-data-in-scale-spata-launch-indexed-2026-07-21",
        "ast-janciems-building-complete-fitout-started-indexed-2026-07-21",
        "serbia-state-dc-kragujevac-modules-3-4-live-captured-2026-07-21",
    }
)
ADDED_SOURCE_FAMILIES = frozenset(
    {
        "renco_investor_reporting",
        "gek_terna_project_pages",
        "renco_project_pages",
        "citrus_solutions_project_pages",
        "enersense_press_releases",
        "ten_brinke_current_project_pages",
        "ppc_investor_presentations",
        "ppc_stock_news",
        "ast_official_events",
        "serbia_ite_government_news",
    }
)
PROJECTED_SOURCE_FAMILIES = frozenset(
    {
        "renco_investor_reporting",
        "gek_terna_project_pages",
        "citrus_solutions_project_pages",
        "ten_brinke_current_project_pages",
        "ast_official_events",
        "serbia_ite_government_news",
    }
)
PROJECTED_EVIDENCE_KEYS = frozenset(
    {
        "microsoft-ath04-renco-q1-2026-backlog-captured-2026-07-21",
        "microsoft-ath04-gek-terna-project-page-captured-2026-07-21",
        "tet-dc7-citrus-project-page-captured-2026-07-21",
        "ten-brinke-spata-current-project-captured-2026-07-21",
        "ast-janciems-building-complete-fitout-started-indexed-2026-07-21",
        "serbia-state-dc-kragujevac-modules-3-4-live-captured-2026-07-21",
    }
)
LIFECYCLE_CONTRACT = frozenset(
    {
        (
            "curated:microsoft-ath04-spata-data-center:active-construction",
            "under_construction",
            "2026-03-31",
            "authoritative_physical_status_update",
        ),
        (
            "curated:tet-dc7-salaspils-data-center:phase-1-current-build",
            "under_construction",
            "2026-03-12",
            "authoritative_physical_status_update",
        ),
        (
            "curated:ten-brinke-spata-data-center:active-construction",
            "under_construction",
            "2026-07-21",
            "authoritative_physical_status_update",
        ),
        (
            "curated:ast-janciems-dispatcher-control-data-center:fit-out-after-building-completion",
            "shell",
            "2026-06-27",
            "authoritative_physical_status_update",
        ),
        (
            "curated:serbia-state-data-center-kragujevac:modules-3-4-commissioned-2026",
            "operational",
            "2026-04-30",
            "authoritative_physical_status_update",
        ),
    }
)
CAPACITY_CONTRACT: frozenset[tuple[object, ...]] = frozenset(
    {
        (
            "curated:serbia-state-data-center-kragujevac:modules-3-4-commissioned-2026",
            "generation_nameplate_mw",
            "operational",
            "MW",
            0.3,
            "2026-04-30",
            "reported",
        ),
    }
)
OPERATING_MODEL_CONTRACT = frozenset(
    {
        (
            "curated:microsoft-ath04-spata-data-center:active-construction",
            "hyperscale_self_build",
            "2026-03-31",
        ),
        (
            "curated:serbia-state-data-center-kragujevac:modules-3-4-commissioned-2026",
            "sovereign_research",
            "2026-04-30",
        )
    }
)
WORKLOAD_CONTRACT: frozenset[tuple[str, str, str, str]] = frozenset(
    {
        (
            "curated:microsoft-ath04-spata-data-center:active-construction",
            "general_cloud",
            "2026-03-31",
            "company_disclosure",
        ),
        (
            "curated:serbia-state-data-center-kragujevac:modules-3-4-commissioned-2026",
            "ai_specialized_unspecified",
            "2026-04-30",
            "company_disclosure",
        ),
    }
)
COORDINATE_CONTRACT: dict[str, tuple[float, float]] = {}

ADDED_CANDIDATE_DECISIONS = {
    "curated:microsoft-ath04-spata-data-center:active-construction":
        "seed_eligible_current_under_construction",
    "curated:tet-dc7-salaspils-data-center:phase-1-current-build":
        "seed_eligible_current_under_construction",
    "curated:ten-brinke-spata-data-center:active-construction":
        "seed_eligible_current_under_construction_identity_unresolved_to_data_in_scale",
    "curated:ast-janciems-dispatcher-control-data-center:fit-out-after-building-completion":
        "seed_eligible_shell_fit_out_after_building_completion",
    "curated:serbia-state-data-center-kragujevac:modules-3-4-commissioned-2026":
        "seed_eligible_recent_operational_completion_not_current_construction",
}

UNVERIFIED_EVIDENCE_KEYS = frozenset(
    {
        "ppc-spata-current-development-indexed-2026-07-21",
        "ppc-data-in-scale-spata-launch-indexed-2026-07-21",
        "ast-janciems-building-complete-fitout-started-indexed-2026-07-21",
    }
)

FRESHNESS_README = f"""
Open seed v82 is the exact accepted v81 successor with only the five
seed-eligible source records from
`source_artifacts/global-official-builds-cee-gap-2026-07-21-v1`
appended in frozen artifact order. It preserves all 428 v81 inputs, then
appends Microsoft ATH04, Tet DC7, Ten Brinke Spata, AST Jāņciems, and Serbia
Kragujevac modules 3/4 for 433 inputs.
The frozen official-source manifest is `{OFFICIAL_MANIFEST_PIN[1]}` and its
physical tree is `{OFFICIAL_PHYSICAL_TREE_SHA256}`.

All 19 other carrier candidates remain review-only or already represented and
contribute no v82 input or claim. ATH04's 19.2 MW, Tet's 112 + 112 rack counts,
Data In Scale's 12.5/25 MW, and Serbia's 8/14 MW energy-capacity labels remain
narrative and are never normalized as data-center load. Serbia contributes only
0.3 MW of operational rooftop-solar generation. PPC evidence is resolution-only
and creates no Ten Brinke/Data In Scale identity, role, or capacity link; Serbia
modules 3/4 are not linked to the older planned Block 2. AST remains labelled
`unverified_assertion` even though the first-party page claim and address were
independently opened live. No coordinate, PUE, consumption, annual-energy,
current-load, or current-status claim is inferred.

Lifecycle values remain dated last observations. `current_status_classification`
remains `unknown` and `current_construction_claim` remains `false`.
""".strip()


class OpenSeedV82Error(RuntimeError):
    """Raised when a v82 lineage, claim, or publication guard fails closed."""


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
        raise OpenSeedV82Error(f"expected ordinary JSON file: {path}")
    if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
        raise OpenSeedV82Error(f"file mode differs: {path}")
    raw = path.read_bytes()
    document = json.loads(raw)
    if raw != _canonical(document, sort_keys=sort_keys):
        raise OpenSeedV82Error(f"JSON is not canonical: {path}")
    return raw, document


def _validate_official_artifact() -> dict[str, Any]:
    artifact = OFFICIAL_ARTIFACT
    if (
        artifact.is_symlink()
        or not artifact.is_dir()
        or stat.S_IMODE(artifact.stat().st_mode) != 0o555
        or v69.tree_digest(artifact) != OFFICIAL_PHYSICAL_TREE_SHA256
    ):
        raise OpenSeedV82Error("official CEE-gap artifact is not exact and frozen")
    if any(
        path.is_symlink()
        or stat.S_IMODE(path.stat().st_mode) != (0o555 if path.is_dir() else 0o444)
        for path in artifact.rglob("*")
    ):
        raise OpenSeedV82Error("official artifact member mode differs")
    manifest_raw, manifest = _read_json(artifact / "manifest.json", mode=0o444)
    if (len(manifest_raw), _sha256(manifest_raw)) != OFFICIAL_MANIFEST_PIN:
        raise OpenSeedV82Error("official artifact manifest pin differs")
    if (
        manifest.get("recorded_at") != OFFICIAL_RECORDED_AT
        or manifest.get("tree_sha256") != OFFICIAL_MANIFEST_TREE_SHA256
        or manifest.get("candidate_assessments") != 24
        or manifest.get("curated_source_records") != 5
        or manifest.get("seed_eligible_source_records") != 5
        or manifest.get("review_only_candidates") != 19
        or manifest.get("successful_http_200_body_captures") != 7
        or manifest.get("raw_capture_redistributed") is not False
        or manifest.get("raw_capture_directory_moved_intact_to_trash") is not True
        or manifest.get("regional_completeness_claimed") is not False
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or manifest.get("downstream_product_integration") != "none"
    ):
        raise OpenSeedV82Error("official artifact boundary differs")
    listed = manifest.get("files")
    if not isinstance(listed, list):
        raise OpenSeedV82Error("official artifact inventory differs")
    actual = {
        path.relative_to(artifact).as_posix()
        for path in artifact.rglob("*")
        if path.is_file()
    }
    expected = {row["path"] for row in listed} | {"manifest.json", "manifest.sha256"}
    if actual != expected or manifest.get("closed_file_set") != sorted(expected):
        raise OpenSeedV82Error("official artifact is not a closed file set")
    for row in listed:
        raw = (artifact / row["path"]).read_bytes()
        if (len(raw), _sha256(raw)) != (row["bytes"], row["sha256"]):
            raise OpenSeedV82Error(f"official artifact file pin differs: {row['path']}")
    if _sha256(_canonical(listed)) != OFFICIAL_MANIFEST_TREE_SHA256:
        raise OpenSeedV82Error("official artifact manifest tree differs")
    if (artifact / "manifest.sha256").read_text() != (
        f"{OFFICIAL_MANIFEST_PIN[1]}  manifest.json\n"
    ):
        raise OpenSeedV82Error("official artifact sidecar differs")
    artifact_recorded = v70.parse_utc(
        OFFICIAL_RECORDED_AT, label="official recorded_at"
    )
    if (
        artifact_recorded > datetime.now(UTC)
        or artifact.stat().st_ctime + 1e-6 < artifact_recorded.timestamp()
    ):
        raise OpenSeedV82Error("official artifact publication time differs")

    snapshot_raw, snapshot = _read_json(artifact / "source-snapshot.json", mode=0o444)
    assessment_raw, assessment = _read_json(
        artifact / "candidate-assessment.json", mode=0o444
    )
    rights_raw, rights = _read_json(
        artifact / "rights-and-disposition.json", mode=0o444
    )
    if (len(snapshot_raw), _sha256(snapshot_raw)) != OFFICIAL_SNAPSHOT_PIN:
        raise OpenSeedV82Error("official source snapshot pin differs")
    if (len(assessment_raw), _sha256(assessment_raw)) != OFFICIAL_ASSESSMENT_PIN:
        raise OpenSeedV82Error("official assessment pin differs")
    if (len(rights_raw), _sha256(rights_raw)) != OFFICIAL_RIGHTS_PIN:
        raise OpenSeedV82Error("official rights pin differs")
    if (
        rights.get("raw_capture_redistributed") is not False
        or rights.get("artifact_is_hash_and_fact_only") is not True
        or rights.get("temporary_capture_directory_moved_to_trash") is not True
        or rights.get("candidate_dispositions")
        != {
            "seed_eligible": 5,
            "review_only_or_already_covered": 19,
        }
        or rights.get("cc_by_nc_nd_3_0_serbia_source_count") != 1
        or rights.get("request_credentials_supplied") is not False
        or rights.get("raw_response_bodies_retained_in_artifact") is not False
        or rights.get("raw_response_headers_retained_in_artifact") is not False
        or rights.get("publisher_media_retained_in_artifact") is not False
    ):
        raise OpenSeedV82Error("official source-rights boundary differs")
    return {"manifest": manifest, "snapshot": snapshot, "assessment": assessment}


def _validate_additions(
    recorded_at: str, *, validation_wall_clock: datetime | None = None
) -> dict[str, dict[str, Any]]:
    if tuple(ADDITION_PINS) != ADDITION_ORDER or len(ADDITION_PINS) != 5:
        raise OpenSeedV82Error("v82 requires exactly five ordered additions")
    carrier = _validate_official_artifact()
    target = v70.parse_utc(recorded_at, label="v82 recorded_at")
    wall = validation_wall_clock or datetime.now(UTC)
    if wall.tzinfo is None or target > wall.astimezone(UTC):
        raise OpenSeedV82Error("v82 recorded_at is later than validation wall clock")
    if v70.parse_utc(OFFICIAL_RECORDED_AT, label="official recorded_at") > target:
        raise OpenSeedV82Error("official artifact post-dates v82")

    snapshot = carrier["snapshot"]
    records = snapshot.get("source_records")
    if (
        snapshot.get("recorded_at") != OFFICIAL_RECORDED_AT
        or not isinstance(records, list)
        or len(records) != 5
        or snapshot.get("totals", {}).get("candidate_assessments") != 24
        or snapshot.get("totals", {}).get("source_records") != 5
        or snapshot.get("totals", {}).get("seed_eligible_source_records") != 5
        or snapshot.get("totals", {}).get("review_only_candidates") != 19
        or snapshot.get("totals", {}).get("distinct_campuses") != 5
        or snapshot.get("totals", {}).get("projects") != 5
        or snapshot.get("totals", {}).get("entity_snapshots") != 10
        or snapshot.get("totals", {}).get("unique_evidence_records") != 10
        or snapshot.get("totals", {}).get("lifecycle_observations") != 5
        or snapshot.get("totals", {}).get("operating_model_observations") != 2
        or snapshot.get("totals", {}).get("workload_observations") != 2
        or snapshot.get("totals", {}).get("capacity_estimates") != 1
        or snapshot.get("totals", {}).get(
            "generation_nameplate_capacity_estimates"
        )
        != 1
        or snapshot.get("totals", {}).get("data_center_load_capacity_estimates")
        != 0
        or snapshot.get("totals", {}).get("coordinates_present") != 0
        or snapshot.get("totals", {}).get("geometry_present") != 0
        or snapshot.get("totals", {}).get("placement_observations") != 0
        or snapshot.get("totals", {}).get("energy_consumption_observations") != 0
        or snapshot.get("totals", {}).get("pue_observations") != 0
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
            "source_file_mode": "0444",
            "artifact_directory_mode": "0555",
            "artifact_file_mode": "0444",
        }
    ):
        raise OpenSeedV82Error("official source-snapshot boundary differs")
    record_by_path = {row.get("path"): row for row in records}
    expected_record_order = (*ADDITION_ORDER, *EXCLUDED_ORDER)
    if (
        len(record_by_path) != 5
        or tuple(row.get("path") for row in records) != expected_record_order
    ):
        raise OpenSeedV82Error("official source-snapshot paths collide")
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
        raise OpenSeedV82Error("official seed-eligible source inventory differs")
    excluded_records = {
        path: row for path, row in record_by_path.items() if path in EXCLUDED_SOURCE_PATHS
    }
    if (
        {
            path: (row.get("bytes"), row.get("sha256"))
            for path, row in excluded_records.items()
        }
        != EXCLUDED_SOURCE_PINS
        or any(row.get("seed_eligible") is not False for row in excluded_records.values())
        or set(record_by_path) != set(ADDITION_PINS) | EXCLUDED_SOURCE_PATHS
    ):
        raise OpenSeedV82Error("CEE source inventory differs")

    assessment = carrier["assessment"]
    candidates = {
        row.get("candidate_id"): row for row in assessment.get("candidates", [])
    }
    if (
        assessment.get("candidate_count") != 24
        or assessment.get("seed_eligible_count") != 5
        or assessment.get("review_only_count") != 19
        or set(candidates) != ADDED_PROJECT_KEYS | REVIEW_ONLY_CANDIDATE_IDS
        or any(
            candidates[key].get("decision") != ADDED_CANDIDATE_DECISIONS[key]
            or candidates[key].get("seed_eligible") is not True
            or candidates[key].get("source_record_created") is not True
            for key in ADDED_PROJECT_KEYS
        )
        or any(
            candidates[key].get("seed_eligible") is not False
            or candidates[key].get("source_record_created") is not False
            or candidates[key].get("normalized_claims_created") != 0
            for key in REVIEW_ONLY_CANDIDATE_IDS
        )
        or sum(row.get("seed_eligible") is True for row in candidates.values()) != 5
    ):
        raise OpenSeedV82Error("CEE disposition boundary differs")

    documents: dict[str, dict[str, Any]] = {}
    entities: dict[str, dict[str, Any]] = {}
    evidence: dict[str, dict[str, Any]] = {}
    lifecycle: set[tuple[str, str, str, str]] = set()
    capacities: set[tuple[str, str, str, str, float, str, str]] = set()
    operating_models: set[tuple[str, str, str]] = set()
    workloads: set[tuple[str, str, str, str]] = set()
    for relative, expected_pin in EXCLUDED_SOURCE_PINS.items():
        excluded_path = ROOT / relative
        raw, excluded_document = _read_json(excluded_path, mode=0o644)
        metadata = excluded_path.stat(follow_symlinks=False)
        if (len(raw), _sha256(raw)) != expected_pin:
            raise OpenSeedV82Error(f"v82 excluded source byte pin differs: {relative}")
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV82Error(f"v82 excluded source post-dates publication: {relative}")
        if (
            excluded_document.get("schema_version") != "1.1"
            or excluded_document.get("lifecycle") != []
            or excluded_document.get("capacities") != []
            or excluded_document.get("workloads") != []
            or excluded_document.get("operating_models") != []
        ):
            raise OpenSeedV82Error("v82 review-only source gained a normalized claim")
    for relative in ADDITION_ORDER:
        expected_pin = ADDITION_PINS[relative]
        source = ROOT / relative
        raw, document = _read_json(source, mode=0o444)
        metadata = source.stat(follow_symlinks=False)
        if (len(raw), _sha256(raw)) != expected_pin:
            raise OpenSeedV82Error(f"v82 source byte pin differs: {relative}")
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV82Error(f"v82 source post-dates publication: {relative}")
        if document.get("schema_version") != "1.1":
            raise OpenSeedV82Error(f"v82 source schema differs: {relative}")
        documents[relative] = document
        for row in document.get("evidence", []):
            key = row.get("key")
            if key in evidence:
                raise OpenSeedV82Error(f"v82 duplicate evidence key: {key}")
            retrieved = v70.parse_utc(
                row.get("retrieved_at"), label=f"{relative} evidence retrieved_at"
            )
            if retrieved > target or retrieved > wall.astimezone(UTC):
                raise OpenSeedV82Error("v82 source evidence is future-dated")
            row_metadata = row.get("metadata", {})
            expected_verification = (
                "unverified_assertion"
                if key in UNVERIFIED_EVIDENCE_KEYS
                else "fetched_bytes_sha256"
            )
            expected_license = (
                "Creative Commons Attribution-NonCommercial-NoDerivatives 3.0 "
                "Serbia (CC BY-NC-ND 3.0 RS)"
                if key
                == "serbia-state-dc-kragujevac-modules-3-4-live-captured-2026-07-21"
                else "all-rights-reserved"
            )
            if (
                row_metadata.get("capture_artifact_id") != OFFICIAL_ARTIFACT.name
                or row_metadata.get("content_hash_verification")
                != expected_verification
                or row.get("license") != expected_license
                or (
                    key in UNVERIFIED_EVIDENCE_KEYS
                    and (
                        row_metadata.get("capture_method")
                        != "indexed_official_page_fallback_after_direct_fetch_block"
                        or row_metadata.get("direct_response_claim_bearing") is not False
                    )
                )
                or (
                    key not in UNVERIFIED_EVIDENCE_KEYS
                    and row_metadata.get("capture_method")
                    != "credential_free_curl_location_compressed"
                )
            ):
                raise OpenSeedV82Error(f"v82 evidence lineage differs: {key}")
            evidence[key] = row
        for entity_name in ("campus", "project"):
            row = document.get(entity_name)
            if not isinstance(row, dict) or row.get("stable_key") in entities:
                raise OpenSeedV82Error(f"v82 entity inventory differs: {relative}")
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
            } or set(row.get("roles", {})) - {
                "contractor",
                "developer",
                "operator",
                "owner",
                "user",
            }:
                raise OpenSeedV82Error(
                    f"v82 entity classification or role boundary differs: {relative}"
                )
            stable_key = row["stable_key"]
            expected_point = COORDINATE_CONTRACT.get(stable_key)
            if expected_point is None:
                if row.get("coordinates") is not None or row.get("geometry") is not None:
                    raise OpenSeedV82Error(
                        f"v82 source gained unsupported coordinates: {relative}"
                    )
            elif (
                row.get("coordinates")
                != {"latitude": expected_point[0], "longitude": expected_point[1]}
                or row.get("geometry")
                != {
                    "type": "Point",
                    "coordinates": [expected_point[1], expected_point[0]],
                }
                or row.get("method") != "authoritative_site_plan"
            ):
                raise OpenSeedV82Error(f"v82 official coordinate differs: {relative}")
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
                raise OpenSeedV82Error("v82 source capacity range differs")
        for row in document.get("operating_models", []):
            operating_models.add(
                (
                    document[row["entity"]]["stable_key"],
                    row["value"],
                    row["as_of_date"],
                )
            )
        for row in document.get("workloads", []):
            workloads.add(
                (
                    document[row["entity"]]["stable_key"],
                    row["value"],
                    row["as_of_date"],
                    row["method"],
                )
            )

    if (
        set(entities) != ADDED_ENTITY_KEYS
        or set(evidence) != ADDED_EVIDENCE_KEYS
        or {row["source_family"] for row in evidence.values()}
        != ADDED_SOURCE_FAMILIES
    ):
        raise OpenSeedV82Error("v82 identity or evidence contract differs")
    if (
        lifecycle != LIFECYCLE_CONTRACT
        or capacities != CAPACITY_CONTRACT
        or operating_models != OPERATING_MODEL_CONTRACT
        or workloads != WORKLOAD_CONTRACT
    ):
        raise OpenSeedV82Error(
            "v82 lifecycle, capacity, model, or workload contract differs"
        )
    microsoft = documents[ADDITION_ORDER[0]]
    tet = documents[ADDITION_ORDER[1]]
    ten_brinke = documents[ADDITION_ORDER[2]]
    ast = documents[ADDITION_ORDER[3]]
    serbia = documents[ADDITION_ORDER[4]]
    if (
        sum(len(document["capacities"]) for document in documents.values()) != 1
        or sum(len(document["operating_models"]) for document in documents.values())
        != 2
        or sum(len(document["workloads"]) for document in documents.values()) != 2
        or microsoft["capacities"] != []
        or microsoft["evidence"][1]["metadata"].get(
            "reported_total_installed_capacity_mw"
        )
        != 19.2
        or microsoft["operating_models"][0].get("value")
        != "hyperscale_self_build"
        or microsoft["workloads"][0].get("value") != "general_cloud"
        or tet["capacities"] != []
        or tet["operating_models"] != []
        or tet["workloads"] != []
        or tet["evidence"][0]["metadata"].get("phase_1_racks_as_reported") != 112
        or tet["evidence"][0]["metadata"].get(
            "phase_2_additional_racks_as_reported"
        )
        != 112
        or ten_brinke["capacities"] != []
        or ten_brinke["operating_models"] != []
        or ten_brinke["workloads"] != []
        or ten_brinke["evidence"][1]["metadata"].get(
            "resolution_candidate_stable_key"
        )
        != "curated:data-in-scale-spata-campus:phase-1-current-build"
        or not str(
            ten_brinke["evidence"][1]["metadata"].get(
                "resolution_candidate_only"
            )
        ).startswith("This record does not assert")
        or ten_brinke["evidence"][2]["metadata"].get("resolution_candidate_only")
        is not True
        or ten_brinke["evidence"][2]["metadata"].get("identity_link_asserted")
        is not False
        or ten_brinke["evidence"][2]["metadata"].get("role_link_asserted")
        is not False
        or ten_brinke["evidence"][2]["metadata"].get("capacity_rows_created") != 0
        or any(
            marker in json.dumps(ten_brinke[name]["roles"], ensure_ascii=False)
            for marker in ("PPC", "Data In Scale", "EDGNEX")
            for name in ("campus", "project")
        )
        or ast["capacities"] != []
        or ast["operating_models"] != []
        or ast["workloads"] != []
        or ast["evidence"][0]["metadata"].get("content_hash_verification")
        != "unverified_assertion"
        or ast["evidence"][0]["metadata"].get("independent_live_page_open_verification", {}).get(
            "source_byte_hash_claimed"
        )
        is not False
        or serbia["capacities"][0].get("entity") != "project"
        or serbia["capacities"][0].get("metric") != "generation_nameplate_mw"
        or serbia["capacities"][0].get("stage") != "operational"
        or float(serbia["capacities"][0].get("base")) != 0.3
        or serbia["evidence"][0]["metadata"].get(
            "reported_module_energy_capacity_mw"
        )
        != 8
        or serbia["evidence"][0]["metadata"].get(
            "reported_total_energy_capacity_mw"
        )
        != 14
        or serbia["evidence"][0]["metadata"].get(
            "prior_discovery_reconciliation", {}
        ).get("block_2_identity_asserted")
        is not False
        or serbia["operating_models"][0].get("value") != "sovereign_research"
        or serbia["workloads"][0].get("value")
        != "ai_specialized_unspecified"
        or any(
            document[name].get("coordinates") is not None
            or document[name].get("geometry") is not None
            for document in documents.values()
            for name in ("campus", "project")
        )
    ):
        raise OpenSeedV82Error("v82 CEE claim guardrail differs")
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
            raise OpenSeedV82Error(f"accepted v81 input pin differs: {row['path']}")
        paths.append(path)
    return paths


def selected_inputs(
    base: Mapping[str, Any],
    *,
    recorded_at: str,
    validation_wall_clock: datetime | None = None,
) -> tuple[list[dict[str, str]], list[Path]]:
    if base.get("release_id") != "2026-07-21-open-seed-v81":
        raise OpenSeedV82Error("v82 base must be exactly accepted v81")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 428:
        raise OpenSeedV82Error("accepted v81 curated inventory differs")
    if any(not isinstance(row, dict) or set(row) != {"path", "sha256"} for row in rows):
        raise OpenSeedV82Error("accepted v81 curated rows differ")
    base_names = [row["path"] for row in rows]
    if len(set(base_names)) != 428:
        raise OpenSeedV82Error("accepted v81 input paths collide")
    documents = _validate_additions(
        recorded_at, validation_wall_clock=validation_wall_clock
    )
    if set(base_names) & (set(ADDITION_PINS) | EXCLUDED_SOURCE_PATHS):
        raise OpenSeedV82Error("v81 already contains a CEE source")

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
        raise OpenSeedV82Error("v82 addition collides with accepted v81 semantics")

    selected = [dict(row) for row in rows]
    for relative in ADDITION_ORDER:
        selected.append({"path": relative, "sha256": ADDITION_PINS[relative][1]})
        paths.append(ROOT / relative)
    if (
        selected[:428] != rows
        or [row["path"] for row in selected[428:]] != list(ADDITION_ORDER)
        or tuple(documents) != ADDITION_ORDER
        or len(selected) != 433
        or set(row["path"] for row in selected) & EXCLUDED_SOURCE_PATHS
    ):
        raise OpenSeedV82Error("v82 did not preserve v81 and append exactly five inputs")
    return selected, paths


def _guard_state() -> dict[str, Any]:
    _validate_official_artifact()
    return {
        "base_definition": (BASE_DEFINITION.stat().st_size, v69.sha256(BASE_DEFINITION)),
        "base_manifest": v69.sha256(BASE_RELEASE / "manifest.json"),
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
        "entities": 890,
        "evidence": 719,
        "entity_snapshots": 910,
        "lifecycle_observations": 518,
        "capacity_estimates": 542,
        "operating_model_observations": 64,
        "workload_observations": 135,
    }
    actual_counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in expected_counts
    }
    if actual_counts != expected_counts:
        raise OpenSeedV82Error(f"v82 database counts differ: {actual_counts}")
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v82-base-", dir="/private/tmp"
    ) as td:
        prior = v69._populate_database(
            base, _base_paths(base), Path(td) / "v81.sqlite", recorded_at=recorded_at
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
                    raise OpenSeedV82Error(f"v82 changed a prior database row: {table}")
            before_keys = {row[0] for row in prior.execute("SELECT stable_key FROM entities")}
            after_keys = {row[0] for row in connection.execute("SELECT stable_key FROM entities")}
            if after_keys - before_keys != ADDED_ENTITY_KEYS or before_keys - after_keys:
                raise OpenSeedV82Error("v82 database identity delta differs")
            before_evidence = set(v70._evidence_by_key(prior))
            after_evidence = set(v70._evidence_by_key(connection))
            if (
                after_evidence - before_evidence != ADDED_EVIDENCE_KEYS
                or before_evidence - after_evidence
            ):
                raise OpenSeedV82Error("v82 database evidence delta differs")
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
        raise OpenSeedV82Error("v82 entity-kind contract differs")

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
    imported_workloads = {
        tuple(row)
        for row in connection.execute(
            f"""
            SELECT entities.stable_key, workload, as_of_date,
                   workload_observations.method
            FROM workload_observations
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
        or imported_workloads != WORKLOAD_CONTRACT
    ):
        raise OpenSeedV82Error("v82 imported claim contract differs")
    for stable_key, latitude, longitude, geometry in connection.execute(
        f"""
        SELECT entities.stable_key, latitude, longitude, geometry_json
        FROM entity_snapshots JOIN entities ON entities.id = entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        keys,
    ):
        expected_point = COORDINATE_CONTRACT.get(stable_key)
        if expected_point is None:
            if latitude is not None or longitude is not None or geometry not in {
                None,
                "null",
            }:
                raise OpenSeedV82Error(
                    f"v82 imported unsupported coordinates: {stable_key}"
                )
        elif (
            latitude != expected_point[0]
            or longitude != expected_point[1]
            or json.loads(geometry)
            != {
                "type": "Point",
                "coordinates": [expected_point[1], expected_point[0]],
            }
        ):
            raise OpenSeedV82Error(f"v82 imported coordinate differs: {stable_key}")


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
            raise OpenSeedV82Error("precreated v82 release stage must be empty")
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
    "entities.csv": (880, 10, 0),
    "evidence.csv": (568, 6, 0),
    "capacity_estimates.csv": (540, 1, 0),
    "construction_pipeline.csv": (451, 4, 0),
    "construction_source_signals.csv": (353, 4, 0),
    "resolution_candidates.csv": (7, 0, 0),
    "lifecycle_freshness.csv": (493, 5, 0),
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
            raise OpenSeedV82Error(
                f"v82 public CSV delta differs: {filename}: {actual}"
            )

    before_entities = {
        row["stable_key"]: row for row in _csv_rows(BASE_RELEASE / "entities.csv")
    }
    after_entities = {
        row["stable_key"]: row for row in _csv_rows(stage / "entities.csv")
    }
    if set(after_entities) - set(before_entities) != ADDED_ENTITY_KEYS:
        raise OpenSeedV82Error("v82 public identity delta differs")
    if set(before_entities) - set(after_entities) or any(
        after_entities[key] != row for key, row in before_entities.items()
    ):
        raise OpenSeedV82Error("v82 changed an accepted v81 public entity")
    for stable_key in ADDED_ENTITY_KEYS:
        row = after_entities[stable_key]
        expected_point = COORDINATE_CONTRACT.get(stable_key)
        if expected_point is None:
            if row["latitude"] or row["longitude"] or row["geometry_json"] != "null":
                raise OpenSeedV82Error("v82 public addition gained unsupported coordinates")
        elif (
            float(row["latitude"]) != expected_point[0]
            or float(row["longitude"]) != expected_point[1]
            or json.loads(row["geometry_json"])
            != {
                "type": "Point",
                "coordinates": [expected_point[1], expected_point[0]],
            }
        ):
            raise OpenSeedV82Error("v82 public official coordinate differs")
        workloads = json.loads(row.get("workloads_json", "null"))
        expected_workloads = {
            "curated:microsoft-ath04-spata-data-center:active-construction": {
                ("general_cloud", "2026-03-31", "company_disclosure")
            },
            "curated:serbia-state-data-center-kragujevac:modules-3-4-commissioned-2026": {
                ("ai_specialized_unspecified", "2026-04-30", "company_disclosure")
            },
        }.get(stable_key, set())
        actual_workloads = {
            (row.get("workload"), row.get("as_of_date"), row.get("method"))
            for row in workloads
        }
        if actual_workloads != expected_workloads or len(workloads) != len(
            expected_workloads
        ):
            raise OpenSeedV82Error("v82 public workload boundary differs")
        expected_model = {
            "curated:microsoft-ath04-spata-data-center:active-construction":
                "hyperscale_self_build",
            "curated:serbia-state-data-center-kragujevac:modules-3-4-commissioned-2026":
                "sovereign_research",
        }.get(stable_key, "")
        if row.get("operating_model") != expected_model:
            raise OpenSeedV82Error("v82 public operating-model boundary differs")
        capacities = json.loads(row.get("capacity_estimates_json", "null"))
        expected_capacity = {
            "curated:serbia-state-data-center-kragujevac:modules-3-4-commissioned-2026": (
                0.3,
                "2026-04-30",
            ),
        }.get(stable_key)
        if expected_capacity is None:
            if capacities != []:
                raise OpenSeedV82Error("v82 public addition gained unsupported capacity")
        elif (
            len(capacities) != 1
            or capacities[0].get("metric") != "generation_nameplate_mw"
            or capacities[0].get("stage") != "operational"
            or capacities[0].get("unit") != "MW"
            or float(capacities[0].get("base")) != expected_capacity[0]
            or capacities[0].get("as_of_date") != expected_capacity[1]
            or capacities[0].get("method") != "reported"
        ):
            raise OpenSeedV82Error("v82 public generation capacity differs")

    before_evidence = {
        row["evidence_id"]: row for row in _csv_rows(BASE_RELEASE / "evidence.csv")
    }
    after_evidence = {
        row["evidence_id"]: row for row in _csv_rows(stage / "evidence.csv")
    }
    if set(before_evidence) - set(after_evidence) or any(
        after_evidence[key] != row for key, row in before_evidence.items()
    ):
        raise OpenSeedV82Error("v82 changed accepted v81 public evidence")
    added_evidence = [
        row for key, row in after_evidence.items() if key not in before_evidence
    ]
    if (
        len(added_evidence) != 6
        or {row["source_family"] for row in added_evidence}
        != PROJECTED_SOURCE_FAMILIES
        or {row["kind"] for row in added_evidence}
        != {"company_disclosure", "government_record"}
    ):
        raise OpenSeedV82Error("v82 public evidence projection differs")

    before_pipeline = {
        row["stable_key"]: row
        for row in _csv_rows(BASE_RELEASE / "construction_pipeline.csv")
    }
    after_pipeline = {
        row["stable_key"]: row
        for row in _csv_rows(stage / "construction_pipeline.csv")
    }
    if (
        set(after_pipeline) - set(before_pipeline) != ADDED_PIPELINE_PROJECT_KEYS
        or set(before_pipeline) - set(after_pipeline)
        or any(after_pipeline[key] != row for key, row in before_pipeline.items())
    ):
        raise OpenSeedV82Error("v82 construction-pipeline delta differs")
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
        or len(added_signals) != 4
        or {row["representative_stable_key"] for row in added_signals}
        != ADDED_PIPELINE_PROJECT_KEYS
    ):
        raise OpenSeedV82Error("v82 construction-signal delta differs")
    signal_by_key = {
        row["representative_stable_key"]: row for row in added_signals
    }
    for stable_key, row in signal_by_key.items():
        expected_point = COORDINATE_CONTRACT.get(stable_key)
        if expected_point is None:
            if row["representative_latitude"] or row["representative_longitude"]:
                raise OpenSeedV82Error("v82 signal gained unsupported coordinates")
        elif (
            float(row["representative_latitude"]) != expected_point[0]
            or float(row["representative_longitude"]) != expected_point[1]
        ):
            raise OpenSeedV82Error("v82 signal official coordinate differs")

    before_resolution = json.loads(
        (BASE_RELEASE / "resolution_candidates.json").read_text()
    )
    after_resolution = json.loads((stage / "resolution_candidates.json").read_text())
    if _normalize_timestamps(before_resolution, recorded_at) != _normalize_timestamps(
        after_resolution, recorded_at
    ):
        raise OpenSeedV82Error("v82 changed the resolution advisory")
    for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
        if (stage / filename).read_bytes() != (BASE_RELEASE / filename).read_bytes():
            raise OpenSeedV82Error(f"v82 changed invariant release file: {filename}")

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
    source_by_family = {row["source_family"]: row for row in added_sources}
    if (
        before_source_rows - after_source_rows
        or len(added_sources) != 6
        or {row["source_family"] for row in added_sources}
        != PROJECTED_SOURCE_FAMILIES
        or {
            row.get("provenance", {}).get("curated_record_key")
            for row in added_sources
        }
        != PROJECTED_EVIDENCE_KEYS
        or source_by_family["ast_official_events"].get("provenance", {}).get(
            "content_hash_verification"
        )
        != "unverified_assertion"
        or not source_by_family["ast_official_events"].get(
            "provenance", {}
        ).get("content_hash_scope", "").endswith("not source bytes")
    ):
        raise OpenSeedV82Error("v82 source-input projection differs")

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
        raise OpenSeedV82Error("v82 GeoJSON base preservation differs")
    for stable_key in ADDED_ENTITY_KEYS:
        expected_point = COORDINATE_CONTRACT.get(stable_key)
        expected_geometry = (
            None
            if expected_point is None
            else {
                "type": "Point",
                "coordinates": [expected_point[1], expected_point[0]],
            }
        )
        if after_features[stable_key]["geometry"] != expected_geometry:
            raise OpenSeedV82Error("v82 GeoJSON coordinate boundary differs")


def _validate_release_facts(stage: Path, *, recorded_at: str) -> None:
    summary = json.loads((stage / "summary.json").read_text())
    expected_summary = {
        "campuses_total": 467,
        "campuses_with_coordinates": 136,
        "capacity_estimates_current": 541,
        "construction_pipeline_records": 455,
        "construction_source_signals": 357,
        "entities_total": 890,
        "entities_with_coordinates": 200,
        "evidence_total": 719,
        "lifecycle_observations_current": 498,
        "projects_total": 423,
        "recorded_at": recorded_at,
    }
    if {key: summary.get(key) for key in expected_summary} != expected_summary:
        raise OpenSeedV82Error(
            f"v82 summary facts differ: "
            f"{ {key: summary.get(key) for key in expected_summary} }"
        )
    if (
        summary.get("entities_by_status", {}).get("under_construction") != 344
        or summary.get("entities_by_status", {}).get("commissioning") != 3
        or summary.get("entities_by_status", {}).get("shell") != 31
        or summary.get("entities_by_status", {}).get("operational") != 43
    ):
        raise OpenSeedV82Error("v82 last-observed status summary differs")
    if (
        summary.get("capacity_estimates_by_metric", {}).get("critical_it_mw") != 272
        or summary.get("capacity_estimates_by_metric", {}).get(
            "generation_nameplate_mw"
        )
        != 5
        or summary.get("capacity_estimates_by_metric", {}).get("grid_connection_mw")
        != 24
        or summary.get("capacity_estimates_by_metric", {}).get("pue") != 6
        or summary.get("capacity_estimates_by_stage", {}).get("planned") != 158
        or summary.get("capacity_estimates_by_stage", {}).get("contracted") != 19
        or summary.get("capacity_estimates_by_stage", {}).get("design") != 21
        or summary.get("capacity_estimates_by_stage", {}).get("operational") != 172
    ):
        raise OpenSeedV82Error("v82 typed-capacity summary differs")
    expected_summary_document = json.loads(
        (BASE_RELEASE / "summary.json").read_text()
    )
    expected_summary_document.update(
        {
            "campuses_total": 467,
            "campuses_with_coordinates": 136,
            "capacity_estimates_current": 541,
            "construction_pipeline_records": 455,
            "construction_source_signals": 357,
            "entities_total": 890,
            "entities_with_coordinates": 200,
            "evidence_total": 719,
            "lifecycle_observations_current": 498,
            "projects_total": 423,
            "recorded_at": recorded_at,
        }
    )
    expected_summary_document["country_assignment_counts"]["not_evaluated"] = 890
    expected_summary_document["country_source_claims_by_method"][
        "source_explicit_country_tag"
    ] = 890
    expected_summary_document["country_source_tag_fallbacks"] = 890
    expected_summary_document["entities_by_country"].update(
        {"Greece": 6, "Latvia": 6, "Serbia": 2}
    )
    expected_summary_document["entities_by_kind"] = {"campus": 467, "project": 423}
    expected_summary_document["entities_by_status"].update(
        {"operational": 43, "shell": 31, "under_construction": 344}
    )
    expected_summary_document["evidence_by_kind"].update(
        {"company_disclosure": 529, "government_record": 112}
    )
    expected_summary_document["capacity_estimates_by_metric"][
        "generation_nameplate_mw"
    ] = 5
    expected_summary_document["capacity_estimates_by_stage"]["operational"] = 172
    if summary != expected_summary_document:
        raise OpenSeedV82Error("v82 full summary delta differs")

    manifest = json.loads((stage / "manifest.json").read_text())
    expected_manifest = {
        "entities": 890,
        "evidence_records": 574,
        "capacity_estimates": 541,
        "construction_pipeline_records": 455,
        "construction_source_signals": 357,
        "resolution_candidates": 7,
        "lifecycle_freshness_records": 498,
        "lifecycle_status_semantics": "last_observed",
        "current_status_inferred": False,
        "publication_contract_version": 4,
        "recorded_at": recorded_at,
    }
    if {key: manifest.get(key) for key in expected_manifest} != expected_manifest:
        raise OpenSeedV82Error("v82 release manifest facts differ")
    base_manifest = json.loads((BASE_RELEASE / "manifest.json").read_text())
    if (
        set(manifest["source_families"]) - set(base_manifest["source_families"])
        != PROJECTED_SOURCE_FAMILIES
        or set(base_manifest["source_families"]) - set(manifest["source_families"])
        or len(manifest["source_families"]) != 341
    ):
        raise OpenSeedV82Error("v82 public source-family delta differs")
    expected_manifest_document = {
        key: value for key, value in base_manifest.items() if key != "files"
    }
    expected_manifest_document.update(
        {
            "entities": 890,
            "entities_by_kind": {"campus": 467, "project": 423},
            "evidence_records": 574,
            "capacity_estimates": 541,
            "construction_pipeline_records": 455,
            "construction_source_signals": 357,
            "lifecycle_freshness_records": 498,
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
        raise OpenSeedV82Error("v82 full manifest delta differs")

    freshness = _csv_rows(stage / FRESHNESS_FILENAME)
    classes = Counter(row["freshness_class"] for row in freshness)
    by_key = {row["stable_key"]: row for row in freshness}
    if (
        len(freshness) != 498
        or tuple(freshness[0]) != FRESHNESS_FIELDS
        or classes
        != {
            "recent_0_90_days": 260,
            "aging_91_365_days": 206,
            "stale_over_365_days": 32,
        }
        or any(
            row["status_semantics"] != "last_observed"
            or row["current_status_classification"] != "unknown"
            or row["current_construction_claim"] != "false"
            for row in freshness
        )
    ):
        raise OpenSeedV82Error("v82 freshness/current-status boundary differs")
    expected_freshness = {
        "curated:microsoft-ath04-spata-data-center:active-construction": (
            "under_construction",
            "2026-03-31",
            "aging_91_365_days",
        ),
        "curated:tet-dc7-salaspils-data-center:phase-1-current-build": (
            "under_construction",
            "2026-03-12",
            "aging_91_365_days",
        ),
        "curated:ten-brinke-spata-data-center:active-construction": (
            "under_construction",
            "2026-07-21",
            "recent_0_90_days",
        ),
        "curated:ast-janciems-dispatcher-control-data-center:fit-out-after-building-completion": (
            "shell",
            "2026-06-27",
            "recent_0_90_days",
        ),
        "curated:serbia-state-data-center-kragujevac:modules-3-4-commissioned-2026": (
            "operational",
            "2026-04-30",
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
            raise OpenSeedV82Error(f"v82 source freshness differs: {stable_key}")

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
        raise OpenSeedV82Error("v82 public capacity boundary differs")

    readme = (stage / "README.md").read_text()
    for marker in (
        OFFICIAL_MANIFEST_PIN[1],
        OFFICIAL_PHYSICAL_TREE_SHA256,
        "All 19 other carrier candidates remain review-only or already represented",
        "ATH04's 19.2 MW",
        "Tet's 112 + 112 rack counts",
        "Data In Scale's 12.5/25 MW",
        "Serbia's 8/14 MW energy-capacity labels remain",
        "0.3 MW of operational rooftop-solar generation",
        "PPC evidence is resolution-only",
        "no Ten Brinke/Data In Scale identity, role, or capacity link",
        "modules 3/4 are not linked to the older planned Block 2",
        "AST remains labelled\n`unverified_assertion`",
        "current_status_classification`\nremains `unknown",
        "current_construction_claim` remains `false",
    ):
        if marker not in readme:
            raise OpenSeedV82Error(f"v82 README guardrail differs: {marker}")
    if len(list(stage.iterdir())) != 14:
        raise OpenSeedV82Error("v82 release file inventory count differs")


def _validate_definition(
    document: Mapping[str, Any],
    base: Mapping[str, Any],
    *,
    validation_wall_clock: datetime,
) -> str:
    if set(document) != set(base) or document.get("release_id") != RELEASE_ID:
        raise OpenSeedV82Error("v82 definition identity or schema differs")
    build = document.get("build")
    if not isinstance(build, dict) or set(build) != {"as_of", "recorded_at"}:
        raise OpenSeedV82Error("v82 definition build carrier differs")
    if build["as_of"] != AS_OF:
        raise OpenSeedV82Error("v82 as_of differs")
    recorded = v70.parse_utc(build["recorded_at"], label="v82 recorded_at")
    if (
        validation_wall_clock.tzinfo is None
        or recorded > validation_wall_clock.astimezone(UTC)
    ):
        raise OpenSeedV82Error("v82 recorded_at is later than validation wall clock")
    for key in (
        "epoch_capture",
        "expected_epoch_result",
        "freshness_contract",
        "publication_contract_version",
        "schema_version",
        "scope",
    ):
        if document.get(key) != base.get(key):
            raise OpenSeedV82Error(f"v82 inherited definition field differs: {key}")
    return build["recorded_at"]


def _validate_publication_times(
    definition: Path,
    release: Path,
    *,
    recorded_at: str,
    require_live: bool,
) -> None:
    target = v70.parse_utc(recorded_at, label="v82 recorded_at")
    for path in (definition, release, *release.iterdir()):
        metadata = path.stat(follow_symlinks=False)
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV82Error(f"v82 staged inode post-dates recorded_at: {path.name}")
    if require_live:
        if datetime.now(UTC) < target:
            raise OpenSeedV82Error("v82 recorded_at is not live")
        for path in (definition, release):
            if path.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
                raise OpenSeedV82Error(
                    f"v82 final root ctime predates recorded_at: {path.name}"
                )


def validate_open_seed_v82(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
    require_live: bool = True,
) -> dict[str, Any]:
    if replay_count != 2:
        raise OpenSeedV82Error("v82 requires exactly two offline replays")
    wall = validation_wall_clock or datetime.now(UTC)
    guard = _guard_state()
    if guard["base_definition"] != BASE_DEFINITION_PIN:
        raise OpenSeedV82Error("accepted v81 definition pin differs")
    if (
        guard["base_manifest"] != BASE_MANIFEST_SHA256
        or guard["base_tree"] != BASE_TREE_SHA256
        or guard["base_entities"] != BASE_ENTITIES_PIN
    ):
        raise OpenSeedV82Error("accepted v81 release pin differs")
    if guard["excluded"] != EXCLUDED_SOURCE_PINS:
        raise OpenSeedV82Error("v82 excluded source pin differs")
    if guard["official_manifest"] != OFFICIAL_MANIFEST_PIN:
        raise OpenSeedV82Error("official artifact manifest pin differs")
    base = json.loads(BASE_DEFINITION.read_text())
    definition_raw, definition = _read_json(
        definition_path, mode=0o444, sort_keys=True
    )
    recorded_at = _validate_definition(definition, base, validation_wall_clock=wall)
    selected, paths = selected_inputs(
        base, recorded_at=recorded_at, validation_wall_clock=wall
    )
    if definition.get("curated_inputs") != selected:
        raise OpenSeedV82Error("v82 selected input inventory differs")
    if release_path.is_symlink() or not release_path.is_dir():
        raise OpenSeedV82Error("v82 release must be an ordinary directory")
    if require_frozen and stat.S_IMODE(release_path.stat().st_mode) != 0o555:
        raise OpenSeedV82Error("v82 release root is not frozen")
    release_files = {path.name: path for path in release_path.iterdir()}
    if any(path.is_symlink() or not path.is_file() for path in release_files.values()):
        raise OpenSeedV82Error("v82 release contains a non-file")
    if require_frozen and any(
        stat.S_IMODE(path.stat().st_mode) != 0o444 for path in release_files.values()
    ):
        raise OpenSeedV82Error("v82 release file is not frozen")
    manifest_raw, manifest = _read_json(
        release_path / "manifest.json", mode=0o444, sort_keys=True
    )
    if _sha256(manifest_raw) != definition["expected_release"].get(
        "manifest_sha256"
    ):
        raise OpenSeedV82Error("v82 manifest hash differs")
    expected_release = {
        key: value
        for key, value in definition["expected_release"].items()
        if key != "manifest_sha256"
    }
    if {key: value for key, value in manifest.items() if key != "files"} != expected_release:
        raise OpenSeedV82Error("v82 expected release facts differ")
    if set(release_files) != set(manifest["files"]) | {"manifest.json"}:
        raise OpenSeedV82Error("v82 release file inventory differs")
    for filename, pin in manifest["files"].items():
        raw = (release_path / filename).read_bytes()
        if (len(raw), _sha256(raw)) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV82Error(f"v82 release pin differs: {filename}")
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
        raise OpenSeedV82Error("v82 expected summary differs")

    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v82-replay-{replay + 1}-", dir="/private/tmp"
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
                raise OpenSeedV82Error("v82 replay file inventory differs")
            for filename, frozen in release_files.items():
                if (replay_release / filename).read_bytes() != frozen.read_bytes():
                    raise OpenSeedV82Error(f"v82 offline replay differs: {filename}")
    if _guard_state() != guard:
        raise OpenSeedV82Error("v82 validation mutated accepted inputs")
    return manifest


def _path_identity(path: Path, *, directory: bool) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    expected = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if not expected:
        raise OpenSeedV82Error(f"v82 stage type differs: {path}")
    return metadata.st_dev, metadata.st_ino


def _release_identities(root: Path) -> dict[str, tuple[int, int]]:
    return {path.name: _path_identity(path, directory=False) for path in root.iterdir()}


def _assert_release_identities(
    root: Path,
    root_identity: tuple[int, int],
    members: Mapping[str, tuple[int, int]],
) -> None:
    if _path_identity(root, directory=True) != root_identity:
        raise OpenSeedV82Error("v82 release stage root identity changed")
    if _release_identities(root) != dict(members):
        raise OpenSeedV82Error("v82 release stage member identity changed")


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
        raise OpenSeedV82Error("refusing substituted v82 definition cleanup")
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
        raise OpenSeedV82Error("active v82 publication lock exists") from error
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
                raise OpenSeedV82Error("refusing substituted v82 lock cleanup")
            PUBLICATION_LOCK.unlink()


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _require_absent(label: str) -> None:
    if DEFINITION.exists() or DEFINITION.is_symlink():
        raise OpenSeedV82Error(f"{label} v82 definition collision")
    if RELEASE.exists() or RELEASE.is_symlink():
        raise OpenSeedV82Error(f"{label} v82 release collision")


def _rollback_release(release_identity: tuple[int, int], release_stage: Path) -> None:
    if _path_identity(RELEASE, directory=True) != release_identity:
        raise OpenSeedV82Error("refusing rollback of substituted v82 release")
    if release_stage.exists() or release_stage.is_symlink():
        raise OpenSeedV82Error("v82 release rollback stage is occupied")
    v69.promote_noreplace(RELEASE, release_stage)


def build_open_seed_v82(recorded_at: str | None = None) -> dict[str, Any]:
    """Build and atomically publish the five-source v81 successor."""

    if (DEFINITION.exists() or DEFINITION.is_symlink()) and (
        RELEASE.exists() or RELEASE.is_symlink()
    ):
        manifest = validate_open_seed_v82()
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
        raise OpenSeedV82Error("partial v82 final-path collision")

    guard = _guard_state()
    if guard["base_definition"] != BASE_DEFINITION_PIN:
        raise OpenSeedV82Error("accepted v81 definition pin differs")
    if (
        guard["base_manifest"] != BASE_MANIFEST_SHA256
        or guard["base_tree"] != BASE_TREE_SHA256
        or guard["base_entities"] != BASE_ENTITIES_PIN
    ):
        raise OpenSeedV82Error("accepted v81 release pin differs")
    if guard["excluded"] != EXCLUDED_SOURCE_PINS:
        raise OpenSeedV82Error("v82 excluded source pin differs")
    target = (
        v70.parse_utc(recorded_at, label="v82 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise OpenSeedV82Error("v82 recorded_at must be future before staging")
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
                prefix="open-seed-v82-db-", dir="/private/tmp"
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
                raise OpenSeedV82Error("v82 definition stage identity changed")
            _assert_release_identities(
                release_stage, release_identity, release_members
            )
            if (
                definition_stage.read_bytes() != frozen_definition
                or v69.tree_digest(release_stage) != frozen_tree
            ):
                raise OpenSeedV82Error("v82 private stage changed while waiting")
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
                    error.add_note(f"v82 release rollback failed: {rollback_error}")
                raise
            manifest = validate_open_seed_v82(DEFINITION, RELEASE)
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
        raise OpenSeedV82Error("v82 build mutated accepted inputs")
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
    print(json.dumps(build_open_seed_v82(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
