"""Publish four governed US operator-gap source records.

The raw Riot, DataBank, and LinkedIn responses are all-rights-reserved and are
not redistributed.  This module binds compact factual extracts to exact
credential-free capture hashes, publishes four schema-1.1 records, and keeps
all lifecycle values as dated last-observed facts.
"""

from __future__ import annotations

from contextlib import contextmanager
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
from . import global_official_builds_six_candidate_20260721 as publication
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "global-official-builds-us-operator-gap-2026-07-21-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".global-official-builds-us-operator-gap.lock"
CAPTURE_ORIGIN = Path("/private/tmp/dc-riot-20260721.DX92tY")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-riot-20260721.DX92tY")
CAPTURE_FILE_COUNT = 17
CAPTURE_TOTAL_BYTES = 1_477_617
CAPTURE_TREE_SHA256 = "f84faf31a6aaedbef2399d14f77399ad34b0c48a0a90b4b88f4eaf0c3abea284"

V86_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v86.json"
V86_RELEASE = ROOT / "releases/2026-07-21-open-seed-v86"
V86_MANIFEST = V86_RELEASE / "manifest.json"
V86_PINS = {
    V86_DEFINITION: (
        102_240,
        "2a2f0cded9e95efd2ab90cbde1d8ad11306b14f019f42cb14086fb80a63fb25d",
    ),
    V86_MANIFEST: (
        15_531,
        "5bc24a692e2d4fc793192f03bd23fa921e434661a0675e6612370d354cf11488",
    ),
}
V86_TREE_SHA256 = "593fe37f16cc81bd6e2011c9b893251be4041dc54376ffec2f743a510fb4d4de"
V86_INPUT_COUNT = 452

SOURCE_FILENAMES = (
    "curated-official-2026-07-21-riot-rockdale-amd-25mw-retrofit.json",
    "curated-official-2026-07-21-riot-rockdale-amd-first-phase-operational-closure.json",
    "curated-official-2026-07-21-databank-atl5-current-build.json",
    "curated-official-2026-07-21-databank-atl6-current-build.json",
)
CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

USOperatorGapError = publication.OfficialBuildsError
_canonical = publication._canonical
_sha256 = publication._sha256
_sha256_bytes = publication._sha256_bytes
_instant = publication._instant
_pin = publication._pin
_fsync_regular = publication._fsync_regular
_fsync_directory = publication._fsync_directory
_promote_noreplace = publication._promote_noreplace


CAPTURE_FILE_PINS: dict[str, tuple[int, str]] = {
    "databank-atl5-headers.txt": (7_435, "d9530624dca423475808c2a8e39dcda06227b6382202cf257e47a58bc41f0a87"),
    "databank-atl5.html": (115_155, "ee90bf259495bba3118b253e8d289b390d8901fe44a454b1d56628c280cd93da"),
    "databank-atl6-headers.txt": (7_095, "5960f95121532a4d9d6a90ca5797c4e6188a5a74f495dd173c98ad95204250fa"),
    "databank-atl6.html": (114_551, "387ce3b0ac183fcd840e02fda2907b53f2fb1af6730917d7c4b6fb188f8d7f9d"),
    "databank-campus-headers.txt": (7_098, "9ebbcc0e551cd8b628015d0b967e12bc301615a1a90ce48a0f87edaa7b6fce28"),
    "databank-campus.html": (119_287, "5cac1845447f1c7dd34316c0b8be0eca0b557a8337dd808994140e0c72c06a94"),
    "databank-social-headers.txt": (5_616, "9b0fe9276456988124dcbb8e2f9d1dadab388c747d06bbb9bed80593da6a1199"),
    "databank-social.html": (350_468, "583fc0eba75e0de52d1573bc0b48445ad98d39772c0f58e62f1f99a994d4ffe0"),
    "fy-company-headers.txt": (900, "1dfd56d5ba48ec0188821b5c25381352254dfada39338c9cabd98b364322aced"),
    "fy-company.html": (268_680, "8865f089c0e4fd114f6dd76b98eeaf1ae5c80634a802b61e069241bfcb1c78fc"),
    "lease-company-headers.txt": (896, "83bd3363d05fba99ba2ce002142543d1e17f83c3c61a776929125248891ea499"),
    "lease-company.html": (222_884, "0492499f423b565db251b8a83eb9eba42ac2a3f3adf83c4b92b662d4cb680118"),
    "lease-headers.txt": (322, "bc9d82624e958ca4ac484c1ea81071defd84c7a40478da05ac689345c58b791d"),
    "q1-company-headers.txt": (899, "df268b20bf57a030481c48903c1f408324764871f0e3724e601244ee5906c475"),
    "q1-company.html": (255_687, "cbdb3d424ca00ba3a514e88540df630ef067ba6ff67c093c41593cf083ef324e"),
    "q1-headers.txt": (322, "bc9d82624e958ca4ac484c1ea81071defd84c7a40478da05ac689345c58b791d"),
    "q1-sec-headers.txt": (322, "c64179027783af4922e45fed4e9b09b96a3904d459bbe03adf12da9c7ec24859"),
}


CAPTURES: dict[str, dict[str, Any]] = {
    "riot_lease": {
        "body": "lease-company.html",
        "headers": "lease-company-headers.txt",
        "url": "https://www.riotplatforms.com/riot-announces-fee-simple-acquisition-of-land-and-first-data-center-lease-with-amd-at-the-rockdale-site/",
        "effective_url": "https://www.riotplatforms.com/riot-announces-fee-simple-acquisition-of-land-and-first-data-center-lease-with-amd-at-the-rockdale-site/",
        "retrieved_at": "2026-07-21T23:43:46Z",
        "published_at": "2026-01-16",
        "http_status": 200,
        "content_type": "text/html; charset=UTF-8",
        "used": True,
    },
    "riot_fy": {
        "body": "fy-company.html",
        "headers": "fy-company-headers.txt",
        "url": "https://www.riotplatforms.com/riot-platforms-reports-full-year-2025-financial-results-and-strategic-highlights/",
        "effective_url": "https://www.riotplatforms.com/riot-platforms-reports-full-year-2025-financial-results-and-strategic-highlights/",
        "retrieved_at": "2026-07-21T23:43:48Z",
        "published_at": "2026-03-02",
        "http_status": 200,
        "content_type": "text/html; charset=UTF-8",
        "used": True,
    },
    "riot_q1": {
        "body": "q1-company.html",
        "headers": "q1-company-headers.txt",
        "url": "https://www.riotplatforms.com/riot-platforms-reports-first-quarter-2026-financial-results-and-strategic-highlights/",
        "effective_url": "https://www.riotplatforms.com/riot-platforms-reports-first-quarter-2026-financial-results-and-strategic-highlights/",
        "retrieved_at": "2026-07-21T23:43:48Z",
        "published_at": "2026-04-30",
        "http_status": 200,
        "content_type": "text/html; charset=UTF-8",
        "used": False,
    },
    "databank_campus": {
        "body": "databank-campus.html",
        "headers": "databank-campus-headers.txt",
        "url": "https://www.databank.com/data-centers/atlanta/lithia-springs/",
        "effective_url": "https://www.databank.com/data-centers/atlanta/lithia-springs/",
        "retrieved_at": "2026-07-21T23:52:19Z",
        "published_at": "2025-01-23",
        "http_status": 200,
        "content_type": "text/html; charset=UTF-8",
        "used": True,
    },
    "databank_atl5": {
        "body": "databank-atl5.html",
        "headers": "databank-atl5-headers.txt",
        "url": "https://www.databank.com/data-centers/atlanta/lithia-springs/atl5/",
        "effective_url": "https://www.databank.com/data-centers/atlanta/lithia-springs/4764-bakers-ferry-rd/",
        "retrieved_at": "2026-07-21T23:52:20Z",
        "published_at": "2026-05-14",
        "http_status": 200,
        "content_type": "text/html; charset=UTF-8",
        "used": True,
    },
    "databank_atl6": {
        "body": "databank-atl6.html",
        "headers": "databank-atl6-headers.txt",
        "url": "https://www.databank.com/data-centers/atlanta/lithia-springs/atl6/",
        "effective_url": "https://www.databank.com/data-centers/atlanta/lithia-springs/atl6/",
        "retrieved_at": "2026-07-21T23:52:21Z",
        "published_at": "2026-05-14",
        "http_status": 200,
        "content_type": "text/html; charset=UTF-8",
        "used": True,
    },
    "databank_social": {
        "body": "databank-social.html",
        "headers": "databank-social-headers.txt",
        "url": "https://www.linkedin.com/posts/databank_atl5-atl6-construction-update-activity-7458169639072718848-KS-b",
        "effective_url": "https://www.linkedin.com/posts/databank_atl5-atl6-construction-update-activity-7458169639072718848-KS-b",
        "retrieved_at": "2026-07-21T23:52:22Z",
        "published_at": "2026-05-07",
        "http_status": 200,
        "content_type": "text/html; charset=utf-8",
        "used": True,
    },
}


def _evidence(
    capture_id: str,
    *,
    key: str,
    title: str,
    publisher: str,
    source_family: str,
    excerpt: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    capture = CAPTURES[capture_id]
    body_bytes, body_sha = CAPTURE_FILE_PINS[capture["body"]]
    header_bytes, header_sha = CAPTURE_FILE_PINS[capture["headers"]]
    common = {
        "content_hash_scope": f"SHA-256 of the exact {body_bytes}-byte content-decoded credential-free public response body",
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_headers_scope": f"SHA-256 of the exact {header_bytes}-byte raw HTTP response-header capture",
        "capture_headers_sha256": header_sha,
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture_id,
        "capture_method": "credential_free_curl_location_compressed",
        "http_status": capture["http_status"],
        "content_type": capture["content_type"],
        "requested_url": capture["url"],
        "effective_url": capture["effective_url"],
        "request_credentials_supplied": False,
        "rights_scope": "Compact factual extraction from all-rights-reserved official bytes; raw body, headers, telemetry, and publisher media are not redistributed.",
        "status_semantics": "dated_last_observed_current_status_unknown",
        "imagery_guardrail": "No publisher image, satellite image, aerial image, computer vision, map click, or analyst geolocation contributes to a normalized claim.",
    }
    common.update(metadata)
    return {
        "key": key,
        "kind": "company_disclosure",
        "title": title,
        "source_url": capture["effective_url"],
        "publisher": publisher,
        "source_family": source_family,
        "published_at": capture["published_at"],
        "retrieved_at": capture["retrieved_at"],
        "license": "all-rights-reserved",
        "attribution": publisher,
        "excerpt": excerpt,
        "content_hash": body_sha,
        "metadata": common,
    }


RIOT_LEASE_EVIDENCE = "riot-rockdale-amd-25mw-retrofit-captured-2026-07-21"
RIOT_FY_EVIDENCE = "riot-rockdale-amd-first-phase-operational-captured-2026-07-21"
DATABANK_CAMPUS_EVIDENCE = "databank-lithia-springs-campus-page-captured-2026-07-21"
DATABANK_SOCIAL_EVIDENCE = "databank-atl5-atl6-physical-construction-captured-2026-07-21"
DATABANK_ATL5_EVIDENCE = "databank-atl5-facility-page-captured-2026-07-21"
DATABANK_ATL6_EVIDENCE = "databank-atl6-facility-page-captured-2026-07-21"


def _riot_lease_evidence() -> dict[str, Any]:
    return _evidence(
        "riot_lease",
        key=RIOT_LEASE_EVIDENCE,
        title="Riot first data center lease with AMD at Rockdale",
        publisher="Riot Platforms, Inc.",
        source_family="riot_platforms_company_news",
        excerpt="Riot reports that it commenced retrofitting one existing Rockdale building for an initial 25 MW critical-IT lease deployment to AMD.",
        metadata={
            "location_as_reported": "Rockdale Site on 200 acres in Milam County, Texas",
            "physical_status_as_reported": "commenced retrofitting one of its existing buildings",
            "status_scope": "The explicit commenced-retrofitting wording supports under_construction for one existing-building retrofit on 2026-01-16; it does not establish delivery, completion, commissioning, energization, or operation.",
            "capacity_wording_as_reported": "initial deployment of 25 MW of critical IT load capacity",
            "capacity_scope": "25 MW is retained once as planned project critical-IT capacity under the signed initial lease. It is not current load, measured consumption, gross power, generation, annual energy, or PUE.",
            "tenant_as_reported": "Advanced Micro Devices, Inc. (AMD)",
            "future_option_guardrail": "The 75 MW option, 100 MW right of first refusal, 200 MW potential lease total, 700 MW site interconnection, and future conversion intention create no project, capacity, lifecycle, load, or energy row.",
            "delivery_forecast_guardrail": "Expected phased delivery through May 2026 creates no later lifecycle observation.",
            "workload_guardrail": "AMD identity and high-performance-computing language create no normalized workload, hardware, accelerator, model, user, or utilization observation.",
            "coordinate_guardrail": "Milam County is retained as broad authoritative locality only; no coordinate, parcel, point, footprint, or geometry is inferred.",
        },
    )


def _riot_fy_evidence() -> dict[str, Any]:
    return _evidence(
        "riot_fy",
        key=RIOT_FY_EVIDENCE,
        title="Riot full-year 2025 results and strategic highlights",
        publisher="Riot Platforms, Inc.",
        source_family="riot_platforms_company_news",
        excerpt="Riot reports that operations on the first phase of its AMD lease had successfully commenced, generating revenue, as of January 2026.",
        metadata={
            "physical_status_as_reported": "successfully commenced operations on the first phase of the lease with AMD, generating revenue, as of January 2026",
            "month_end_as_of_date": "2026-01-31",
            "month_end_as_of_basis": "The source gives only month precision. Month-end means the first phase was operational by the end of January 2026, not that operation began exactly on January 31.",
            "status_scope": "The statement supports operational status only for a distinct first-phase project identity. It does not advance the entire existing-building retrofit, full initial 25 MW lease, Rockdale site, or later expansion.",
            "capacity_guardrail": "The results page does not state the first phase's MW. No capacity is allocated to the operational phase and the separate 25 MW whole-initial-lease value is not inherited.",
            "revenue_guardrail": "Revenue wording corroborates operation but creates no contract-value, utilization, current-load, energy-consumption, or financial row.",
            "workload_guardrail": "AMD identity creates no normalized workload, hardware, accelerator, model, user, or utilization observation.",
        },
    )


def _databank_campus_evidence() -> dict[str, Any]:
    return _evidence(
        "databank_campus",
        key=DATABANK_CAMPUS_EVIDENCE,
        title="DataBank Lithia Springs Campus",
        publisher="DataBank Holdings, Ltd.",
        source_family="databank_facility_pages",
        excerpt="DataBank identifies ATL5 and ATL6 at 4764 Bakers Ferry Road SW in South Fulton and labels them 48 MW and 72 MW critical IT load respectively.",
        metadata={
            "page_original_published_at": "2022-11-21T19:56:58+00:00",
            "page_modified_at": "2025-01-23T17:48:42+00:00",
            "publication_date_scope": "published_at uses the current page's schema.org dateModified.",
            "address_as_reported": "4764 Bakers Ferry Rd. SW - South Fulton, GA 30336",
            "campus_scope_as_reported": "two facilities, ATL5 and ATL6, with up to 120 MW critical IT load",
            "capacity_scope": "The campus page corroborates facility-specific 48 MW and 72 MW critical-IT labels. Only those two facility rows are normalized; the 120 MW campus total is not added separately.",
            "substation_guardrail": "The adjacent 180 MW Georgia Power substation is upstream infrastructure, not data-center critical IT, current load, energy use, or generation, and is not normalized.",
            "coordinate_guardrail": "The exact publisher address is retained as text only. No coordinate, parcel, map destination, point, footprint, or geometry is inferred.",
        },
    )


def _databank_social_evidence() -> dict[str, Any]:
    return _evidence(
        "databank_social",
        key=DATABANK_SOCIAL_EVIDENCE,
        title="ATL5 and ATL6 construction update",
        publisher="DataBank",
        source_family="databank_official_linkedin",
        excerpt="DataBank reports concrete, steel, roofing, MEP, and interior work at ATL5 and generator-yard, dunnage-platform, and data-hall construction at ATL6.",
        metadata={
            "structured_date_published": "2026-05-07T15:03:28.023Z",
            "publication_date_scope": "The public post encodes its exact datePublished in schema.org SocialMediaPosting metadata.",
            "atl5_physical_work_as_reported": "generator-yard concrete pours, structural steel and roofing, MEP systems, framing, drywall, raised flooring, and electrical rough-in",
            "atl6_physical_work_as_reported": "generator-yard development, dunnage-platform work, and continued data-hall construction",
            "status_scope": "Direct present-tense facility-specific physical work supports under_construction for ATL5 and ATL6 on 2026-05-07; it does not establish completion, commissioning, energization, occupancy, or operation.",
            "workload_guardrail": "AI, cloud, high-density, and future-facing language creates no normalized workload, hardware, tenant, customer, user, or utilization observation.",
            "publisher_media_guardrail": "The post's images are disclosure context only and are not redistributed or used for computer-vision inference.",
        },
    )


def _databank_facility_evidence(facility: str, megawatts: int) -> dict[str, Any]:
    capture_id = f"databank_{facility.casefold()}"
    key = DATABANK_ATL5_EVIDENCE if facility == "ATL5" else DATABANK_ATL6_EVIDENCE
    original = "2023-11-27T21:06:13+00:00" if facility == "ATL5" else "2024-12-03T19:18:57+00:00"
    return _evidence(
        capture_id,
        key=key,
        title=f"DataBank {facility} Lithia Springs facility page",
        publisher="DataBank Holdings, Ltd.",
        source_family="databank_facility_pages",
        excerpt=f"DataBank's {facility} page identifies the facility at 4764 Bakers Ferry Road SW, labels {megawatts} MW critical IT load, and advertises Cabinets & Cages colocation.",
        metadata={
            "page_original_published_at": original,
            "page_modified_at": "2026-05-14T19:00:18+00:00",
            "publication_date_scope": "published_at uses the current page's schema.org dateModified.",
            "address_as_reported": "4764 Bakers Ferry Rd. SW - South Fulton, GA 30336",
            "capacity_wording_as_reported": f"{megawatts}MW Critical IT Load",
            "capacity_scope": f"The exact {facility} value is retained once as project critical_it_mw at design stage. It is not current operating load, gross demand, grid connection, generation, annual energy, PUE, or measured consumption.",
            "operating_model_as_reported": "Cabinets & Cages Colocation",
            "operating_model_scope": "The facility-specific service listing supports generic project-level colocation only; it identifies no tenant or customer.",
            "workload_guardrail": "Enterprise, hyperscale, HPC, AI, rack-density, and cooling-capability language describes supported designs, not an active workload, installed hardware, tenant, customer, or user.",
            "renewable_guardrail": "Any renewable-energy label creates no procurement volume, delivered electricity, current load, annual energy, generation, additionality, emissions, PUE, or WUE observation.",
            "forecast_guardrail": "Future-tense service and go-live language creates no completion, commissioning, energization, occupancy, or operational observation.",
            "coordinate_guardrail": "The publisher address is retained as text only; no coordinate, parcel, map destination, point, footprint, or geometry is inferred.",
        },
    )


def _entity(*, stable_key: str, name: str, address: str, roles: Mapping[str, list[str]], evidence_key: str, as_of_date: str) -> dict[str, Any]:
    return {
        "stable_key": stable_key,
        "name": name,
        "country": "United States",
        "address": address,
        "roles": dict(roles),
        "coordinates": None,
        "geometry": None,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": "authoritative_locality",
        "confidence": 0.99,
    }


def _capacity(*, entity: str, base: float, stage: str, evidence_key: str, as_of_date: str, notes: str) -> dict[str, Any]:
    return {
        "entity": entity,
        "metric": "critical_it_mw",
        "stage": stage,
        "unit": "MW",
        "low": base,
        "base": base,
        "high": base,
        "method": "reported",
        "confidence": 0.99,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "target_date": None,
        "notes": notes,
    }


def _classification(*, evidence_key: str, as_of_date: str) -> dict[str, Any]:
    return {
        "entity": "project",
        "value": "colocation",
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": "company_disclosure",
        "confidence": 0.99,
    }


def _riot_retrofit_source() -> dict[str, Any]:
    roles = {"developer": ["Riot Platforms, Inc."], "operator": ["Riot Platforms, Inc."], "tenant": ["Advanced Micro Devices, Inc."]}
    campus = "curated:riot-rockdale-site"
    project = f"{campus}:amd-25mw-existing-building-retrofit"
    address = "Milam County, Texas, United States"
    evidence = _riot_lease_evidence()
    return {
        "schema_version": "1.1",
        "evidence": [evidence],
        "campus": _entity(stable_key=campus, name="Riot Rockdale Site", address=address, roles=roles, evidence_key=RIOT_LEASE_EVIDENCE, as_of_date="2026-01-16"),
        "project": _entity(stable_key=project, name="Riot Rockdale AMD Initial 25 MW Existing-Building Retrofit", address=address, roles=roles, evidence_key=RIOT_LEASE_EVIDENCE, as_of_date="2026-01-16"),
        "lifecycle": [{"entity": "project", "value": "under_construction", "evidence_key": RIOT_LEASE_EVIDENCE, "as_of_date": "2026-01-16", "method": "authoritative_physical_status_update", "confidence": 0.99}],
        "operating_models": [],
        "workloads": [],
        "capacities": [_capacity(entity="project", base=25.0, stage="planned", evidence_key=RIOT_LEASE_EVIDENCE, as_of_date="2026-01-16", notes="Initial whole-lease critical-IT capacity under retrofit; not current load, energy use, or the later first-phase capacity.")],
    }


def _riot_operational_source() -> dict[str, Any]:
    roles = {"developer": ["Riot Platforms, Inc."], "operator": ["Riot Platforms, Inc."], "tenant": ["Advanced Micro Devices, Inc."]}
    campus = "curated:riot-rockdale-site"
    project = f"{campus}:amd-lease-first-phase"
    address = "Milam County, Texas, United States"
    return {
        "schema_version": "1.1",
        "evidence": [_riot_lease_evidence(), _riot_fy_evidence()],
        "campus": _entity(stable_key=campus, name="Riot Rockdale Site", address=address, roles=roles, evidence_key=RIOT_LEASE_EVIDENCE, as_of_date="2026-01-16"),
        "project": _entity(stable_key=project, name="Riot Rockdale AMD Lease First Phase", address=address, roles=roles, evidence_key=RIOT_FY_EVIDENCE, as_of_date="2026-03-02"),
        "lifecycle": [{"entity": "project", "value": "operational", "evidence_key": RIOT_FY_EVIDENCE, "as_of_date": "2026-01-31", "method": "authoritative_status_update", "confidence": 0.99}],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _databank_source(facility: str, megawatts: int) -> dict[str, Any]:
    roles = {"developer": ["DataBank"], "operator": ["DataBank"]}
    campus = "curated:databank-lithia-springs-campus"
    project = f"{campus}:{facility.casefold()}-current-build"
    address = "4764 Bakers Ferry Rd SW, South Fulton, Georgia 30336, United States"
    facility_evidence = DATABANK_ATL5_EVIDENCE if facility == "ATL5" else DATABANK_ATL6_EVIDENCE
    return {
        "schema_version": "1.1",
        "evidence": [_databank_campus_evidence(), _databank_facility_evidence(facility, megawatts), _databank_social_evidence()],
        "campus": _entity(stable_key=campus, name="DataBank Lithia Springs Campus", address=address, roles=roles, evidence_key=DATABANK_CAMPUS_EVIDENCE, as_of_date="2025-01-23"),
        "project": _entity(stable_key=project, name=f"DataBank {facility} Lithia Springs Facility Build", address=address, roles=roles, evidence_key=facility_evidence, as_of_date="2026-05-14"),
        "lifecycle": [{"entity": "project", "value": "under_construction", "evidence_key": DATABANK_SOCIAL_EVIDENCE, "as_of_date": "2026-05-07", "method": "authoritative_physical_status_update", "confidence": 0.99}],
        "operating_models": [_classification(evidence_key=facility_evidence, as_of_date="2026-05-14")],
        "workloads": [],
        "capacities": [_capacity(entity="project", base=float(megawatts), stage="design", evidence_key=facility_evidence, as_of_date="2026-05-14", notes=f"DataBank-reported {facility} critical-IT design capacity; not current load, energy use, or measured consumption.")],
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    builders = (_riot_retrofit_source, _riot_operational_source, lambda: _databank_source("ATL5", 48), lambda: _databank_source("ATL6", 72))
    return {name: builder() for name, builder in zip(SOURCE_FILENAMES, builders, strict=True)}


def _source_records(documents: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for name in SOURCE_FILENAMES:
        document = documents[name]
        payload = _canonical(document)
        rows.append({
            "path": f"sources/{name}",
            "bytes": len(payload),
            "sha256": _sha256_bytes(payload),
            "schema_version": "1.1",
            "country": "United States",
            "campus_stable_key": document["campus"]["stable_key"],
            "project_stable_key": document["project"]["stable_key"],
            "evidence_records": len(document["evidence"]),
            "lifecycle_observations": 1,
            "operating_model_observations": len(document["operating_models"]),
            "workload_observations": 0,
            "capacity_estimates": len(document["capacities"]),
            "coordinates_present": 0,
            "geometry_present": 0,
            "disposition": "seed_eligible_direct_authoritative_physical_update",
            "seed_eligible": True,
            "seeded": False,
        })
    return rows


def _base_collision_witness(documents: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    definition = json.loads(V86_DEFINITION.read_text(encoding="utf-8"))
    rows = definition.get("curated_inputs", [])
    if len(rows) != V86_INPUT_COUNT:
        raise USOperatorGapError("v86 input count differs")
    planned_stable = {document[entity]["stable_key"] for document in documents.values() for entity in ("campus", "project")}
    planned_evidence = {evidence["key"] for document in documents.values() for evidence in document["evidence"]}
    base_stable: set[str] = set()
    base_evidence: set[str] = set()
    for row in rows:
        path = ROOT / row["path"]
        if _sha256(path) != row["sha256"]:
            raise USOperatorGapError(f"v86 selected source pin differs: {row['path']}")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        for entity in ("campus", "facility", "building", "project"):
            value = document.get(entity)
            if isinstance(value, dict) and isinstance(value.get("stable_key"), str):
                base_stable.add(value["stable_key"])
        base_evidence.update(item["key"] for item in document.get("evidence", []) if isinstance(item, dict) and isinstance(item.get("key"), str))
    if planned_stable & base_stable or planned_evidence & base_evidence:
        raise USOperatorGapError("planned semantic key collides with accepted v86")
    return {
        "v86_selected_input_count": len(rows),
        "planned_distinct_stable_keys": len(planned_stable),
        "planned_distinct_evidence_keys": len(planned_evidence),
        "exact_stable_key_collisions": 0,
        "exact_evidence_key_collisions": 0,
        "potential_cross_source_identity_note": "An older non-curated source may describe Riot Rockdale. No automatic identity merge, coordinate inheritance, or status inheritance is performed.",
    }


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    documents = expected_source_documents()
    withheld = {
        SOURCE_FILENAMES[0]: ["75 MW expansion option", "100 MW right of first refusal", "200 MW potential lease total", "700 MW site interconnection"],
        SOURCE_FILENAMES[1]: ["25 MW whole-initial-lease capacity not allocated to first phase"],
        SOURCE_FILENAMES[2]: ["180 MW adjacent substation", "120 MW campus total not duplicated"],
        SOURCE_FILENAMES[3]: ["180 MW adjacent substation", "120 MW campus total not duplicated"],
    }
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-us-operator-gap-assessment-v1",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "candidate_count": 4,
        "seed_eligible_count": 4,
        "review_only_count": 0,
        "regional_completeness_claimed": False,
        "candidates": [{
            "candidate_id": document["project"]["stable_key"],
            "decision": "seed_eligible_direct_authoritative_physical_update",
            "source_record_created": True,
            "source_path": f"sources/{name}",
            "seed_eligible": True,
            "lifecycle": document["lifecycle"][0],
            "normalized_capacities": document["capacities"],
            "normalized_operating_models": document["operating_models"],
            "withheld_non_normalized_labels": withheld[name],
            "workload_observations": 0,
            "coordinates_created": 0,
            "geometry_created": 0,
        } for name, document in documents.items()],
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "request_credentials_supplied": False,
        "successful_http_200_body_captures": 7,
        "http_error_header_only_captures": 3,
        "raw_capture_redistributed": False,
        "capture_file_count": CAPTURE_FILE_COUNT,
        "capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "controlled_captures": [{
            "capture_id": capture_id,
            "requested_url": capture["url"],
            "effective_url": capture["effective_url"],
            "retrieved_at": capture["retrieved_at"],
            "published_at": capture["published_at"],
            "http_status": capture["http_status"],
            "content_type": capture["content_type"],
            "body": {"path": capture["body"], "bytes": CAPTURE_FILE_PINS[capture["body"]][0], "sha256": CAPTURE_FILE_PINS[capture["body"]][1], "retained_in_artifact": False, "moved_to_trash": True},
            "headers": {"path": capture["headers"], "bytes": CAPTURE_FILE_PINS[capture["headers"]][0], "sha256": CAPTURE_FILE_PINS[capture["headers"]][1], "retained_in_artifact": False, "moved_to_trash": True},
            "request_credentials_supplied": False,
            "used_for_normalized_claims": capture["used"],
        } for capture_id, capture in CAPTURES.items()],
        "header_only_failed_requests": [
            {"path": "lease-headers.txt", "http_status": 403, "normalized_claims_created": 0},
            {"path": "q1-headers.txt", "http_status": 403, "normalized_claims_created": 0},
            {"path": "q1-sec-headers.txt", "http_status": 403, "normalized_claims_created": 0},
        ],
        "complete_private_file_inventory": [{"path": name, "bytes": pin[0], "sha256": pin[1]} for name, pin in sorted(CAPTURE_FILE_PINS.items())],
        "excluded_capture_disposition": {
            "capture_id": "riot_q1",
            "basis": "Retained only as a negative witness. Its additional contracted capacity is not evidence of physical construction, delivery, current load, or operation and creates no normalized claim.",
        },
    }


def _artifact_documents(recorded_at: str, source_documents: Mapping[str, Mapping[str, Any]]) -> dict[str, bytes]:
    collision = _base_collision_witness(source_documents)
    source_records = _source_records(source_documents)
    readme = f"""# US operator-gap official builds

This immutable artifact publishes four direct official-source records: Riot Rockdale's initial 25 MW AMD existing-building retrofit, a capacity-unspecified operational closure for only the first AMD lease phase, and DataBank ATL5 and ATL6 physical builds.

Riot's 75 MW option, 100 MW right of first refusal, 200 MW potential lease total, later 50 MW contracted figure, 700 MW site interconnection, and Corsicana development wording are excluded. The first operational phase inherits no share of the 25 MW initial lease. DataBank contributes 48 MW and 72 MW critical-IT design rows and directly advertised colocation, but no current load, energy use, PUE, WUE, workload, tenant, customer, or coordinate.

All lifecycle observations are dated last-observed facts; current status remains unknown after the evidence date. No satellite image, publisher image, map, or CV result establishes identity, location, status, capacity, type, or site count.

All source and artifact bytes were staged before {recorded_at}; final paths were absent until that instant and promoted without replacement. Raw all-rights-reserved captures are represented only by hashes and retrieval facts. The intact {CAPTURE_FILE_COUNT}-file capture directory was moved to recoverable Trash after publication.
"""
    totals = {
        "candidate_assessments": 4,
        "source_records": 4,
        "seed_eligible_source_records": 4,
        "review_only_candidates": 0,
        "distinct_campuses": 2,
        "projects": 4,
        "distinct_entities": 6,
        "source_document_entity_snapshots": 8,
        "unique_evidence_records": 6,
        "source_document_evidence_references": 9,
        "lifecycle_observations": 4,
        "operating_model_observations": 2,
        "workload_observations": 0,
        "capacity_estimates": 3,
        "coordinates_present": 0,
        "geometry_present": 0,
    }
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "regional_completeness_claimed": False,
        "source_records": source_records,
        "totals": totals,
        "frozen_v86_non_mutation_witness": {
            "definition": {"path": "sources/open-seed-2026-07-21-v86.json", "bytes": V86_PINS[V86_DEFINITION][0], "sha256": V86_PINS[V86_DEFINITION][1]},
            "release_manifest": {"path": "releases/2026-07-21-open-seed-v86/manifest.json", "bytes": V86_PINS[V86_MANIFEST][0], "sha256": V86_PINS[V86_MANIFEST][1]},
            "release_tree_sha256": V86_TREE_SHA256,
            "new_source_paths_selected_by_v86": False,
            **collision,
        },
        "integration": {"open_seed_successor_created": False, "open_seed_v86_mutated": False, "release_integration": "none", "construction_timeline_integration": "none", "federation_integration": "none", "identity_integration": "none", "coverage_ledger_integration": "none"},
        "publication_contract": {"version": 1, "all_source_and_artifact_bytes_staged_before_recorded_at": True, "final_paths_absent_before_recorded_at": True, "publication_waited_until_recorded_at": True, "no_replace_promotion": True, "identity_checked_rollback_on_late_collision": True, "final_root_ctime_not_before_recorded_at": True, "source_file_mode": "0444", "artifact_directory_mode": "0555", "artifact_file_mode": "0444"},
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-disposition-v3",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "source_rights": "Captured publisher response bodies are treated as all-rights-reserved; no redistribution license was relied on.",
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
        "candidate_dispositions": {"seed_eligible": 4, "review_only": 0},
    }
    return {
        "README.md": readme.encode(),
        "candidate-assessment.json": _canonical(_candidate_assessment(recorded_at)),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _file_tree(rows: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_bytes((json.dumps(rows, indent=2, sort_keys=True) + "\n").encode())


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
        "candidate_assessments": 4,
        "curated_source_records": 4,
        "seed_eligible_source_records": 4,
        "review_only_candidates": 0,
        "successful_http_200_body_captures": 7,
        "http_error_header_only_captures": 3,
        "raw_capture_redistributed": False,
        "raw_capture_directory_moved_intact_to_trash": True,
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


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def _validate_sources(paths: Mapping[str, Path]) -> list[dict[str, Any]]:
    expected = expected_source_documents()
    if set(paths) != set(SOURCE_FILENAMES):
        raise USOperatorGapError("source path inventory differs")
    for name in SOURCE_FILENAMES:
        path = paths[name]
        if path.is_symlink() or not path.is_file() or path.read_bytes() != _canonical(expected[name]) or stat.S_IMODE(path.stat().st_mode) != 0o444:
            raise USOperatorGapError(f"curated source differs: {name}")
    documents = list(expected.values())
    if any(document[entity][field] is not None for document in documents for entity in ("campus", "project") for field in ("coordinates", "geometry")):
        raise USOperatorGapError("source invented coordinates or geometry")
    if any(document["workloads"] for document in documents):
        raise USOperatorGapError("source invented workloads")
    lifecycle = [(document["project"]["stable_key"], document["lifecycle"][0]["value"], document["lifecycle"][0]["as_of_date"]) for document in documents]
    if lifecycle != [
        ("curated:riot-rockdale-site:amd-25mw-existing-building-retrofit", "under_construction", "2026-01-16"),
        ("curated:riot-rockdale-site:amd-lease-first-phase", "operational", "2026-01-31"),
        ("curated:databank-lithia-springs-campus:atl5-current-build", "under_construction", "2026-05-07"),
        ("curated:databank-lithia-springs-campus:atl6-current-build", "under_construction", "2026-05-07"),
    ]:
        raise USOperatorGapError("lifecycle contract differs")
    capacities = sorted((document["project"]["stable_key"], row["metric"], row["stage"], row["base"]) for document in documents for row in document["capacities"])
    if capacities != [
        ("curated:databank-lithia-springs-campus:atl5-current-build", "critical_it_mw", "design", 48.0),
        ("curated:databank-lithia-springs-campus:atl6-current-build", "critical_it_mw", "design", 72.0),
        ("curated:riot-rockdale-site:amd-25mw-existing-building-retrofit", "critical_it_mw", "planned", 25.0),
    ]:
        raise USOperatorGapError("capacity contract differs")
    return _source_records(expected)


def _validate_source_collisions() -> None:
    planned = expected_source_documents()
    _base_collision_witness(planned)
    source_names = set(SOURCE_FILENAMES)
    planned_stable = {document[entity]["stable_key"] for document in planned.values() for entity in ("campus", "project")}
    planned_evidence = {evidence["key"] for document in planned.values() for evidence in document["evidence"]}
    collisions = {}
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
            collisions[str(path.relative_to(ROOT))] = {"stable_keys": sorted(planned_stable & stable), "evidence_keys": sorted(planned_evidence & evidence)}
    if collisions:
        raise USOperatorGapError(f"source collision detected: {collisions!r}")


def _validate_frozen_witnesses() -> None:
    for path, pin in V86_PINS.items():
        _pin(path, pin)
    if tree_digest(V86_RELEASE) != V86_TREE_SHA256:
        raise USOperatorGapError("v86 release tree differs")
    _base_collision_witness(expected_source_documents())


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise USOperatorGapError(f"capture directory is absent or unsafe: {directory}")
    entries = list(directory.iterdir())
    if len(entries) != CAPTURE_FILE_COUNT or any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise USOperatorGapError("capture directory closed file set differs")
    if sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES or tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise USOperatorGapError("capture directory aggregate differs")
    if set(CAPTURE_FILE_PINS) != {entry.name for entry in entries}:
        raise USOperatorGapError("capture directory names differ")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(directory / name, pin)


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory(prefix="us-operator-gap-import-", dir="/private/tmp") as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            for name in SOURCE_FILENAMES:
                adapter.import_file(connection, paths[name], recorded_at=recorded_at)
        validate_database(connection)
        tables = ("entities", "entity_snapshots", "evidence", "lifecycle_observations", "operating_model_observations", "workload_observations", "capacity_estimates")
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
        expected = {"entities": 6, "entity_snapshots": 6, "evidence": 6, "lifecycle_observations": 4, "operating_model_observations": 2, "workload_observations": 0, "capacity_estimates": 3}
        if counts != expected:
            raise USOperatorGapError(f"offline import counts differ: {counts!r}")
        operational_capacity = connection.execute("SELECT COUNT(*) FROM capacity_estimates WHERE stage='operational'").fetchone()[0]
        if operational_capacity != 0:
            raise USOperatorGapError("first phase inherited unsupported operational MW")
        return counts


def validate_artifact(path: Path = ARTIFACT, *, source_paths: Mapping[str, Path] | None = None, require_live: bool = True, wall_clock: datetime | None = None) -> dict[str, Any]:
    paths = source_paths or _source_paths(SOURCES_ROOT)
    source_records = _validate_sources(paths)
    if path.is_symlink() or not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise USOperatorGapError("artifact must be a frozen ordinary directory")
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES or any(entry.is_symlink() or not entry.is_file() or stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries.values()):
        raise USOperatorGapError("artifact closed frozen file set differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest) or manifest.get("artifact_id") != ARTIFACT_ID or set(manifest.get("closed_file_set", [])) != CLOSED_FILES or manifest.get("candidate_assessments") != 4 or manifest.get("curated_source_records") != 4 or manifest.get("seed_eligible_source_records") != 4 or manifest.get("review_only_candidates") != 0 or manifest.get("successful_http_200_body_captures") != 7 or manifest.get("http_error_header_only_captures") != 3 or manifest.get("regional_completeness_claimed") is not False or manifest.get("open_seed_successor_created") is not False or manifest.get("release_integration") != "none" or _file_tree(manifest["files"]) != manifest.get("tree_sha256"):
        raise USOperatorGapError("manifest contract differs")
    if [row["path"] for row in manifest["files"]] != list(CONTENT_FILES):
        raise USOperatorGapError("manifest file order differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (row["bytes"], row["sha256"]):
            raise USOperatorGapError(f"manifest file pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != f"{_sha256_bytes(manifest_raw)}  manifest.json\n":
        raise USOperatorGapError("manifest checksum differs")
    expected = _artifact_documents(manifest["recorded_at"], expected_source_documents())
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected[name]:
            raise USOperatorGapError(f"artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records:
        raise USOperatorGapError("artifact source pins differ")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise USOperatorGapError("validation wall clock lacks timezone")
    if require_live and now.astimezone(UTC) < target:
        raise USOperatorGapError("artifact recorded_at is not live")
    if require_live:
        for final in (*paths.values(), path):
            if final.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
                raise USOperatorGapError(f"final ctime predates recorded_at: {final.name}")
    for capture in CAPTURES.values():
        if _instant(capture["retrieved_at"]) > target:
            raise USOperatorGapError("capture retrieval post-dates recorded_at")
    _offline_import(paths, manifest["recorded_at"])
    return manifest


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise USOperatorGapError("active US operator-gap publication lock exists") from error
    os.write(descriptor, f"pid={os.getpid()}\n".encode())
    os.fsync(descriptor)
    metadata = os.fstat(descriptor)
    identity = (metadata.st_dev, metadata.st_ino)
    try:
        yield
    finally:
        os.close(descriptor)
        if PUBLICATION_LOCK.exists():
            current = PUBLICATION_LOCK.stat(follow_symlinks=False)
            if not stat.S_ISREG(current.st_mode) or (current.st_dev, current.st_ino) != identity:
                raise USOperatorGapError("refusing substituted publication-lock cleanup")
            PUBLICATION_LOCK.unlink()


@dataclass(frozen=True)
class _Prepared:
    source_stage: Path
    artifact_stage: Path
    source_identities: Mapping[str, tuple[int, int]]
    artifact_identity: tuple[int, int]
    artifact_members: Mapping[str, tuple[int, int]]
    recorded_at: str


def _identity(path: Path) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    return metadata.st_dev, metadata.st_ino


def _prepare(recorded_at: str) -> _Prepared:
    if any((SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink() for name in SOURCE_FILENAMES) or ARTIFACT.exists() or ARTIFACT.is_symlink():
        raise USOperatorGapError("US operator-gap final path collision")
    _validate_frozen_witnesses()
    _validate_source_collisions()
    capture_directory = resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(capture_directory)
    documents = expected_source_documents()
    source_stage = Path(tempfile.mkdtemp(prefix=".us-operator-gap-sources.", dir=SOURCES_ROOT))
    artifact_stage = Path(tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT))
    try:
        _write_source_stage(source_stage, documents)
        _write_artifact_stage(artifact_stage, recorded_at, documents)
        paths = _source_paths(source_stage)
        _validate_sources(paths)
        validate_artifact(artifact_stage, source_paths=paths, require_live=False, wall_clock=_instant(recorded_at))
        target = _instant(recorded_at).timestamp()
        for path in (*paths.values(), artifact_stage, *artifact_stage.iterdir()):
            metadata = path.stat(follow_symlinks=False)
            if max(metadata.st_birthtime, metadata.st_mtime) > target + 1e-6:
                raise USOperatorGapError(f"stage post-dates recorded_at: {path.name}")
        return _Prepared(source_stage, artifact_stage, {name: _identity(path) for name, path in paths.items()}, _identity(artifact_stage), {path.name: _identity(path) for path in artifact_stage.iterdir()}, recorded_at)
    except Exception:
        if source_stage.exists():
            shutil.rmtree(source_stage)
        if artifact_stage.exists():
            artifact_stage.chmod(0o700)
            shutil.rmtree(artifact_stage)
        raise


def _assert_prepared(prepared: _Prepared) -> None:
    if _identity(prepared.source_stage) == (0, 0) or _identity(prepared.artifact_stage) != prepared.artifact_identity:
        raise USOperatorGapError("private stage identity changed")
    if {path.name: _identity(path) for path in prepared.artifact_stage.iterdir()} != dict(prepared.artifact_members):
        raise USOperatorGapError("artifact-stage member identity changed")
    for name, identity in prepared.source_identities.items():
        if _identity(prepared.source_stage / name) != identity:
            raise USOperatorGapError("source-stage member identity changed")


def _publish(prepared: _Prepared) -> None:
    target = _instant(prepared.recorded_at)
    while datetime.now(UTC) < target:
        time.sleep(min(0.25, (target - datetime.now(UTC)).total_seconds()))
    _assert_prepared(prepared)
    if any((SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink() for name in SOURCE_FILENAMES) or ARTIFACT.exists() or ARTIFACT.is_symlink():
        raise USOperatorGapError("late US operator-gap final path collision")
    promoted: list[tuple[Path, Path]] = []
    try:
        for name in SOURCE_FILENAMES:
            staged = prepared.source_stage / name
            final = SOURCES_ROOT / name
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


def _cleanup(prepared: _Prepared) -> None:
    if prepared.source_stage.exists():
        if any(prepared.source_stage.iterdir()):
            raise USOperatorGapError("source stage not empty after publication")
        prepared.source_stage.rmdir()


def _move_capture_to_trash() -> None:
    if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
        raise USOperatorGapError("both capture origin and Trash destination exist")
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH))


def _rollback_published(prepared: _Prepared) -> None:
    if ARTIFACT.exists():
        if _identity(ARTIFACT) != prepared.artifact_identity:
            raise USOperatorGapError("refusing rollback of substituted artifact")
        _promote_noreplace(ARTIFACT, prepared.artifact_stage)
    for name in reversed(SOURCE_FILENAMES):
        final = SOURCES_ROOT / name
        if final.exists():
            if _identity(final) != prepared.source_identities[name]:
                raise USOperatorGapError(f"refusing rollback of substituted source: {name}")
            _promote_noreplace(final, prepared.source_stage / name)


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    if ARTIFACT.exists() and all((SOURCES_ROOT / name).exists() for name in SOURCE_FILENAMES):
        manifest = validate_artifact()
        return {"artifact": str(ARTIFACT), "artifact_tree_sha256": tree_digest(ARTIFACT), "manifest_sha256": _sha256(ARTIFACT / "manifest.json"), "recorded_at": manifest["recorded_at"], "source_records": len(SOURCE_FILENAMES), "status": "existing-identical"}
    if ARTIFACT.exists() or ARTIFACT.is_symlink() or any((SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink() for name in SOURCE_FILENAMES):
        raise USOperatorGapError("partial US operator-gap final-path collision")
    target = _instant(recorded_at) if recorded_at else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    if datetime.now(UTC) >= target:
        raise USOperatorGapError("recorded_at must be future before staging")
    recorded_at = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    with _publication_lock():
        prepared = _prepare(recorded_at)
        published = False
        try:
            _move_capture_to_trash()
            _publish(prepared)
            published = True
            manifest = validate_artifact()
            _cleanup(prepared)
        except BaseException as error:
            if published:
                try:
                    _rollback_published(prepared)
                    published = False
                except Exception as rollback_error:
                    error.add_note(f"identity-safe rollback failed: {rollback_error}")
            if prepared.source_stage.exists() or prepared.artifact_stage.exists():
                if prepared.source_stage.exists():
                    shutil.rmtree(prepared.source_stage)
                if prepared.artifact_stage.exists():
                    prepared.artifact_stage.chmod(0o700)
                    shutil.rmtree(prepared.artifact_stage)
            raise
    return {"artifact": str(ARTIFACT), "artifact_tree_sha256": tree_digest(ARTIFACT), "capture_trash": str(CAPTURE_TRASH), "capture_recoverable": True, "manifest_sha256": _sha256(ARTIFACT / "manifest.json"), "recorded_at": manifest["recorded_at"], "source_records": len(SOURCE_FILENAMES), "status": "published"}


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
