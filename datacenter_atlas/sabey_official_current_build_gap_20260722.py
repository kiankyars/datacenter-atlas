"""Publish a hash-bound Sabey official current-build source tranche.

Two exact campus/project records are seed eligible. Raw response bytes remain
all-rights-reserved and are represented only by exact hashes and compact
factual extracts.
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
from . import global_official_current_build_gap_20260721 as prior
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "sabey-official-current-build-gap-2026-07-22-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".sabey-official-current-build-gap.lock"

CAPTURE_ORIGIN = Path("/private/tmp/dc-sabey-current-build-20260722.dJUc9C")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-sabey-current-build-20260722.dJUc9C")
CAPTURE_FILE_COUNT = 12
CAPTURE_TOTAL_BYTES = 587_054
CAPTURE_TREE_SHA256 = "99cde72dae24ab89020f1838b6bff94219ca05e23bd2a773271752bc00d72cb5"

V91_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v91.json"
V91_RELEASE = ROOT / "releases/2026-07-21-open-seed-v91"
V91_MANIFEST = V91_RELEASE / "manifest.json"
V91_ENTITIES = V91_RELEASE / "entities.csv"
V91_PINS = {
    V91_DEFINITION: (
        108_188,
        "e1a1c657c88468233dc72e66012ec1f56afd69a599f129c5fcc64f20bdf3038a",
    ),
    V91_MANIFEST: (
        15_954,
        "8be929e9f24b0bb1d11a318cfd67d8c4e538f2979db9468ecd359cb36afb45f9",
    ),
    V91_ENTITIES: (
        1_018_118,
        "b1f07223ff1a61e64670aaf23bc9b3a7ee5834c2131e031a59401b404acebe75",
    ),
}
V91_TREE_SHA256 = "9c89ab93baf5a13965db764a376affe231186df6a5cbc2758fd9ad95a85a5a5e"
V91_INPUT_COUNT = 480

MASTER_RELEASE = ROOT / "construction_master/2026-07-21-public-open-v31"
MASTER_MANIFEST = MASTER_RELEASE / "manifest.json"
MASTER_CSV = MASTER_RELEASE / "construction-master.csv"
MASTER_PINS = {
    MASTER_MANIFEST: (
        9_721,
        "8d2cb42034ca040c3341582ee0ac125013f208a6712c211fb334943763412c7e",
    ),
    MASTER_CSV: (
        190_003_570,
        "3c05febb4bc9ed6bc4fa0876e42e1b685269d6763b4c0bbf1f9ecefea3921e5c",
    ),
}
MASTER_TREE_SHA256 = "90790b8d72592bd8c1a9971576cc9bb27a4cbc334b16b0b13246e1ed2639b9da"
GLOBAL_ENTITIES = ROOT / "releases/2026-07-18-global-open-v3/entities.csv"
GLOBAL_ENTITIES_PIN = (
    12_716_173,
    "badd13d11d9aa720f3208a07f93de4a19a73f9bb781db5f1714b3faf68d489f3",
)

_canonical = prior._canonical
_sha256 = prior._sha256
_sha256_bytes = prior._sha256_bytes
_instant = prior._instant
_pin = prior._pin
_fsync_regular = prior._fsync_regular
_fsync_directory = prior._fsync_directory
_promote_noreplace = prior._promote_noreplace


CAPTURE_FILE_PINS: dict[str, tuple[int, str]] = {
    "ashburn-groundbreak-headers.txt": (1_934, "96001fa17a9017c646a6314c3039b8888d098ff94ef6b9e47394655313514eeb"),
    "ashburn-groundbreak.body": (75_356, "c4b9948c203643895b5037a324e923e10041d20e0e5e67b9b8c80d1a63a44db3"),
    "ashburn-location-headers.txt": (1_892, "5066186b867aff815215441c95c11f7e8b4216774c9c5d3c0223d58cc8989d09"),
    "ashburn-location.body": (200_752, "d33eff952d3fe9869e9cc4822131232b18b5331cd7d8d42c7310f31d3522901a"),
    "austin-launch-headers.txt": (1_954, "c9d483627b26e02c7c3224ed28908f64391a8b4229afe9104e4d00d94bf4e5fc"),
    "austin-launch.body": (78_309, "752ac59db8b2d8a717b5d1f4b0bc64dfb77fdc61325da77b5b612858f14e2fb5"),
    "austin-q1-2026-headers.txt": (1_891, "1669da23eb2753ca947804bd7888ea3023d2c4f721b9a215e7788f09ee3d5f39"),
    "austin-q1-2026.body": (73_299, "be98fc04d0578d237fe08560bdaa93848fb12f380695f139002cd0be6ddc051e"),
    "austin-q2-2026-headers.txt": (1_905, "7030c00932df269c1800667a4223e3f595e726ab0ceb5c938212c61d6a4e928f"),
    "austin-q2-2026.body": (75_667, "95ab882f066671c2c3ba51fda484fa92007b6d6074cba25a001e6d2db8efb92e"),
    "austin-q3-2025-headers.txt": (1_889, "2001a6213589041f141777e85cedc22de6352aaae5e332165c62d955dccef75c"),
    "austin-q3-2025.body": (72_206, "1887a44fe353f0967755641cafe0d3240a89f0b8bc3ee125203c46fb0bb49d52"),
}


@dataclass(frozen=True)
class Capture:
    capture_id: str
    file_stem: str
    url: str
    retrieved_at: str
    published_at: str | None
    http_status: int
    content_type: str
    use: str


CAPTURES = (
    Capture("ashburn_groundbreak", "ashburn-groundbreak", "https://sabeydatacenters.com/news/sabey-breaks-ground-on-final-phase-of-ashburn-campus-expansion", "2026-07-22T01:35:47Z", "2025-06-25", 200, "text/html; charset=UTF-8", "normalized"),
    Capture("ashburn_location", "ashburn-location", "https://sabeydatacenters.com/locations/ashburn-data-center", "2026-07-22T01:35:48Z", None, 200, "text/html; charset=UTF-8", "normalized_corroboration"),
    Capture("austin_launch", "austin-launch", "https://sabeydatacenters.com/news/sdc-announces-launch-of-austin-building-b-expanding-presence-in-key-technology-hub", "2026-07-22T01:35:49Z", "2025-07-29", 200, "text/html; charset=UTF-8", "normalized"),
    Capture("austin_q3_2025", "austin-q3-2025", "https://sabeydatacenters.com/news/sdc-austin-progress-q3-2025", "2026-07-22T01:35:50Z", "2025-09-29", 200, "text/html; charset=UTF-8", "normalized_corroboration"),
    Capture("austin_q1_2026", "austin-q1-2026", "https://sabeydatacenters.com/news/sdc-austin-progress-q1-2026", "2026-07-22T01:35:52Z", "2026-02-17", 200, "text/html; charset=UTF-8", "normalized_corroboration"),
    Capture("austin_q2_2026", "austin-q2-2026", "https://sabeydatacenters.com/news/sdc-austin-progress-q2-2026", "2026-07-22T01:35:53Z", "2026-06-16", 200, "text/html; charset=UTF-8", "normalized_latest_physical_update"),
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
    EvidenceSpec("sabey-ashburn-building-a-construction-start-2025-06-25", "ashburn_groundbreak", "Construction Moving Along for Final Phase of Ashburn Campus Expansion", "Sabey Data Centers", "sabey_data_centers_news", "company_disclosure", "Sabey says construction is under way for Building A, the third and final facility on its Ashburn campus.", {"physical_status_as_reported": "Construction under way for Ashburn Building A.", "power_context_not_normalized": "18 MW initial leasable, 36 MW future, 54 MW building-total and 85 MW campus-total figures do not establish critical IT, gross facility, grid, or measured load scope.", "pue_context_not_normalized": "1.35 average annualized PUE describes current campus buildings, not the new Building A project.", "design_context_not_normalized": "Air, liquid, and hybrid cooling and high-density deployment language describes design capability, not actual cooling type or workload.", "roles_and_joint_venture_context_not_normalized": "Sabey developer, owner and operator wording and the National Real Estate Advisors joint-venture context are evidence metadata only."}),
    EvidenceSpec("sabey-ashburn-location-observed-2026-07-22", "ashburn_location", "SDC Ashburn", "Sabey Data Centers", "sabey_data_centers_location", "company_disclosure", "Sabey's current Ashburn location page identifies Building A as the third campus building and describes it as coming online starting in 2026.", {"address_as_reported": "21741 Red Rum Dr, Ashburn, VA 20147.", "power_context_not_normalized": "54 MW additional leasable and 85 MW campus figures are untyped commercial or campus context.", "pue_context_not_normalized": "1.35 is an average annualized campus context, not Building A project PUE.", "design_context_not_normalized": "Cooling configurations and density are design capabilities only."}),
    EvidenceSpec("sabey-austin-building-b-construction-start-2025-07-29", "austin_launch", "SDC Announces Launch of Austin Building B", "Sabey Data Centers", "sabey_data_centers_news", "company_disclosure", "Sabey announces construction is under way for Building B on its Round Rock campus.", {"physical_status_as_reported": "Construction under way for Austin Building B.", "power_context_not_normalized": "18 MW initial and 54 MW total figures do not establish critical IT, gross facility, grid, or measured load scope.", "design_context_not_normalized": "Liquid-cooling-ready, rack-density, AI, HPC, advanced research, enterprise and hyperscale wording describes design capability or target demand, not actual cooling type or workload.", "roles_and_joint_venture_context_not_normalized": "Sabey developer, owner and operator wording and the National Real Estate Advisors joint-venture context are evidence metadata only."}),
    EvidenceSpec("sabey-austin-building-b-progress-2025-09-29", "austin_q3_2025", "SDC Austin Building B Progress Q3 2025", "Sabey Data Centers", "sabey_data_centers_news", "company_disclosure", "Sabey says construction has begun on Austin Building B and provides a construction-progress update.", {"physical_status_as_reported": "Construction begun on Austin Building B.", "power_context_not_normalized": "18 MW pre-leasing and 54 MW total figures are commercial or untyped power context.", "design_context_not_normalized": "Liquid-cooling optimized and next-generation workload wording describes design capability."}),
    EvidenceSpec("sabey-austin-building-b-progress-2026-02-17", "austin_q1_2026", "SDC Austin Building B Progress Q1 2026", "Sabey Data Centers", "sabey_data_centers_news", "company_disclosure", "Sabey says Austin Building B construction is well underway, with its concrete structure rising and vertical construction progressing.", {"physical_status_as_reported": "Concrete structure rising and vertical construction progressing.", "power_context_not_normalized": "54 MW total and secured utility-power wording does not cleanly establish a normalized capacity metric.", "design_context_not_normalized": "Liquid-cooling optimized and next-generation workload wording describes design capability."}),
    EvidenceSpec("sabey-austin-building-b-shell-update-2026-06-16", "austin_q2_2026", "SDC Austin Building B Progress Q2 2026", "Sabey Data Centers", "sabey_data_centers_news", "company_disclosure", "Sabey says Austin Building B's shell is nearing completion and vertical construction is substantially complete.", {"physical_status_as_reported": "Building shell nearing completion; vertical construction substantially complete; early interior electrical and mechanical installation follows.", "power_context_not_normalized": "18 MW pre-leasing and 54 MW total figures are commercial or untyped power context.", "design_context_not_normalized": "Liquid-cooling-enabled and next-generation workload wording describes design capability."}),
)
EVIDENCE_BY_KEY = {evidence.key: evidence for evidence in EVIDENCE}


@dataclass(frozen=True)
class Site:
    slug: str
    country: str
    address: str
    campus_key: str
    project_key: str
    campus_name: str
    project_name: str
    evidence_keys: tuple[str, ...]
    primary_evidence_key: str
    as_of_date: str
    status: str
    method: str

    @property
    def filename(self) -> str:
        return f"curated-official-2026-07-22-sabey-{self.slug}-current-build.json"


SITES = (
    Site("ashburn-building-a", "United States", "21741 Red Rum Dr, Ashburn, VA 20147, United States", "curated:sabey-sdc-ashburn-campus", "curated:sabey-sdc-ashburn-campus:building-a-current-build", "Sabey SDC Ashburn Campus", "Sabey SDC Ashburn Building A Current Build", ("sabey-ashburn-building-a-construction-start-2025-06-25", "sabey-ashburn-location-observed-2026-07-22"), "sabey-ashburn-building-a-construction-start-2025-06-25", "2025-06-25", "under_construction", "authoritative_construction_start"),
    Site("austin-round-rock-building-b", "United States", "Round Rock, Texas, United States", "curated:sabey-sdc-austin-round-rock-campus", "curated:sabey-sdc-austin-round-rock-campus:building-b-current-build", "Sabey SDC Austin Round Rock Campus", "Sabey SDC Austin Building B Current Build", ("sabey-austin-building-b-construction-start-2025-07-29", "sabey-austin-building-b-progress-2025-09-29", "sabey-austin-building-b-progress-2026-02-17", "sabey-austin-building-b-shell-update-2026-06-16"), "sabey-austin-building-b-shell-update-2026-06-16", "2026-06-16", "shell", "authoritative_physical_status_update"),
)

SOURCE_FILENAMES = tuple(site.filename for site in SITES)
SITE_BY_FILENAME = {site.filename: site for site in SITES}
CONTENT_FILES = (
    "README.md", "candidate-assessment.json", "retrieval-inventory.json",
    "rights-and-disposition.json", "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))


def _evidence(spec: EvidenceSpec) -> dict[str, Any]:
    capture = CAPTURE_BY_ID[spec.capture_id]
    body = f"{capture.file_stem}.body"
    headers = f"{capture.file_stem}-headers.txt"
    body_bytes, body_sha = CAPTURE_FILE_PINS[body]
    header_bytes, header_sha = CAPTURE_FILE_PINS[headers]
    metadata = {
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture.capture_id,
        "capture_method": "credential_free_curl_location_compressed",
        "requested_url": capture.url,
        "effective_url": capture.url,
        "request_credentials_supplied": False,
        "http_status": capture.http_status,
        "content_type": capture.content_type,
        "content_hash_scope": f"SHA-256 of the exact {body_bytes}-byte content-decoded credential-free public response body",
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_headers_scope": f"SHA-256 of the exact {header_bytes}-byte raw HTTP response-header capture",
        "capture_headers_sha256": header_sha,
        "status_semantics": "dated_last_observed_current_status_unknown",
        "rights_scope": "Compact factual extraction from all-rights-reserved official bytes; raw bodies, headers, telemetry, and publisher media are not redistributed.",
        "normalization_guardrail": "No capacity, energy use, PUE, WUE, generation, facility type, operating model, workload, role, coordinate, geometry, satellite, aerial, map-click, or computer-vision claim is normalized.",
        **spec.factual_extract,
    }
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
        "content_hash": body_sha,
        "metadata": metadata,
    }


def _entity(site: Site, *, project: bool) -> dict[str, Any]:
    return {
        "stable_key": site.project_key if project else site.campus_key,
        "name": site.project_name if project else site.campus_name,
        "country": site.country,
        "address": site.address,
        "roles": {},
        "coordinates": None,
        "geometry": None,
        "evidence_key": site.primary_evidence_key,
        "as_of_date": site.as_of_date,
        "method": "authoritative_locality",
        "confidence": 0.99,
    }


def _source(site: Site) -> dict[str, Any]:
    lifecycle = []
    if site.slug == "austin-round-rock-building-b":
        lifecycle.append({
            "entity": "project", "value": "under_construction",
            "evidence_key": "sabey-austin-building-b-construction-start-2025-07-29",
            "as_of_date": "2025-07-29",
            "method": "authoritative_construction_start", "confidence": 0.99,
        })
    lifecycle.append({
        "entity": "project", "value": site.status,
        "evidence_key": site.primary_evidence_key, "as_of_date": site.as_of_date,
        "method": site.method, "confidence": 0.99,
    })
    return {
        "schema_version": "1.1",
        "evidence": [_evidence(EVIDENCE_BY_KEY[key]) for key in site.evidence_keys],
        "campus": _entity(site, project=False),
        "project": _entity(site, project=True),
        "lifecycle": lifecycle,
        "operating_models": [], "workloads": [], "capacities": [],
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    return {site.filename: _source(site) for site in SITES}


def _source_records(documents: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for name in SOURCE_FILENAMES:
        document = documents[name]
        payload = _canonical(document)
        rows.append({
            "path": f"sources/{name}", "bytes": len(payload),
            "sha256": _sha256_bytes(payload), "schema_version": "1.1",
            "country": document["campus"]["country"],
            "campus_stable_key": document["campus"]["stable_key"],
            "project_stable_key": document["project"]["stable_key"],
            "evidence_records": len(document["evidence"]),
            "lifecycle_observations": len(document["lifecycle"]),
            "operating_model_observations": 0, "workload_observations": 0,
            "capacity_estimates": 0, "coordinates_present": 0,
            "geometry_present": 0,
            "disposition": "seed_eligible_direct_authoritative_physical_update",
            "seed_eligible": True, "seeded": False,
        })
    return rows


def _planned_keys(documents: Mapping[str, Mapping[str, Any]]) -> tuple[set[str], set[str]]:
    stable = {document[entity]["stable_key"] for document in documents.values() for entity in ("campus", "project")}
    evidence = {row["key"] for document in documents.values() for row in document["evidence"]}
    return stable, evidence


def _collision_witness(documents: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    for path, pin in {**V91_PINS, **MASTER_PINS, GLOBAL_ENTITIES: GLOBAL_ENTITIES_PIN}.items():
        _pin(path, pin)
    if tree_digest(V91_RELEASE) != V91_TREE_SHA256:
        raise RuntimeError("v91 release tree differs")
    if tree_digest(MASTER_RELEASE) != MASTER_TREE_SHA256:
        raise RuntimeError("master v31 tree differs")
    definition = json.loads(V91_DEFINITION.read_text(encoding="utf-8"))
    selected = definition.get("curated_inputs")
    if not isinstance(selected, list) or len(selected) != V91_INPUT_COUNT:
        raise RuntimeError("v91 selected input inventory differs")
    planned_stable, planned_evidence = _planned_keys(documents)
    with V91_ENTITIES.open(encoding="utf-8", newline="") as stream:
        base_rows = list(csv.DictReader(stream))
    base_stable = {row["stable_key"] for row in base_rows}
    if planned_stable & base_stable:
        raise RuntimeError("planned Sabey stable key collides with v91")
    source_inputs = json.loads((V91_RELEASE / "source_inputs.json").read_text(encoding="utf-8")).get("sources")
    base_evidence = {
        key for row in source_inputs or [] if isinstance(row, dict)
        for key in [row.get("provenance", {}).get("curated_record_key")]
        if isinstance(key, str)
    }
    if planned_evidence & base_evidence:
        raise RuntimeError("planned Sabey evidence key collides with v91")

    with GLOBAL_ENTITIES.open(encoding="utf-8", newline="") as stream:
        global_rows = {row["stable_key"]: row for row in csv.DictReader(stream)}
    related_structural_keys = {
        "osm:way/793888427",
        "pnnl_im3:2026-02-09:building/00793888427",
    }
    expected_names = {
        "osm:way/793888427": "Sabey Intergate.Ashburn (Building A)",
        "pnnl_im3:2026-02-09:building/00793888427": "Sabey Intergate.Ashburn (Building A)",
    }
    if {key: global_rows.get(key, {}).get("name") for key in expected_names} != expected_names:
        raise RuntimeError("global-open Sabey Ashburn structural witness differs")
    if {global_rows[key].get("entity_kind") for key in related_structural_keys} != {
        "building"
    }:
        raise RuntimeError("Sabey Ashburn structural-kind witness differs")
    if planned_stable & related_structural_keys:
        raise RuntimeError("Sabey source selected a structural identity")
    return {
        "v91_selected_input_count": len(selected),
        "v91_entity_count": len(base_rows),
        "planned_distinct_stable_keys": len(planned_stable),
        "planned_distinct_evidence_keys": len(planned_evidence),
        "exact_v91_stable_key_collisions": [],
        "exact_v91_evidence_key_collisions": [],
        "related_global_open_structural_keys_not_reused": sorted(related_structural_keys),
        "collision_resolution": "The curated Ashburn campus/project aggregation is kept distinct from two global-open Building A structural identities. No global identity is reused for Austin.",
        "geometry_boundary": "No PNNL, OSM, satellite, aerial, map-click, or computer-vision coordinate or geometry is copied into either official source record.",
    }


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    documents = expected_source_documents()
    candidates = [
        {
            "candidate_id": site.slug,
            "decision": "seed_eligible_direct_authoritative_physical_update",
            "source_paths": [f"sources/{site.filename}"],
            "campus_stable_key": site.campus_key,
            "project_stable_key": site.project_key,
            "lifecycle": documents[site.filename]["lifecycle"],
            "withheld": [
                "current-status extrapolation", "capacity or energy",
                "PUE or WUE", "facility type or workload",
                "standardized role or operating model", "coordinates or geometry",
                "satellite, aerial, map-click, or computer-vision claims",
            ],
        }
        for site in SITES
    ]
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-current-build-assessment-v1",
        "research_date": "2026-07-22", "recorded_at": recorded_at,
        "candidate_count": 2, "seed_eligible_candidate_count": 2,
        "seed_eligible_source_record_count": 2, "review_only_count": 0,
        "regional_completeness_claimed": False, "candidates": candidates,
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-22", "recorded_at": recorded_at,
        "request_credentials_supplied": False,
        "successful_http_200_body_captures": 6,
        "failed_http_body_captures": 0,
        "raw_capture_redistributed": False,
        "capture_file_count": CAPTURE_FILE_COUNT,
        "capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "controlled_captures": [{
            "capture_id": capture.capture_id,
            "requested_url": capture.url,
            "effective_url": capture.url,
            "retrieved_at": capture.retrieved_at,
            "body": {"path": f"{capture.file_stem}.body", "bytes": CAPTURE_FILE_PINS[f"{capture.file_stem}.body"][0], "sha256": CAPTURE_FILE_PINS[f"{capture.file_stem}.body"][1], "retained_in_artifact": False, "moved_to_trash": True},
            "headers": {"path": f"{capture.file_stem}-headers.txt", "bytes": CAPTURE_FILE_PINS[f"{capture.file_stem}-headers.txt"][0], "sha256": CAPTURE_FILE_PINS[f"{capture.file_stem}-headers.txt"][1], "retained_in_artifact": False, "moved_to_trash": True},
            "http_status": capture.http_status,
            "content_type": capture.content_type,
            "request_credentials_supplied": False,
            "claim_use": capture.use,
        } for capture in CAPTURES],
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
        "candidate_assessments": 2, "source_records": 2,
        "seed_eligible_candidates": 2, "seed_eligible_source_records": 2,
        "review_only_candidates": 0, "distinct_campuses_in_source_records": 2,
        "projects": 2, "distinct_entities_in_source_records": 4,
        "new_entities_against_v91": 4,
        "global_open_identity_keys_reused": 0,
        "source_document_entity_snapshots": 4,
        "unique_imported_entity_snapshots": 4,
        "source_document_evidence_references": 6,
        "unique_evidence_records": 6, "lifecycle_observations": 3,
        "operating_model_observations": 0, "workload_observations": 0,
        "capacity_estimates": 0, "coordinates_present": 0, "geometry_present": 0,
    }
    readme = f"""# Sabey official current-build gap tranche

This immutable artifact closes six credential-free official captures and publishes exactly two named, seed-eligible campus/project records: Ashburn Building A and Austin Building B. Austin retains the exact 2025-07-29 construction-start observation and adds the exact 2026-06-16 shell update; the intervening Q3 2025 and Q1 2026 pages remain evidence corroboration. The curated Ashburn aggregation is kept distinct from existing global-open structural Building A identities, and no structural identity or geometry is inherited.

All 18, 36, 54, and 85 MW figures remain untyped, leasable, or total power context in evidence metadata. The 1.35 PUE describes existing Ashburn buildings or campus context, not Building A. Cooling and workload wording is design capability only. Sabey developer, owner and operator wording and National Real Estate Advisors joint-venture context remain metadata. No capacity, energy use, PUE, WUE, facility type, operating model, workload, standardized role, current-status extrapolation, coordinate, geometry, satellite, aerial, map-click, or computer-vision claim is added. All normalized statuses are dated last-observed facts whose current status is unknown.

All source and artifact bytes were staged before {recorded_at}; final paths were absent until that instant and promoted without replacement. Raw all-rights-reserved captures are represented only by exact hashes and retrieval facts. The intact {CAPTURE_FILE_COUNT}-file raw capture directory was moved to recoverable Trash only after successful source publication.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at, "research_date": "2026-07-22",
        "regional_completeness_claimed": False,
        "source_records": source_records, "totals": totals,
        "frozen_v91_non_mutation_witness": {
            "definition": {"path": "sources/open-seed-2026-07-21-v91.json", "bytes": V91_PINS[V91_DEFINITION][0], "sha256": V91_PINS[V91_DEFINITION][1]},
            "release_manifest": {"path": "releases/2026-07-21-open-seed-v91/manifest.json", "bytes": V91_PINS[V91_MANIFEST][0], "sha256": V91_PINS[V91_MANIFEST][1]},
            "release_entities": {"path": "releases/2026-07-21-open-seed-v91/entities.csv", "bytes": V91_PINS[V91_ENTITIES][0], "sha256": V91_PINS[V91_ENTITIES][1]},
            "release_tree_sha256": V91_TREE_SHA256,
            **collision,
        },
        "integration": {
            "open_seed_successor_created": False, "open_seed_v91_mutated": False,
            "release_integration": "none", "construction_master_integration": "none",
            "map_integration": "none", "federation_integration": "none",
            "coverage_integration": "none", "review_integration": "none",
        },
        "publication_contract": {
            "version": 1, "all_source_and_artifact_bytes_staged_before_recorded_at": True,
            "final_paths_absent_before_recorded_at": True,
            "publication_waited_until_recorded_at": True, "no_replace_promotion": True,
            "identity_checked_rollback_on_late_collision": True,
            "raw_capture_moved_to_trash_after_source_publication": True,
            "source_file_mode": "0444", "artifact_directory_mode": "0555",
            "artifact_file_mode": "0444",
        },
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-disposition-v3",
        "research_date": "2026-07-22", "recorded_at": recorded_at,
        "source_rights": "All captured official response bodies are treated as all-rights-reserved; no redistribution license was relied on.",
        "artifact_is_hash_only": True, "raw_capture_redistributed": False,
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
        path = paths[name]
        if path.is_symlink() or not path.is_file() or path.read_bytes() != _canonical(expected[name]) or stat.S_IMODE(path.stat().st_mode) != 0o444:
            raise RuntimeError(f"curated source differs: {name}")
    documents = list(expected.values())
    if any(document[entity][field] is not None for document in documents for entity in ("campus", "project") for field in ("coordinates", "geometry")):
        raise RuntimeError("source invented coordinates or geometry")
    if any(document[entity]["roles"] for document in documents for entity in ("campus", "project")):
        raise RuntimeError("source invented roles")
    if any(document[collection] for document in documents for collection in ("operating_models", "workloads", "capacities")):
        raise RuntimeError("source invented normalized non-lifecycle claims")
    lifecycle = {(document["project"]["stable_key"], row["value"], row["as_of_date"], row["method"]) for document in documents for row in document["lifecycle"]}
    expected_lifecycle = {(site.project_key, site.status, site.as_of_date, site.method) for site in SITES}
    expected_lifecycle.add((
        "curated:sabey-sdc-austin-round-rock-campus:building-b-current-build",
        "under_construction", "2025-07-29", "authoritative_construction_start",
    ))
    if lifecycle != expected_lifecycle:
        raise RuntimeError("lifecycle contract differs")
    return _source_records(expected)


def _validate_source_collisions() -> None:
    planned = expected_source_documents()
    _collision_witness(planned)
    planned_stable, planned_evidence = _planned_keys(planned)
    source_names = set(SOURCE_FILENAMES)
    collisions: dict[str, Any] = {}
    for path in SOURCES_ROOT.glob("*.json"):
        if path.name in source_names:
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        stable = {row.get("stable_key") for key in ("campus", "facility", "building", "project") if isinstance((row := document.get(key)), dict)}
        evidence = {row.get("key") for row in document.get("evidence", []) if isinstance(row, dict)}
        if planned_stable & stable or planned_evidence & evidence:
            collisions[str(path.relative_to(ROOT))] = {
                "stable_keys": sorted(planned_stable & stable),
                "evidence_keys": sorted(planned_evidence & evidence),
            }
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
    with tempfile.TemporaryDirectory(prefix="sabey-current-build-import-", dir="/private/tmp") as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            for name in SOURCE_FILENAMES:
                adapter.import_file(connection, paths[name], recorded_at=recorded_at)
        validate_database(connection)
        tables = ("entities", "entity_snapshots", "evidence", "lifecycle_observations", "operating_model_observations", "workload_observations", "capacity_estimates")
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
        expected = {"entities": 4, "entity_snapshots": 4, "evidence": 6, "lifecycle_observations": 3, "operating_model_observations": 0, "workload_observations": 0, "capacity_estimates": 0}
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
    if manifest_raw != _canonical(manifest) or manifest.get("artifact_id") != ARTIFACT_ID or set(manifest.get("closed_file_set", [])) != CLOSED_FILES or manifest.get("candidate_assessments") != 2 or manifest.get("curated_source_records") != 2 or manifest.get("seed_eligible_candidates") != 2 or manifest.get("review_only_candidates") != 0 or _file_tree(manifest["files"]) != manifest.get("tree_sha256"):
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
    if snapshot["source_records"] != source_records:
        raise RuntimeError("artifact source pins differ")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None or (require_live and now.astimezone(UTC) < target):
        raise RuntimeError("artifact recorded_at is not live")
    if any(_instant(capture.retrieved_at) > target for capture in CAPTURES):
        raise RuntimeError("capture retrieval post-dates recorded_at")
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
        "recorded_at": recorded_at, "files": rows, "tree_sha256": _file_tree(rows),
        "closed_file_set": sorted(CLOSED_FILES), "candidate_assessments": 2,
        "curated_source_records": 2, "seed_eligible_candidates": 2,
        "seed_eligible_source_records": 2, "review_only_candidates": 0,
        "successful_http_200_body_captures": 6,
        "raw_capture_redistributed": False,
        "raw_capture_directory_moved_intact_to_trash": True,
        "raw_capture_moved_after_source_publication": True,
        "regional_completeness_claimed": False,
        "open_seed_successor_created": False, "release_integration": "none",
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


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise RuntimeError("active Sabey source publication lock exists") from error
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
        raise RuntimeError("Sabey source final-path collision")
    _validate_source_collisions()
    capture = CAPTURE_ORIGIN if CAPTURE_ORIGIN.exists() else CAPTURE_TRASH
    _validate_capture_directory(capture)
    documents = expected_source_documents()
    source_stage = Path(tempfile.mkdtemp(prefix=".sabey-current-build-sources.", dir=SOURCES_ROOT))
    artifact_stage = Path(tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT))
    try:
        _write_source_stage(source_stage, documents)
        _write_artifact_stage(artifact_stage, recorded_at, documents)
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
        raise RuntimeError("late Sabey source final-path collision")
    promoted: list[tuple[Path, Path]] = []
    try:
        for name in SOURCE_FILENAMES:
            staged, final = prepared.source_stage / name, SOURCES_ROOT / name
            _promote_noreplace(staged, final)
            promoted.append((final, staged))
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        promoted.append((ARTIFACT, prepared.artifact_stage))
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
    if ARTIFACT.exists() and all((SOURCES_ROOT / name).exists() for name in SOURCE_FILENAMES):
        manifest = validate_artifact()
        _move_capture_to_trash()
        return {"artifact": str(ARTIFACT), "artifact_tree_sha256": tree_digest(ARTIFACT), "capture_trash": str(CAPTURE_TRASH), "manifest_sha256": _sha256(ARTIFACT / "manifest.json"), "recorded_at": manifest["recorded_at"], "source_records": 2, "status": "existing-identical"}
    if ARTIFACT.exists() or ARTIFACT.is_symlink() or any((SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink() for name in SOURCE_FILENAMES):
        raise RuntimeError("partial Sabey source final-path collision")
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
    return {"artifact": str(ARTIFACT), "artifact_tree_sha256": tree_digest(ARTIFACT), "capture_trash": str(CAPTURE_TRASH), "manifest_sha256": _sha256(ARTIFACT / "manifest.json"), "recorded_at": manifest["recorded_at"], "source_records": 2, "status": "published"}


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
