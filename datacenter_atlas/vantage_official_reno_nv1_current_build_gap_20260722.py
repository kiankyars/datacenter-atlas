"""Publish the bounded Vantage NV1/NV12 official-source tranche.

The source record contains one newly keyed NV1 campus and one NV12 project.
NV12 is last observed at shell stage when McCarthy reported its top-out. Only
the exact project-specific 64 MW critical-IT value is normalized. NV11 remains
context-only and all campus, phase, substation, water, and schedule figures are
retained only as non-additive metadata.
"""

from __future__ import annotations

from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence

from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from . import coreweave_official_lancaster_current_build_gap_20260722 as prior
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "vantage-official-reno-nv1-current-build-gap-2026-07-22-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".vantage-official-reno-nv1-current-build-gap.lock"

SOURCE_FILENAME = "curated-official-2026-07-22-vantage-nv1-reno-nv12-current-build.json"
SOURCE_FILENAMES = (SOURCE_FILENAME,)

CAPTURE_ORIGIN = Path("/private/tmp/dc-vantage-nv1-20260722.OHFtAs")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-vantage-nv1-20260722.OHFtAs")
CAPTURE_FILE_COUNT = 8
CAPTURE_TOTAL_BYTES = 9_532_448
CAPTURE_TREE_SHA256 = "2482615652b091c8092c39a36874c11137e5a64aa298782df2d1fd3c29589b8f"

V90_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v90.json"
V90_RELEASE = ROOT / "releases/2026-07-21-open-seed-v90"
V90_MANIFEST = V90_RELEASE / "manifest.json"
V90_ENTITIES = V90_RELEASE / "entities.csv"
V90_PINS = {
    V90_DEFINITION: (
        107_554,
        "3e224d0560e7f82fc31f7bdf6eb6b723ce50ad8423e2296de8c509b75c0fbdda",
    ),
    V90_MANIFEST: (
        15_902,
        "40be71c613c74e4e843c5c60ad85ce172c206f72350df5a0996b7e971ca54b66",
    ),
    V90_ENTITIES: (
        1_014_802,
        "732b1e8414532bf5ff9498b694678c9f4e6cacb83a2df4cadb7d135141d49aa8",
    ),
}
V90_TREE_SHA256 = "18cda7d054789dde956a393959cde79349f835927b1e757da364e15d974b78f3"
V90_INPUT_COUNT = 477
V90_ENTITY_COUNT = 973

CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

_canonical = prior._canonical
_sha256 = prior._sha256
_sha256_bytes = prior._sha256_bytes
_instant = prior._instant
_pin = prior._pin
_fsync_regular = prior._fsync_regular
_fsync_directory = prior._fsync_directory
_promote_noreplace = prior._promote_noreplace


CAPTURE_FILE_PINS: dict[str, tuple[int, str]] = {
    "mccarthy-nv1-construction-headers.txt": (
        2_745,
        "fb6e9ccf032b27aea687382153733c45513b4213f7e3d0e0fa80f9cbaa7267c3",
    ),
    "mccarthy-nv1-construction.body": (
        169_685,
        "a3b121a3498237a40979fa2897c011f640131ece94c4423cab0ae65ca34451ec",
    ),
    "mccarthy-nv12-topping-headers.txt": (
        2_747,
        "9c6ee2d563895ff24564de4e71e3231a3369af7b8abef515e868fcae044b7895",
    ),
    "mccarthy-nv12-topping.body": (
        143_190,
        "deecfc377d04faf2afefc8dd792c235f63a0cf606fbe7fd259166211473177ce",
    ),
    "vantage-reno-campus-headers.txt": (
        1_988,
        "b56f3aa4983dc4302035b29285e85a968fe5f708068bf7ae7d28bad2d53747da",
    ),
    "vantage-reno-campus.body": (
        220_346,
        "c778f4e3ab0d7f33d0b0feed852b316b23c3babef801d1c9096eac99604456e2",
    ),
    "vantage-reno-datasheet-headers.txt": (
        746,
        "8fb54f415bdb75fc344e0adc2b4376688178ec698df1f6df85554fd7852ffb4d",
    ),
    "vantage-reno-datasheet.body": (
        8_991_001,
        "aa855064de766d4ccf81eea26aef6d681aacef791178a9cd49d2290ca5edc81c",
    ),
}


@dataclass(frozen=True)
class Capture:
    capture_id: str
    file_stem: str
    url: str
    retrieved_at: str
    published_at: str | None
    content_type: str
    use: str


CAPTURES = (
    Capture(
        "mccarthy_nv12_topping",
        "mccarthy-nv12-topping",
        "https://www.mccarthy.com/es/node/4806",
        "2026-07-22T01:34:59Z",
        "2026-01-22",
        "text/html; charset=UTF-8",
        "normalized_nv12_status_and_capacity",
    ),
    Capture(
        "mccarthy_nv1_construction",
        "mccarthy-nv1-construction",
        "https://www.mccarthy.com/insights/how-mccarthys-vantage-data-centers-nv1-team-is-shaping-the-future-of-mission-critical",
        "2026-07-22T01:34:59Z",
        "2025-10-27",
        "text/html; charset=UTF-8",
        "normalized_campus_construction_context",
    ),
    Capture(
        "vantage_reno_campus",
        "vantage-reno-campus",
        "https://vantage-dc.com/data-center-locations/north-america/reno-nevada/",
        "2026-07-22T01:34:59Z",
        None,
        "text/html; charset=UTF-8",
        "normalized_identity_context",
    ),
    Capture(
        "vantage_reno_datasheet",
        "vantage-reno-datasheet",
        "https://vantage-dc.com/wp-content/uploads/2025/07/VDC_DataSheet_Reno_EN.pdf",
        "2026-07-22T01:35:06Z",
        None,
        "application/pdf",
        "campus_context_only",
    ),
)
CAPTURE_BY_ID = {capture.capture_id: capture for capture in CAPTURES}


@dataclass(frozen=True)
class EvidenceSpec:
    key: str
    capture_id: str
    title: str
    publisher: str
    source_family: str
    kind: str
    excerpt: str
    factual_extract: Mapping[str, Any]


EVIDENCE = (
    EvidenceSpec(
        "mccarthy-vantage-nv12-topped-out-2026-01-22",
        "mccarthy_nv12_topping",
        "McCarthy celebrates topping out Vantage NV12",
        "McCarthy Building Companies",
        "mccarthy_vantage_nv1",
        "company_disclosure",
        "McCarthy reports that NV12, the second planned NV1 facility, topped out and is a 64 MW critical-IT data center.",
        {
            "physical_status_as_reported": "NV12 completed the topping-out milestone.",
            "project_capacity_as_reported": "NV12 is the second 64 MW critical-IT data center on the campus.",
            "phase_capacity_context_not_normalized": "Phase I provides 128 MW combined critical IT across NV11 and NV12; it is non-additive context and is not allocated again.",
            "campus_start_context_not_project_status": "The campus broke ground in May 2024; that date is not used as an NV12-specific lifecycle observation.",
            "forecast_context_not_status": "Phased NV12 turnover beginning December 2027 and final completion in early 2029 are forecasts, not current status.",
            "nv11_guardrail": "The statement following turnover of NV11 creates no NV11 status, operation, lifecycle, capacity, or entity claim in this tranche.",
            "role_context_not_normalized": "McCarthy is described as general contractor and Vantage as developer context; roles remain unnormalized.",
            "status_semantics": "Dated last-observed shell milestone; no persistence after 2026-01-22 is asserted.",
        },
    ),
    EvidenceSpec(
        "mccarthy-vantage-nv1-construction-narrative-2025-10-27",
        "mccarthy_nv1_construction",
        "How McCarthy's Vantage NV1 team is shaping mission-critical construction",
        "McCarthy Building Companies",
        "mccarthy_vantage_nv1",
        "company_disclosure",
        "McCarthy describes active construction of the four-building Vantage NV1 campus outside Reno.",
        {
            "physical_context_as_reported": "McCarthy says its team is building the NV1 campus and describes ongoing site work.",
            "campus_capacity_context_not_normalized": "Projected 224 MW across four buildings is campus-level context and is not allocated to NV12.",
            "site_scale_context_not_normalized": "The 137-acre site and 30-acre building pad are metadata only.",
            "type_workload_guardrail": "Mission-critical and data-center language creates no normalized type or workload observation.",
        },
    ),
    EvidenceSpec(
        "vantage-reno-nv1-campus-page-observed-2026-07-22",
        "vantage_reno_campus",
        "Reno NV1 data center campus",
        "Vantage Data Centers",
        "vantage_nv1_campus",
        "company_disclosure",
        "Vantage identifies its Storey County NV1 campus at 1121 USA Parkway and describes four planned facilities with 224 MW combined critical IT.",
        {
            "identity_scope": "Reno NV1 is Vantage's four-facility campus in Storey County, Nevada, with the address 1121 USA Parkway, Sparks, NV 89437.",
            "campus_capacity_context_not_normalized": "224 MW combined campus critical IT is non-additive context and is not allocated to NV12.",
            "substation_context_not_normalized": "A private 500 MW on-site substation is infrastructure context, not critical IT, current draw, installed or energized project capacity, generation, or annual energy.",
            "nv11_guardrail": "The first-facility opening forecast creates no NV11 current-status or operation claim.",
            "water_guardrail": "Near-zero WUE design language is not normalized as PUE, WUE, water use, or measured performance.",
            "type_workload_guardrail": "AI, GPU, carrier-neutral, and hyperscale wording creates no normalized facility type or workload.",
        },
    ),
    EvidenceSpec(
        "vantage-reno-nv1-datasheet-observed-2026-07-22",
        "vantage_reno_datasheet",
        "Reno, Nevada data center campus overview",
        "Vantage Data Centers",
        "vantage_nv1_campus",
        "company_disclosure",
        "Vantage's data sheet describes the fully developed four-facility campus and its 224 MW combined critical-IT specification.",
        {
            "campus_capacity_context_not_normalized": "The repeated 224 MW figure is campus-level and is not added to the NV12 project row.",
            "substation_context_not_normalized": "The 500 MW substation figure remains non-capacity infrastructure metadata.",
            "water_guardrail": "The design WUE statement is not normalized or treated as measured performance.",
        },
    ),
)
EVIDENCE_BY_KEY = {evidence.key: evidence for evidence in EVIDENCE}
EVIDENCE_KEYS = tuple(evidence.key for evidence in EVIDENCE)

CAMPUS_KEY = "curated:vantage-nv1-reno-storey-county-campus"
PROJECT_KEY = "curated:vantage-nv1-reno-storey-county-campus:nv12-current-build"
PRIMARY_EVIDENCE_KEY = "mccarthy-vantage-nv12-topped-out-2026-01-22"


def _capture_metadata(capture: Capture) -> dict[str, Any]:
    body_pin = CAPTURE_FILE_PINS[f"{capture.file_stem}.body"]
    headers_pin = CAPTURE_FILE_PINS[f"{capture.file_stem}-headers.txt"]
    return {
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture.capture_id,
        "capture_method": "credential_free_curl_location",
        "requested_url": capture.url,
        "effective_url": capture.url,
        "request_credentials_supplied": False,
        "http_status": 200,
        "content_type": capture.content_type,
        "content_hash_scope": f"SHA-256 of the exact {body_pin[0]}-byte credential-free public response body",
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_headers_scope": f"SHA-256 of the exact {headers_pin[0]}-byte raw HTTP response-header capture",
        "capture_headers_sha256": headers_pin[1],
        "status_semantics": "dated_last_observed_current_status_unknown",
        "rights_scope": "Compact factual extraction from all-rights-reserved official bytes; raw bodies, headers, telemetry, and publisher media are not redistributed.",
        "normalization_guardrail": "Only NV12's exact 64 MW planned critical-IT value and dated shell lifecycle are normalized; no other capacity, energy, PUE, WUE, type, workload, operating model, role, coordinate, geometry, satellite, aerial, map-click, or computer-vision claim is normalized.",
    }


def _evidence(spec: EvidenceSpec) -> dict[str, Any]:
    capture = CAPTURE_BY_ID[spec.capture_id]
    return {
        "key": spec.key,
        "kind": spec.kind,
        "title": spec.title,
        "source_url": capture.url,
        "publisher": spec.publisher,
        "source_family": spec.source_family,
        "published_at": capture.published_at,
        "retrieved_at": capture.retrieved_at,
        "license": "all-rights-reserved",
        "attribution": spec.publisher,
        "excerpt": spec.excerpt,
        "content_hash": CAPTURE_FILE_PINS[f"{capture.file_stem}.body"][1],
        "metadata": {**_capture_metadata(capture), **spec.factual_extract},
    }


def _entity(*, project: bool) -> dict[str, Any]:
    return {
        "stable_key": PROJECT_KEY if project else CAMPUS_KEY,
        "name": "Vantage NV12 Current Build" if project else "Vantage Reno NV1 Campus",
        "country": "United States",
        "address": "1121 USA Parkway, Sparks, Nevada 89437, United States",
        "roles": {},
        "coordinates": None,
        "geometry": None,
        "evidence_key": PRIMARY_EVIDENCE_KEY,
        "as_of_date": "2026-01-22",
        "method": "authoritative_locality",
        "confidence": 0.99,
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    return {
        SOURCE_FILENAME: {
            "schema_version": "1.1",
            "evidence": [_evidence(EVIDENCE_BY_KEY[key]) for key in EVIDENCE_KEYS],
            "campus": _entity(project=False),
            "project": _entity(project=True),
            "lifecycle": [
                {
                    "entity": "project",
                    "value": "shell",
                    "evidence_key": PRIMARY_EVIDENCE_KEY,
                    "as_of_date": "2026-01-22",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
            "operating_models": [],
            "workloads": [],
            "capacities": [
                {
                    "entity": "project",
                    "metric": "critical_it_mw",
                    "stage": "planned",
                    "unit": "MW",
                    "low": 64,
                    "base": 64,
                    "high": 64,
                    "method": "reported",
                    "confidence": 0.99,
                    "evidence_key": PRIMARY_EVIDENCE_KEY,
                    "as_of_date": "2026-01-22",
                    "target_date": None,
                    "notes": "Planned critical-IT capacity for NV12 only. It is not the 128 MW Phase I total, the 224 MW campus total, 500 MW substation capacity, gross facility demand, current draw, installed or energized capacity, generation, annual energy, or measured consumption.",
                }
            ],
        }
    }


def _source_records(documents: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    document = documents[SOURCE_FILENAME]
    payload = _canonical(document)
    return [
        {
            "path": f"sources/{SOURCE_FILENAME}",
            "bytes": len(payload),
            "sha256": _sha256_bytes(payload),
            "schema_version": "1.1",
            "country": "United States",
            "campus_stable_key": CAMPUS_KEY,
            "project_stable_key": PROJECT_KEY,
            "evidence_records": len(EVIDENCE),
            "lifecycle_observations": 1,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 1,
            "coordinates_present": 0,
            "geometry_present": 0,
            "disposition": "seed_eligible_nv12_topped_out_exact_capacity",
            "seed_eligible": True,
            "seeded": False,
        }
    ]


def _planned_keys(documents: Mapping[str, Mapping[str, Any]]) -> tuple[set[str], set[str]]:
    stable = {
        document[entity]["stable_key"]
        for document in documents.values()
        for entity in ("campus", "project")
    }
    evidence = {
        row["key"] for document in documents.values() for row in document["evidence"]
    }
    return stable, evidence


def _collision_witness(documents: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    for target, pin in V90_PINS.items():
        _pin(target, pin)
    if tree_digest(V90_RELEASE) != V90_TREE_SHA256:
        raise RuntimeError("v90 release tree differs")
    definition = json.loads(V90_DEFINITION.read_text(encoding="utf-8"))
    selected = definition.get("curated_inputs")
    if not isinstance(selected, list) or len(selected) != V90_INPUT_COUNT:
        raise RuntimeError("v90 selected input inventory differs")
    planned_stable, planned_evidence = _planned_keys(documents)
    with V90_ENTITIES.open(encoding="utf-8", newline="") as stream:
        base_rows = list(csv.DictReader(stream))
    if len(base_rows) != V90_ENTITY_COUNT:
        raise RuntimeError("v90 entity count differs")
    base_stable = {row["stable_key"] for row in base_rows}
    if planned_stable & base_stable:
        raise RuntimeError("planned Vantage stable key collides with v90")
    exact_address_hits = [
        row for row in base_rows if "1121 usa parkway" in (row.get("address") or "").lower()
    ]
    if exact_address_hits:
        raise RuntimeError("v90 contains exact Vantage NV1 address")
    source_inputs = json.loads((V90_RELEASE / "source_inputs.json").read_text(encoding="utf-8")).get("sources")
    base_evidence = {
        key
        for row in source_inputs or []
        if isinstance(row, dict)
        for key in [row.get("provenance", {}).get("curated_record_key")]
        if isinstance(key, str)
    }
    if planned_evidence & base_evidence:
        raise RuntimeError("planned Vantage evidence key collides with v90")
    google_storey = [
        row
        for row in base_rows
        if row["stable_key"] == "epoch-ai:data-center:4ffff708-2ef2-5bc5-8c8f-a54332398912"
    ]
    if len(google_storey) != 1 or google_storey[0]["name"] != "Google Storey County":
        raise RuntimeError("distinct Google Storey County witness differs")
    return {
        "v90_selected_input_count": len(selected),
        "v90_entity_count": len(base_rows),
        "planned_distinct_stable_keys": len(planned_stable),
        "planned_distinct_evidence_keys": len(planned_evidence),
        "exact_v90_stable_key_collisions": [],
        "exact_v90_evidence_key_collisions": [],
        "exact_v90_address_matches": [],
        "exact_existing_identity_keys_reused": [],
        "distinct_storey_county_boundary": "Vantage NV1 is not merged with the separate Google Storey County record.",
        "identity_resolution": "New curated NV1 campus and NV12 project keys are used; no existing capacity, status, role, coordinate, or geometry is inherited.",
    }


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-current-build-assessment-v1",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "candidate_count": 2,
        "seed_eligible_candidate_count": 1,
        "seed_eligible_source_record_count": 1,
        "review_only_count": 1,
        "regional_completeness_claimed": False,
        "candidates": [
            {
                "candidate_id": "vantage-nv1-nv12-current-build",
                "decision": "seed_eligible_nv12_topped_out_exact_capacity",
                "source_paths": [f"sources/{SOURCE_FILENAME}"],
                "campus_stable_key": CAMPUS_KEY,
                "project_stable_key": PROJECT_KEY,
                "existing_atlas_identity_link": None,
                "lifecycle": {
                    "status": "shell",
                    "as_of_date": "2026-01-22",
                    "method": "authoritative_physical_status_update",
                    "current_status_persisted": False,
                },
                "normalized_capacity": {
                    "entity": "project",
                    "metric": "critical_it_mw",
                    "stage": "planned",
                    "low": 64,
                    "base": 64,
                    "high": 64,
                    "unit": "MW",
                    "non_additive": True,
                },
                "reported_context_not_normalized": [
                    {"value": 128, "unit": "MW", "scope": "Phase I combined critical IT across NV11 and NV12", "reason": "contains the normalized NV12 64 MW and must not be added"},
                    {"value": 224, "unit": "MW", "scope": "fully developed four-facility campus critical IT", "reason": "campus aggregate not project allocation"},
                    {"value": 500, "unit": "MW", "scope": "private on-site substation", "reason": "infrastructure rating, not critical IT or current load"},
                ],
                "forecast_context_not_status": {
                    "phased_turnover_begins": "2027-12",
                    "final_completion": "early 2029",
                },
                "role_context_not_normalized": {
                    "mccarthy": "contractor metadata only",
                    "vantage": "developer/operator context metadata only",
                },
                "withheld": [
                    "energy or generation",
                    "PUE or WUE",
                    "facility type or workload",
                    "operating model or standardized role",
                    "coordinates or geometry",
                    "satellite, aerial, or computer-vision claim",
                    "current-status persistence",
                    "unique physical-site claim",
                    "NV11 current status or operation",
                ],
            },
            {
                "candidate_id": "vantage-nv1-nv11-context",
                "decision": "review_only_context_no_current_status_claim",
                "source_paths": [],
                "seed_eligible": False,
                "official_factual_extract": "McCarthy refers to turnover of NV11 and Vantage gives a forecast for the first facility, but this tranche does not establish or persist NV11's current status or operation.",
                "stable_key_created": False,
                "lifecycle_claim_created": False,
                "operation_claim_created": False,
                "capacity_claim_created": False,
            },
        ],
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "request_credentials_supplied": False,
        "controlled_capture_count": len(CAPTURES),
        "successful_http_200_body_captures": len(CAPTURES),
        "failed_http_body_captures": 0,
        "raw_capture_redistributed": False,
        "capture_file_count": CAPTURE_FILE_COUNT,
        "capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "controlled_captures": [
            {
                "capture_id": capture.capture_id,
                "requested_url": capture.url,
                "effective_url": capture.url,
                "retrieved_at": capture.retrieved_at,
                "body": {
                    "path": f"{capture.file_stem}.body",
                    "bytes": CAPTURE_FILE_PINS[f"{capture.file_stem}.body"][0],
                    "sha256": CAPTURE_FILE_PINS[f"{capture.file_stem}.body"][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "headers": {
                    "path": f"{capture.file_stem}-headers.txt",
                    "bytes": CAPTURE_FILE_PINS[f"{capture.file_stem}-headers.txt"][0],
                    "sha256": CAPTURE_FILE_PINS[f"{capture.file_stem}-headers.txt"][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "http_status": 200,
                "content_type": capture.content_type,
                "request_credentials_supplied": False,
                "claim_use": capture.use,
            }
            for capture in CAPTURES
        ],
        "complete_private_file_inventory": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in sorted(CAPTURE_FILE_PINS.items())
        ],
    }


def _file_tree(rows: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_bytes((json.dumps(rows, indent=2, sort_keys=True) + "\n").encode())


def _artifact_documents(recorded_at: str, source_documents: Mapping[str, Mapping[str, Any]]) -> dict[str, bytes]:
    collision = _collision_witness(source_documents)
    source_records = _source_records(source_documents)
    totals = {
        "candidate_assessments": 2,
        "source_records": 1,
        "seed_eligible_candidates": 1,
        "seed_eligible_source_records": 1,
        "review_only_candidates": 1,
        "distinct_campuses_in_source_records": 1,
        "projects": 1,
        "distinct_entities_in_source_records": 2,
        "new_entities_against_v90": 2,
        "exact_existing_identity_keys_reused": 0,
        "source_document_entity_snapshots": 2,
        "unique_imported_entity_snapshots": 2,
        "source_document_evidence_references": 4,
        "unique_evidence_records": 4,
        "lifecycle_observations": 1,
        "operating_model_observations": 0,
        "workload_observations": 0,
        "capacity_estimates": 1,
        "normalized_critical_it_mw_sum": 64,
        "energy_estimates": 0,
        "coordinates_present": 0,
        "geometry_present": 0,
        "satellite_observations": 0,
        "computer_vision_observations": 0,
        "unique_physical_sites_claimed": 0,
    }
    readme = f"""# Vantage NV1/NV12 official-source tranche

This immutable artifact publishes one newly keyed Vantage NV1 campus and one NV12 project. McCarthy's January 22, 2026 disclosure reports that NV12 topped out, supporting one dated shell-stage lifecycle observation. Its exact 64 MW project critical-IT value is normalized once as planned capacity.

The 128 MW Phase I value, 224 MW campus value, and 500 MW substation rating remain non-additive metadata only. NV11 is context-only and receives no entity, current-status, operation, lifecycle, or capacity claim. Forecast turnover and completion dates are metadata only. No energy, generation, PUE, WUE, facility type, workload, operating model, standardized role, coordinate, geometry, satellite, aerial, map-click, computer-vision, current-status persistence, or unique-site claim is emitted.

All source and artifact bytes were staged before {recorded_at}; final paths were absent until that instant and promoted without replacement. Raw all-rights-reserved captures are represented only by exact hashes and retrieval facts. The intact {CAPTURE_FILE_COUNT}-file raw capture directory was moved to recoverable Trash only after successful source publication.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "regional_completeness_claimed": False,
        "source_records": source_records,
        "totals": totals,
        "frozen_v90_non_mutation_witness": {
            "definition": {"path": "sources/open-seed-2026-07-21-v90.json", "bytes": V90_PINS[V90_DEFINITION][0], "sha256": V90_PINS[V90_DEFINITION][1]},
            "release_manifest": {"path": "releases/2026-07-21-open-seed-v90/manifest.json", "bytes": V90_PINS[V90_MANIFEST][0], "sha256": V90_PINS[V90_MANIFEST][1]},
            "release_entities": {"path": "releases/2026-07-21-open-seed-v90/entities.csv", "bytes": V90_PINS[V90_ENTITIES][0], "sha256": V90_PINS[V90_ENTITIES][1]},
            "release_tree_sha256": V90_TREE_SHA256,
            **collision,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v90_mutated": False,
            "release_integration": "none",
            "construction_master_integration": "none",
            "map_integration": "none",
            "federation_integration": "none",
            "coverage_integration": "none",
            "review_integration": "none",
        },
        "publication_contract": {
            "version": 1,
            "all_source_and_artifact_bytes_staged_before_recorded_at": True,
            "final_paths_absent_before_recorded_at": True,
            "publication_waited_until_recorded_at": True,
            "no_replace_promotion": True,
            "identity_checked_rollback_on_late_collision": True,
            "raw_capture_moved_to_trash_after_source_publication": True,
            "source_file_mode": "0444",
            "artifact_directory_mode": "0555",
            "artifact_file_mode": "0444",
        },
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-disposition-v3",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "source_rights": "All captured official response bodies are treated as all-rights-reserved; no redistribution license was relied on.",
        "artifact_is_hash_only": True,
        "raw_capture_redistributed": False,
        "raw_response_bodies_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "publisher_media_retained_in_artifact": False,
        "request_credentials_supplied": False,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "temporary_capture_file_count": CAPTURE_FILE_COUNT,
        "temporary_capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "temporary_capture_tree_sha256": CAPTURE_TREE_SHA256,
        "deletion_performed": False,
    }
    return {
        "README.md": readme.encode(),
        "candidate-assessment.json": _canonical(_candidate_assessment(recorded_at)),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _validate_sources(paths: Mapping[str, Path]) -> list[dict[str, Any]]:
    expected = expected_source_documents()
    if set(paths) != set(SOURCE_FILENAMES):
        raise RuntimeError("source path inventory differs")
    for name in SOURCE_FILENAMES:
        target = paths[name]
        if target.is_symlink() or not target.is_file() or target.read_bytes() != _canonical(expected[name]) or stat.S_IMODE(target.stat().st_mode) != 0o444:
            raise RuntimeError(f"curated source differs: {name}")
    document = expected[SOURCE_FILENAME]
    if any(document[entity][field] is not None for entity in ("campus", "project") for field in ("coordinates", "geometry")):
        raise RuntimeError("source invented coordinates or geometry")
    if any(document[entity]["roles"] for entity in ("campus", "project")):
        raise RuntimeError("source invented roles")
    if document["operating_models"] or document["workloads"]:
        raise RuntimeError("source invented operating model or workload")
    if document["lifecycle"] != [{"entity": "project", "value": "shell", "evidence_key": PRIMARY_EVIDENCE_KEY, "as_of_date": "2026-01-22", "method": "authoritative_physical_status_update", "confidence": 0.99}]:
        raise RuntimeError("lifecycle contract differs")
    capacities = document["capacities"]
    if len(capacities) != 1 or capacities[0]["entity"] != "project" or capacities[0]["metric"] != "critical_it_mw" or capacities[0]["stage"] != "planned" or [capacities[0][key] for key in ("low", "base", "high")] != [64, 64, 64]:
        raise RuntimeError("capacity contract differs")
    return _source_records(expected)


def _validate_source_collisions() -> None:
    planned = expected_source_documents()
    _collision_witness(planned)
    planned_stable, planned_evidence = _planned_keys(planned)
    collisions: dict[str, Any] = {}
    for target in SOURCES_ROOT.glob("*.json"):
        if target.name in SOURCE_FILENAMES:
            continue
        try:
            document = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        stable = {row.get("stable_key") for key in ("campus", "facility", "building", "project") if isinstance((row := document.get(key)), dict)}
        evidence = {row.get("key") for row in document.get("evidence", []) if isinstance(row, dict)}
        if planned_stable & stable or planned_evidence & evidence:
            collisions[str(target.relative_to(ROOT))] = {"stable_keys": sorted(planned_stable & stable), "evidence_keys": sorted(planned_evidence & evidence)}
    if collisions:
        raise RuntimeError(f"source collision detected: {collisions!r}")


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("capture directory absent or unsafe")
    entries = list(directory.iterdir())
    if len(entries) != CAPTURE_FILE_COUNT or set(CAPTURE_FILE_PINS) != {entry.name for entry in entries} or any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise RuntimeError("capture directory closed set differs")
    if sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES or tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise RuntimeError("capture directory aggregate differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(directory / name, pin)


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory(prefix="vantage-nv1-import-", dir="/private/tmp") as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            adapter.import_file(connection, paths[SOURCE_FILENAME], recorded_at=recorded_at)
        validate_database(connection)
        tables = ("entities", "entity_snapshots", "evidence", "lifecycle_observations", "operating_model_observations", "workload_observations", "capacity_estimates")
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
        expected = {"entities": 2, "entity_snapshots": 2, "evidence": 4, "lifecycle_observations": 1, "operating_model_observations": 0, "workload_observations": 0, "capacity_estimates": 1}
        if counts != expected:
            raise RuntimeError(f"offline import counts differ: {counts!r}")
        return counts


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def validate_artifact(path: Path = ARTIFACT, *, source_paths: Mapping[str, Path] | None = None, require_live: bool = True, wall_clock: datetime | None = None) -> dict[str, Any]:
    paths = source_paths or _source_paths(SOURCES_ROOT)
    source_records = _validate_sources(paths)
    if path.is_symlink() or not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise RuntimeError("artifact must be a frozen ordinary directory")
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES or any(entry.is_symlink() or not entry.is_file() or stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries.values()):
        raise RuntimeError("artifact closed frozen set differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest) or manifest.get("artifact_id") != ARTIFACT_ID or set(manifest.get("closed_file_set", [])) != CLOSED_FILES or manifest.get("candidate_assessments") != 2 or manifest.get("curated_source_records") != 1 or manifest.get("seed_eligible_candidates") != 1 or manifest.get("review_only_candidates") != 1 or _file_tree(manifest["files"]) != manifest.get("tree_sha256"):
        raise RuntimeError("manifest contract differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (row["bytes"], row["sha256"]):
            raise RuntimeError(f"manifest file pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != f"{_sha256_bytes(manifest_raw)}  manifest.json\n":
        raise RuntimeError("manifest checksum differs")
    expected = _artifact_documents(manifest["recorded_at"], expected_source_documents())
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected[name]:
            raise RuntimeError(f"artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records or snapshot["totals"]["normalized_critical_it_mw_sum"] != 64:
        raise RuntimeError("artifact source pins or capacity totals differ")
    assessment = json.loads(entries["candidate-assessment.json"].read_text(encoding="utf-8"))
    if assessment["candidates"][1]["source_paths"] != [] or assessment["candidates"][1]["operation_claim_created"] is not False:
        raise RuntimeError("NV11 review-only boundary differs")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise RuntimeError("wall clock lacks timezone")
    if require_live and now.astimezone(UTC) < target:
        raise RuntimeError("artifact recorded_at is not live")
    if any(_instant(capture.retrieved_at) > target for capture in CAPTURES):
        raise RuntimeError("capture retrieval post-dates recorded_at")
    if require_live and path == ARTIFACT and path.stat().st_ctime + 1e-6 < target.timestamp():
        raise RuntimeError("artifact final root predates recorded_at")
    replay = [_offline_import(paths, manifest["recorded_at"]) for _ in range(2)]
    if replay[0] != replay[1]:
        raise RuntimeError("offline replay differs")
    return manifest


def _write_source_stage(stage: Path, documents: Mapping[str, Mapping[str, Any]]) -> None:
    for name in SOURCE_FILENAMES:
        target = stage / name
        target.write_bytes(_canonical(documents[name]))
        target.chmod(0o444)
        _fsync_regular(target)
    _fsync_directory(stage)


def _write_artifact_stage(stage: Path, recorded_at: str, documents: Mapping[str, Mapping[str, Any]]) -> None:
    payloads = _artifact_documents(recorded_at, documents)
    for name in CONTENT_FILES:
        target = stage / name
        target.write_bytes(payloads[name])
        target.chmod(0o444)
        _fsync_regular(target)
    rows = [{"bytes": (stage / name).stat().st_size, "path": name, "sha256": _sha256(stage / name)} for name in CONTENT_FILES]
    manifest = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-artifact-manifest-v3",
        "recorded_at": recorded_at,
        "files": rows,
        "tree_sha256": _file_tree(rows),
        "closed_file_set": sorted(CLOSED_FILES),
        "candidate_assessments": 2,
        "curated_source_records": 1,
        "seed_eligible_candidates": 1,
        "seed_eligible_source_records": 1,
        "review_only_candidates": 1,
        "controlled_capture_count": len(CAPTURES),
        "successful_http_200_body_captures": len(CAPTURES),
        "failed_http_body_captures": 0,
        "raw_capture_redistributed": False,
        "raw_capture_directory_moved_intact_to_trash": True,
        "raw_capture_moved_after_source_publication": True,
        "regional_completeness_claimed": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
    }
    manifest_path = stage / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    manifest_path.chmod(0o444)
    _fsync_regular(manifest_path)
    sidecar = stage / "manifest.sha256"
    sidecar.write_text(f"{_sha256(manifest_path)}  manifest.json\n", encoding="utf-8")
    sidecar.chmod(0o444)
    _fsync_regular(sidecar)
    stage.chmod(0o555)
    _fsync_directory(stage)


def _assert_stage_precedes(stage: Path, recorded_at: str) -> None:
    target = _instant(recorded_at).timestamp()
    if any(entry.stat(follow_symlinks=False).st_mtime > target for entry in [stage, *stage.rglob("*")]):
        raise RuntimeError("staged byte post-dates recorded_at")


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise RuntimeError("active Vantage source publication lock exists") from error
    os.write(descriptor, f"pid={os.getpid()}\n".encode())
    os.fsync(descriptor)
    identity = (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
    try:
        yield
    finally:
        os.close(descriptor)
        if PUBLICATION_LOCK.exists():
            current = PUBLICATION_LOCK.stat(follow_symlinks=False)
            if (current.st_dev, current.st_ino) != identity:
                raise RuntimeError("refusing substituted lock cleanup")
            PUBLICATION_LOCK.unlink()


@dataclass(frozen=True)
class _Prepared:
    source_stage: Path
    artifact_stage: Path
    recorded_at: str


def _prepare(recorded_at: str) -> _Prepared:
    if any((SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink() for name in SOURCE_FILENAMES) or ARTIFACT.exists() or ARTIFACT.is_symlink():
        raise RuntimeError("Vantage source final-path collision")
    _validate_source_collisions()
    capture = CAPTURE_ORIGIN if CAPTURE_ORIGIN.exists() else CAPTURE_TRASH
    _validate_capture_directory(capture)
    documents = expected_source_documents()
    source_stage = Path(tempfile.mkdtemp(prefix=".vantage-nv1-sources.", dir=SOURCES_ROOT))
    artifact_stage = Path(tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT))
    try:
        _write_source_stage(source_stage, documents)
        _write_artifact_stage(artifact_stage, recorded_at, documents)
        _assert_stage_precedes(source_stage, recorded_at)
        _assert_stage_precedes(artifact_stage, recorded_at)
        validate_artifact(artifact_stage, source_paths=_source_paths(source_stage), require_live=False, wall_clock=_instant(recorded_at))
        return _Prepared(source_stage, artifact_stage, recorded_at)
    except Exception:
        if source_stage.exists():
            shutil.rmtree(source_stage)
        if artifact_stage.exists():
            artifact_stage.chmod(0o700)
            shutil.rmtree(artifact_stage)
        raise


def _publish(prepared: _Prepared) -> None:
    target = _instant(prepared.recorded_at)
    while datetime.now(UTC) < target:
        time.sleep(min(0.25, (target - datetime.now(UTC)).total_seconds()))
    if any((SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink() for name in SOURCE_FILENAMES) or ARTIFACT.exists() or ARTIFACT.is_symlink():
        raise RuntimeError("late Vantage source final-path collision")
    promoted: list[tuple[Path, Path]] = []
    try:
        for name in SOURCE_FILENAMES:
            staged, final = prepared.source_stage / name, SOURCES_ROOT / name
            _promote_noreplace(staged, final)
            promoted.append((final, staged))
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        promoted.append((ARTIFACT, prepared.artifact_stage))
        _fsync_directory(SOURCES_ROOT)
        _fsync_directory(ARTIFACT_ROOT)
        if ARTIFACT.stat().st_ctime + 1e-6 < target.timestamp():
            raise RuntimeError("artifact final root predates recorded_at")
    except BaseException as error:
        for final, staged in reversed(promoted):
            try:
                _promote_noreplace(final, staged)
            except Exception as rollback_error:
                error.add_note(f"rollback failed for {final}: {rollback_error}")
        raise


def _move_capture_to_trash() -> None:
    if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
        raise RuntimeError("both raw capture origin and Trash destination exist")
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(CAPTURE_TRASH)


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    source_exists = all((SOURCES_ROOT / name).exists() for name in SOURCE_FILENAMES)
    if ARTIFACT.exists() and source_exists:
        manifest = validate_artifact()
        _move_capture_to_trash()
        return {"artifact": str(ARTIFACT), "artifact_tree_sha256": tree_digest(ARTIFACT), "capture_trash": str(CAPTURE_TRASH), "manifest_sha256": _sha256(ARTIFACT / "manifest.json"), "recorded_at": manifest["recorded_at"], "source_records": 1, "status": "existing-identical"}
    if ARTIFACT.exists() or ARTIFACT.is_symlink() or any((SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink() for name in SOURCE_FILENAMES):
        raise RuntimeError("partial Vantage source final-path collision")
    target = _instant(recorded_at) if recorded_at else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    if datetime.now(UTC) >= target:
        raise RuntimeError("recorded_at must be future before staging")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    with _publication_lock():
        prepared = _prepare(timestamp)
        _publish(prepared)
        _move_capture_to_trash()
        manifest = validate_artifact()
        if any(prepared.source_stage.iterdir()):
            raise RuntimeError("source stage not empty after publication")
        prepared.source_stage.rmdir()
    return {"artifact": str(ARTIFACT), "artifact_tree_sha256": tree_digest(ARTIFACT), "capture_trash": str(CAPTURE_TRASH), "manifest_sha256": _sha256(ARTIFACT / "manifest.json"), "recorded_at": manifest["recorded_at"], "source_records": 1, "status": "published"}


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
