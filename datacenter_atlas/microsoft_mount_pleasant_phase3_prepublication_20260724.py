"""Build a private Mount Pleasant Phase 3 official-source candidate.

The candidate is deliberately prepublication-only. It preserves Microsoft's
phase labels and normalizes only the March 2026 statement that preliminary
earthwork was underway for Phase 3 at Durand and Hewitt Memorial Drive. The
July soil-hauling notice remains unallocated, prospective metadata.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database

ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = (
    "microsoft-mount-pleasant-phase3-official-prepublication-2026-07-24-v1"
)
PROSPECTIVE_ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID

SOURCE_FILENAME = (
    "curated-official-2026-07-24-microsoft-mount-pleasant-"
    "phase3-earthwork.json"
)
SOURCE_FILENAMES = (SOURCE_FILENAME,)

CAPTURE_ORIGIN = Path(
    "/private/tmp/dc-microsoft-mount-pleasant-20260724.6uHVN3"
)
CAPTURE_FILE_COUNT = 4
CAPTURE_TOTAL_BYTES = 384_048
CAPTURE_TREE_SHA256 = (
    "ae6d24c31fedfb4350f67bb07aa46768e90453109dc3f96d68dea0f694e45b61"
)
CAPTURE_FILE_PINS: dict[str, tuple[int, str]] = {
    "mount-pleasant-june-news.body": (
        144_178,
        "0fdf021ce977396aa174b5011f144b4f5b731566130197dedde68631c51886d2",
    ),
    "mount-pleasant-june-news.headers": (
        1_675,
        "aec24ff085059e9caa695c5cfa46882f7052c56da441cb92f75ede83750ff4b5",
    ),
    "mount-pleasant.body": (
        237_137,
        "fbfb640af039daefec6e7507b519ed4892b3643e348cc429dd1a6d73a6dbdeea",
    ),
    "mount-pleasant.headers": (
        1_058,
        "87164c94f90ba1196feb21516e3e2dc206dea6b9d7c0fe11336ff7d8bb73a264",
    ),
}

LOCAL_UPDATE_URL = (
    "https://local.microsoft.com/blog/"
    "mount-pleasant-datacenter-project-update/"
)
JUNE_NEWS_URL = (
    "https://news.microsoft.com/source/2026/06/23/"
    "microsoft-completes-construction-on-first-datacenter-facility-"
    "in-mount-pleasant-wisconsin/"
)
LOCAL_RETRIEVED_AT = "2026-07-24T21:36:13Z"
JUNE_RETRIEVED_AT = "2026-07-24T21:36:46Z"

V97_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-22-v97.json"
V97_RELEASE = ROOT / "releases/2026-07-22-open-seed-v97"
V97_MANIFEST = V97_RELEASE / "manifest.json"
V97_ENTITIES = V97_RELEASE / "entities.csv"
V97_EVIDENCE = V97_RELEASE / "evidence.csv"
V97_SOURCE_INPUTS = V97_RELEASE / "source_inputs.json"
V97_RESOLUTION = V97_RELEASE / "resolution_candidates.json"
V97_DEFINITION_PIN = (
    120_979,
    "32f22ccc74ec6ec33dc9bc7377a83bfee83f88dff3555555fc89cb43a27d673f",
)
V97_MANIFEST_PIN = (
    20_402,
    "0a6f41f4239944df27f2ce70e81a089b91cec401f154bbae28412b27a4d00fdd",
)
V97_ENTITIES_PIN = (
    1_076_359,
    "7950a4e871d4afd0fd877e6e4f3ba9f9cbc1ffd664a611bc036896fbdba46fa1",
)
V97_EVIDENCE_PIN = (
    271_797,
    "c73263c3b27f984c8bebf76f9db31b63a22059a3774dbec9ed944ceee344f2d1",
)
V97_RELEASE_TREE_SHA256 = (
    "5136ad66f56b7474053ff3b8cbbffca1f3df3479d8a30745a1502917fa0e7954"
)
V97_CURATED_INPUT_COUNT = 519
V97_ENTITY_COUNT = 1_053
V97_EVIDENCE_COUNT = 693

EXISTING_SOURCE = (
    SOURCES_ROOT
    / "curated-official-2026-07-19-microsoft-mount-pleasant-second.json"
)
EXISTING_SOURCE_SELECTED_PATH = (
    "sources/curated-official-2026-07-19-"
    "microsoft-mount-pleasant-second.json"
)
EXISTING_SOURCE_PIN = (
    3_746,
    "9ad3498bc28f1e00993922af38f4010c2ac81756c8cc9c5da70838d5b04c649d",
)
EXISTING_SOURCE_RETRIEVED_AT = "2026-07-19T13:13:42Z"

CAMPUS_KEY = "curated:microsoft-mount-pleasant-datacenter-campus"
PHASE2_KEY = (
    "curated:microsoft-mount-pleasant-datacenter-campus:second-facility"
)
PHASE3_KEY = (
    "curated:microsoft-mount-pleasant-datacenter-campus:"
    "phase-3-durand-hewitt"
)
EVIDENCE_KEY = (
    "microsoft-local-mount-pleasant-phase3-earthwork-captured-2026-07-24"
)
EPOCH_FAIRWATER_KEY = (
    "epoch-ai:data-center:d3126a51-6b5e-5270-997c-3efa73ca63e2"
)

CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))


@dataclass(frozen=True)
class PreparedCandidate:
    source_stage: Path
    artifact_stage: Path
    recorded_at: str


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _pin(path: Path, expected: tuple[int, str]) -> None:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"missing or unsafe pinned file: {path}")
    actual = (path.stat().st_size, _sha256(path))
    if actual != expected:
        raise RuntimeError(
            f"pinned file differs: {path}: expected {expected!r}, got {actual!r}"
        )


def _evidence() -> dict[str, Any]:
    body_bytes, body_sha = CAPTURE_FILE_PINS["mount-pleasant.body"]
    header_bytes, header_sha = CAPTURE_FILE_PINS["mount-pleasant.headers"]
    return {
        "key": EVIDENCE_KEY,
        "kind": "company_disclosure",
        "title": "Microsoft Mount Pleasant datacenter project update",
        "source_url": LOCAL_UPDATE_URL,
        "publisher": "Microsoft",
        "source_family": "microsoft_local_project_updates",
        "published_at": "2023-06-30",
        "retrieved_at": LOCAL_RETRIEVED_AT,
        "license": "all-rights-reserved",
        "attribution": "Microsoft",
        "excerpt": (
            "Microsoft's March 2026 update reports preliminary earthwork at "
            "Phase 3—Durand & Hewitt Memorial Drive for future construction."
        ),
        "content_hash": body_sha,
        "metadata": {
            "capture_artifact_id": ARTIFACT_ID,
            "capture_request_id": "mount-pleasant-local-update",
            "capture_method": "credential_free_curl_location_compressed",
            "requested_url": LOCAL_UPDATE_URL,
            "effective_url": LOCAL_UPDATE_URL,
            "request_credentials_supplied": False,
            "http_status": 200,
            "content_type": "text/html; charset=UTF-8",
            "content_hash_scope": (
                "SHA-256 of the exact "
                f"{body_bytes}-byte content-decoded credential-free public "
                "response body"
            ),
            "content_hash_verification": "fetched_bytes_sha256",
            "capture_headers_scope": (
                "SHA-256 of the exact "
                f"{header_bytes}-byte raw HTTP response-header capture"
            ),
            "capture_headers_sha256": header_sha,
            "page_date_published": "2023-06-30T16:06:12+00:00",
            "page_date_modified": "2026-07-11T10:22:01+00:00",
            "phase3_heading": "Phase 3—Durand & Hewitt Memorial Drive",
            "phase3_reported_status_wording": (
                "Preliminary earthwork is underway"
            ),
            "phase3_reported_purpose": (
                "prepare the site for future construction"
            ),
            "phase3_as_of_basis": (
                "The physical update has March 2026 month precision. "
                "Month-end preserves that precision and is not an exact "
                "observation-day claim."
            ),
            "phase1_context": {
                "heading": "Phase 1—KR & 90th",
                "reported_status": "nearing completion",
                "reported_work": [
                    "final interior work in several buildings",
                    "landscaping",
                ],
                "normalized_in_this_source": False,
            },
            "phase2_context": {
                "heading": "Phase 2—KR & H",
                "reported_status": "ongoing",
                "reported_work": [
                    "foundation installation",
                    "steel erection",
                    "underground utility installation",
                ],
                "reported_completion_schedule": "early 2028",
                "normalized_in_this_source": False,
            },
            "july_2026_context": {
                "reported_action": (
                    "soil hauling between project-site areas was planned to "
                    "start on or around July 13 to support future development"
                ),
                "reported_duration": (
                    "approximately eight weeks, conditional on weather, "
                    "permitting, and construction schedules"
                ),
                "phase_assignment": None,
                "normalized_lifecycle_created": False,
            },
            "status_semantics": (
                "dated_last_observed_historical_status_current_status_unknown"
            ),
            "phase_guardrail": (
                "Phase 1, Phase 2, Phase 3, and the unallocated July soil "
                "hauling remain distinct. No building, phase crosswalk, or "
                "later status is inferred."
            ),
            "normalization_guardrail": (
                "No building count, coordinate, geometry, facility type, "
                "operating model, workload, standardized role, capacity, "
                "load, energy, generation, commissioning, operation, "
                "satellite, aerial, map-derived, or computer-vision claim "
                "is normalized."
            ),
            "rights_scope": (
                "Compact factual extraction from all-rights-reserved "
                "official bytes; raw bodies, headers, telemetry, cookies, "
                "and publisher media are not redistributed."
            ),
        },
    }


def _entity(*, project: bool) -> dict[str, Any]:
    return {
        "stable_key": PHASE3_KEY if project else CAMPUS_KEY,
        "name": (
            "Microsoft Mount Pleasant Phase 3—Durand & Hewitt Memorial Drive"
            if project
            else "Microsoft Mount Pleasant Datacenter Campus"
        ),
        "country": "United States",
        "address": "Mount Pleasant, Wisconsin, United States",
        "roles": {},
        "coordinates": None,
        "geometry": None,
        "evidence_key": EVIDENCE_KEY,
        "as_of_date": "2026-03-31",
        "method": "authoritative_locality",
        "confidence": 0.99,
    }


def expected_source_document() -> dict[str, Any]:
    document = {
        "schema_version": "1.1",
        "evidence": [_evidence()],
        "campus": _entity(project=False),
        "project": _entity(project=True),
        "lifecycle": [
            {
                "entity": "project",
                "value": "site_preparation",
                "evidence_key": EVIDENCE_KEY,
                "as_of_date": "2026-03-31",
                "method": "authoritative_physical_status_update",
                "confidence": 0.99,
            }
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }
    for entity_name in ("campus", "project"):
        entity = document[entity_name]
        if entity["coordinates"] is not None or entity["geometry"] is not None:
            raise RuntimeError("spatial boundary differs")
    return document


def expected_source_documents() -> dict[str, dict[str, Any]]:
    return {SOURCE_FILENAME: expected_source_document()}


def _validate_capture_directory(directory: Path = CAPTURE_ORIGIN) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("private capture directory is unsafe")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555:
        raise RuntimeError("private capture directory is not frozen")
    entries = {path.name: path for path in directory.iterdir()}
    if set(entries) != set(CAPTURE_FILE_PINS):
        raise RuntimeError("private capture inventory differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(entries[name], pin)
        if stat.S_IMODE(entries[name].stat().st_mode) != 0o444:
            raise RuntimeError(f"private capture is not frozen: {name}")
    if sum(pin[0] for pin in CAPTURE_FILE_PINS.values()) != CAPTURE_TOTAL_BYTES:
        raise RuntimeError("private capture byte total differs")
    if tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise RuntimeError("private capture tree differs")


def _v97_witness() -> dict[str, Any]:
    _pin(V97_DEFINITION, V97_DEFINITION_PIN)
    _pin(V97_MANIFEST, V97_MANIFEST_PIN)
    _pin(V97_ENTITIES, V97_ENTITIES_PIN)
    _pin(V97_EVIDENCE, V97_EVIDENCE_PIN)
    _pin(EXISTING_SOURCE, EXISTING_SOURCE_PIN)
    if tree_digest(V97_RELEASE) != V97_RELEASE_TREE_SHA256:
        raise RuntimeError("v97 release tree differs")

    definition = json.loads(V97_DEFINITION.read_text(encoding="utf-8"))
    manifest = json.loads(V97_MANIFEST.read_text(encoding="utf-8"))
    existing_source = json.loads(EXISTING_SOURCE.read_text(encoding="utf-8"))
    source_inputs = json.loads(V97_SOURCE_INPUTS.read_text(encoding="utf-8"))
    resolution = json.loads(V97_RESOLUTION.read_text(encoding="utf-8"))
    with V97_ENTITIES.open(encoding="utf-8", newline="") as handle:
        entity_rows = list(csv.DictReader(handle))
    with V97_EVIDENCE.open(encoding="utf-8", newline="") as handle:
        evidence_rows = list(csv.DictReader(handle))

    if (
        definition["release_id"] != "2026-07-22-open-seed-v97"
        or len(definition["curated_inputs"]) != V97_CURATED_INPUT_COUNT
        or manifest["recorded_at"] != "2026-07-22T06:06:40Z"
        or len(entity_rows) != V97_ENTITY_COUNT
        or len(evidence_rows) != V97_EVIDENCE_COUNT
    ):
        raise RuntimeError("v97 cardinality witness differs")

    selected = {
        row["path"]: row["sha256"] for row in definition["curated_inputs"]
    }
    if (
        selected.get(EXISTING_SOURCE_SELECTED_PATH)
        != EXISTING_SOURCE_PIN[1]
    ):
        raise RuntimeError("v97 Mount Pleasant source selection differs")

    by_stable = {row["stable_key"]: row for row in entity_rows}
    campus = by_stable.get(CAMPUS_KEY)
    phase2 = by_stable.get(PHASE2_KEY)
    epoch = by_stable.get(EPOCH_FAIRWATER_KEY)
    if (
        campus is None
        or campus["entity_kind"] != "campus"
        or campus["name"] != "Microsoft Mount Pleasant Datacenter Campus"
        or campus["address"] != "Mount Pleasant, Wisconsin, United States"
    ):
        raise RuntimeError("v97 official campus witness differs")
    if (
        phase2 is None
        or phase2["entity_kind"] != "project"
        or phase2["name"]
        != "Microsoft Mount Pleasant Second Datacenter Facility"
        or phase2["status"] != "under_construction"
        or phase2["status_as_of"] != "2026-06-23"
    ):
        raise RuntimeError("v97 official Phase 2 witness differs")
    if (
        epoch is None
        or epoch["name"] != "Microsoft Fairwater Wisconsin"
        or epoch["address"] != "4800 90th St, Mount Pleasant, WI 53403"
    ):
        raise RuntimeError("v97 Epoch Fairwater witness differs")

    if (
        existing_source["campus"]["stable_key"] != CAMPUS_KEY
        or existing_source["project"]["stable_key"] != PHASE2_KEY
        or existing_source["lifecycle"] != [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": (
                    "microsoft-mount-pleasant-second-facility-"
                    "construction-2026-06-23"
                ),
                "as_of_date": "2026-06-23",
                "method": "authoritative_construction_start",
                "confidence": 0.99,
            }
        ]
    ):
        raise RuntimeError("existing official source boundary differs")

    base_evidence_keys = {
        row.get("provenance", {}).get("curated_record_key")
        for row in source_inputs.get("sources", [])
        if isinstance(row, dict)
    }
    planned_collisions = sorted({CAMPUS_KEY, PHASE3_KEY} & set(by_stable))
    if planned_collisions != [CAMPUS_KEY]:
        raise RuntimeError("planned stable-key collision boundary differs")
    if EVIDENCE_KEY in base_evidence_keys:
        raise RuntimeError("planned evidence key collides with v97")

    fairwater_links = [
        row
        for row in resolution
        if {row.get("left_entity_id"), row.get("right_entity_id")}
        == {epoch["entity_id"], campus["entity_id"]}
    ]
    if len(fairwater_links) != 1:
        raise RuntimeError("v97 Fairwater resolution witness differs")
    fairwater_link = fairwater_links[0]
    if (
        fairwater_link["relationship_suggestion"] != "nearby_only"
        or fairwater_link["suggested_child_entity_id"] is not None
        or fairwater_link["suggested_parent_entity_id"] is not None
    ):
        raise RuntimeError("v97 Fairwater no-merge boundary differs")

    return {
        "release_id": definition["release_id"],
        "recorded_at": manifest["recorded_at"],
        "curated_input_count": len(definition["curated_inputs"]),
        "entity_count": len(entity_rows),
        "evidence_count": len(evidence_rows),
        "release_tree_sha256": V97_RELEASE_TREE_SHA256,
        "existing_source_selected": True,
        "existing_source_path": EXISTING_SOURCE_SELECTED_PATH,
        "existing_source_sha256": EXISTING_SOURCE_PIN[1],
        "planned_stable_key_collisions": planned_collisions,
        "planned_new_stable_keys": [PHASE3_KEY],
        "planned_evidence_key_collisions": [],
        "campus_identity_reuse": {
            "stable_key": CAMPUS_KEY,
            "integration_mode": (
                "co_select_new_phase_source_with_existing_v1_campus_reuse"
            ),
            "replace_existing_source": False,
        },
        "phase2_existing_record": {
            "stable_key": PHASE2_KEY,
            "name": phase2["name"],
            "status": phase2["status"],
            "status_as_of": phase2["status_as_of"],
            "new_entity_created": False,
            "merge_decision": "reuse_exact_existing_phase2_project",
        },
        "epoch_fairwater_record": {
            "stable_key": EPOCH_FAIRWATER_KEY,
            "name": epoch["name"],
            "address": epoch["address"],
            "relationship_suggestion": "nearby_only",
            "distance_m": fairwater_link["distance_m"],
            "merged_with_official_campus_or_any_phase": False,
        },
    }


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    witness = _v97_witness()
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-phase-assessment-v1",
        "research_date": "2026-07-24",
        "recorded_at": recorded_at,
        "candidate_count": 4,
        "governed_source_candidate_count": 1,
        "review_only_count": 3,
        "published": False,
        "candidates": [
            {
                "candidate_id": "mount-pleasant-phase3-durand-hewitt",
                "decision": (
                    "governed_prepublication_authoritative_site_preparation"
                ),
                "source_paths": [f"prospective-sources/{SOURCE_FILENAME}"],
                "campus_stable_key": CAMPUS_KEY,
                "project_stable_key": PHASE3_KEY,
                "lifecycle": "site_preparation",
                "as_of_date": "2026-03-31",
                "current_status_claimed": False,
                "new_entity_snapshots": 2,
            },
            {
                "candidate_id": "mount-pleasant-phase1-kr-90th",
                "decision": (
                    "review_only_phase_identity_and_chronology_boundary"
                ),
                "source_paths": [],
                "reported_march_status": "nearing completion",
                "reported_march_work": [
                    "final interior work in several buildings",
                    "landscaping",
                ],
                "june_official_context": (
                    "Microsoft later described its first facility as fully "
                    "operational."
                ),
                "crosswalk_to_first_facility_or_epoch_fairwater_asserted": False,
                "stable_key_created": False,
                "lifecycle_claim_created": False,
            },
            {
                "candidate_id": "mount-pleasant-phase2-kr-h",
                "decision": (
                    "review_only_exact_existing_phase2_reconciliation"
                ),
                "source_paths": [],
                "existing_project_stable_key": PHASE2_KEY,
                "reported_march_status": "ongoing",
                "reported_march_work": [
                    "foundation installation",
                    "steel erection",
                    "underground utility installation",
                ],
                "identity_basis": (
                    "The March Phase 2 work list and early-2028 schedule "
                    "match the June official second-facility disclosure."
                ),
                "new_entity_created": False,
                "new_lifecycle_claim_created": False,
                "existing_later_observation_preserved": True,
            },
            {
                "candidate_id": (
                    "mount-pleasant-july-2026-site-wide-soil-hauling"
                ),
                "decision": (
                    "review_only_prospective_unallocated_site_activity"
                ),
                "source_paths": [],
                "reported_timing": "starting on or around July 13, 2026",
                "reported_purpose": "support future development",
                "phase_assignment": None,
                "phase3_status_update_created": False,
                "currentness_inferred_from_elapsed_calendar_date": False,
                "stable_key_created": False,
                "lifecycle_claim_created": False,
            },
        ],
        "phase_distinctions": {
            "phase1": "historical March context, no new normalized entity",
            "phase2": "exact existing v97 project, no duplicate entity",
            "phase3": "new phase project with March site-preparation observation",
            "july_soil_hauling": (
                "site-wide prospective activity, not allocated to a phase"
            ),
        },
        "cross_record_reconciliation": {
            "official_mount_pleasant": witness["campus_identity_reuse"],
            "existing_phase2": witness["phase2_existing_record"],
            "epoch_fairwater": witness["epoch_fairwater_record"],
        },
    }


def _retrieval_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v4",
        "research_date": "2026-07-24",
        "recorded_at": recorded_at,
        "request_credentials_supplied": False,
        "successful_http_200_body_captures": 2,
        "raw_capture_redistributed": False,
        "capture_file_count": CAPTURE_FILE_COUNT,
        "capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "private_capture_directory": str(CAPTURE_ORIGIN),
        "private_capture_directory_frozen": True,
        "private_capture_retained_at_original_path": True,
        "trash_move_attempted": True,
        "trash_move_succeeded": False,
        "trash_move_result": (
            "host_permission_denied_retained_frozen_at_original_path"
        ),
        "controlled_captures": [
            {
                "capture_id": "mount-pleasant-local-update",
                "url": LOCAL_UPDATE_URL,
                "effective_url": LOCAL_UPDATE_URL,
                "retrieved_at": LOCAL_RETRIEVED_AT,
                "http_status": 200,
                "content_type": "text/html; charset=UTF-8",
                "claim_use": "normalized_phase3_and_review_context",
                "body": {
                    "path": "mount-pleasant.body",
                    "bytes": CAPTURE_FILE_PINS["mount-pleasant.body"][0],
                    "sha256": CAPTURE_FILE_PINS["mount-pleasant.body"][1],
                    "retained_in_artifact": False,
                },
                "headers": {
                    "path": "mount-pleasant.headers",
                    "bytes": CAPTURE_FILE_PINS["mount-pleasant.headers"][0],
                    "sha256": CAPTURE_FILE_PINS["mount-pleasant.headers"][1],
                    "retained_in_artifact": False,
                },
            },
            {
                "capture_id": "mount-pleasant-june-official-news",
                "url": JUNE_NEWS_URL,
                "effective_url": JUNE_NEWS_URL,
                "retrieved_at": JUNE_RETRIEVED_AT,
                "http_status": 200,
                "content_type": "text/html; charset=UTF-8",
                "claim_use": "dedup_and_chronology_reconciliation_only",
                "body": {
                    "path": "mount-pleasant-june-news.body",
                    "bytes": CAPTURE_FILE_PINS[
                        "mount-pleasant-june-news.body"
                    ][0],
                    "sha256": CAPTURE_FILE_PINS[
                        "mount-pleasant-june-news.body"
                    ][1],
                    "retained_in_artifact": False,
                },
                "headers": {
                    "path": "mount-pleasant-june-news.headers",
                    "bytes": CAPTURE_FILE_PINS[
                        "mount-pleasant-june-news.headers"
                    ][0],
                    "sha256": CAPTURE_FILE_PINS[
                        "mount-pleasant-june-news.headers"
                    ][1],
                    "retained_in_artifact": False,
                },
            },
        ],
        "complete_private_file_inventory": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in sorted(CAPTURE_FILE_PINS.items())
        ],
    }


def _source_paths(directory: Path) -> dict[str, Path]:
    return {SOURCE_FILENAME: directory / SOURCE_FILENAME}


def _write_sources(
    directory: Path,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    for name in SOURCE_FILENAMES:
        path = directory / name
        path.write_bytes(_canonical(documents[name]))
        path.chmod(0o600)


def _table_counts(connection: Any) -> dict[str, int]:
    tables = (
        "entities",
        "entity_snapshots",
        "evidence",
        "lifecycle_observations",
        "operating_model_observations",
        "workload_observations",
        "capacity_estimates",
    )
    return {
        table: connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        for table in tables
    }


def _offline_import(
    source_path: Path,
    recorded_at: str,
) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="mount-pleasant-phase3-prepublication-import-",
        dir="/private/tmp",
    ) as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            adapter.import_file(
                connection,
                source_path,
                recorded_at=recorded_at,
            )
        errors = validate_database(connection)
        if errors:
            raise RuntimeError(
                f"offline database validation failed: {errors!r}"
            )
        counts = _table_counts(connection)
        expected = {
            "entities": 2,
            "entity_snapshots": 2,
            "evidence": 1,
            "lifecycle_observations": 1,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
        }
        if counts != expected:
            raise RuntimeError(f"offline import counts differ: {counts!r}")
        return counts


def _compatibility_import(
    source_path: Path,
    recorded_at: str,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix="mount-pleasant-phase3-v97-compatibility-",
        dir="/private/tmp",
    ) as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        adapter.import_file(
            connection,
            EXISTING_SOURCE,
            recorded_at=EXISTING_SOURCE_RETRIEVED_AT,
        )
        for _ in range(2):
            adapter.import_file(
                connection,
                source_path,
                recorded_at=recorded_at,
            )
        errors = validate_database(connection)
        if errors:
            raise RuntimeError(
                f"compatibility database validation failed: {errors!r}"
            )
        counts = _table_counts(connection)
        expected = {
            "entities": 3,
            "entity_snapshots": 4,
            "evidence": 2,
            "lifecycle_observations": 2,
            "operating_model_observations": 1,
            "workload_observations": 0,
            "capacity_estimates": 0,
        }
        if counts != expected:
            raise RuntimeError(
                f"compatibility import counts differ: {counts!r}"
            )
        campus_rows = connection.execute(
            "SELECT COUNT(*) FROM entities WHERE stable_key = ?",
            (CAMPUS_KEY,),
        ).fetchone()[0]
        phase_keys = {
            row[0]
            for row in connection.execute(
                "SELECT stable_key FROM entities WHERE stable_key IN (?, ?)",
                (PHASE2_KEY, PHASE3_KEY),
            )
        }
        if campus_rows != 1 or phase_keys != {PHASE2_KEY, PHASE3_KEY}:
            raise RuntimeError("compatibility identity boundary differs")
        return {
            "counts": counts,
            "campus_entity_rows": campus_rows,
            "distinct_phase_project_keys": sorted(phase_keys),
            "existing_source_replaced": False,
        }


def _validate_sources(
    paths: Mapping[str, Path],
    recorded_at: str,
) -> tuple[dict[str, int], dict[str, Any]]:
    if set(paths) != set(SOURCE_FILENAMES):
        raise RuntimeError("staged source inventory differs")
    expected = expected_source_documents()
    for name in SOURCE_FILENAMES:
        path = paths[name]
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"missing or unsafe staged source: {name}")
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise RuntimeError(f"staged source mode differs: {name}")
        if path.read_bytes() != _canonical(expected[name]):
            raise RuntimeError(f"staged source differs: {name}")
    first = _offline_import(paths[SOURCE_FILENAME], recorded_at)
    second = _offline_import(paths[SOURCE_FILENAME], recorded_at)
    if first != second:
        raise RuntimeError("offline import replay differs")
    compatibility = _compatibility_import(
        paths[SOURCE_FILENAME],
        recorded_at,
    )
    return first, compatibility


def _artifact_documents(
    recorded_at: str,
    documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    witness = _v97_witness()
    source_bytes = _canonical(documents[SOURCE_FILENAME])
    source_record = {
        "path": f"prospective-sources/{SOURCE_FILENAME}",
        "bytes": len(source_bytes),
        "sha256": _sha256_bytes(source_bytes),
        "schema_version": "1.1",
        "campus_stable_key": CAMPUS_KEY,
        "project_stable_key": PHASE3_KEY,
        "evidence_records": 1,
        "lifecycle_observations": 1,
        "operating_model_observations": 0,
        "workload_observations": 0,
        "capacity_estimates": 0,
        "coordinates_present": 0,
        "geometry_present": 0,
        "disposition": "prepublication_candidate_not_published",
    }
    assessment = _candidate_assessment(recorded_at)
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v4",
        "research_date": "2026-07-24",
        "recorded_at": recorded_at,
        "published": False,
        "source_records": [source_record],
        "totals": {
            "candidate_assessments": 4,
            "governed_source_candidates": 1,
            "review_only_candidates": 3,
            "source_records": 1,
            "distinct_entity_snapshots": 2,
            "new_entities_against_v97": 1,
            "exact_existing_stable_keys_reused": 1,
            "unique_evidence_records": 1,
            "lifecycle_observations": 1,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
            "coordinates_present": 0,
            "geometry_present": 0,
        },
        "frozen_v97_non_mutation_witness": {
            "definition": {
                "path": "sources/open-seed-2026-07-22-v97.json",
                "bytes": V97_DEFINITION_PIN[0],
                "sha256": V97_DEFINITION_PIN[1],
            },
            "manifest": {
                "path": "releases/2026-07-22-open-seed-v97/manifest.json",
                "bytes": V97_MANIFEST_PIN[0],
                "sha256": V97_MANIFEST_PIN[1],
            },
            "entities": {
                "path": "releases/2026-07-22-open-seed-v97/entities.csv",
                "bytes": V97_ENTITIES_PIN[0],
                "sha256": V97_ENTITIES_PIN[1],
            },
            "evidence": {
                "path": "releases/2026-07-22-open-seed-v97/evidence.csv",
                "bytes": V97_EVIDENCE_PIN[0],
                "sha256": V97_EVIDENCE_PIN[1],
            },
            **witness,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v97_mutated": False,
            "release_integration": "none",
            "federation_integration": "none",
            "identity_integration": "none",
            "construction_master_integration": "none",
            "map_integration": "none",
            "ledger_integration": "none",
        },
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-and-disposition-v3",
        "recorded_at": recorded_at,
        "publisher": "Microsoft",
        "source_license": "all-rights-reserved",
        "artifact_is_hash_and_factual_extract_only": True,
        "raw_capture_redistributed": False,
        "raw_response_bodies_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "publisher_media_retained_in_artifact": False,
        "private_capture_directory": str(CAPTURE_ORIGIN),
        "private_capture_directory_frozen": True,
        "private_capture_file_count": CAPTURE_FILE_COUNT,
        "private_capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "private_capture_tree_sha256": CAPTURE_TREE_SHA256,
        "trash_move_attempted": True,
        "trash_move_succeeded": False,
        "trash_move_result": (
            "host_permission_denied_retained_frozen_at_original_path"
        ),
        "publication_performed": False,
    }
    readme = f"""# Microsoft Mount Pleasant Phase 3 prepublication candidate

This private artifact assesses four phase-scoped observations from official
Microsoft pages. Exactly one governed source candidate is staged: the March
2026 statement that preliminary earthwork was underway for Phase 3—Durand &
Hewitt Memorial Drive. It is a dated `site_preparation` observation whose
current status remains unknown.

Phase 1 remains historical review context because its March "nearing
completion" wording precedes Microsoft's separate June first-facility
operational disclosure, and this tranche does not assert a crosswalk to the
Epoch Fairwater row. Phase 2 reuses the exact existing v97 second-facility
project identity; no duplicate entity or older lifecycle row is created. The
July soil-hauling notice remains prospective, site-wide metadata and is not
assigned to Phase 3.

The source adds no building count, coordinate, geometry, role, facility type,
operating model, workload, capacity, load, energy, generation, commissioning,
operation, satellite, aerial, map-derived, or computer-vision claim. Raw
all-rights-reserved captures are represented only by hashes and compact facts.

Status: `PREPUBLICATION_CANDIDATE_BUILT_NOT_PUBLISHED` as of {recorded_at}.
"""
    return {
        "README.md": readme.encode(),
        "candidate-assessment.json": _canonical(assessment),
        "retrieval-inventory.json": _canonical(
            _retrieval_inventory(recorded_at)
        ),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _write_artifact(
    directory: Path,
    recorded_at: str,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    payloads = _artifact_documents(recorded_at, documents)
    for name in CONTENT_FILES:
        path = directory / name
        path.write_bytes(payloads[name])
        path.chmod(0o600)
    rows = [
        {
            "path": name,
            "bytes": (directory / name).stat().st_size,
            "sha256": _sha256(directory / name),
        }
        for name in CONTENT_FILES
    ]
    manifest = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-prepublication-manifest-v1",
        "recorded_at": recorded_at,
        "files": rows,
        "tree_sha256": _sha256_bytes(_canonical(rows)),
        "closed_file_set": sorted(CLOSED_FILES),
        "candidate_assessments": 4,
        "curated_source_candidates": 1,
        "review_only_candidates": 3,
        "raw_capture_redistributed": False,
        "published": False,
        "publisher_function_present": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
        "federation_integration": "none",
        "identity_integration": "none",
        "construction_master_integration": "none",
        "map_integration": "none",
        "ledger_integration": "none",
    }
    manifest_path = directory / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    manifest_path.chmod(0o600)
    sidecar = directory / "manifest.sha256"
    sidecar.write_text(
        f"{_sha256(manifest_path)}  manifest.json\n",
        encoding="utf-8",
    )
    sidecar.chmod(0o600)


def _assert_no_publication() -> None:
    paths = (
        PROSPECTIVE_ARTIFACT,
        *(SOURCES_ROOT / name for name in SOURCE_FILENAMES),
    )
    collisions = [
        str(path) for path in paths if path.exists() or path.is_symlink()
    ]
    if collisions:
        raise RuntimeError(
            f"prospective final-path collision: {collisions!r}"
        )


def validate_candidate(
    artifact_stage: Path,
    source_stage: Path,
    recorded_at: str,
) -> dict[str, Any]:
    _assert_no_publication()
    _validate_capture_directory()
    witness = _v97_witness()
    if witness["planned_stable_key_collisions"] != [CAMPUS_KEY]:
        raise RuntimeError("expected campus reuse collision differs")
    for stage_name, stage in (
        ("artifact", artifact_stage),
        ("source", source_stage),
    ):
        if stage.is_symlink() or not stage.is_dir():
            raise RuntimeError(f"{stage_name} stage is missing or unsafe")
        if stat.S_IMODE(stage.stat().st_mode) != 0o700:
            raise RuntimeError(f"{stage_name} stage mode differs")

    source_counts, compatibility = _validate_sources(
        _source_paths(source_stage),
        recorded_at,
    )
    artifact_entries = {
        path.name: path for path in artifact_stage.iterdir()
    }
    if set(artifact_entries) != CLOSED_FILES:
        raise RuntimeError("candidate artifact closed file set differs")
    for name, path in artifact_entries.items():
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"unsafe artifact member: {name}")
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise RuntimeError(f"artifact member mode differs: {name}")

    manifest_path = artifact_entries["manifest.json"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest["published"] is not False
        or manifest["publisher_function_present"] is not False
        or manifest["curated_source_candidates"] != 1
        or manifest["review_only_candidates"] != 3
        or manifest["identity_integration"] != "none"
        or manifest["ledger_integration"] != "none"
    ):
        raise RuntimeError("prepublication manifest boundary differs")
    sidecar = artifact_entries["manifest.sha256"].read_text(encoding="utf-8")
    if sidecar != f"{_sha256(manifest_path)}  manifest.json\n":
        raise RuntimeError("manifest sidecar differs")
    listed = {row["path"]: row for row in manifest["files"]}
    if set(listed) != set(CONTENT_FILES):
        raise RuntimeError("manifest file inventory differs")
    for name, row in listed.items():
        path = artifact_entries[name]
        if (
            row["bytes"] != path.stat().st_size
            or row["sha256"] != _sha256(path)
        ):
            raise RuntimeError(f"manifest member pin differs: {name}")

    assessment = json.loads(
        artifact_entries["candidate-assessment.json"].read_text(
            encoding="utf-8"
        )
    )
    if (
        assessment["candidate_count"] != 4
        or assessment["governed_source_candidate_count"] != 1
        or assessment["review_only_count"] != 3
        or assessment["published"] is not False
    ):
        raise RuntimeError("candidate-assessment counts differ")
    _assert_no_publication()
    return {
        **manifest,
        "offline_import_counts": source_counts,
        "v97_compatibility_import": compatibility,
        "v97_witness": witness,
    }


def prepare_candidate(*, recorded_at: str | None = None) -> PreparedCandidate:
    _assert_no_publication()
    _validate_capture_directory()
    timestamp = recorded_at or datetime.now(UTC).isoformat().replace(
        "+00:00",
        "Z",
    )
    source_stage = Path(
        tempfile.mkdtemp(
            prefix=".microsoft-mount-pleasant-phase3-prepublication-sources.",
            dir=SOURCES_ROOT,
        )
    )
    artifact_stage = Path(
        tempfile.mkdtemp(
            prefix=".microsoft-mount-pleasant-phase3-prepublication-artifact.",
            dir=ARTIFACT_ROOT,
        )
    )
    source_stage.chmod(0o700)
    artifact_stage.chmod(0o700)
    try:
        documents = expected_source_documents()
        _write_sources(source_stage, documents)
        _write_artifact(artifact_stage, timestamp, documents)
        validate_candidate(
            artifact_stage,
            source_stage,
            timestamp,
        )
    except BaseException:
        shutil.rmtree(source_stage, ignore_errors=True)
        shutil.rmtree(artifact_stage, ignore_errors=True)
        raise
    return PreparedCandidate(source_stage, artifact_stage, timestamp)


def candidate_result(prepared: PreparedCandidate) -> dict[str, Any]:
    manifest = validate_candidate(
        prepared.artifact_stage,
        prepared.source_stage,
        prepared.recorded_at,
    )
    return {
        "status": "PREPUBLICATION_CANDIDATE_BUILT_NOT_PUBLISHED",
        "artifact_id": ARTIFACT_ID,
        "recorded_at": prepared.recorded_at,
        "source_stage": str(prepared.source_stage),
        "artifact_stage": str(prepared.artifact_stage),
        "source_stage_tree_sha256": tree_digest(prepared.source_stage),
        "artifact_stage_tree_sha256": tree_digest(prepared.artifact_stage),
        "candidate_assessments": manifest["candidate_assessments"],
        "curated_source_candidates": manifest["curated_source_candidates"],
        "review_only_candidates": manifest["review_only_candidates"],
        "offline_import_counts": manifest["offline_import_counts"],
        "v97_compatibility_import": manifest["v97_compatibility_import"],
        "planned_stable_key_collisions": manifest["v97_witness"][
            "planned_stable_key_collisions"
        ],
        "planned_new_stable_keys": manifest["v97_witness"][
            "planned_new_stable_keys"
        ],
        "published": False,
        "prospective_final_artifact_exists": PROSPECTIVE_ARTIFACT.exists(),
        "prospective_final_sources_exist": {
            name: (SOURCES_ROOT / name).exists() for name in SOURCE_FILENAMES
        },
        "open_seed_successor_created": False,
        "release_integration": "none",
        "federation_integration": "none",
        "identity_integration": "none",
        "construction_master_integration": "none",
        "map_integration": "none",
        "ledger_integration": "none",
    }


def main() -> int:
    prepared = prepare_candidate()
    print(json.dumps(candidate_result(prepared), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
