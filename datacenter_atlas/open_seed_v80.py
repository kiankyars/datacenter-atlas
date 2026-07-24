"""Build the strict two-source append-only successor to open seed v79."""

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
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v79.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v79"
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v80.json"
RELEASE_ID = "2026-07-21-open-seed-v80"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v80.lock"
AS_OF = "2026-07-21"

BASE_RECORDED_AT = "2026-07-21T16:49:49Z"
BASE_DEFINITION_PIN = (
    94_039,
    "3a8cfb0d6ed9f858f5be3ac8cfda7502673241ede8f0aa23715714a09a7d462e",
)
BASE_MANIFEST_SHA256 = (
    "4eaceee00a0ed0e9073bc6cd19a8f82c97a442f05e773615ee1bb470a95a5c71"
)
BASE_TREE_SHA256 = "f5cfdebad04ccb8347cdf9cd965e88f096dc44699b938ecc111acc28348858a2"

OFFICIAL_ARTIFACT = (
    ROOT
    / "source_artifacts/global-official-builds-africa-gap-2026-07-21-v1"
)
OFFICIAL_RECORDED_AT = "2026-07-21T16:55:54Z"
OFFICIAL_MANIFEST_PIN = (
    1_817,
    "c859d9a429729710d92f43fadf2570551a9959485c5c3ace005b612376b1478a",
)
OFFICIAL_MANIFEST_TREE_SHA256 = (
    "b7e01474654331c4e178ada40e02c7c0ce28f578b5348b0ea5e5d790f229ecd4"
)
OFFICIAL_PHYSICAL_TREE_SHA256 = (
    "2c64c04f31f2001380a7f673a201447fbf522e2ee80ba939adccf3eedd3da152"
)
OFFICIAL_SNAPSHOT_PIN = (
    7_078,
    "5f23943c275aead25a26b225e27e437732499f82c80a014e4e718bf3021eb5a7",
)
OFFICIAL_ASSESSMENT_PIN = (
    4_884,
    "2303075ead053484beca6033497d7614a6e94e2de19e67e16a4b67e4c25d10b2",
)
OFFICIAL_RIGHTS_PIN = (
    1_313,
    "967f1824b797456e0d96a1b0bd96522a2f03f29648d2e273bed7e39bf62878fc",
)

ADDITION_ORDER = (
    "sources/curated-official-2026-07-21-icolo-nbo2-current-build.json",
    "sources/curated-official-2026-07-21-telecom-egypt-rdh2-commissioning.json",
)
ADDITION_PINS = {
    ADDITION_ORDER[0]: (
        10_196,
        "b7b003f7a4065572e9c3778b080b438955ea62fd066e346dc0608a2cdc54d221",
    ),
    ADDITION_ORDER[1]: (
        9_305,
        "910f4a3240f17c33454a09746dc3d1761f33c4ce5c7b80ce423db1d8b6113d88",
    ),
}
EXCLUDED_ORDER = (
    "sources/curated-official-2026-07-21-teraco-jb7-review-only.json",
    "sources/curated-official-2026-07-21-adc-accra-review-only.json",
    "sources/curated-official-2026-07-21-ixafrica-nbox-phase2-review-only.json",
)
EXCLUDED_SOURCE_PATHS = frozenset(EXCLUDED_ORDER)
EXCLUDED_SOURCE_PINS = {
    "sources/curated-official-2026-07-21-teraco-jb7-review-only.json": (
        5_768,
        "e25a53734131c79d613af6e66dfa1a2c155033029f784ec1c4f4daf71b31a0b7",
    ),
    "sources/curated-official-2026-07-21-adc-accra-review-only.json": (
        6_336,
        "fec49f1e1369d8bfbe67547c94214eef52bb2c75553305a4bef102fa912a024a",
    ),
    "sources/curated-official-2026-07-21-ixafrica-nbox-phase2-review-only.json": (
        6_095,
        "96bc798869509bfc0a2f06a4b41068dd91ccd5b63c55960fcea4108b078b75dc",
    ),
}

ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:icolo-nbo2-karen-nairobi-campus",
        "curated:icolo-nbo2-karen-nairobi-campus:initial-build",
        "curated:telecom-egypt-rdh2-smart-village-campus",
        "curated:telecom-egypt-rdh2-smart-village-campus:regional-data-hub-2",
    }
)
ADDED_PROJECT_KEYS = frozenset(key for key in ADDED_ENTITY_KEYS if key.count(":") >= 2)
ADDED_EVIDENCE_KEYS = frozenset(
    {
        "icolo-nbo2-physical-update-2026-04-21-captured-2026-07-21",
        "icolo-nbo2-design-specs-2026-01-29-captured-2026-07-21",
        "peeringdb-fac-14166-rights-metadata-only-captured-2026-07-21",
        "tab-rdh2-commissioning-2026-06-10-captured-2026-07-21",
        "telecom-egypt-rdh2-design-2024-11-18-captured-2026-07-21",
        "ecg-rdh2-project-page-2026-01-20-captured-2026-07-21",
    }
)
ADDED_SOURCE_FAMILIES = frozenset(
    {
        "icolo_official_linkedin_updates",
        "peeringdb_blocked_direct_lane_metadata",
        "tab_egypt_official_linkedin_updates",
        "telecom_egypt_corporate_news",
        "ecg_project_pages",
    }
)
PROJECTED_SOURCE_FAMILIES = frozenset(
    {
        "icolo_official_linkedin_updates",
        "tab_egypt_official_linkedin_updates",
        "telecom_egypt_corporate_news",
    }
)
LIFECYCLE_CONTRACT = frozenset(
    {
        (
            "curated:icolo-nbo2-karen-nairobi-campus:initial-build",
            "under_construction",
            "2026-04-21",
            "authoritative_physical_status_update",
        ),
        (
            "curated:telecom-egypt-rdh2-smart-village-campus:regional-data-hub-2",
            "commissioning",
            "2026-06-10",
            "authoritative_physical_status_update",
        ),
    }
)
CAPACITY_CONTRACT: frozenset[tuple[object, ...]] = frozenset(
    {
        (
            "curated:icolo-nbo2-karen-nairobi-campus:initial-build",
            "critical_it_mw",
            "design",
            "MW",
            6.5,
            "2026-01-29",
            "reported",
        ),
        (
            "curated:telecom-egypt-rdh2-smart-village-campus:regional-data-hub-2",
            "critical_it_mw",
            "design",
            "MW",
            4.6,
            "2024-11-18",
            "reported",
        ),
    }
)
OPERATING_MODEL_CONTRACT = frozenset(
    {
        (
            "curated:icolo-nbo2-karen-nairobi-campus:initial-build",
            "colocation",
            "2026-01-29",
        )
    }
)
WORKLOAD_CONTRACT = frozenset(
    {
        (
            "curated:icolo-nbo2-karen-nairobi-campus:initial-build",
            "enterprise_it",
            "2026-01-29",
            "company_disclosure",
        ),
        (
            "curated:icolo-nbo2-karen-nairobi-campus:initial-build",
            "general_cloud",
            "2026-01-29",
            "company_disclosure",
        ),
        (
            "curated:telecom-egypt-rdh2-smart-village-campus:regional-data-hub-2",
            "enterprise_it",
            "2024-11-18",
            "company_disclosure",
        ),
        (
            "curated:telecom-egypt-rdh2-smart-village-campus:regional-data-hub-2",
            "general_cloud",
            "2024-11-18",
            "company_disclosure",
        )
    }
)
COORDINATE_CONTRACT: dict[str, tuple[float, float]] = {}

FRESHNESS_README = f"""
Open seed v80 is the exact accepted v79 successor with only the two
seed-eligible source records from
`source_artifacts/global-official-builds-africa-gap-2026-07-21-v1`
appended in frozen artifact order. It preserves all 421 v79 inputs, then
appends iColo NBO2 and Telecom Egypt RDH2 for 423 inputs total.
The frozen official-source manifest is `{OFFICIAL_MANIFEST_PIN[1]}` and its
physical tree is `{OFFICIAL_PHYSICAL_TREE_SHA256}`.

Teraco JB7, Africa Data Centres Accra, and iXAfrica NBOX2 remain review-only
and contribute no v80 input or claim. NBO2's 6.5 MW and RDH2's 4.6 MW are
design critical IT only, not current draw, gross facility demand, utility
supply, generation, consumption, or annual energy. ECG's conflicting 4.9 MW
remains evidence narrative and is not normalized. NBO2's colocation model and
both projects' enterprise and cloud workloads are design/customer intent, not
active tenants, users, hardware, or load. PeeringDB contributes no identity,
address, coordinate, or placement value. No coordinate, PUE, energy,
current-load, or current-status claim is inferred.

Lifecycle values remain dated last observations. `current_status_classification`
remains `unknown` and `current_construction_claim` remains `false`.
""".strip()


class OpenSeedV80Error(RuntimeError):
    """Raised when a v80 lineage, claim, or publication guard fails closed."""


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
        raise OpenSeedV80Error(f"expected ordinary JSON file: {path}")
    if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
        raise OpenSeedV80Error(f"file mode differs: {path}")
    raw = path.read_bytes()
    document = json.loads(raw)
    if raw != _canonical(document, sort_keys=sort_keys):
        raise OpenSeedV80Error(f"JSON is not canonical: {path}")
    return raw, document


def _validate_official_artifact() -> dict[str, Any]:
    artifact = OFFICIAL_ARTIFACT
    if (
        artifact.is_symlink()
        or not artifact.is_dir()
        or stat.S_IMODE(artifact.stat().st_mode) != 0o555
        or v69.tree_digest(artifact) != OFFICIAL_PHYSICAL_TREE_SHA256
    ):
        raise OpenSeedV80Error("official Africa-gap artifact is not exact and frozen")
    if any(
        path.is_symlink()
        or stat.S_IMODE(path.stat().st_mode) != (0o555 if path.is_dir() else 0o444)
        for path in artifact.rglob("*")
    ):
        raise OpenSeedV80Error("official artifact member mode differs")
    manifest_raw, manifest = _read_json(artifact / "manifest.json", mode=0o444)
    if (len(manifest_raw), _sha256(manifest_raw)) != OFFICIAL_MANIFEST_PIN:
        raise OpenSeedV80Error("official artifact manifest pin differs")
    if (
        manifest.get("recorded_at") != OFFICIAL_RECORDED_AT
        or manifest.get("tree_sha256") != OFFICIAL_MANIFEST_TREE_SHA256
        or manifest.get("candidate_assessments") != 5
        or manifest.get("curated_source_records") != 5
        or manifest.get("seed_eligible_source_records") != 2
        or manifest.get("review_only_candidates") != 3
        or manifest.get("review_only_source_records") != 3
        or manifest.get("successful_http_200_requests") != 21
        or manifest.get("raw_capture_redistributed") is not False
        or manifest.get("raw_capture_directory_moved_intact_to_trash") is not True
        or manifest.get("peeringdb_direct_release_permitted") is not False
        or manifest.get("peeringdb_record_values_released") != 0
        or manifest.get("peeringdb_placements_created") != 0
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or manifest.get("downstream_product_integration") != "none"
    ):
        raise OpenSeedV80Error("official artifact boundary differs")
    listed = manifest.get("files")
    if not isinstance(listed, list):
        raise OpenSeedV80Error("official artifact inventory differs")
    actual = {
        path.relative_to(artifact).as_posix()
        for path in artifact.rglob("*")
        if path.is_file()
    }
    expected = {row["path"] for row in listed} | {"manifest.json", "manifest.sha256"}
    if actual != expected or manifest.get("closed_file_set") != sorted(expected):
        raise OpenSeedV80Error("official artifact is not a closed file set")
    for row in listed:
        raw = (artifact / row["path"]).read_bytes()
        if (len(raw), _sha256(raw)) != (row["bytes"], row["sha256"]):
            raise OpenSeedV80Error(f"official artifact file pin differs: {row['path']}")
    if _sha256(_canonical(listed)) != OFFICIAL_MANIFEST_TREE_SHA256:
        raise OpenSeedV80Error("official artifact manifest tree differs")
    if (artifact / "manifest.sha256").read_text() != (
        f"{OFFICIAL_MANIFEST_PIN[1]}  manifest.json\n"
    ):
        raise OpenSeedV80Error("official artifact sidecar differs")
    artifact_recorded = v70.parse_utc(
        OFFICIAL_RECORDED_AT, label="official recorded_at"
    )
    if (
        artifact_recorded > datetime.now(UTC)
        or artifact.stat().st_ctime + 1e-6 < artifact_recorded.timestamp()
    ):
        raise OpenSeedV80Error("official artifact publication time differs")

    snapshot_raw, snapshot = _read_json(artifact / "source-snapshot.json", mode=0o444)
    assessment_raw, assessment = _read_json(
        artifact / "candidate-assessment.json", mode=0o444
    )
    rights_raw, rights = _read_json(
        artifact / "rights-and-disposition.json", mode=0o444
    )
    if (len(snapshot_raw), _sha256(snapshot_raw)) != OFFICIAL_SNAPSHOT_PIN:
        raise OpenSeedV80Error("official source snapshot pin differs")
    if (len(assessment_raw), _sha256(assessment_raw)) != OFFICIAL_ASSESSMENT_PIN:
        raise OpenSeedV80Error("official assessment pin differs")
    if (len(rights_raw), _sha256(rights_raw)) != OFFICIAL_RIGHTS_PIN:
        raise OpenSeedV80Error("official rights pin differs")
    if (
        rights.get("raw_capture_redistributed") is not False
        or rights.get("artifact_is_hash_only") is not True
        or rights.get("temporary_capture_directory_moved_to_trash") is not True
        or rights.get("candidate_dispositions")
        != {
            "seed_eligible": 2,
            "review_only": 3,
        }
        or rights.get("request_credentials_supplied") is not False
        or rights.get("raw_response_bodies_retained_in_artifact") is not False
        or rights.get("raw_response_headers_retained_in_artifact") is not False
        or rights.get("publisher_media_retained_in_artifact") is not False
        or rights.get("peeringdb_direct_release_permitted") is not False
        or rights.get("peeringdb_record_values_released") != 0
        or rights.get("peeringdb_placements_created") != 0
    ):
        raise OpenSeedV80Error("official source-rights boundary differs")
    return {"manifest": manifest, "snapshot": snapshot, "assessment": assessment}


def _validate_additions(
    recorded_at: str, *, validation_wall_clock: datetime | None = None
) -> dict[str, dict[str, Any]]:
    if tuple(ADDITION_PINS) != ADDITION_ORDER or len(ADDITION_PINS) != 2:
        raise OpenSeedV80Error("v80 requires exactly two ordered additions")
    carrier = _validate_official_artifact()
    target = v70.parse_utc(recorded_at, label="v80 recorded_at")
    wall = validation_wall_clock or datetime.now(UTC)
    if wall.tzinfo is None or target > wall.astimezone(UTC):
        raise OpenSeedV80Error("v80 recorded_at is later than validation wall clock")
    if v70.parse_utc(OFFICIAL_RECORDED_AT, label="official recorded_at") > target:
        raise OpenSeedV80Error("official artifact post-dates v80")

    snapshot = carrier["snapshot"]
    records = snapshot.get("source_records")
    if (
        snapshot.get("recorded_at") != OFFICIAL_RECORDED_AT
        or not isinstance(records, list)
        or len(records) != 5
        or snapshot.get("totals", {}).get("candidate_assessments") != 5
        or snapshot.get("totals", {}).get("source_records") != 5
        or snapshot.get("totals", {}).get("seed_eligible_source_records") != 2
        or snapshot.get("totals", {}).get("review_only_candidates") != 3
        or snapshot.get("totals", {}).get("review_only_source_records") != 3
        or snapshot.get("totals", {}).get("distinct_campuses") != 5
        or snapshot.get("totals", {}).get("projects") != 5
        or snapshot.get("totals", {}).get("entity_snapshots") != 10
        or snapshot.get("totals", {}).get("unique_evidence_records") != 12
        or snapshot.get("totals", {}).get("lifecycle_observations") != 2
        or snapshot.get("totals", {}).get("operating_model_observations") != 1
        or snapshot.get("totals", {}).get("workload_observations") != 4
        or snapshot.get("totals", {}).get("capacity_estimates") != 2
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
        raise OpenSeedV80Error("official source-snapshot boundary differs")
    record_by_path = {row.get("path"): row for row in records}
    expected_record_order = (*ADDITION_ORDER, *EXCLUDED_ORDER)
    if (
        len(record_by_path) != 5
        or tuple(row.get("path") for row in records) != expected_record_order
    ):
        raise OpenSeedV80Error("official source-snapshot paths collide")
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
        raise OpenSeedV80Error("official seed-eligible source inventory differs")
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
        raise OpenSeedV80Error("Africa source inventory differs")

    assessment = carrier["assessment"]
    candidates = {
        row.get("candidate_id"): row for row in assessment.get("candidates", [])
    }
    if (
        assessment.get("candidate_count") != 5
        or assessment.get("seed_eligible_count") != 2
        or assessment.get("review_only_count") != 3
        or set(candidates)
        != {
            "icolo-nbo2-karen-nairobi",
            "telecom-egypt-rdh2-smart-village",
            "teraco-jb7-isando",
            "africa-data-centres-accra-trade-fair",
            "ixafrica-nbox2-phase-2",
        }
        or candidates.get("icolo-nbo2-karen-nairobi", {}).get("decision")
        != "seed_eligible_first_party_physical_update"
        or candidates.get("telecom-egypt-rdh2-smart-village", {}).get("decision")
        != "seed_eligible_current_pre_operation_commissioning"
        or {
            key: candidates.get(key, {}).get("decision")
            for key in (
                "teraco-jb7-isando",
                "africa-data-centres-accra-trade-fair",
                "ixafrica-nbox2-phase-2",
            )
        }
        != {
            "teraco-jb7-isando": "review_only_old_start_and_unbound_current_portfolio_aggregate",
            "africa-data-centres-accra-trade-fair": "review_only_no_2026_site_specific_physical_continuation",
            "ixafrica-nbox2-phase-2": "review_only_phase_and_specs_without_physical_status",
        }
        or any(
            candidates[key].get("seed_eligible") is not False
            or candidates[key].get("source_record_created") is not True
            for key in (
                "teraco-jb7-isando",
                "africa-data-centres-accra-trade-fair",
                "ixafrica-nbox2-phase-2",
            )
        )
        or sum(row.get("seed_eligible") is True for row in candidates.values()) != 2
    ):
        raise OpenSeedV80Error("Africa disposition boundary differs")

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
            raise OpenSeedV80Error(f"v80 excluded source byte pin differs: {relative}")
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV80Error(f"v80 excluded source post-dates publication: {relative}")
        if (
            excluded_document.get("schema_version") != "1.1"
            or excluded_document.get("lifecycle") != []
            or excluded_document.get("capacities") != []
            or excluded_document.get("workloads") != []
            or excluded_document.get("operating_models") != []
        ):
            raise OpenSeedV80Error("v80 review-only source gained a normalized claim")
    for relative in ADDITION_ORDER:
        expected_pin = ADDITION_PINS[relative]
        source = ROOT / relative
        raw, document = _read_json(source, mode=0o644)
        metadata = source.stat(follow_symlinks=False)
        if (len(raw), _sha256(raw)) != expected_pin:
            raise OpenSeedV80Error(f"v80 source byte pin differs: {relative}")
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV80Error(f"v80 source post-dates publication: {relative}")
        if document.get("schema_version") != "1.1":
            raise OpenSeedV80Error(f"v80 source schema differs: {relative}")
        documents[relative] = document
        for row in document.get("evidence", []):
            key = row.get("key")
            if key in evidence:
                raise OpenSeedV80Error(f"v80 duplicate evidence key: {key}")
            retrieved = v70.parse_utc(
                row.get("retrieved_at"), label=f"{relative} evidence retrieved_at"
            )
            if retrieved > target or retrieved > wall.astimezone(UTC):
                raise OpenSeedV80Error("v80 source evidence is future-dated")
            row_metadata = row.get("metadata", {})
            if (
                row_metadata.get("capture_artifact_id") != OFFICIAL_ARTIFACT.name
                or row_metadata.get("content_hash_verification")
                != "fetched_bytes_sha256"
                or row.get("license") != "all-rights-reserved"
            ):
                raise OpenSeedV80Error(f"v80 evidence lineage differs: {key}")
            evidence[key] = row
        for entity_name in ("campus", "project"):
            row = document.get(entity_name)
            if not isinstance(row, dict) or row.get("stable_key") in entities:
                raise OpenSeedV80Error(f"v80 entity inventory differs: {relative}")
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
            }:
                raise OpenSeedV80Error(
                    f"v80 entity classification or role boundary differs: {relative}"
                )
            stable_key = row["stable_key"]
            expected_point = COORDINATE_CONTRACT.get(stable_key)
            if expected_point is None:
                if row.get("coordinates") is not None or row.get("geometry") is not None:
                    raise OpenSeedV80Error(
                        f"v80 source gained unsupported coordinates: {relative}"
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
                raise OpenSeedV80Error(f"v80 official coordinate differs: {relative}")
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
                raise OpenSeedV80Error("v80 source capacity range differs")
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
        raise OpenSeedV80Error("v80 identity or evidence contract differs")
    if (
        lifecycle != LIFECYCLE_CONTRACT
        or capacities != CAPACITY_CONTRACT
        or operating_models != OPERATING_MODEL_CONTRACT
        or workloads != WORKLOAD_CONTRACT
    ):
        raise OpenSeedV80Error(
            "v80 lifecycle, capacity, model, or workload contract differs"
        )
    nbo2 = documents[ADDITION_ORDER[0]]
    rdh2 = documents[ADDITION_ORDER[1]]
    peering = next(
        row
        for row in nbo2["evidence"]
        if row["key"]
        == "peeringdb-fac-14166-rights-metadata-only-captured-2026-07-21"
    )
    peering_metadata = peering["metadata"]
    referenced_evidence = {
        row["evidence_key"]
        for document in documents.values()
        for section in (
            [document["campus"], document["project"]],
            document["lifecycle"],
            document["operating_models"],
            document["workloads"],
            document["capacities"],
        )
        for row in section
    }
    if (
        sum(len(document["capacities"]) for document in documents.values()) != 2
        or sum(len(document["operating_models"]) for document in documents.values())
        != 1
        or sum(len(document["workloads"]) for document in documents.values()) != 4
        or nbo2["campus"]["address"] != "Nairobi, Kenya"
        or nbo2["project"]["address"] != "Nairobi, Kenya"
        or nbo2["campus"]["evidence_key"]
        != "icolo-nbo2-design-specs-2026-01-29-captured-2026-07-21"
        or nbo2["project"]["evidence_key"]
        != "icolo-nbo2-physical-update-2026-04-21-captured-2026-07-21"
        or nbo2["capacities"][0].get("entity") != "project"
        or nbo2["capacities"][0].get("metric") != "critical_it_mw"
        or nbo2["capacities"][0].get("stage") != "design"
        or float(nbo2["capacities"][0].get("base")) != 6.5
        or nbo2["operating_models"][0].get("value") != "colocation"
        or {row.get("value") for row in nbo2["workloads"]}
        != {"enterprise_it", "general_cloud"}
        or nbo2["campus"].get("coordinates") is not None
        or nbo2["project"].get("coordinates") is not None
        or peering["source_family"] != "peeringdb_blocked_direct_lane_metadata"
        or peering["key"] in referenced_evidence
        or peering_metadata.get("record_values_released") != 0
        or peering_metadata.get("address_values_released") != 0
        or peering_metadata.get("coordinate_values_released") != 0
        or peering_metadata.get("identity_values_released") != 0
        or peering_metadata.get("placement_rows_created") != 0
        or peering_metadata.get("direct_release_permitted") is not False
        or peering_metadata.get("publication_eligible") is not False
        or rdh2["campus"]["address"] != "Smart Village, Giza, Egypt"
        or rdh2["project"]["address"] != "Smart Village, Giza, Egypt"
        or rdh2["capacities"][0].get("entity") != "project"
        or rdh2["capacities"][0].get("metric") != "critical_it_mw"
        or rdh2["capacities"][0].get("stage") != "design"
        or float(rdh2["capacities"][0].get("base")) != 4.6
        or any(float(row.get("base")) == 4.9 for row in rdh2["capacities"])
        or rdh2["operating_models"] != []
        or {row.get("value") for row in rdh2["workloads"]}
        != {"enterprise_it", "general_cloud"}
        or rdh2["campus"].get("coordinates") is not None
        or rdh2["project"].get("coordinates") is not None
        or any(
            token in relative.lower()
            for relative in ADDITION_ORDER
            for token in ("jb7", "accra", "nbox")
        )
    ):
        raise OpenSeedV80Error("v80 Africa claim guardrail differs")
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
            raise OpenSeedV80Error(f"accepted v79 input pin differs: {row['path']}")
        paths.append(path)
    return paths


def selected_inputs(
    base: Mapping[str, Any],
    *,
    recorded_at: str,
    validation_wall_clock: datetime | None = None,
) -> tuple[list[dict[str, str]], list[Path]]:
    if base.get("release_id") != "2026-07-21-open-seed-v79":
        raise OpenSeedV80Error("v80 base must be exactly accepted v79")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 421:
        raise OpenSeedV80Error("accepted v79 curated inventory differs")
    if any(not isinstance(row, dict) or set(row) != {"path", "sha256"} for row in rows):
        raise OpenSeedV80Error("accepted v79 curated rows differ")
    base_names = [row["path"] for row in rows]
    if len(set(base_names)) != 421:
        raise OpenSeedV80Error("accepted v79 input paths collide")
    documents = _validate_additions(
        recorded_at, validation_wall_clock=validation_wall_clock
    )
    if set(base_names) & (set(ADDITION_PINS) | EXCLUDED_SOURCE_PATHS):
        raise OpenSeedV80Error("v79 already contains an Africa source")

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
        raise OpenSeedV80Error("v80 addition collides with accepted v79 semantics")

    selected = [dict(row) for row in rows]
    for relative in ADDITION_ORDER:
        selected.append({"path": relative, "sha256": ADDITION_PINS[relative][1]})
        paths.append(ROOT / relative)
    if (
        selected[:421] != rows
        or [row["path"] for row in selected[421:]] != list(ADDITION_ORDER)
        or tuple(documents) != ADDITION_ORDER
        or len(selected) != 423
        or set(row["path"] for row in selected) & EXCLUDED_SOURCE_PATHS
    ):
        raise OpenSeedV80Error("v80 did not preserve v79 and append exactly two inputs")
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
        "entities": 870,
        "evidence": 696,
        "entity_snapshots": 890,
        "lifecycle_observations": 508,
        "capacity_estimates": 540,
        "operating_model_observations": 61,
        "workload_observations": 133,
    }
    actual_counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in expected_counts
    }
    if actual_counts != expected_counts:
        raise OpenSeedV80Error(f"v80 database counts differ: {actual_counts}")
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v80-base-", dir="/private/tmp"
    ) as td:
        prior = v69._populate_database(
            base, _base_paths(base), Path(td) / "v79.sqlite", recorded_at=recorded_at
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
                    raise OpenSeedV80Error(f"v80 changed a prior database row: {table}")
            before_keys = {row[0] for row in prior.execute("SELECT stable_key FROM entities")}
            after_keys = {row[0] for row in connection.execute("SELECT stable_key FROM entities")}
            if after_keys - before_keys != ADDED_ENTITY_KEYS or before_keys - after_keys:
                raise OpenSeedV80Error("v80 database identity delta differs")
            before_evidence = set(v70._evidence_by_key(prior))
            after_evidence = set(v70._evidence_by_key(connection))
            if (
                after_evidence - before_evidence != ADDED_EVIDENCE_KEYS
                or before_evidence - after_evidence
            ):
                raise OpenSeedV80Error("v80 database evidence delta differs")
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
        raise OpenSeedV80Error("v80 entity-kind contract differs")

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
        raise OpenSeedV80Error("v80 imported claim contract differs")
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
                raise OpenSeedV80Error(
                    f"v80 imported unsupported coordinates: {stable_key}"
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
            raise OpenSeedV80Error(f"v80 imported coordinate differs: {stable_key}")


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
            raise OpenSeedV80Error("precreated v80 release stage must be empty")
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
    "entities.csv": (866, 4, 0),
    "evidence.csv": (554, 4, 0),
    "capacity_estimates.csv": (537, 2, 0),
    "construction_pipeline.csv": (444, 2, 0),
    "construction_source_signals.csv": (346, 2, 0),
    "resolution_candidates.csv": (7, 0, 0),
    "lifecycle_freshness.csv": (486, 2, 0),
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
            raise OpenSeedV80Error(
                f"v80 public CSV delta differs: {filename}: {actual}"
            )

    before_entities = {
        row["stable_key"]: row for row in _csv_rows(BASE_RELEASE / "entities.csv")
    }
    after_entities = {
        row["stable_key"]: row for row in _csv_rows(stage / "entities.csv")
    }
    if set(after_entities) - set(before_entities) != ADDED_ENTITY_KEYS:
        raise OpenSeedV80Error("v80 public identity delta differs")
    if set(before_entities) - set(after_entities) or any(
        after_entities[key] != row for key, row in before_entities.items()
    ):
        raise OpenSeedV80Error("v80 changed an accepted v79 public entity")
    for stable_key in ADDED_ENTITY_KEYS:
        row = after_entities[stable_key]
        expected_point = COORDINATE_CONTRACT.get(stable_key)
        if expected_point is None:
            if row["latitude"] or row["longitude"] or row["geometry_json"] != "null":
                raise OpenSeedV80Error("v80 public addition gained unsupported coordinates")
        elif (
            float(row["latitude"]) != expected_point[0]
            or float(row["longitude"]) != expected_point[1]
            or json.loads(row["geometry_json"])
            != {
                "type": "Point",
                "coordinates": [expected_point[1], expected_point[0]],
            }
        ):
            raise OpenSeedV80Error("v80 public official coordinate differs")
        workloads = json.loads(row.get("workloads_json", "null"))
        expected_workloads = {
            "curated:icolo-nbo2-karen-nairobi-campus:initial-build": {
                ("enterprise_it", "2026-01-29", "company_disclosure"),
                ("general_cloud", "2026-01-29", "company_disclosure"),
            },
            "curated:telecom-egypt-rdh2-smart-village-campus:regional-data-hub-2": {
                ("enterprise_it", "2024-11-18", "company_disclosure"),
                ("general_cloud", "2024-11-18", "company_disclosure"),
            },
        }.get(stable_key, set())
        actual_workloads = {
            (row.get("workload"), row.get("as_of_date"), row.get("method"))
            for row in workloads
        }
        if actual_workloads != expected_workloads or len(workloads) != len(
            expected_workloads
        ):
            raise OpenSeedV80Error("v80 public workload boundary differs")
        expected_model = (
            "colocation"
            if stable_key == "curated:icolo-nbo2-karen-nairobi-campus:initial-build"
            else ""
        )
        if row.get("operating_model") != expected_model:
            raise OpenSeedV80Error("v80 public operating-model boundary differs")
        capacities = json.loads(row.get("capacity_estimates_json", "null"))
        expected_capacity = {
            "curated:icolo-nbo2-karen-nairobi-campus:initial-build": (
                6.5,
                "2026-01-29",
            ),
            "curated:telecom-egypt-rdh2-smart-village-campus:regional-data-hub-2": (
                4.6,
                "2024-11-18",
            ),
        }.get(stable_key)
        if expected_capacity is None:
            if capacities != []:
                raise OpenSeedV80Error("v80 public addition gained unsupported capacity")
        elif (
            len(capacities) != 1
            or capacities[0].get("metric") != "critical_it_mw"
            or capacities[0].get("stage") != "design"
            or capacities[0].get("unit") != "MW"
            or float(capacities[0].get("base")) != expected_capacity[0]
            or capacities[0].get("as_of_date") != expected_capacity[1]
            or capacities[0].get("method") != "reported"
        ):
            raise OpenSeedV80Error("v80 public critical-IT capacity differs")

    before_evidence = {
        row["evidence_id"]: row for row in _csv_rows(BASE_RELEASE / "evidence.csv")
    }
    after_evidence = {
        row["evidence_id"]: row for row in _csv_rows(stage / "evidence.csv")
    }
    if set(before_evidence) - set(after_evidence) or any(
        after_evidence[key] != row for key, row in before_evidence.items()
    ):
        raise OpenSeedV80Error("v80 changed accepted v79 public evidence")
    added_evidence = [
        row for key, row in after_evidence.items() if key not in before_evidence
    ]
    if (
        len(added_evidence) != 4
        or {row["source_family"] for row in added_evidence}
        != PROJECTED_SOURCE_FAMILIES
        or {row["kind"] for row in added_evidence} != {"company_disclosure"}
    ):
        raise OpenSeedV80Error("v80 public evidence projection differs")

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
        raise OpenSeedV80Error("v80 construction-pipeline delta differs")
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
        or len(added_signals) != 2
        or {row["representative_stable_key"] for row in added_signals}
        != ADDED_PROJECT_KEYS
    ):
        raise OpenSeedV80Error("v80 construction-signal delta differs")
    signal_by_key = {
        row["representative_stable_key"]: row for row in added_signals
    }
    for stable_key, row in signal_by_key.items():
        expected_point = COORDINATE_CONTRACT.get(stable_key)
        if expected_point is None:
            if row["representative_latitude"] or row["representative_longitude"]:
                raise OpenSeedV80Error("v80 signal gained unsupported coordinates")
        elif (
            float(row["representative_latitude"]) != expected_point[0]
            or float(row["representative_longitude"]) != expected_point[1]
        ):
            raise OpenSeedV80Error("v80 signal official coordinate differs")

    before_resolution = json.loads(
        (BASE_RELEASE / "resolution_candidates.json").read_text()
    )
    after_resolution = json.loads((stage / "resolution_candidates.json").read_text())
    if _normalize_timestamps(before_resolution, recorded_at) != _normalize_timestamps(
        after_resolution, recorded_at
    ):
        raise OpenSeedV80Error("v80 changed the resolution advisory")
    for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
        if (stage / filename).read_bytes() != (BASE_RELEASE / filename).read_bytes():
            raise OpenSeedV80Error(f"v80 changed invariant release file: {filename}")

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
        or len(added_sources) != 4
        or {row["source_family"] for row in added_sources}
        != PROJECTED_SOURCE_FAMILIES
    ):
        raise OpenSeedV80Error("v80 source-input projection differs")

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
        raise OpenSeedV80Error("v80 GeoJSON base preservation differs")
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
            raise OpenSeedV80Error("v80 GeoJSON coordinate boundary differs")


def _validate_release_facts(stage: Path, *, recorded_at: str) -> None:
    summary = json.loads((stage / "summary.json").read_text())
    expected_summary = {
        "campuses_total": 457,
        "campuses_with_coordinates": 136,
        "capacity_estimates_current": 539,
        "construction_pipeline_records": 446,
        "construction_source_signals": 348,
        "entities_total": 870,
        "entities_with_coordinates": 200,
        "evidence_total": 696,
        "lifecycle_observations_current": 488,
        "projects_total": 413,
        "recorded_at": recorded_at,
    }
    if {key: summary.get(key) for key in expected_summary} != expected_summary:
        raise OpenSeedV80Error(
            f"v80 summary facts differ: "
            f"{ {key: summary.get(key) for key in expected_summary} }"
        )
    if (
        summary.get("entities_by_status", {}).get("under_construction") != 336
        or summary.get("entities_by_status", {}).get("commissioning") != 3
        or summary.get("entities_by_status", {}).get("shell") != 30
    ):
        raise OpenSeedV80Error("v80 last-observed status summary differs")
    if (
        summary.get("capacity_estimates_by_metric", {}).get("critical_it_mw") != 271
        or summary.get("capacity_estimates_by_metric", {}).get("grid_connection_mw")
        != 24
        or summary.get("capacity_estimates_by_metric", {}).get("pue") != 6
        or summary.get("capacity_estimates_by_stage", {}).get("planned") != 158
        or summary.get("capacity_estimates_by_stage", {}).get("contracted") != 19
        or summary.get("capacity_estimates_by_stage", {}).get("design") != 20
    ):
        raise OpenSeedV80Error("v80 typed-capacity summary differs")
    expected_summary_document = json.loads(
        (BASE_RELEASE / "summary.json").read_text()
    )
    expected_summary_document.update(
        {
            "campuses_total": 457,
            "campuses_with_coordinates": 136,
            "capacity_estimates_current": 539,
            "construction_pipeline_records": 446,
            "construction_source_signals": 348,
            "entities_total": 870,
            "entities_with_coordinates": 200,
            "evidence_total": 696,
            "lifecycle_observations_current": 488,
            "projects_total": 413,
            "recorded_at": recorded_at,
        }
    )
    expected_summary_document["country_assignment_counts"]["not_evaluated"] = 870
    expected_summary_document["country_source_claims_by_method"][
        "source_explicit_country_tag"
    ] = 870
    expected_summary_document["country_source_tag_fallbacks"] = 870
    expected_summary_document["entities_by_country"].update(
        {"Egypt": 2, "Kenya": 6}
    )
    expected_summary_document["entities_by_kind"] = {"campus": 457, "project": 413}
    expected_summary_document["entities_by_status"].update(
        {"commissioning": 3, "under_construction": 336}
    )
    expected_summary_document["evidence_by_kind"].update(
        {"company_disclosure": 507}
    )
    expected_summary_document["capacity_estimates_by_metric"]["critical_it_mw"] = 271
    expected_summary_document["capacity_estimates_by_stage"]["design"] = 20
    if summary != expected_summary_document:
        raise OpenSeedV80Error("v80 full summary delta differs")

    manifest = json.loads((stage / "manifest.json").read_text())
    expected_manifest = {
        "entities": 870,
        "evidence_records": 558,
        "capacity_estimates": 539,
        "construction_pipeline_records": 446,
        "construction_source_signals": 348,
        "resolution_candidates": 7,
        "lifecycle_freshness_records": 488,
        "lifecycle_status_semantics": "last_observed",
        "current_status_inferred": False,
        "publication_contract_version": 4,
        "recorded_at": recorded_at,
    }
    if {key: manifest.get(key) for key in expected_manifest} != expected_manifest:
        raise OpenSeedV80Error("v80 release manifest facts differ")
    base_manifest = json.loads((BASE_RELEASE / "manifest.json").read_text())
    if (
        set(manifest["source_families"]) - set(base_manifest["source_families"])
        != PROJECTED_SOURCE_FAMILIES
        or set(base_manifest["source_families"]) - set(manifest["source_families"])
        or len(manifest["source_families"]) != 325
    ):
        raise OpenSeedV80Error("v80 public source-family delta differs")
    expected_manifest_document = {
        key: value for key, value in base_manifest.items() if key != "files"
    }
    expected_manifest_document.update(
        {
            "entities": 870,
            "entities_by_kind": {"campus": 457, "project": 413},
            "evidence_records": 558,
            "capacity_estimates": 539,
            "construction_pipeline_records": 446,
            "construction_source_signals": 348,
            "lifecycle_freshness_records": 488,
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
        raise OpenSeedV80Error("v80 full manifest delta differs")

    freshness = _csv_rows(stage / FRESHNESS_FILENAME)
    classes = Counter(row["freshness_class"] for row in freshness)
    by_key = {row["stable_key"]: row for row in freshness}
    if (
        len(freshness) != 488
        or tuple(freshness[0]) != FRESHNESS_FIELDS
        or classes
        != {
            "recent_0_90_days": 253,
            "aging_91_365_days": 203,
            "stale_over_365_days": 32,
        }
        or any(
            row["status_semantics"] != "last_observed"
            or row["current_status_classification"] != "unknown"
            or row["current_construction_claim"] != "false"
            for row in freshness
        )
    ):
        raise OpenSeedV80Error("v80 freshness/current-status boundary differs")
    expected_freshness = {
        "curated:icolo-nbo2-karen-nairobi-campus:initial-build": (
            "under_construction",
            "2026-04-21",
            "aging_91_365_days",
        ),
        "curated:telecom-egypt-rdh2-smart-village-campus:regional-data-hub-2": (
            "commissioning",
            "2026-06-10",
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
            raise OpenSeedV80Error(f"v80 source freshness differs: {stable_key}")

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
        raise OpenSeedV80Error("v80 public capacity boundary differs")

    readme = (stage / "README.md").read_text()
    for marker in (
        OFFICIAL_MANIFEST_PIN[1],
        OFFICIAL_PHYSICAL_TREE_SHA256,
        "Teraco JB7",
        "Africa Data Centres Accra",
        "iXAfrica NBOX2 remain review-only",
        "NBO2's 6.5 MW and RDH2's 4.6 MW are\ndesign critical IT only",
        "ECG's conflicting 4.9 MW\nremains evidence narrative",
        "design/customer intent, not\nactive tenants, users, hardware, or load",
        "PeeringDB contributes no identity,\naddress, coordinate, or placement value",
        "current_status_classification`\nremains `unknown",
        "current_construction_claim` remains `false",
    ):
        if marker not in readme:
            raise OpenSeedV80Error(f"v80 README guardrail differs: {marker}")
    if len(list(stage.iterdir())) != 14:
        raise OpenSeedV80Error("v80 release file inventory count differs")


def _validate_definition(
    document: Mapping[str, Any],
    base: Mapping[str, Any],
    *,
    validation_wall_clock: datetime,
) -> str:
    if set(document) != set(base) or document.get("release_id") != RELEASE_ID:
        raise OpenSeedV80Error("v80 definition identity or schema differs")
    build = document.get("build")
    if not isinstance(build, dict) or set(build) != {"as_of", "recorded_at"}:
        raise OpenSeedV80Error("v80 definition build carrier differs")
    if build["as_of"] != AS_OF:
        raise OpenSeedV80Error("v80 as_of differs")
    recorded = v70.parse_utc(build["recorded_at"], label="v80 recorded_at")
    if (
        validation_wall_clock.tzinfo is None
        or recorded > validation_wall_clock.astimezone(UTC)
    ):
        raise OpenSeedV80Error("v80 recorded_at is later than validation wall clock")
    for key in (
        "epoch_capture",
        "expected_epoch_result",
        "freshness_contract",
        "publication_contract_version",
        "schema_version",
        "scope",
    ):
        if document.get(key) != base.get(key):
            raise OpenSeedV80Error(f"v80 inherited definition field differs: {key}")
    return build["recorded_at"]


def _validate_publication_times(
    definition: Path,
    release: Path,
    *,
    recorded_at: str,
    require_live: bool,
) -> None:
    target = v70.parse_utc(recorded_at, label="v80 recorded_at")
    for path in (definition, release, *release.iterdir()):
        metadata = path.stat(follow_symlinks=False)
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV80Error(f"v80 staged inode post-dates recorded_at: {path.name}")
    if require_live:
        if datetime.now(UTC) < target:
            raise OpenSeedV80Error("v80 recorded_at is not live")
        for path in (definition, release):
            if path.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
                raise OpenSeedV80Error(
                    f"v80 final root ctime predates recorded_at: {path.name}"
                )


def validate_open_seed_v80(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
    require_live: bool = True,
) -> dict[str, Any]:
    if replay_count != 2:
        raise OpenSeedV80Error("v80 requires exactly two offline replays")
    wall = validation_wall_clock or datetime.now(UTC)
    guard = _guard_state()
    if guard["base_definition"] != BASE_DEFINITION_PIN:
        raise OpenSeedV80Error("accepted v79 definition pin differs")
    if (
        guard["base_manifest"] != BASE_MANIFEST_SHA256
        or guard["base_tree"] != BASE_TREE_SHA256
    ):
        raise OpenSeedV80Error("accepted v79 release pin differs")
    if guard["excluded"] != EXCLUDED_SOURCE_PINS:
        raise OpenSeedV80Error("v80 excluded source pin differs")
    if guard["official_manifest"] != OFFICIAL_MANIFEST_PIN:
        raise OpenSeedV80Error("official artifact manifest pin differs")
    base = json.loads(BASE_DEFINITION.read_text())
    definition_raw, definition = _read_json(
        definition_path, mode=0o444, sort_keys=True
    )
    recorded_at = _validate_definition(definition, base, validation_wall_clock=wall)
    selected, paths = selected_inputs(
        base, recorded_at=recorded_at, validation_wall_clock=wall
    )
    if definition.get("curated_inputs") != selected:
        raise OpenSeedV80Error("v80 selected input inventory differs")
    if release_path.is_symlink() or not release_path.is_dir():
        raise OpenSeedV80Error("v80 release must be an ordinary directory")
    if require_frozen and stat.S_IMODE(release_path.stat().st_mode) != 0o555:
        raise OpenSeedV80Error("v80 release root is not frozen")
    release_files = {path.name: path for path in release_path.iterdir()}
    if any(path.is_symlink() or not path.is_file() for path in release_files.values()):
        raise OpenSeedV80Error("v80 release contains a non-file")
    if require_frozen and any(
        stat.S_IMODE(path.stat().st_mode) != 0o444 for path in release_files.values()
    ):
        raise OpenSeedV80Error("v80 release file is not frozen")
    manifest_raw, manifest = _read_json(
        release_path / "manifest.json", mode=0o444, sort_keys=True
    )
    if _sha256(manifest_raw) != definition["expected_release"].get(
        "manifest_sha256"
    ):
        raise OpenSeedV80Error("v80 manifest hash differs")
    expected_release = {
        key: value
        for key, value in definition["expected_release"].items()
        if key != "manifest_sha256"
    }
    if {key: value for key, value in manifest.items() if key != "files"} != expected_release:
        raise OpenSeedV80Error("v80 expected release facts differ")
    if set(release_files) != set(manifest["files"]) | {"manifest.json"}:
        raise OpenSeedV80Error("v80 release file inventory differs")
    for filename, pin in manifest["files"].items():
        raw = (release_path / filename).read_bytes()
        if (len(raw), _sha256(raw)) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV80Error(f"v80 release pin differs: {filename}")
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
        raise OpenSeedV80Error("v80 expected summary differs")

    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v80-replay-{replay + 1}-", dir="/private/tmp"
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
                raise OpenSeedV80Error("v80 replay file inventory differs")
            for filename, frozen in release_files.items():
                if (replay_release / filename).read_bytes() != frozen.read_bytes():
                    raise OpenSeedV80Error(f"v80 offline replay differs: {filename}")
    if _guard_state() != guard:
        raise OpenSeedV80Error("v80 validation mutated accepted inputs")
    return manifest


def _path_identity(path: Path, *, directory: bool) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    expected = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if not expected:
        raise OpenSeedV80Error(f"v80 stage type differs: {path}")
    return metadata.st_dev, metadata.st_ino


def _release_identities(root: Path) -> dict[str, tuple[int, int]]:
    return {path.name: _path_identity(path, directory=False) for path in root.iterdir()}


def _assert_release_identities(
    root: Path,
    root_identity: tuple[int, int],
    members: Mapping[str, tuple[int, int]],
) -> None:
    if _path_identity(root, directory=True) != root_identity:
        raise OpenSeedV80Error("v80 release stage root identity changed")
    if _release_identities(root) != dict(members):
        raise OpenSeedV80Error("v80 release stage member identity changed")


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
        raise OpenSeedV80Error("refusing substituted v80 definition cleanup")
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
        raise OpenSeedV80Error("active v80 publication lock exists") from error
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
                raise OpenSeedV80Error("refusing substituted v80 lock cleanup")
            PUBLICATION_LOCK.unlink()


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _require_absent(label: str) -> None:
    if DEFINITION.exists() or DEFINITION.is_symlink():
        raise OpenSeedV80Error(f"{label} v80 definition collision")
    if RELEASE.exists() or RELEASE.is_symlink():
        raise OpenSeedV80Error(f"{label} v80 release collision")


def _rollback_release(release_identity: tuple[int, int], release_stage: Path) -> None:
    if _path_identity(RELEASE, directory=True) != release_identity:
        raise OpenSeedV80Error("refusing rollback of substituted v80 release")
    if release_stage.exists() or release_stage.is_symlink():
        raise OpenSeedV80Error("v80 release rollback stage is occupied")
    v69.promote_noreplace(RELEASE, release_stage)


def build_open_seed_v80(recorded_at: str | None = None) -> dict[str, Any]:
    """Build and atomically publish the two-source v79 successor."""

    if (DEFINITION.exists() or DEFINITION.is_symlink()) and (
        RELEASE.exists() or RELEASE.is_symlink()
    ):
        manifest = validate_open_seed_v80()
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
        raise OpenSeedV80Error("partial v80 final-path collision")

    guard = _guard_state()
    if guard["base_definition"] != BASE_DEFINITION_PIN:
        raise OpenSeedV80Error("accepted v79 definition pin differs")
    if (
        guard["base_manifest"] != BASE_MANIFEST_SHA256
        or guard["base_tree"] != BASE_TREE_SHA256
    ):
        raise OpenSeedV80Error("accepted v79 release pin differs")
    if guard["excluded"] != EXCLUDED_SOURCE_PINS:
        raise OpenSeedV80Error("v80 excluded source pin differs")
    target = (
        v70.parse_utc(recorded_at, label="v80 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise OpenSeedV80Error("v80 recorded_at must be future before staging")
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
                prefix="open-seed-v80-db-", dir="/private/tmp"
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
                raise OpenSeedV80Error("v80 definition stage identity changed")
            _assert_release_identities(
                release_stage, release_identity, release_members
            )
            if (
                definition_stage.read_bytes() != frozen_definition
                or v69.tree_digest(release_stage) != frozen_tree
            ):
                raise OpenSeedV80Error("v80 private stage changed while waiting")
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
                    error.add_note(f"v80 release rollback failed: {rollback_error}")
                raise
            manifest = validate_open_seed_v80(DEFINITION, RELEASE)
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
        raise OpenSeedV80Error("v80 build mutated accepted inputs")
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
    print(json.dumps(build_open_seed_v80(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
