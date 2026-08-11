"""Publish a hash-bound Meta official current-build source tranche.

Three exact campus/project records are seed eligible. Jamnagar remains
review-only because the captured agreement does not establish a physical start
for the exact project. Raw response bytes remain all-rights-reserved and are
represented only by exact hashes and compact factual extracts.
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

from .external_captures import resolve_external_capture
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from . import global_official_current_build_gap_20260721 as prior
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "meta-official-current-build-gap-2026-07-22-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".meta-official-current-build-gap.lock"

CAPTURE_ORIGIN = Path("/private/tmp/dc-meta-current-build-20260722.gIC9Lb")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-meta-current-build-20260722.gIC9Lb")
CAPTURE_FILE_COUNT = 12
CAPTURE_TOTAL_BYTES = 1_313_782
CAPTURE_TREE_SHA256 = "e585a4fdeca5e00f4a9d24d410d1d8b3240ef0c296685536874416174c698c54"

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
    "all-locations-headers.txt": (857, "4c95d483fe09e4d37c41471b38b815cc31ee31fa868dfc3bbe0f0e62109098f3"),
    "all-locations.body": (151_751, "be57ee5080e271b501ab3bba4a023b5bba69bb5b80191f419739fe176e519026"),
    "beaver-about-headers.txt": (807, "396d72d896787831388931f8a635107c3e61b306fcb2b2b41d674fb52646925a"),
    "beaver-about.body": (540_225, "7c0bc5fb179c2faae2198dabb07a058e1f9d7b160c073f19ecf61c91839210e0"),
    "beaver-dam-headers.txt": (859, "ca570a5323ddfb21c1ded7cd198672d8510a093bc3fa8038344e0d61e2fb6cd4"),
    "beaver-dam.body": (108_376, "610596942caa9bb4bd2ca3fea1e380c949387609b8733e1c199f8887b2b86cdb"),
    "bowling-green-headers.txt": (856, "616e2cef2d0ad01ee1140dff6b97aaf4ef4192139344d66257afa2c70126e305"),
    "bowling-green.body": (88_306, "fcf7daec2eec63911e3dc97dbfa66074373b01ca1cd34ddf5a1984c24c2589c5"),
    "jamnagar-headers.txt": (806, "732336d75228e66b3b033f6363139644e32aa38a4610a8cc4fc2f93c6f832c01"),
    "jamnagar.body": (332_001, "c18eb24b7667afb26e788b9f604c0077bb8733252f608ae37e2ef235ea1b2172"),
    "montgomery-headers.txt": (857, "9002eb7bace90a98dc07c50e08895187f25cb42cb7b16894d9b938a67a3f8e8b"),
    "montgomery.body": (88_081, "5e780d072fbfaa1054c219b4ac4ba1f4d8d7856ce6fb89cc40286c87d6de95de"),
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
    Capture("bowling_green", "bowling-green", "https://datacenters.atmeta.com/2025/04/hello-bowling-green/", "2026-07-22T01:22:45Z", "2025-04-09", 200, "text/html; charset=UTF-8", "normalized"),
    Capture("all_locations", "all-locations", "https://datacenters.atmeta.com/all-locations/", "2026-07-22T01:22:45Z", None, 200, "text/html; charset=UTF-8", "normalized_corroboration"),
    Capture("beaver_about", "beaver-about", "https://about.fb.com/news/2025/11/metas-30th-data-center-delivering-ai-supporting-wetlands-restoration/", "2026-07-22T01:22:45Z", "2025-11-12", 200, "text/html; charset=UTF-8", "normalized"),
    Capture("beaver_dam", "beaver-dam", "https://datacenters.atmeta.com/2025/11/hello-beaver-dam/", "2026-07-22T01:22:47Z", "2025-11-12", 200, "text/html; charset=UTF-8", "normalized_corroboration"),
    Capture("montgomery", "montgomery", "https://datacenters.atmeta.com/2025/09/montgomery-were-growing/", "2026-07-22T01:22:47Z", "2025-09-23", 200, "text/html; charset=UTF-8", "normalized"),
    Capture("jamnagar", "jamnagar", "https://about.fb.com/news/2026/06/meta-partners-with-reliance-on-ai-enabled-data-center-in-india/", "2026-07-22T01:22:47Z", "2026-06-09", 200, "text/html; charset=UTF-8", "review_only_agreement_without_physical_start"),
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
    EvidenceSpec("meta-bowling-green-groundbreaking-2025-04-09", "bowling_green", "Hello Bowling Green", "Meta", "meta_data_centers", "company_disclosure", "Meta identifies Bowling Green as its 28th data center and links the announcement to the campus groundbreaking.", {"physical_status_as_reported": "Bowling Green campus groundbreaking announcement.", "building_area_context_not_normalized": "715,000 square feet.", "investment_context_not_normalized": "More than $800 million.", "construction_workforce_context_not_normalized": "More than 1,000 workers.", "design_context_not_normalized": "The source says the campus is designed to support AI workloads.", "ownership_wording_not_normalized": "The source describes the campus as owned and operated by Meta."}),
    EvidenceSpec("meta-all-locations-observed-2026-07-22", "all_locations", "Meta data center locations", "Meta", "meta_data_centers", "company_disclosure", "Meta's current location directory lists Bowling Green and Beaver Dam with 2025 break-ground entries.", {"physical_status_as_reported": "The current directory corroborates 2025 break-ground years for Bowling Green and Beaver Dam.", "date_scope": "Year-level corroboration only; the dated site announcements provide the exact observation dates."}),
    EvidenceSpec("meta-beaver-dam-groundbreaking-2025-11-12", "beaver_about", "Meta's 30th data center breaks ground in Beaver Dam", "Meta", "meta_about_newsroom", "company_disclosure", "Meta announces that it is breaking ground on its Beaver Dam data center.", {"physical_status_as_reported": "Groundbreaking at Beaver Dam.", "investment_context_not_normalized": "More than $1 billion for the campus.", "construction_workforce_context_not_normalized": "More than 1,000 workers.", "energy_infrastructure_spend_not_capacity": "Nearly $200 million is described as energy-infrastructure spend and is not facility load, IT capacity, grid capacity, generation, or energy use.", "cooling_context_not_normalized": "The source describes dry cooling."}),
    EvidenceSpec("meta-beaver-dam-campus-details-2025-11-12", "beaver_dam", "Hello Beaver Dam", "Meta", "meta_data_centers", "company_disclosure", "Meta describes its new Beaver Dam data center and the construction workforce expected on site.", {"building_area_context_not_normalized": "More than 700,000 square feet.", "investment_context_not_normalized": "More than $1 billion.", "construction_workforce_context_not_normalized": "More than 1,000 workers.", "design_context_not_normalized": "The source says the campus is designed to support AI workloads."}),
    EvidenceSpec("meta-montgomery-two-building-expansion-2025-09-23", "montgomery", "Montgomery, we're growing", "Meta", "meta_data_centers", "company_disclosure", "Meta says construction is underway on two new buildings at its Montgomery data center campus.", {"physical_status_as_reported": "Construction underway on a two-building expansion.", "building_area_context_not_normalized": "Nearly 1.3 million square feet across the two buildings.", "investment_context_not_normalized": "More than $1.5 billion.", "construction_workforce_context_not_normalized": "More than 1,000 workers.", "design_context_not_normalized": "The source says the expansion is designed to support AI workloads.", "renewable_project_context_not_capacity": "227 MW refers to renewable-project generation or procurement context, not facility load, IT capacity, grid capacity, or energy consumption."}),
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
        return f"curated-official-2026-07-22-meta-{self.slug}-current-build.json"


SITES = (
    Site("bowling-green", "United States", "Bowling Green, Wood County, Ohio, United States", "pnnl_im3:2026-02-09:campus/01377162298", "curated:meta-bowling-green-data-center:2025-current-campus-build", "Meta Bowling Green Data Center", "Meta Bowling Green 2025 Current Campus Build", ("meta-bowling-green-groundbreaking-2025-04-09", "meta-all-locations-observed-2026-07-22"), "meta-bowling-green-groundbreaking-2025-04-09", "2025-04-09", "under_construction", "authoritative_construction_start"),
    Site("beaver-dam", "United States", "Beaver Dam, Dodge County, Wisconsin, United States", "pnnl_im3:2026-02-09:campus/01453996659", "curated:meta-beaver-dam-data-center:2025-current-campus-build", "Meta Beaver Dam Data Center", "Meta Beaver Dam 2025 Current Campus Build", ("meta-beaver-dam-groundbreaking-2025-11-12", "meta-beaver-dam-campus-details-2025-11-12", "meta-all-locations-observed-2026-07-22"), "meta-beaver-dam-groundbreaking-2025-11-12", "2025-11-12", "under_construction", "authoritative_construction_start"),
    Site("montgomery-two-building-expansion", "United States", "Co Rd 42, Montgomery, AL 36105, USA", "epoch-ai:data-center:dec73855-d62c-5f35-bd1a-3b1f00b20bec", "curated:meta-montgomery-data-center:2025-two-building-expansion", "Meta Montgomery", "Meta Montgomery 2025 Two-Building Expansion", ("meta-montgomery-two-building-expansion-2025-09-23",), "meta-montgomery-two-building-expansion-2025-09-23", "2025-09-23", "under_construction", "authoritative_physical_status_update"),
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
    return {
        "schema_version": "1.1",
        "evidence": [_evidence(EVIDENCE_BY_KEY[key]) for key in site.evidence_keys],
        "campus": _entity(site, project=False),
        "project": _entity(site, project=True),
        "lifecycle": [{
            "entity": "project", "value": site.status,
            "evidence_key": site.primary_evidence_key, "as_of_date": site.as_of_date,
            "method": site.method, "confidence": 0.99,
        }],
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
            "evidence_records": len(document["evidence"]), "lifecycle_observations": 1,
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
    for path, pin in {**V90_PINS, **MASTER_PINS, GLOBAL_ENTITIES: GLOBAL_ENTITIES_PIN}.items():
        _pin(path, pin)
    if tree_digest(V90_RELEASE) != V90_TREE_SHA256:
        raise RuntimeError("v90 release tree differs")
    if tree_digest(MASTER_RELEASE) != MASTER_TREE_SHA256:
        raise RuntimeError("master v31 tree differs")
    definition = json.loads(V90_DEFINITION.read_text(encoding="utf-8"))
    selected = definition.get("curated_inputs")
    if not isinstance(selected, list) or len(selected) != V90_INPUT_COUNT:
        raise RuntimeError("v90 selected input inventory differs")
    planned_stable, planned_evidence = _planned_keys(documents)
    with V90_ENTITIES.open(encoding="utf-8", newline="") as stream:
        base_rows = list(csv.DictReader(stream))
    base_stable = {row["stable_key"] for row in base_rows}
    montgomery_key = "epoch-ai:data-center:dec73855-d62c-5f35-bd1a-3b1f00b20bec"
    if planned_stable & base_stable != {montgomery_key}:
        raise RuntimeError("planned Meta stable-key collision set differs")
    montgomery = next(
        (row for row in base_rows if row["stable_key"] == montgomery_key), None
    )
    if montgomery is None or {
        field: montgomery[field]
        for field in ("entity_kind", "name", "address", "country")
    } != {
        "entity_kind": "campus",
        "name": "Meta Montgomery",
        "address": "Co Rd 42, Montgomery, AL 36105, USA",
        "country": "United States",
    }:
        raise RuntimeError("v90 Montgomery reuse witness differs")
    source_inputs = json.loads((V90_RELEASE / "source_inputs.json").read_text(encoding="utf-8")).get("sources")
    base_evidence = {
        key for row in source_inputs or [] if isinstance(row, dict)
        for key in [row.get("provenance", {}).get("curated_record_key")]
        if isinstance(key, str)
    }
    if planned_evidence & base_evidence:
        raise RuntimeError("planned Meta evidence key collides with v90")

    with GLOBAL_ENTITIES.open(encoding="utf-8", newline="") as stream:
        global_rows = {row["stable_key"]: row for row in csv.DictReader(stream)}
    exact_global_campus_keys = {
        "pnnl_im3:2026-02-09:campus/01377162298",
        "pnnl_im3:2026-02-09:campus/01453996659",
    }
    forbidden_facility_keys = {
        "osm:way/1377162298",
        "osm:way/1453996659",
    }
    expected_names = {
        "pnnl_im3:2026-02-09:campus/01377162298": "Meta Bowling Green Data Center",
        "pnnl_im3:2026-02-09:campus/01453996659": "Meta Beaver Dam Data Center",
        "osm:way/1377162298": "Meta Bowling Green Data Center",
        "osm:way/1453996659": "Meta Beaver Dam Data Center",
    }
    if {key: global_rows.get(key, {}).get("name") for key in expected_names} != expected_names:
        raise RuntimeError("global-open exact Meta identity witness differs")
    if {
        key: global_rows[key].get("entity_kind") for key in exact_global_campus_keys
    } != {key: "campus" for key in exact_global_campus_keys}:
        raise RuntimeError("PNNL Meta campus-kind witness differs")
    if {
        key: global_rows[key].get("entity_kind") for key in forbidden_facility_keys
    } != {key: "facility" for key in forbidden_facility_keys}:
        raise RuntimeError("forbidden OSM facility-kind witness differs")
    if planned_stable & forbidden_facility_keys:
        raise RuntimeError("Meta source selected a forbidden facility identity")
    return {
        "v90_selected_input_count": len(selected),
        "v90_entity_count": len(base_rows),
        "planned_distinct_stable_keys": len(planned_stable),
        "planned_distinct_evidence_keys": len(planned_evidence),
        "exact_v90_stable_key_collisions": [montgomery_key],
        "exact_v90_evidence_key_collisions": [],
        "exact_global_open_campus_identity_keys_reused": sorted(exact_global_campus_keys),
        "forbidden_global_open_facility_keys": sorted(forbidden_facility_keys),
        "collision_resolution": "Bowling Green and Beaver Dam reuse the exact PNNL campus identities, never the same-name OSM facilities. Montgomery reuses the exact v90 Epoch campus; the official source adds only an older locality snapshot and the new expansion project.",
        "geometry_boundary": "No PNNL, OSM, Epoch, satellite, aerial, map-click, or computer-vision coordinate or geometry is copied into the three official source records.",
    }


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    candidates = [{
        "candidate_id": site.slug,
        "decision": "seed_eligible_direct_authoritative_physical_update",
        "source_paths": [f"sources/{site.filename}"],
        "campus_stable_key": site.campus_key,
        "project_stable_key": site.project_key,
        "lifecycle": {"status": site.status, "as_of_date": site.as_of_date, "method": site.method},
        "withheld": ["current-status extrapolation", "capacity or energy", "PUE or WUE", "facility type or workload", "standardized role", "coordinates or geometry"],
    } for site in SITES]
    candidates.append({
        "candidate_id": "jamnagar-reliance-lease-agreement",
        "decision": "review_only_agreement_without_physical_start",
        "source_paths": [], "seed_eligible": False,
        "capture_id": "jamnagar",
        "official_factual_extract": "Meta and Reliance announced an agreement under which Reliance will build a 168 MW data center in Jamnagar and Meta will lease capacity.",
        "boundary": "The agreement allocates future build and lease roles but reports no physical start, so it creates no entity, lifecycle, role, operating-model, capacity, energy, coordinate, or geometry claim.",
    })
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-current-build-assessment-v1",
        "research_date": "2026-07-22", "recorded_at": recorded_at,
        "candidate_count": 4, "seed_eligible_candidate_count": 3,
        "seed_eligible_source_record_count": 3, "review_only_count": 1,
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
        "candidate_assessments": 4, "source_records": 3,
        "seed_eligible_candidates": 3, "seed_eligible_source_records": 3,
        "review_only_candidates": 1, "distinct_campuses_in_source_records": 3,
        "projects": 3, "distinct_entities_in_source_records": 6,
        "new_entities_against_v90": 5,
        "exact_global_open_campus_identity_keys_reused": 2,
        "exact_v90_entity_keys_reused": 1,
        "source_document_entity_snapshots": 6,
        "unique_imported_entity_snapshots": 6,
        "source_document_evidence_references": 6,
        "unique_evidence_records": 5, "lifecycle_observations": 3,
        "operating_model_observations": 0, "workload_observations": 0,
        "capacity_estimates": 0, "coordinates_present": 0, "geometry_present": 0,
    }
    readme = f"""# Meta official current-build gap tranche

This immutable artifact closes six credential-free official captures and publishes three named, seed-eligible campus/project records. Bowling Green and Beaver Dam reuse exact global-open-v3 PNNL campus keys after pinned collision audits, never the same-name OSM facility keys. Montgomery reuses the exact v90 Epoch campus and adds only an older official locality snapshot plus the new expansion project; v91 must preserve the newer v90 campus export byte-identically. Jamnagar remains review-only because the agreement assigns a future Reliance build and Meta lease but reports no physical start.

Building area, investment, workforce, AI-design, ownership wording, dry cooling, energy-infrastructure spend, and renewable-project context remain factual evidence metadata only. No capacity, energy use, generation, PUE, WUE, facility type, operating model, workload, standardized role, current-status extrapolation, coordinate, geometry, satellite, aerial, map-click, or computer-vision claim is added. All normalized statuses are dated last-observed facts whose current status is unknown.

All source and artifact bytes were staged before {recorded_at}; final paths were absent until that instant and promoted without replacement. Raw all-rights-reserved captures are represented only by exact hashes and retrieval facts. The intact {CAPTURE_FILE_COUNT}-file raw capture directory was moved to recoverable Trash only after successful source publication.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at, "research_date": "2026-07-22",
        "regional_completeness_claimed": False,
        "source_records": source_records, "totals": totals,
        "frozen_v90_non_mutation_witness": {
            "definition": {"path": "sources/open-seed-2026-07-21-v90.json", "bytes": V90_PINS[V90_DEFINITION][0], "sha256": V90_PINS[V90_DEFINITION][1]},
            "release_manifest": {"path": "releases/2026-07-21-open-seed-v90/manifest.json", "bytes": V90_PINS[V90_MANIFEST][0], "sha256": V90_PINS[V90_MANIFEST][1]},
            "release_entities": {"path": "releases/2026-07-21-open-seed-v90/entities.csv", "bytes": V90_PINS[V90_ENTITIES][0], "sha256": V90_PINS[V90_ENTITIES][1]},
            "release_tree_sha256": V90_TREE_SHA256,
            **collision,
        },
        "integration": {
            "open_seed_successor_created": False, "open_seed_v90_mutated": False,
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
    with tempfile.TemporaryDirectory(prefix="meta-current-build-import-", dir="/private/tmp") as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            for name in SOURCE_FILENAMES:
                adapter.import_file(connection, paths[name], recorded_at=recorded_at)
        validate_database(connection)
        tables = ("entities", "entity_snapshots", "evidence", "lifecycle_observations", "operating_model_observations", "workload_observations", "capacity_estimates")
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
        expected = {"entities": 6, "entity_snapshots": 6, "evidence": 5, "lifecycle_observations": 3, "operating_model_observations": 0, "workload_observations": 0, "capacity_estimates": 0}
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
    if manifest_raw != _canonical(manifest) or manifest.get("artifact_id") != ARTIFACT_ID or set(manifest.get("closed_file_set", [])) != CLOSED_FILES or manifest.get("candidate_assessments") != 4 or manifest.get("curated_source_records") != 3 or manifest.get("seed_eligible_candidates") != 3 or manifest.get("review_only_candidates") != 1 or _file_tree(manifest["files"]) != manifest.get("tree_sha256"):
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
        "closed_file_set": sorted(CLOSED_FILES), "candidate_assessments": 4,
        "curated_source_records": 3, "seed_eligible_candidates": 3,
        "seed_eligible_source_records": 3, "review_only_candidates": 1,
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
        raise RuntimeError("active Meta source publication lock exists") from error
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
        raise RuntimeError("Meta source final-path collision")
    _validate_source_collisions()
    capture = resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(capture)
    documents = expected_source_documents()
    source_stage = Path(tempfile.mkdtemp(prefix=".meta-current-build-sources.", dir=SOURCES_ROOT))
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
        raise RuntimeError("late Meta source final-path collision")
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
    _validate_capture_directory(resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH))


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    if ARTIFACT.exists() and all((SOURCES_ROOT / name).exists() for name in SOURCE_FILENAMES):
        manifest = validate_artifact()
        _move_capture_to_trash()
        return {"artifact": str(ARTIFACT), "artifact_tree_sha256": tree_digest(ARTIFACT), "capture_trash": str(CAPTURE_TRASH), "manifest_sha256": _sha256(ARTIFACT / "manifest.json"), "recorded_at": manifest["recorded_at"], "source_records": 3, "status": "existing-identical"}
    if ARTIFACT.exists() or ARTIFACT.is_symlink() or any((SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink() for name in SOURCE_FILENAMES):
        raise RuntimeError("partial Meta source final-path collision")
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
    return {"artifact": str(ARTIFACT), "artifact_tree_sha256": tree_digest(ARTIFACT), "capture_trash": str(CAPTURE_TRASH), "manifest_sha256": _sha256(ARTIFACT / "manifest.json"), "recorded_at": manifest["recorded_at"], "source_records": 3, "status": "published"}


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
