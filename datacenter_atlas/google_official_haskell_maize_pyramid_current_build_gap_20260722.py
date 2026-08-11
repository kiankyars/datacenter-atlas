"""Publish three bounded Google official current-build source records.

The tranche contains exactly one Haskell County Quantum-linked campus/project
pair, Michigan City's Project Maize site works, and West Memphis Project
Pyramid. Three additional Google prospects are retained only as review notes.
Raw official response bytes are represented by exact pins and moved intact to
recoverable Trash after immutable publication.
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
from . import aws_official_clinton_adaptive_reuse_current_build_gap_20260722 as prior
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = (
    "google-official-haskell-maize-pyramid-current-build-gap-2026-07-22-v1"
)
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".google-haskell-maize-pyramid-current-build.lock"

CAPTURE_ORIGIN = Path(
    "/private/tmp/dc-google-haskell-maize-pyramid-20260722.HYTTdd"
)
CAPTURE_TRASH = Path(
    "/Users/kian/.Trash/dc-google-haskell-maize-pyramid-20260722.HYTTdd"
)
CAPTURE_FILE_COUNT = 28
CAPTURE_TOTAL_BYTES = 17_273_154
CAPTURE_TREE_SHA256 = (
    "add36335127c2053c27b180946ea170ddd56fde81d0f9ba8dba25f475298a291"
)

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
V91_TREE_SHA256 = (
    "9c89ab93baf5a13965db764a376affe231186df6a5cbc2758fd9ad95a85a5a5e"
)
V91_INPUT_COUNT = 480
V91_ENTITY_COUNT = 978

_canonical = prior._canonical
_sha256 = prior._sha256
_sha256_bytes = prior._sha256_bytes
_instant = prior._instant
_pin = prior._pin
_fsync_regular = prior._fsync_regular
_fsync_directory = prior._fsync_directory
_promote_noreplace = prior._promote_noreplace


CAPTURE_FILE_PINS: dict[str, tuple[int, str]] = {
    "haskell-google.body": (75_104, "c8e824ee045d9b1c8f5a3e029353094babc80509635044a50fd01e3077e3cbaf"),
    "haskell-google.headers": (1_595, "db01055ca07b2a3460f76c60403162c32fdbb5a69e4d080f8059dd6564774c00"),
    "maize-edcmc.body": (130_395, "21f4b3710f5ba1e9fbce32459726b93a6148b6ba88473279b470f769faa19149"),
    "maize-edcmc.headers": (1_636, "512b53993ebc1cd5b6b6ea96aa32750305040d9d0d99b23c953b28c39d50fda3"),
    "maize-google.body": (75_741, "8c4fb14905acba6692e34b0693b507cc077586e53301a87c0d616636acca0812"),
    "maize-google.headers": (595, "1062784ce2fdac4d22a8302e55d134f6925e2e771dcb310dc77e9a12fe3bc295"),
    "maize-idem.body": (2_273_533, "a1e2c776c363d27495fdcaaf45680248cdc3bfa598f6e0d053c3fa695fe57aca"),
    "maize-idem.headers": (1_293, "cbb1a2fa1d618386f9f61180ae05592ac55a06b3bac4492dfaac433752b05ff8"),
    "pyramid-aedc.body": (85_082, "fd12615d4affdf7577debd744c3229ff9ea6b64b273d5b352b0ebbcb0fe39d98"),
    "pyramid-aedc.headers": (757, "2f0021afc202a0d143d970b24dff776c028f5180d112983e1e810976f7d480f5"),
    "pyramid-serc.body": (13_868_541, "d2117b889bb7fe3c9098a6079e56081ad3644577c06c75bd1e390fbb9ce76b8e"),
    "pyramid-serc.headers": (1_911, "3ae274400474956a9fa8f14fd14d546eecf96f939ac93ee9702da9a71ac81f45"),
    "pyramid-usace-index.body": (444, "670e27889c4e24ffd94e82c3503011d420e99d2abd0421dbeff57642c70709a7"),
    "pyramid-usace-index.headers": (204, "f29fc9ac867d47931ab7b7c997d5b6ba2e8bf4c76e9d5d18c512e34da15b5e1c"),
    "pyramid-usace-jina.body": (371, "f18f91c88e088cfb556cd773a3912ec4ce62a7f803ffde5e20015a4406cd2719"),
    "pyramid-usace-jina.headers": (723, "cfc9ee9e24623d90f6bacc38b33f9012516c55e6becd357ade208721ff422e49"),
    "pyramid-usace.body": (433, "fb36f865d32ef4fbe6ed3f05e4639eece9171a4c4bda0b425be71e1329a88906"),
    "pyramid-usace.headers": (204, "090a367acf62ca99f5bd107c88dbca7c80b51efd22a9037d8d927a4f2b637ea8"),
    "quantum-intersect.body": (48_281, "c078280c74027ae4d7121b63d2411ce494d94d624bb951b3ee8cc630e0fae480"),
    "quantum-intersect.headers": (569, "b4ad24dedadc81a90e0d58803d2f8916c4deace6950aca35210d22572a32cc66"),
    "review-hermantown.body": (142_282, "f23ba4f207a9158addb774b6b5dd94ae5357ef935bb1fba88d56cca7e022951e"),
    "review-hermantown.headers": (1_134, "7748aa9a8db4a16fe3bc4d7a13cdde044a0652891759cf8e78c6a49aa71d6f11"),
    "review-pine-island.body": (79_169, "151944dad236b5f0c50c9a4c8d69518c08ff9c810da979bde35cf06f7af5bfc8"),
    "review-pine-island.headers": (466, "8b8b6f59dda554bbfcc6fc56e3f1a9c93f8cbe4cffd8c050aa6ff8f2b8997a56"),
    "review-spade.body": (103_387, "129ffd694b188f001f78d211dd5b66b5d3e38feb8cb1e3e1c0cb0cc170b90c42"),
    "review-spade.headers": (445, "4e28137e7d1a35be2d09cbe9e6d13e5874c3c40dbfe3e34308a8df98e4e86d41"),
    "texas-google.body": (376_083, "d98e6af00fdb87ca08087e627a930ba4a5d21185a50442d0063c6ebbe6bb1684"),
    "texas-google.headers": (2_776, "0cc64f75da1a7d1b3827e93451f13d726af5c6453afe080265d2d3486b9fb998"),
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
    Capture("google_haskell", "haskell-google", "https://datacenters.google/haskell-county/", "2026-07-22T01:52:00Z", None, 200, "text/html", "normalized_physical_start"),
    Capture("google_texas", "texas-google", "https://blog.google/company-news/inside-google/company-announcements/google-american-innovation-texas/", "2026-07-22T01:52:00Z", "2025-11-14", 200, "text/html; charset=utf-8", "normalized_identity_boundary"),
    Capture("intersect_quantum", "quantum-intersect", "https://www.intersect.com/portfolio/quantum", "2026-07-22T01:52:01Z", None, 200, "text/html; charset=UTF-8", "normalized_identity_and_energy_supply_metadata"),
    Capture("google_maize", "maize-google", "https://www.michigancitydatacenter.com/", "2026-07-22T01:52:01Z", None, 200, "text/html; charset=utf-8", "normalized_identity"),
    Capture("edcmc_maize", "maize-edcmc", "https://edcmc.com/google-acquires-data-center-collaborates-with-community/", "2026-07-22T01:52:01Z", "2026-04-16", 200, "text/html; charset=UTF-8", "normalized_identity_and_address"),
    Capture("idem_maize", "maize-idem", "https://michigancityin.gov/wp-content/uploads/2026/01/IDEM-File_83897119.pdf", "2026-07-22T01:52:01Z", None, 200, "application/pdf", "normalized_site_works"),
    Capture("aedc_pyramid", "pyramid-aedc", "https://www.arkansasedc.com/news-events/newsroom/detail/2025/10/02/google-locating-new-data-center-in-west-memphis--arkansas-with-multi-billion-dollar-investment", "2026-07-22T01:52:01Z", "2025-10-02", 200, "text/html; charset=utf-8", "normalized_physical_status"),
    Capture("serc_pyramid", "pyramid-serc", "https://www.serc.org/wp-content/uploads/default-source.FilePath/about-serc/boardofdirectors/boardmeetingmaterials/2026/Public-June-24-2026-Board-of-Directors-Meeting-Agenda.pdf", "2026-07-22T01:52:01Z", "2026-06-24", 200, "application/pdf", "normalized_identity_only"),
    Capture("review_spade", "review-spade", "https://www.projectspade-missouri.com/", "2026-07-22T01:52:01Z", None, 200, "text/html; charset=utf-8", "review_only_future_start"),
    Capture("review_pine_island", "review-pine-island", "https://pineislandmn.gov/skyway", "2026-07-22T01:52:00Z", None, 200, "text/html", "review_only_under_evaluation"),
    Capture("review_hermantown", "review-hermantown", "https://hermantownmn.com/project/", "2026-07-22T01:52:00Z", None, 200, "text/html; charset=UTF-8", "review_only_under_evaluation"),
    Capture("usace_pdf_failed", "pyramid-usace", "https://www.mvm.usace.army.mil/Portals/51/MVM%202024-216.pdf", "2026-07-22T01:52:13Z", "2024-12-10", 403, "text/html", "failed_coordinate_voltage_source_fetch"),
    Capture("usace_index_failed", "pyramid-usace-index", "https://www.mvm.usace.army.mil/About/Offices/Regulatory/Public-Notices/", "2026-07-22T01:52:29Z", None, 403, "text/html", "failed_official_index_fetch"),
    Capture("usace_proxy_failed", "pyramid-usace-jina", "https://r.jina.ai/https://www.mvm.usace.army.mil/Portals/51/MVM%202024-216.pdf", "2026-07-22T01:52:57Z", None, 401, "application/json; charset=utf-8", "failed_proxy_fetch_not_evidence"),
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
        "google-haskell-county-construction-start-2025-11",
        "google_haskell",
        "Google Haskell County data center",
        "Google",
        "google_data_centers",
        "company_disclosure",
        "Google says its Haskell County construction process began in November 2025 and that it broke ground.",
        {
            "physical_status_as_reported": "Construction process began and Google broke ground in November 2025.",
            "status_date_precision": "month",
            "month_end_as_of_basis": "The source gives November 2025 precision only. November 30 means construction was underway by month-end and does not claim an event on that day.",
            "site_scope_guardrail": "The page is Haskell County scoped and does not identify or authorize separate THM or Journey building/project records.",
        },
    ),
    EvidenceSpec(
        "google-texas-one-haskell-energy-colocation-2025-11-14",
        "google_texas",
        "Google announces Texas data center and energy investments",
        "Google",
        "google_company_blog",
        "company_disclosure",
        "Google says one of its new Haskell County data centers will be built alongside a new solar and battery storage plant.",
        {
            "identity_boundary": "One of Google's new Haskell County data centers is alongside an energy plant; the wording does not collapse every Haskell site into one campus.",
            "multiple_site_guardrail": "Only the independently Quantum-linked campus is promoted in this tranche.",
        },
    ),
    EvidenceSpec(
        "intersect-quantum-google-colocation-observed-2026-07-22",
        "intersect_quantum",
        "Quantum I and II",
        "Intersect Power",
        "intersect_power_portfolio",
        "company_disclosure",
        "Intersect identifies Quantum I and II in Haskell County as co-located with a Google data center campus and says the Google data center recently began construction.",
        {
            "identity_basis": "Quantum I and II, Haskell County, are directly alongside a Google data center campus.",
            "physical_status_as_reported": "The Google data center recently began construction.",
            "energy_supply_metadata": {
                "asset": "Intersect Power Quantum I and II solar and battery energy project",
                "solar_generation_nameplate_mw": 640,
                "battery_storage_energy_gwh": 1.3,
                "relationship": "co-located with and built directly alongside the Google data center campus",
                "normalization": "Source-typed energy-supply metadata only; neither value is data-center IT capacity, utility load, energized capacity, draw, consumption, or annual energy.",
            },
        },
    ),
    EvidenceSpec(
        "google-michigan-city-project-maize-identity-observed-2026-07-22",
        "google_maize",
        "Michigan City Data Center",
        "Google",
        "google_project_site",
        "company_disclosure",
        "Google says it acquired the ongoing Michigan City data center development known as Project Maize.",
        {
            "identity_basis": "Google acquisition of the ongoing development known as Project Maize.",
            "ownership_timing_guardrail": "This current identity statement does not backdate Google ownership to the September 2025 site works.",
        },
    ),
    EvidenceSpec(
        "edcmc-google-project-maize-acquisition-2026-04-16",
        "edcmc_maize",
        "Google acquires data center, collaborates with community",
        "Economic Development Corporation Michigan City",
        "michigan_city_economic_development",
        "government_record",
        "Michigan City's economic-development corporation identifies Google's acquisition of Project Maize at 402 Royal Road, the former Federal-Mogul property.",
        {
            "identity_basis": "Project Maize, 402 Royal Road, former Federal-Mogul property, later acquired by Google.",
            "identity_resolution_date": "2026-04-16",
            "investment_context_not_normalized": "$832 million is investment metadata, not capacity or energy.",
        },
    ),
    EvidenceSpec(
        "idem-project-maize-site-works-inspection-2025-09-24",
        "idem_maize",
        "IDEM file 83897119: Project Maize Data Center",
        "Indiana Department of Environmental Management",
        "indiana_environmental_record",
        "government_record",
        "The IDEM file documents a September 24, 2025 inspection at the Project Maize Data Center site, soil removal, a construction contractor, and constructed berms.",
        {
            "physical_observation_date": "2025-09-24",
            "site_address": "402 Royal Road, Michigan City, Indiana",
            "physical_status_as_reported": "Soils were removed; Blydan was working for Phoenix Construction; soils were retained in constructed berms.",
            "stage_scope": "Site preparation or early site works only; no vertical data-center building start, completion, commissioning, or operation is inferred.",
            "identity_at_observation": "Phoenix Michigan City Industrial Investors LLC owner; Phoenix Construction LLC general contractor.",
        },
    ),
    EvidenceSpec(
        "arkansas-google-west-memphis-construction-2025-10-02",
        "aedc_pyramid",
        "Google locating new data center in West Memphis",
        "Arkansas Economic Development Commission",
        "arkansas_economic_development",
        "government_record",
        "Arkansas says Google is constructing an advanced data center campus in West Memphis across more than 1,000 acres.",
        {
            "physical_status_as_reported": "Google is constructing the West Memphis data center campus.",
            "site_scope": "More than 1,000 acres in West Memphis, Arkansas.",
            "infrastructure_context_not_normalized": "The campus description includes a data center facility, offices, a substation facility, and other infrastructure.",
            "energy_context_guardrail": "Solar and battery wording is not quantified or normalized as capacity, load, consumption, or generation in this source record.",
        },
    ),
    EvidenceSpec(
        "serc-project-pyramid-google-west-memphis-identity-2026-06-24",
        "serc_pyramid",
        "Project Pyramid - Google Campus",
        "SERC Reliability Corporation",
        "serc_board_materials",
        "utility_record",
        "SERC board materials label Project Pyramid as a Google campus in West Memphis, Arkansas.",
        {
            "identity_basis": "Project Pyramid - Google Campus, West Memphis, Arkansas.",
            "scope_guardrail": "Used only to bridge the project codename; deck investment, load, generation, storage, plant, and AI/cloud figures are excluded.",
        },
    ),
)
EVIDENCE_BY_KEY = {evidence.key: evidence for evidence in EVIDENCE}


@dataclass(frozen=True)
class Site:
    slug: str
    campus_key: str
    project_key: str
    campus_name: str
    project_name: str
    address: str
    evidence_keys: tuple[str, ...]
    entity_evidence_key: str
    entity_as_of_date: str
    entity_method: str
    lifecycle_evidence_key: str
    lifecycle_status: str
    lifecycle_as_of_date: str
    lifecycle_method: str
    confidence: float

    @property
    def filename(self) -> str:
        return f"curated-official-2026-07-22-google-{self.slug}.json"


SITES = (
    Site(
        "haskell-quantum-linked-current-build",
        "curated:google-haskell-county-quantum-linked-data-center-campus",
        "curated:google-haskell-county-quantum-linked-data-center-campus:current-development",
        "Google Haskell County Quantum-Linked Data Center Campus",
        "Google Haskell County Quantum-Linked Current Development",
        "Haskell County, Texas, United States",
        (
            "google-haskell-county-construction-start-2025-11",
            "google-texas-one-haskell-energy-colocation-2025-11-14",
            "intersect-quantum-google-colocation-observed-2026-07-22",
        ),
        "intersect-quantum-google-colocation-observed-2026-07-22",
        "2026-07-22",
        "authoritative_locality",
        "google-haskell-county-construction-start-2025-11",
        "under_construction",
        "2025-11-30",
        "authoritative_physical_status_update",
        0.95,
    ),
    Site(
        "michigan-city-project-maize-site-works",
        "curated:google-michigan-city-project-maize-data-center",
        "curated:google-michigan-city-project-maize-data-center:2025-site-works",
        "Google Michigan City Project Maize Data Center",
        "Project Maize 2025 Site Works",
        "402 Royal Road, Michigan City, Indiana, United States",
        (
            "google-michigan-city-project-maize-identity-observed-2026-07-22",
            "edcmc-google-project-maize-acquisition-2026-04-16",
            "idem-project-maize-site-works-inspection-2025-09-24",
        ),
        "edcmc-google-project-maize-acquisition-2026-04-16",
        "2026-04-16",
        "authoritative_locality",
        "idem-project-maize-site-works-inspection-2025-09-24",
        "site_preparation",
        "2025-09-24",
        "authoritative_physical_status_update",
        0.99,
    ),
    Site(
        "west-memphis-project-pyramid-current-build",
        "curated:google-west-memphis-project-pyramid-data-center-campus",
        "curated:google-west-memphis-project-pyramid-data-center-campus:current-development",
        "Google West Memphis Project Pyramid Data Center Campus",
        "Google West Memphis Project Pyramid Current Development",
        "More than 1,000-acre site, West Memphis, Arkansas, United States",
        (
            "arkansas-google-west-memphis-construction-2025-10-02",
            "serc-project-pyramid-google-west-memphis-identity-2026-06-24",
        ),
        "serc-project-pyramid-google-west-memphis-identity-2026-06-24",
        "2026-06-24",
        "authoritative_locality",
        "arkansas-google-west-memphis-construction-2025-10-02",
        "under_construction",
        "2025-10-02",
        "authoritative_physical_status_update",
        0.99,
    ),
)

SOURCE_FILENAMES = tuple(site.filename for site in SITES)
CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))


def _evidence(spec: EvidenceSpec) -> dict[str, Any]:
    capture = CAPTURE_BY_ID[spec.capture_id]
    body_name = f"{capture.file_stem}.body"
    headers_name = f"{capture.file_stem}.headers"
    body_pin = CAPTURE_FILE_PINS[body_name]
    headers_pin = CAPTURE_FILE_PINS[headers_name]
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
        "content_hash": body_pin[1],
        "metadata": {
            "capture_artifact_id": ARTIFACT_ID,
            "capture_request_id": capture.capture_id,
            "capture_method": "credential_free_curl_location",
            "requested_url": capture.url,
            "effective_url": capture.url,
            "request_credentials_supplied": False,
            "http_status": capture.http_status,
            "content_type": capture.content_type,
            "content_hash_scope": f"SHA-256 of the exact {body_pin[0]}-byte public response body",
            "content_hash_verification": "fetched_bytes_sha256",
            "capture_headers_scope": f"SHA-256 of the exact {headers_pin[0]}-byte response-header capture",
            "capture_headers_sha256": headers_pin[1],
            "status_semantics": "dated_last_observed_current_status_unknown",
            "rights_scope": "Compact factual extraction from all-rights-reserved official bytes; raw bytes and publisher media are not redistributed.",
            "normalization_guardrail": "No data-center capacity, load, draw, annual energy, PUE, WUE, operating model, workload, standardized role, or inferred coordinate is normalized.",
            **spec.factual_extract,
        },
    }


def _entity(site: Site, *, project: bool) -> dict[str, Any]:
    return {
        "stable_key": site.project_key if project else site.campus_key,
        "name": site.project_name if project else site.campus_name,
        "country": "United States",
        "address": site.address,
        "roles": {},
        "coordinates": None,
        "geometry": None,
        "evidence_key": site.entity_evidence_key,
        "as_of_date": site.entity_as_of_date,
        "method": site.entity_method,
        "confidence": site.confidence,
    }


def _source(site: Site) -> dict[str, Any]:
    return {
        "schema_version": "1.1",
        "evidence": [
            _evidence(EVIDENCE_BY_KEY[key]) for key in site.evidence_keys
        ],
        "campus": _entity(site, project=False),
        "project": _entity(site, project=True),
        "lifecycle": [
            {
                "entity": "project",
                "value": site.lifecycle_status,
                "evidence_key": site.lifecycle_evidence_key,
                "as_of_date": site.lifecycle_as_of_date,
                "method": site.lifecycle_method,
                "confidence": site.confidence,
            }
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    return {site.filename: _source(site) for site in SITES}


def _source_records(
    documents: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in SOURCE_FILENAMES:
        document = documents[name]
        payload = _canonical(document)
        rows.append(
            {
                "path": f"sources/{name}",
                "bytes": len(payload),
                "sha256": _sha256_bytes(payload),
                "schema_version": "1.1",
                "country": "United States",
                "campus_stable_key": document["campus"]["stable_key"],
                "project_stable_key": document["project"]["stable_key"],
                "evidence_records": len(document["evidence"]),
                "lifecycle_observations": 1,
                "operating_model_observations": 0,
                "workload_observations": 0,
                "capacity_estimates": 0,
                "coordinates_present": 0,
                "geometry_present": 0,
                "disposition": "seed_eligible_bounded_authoritative_physical_status",
                "seed_eligible": True,
                "seeded": False,
            }
        )
    return rows


def _planned_keys(
    documents: Mapping[str, Mapping[str, Any]],
) -> tuple[set[str], set[str]]:
    stable = {
        document[entity]["stable_key"]
        for document in documents.values()
        for entity in ("campus", "project")
    }
    evidence = {
        row["key"]
        for document in documents.values()
        for row in document["evidence"]
    }
    return stable, evidence


def _collision_witness(documents: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    for target, pin in V91_PINS.items():
        _pin(target, pin)
    if tree_digest(V91_RELEASE) != V91_TREE_SHA256:
        raise RuntimeError("v91 release tree differs")
    definition = json.loads(V91_DEFINITION.read_text(encoding="utf-8"))
    selected = definition.get("curated_inputs")
    if not isinstance(selected, list) or len(selected) != V91_INPUT_COUNT:
        raise RuntimeError("v91 selected input inventory differs")
    planned_stable, planned_evidence = _planned_keys(documents)
    with V91_ENTITIES.open(encoding="utf-8", newline="") as stream:
        base_rows = list(csv.DictReader(stream))
    if len(base_rows) != V91_ENTITY_COUNT:
        raise RuntimeError("v91 entity count differs")
    base_stable = {row["stable_key"] for row in base_rows}
    if planned_stable & base_stable:
        raise RuntimeError("planned Google stable key collides with v91")
    identity_patterns = {
        "haskell_quantum": ("haskell county", "quantum-linked"),
        "project_maize": ("project maize", "402 royal road", "michigan city"),
        "project_pyramid": ("project pyramid", "west memphis"),
    }
    hits: dict[str, list[dict[str, str]]] = {}
    for label, patterns in identity_patterns.items():
        matches = []
        for row in base_rows:
            haystack = " ".join(
                (row.get("name") or "", row.get("address") or "", row.get("stable_key") or "")
            ).casefold()
            if any(pattern in haystack for pattern in patterns):
                matches.append(
                    {
                        "stable_key": row["stable_key"],
                        "name": row.get("name") or "",
                        "address": row.get("address") or "",
                    }
                )
        if matches:
            hits[label] = matches
    if hits:
        raise RuntimeError(f"v91 exact locality/codename witness differs: {hits!r}")
    source_inputs = json.loads(
        (V91_RELEASE / "source_inputs.json").read_text(encoding="utf-8")
    ).get("sources")
    base_evidence = {
        key
        for row in source_inputs or []
        if isinstance(row, dict)
        for key in [row.get("provenance", {}).get("curated_record_key")]
        if isinstance(key, str)
    }
    if planned_evidence & base_evidence:
        raise RuntimeError("planned Google evidence key collides with v91")
    return {
        "v91_selected_input_count": len(selected),
        "v91_entity_count": len(base_rows),
        "planned_distinct_stable_keys": len(planned_stable),
        "planned_distinct_evidence_keys": len(planned_evidence),
        "exact_v91_stable_key_collisions": [],
        "exact_v91_evidence_key_collisions": [],
        "exact_v91_haskell_quantum_matches": [],
        "exact_v91_project_maize_matches": [],
        "exact_v91_project_pyramid_matches": [],
        "exact_existing_identity_keys_reused": [],
        "identity_resolution": "Six new bounded curated keys are used; no existing row supplies capacity, coordinates, roles, status, or identity inheritance.",
    }


def _review_note(capture_id: str, **fields: Any) -> dict[str, Any]:
    capture = CAPTURE_BY_ID[capture_id]
    body_pin = CAPTURE_FILE_PINS[f"{capture.file_stem}.body"]
    return {
        "source_url": capture.url,
        "published_at": capture.published_at,
        "retrieved_at": capture.retrieved_at,
        "body_sha256": body_pin[1],
        **fields,
    }


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-current-build-assessment-v1",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "candidate_count": 6,
        "seed_eligible_candidate_count": 3,
        "seed_eligible_source_record_count": 3,
        "review_only_count": 3,
        "regional_completeness_claimed": False,
        "candidates": [
            {
                "candidate_id": "google-haskell-quantum-linked-campus",
                "decision": "seed_eligible_one_bounded_campus_project_pair",
                "source_paths": [f"sources/{SITES[0].filename}"],
                "campus_stable_key": SITES[0].campus_key,
                "project_stable_key": SITES[0].project_key,
                "identity_limit": "Exactly one Quantum-linked Google Haskell County campus and one current-development project. THM and Journey labels are not independently bridged and are not split into records.",
                "lifecycle": {
                    "status": "under_construction",
                    "as_of_date": "2025-11-30",
                    "source_date_precision": "month",
                    "month_end_normalization": "Under construction by the end of November 2025; no November 30 event is claimed.",
                    "current_status_persisted": False,
                },
                "normalized_capacity": None,
                "energy_supply_metadata": {
                    "source_type": "co-located third-party solar and battery supply project",
                    "solar_generation_nameplate_mw": 640,
                    "battery_storage_energy_gwh": 1.3,
                    "not_data_center_capacity_or_consumption": True,
                },
                "coordinates": None,
                "withheld": ["THM/Journey project splits", "data-center capacity/load/draw", "annual energy", "PUE/WUE", "roles", "facility type/workload", "coordinates/geometry"],
            },
            {
                "candidate_id": "google-michigan-city-project-maize",
                "decision": "seed_eligible_site_preparation_with_later_identity_join",
                "source_paths": [f"sources/{SITES[1].filename}"],
                "campus_stable_key": SITES[1].campus_key,
                "project_stable_key": SITES[1].project_key,
                "identity_join": {
                    "physical_observation_evidence_key": "idem-project-maize-site-works-inspection-2025-09-24",
                    "physical_observation_date": "2025-09-24",
                    "owner_at_observation": "Phoenix Michigan City Industrial Investors LLC",
                    "identity_resolution_evidence_key": "edcmc-google-project-maize-acquisition-2026-04-16",
                    "identity_resolution_date": "2026-04-16",
                    "google_ownership_not_backdated": True,
                },
                "lifecycle": {"status": "site_preparation", "as_of_date": "2025-09-24", "current_status_persisted": False},
                "normalized_capacity": None,
                "coordinates": None,
                "withheld": ["vertical construction", "data-center capacity/load/draw", "annual energy", "PUE/WUE", "roles", "facility type/workload", "coordinates/geometry"],
            },
            {
                "candidate_id": "google-west-memphis-project-pyramid",
                "decision": "seed_eligible_authoritative_construction_with_codename_join",
                "source_paths": [f"sources/{SITES[2].filename}"],
                "campus_stable_key": SITES[2].campus_key,
                "project_stable_key": SITES[2].project_key,
                "identity_join": "AEDC supplies Google/West Memphis/construction; SERC supplies Project Pyramid/Google Campus/West Memphis.",
                "lifecycle": {"status": "under_construction", "as_of_date": "2025-10-02", "current_status_persisted": False},
                "normalized_capacity": None,
                "coordinate": None,
                "voltage_metadata": None,
                "usace_omission": "The official MVM-2024-216 PDF and index returned HTTP 403 to the independent raw fetch and the proxy attempt returned 401. Coordinate and 500/230-kV diagram facts are therefore not promoted.",
                "serc_scope": "Identity corroboration only; every MW figure in the board deck is excluded.",
                "withheld": ["data-center capacity/load/draw", "generation/storage figures", "annual energy", "PUE/WUE", "roles", "facility type/workload", "USACE coordinate", "USACE voltage", "geometry"],
            },
            _review_note(
                "review_spade",
                candidate_id="google-new-florence-project-spade",
                decision="review_only_future_physical_start",
                reason="The official project site anticipates groundbreaking in late 2026; it does not establish a completed physical start.",
            ),
            _review_note(
                "review_pine_island",
                candidate_id="google-pine-island-project-skyway",
                decision="review_only_under_evaluation",
                reason="The city says the data center proposal is under evaluation; permits or prospective development do not establish physical start.",
            ),
            _review_note(
                "review_hermantown",
                candidate_id="google-hermantown-potential-campus",
                decision="review_only_under_evaluation",
                reason="The city describes a potential Google project under evaluation and AUAR review, not an established physical start.",
            ),
        ],
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-private-capture-inventory-v3",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "controlled_capture_count": len(CAPTURES),
        "successful_http_200_body_captures": sum(c.http_status == 200 for c in CAPTURES),
        "failed_http_body_captures": sum(c.http_status != 200 for c in CAPTURES),
        "capture_file_count": CAPTURE_FILE_COUNT,
        "capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "raw_capture_redistributed": False,
        "captures": [
            {
                "capture_id": capture.capture_id,
                "requested_url": capture.url,
                "retrieved_at": capture.retrieved_at,
                "published_at": capture.published_at,
                "http_status": capture.http_status,
                "content_type": capture.content_type,
                "claim_use": capture.use,
                "request_credentials_supplied": False,
                "body": {
                    "path": f"{capture.file_stem}.body",
                    "bytes": CAPTURE_FILE_PINS[f"{capture.file_stem}.body"][0],
                    "sha256": CAPTURE_FILE_PINS[f"{capture.file_stem}.body"][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "headers": {
                    "path": f"{capture.file_stem}.headers",
                    "bytes": CAPTURE_FILE_PINS[f"{capture.file_stem}.headers"][0],
                    "sha256": CAPTURE_FILE_PINS[f"{capture.file_stem}.headers"][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
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


def _artifact_documents(
    recorded_at: str,
    source_documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    collision = _collision_witness(source_documents)
    source_records = _source_records(source_documents)
    totals = {
        "candidate_assessments": 6,
        "source_records": 3,
        "seed_eligible_candidates": 3,
        "seed_eligible_source_records": 3,
        "review_only_candidates": 3,
        "distinct_campuses_in_source_records": 3,
        "projects": 3,
        "distinct_entities_in_source_records": 6,
        "new_entities_against_v91": 6,
        "exact_existing_identity_keys_reused": 0,
        "source_document_entity_snapshots": 6,
        "unique_imported_entity_snapshots": 6,
        "source_document_evidence_references": 8,
        "unique_evidence_records": 8,
        "lifecycle_observations": 3,
        "operating_model_observations": 0,
        "workload_observations": 0,
        "capacity_estimates": 0,
        "normalized_critical_it_mw_sum": 0,
        "annual_energy_estimates": 0,
        "pue_estimates": 0,
        "wue_estimates": 0,
        "coordinates_present": 0,
        "geometry_present": 0,
        "satellite_observations": 0,
        "computer_vision_observations": 0,
        "source_typed_energy_supply_metadata_records": 1,
        "voltage_metadata_records": 0,
        "usace_failed_fetch_attempts": 3,
    }
    readme = f"""# Google Haskell, Maize, and Pyramid current-build tranche

This immutable artifact publishes exactly three separate curated-official source records: one Quantum-linked Haskell County campus/current-development pair, Michigan City Project Maize site works, and West Memphis Project Pyramid. New Florence Project Spade, Pine Island Project Skyway, and Hermantown remain review-only notes.

Haskell's November 2025 source precision is preserved: November 30 means construction was underway by month-end, not that an event occurred on that date. The Quantum solar nameplate and battery energy figures remain source-typed third-party energy-supply metadata and are never data-center capacity, load, draw, consumption, or annual energy. THM and Journey labels are not split or promoted.

Project Maize normalizes only site preparation observed on September 24, 2025. The later Google acquisition resolves current identity without backdating Google ownership or claiming vertical construction. Project Pyramid normalizes only the Arkansas construction statement and uses SERC solely for the codename bridge. The official USACE PDF/index returned 403 and the proxy attempt returned 401; no USACE coordinate or voltage is emitted.

No normalized capacity, energy consumption, PUE, WUE, facility type, operating model, workload, standardized role, coordinate, geometry, satellite, aerial, map-click, or computer-vision claim is added. Every lifecycle value is a dated last-observed fact whose current status is unknown.

All source and artifact bytes were staged before {recorded_at}; final paths were absent until that instant and promoted without replacement. Raw captures are represented only by exact hashes and retrieval facts. The intact {CAPTURE_FILE_COUNT}-file directory was moved to recoverable Trash only after publication. No open-seed definition, release, construction master, map, or other downstream integration was created or mutated.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "regional_completeness_claimed": False,
        "source_records": source_records,
        "totals": totals,
        "frozen_v91_non_mutation_witness": {
            "definition": {"path": "sources/open-seed-2026-07-21-v91.json", "bytes": V91_PINS[V91_DEFINITION][0], "sha256": V91_PINS[V91_DEFINITION][1]},
            "release_manifest": {"path": "releases/2026-07-21-open-seed-v91/manifest.json", "bytes": V91_PINS[V91_MANIFEST][0], "sha256": V91_PINS[V91_MANIFEST][1]},
            "release_entities": {"path": "releases/2026-07-21-open-seed-v91/entities.csv", "bytes": V91_PINS[V91_ENTITIES][0], "sha256": V91_PINS[V91_ENTITIES][1]},
            "release_tree_sha256": V91_TREE_SHA256,
            **collision,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v91_mutated": False,
            "open_seed_v92_touched": False,
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
        "source_rights": "Captured official response bodies are treated as all-rights-reserved; no redistribution license was relied on.",
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
        path = paths[name]
        if (
            path.is_symlink()
            or not path.is_file()
            or path.read_bytes() != _canonical(expected[name])
            or stat.S_IMODE(path.stat().st_mode) != 0o444
        ):
            raise RuntimeError(f"curated source differs: {name}")
    documents = list(expected.values())
    if any(
        document[entity][field] is not None
        for document in documents
        for entity in ("campus", "project")
        for field in ("coordinates", "geometry")
    ):
        raise RuntimeError("source invented coordinates or geometry")
    if any(document[entity]["roles"] for document in documents for entity in ("campus", "project")):
        raise RuntimeError("source invented roles")
    if any(document[collection] for document in documents for collection in ("operating_models", "workloads", "capacities")):
        raise RuntimeError("source invented normalized non-lifecycle claims")
    lifecycle = {
        (document["project"]["stable_key"], row["value"], row["as_of_date"], row["method"])
        for document in documents
        for row in document["lifecycle"]
    }
    expected_lifecycle = {
        (site.project_key, site.lifecycle_status, site.lifecycle_as_of_date, site.lifecycle_method)
        for site in SITES
    }
    if lifecycle != expected_lifecycle:
        raise RuntimeError("lifecycle contract differs")
    serialized = {name: json.dumps(document, sort_keys=True) for name, document in expected.items()}
    if "640" not in serialized[SITES[0].filename] or "1.3" not in serialized[SITES[0].filename]:
        raise RuntimeError("Haskell source-typed energy metadata absent")
    if any(token in serialized[SITES[1].filename] for token in ("critical_it_mw", "utility_mw", "annual_energy")):
        raise RuntimeError("Michigan City source contains capacity or energy")
    if any(token in serialized[SITES[2].filename].casefold() for token in ("500/230", "latitude", "longitude", "voltage_kv")):
        raise RuntimeError("West Memphis source contains withheld USACE facts")
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
        stable = {
            row.get("stable_key")
            for key in ("campus", "facility", "building", "project")
            if isinstance((row := document.get(key)), dict)
        }
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
    if (
        len(entries) != CAPTURE_FILE_COUNT
        or set(CAPTURE_FILE_PINS) != {entry.name for entry in entries}
        or any(entry.is_symlink() or not entry.is_file() for entry in entries)
    ):
        raise RuntimeError("capture directory closed set differs")
    if (
        sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES
        or tree_digest(directory) != CAPTURE_TREE_SHA256
    ):
        raise RuntimeError("capture directory aggregate differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(directory / name, pin)


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory(prefix="google-hmp-import-", dir="/private/tmp") as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            for name in SOURCE_FILENAMES:
                adapter.import_file(connection, paths[name], recorded_at=recorded_at)
        validate_database(connection)
        tables = (
            "entities",
            "entity_snapshots",
            "evidence",
            "lifecycle_observations",
            "operating_model_observations",
            "workload_observations",
            "capacity_estimates",
        )
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        }
        expected = {
            "entities": 6,
            "entity_snapshots": 6,
            "evidence": 8,
            "lifecycle_observations": 3,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
        }
        if counts != expected:
            raise RuntimeError(f"offline import counts differ: {counts!r}")
        return counts


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def validate_artifact(
    path: Path = ARTIFACT,
    *,
    source_paths: Mapping[str, Path] | None = None,
    require_live: bool = True,
    wall_clock: datetime | None = None,
) -> dict[str, Any]:
    paths = source_paths or _source_paths(SOURCES_ROOT)
    source_records = _validate_sources(paths)
    if path.is_symlink() or not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise RuntimeError("artifact must be a frozen ordinary directory")
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES or any(
        entry.is_symlink() or not entry.is_file() or stat.S_IMODE(entry.stat().st_mode) != 0o444
        for entry in entries.values()
    ):
        raise RuntimeError("artifact closed frozen set differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if (
        manifest_raw != _canonical(manifest)
        or manifest.get("artifact_id") != ARTIFACT_ID
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or manifest.get("candidate_assessments") != 6
        or manifest.get("curated_source_records") != 3
        or manifest.get("seed_eligible_candidates") != 3
        or manifest.get("review_only_candidates") != 3
        or manifest.get("controlled_capture_count") != 14
        or manifest.get("successful_http_200_body_captures") != 11
        or manifest.get("failed_http_body_captures") != 3
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
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
    totals = snapshot["totals"]
    zero_fields = (
        "capacity_estimates",
        "normalized_critical_it_mw_sum",
        "annual_energy_estimates",
        "pue_estimates",
        "wue_estimates",
        "operating_model_observations",
        "workload_observations",
        "coordinates_present",
        "geometry_present",
        "satellite_observations",
        "computer_vision_observations",
        "voltage_metadata_records",
    )
    if snapshot["source_records"] != source_records or any(totals[field] != 0 for field in zero_fields):
        raise RuntimeError("artifact zero-normalization contract differs")
    assessment = json.loads(entries["candidate-assessment.json"].read_text(encoding="utf-8"))
    if [row["candidate_id"] for row in assessment["candidates"][3:]] != [
        "google-new-florence-project-spade",
        "google-pine-island-project-skyway",
        "google-hermantown-potential-campus",
    ]:
        raise RuntimeError("review-only notes differ")
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


def _write_artifact_stage(
    stage: Path,
    recorded_at: str,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    payloads = _artifact_documents(recorded_at, documents)
    for name in CONTENT_FILES:
        target = stage / name
        target.write_bytes(payloads[name])
        target.chmod(0o444)
        _fsync_regular(target)
    rows = [
        {"bytes": (stage / name).stat().st_size, "path": name, "sha256": _sha256(stage / name)}
        for name in CONTENT_FILES
    ]
    manifest = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-artifact-manifest-v3",
        "recorded_at": recorded_at,
        "files": rows,
        "tree_sha256": _file_tree(rows),
        "closed_file_set": sorted(CLOSED_FILES),
        "candidate_assessments": 6,
        "curated_source_records": 3,
        "seed_eligible_candidates": 3,
        "seed_eligible_source_records": 3,
        "review_only_candidates": 3,
        "controlled_capture_count": 14,
        "successful_http_200_body_captures": 11,
        "failed_http_body_captures": 3,
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
        raise RuntimeError("active Google Haskell/Maize/Pyramid publication lock exists") from error
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
    if (
        any((SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink() for name in SOURCE_FILENAMES)
        or ARTIFACT.exists()
        or ARTIFACT.is_symlink()
    ):
        raise RuntimeError("Google Haskell/Maize/Pyramid final-path collision")
    _validate_source_collisions()
    capture = resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(capture)
    documents = expected_source_documents()
    source_stage = Path(tempfile.mkdtemp(prefix=".google-hmp-sources.", dir=SOURCES_ROOT))
    artifact_stage = Path(tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT))
    try:
        _write_source_stage(source_stage, documents)
        _write_artifact_stage(artifact_stage, recorded_at, documents)
        _assert_stage_precedes(source_stage, recorded_at)
        _assert_stage_precedes(artifact_stage, recorded_at)
        validate_artifact(
            artifact_stage,
            source_paths=_source_paths(source_stage),
            require_live=False,
            wall_clock=_instant(recorded_at),
        )
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
    if (
        any((SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink() for name in SOURCE_FILENAMES)
        or ARTIFACT.exists()
        or ARTIFACT.is_symlink()
    ):
        raise RuntimeError("late Google Haskell/Maize/Pyramid final-path collision")
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
    _validate_capture_directory(resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH))


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    source_exists = all((SOURCES_ROOT / name).exists() for name in SOURCE_FILENAMES)
    if ARTIFACT.exists() and source_exists:
        manifest = validate_artifact()
        _move_capture_to_trash()
        return {
            "artifact": str(ARTIFACT),
            "artifact_tree_sha256": tree_digest(ARTIFACT),
            "capture_trash": str(CAPTURE_TRASH),
            "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
            "recorded_at": manifest["recorded_at"],
            "source_records": 3,
            "status": "existing-identical",
        }
    if (
        ARTIFACT.exists()
        or ARTIFACT.is_symlink()
        or any((SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink() for name in SOURCE_FILENAMES)
    ):
        raise RuntimeError("partial Google Haskell/Maize/Pyramid final-path collision")
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
    return {
        "artifact": str(ARTIFACT),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "capture_trash": str(CAPTURE_TRASH),
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "recorded_at": manifest["recorded_at"],
        "source_records": 3,
        "status": "published",
    }


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
