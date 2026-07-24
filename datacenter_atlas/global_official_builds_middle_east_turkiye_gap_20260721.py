"""Publish the bounded Middle East and Turkiye official current-build gap.

The five curated records carry only direct first-party physical observations.
Ambiguous power labels, design capabilities, and regional programs remain
narrative or review-only. Publication is collision-failing and immutable.
"""

from __future__ import annotations

from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence

from . import global_official_builds_next_tranche_20260721 as publication
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "global-official-builds-middle-east-turkiye-gap-2026-07-21-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".global-official-builds-middle-east-turkiye-gap-20260721.lock"
CAPTURE_ORIGIN = Path("/private/tmp/dc-official-middle-east-turkiye-20260721.0cD4aL")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-official-middle-east-turkiye-20260721.0cD4aL")
CAPTURE_TREE_SHA256 = "fdb7176c75e5cefdef99b1f00681246d32842f4303505d39ce212acee8f19691"
CAPTURE_FILE_COUNT = 26
CAPTURE_TOTAL_BYTES = 3_058_430

V79_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v79.json"
V79_RELEASE = ROOT / "releases/2026-07-21-open-seed-v79"
V79_MANIFEST = V79_RELEASE / "manifest.json"
V79_ENTITIES = V79_RELEASE / "entities.csv"
V79_PINS = {
    V79_DEFINITION: (
        94_039,
        "3a8cfb0d6ed9f858f5be3ac8cfda7502673241ede8f0aa23715714a09a7d462e",
    ),
    V79_MANIFEST: (
        13_885,
        "4eaceee00a0ed0e9073bc6cd19a8f82c97a442f05e773615ee1bb470a95a5c71",
    ),
    V79_ENTITIES: (
        924_382,
        "33ba938178fcc6405f2ca44736cb9b3ba29139ef34a4adbf93e555c2b90ddd2f",
    ),
}
V79_TREE_SHA256 = "f5cfdebad04ccb8347cdf9cd965e88f096dc44699b938ecc111acc28348858a2"
V79_INPUT_COUNT = 421

SOURCE_FILENAMES = (
    "curated-official-2026-07-21-enka-eds-ist01-tuzla-current-build.json",
    "curated-official-2026-07-21-t964-baghdad-phase1-current-build.json",
    "curated-official-2026-07-21-ezditek-ruh01-pnu-phase1-current-build.json",
    "curated-official-2026-07-21-quantum-switch-doha-4-5mw-expansion-current-build.json",
    "curated-official-2026-07-21-xds-desert-dragon-jeddah-current-build.json",
)
CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

OfficialMiddleEastTurkiyeGapError = publication.OfficialTrancheError
_canonical = publication._canonical
_sha256 = publication._sha256
_sha256_bytes = publication._sha256_bytes
_instant = publication._instant
_pin = publication._pin
_fsync_regular = publication._fsync_regular
_fsync_directory = publication._fsync_directory
_identity = publication._identity
_has_identity = publication._has_identity
_promote_noreplace = publication._promote_noreplace
_discard_owned_directory = publication._discard_owned_directory
_assert_stage_precedes_target = publication._assert_stage_precedes_target
_assert_final_ctimes = publication._assert_final_ctimes
_require_finals_absent = publication._require_finals_absent
_wait_until = publication._wait_until
_rollback_promotions = publication._rollback_promotions


CAPTURE_FILE_PINS: dict[str, tuple[int, str]] = {
    "dragon_mou.body": (324_719, "e7d2eb4e61cf311743ad3e4339e2258af57b6f090d9f677f2738d98bfee4a1f0"),
    "dragon_mou.headers": (923, "67e8bef3ffee3a4807b56dda5ef4152bcd17169a921f2ef3fedafeb952e4c050"),
    "enka_equipment_june01.body": (35_349, "aa750140a98c03434e063bea0e4795942581bb112e0e473cba9cdf47fa90cd92"),
    "enka_equipment_june01.headers": (3_870, "a1e7f6780797a7c42c7fb9ea3a454f24953805d55b01b980476a88742b21fee5"),
    "enka_project.body": (206_260, "063f80b041c04c7aa5f7cad003a34e7459add371f7acb5cee5f643cae9590262"),
    "enka_project.headers": (1_139, "5fa6dbe1b23487ce804f84e9f184280ab7168a8a6dc21f565da777b60c4257ab"),
    "enka_status_june12.body": (32_410, "2c1fa6414a4701e883467845c56dd7de7b5721d2fb4becf7ac03722e62b1c2df"),
    "enka_status_june12.headers": (4_426, "6b3b945834c0b6c346fa0459b90afd07911437f3c7165b75da6f1a74bf75c25f"),
    "enka_what_we_do.body": (360_205, "7bc183370fd9f9139ded516fc8895c6f65c3692e03163df6dea38b8695a5b7bf"),
    "enka_what_we_do.headers": (1_010, "b5ea3f693efb575917d562f067371ee4aec9d3598315fc809a90b8cee4e975a6"),
    "ezditek_groundbreak.body": (97_072, "1d064701d614d8e14de399fc21be652d5e677c698fa2f63131fab05c97fce208"),
    "ezditek_groundbreak.headers": (1_227, "1f72bf54568b390685fa5971aefe67a801fca404d702651ba152be723b14e3e4"),
    "ezditek_status.body": (24_003, "48e9d6bd33bc864e2fded0653222b7d0594bd19d86da0404b7d76e70b37a32b4"),
    "ezditek_status.headers": (3_870, "cfafbb101d355e0a91c53d5106b3b70cbd4802d7a0a04ddb861e586083d1e530"),
    "ics_desert_dragon.body": (445_919, "ea70b5cd6171e101a1988112af546e6d9cff8712306fbf9e0bf1d505b5871653"),
    "ics_desert_dragon.headers": (444, "aff5442362486a05b641c89d7ad1b98d4dcdc2b49d4337ec3d2e25da61fe6a81"),
    "quantum_portfolio.body": (1_089_996, "64571fe976438a30afcf36096ab56291ddcca8f966f82095db298cd29a434176"),
    "quantum_portfolio.headers": (1_232, "48be592d5aa57c338aeff79eadce6dd0e17db15cc84b43e69cd266344ac2d681"),
    "quantum_status.body": (23_586, "dbdba1f2eb41b557de6cdb60b7f183d2bee4a01a5a64ce7835a03e1814ff544d"),
    "quantum_status.headers": (3_870, "5200b6c40ea99f5e56057a950dd2c4f03e622c1e6fe220c41992f53b8e7527bc"),
    "t964_facility.body": (168_699, "8ad5e6cadf193cefa8412a08fac4a82c5d25154129dbe521106f8f93dd4b1776"),
    "t964_facility.headers": (2_114, "eb1fc6e26dc0282b216a548d25fb187a02f8d062a0d5353150da290dfdb240fa"),
    "t964_linkedin_pulse.body": (120_283, "034d2b10342a2d32dd2b459e940ae512453e6bc830f4bbb5f840b72a99cedb21"),
    "t964_linkedin_pulse.headers": (5_347, "2125021a68e498215cf1700b11fb40ccd0432c3976cbeb4ee7f240ce809f08bd"),
    "xds_locations.body": (99_826, "a620123bc0e5443c4f6404e7080d6e9d346234927fe0ae35bd638eeb0a278156"),
    "xds_locations.headers": (631, "b791c69b8decc2d9505ceaabdc091f6037b7d2dff52dd1b038beabfc97850e04"),
}


def _capture(filename: str, url: str, *, published_at: str | None = None) -> dict[str, Any]:
    size, digest = CAPTURE_FILE_PINS[f"{filename}.body"]
    return {
        "filename": f"{filename}.body",
        "url": url,
        "published_at": published_at,
        "retrieved_at": "2026-07-21T16:52:10Z",
        "http_status": 200,
        "bytes": size,
        "sha256": digest,
        "content_type": "text/html",
    }


CAPTURES = {
    "enka_status": _capture(
        "enka_status_june12",
        "https://www.linkedin.com/embed/feed/update/urn:li:activity:7471178062345297920",
        published_at="2026-06-12",
    ),
    "enka_equipment": _capture(
        "enka_equipment_june01",
        "https://www.linkedin.com/embed/feed/update/urn:li:activity:7467139092640763906",
        published_at="2026-06-01",
    ),
    "enka_project": _capture(
        "enka_project", "https://www.enka.com/portfolio-item/enka-tuzla-data-center/"
    ),
    "enka_identity": _capture(
        "enka_what_we_do", "https://www.enka.com/what-we-do/"
    ),
    "t964_status": _capture(
        "t964_linkedin_pulse",
        "https://www.linkedin.com/pulse/schneider-electric-announces-strategic-collaboration-t964-deliver-tlmwf",
        published_at="2026-07-09",
    ),
    "t964_facility": _capture(
        "t964_facility", "https://www.t964datacenter.com/facility"
    ),
    "ezditek_status": _capture(
        "ezditek_status",
        "https://www.linkedin.com/embed/feed/update/urn:li:activity:7473316883811930112",
        published_at="2026-06-18",
    ),
    "ezditek_identity": _capture(
        "ezditek_groundbreak",
        "https://ezditek.com/2024/11/ezditek-breaks-ground-on-data-center-facility-in-riyadh-to-provide-a-foundation-for-ai-and-cloud-innovation-in-the-kingdom-of-saudi-arabia/",
        published_at="2024-11-18",
    ),
    "quantum_status": _capture(
        "quantum_status",
        "https://www.linkedin.com/embed/feed/update/urn:li:activity:7420488103414386688",
        published_at="2026-01-23",
    ),
    "quantum_portfolio": _capture(
        "quantum_portfolio", "https://www.quantumswitch.com/data-centres/"
    ),
    "xds_locations": _capture(
        "xds_locations", "https://xdsdatacentres.com/locations/"
    ),
    "ics_project": _capture(
        "ics_desert_dragon", "https://icsarabia.com/projects/desert-dragon-data-centers/"
    ),
    "dragon_mou": _capture(
        "dragon_mou",
        "https://dragon-datacenter.com/2025/07/08/xds-signs-mou-with-desert-dragons/",
        published_at="2025-07-08",
    ),
}


PLANNED_ALIASES = frozenset(
    {
        "ENKA Data Solutions EDS IST 01 Tuzla Data Center",
        "EDS IST 01 TUZLA",
        "ENKA Tuzla Data Center",
        "T964 Commercial Tier III Data Center",
        "T964 Data Center",
        "Ezditek RUH01/PNU",
        "RUH01",
        "Quantum Switch Doha Data Center",
        "Quantum Switch Doha 4.5 MW Expansion",
        "XDS/Desert Dragon Jeddah Immersion Data Center",
        "Desert Dragon Jeddah",
    }
)
PLANNED_URLS = frozenset(capture["url"] for capture in CAPTURES.values())


def _evidence(
    capture_id: str,
    *,
    key: str,
    kind: str,
    title: str,
    publisher: str,
    source_family: str,
    excerpt: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    capture = CAPTURES[capture_id]
    common = {
        "content_hash_scope": (
            f"SHA-256 of the exact {capture['bytes']}-byte content-decoded "
            "credential-free public response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture_id,
        "capture_method": "credential_free_curl_location_compressed",
        "network_timeout_contract": "connect_timeout_10s_wall_clock_timeout_45s",
        "http_status": 200,
        "content_type": "text/html",
        "request_credentials_supplied": False,
        "rights_scope": (
            "Compact factual extraction from all-rights-reserved official bytes; "
            "raw bytes, headers, telemetry, and publisher media are not redistributed."
        ),
        "imagery_guardrail": (
            "No publisher image, satellite image, aerial image, computer vision, or "
            "analyst geolocation contributes to a normalized claim."
        ),
    }
    common.update(metadata)
    return {
        "key": key,
        "kind": kind,
        "title": title,
        "source_url": capture["url"],
        "publisher": publisher,
        "source_family": source_family,
        "published_at": capture["published_at"],
        "retrieved_at": capture["retrieved_at"],
        "license": "all-rights-reserved",
        "attribution": publisher,
        "excerpt": excerpt,
        "content_hash": capture["sha256"],
        "metadata": common,
    }


def _entity(
    *,
    stable_key: str,
    name: str,
    country: str,
    address: str,
    roles: Mapping[str, list[str]],
    evidence_key: str,
    as_of_date: str,
) -> dict[str, Any]:
    return {
        "stable_key": stable_key,
        "name": name,
        "country": country,
        "address": address,
        "roles": dict(roles),
        "coordinates": None,
        "geometry": None,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": "authoritative_locality",
        "confidence": 0.99,
    }


def _lifecycle(evidence_key: str, as_of_date: str) -> dict[str, Any]:
    return {
        "entity": "project",
        "value": "under_construction",
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": "authoritative_physical_status_update",
        "confidence": 0.99,
    }


def _enka_source() -> dict[str, Any]:
    status_key = "enka-eds-ist01-tuzla-physical-progress-captured-2026-07-21"
    equipment_key = "enka-eds-ist01-tuzla-equipment-onsite-captured-2026-07-21"
    design_key = "enka-tuzla-project-it-load-schedule-captured-2026-07-21"
    identity_key = "enka-eds-ist01-tuzla-identity-captured-2026-07-21"
    evidence = [
        _evidence(
            "enka_status",
            key=status_key,
            kind="company_disclosure",
            title="EDS IST 01 Tuzla physical-construction update",
            publisher="ENKA Data Solutions",
            source_family="enka_data_solutions_official_updates",
            excerpt="ENKA reports critical civil, mechanical, and electrical installation phases progressing at the Tuzla site.",
            metadata={
                "linkedin_activity_id": "7471178062345297920",
                "physical_status_scope": "Direct current site work supports generic under_construction only.",
            },
        ),
        _evidence(
            "enka_equipment",
            key=equipment_key,
            kind="company_disclosure",
            title="EDS IST 01 Tuzla equipment-arrival update",
            publisher="ENKA Data Solutions",
            source_family="enka_data_solutions_official_updates",
            excerpt="ENKA reports generators, UPS systems, transformers, panels, and cooling equipment arriving at the Tuzla site.",
            metadata={
                "linkedin_activity_id": "7467139092640763906",
                "capability_guardrail": "High-density, GPU, and AI design language creates no active workload row.",
            },
        ),
        _evidence(
            "enka_project",
            key=design_key,
            kind="company_disclosure",
            title="ENKA Tuzla Data Center project page",
            publisher="ENKA İnşaat ve Sanayi A.Ş.",
            source_family="enka_project_portfolio",
            excerpt="The project page states an 11 MW IT load, six data halls, and a May 2025 to May 2027 schedule.",
            metadata={
                "it_load_mw_as_reported": 11,
                "data_halls_as_reported": 6,
                "schedule_as_reported": "May 2025-May 2027",
                "capacity_scope": "Exactly one design-stage critical_it_mw row; not current load, gross demand, energy, generation, or PUE.",
            },
        ),
        _evidence(
            "enka_identity",
            key=identity_key,
            kind="company_disclosure",
            title="ENKA EDS IST 01 TUZLA identity listing",
            publisher="ENKA İnşaat ve Sanayi A.Ş.",
            source_family="enka_corporate_asset_listings",
            excerpt="ENKA's corporate page identifies the data-center asset as EDS IST 01 TUZLA.",
            metadata={"identity_alias_as_reported": "EDS IST 01 TUZLA"},
        ),
    ]
    campus_key = "curated:enka-data-solutions-eds-ist-01-tuzla-data-center"
    project_key = f"{campus_key}:initial-build"
    roles = {"developer": ["ENKA Data Solutions"], "contractor": ["ENKA İnşaat ve Sanayi A.Ş."]}
    address = "Tuzla, İstanbul, Türkiye"
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(stable_key=campus_key, name="ENKA Data Solutions EDS IST 01 Tuzla Data Center", country="Türkiye", address=address, roles=roles, evidence_key=identity_key, as_of_date="2026-06-12"),
        "project": _entity(stable_key=project_key, name="EDS IST 01 Tuzla Initial Build", country="Türkiye", address=address, roles=roles, evidence_key=status_key, as_of_date="2026-06-12"),
        "lifecycle": [_lifecycle(status_key, "2026-06-12")],
        "operating_models": [],
        "workloads": [],
        "capacities": [
            {
                "entity": "project",
                "metric": "critical_it_mw",
                "stage": "design",
                "unit": "MW",
                "low": 11,
                "base": 11,
                "high": 11,
                "method": "reported",
                "confidence": 0.99,
                "evidence_key": design_key,
                "as_of_date": "2026-06-12",
                "target_date": None,
                "notes": "Project-page IT-load design value only; not current load, gross demand, generation, annual energy, consumption, or PUE.",
            }
        ],
    }


def _t964_source() -> dict[str, Any]:
    status_key = "t964-baghdad-phase1-current-build-captured-2026-07-21"
    facility_key = "t964-baghdad-facility-power-labels-captured-2026-07-21"
    evidence = [
        _evidence(
            "t964_status",
            key=status_key,
            kind="company_disclosure",
            title="Schneider Electric and T964 Baghdad delivery update",
            publisher="Schneider Electric",
            source_family="schneider_electric_official_articles",
            excerpt="The article reports construction and infrastructure work underway for a planned end-2026 launch and 340 phase-one racks.",
            metadata={
                "phase_one_racks_as_reported": 340,
                "planned_launch_as_reported": "end of 2026",
                "scalable_capacity_label_as_reported": "up to 12 MW",
                "supporting_power_label_as_reported": "84 MW of on-site power",
                "capacity_guardrail": "Neither 12 MW nor 84 MW has a normalized facility boundary; both remain narrative.",
            },
        ),
        _evidence(
            "t964_facility",
            key=facility_key,
            kind="company_disclosure",
            title="T964 Baghdad facility page",
            publisher="T964 Data Center",
            source_family="t964_current_facility_pages",
            excerpt="T964 presents a Baghdad commercial carrier-neutral Tier III facility and multiple inconsistent 3 MW power labels.",
            metadata={
                "power_label_as_reported": "3MW Power Capacity",
                "conflicting_metric_label_as_reported": "3MW IT Load Capacity",
                "capacity_guardrail": "The current page is internally inconsistent, so no 3 MW capacity is normalized.",
                "workload_guardrail": "AI-ready and cloud capability create no active workload observation.",
            },
        ),
    ]
    campus_key = "curated:t964-baghdad-commercial-tier-iii-data-center"
    project_key = f"{campus_key}:phase-1-current-build"
    roles = {"operator": ["T964 Data Center"]}
    address = "Baghdad, Iraq"
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(stable_key=campus_key, name="T964 Commercial Tier III Data Center", country="Iraq", address=address, roles=roles, evidence_key=facility_key, as_of_date="2026-07-09"),
        "project": _entity(stable_key=project_key, name="T964 Baghdad Phase 1 Current Build", country="Iraq", address=address, roles=roles, evidence_key=status_key, as_of_date="2026-07-09"),
        "lifecycle": [_lifecycle(status_key, "2026-07-09")],
        "operating_models": [
            {
                "entity": "campus",
                "value": "colocation",
                "evidence_key": facility_key,
                "as_of_date": "2026-07-09",
                "method": "company_disclosure",
                "confidence": 0.99,
            }
        ],
        "workloads": [],
        "capacities": [],
    }


def _ezditek_source() -> dict[str, Any]:
    status_key = "ezditek-ruh01-pnu-physical-fitout-captured-2026-07-21"
    identity_key = "ezditek-ruh01-pnu-identity-captured-2026-07-21"
    evidence = [
        _evidence(
            "ezditek_status",
            key=status_key,
            kind="company_disclosure",
            title="Ezditek RUH01 physical-fitout update",
            publisher="Ezditek",
            source_family="ezditek_official_updates",
            excerpt="Ezditek reports installed cooling, data halls taking shape, and phase one nearing ready-for-service.",
            metadata={
                "linkedin_activity_id": "7473316883811930112",
                "capacity_label_as_reported": "Phase 1 of 24MW AI-ready capacity",
                "capacity_guardrail": "The 24 MW boundary is untyped and creates no normalized capacity.",
                "workload_guardrail": "AI-ready is a capability, not an observed active workload.",
            },
        ),
        _evidence(
            "ezditek_identity",
            key=identity_key,
            kind="company_disclosure",
            title="Ezditek RUH01 PNU groundbreaking announcement",
            publisher="Ezditek",
            source_family="ezditek_company_news",
            excerpt="Ezditek identifies RUH01 at Princess Nourah bint Abdulrahman University in Riyadh.",
            metadata={
                "identity_alias_as_reported": "RUH01",
                "location_as_reported": "Princess Nourah bint Abdulrahman University (PNU), Riyadh",
                "location_guardrail": "Campus-level locality only; no coordinate is created.",
            },
        ),
    ]
    campus_key = "curated:ezditek-ruh01-pnu-riyadh-data-center"
    project_key = f"{campus_key}:phase-1-current-build"
    roles = {"developer": ["Ezditek"], "operator": ["Ezditek"]}
    address = "Princess Nourah bint Abdulrahman University, Riyadh, Saudi Arabia"
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(stable_key=campus_key, name="Ezditek RUH01/PNU Riyadh Data Center", country="Saudi Arabia", address=address, roles=roles, evidence_key=identity_key, as_of_date="2026-06-18"),
        "project": _entity(stable_key=project_key, name="Ezditek RUH01 Phase 1 Current Build", country="Saudi Arabia", address=address, roles=roles, evidence_key=status_key, as_of_date="2026-06-18"),
        "lifecycle": [_lifecycle(status_key, "2026-06-18")],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _quantum_source() -> dict[str, Any]:
    status_key = "quantum-switch-doha-expansion-progress-captured-2026-07-21"
    portfolio_key = "quantum-switch-doha-portfolio-captured-2026-07-21"
    evidence = [
        _evidence(
            "quantum_status",
            key=status_key,
            kind="company_disclosure",
            title="Quantum Switch Doha expansion update",
            publisher="Quantum Switch",
            source_family="quantum_switch_official_updates",
            excerpt="Quantum Switch reports Doha expansion work well underway and the structure rapidly taking shape.",
            metadata={
                "linkedin_activity_id": "7420488103414386688",
                "capacity_label_as_reported": "additional 4.5 MW",
                "capacity_guardrail": "The 4.5 MW boundary is untyped and creates no normalized capacity.",
            },
        ),
        _evidence(
            "quantum_portfolio",
            key=portfolio_key,
            kind="company_disclosure",
            title="Quantum Switch Doha data-centre portfolio",
            publisher="Quantum Switch",
            source_family="quantum_switch_current_portfolio",
            excerpt="The portfolio lists DOA-A and DOA-B, but does not resolve which facility receives the current expansion.",
            metadata={
                "portfolio_labels_as_reported": ["DOA-A 6MW", "DOA-B 4MW"],
                "identity_guardrail": "No DOA-A or DOA-B linkage is asserted for the 4.5 MW expansion.",
            },
        ),
    ]
    campus_key = "curated:quantum-switch-doha-data-center"
    project_key = f"{campus_key}:4-5mw-expansion"
    roles = {"operator": ["Quantum Switch"]}
    address = "Doha, Qatar"
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(stable_key=campus_key, name="Quantum Switch Doha Data Center", country="Qatar", address=address, roles=roles, evidence_key=status_key, as_of_date="2026-01-23"),
        "project": _entity(stable_key=project_key, name="Quantum Switch Doha 4.5 MW Expansion", country="Qatar", address=address, roles=roles, evidence_key=status_key, as_of_date="2026-01-23"),
        "lifecycle": [_lifecycle(status_key, "2026-01-23")],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _xds_source() -> dict[str, Any]:
    status_key = "xds-jeddah-current-construction-page-captured-2026-07-21"
    contractor_key = "ics-desert-dragon-jeddah-phase1-captured-2026-07-21"
    agreement_key = "xds-desert-dragon-kingdom-10mw-agreement-captured-2026-07-21"
    evidence = [
        _evidence(
            "xds_locations",
            key=status_key,
            kind="company_disclosure",
            title="XDS Saudi Arabia current locations page",
            publisher="XDS Data Centres",
            source_family="xds_current_location_pages",
            excerpt="The current page says ICS Arabia is constructing and handing over Jeddah with a November 2026 delivery target.",
            metadata={
                "status_date_basis": "retrieval_date_of_current_operator_page",
                "delivery_target_as_reported": "Jeddah November 2026",
                "capacity_label_as_reported": "two 10MW immersion-cooled data centers",
                "capacity_guardrail": "Current per-facility wording conflicts with the earlier 10 MW Kingdom-total agreement; no capacity is normalized.",
                "workload_guardrail": "AI/GPU purpose-built language is intended capability, not active workload.",
            },
        ),
        _evidence(
            "ics_project",
            key=contractor_key,
            kind="company_disclosure",
            title="ICS Arabia Desert Dragon project page",
            publisher="ICS Arabia",
            source_family="ics_arabia_project_portfolio",
            excerpt="ICS Arabia identifies the Jeddah Desert Dragon facility and a December 2026 phase-one target.",
            metadata={
                "phase_one_target_as_reported": "Jeddah December 2026",
                "cooling_design_as_reported": "dielectric-fluid immersion cooling",
                "status_scope": "Contractor identity and schedule corroboration; no exact coordinate or completion assertion.",
            },
        ),
        _evidence(
            "dragon_mou",
            key=agreement_key,
            kind="company_disclosure",
            title="XDS and Desert Dragon strategic agreement",
            publisher="Desert Dragon Data Center",
            source_family="desert_dragon_company_news",
            excerpt="The older agreement describes 10 MW across Saudi Arabia without a per-facility allocation.",
            metadata={
                "capacity_label_as_reported": "10MW of AI workloads in Saudi Arabia",
                "capacity_guardrail": "The 2025 total conflicts with current two-facility wording and creates no normalized row.",
                "lifecycle_guardrail": "The agreement itself creates no construction observation.",
            },
        ),
    ]
    campus_key = "curated:xds-desert-dragon-jeddah-immersion-data-center"
    project_key = f"{campus_key}:initial-build"
    roles = {"operator": ["XDS Data Centres"], "developer": ["Desert Dragon Data Center"], "contractor": ["ICS Arabia"]}
    address = "Jeddah, Saudi Arabia"
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(stable_key=campus_key, name="XDS/Desert Dragon Jeddah Immersion Data Center", country="Saudi Arabia", address=address, roles=roles, evidence_key=contractor_key, as_of_date="2026-07-21"),
        "project": _entity(stable_key=project_key, name="XDS/Desert Dragon Jeddah Initial Build", country="Saudi Arabia", address=address, roles=roles, evidence_key=status_key, as_of_date="2026-07-21"),
        "lifecycle": [_lifecycle(status_key, "2026-07-21")],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    """Return the exact five schema-1.1 source documents in requested order."""

    builders = (_enka_source, _t964_source, _ezditek_source, _quantum_source, _xds_source)
    return {name: builder() for name, builder in zip(SOURCE_FILENAMES, builders, strict=True)}


def _source_records(documents: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for name in SOURCE_FILENAMES:
        document = documents[name]
        payload = _canonical(document)
        records.append(
            {
                "path": f"sources/{name}",
                "bytes": len(payload),
                "sha256": _sha256_bytes(payload),
                "schema_version": "1.1",
                "country": document["project"]["country"],
                "campus_stable_key": document["campus"]["stable_key"],
                "project_stable_key": document["project"]["stable_key"],
                "evidence_records": len(document["evidence"]),
                "lifecycle_observations": len(document["lifecycle"]),
                "operating_model_observations": len(document["operating_models"]),
                "workload_observations": len(document["workloads"]),
                "capacity_estimates": len(document["capacities"]),
                "coordinates_present": 0,
                "geometry_present": 0,
                "disposition": "seed_eligible_official_current_physical_update",
                "seed_eligible": True,
                "seeded": False,
            }
        )
    return records


def _review_candidates() -> list[dict[str, Any]]:
    rows = [
        ("xds-riyadh-immersion-facility", "Saudi Arabia", "review_only_delivery_target_passed_without_later_site_update", "June 2026 delivery target passed without a later site-specific physical update."),
        ("aws-saudi-region", "Saudi Arabia", "review_only_regional_program", "A region and availability-zone program does not identify a current physical data-center project."),
        ("humain-saudi-program", "Saudi Arabia", "review_only_mou_and_program", "Partnership and capacity-program announcements do not prove site-specific physical work."),
        ("equinix-saudi-program", "Saudi Arabia", "review_only_plan", "A market-entry or development plan is not a current physical-build observation."),
        ("uae-stargate", "United Arab Emirates", "already_represented_in_v79", "Existing v79 source coverage is retained; no duplicate record is created."),
        ("uae-khazna-current-builds", "United Arab Emirates", "already_represented_in_v79", "Existing v79 Khazna source coverage is retained; no duplicate record is created."),
        ("equinix-dx3-dubai", "United Arab Emirates", "already_represented_in_v79", "Existing v79 DX3 phase coverage is retained; no duplicate record is created."),
        ("moro-hub-warsan", "United Arab Emirates", "already_represented_in_v79", "Existing v79 Moro Hub source coverage is retained; no duplicate record is created."),
        ("q-data-ooredoo-7-5mw-aggregate", "Qatar", "review_only_unallocable_aggregate", "The 7.5 MW aggregate cannot be allocated to a named current-build project."),
        ("meeza-m-vault-7", "Qatar", "review_only_design_future_start", "Design and future-start language does not establish current physical construction."),
        ("meeza-m-vault-8", "Qatar", "review_only_complete", "Reported completion removes the project from the current-build tranche."),
        ("google-kuwait", "Kuwait", "review_only_land_or_lease", "Land or lease control does not establish physical data-center construction."),
        ("jordan-hashem-data-center", "Jordan", "review_only_design", "Design-stage evidence does not establish physical construction."),
        ("jordan-ain-al-basha-data-center", "Jordan", "review_only_operational", "The facility is operational rather than a current build."),
        ("lebanon-dekwaneh-warehouse-rehabilitation", "Lebanon", "review_only_identity_unresolved", "Warehouse rehabilitation is not direct evidence of data-center construction."),
        ("turkcell-three-ankara-facilities", "Türkiye", "review_only_unnamed_facilities", "Three-facility aggregate language cannot resolve named physical projects."),
        ("turkcell-nevsehir", "Türkiye", "review_only_not_started", "The candidate had not started physical construction at the research cutoff."),
    ]
    return [
        {
            "candidate_id": candidate_id,
            "country": country,
            "decision": decision,
            "source_record_created": False,
            "seed_eligible": False,
            "normalized_claims_created": 0,
            "basis": basis,
        }
        for candidate_id, country, decision, basis in rows
    ]


def _candidate_assessments(recorded_at: str) -> dict[str, Any]:
    seed_rows = []
    for name, document in expected_source_documents().items():
        seed_rows.append(
            {
                "candidate_id": document["project"]["stable_key"],
                "country": document["project"]["country"],
                "decision": "seed_eligible_first_party_current_physical_update",
                "source_record_created": True,
                "source_path": f"sources/{name}",
                "seed_eligible": True,
                "lifecycle_observations": 1,
                "capacity_estimates": len(document["capacities"]),
                "operating_model_observations": len(document["operating_models"]),
                "workload_observations": 0,
                "coordinates_created": 0,
            }
        )
    review_rows = _review_candidates()
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-middle-east-turkiye-official-gap-assessment-v1",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "candidate_count": len(seed_rows) + len(review_rows),
        "seed_eligible_count": len(seed_rows),
        "review_only_count": len(review_rows),
        "regional_completeness_claimed": False,
        "candidates": [*seed_rows, *review_rows],
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "capture_protocol": "Credential-free curl GETs with explicit 10-second connect and 45-second wall-clock timeouts.",
        "successful_http_200_body_captures": len(CAPTURES),
        "failed_or_partial_captures": 0,
        "failed_or_partial_capture_claims": 0,
        "request_credentials_supplied": False,
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
                "capture_id": capture_id,
                "requested_url": capture["url"],
                "effective_url": capture["url"],
                "retrieved_at": capture["retrieved_at"],
                "http_status": 200,
                "content_type": "text/html",
                "body": {"bytes": capture["bytes"], "sha256": capture["sha256"], "retained_in_artifact": False, "moved_to_trash": True},
                "capture_method": "credential_free_curl_location_compressed",
                "network_timeout_contract": "connect_timeout_10s_wall_clock_timeout_45s",
                "request_credentials_supplied": False,
                "used_for_normalized_claims": True,
            }
            for capture_id, capture in sorted(CAPTURES.items())
        ],
        "complete_private_file_inventory": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in sorted(CAPTURE_FILE_PINS.items())
        ],
        "technical_incidents": [],
    }


def _artifact_documents(recorded_at: str, source_documents: Mapping[str, Mapping[str, Any]]) -> dict[str, bytes]:
    source_records = _source_records(source_documents)
    assessment_count = 5 + len(_review_candidates())
    readme = f"""# Middle East and Türkiye official current-build gap assessment

This immutable artifact records {assessment_count} bounded candidate dispositions researched on 2026-07-21: five seed-eligible current physical builds and {len(_review_candidates())} review-only or already-covered candidates. It makes no regional-completeness claim.

The five seed records are ENKA EDS IST 01 Tuzla, T964 Baghdad phase one, Ezditek RUH01/PNU, the unresolved-facility Quantum Switch Doha expansion, and XDS/Desert Dragon Jeddah. Lifecycle rows are dated observations, never timeless current-status claims.

Only ENKA's explicitly labeled 11 MW IT load becomes a capacity row, at design stage. T964's 12 MW, 84 MW, and conflicting 3 MW labels; Ezditek's untyped 24 MW; Quantum Switch's untyped 4.5 MW; and the conflicting XDS/Desert Dragon 10 MW scopes remain narrative. No figure becomes current draw, gross demand, generation, annual energy, consumption, or PUE.

T964's directly advertised carrier-neutral commercial colocation model creates one operating-model row. AI-ready, cloud, GPU, high-density, and immersion-cooling language describes capability or design, not observed active workload. No workload row is created.

Quantum Switch remains anchored to a generic Doha campus because the current expansion cannot be attributed to DOA-A or DOA-B. XDS Riyadh is review-only because its June 2026 target passed without a later site-specific update. Regional programs, MOUs, land/lease control, design-only projects, completed or operational sites, unresolved aggregates, and candidates already represented in accepted v79 create no duplicate source record.

All five planned names, retained identity aliases, source URLs, stable keys, and evidence keys were checked for exact normalized absence from accepted v79. Accepted v79 and downstream products remain unchanged. Raw all-rights-reserved captures are not redistributed; the complete {CAPTURE_FILE_COUNT}-file capture directory was moved intact to the recoverable Trash path in the rights inventory.

All source and artifact bytes were complete in private staging before `{recorded_at}`. Final paths remained absent until the declared instant and were promoted without replacement with identity-checked rollback. Source and artifact files are frozen mode 0444; the artifact directory is mode 0555.
"""
    duplicate_witness = _v79_duplicate_witness(source_documents)
    totals = {
        "candidate_assessments": assessment_count,
        "source_records": 5,
        "seed_eligible_source_records": 5,
        "review_only_candidates": len(_review_candidates()),
        "distinct_campuses": 5,
        "projects": 5,
        "entity_snapshots": 10,
        "unique_evidence_records": 13,
        "lifecycle_observations": 5,
        "operating_model_observations": 1,
        "workload_observations": 0,
        "capacity_estimates": 1,
        "coordinates_present": 0,
        "geometry_present": 0,
        "placement_observations": 0,
    }
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "regional_completeness_claimed": False,
        "source_records": source_records,
        "totals": totals,
        "frozen_v79_non_mutation_witness": {
            "definition": {"path": "sources/open-seed-2026-07-21-v79.json", "bytes": V79_PINS[V79_DEFINITION][0], "sha256": V79_PINS[V79_DEFINITION][1]},
            "release_manifest": {"path": "releases/2026-07-21-open-seed-v79/manifest.json", "bytes": V79_PINS[V79_MANIFEST][0], "sha256": V79_PINS[V79_MANIFEST][1]},
            "release_tree_sha256": V79_TREE_SHA256,
            "v79_selected_input_count": V79_INPUT_COUNT,
            "new_source_paths_selected_by_v79": False,
            **duplicate_witness,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v79_mutated": False,
            "release_integration": "none",
            "construction_timeline_integration": "none",
            "federation_integration": "none",
            "identity_integration": "none",
            "coverage_ledger_integration": "none",
            "downstream_product_integration": "none",
        },
        "publication_contract": {
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
        },
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
        "candidate_dispositions": {"seed_eligible": 5, "review_only_or_already_covered": len(_review_candidates())},
    }
    return {
        "README.md": readme.encode(),
        "candidate-assessment.json": _canonical(_candidate_assessments(recorded_at)),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _file_tree(rows: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_bytes((json.dumps(rows, indent=2, sort_keys=True) + "\n").encode())


def _write_source_stage(stage: Path, documents: Mapping[str, Mapping[str, Any]]) -> None:
    for name in SOURCE_FILENAMES:
        output = stage / name
        output.write_bytes(_canonical(documents[name]))
        output.chmod(0o444)
        _fsync_regular(output)
    _fsync_directory(stage)


def _write_artifact_stage(stage: Path, recorded_at: str, documents: Mapping[str, Mapping[str, Any]]) -> None:
    payloads = _artifact_documents(recorded_at, documents)
    for name in CONTENT_FILES:
        output = stage / name
        output.write_bytes(payloads[name])
        output.chmod(0o444)
        _fsync_regular(output)
    rows = [{"bytes": (stage / name).stat().st_size, "path": name, "sha256": _sha256(stage / name)} for name in CONTENT_FILES]
    manifest = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-artifact-manifest-v3",
        "recorded_at": recorded_at,
        "files": rows,
        "tree_sha256": _file_tree(rows),
        "closed_file_set": sorted(CLOSED_FILES),
        "candidate_assessments": 5 + len(_review_candidates()),
        "curated_source_records": 5,
        "seed_eligible_source_records": 5,
        "review_only_candidates": len(_review_candidates()),
        "successful_http_200_body_captures": len(CAPTURES),
        "raw_capture_redistributed": False,
        "raw_capture_directory_moved_intact_to_trash": True,
        "regional_completeness_claimed": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
        "downstream_product_integration": "none",
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
        raise OfficialMiddleEastTurkiyeGapError("source path inventory differs")
    for name in SOURCE_FILENAMES:
        source = paths[name]
        if source.is_symlink() or not source.is_file():
            raise OfficialMiddleEastTurkiyeGapError(f"curated source is absent: {source}")
        if source.read_bytes() != _canonical(expected[name]):
            raise OfficialMiddleEastTurkiyeGapError(f"curated source differs: {name}")
        if stat.S_IMODE(source.stat().st_mode) != 0o444:
            raise OfficialMiddleEastTurkiyeGapError(f"curated source mode differs: {name}")
    documents = list(expected.values())
    if any(document[entity]["coordinates"] is not None or document[entity]["geometry"] is not None for document in documents for entity in ("campus", "project")):
        raise OfficialMiddleEastTurkiyeGapError("source invented coordinates or geometry")
    if sum(len(document["capacities"]) for document in documents) != 1:
        raise OfficialMiddleEastTurkiyeGapError("capacity boundary differs")
    if documents[0]["capacities"][0]["metric"] != "critical_it_mw" or documents[0]["capacities"][0]["base"] != 11:
        raise OfficialMiddleEastTurkiyeGapError("ENKA capacity differs")
    if any(document["workloads"] for document in documents):
        raise OfficialMiddleEastTurkiyeGapError("capability became workload")
    if sum(len(document["operating_models"]) for document in documents) != 1:
        raise OfficialMiddleEastTurkiyeGapError("operating-model boundary differs")
    return _source_records(expected)


def _validate_source_collisions() -> None:
    planned = expected_source_documents()
    stable_keys = {document[entity]["stable_key"] for document in planned.values() for entity in ("campus", "project")}
    evidence_keys = {evidence["key"] for document in planned.values() for evidence in document["evidence"]}
    if len(stable_keys) != 10 or len(evidence_keys) != 13:
        raise OfficialMiddleEastTurkiyeGapError("planned source keys are not unique")
    collisions: dict[str, dict[str, list[str]]] = {}
    for source in SOURCES_ROOT.glob("*.json"):
        if source.name in SOURCE_FILENAMES:
            continue
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        other_stable = {record.get("stable_key") for key in ("campus", "project") if isinstance((record := document.get(key)), dict)}
        other_evidence = {row.get("key") for row in document.get("evidence", []) if isinstance(row, dict)}
        stable_overlap = sorted(stable_keys & other_stable)
        evidence_overlap = sorted(evidence_keys & other_evidence)
        if stable_overlap or evidence_overlap:
            collisions[source.name] = {"stable_keys": stable_overlap, "evidence_keys": evidence_overlap}
    if collisions:
        raise OfficialMiddleEastTurkiyeGapError(f"curated source collision: {collisions!r}")


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split()).rstrip("/")


def _selected_v79_documents() -> list[Mapping[str, Any]]:
    definition = json.loads(V79_DEFINITION.read_text(encoding="utf-8"))
    documents: list[Mapping[str, Any]] = []
    for row in definition["curated_inputs"]:
        source = ROOT / row["path"]
        document = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(document, dict):
            documents.append(document)
    return documents


def _nested_strings(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, Mapping):
        return {
            text
            for nested in value.values()
            for text in _nested_strings(nested)
        }
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return {text for nested in value for text in _nested_strings(nested)}
    return set()


def _strings_for_key(value: Any, token: str) -> set[str]:
    if isinstance(value, Mapping):
        found: set[str] = set()
        for key, nested in value.items():
            if token in str(key).casefold():
                found.update(_nested_strings(nested))
            found.update(_strings_for_key(nested, token))
        return found
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return {
            text
            for nested in value
            for text in _strings_for_key(nested, token)
        }
    return set()


def _v79_duplicate_witness(planned: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    documents = list((planned or expected_source_documents()).values())
    planned_stable = {document[entity]["stable_key"] for document in documents for entity in ("campus", "project")}
    planned_evidence = {row["key"] for document in documents for row in document["evidence"]}
    existing_stable: set[str] = set()
    existing_evidence: set[str] = set()
    existing_names: set[str] = set()
    existing_urls: set[str] = set()
    for document in _selected_v79_documents():
        existing_names.update(
            _normalize_text(text) for text in _strings_for_key(document, "alias")
        )
        existing_urls.update(
            _normalize_text(text) for text in _strings_for_key(document, "url")
        )
        for entity in ("campus", "project"):
            record = document.get(entity)
            if isinstance(record, dict):
                if isinstance(record.get("stable_key"), str):
                    existing_stable.add(record["stable_key"])
                if isinstance(record.get("name"), str):
                    existing_names.add(_normalize_text(record["name"]))
        for row in document.get("evidence", []):
            if not isinstance(row, dict):
                continue
            if isinstance(row.get("key"), str):
                existing_evidence.add(row["key"])
            if isinstance(row.get("source_url"), str):
                existing_urls.add(_normalize_text(row["source_url"]))
    with V79_ENTITIES.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("name"):
                existing_names.add(_normalize_text(row["name"]))
            if row.get("source_url"):
                existing_urls.add(_normalize_text(row["source_url"]))
    alias_overlap = sorted(alias for alias in PLANNED_ALIASES if _normalize_text(alias) in existing_names)
    url_overlap = sorted(url for url in PLANNED_URLS if _normalize_text(url) in existing_urls)
    stable_overlap = sorted(planned_stable & existing_stable)
    evidence_overlap = sorted(planned_evidence & existing_evidence)
    if alias_overlap or url_overlap or stable_overlap or evidence_overlap:
        raise OfficialMiddleEastTurkiyeGapError(
            f"planned candidate duplicates accepted v79: aliases={alias_overlap!r}, urls={url_overlap!r}, stable={stable_overlap!r}, evidence={evidence_overlap!r}"
        )
    return {
        "planned_identity_aliases_checked": len(PLANNED_ALIASES),
        "planned_source_urls_checked": len(PLANNED_URLS),
        "planned_stable_keys_checked": len(planned_stable),
        "planned_evidence_keys_checked": len(planned_evidence),
        "v79_name_or_alias_exact_normalized_collisions": 0,
        "v79_source_url_exact_normalized_collisions": 0,
        "v79_stable_key_collisions": 0,
        "v79_evidence_key_collisions": 0,
    }


def _validate_v79_nonmutation() -> None:
    for source, pin in V79_PINS.items():
        _pin(source, pin)
    if tree_digest(V79_RELEASE) != V79_TREE_SHA256:
        raise OfficialMiddleEastTurkiyeGapError("accepted v79 release tree differs")
    definition = json.loads(V79_DEFINITION.read_text(encoding="utf-8"))
    if len(definition.get("curated_inputs", [])) != V79_INPUT_COUNT:
        raise OfficialMiddleEastTurkiyeGapError("accepted v79 input count differs")
    selected = {row["path"] for row in definition["curated_inputs"]}
    planned_paths = {f"sources/{name}" for name in SOURCE_FILENAMES}
    if selected & planned_paths:
        raise OfficialMiddleEastTurkiyeGapError("v79 unexpectedly selects a new source path")
    _v79_duplicate_witness()


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise OfficialMiddleEastTurkiyeGapError(f"capture directory is absent or unsafe: {directory}")
    entries = list(directory.iterdir())
    if len(entries) != CAPTURE_FILE_COUNT:
        raise OfficialMiddleEastTurkiyeGapError("capture directory file count differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise OfficialMiddleEastTurkiyeGapError("capture directory contains a non-file")
    if sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES:
        raise OfficialMiddleEastTurkiyeGapError("capture directory total bytes differs")
    if tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise OfficialMiddleEastTurkiyeGapError("capture directory tree differs")
    if set(CAPTURE_FILE_PINS) != {entry.name for entry in entries}:
        raise OfficialMiddleEastTurkiyeGapError("capture directory closed set differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(directory / name, pin)


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory() as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for name in SOURCE_FILENAMES:
            adapter.import_file(connection, paths[name], recorded_at=recorded_at)
        validate_database(connection)
        tables = ("entities", "entity_snapshots", "evidence", "lifecycle_observations", "operating_model_observations", "workload_observations", "capacity_estimates")
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
        expected = {"entities": 10, "entity_snapshots": 10, "evidence": 13, "lifecycle_observations": 5, "operating_model_observations": 1, "workload_observations": 0, "capacity_estimates": 1}
        if counts != expected:
            raise OfficialMiddleEastTurkiyeGapError(f"offline import counts differ: {counts!r}")
        capacity = tuple(connection.execute("SELECT e.stable_key, c.metric, c.stage, c.unit, c.base FROM capacity_estimates AS c JOIN entities AS e ON e.id=c.entity_id").fetchone())
        if capacity != ("curated:enka-data-solutions-eds-ist-01-tuzla-data-center:initial-build", "critical_it_mw", "design", "MW", 11.0):
            raise OfficialMiddleEastTurkiyeGapError(f"offline capacity row differs: {capacity!r}")
        return counts


def validate_artifact(path: Path = ARTIFACT, *, source_paths: Mapping[str, Path] | None = None, require_live: bool = True, wall_clock: datetime | None = None) -> dict[str, Any]:
    paths = source_paths or _source_paths(SOURCES_ROOT)
    source_records = _validate_sources(paths)
    if path.is_symlink() or not path.is_dir():
        raise OfficialMiddleEastTurkiyeGapError("artifact must be an ordinary directory")
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise OfficialMiddleEastTurkiyeGapError("artifact closed file set differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries.values()):
        raise OfficialMiddleEastTurkiyeGapError("artifact contains a non-ordinary file")
    if stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise OfficialMiddleEastTurkiyeGapError("artifact directory mode differs")
    if any(stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries.values()):
        raise OfficialMiddleEastTurkiyeGapError("artifact file mode differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest):
        raise OfficialMiddleEastTurkiyeGapError("manifest JSON is not canonical")
    if manifest.get("artifact_id") != ARTIFACT_ID or set(manifest.get("closed_file_set", [])) != CLOSED_FILES or manifest.get("candidate_assessments") != 22 or manifest.get("curated_source_records") != 5 or manifest.get("seed_eligible_source_records") != 5 or manifest.get("review_only_candidates") != 17 or manifest.get("regional_completeness_claimed") is not False or manifest.get("open_seed_successor_created") is not False or manifest.get("release_integration") != "none" or _file_tree(manifest["files"]) != manifest.get("tree_sha256"):
        raise OfficialMiddleEastTurkiyeGapError("manifest contract differs")
    if [row["path"] for row in manifest["files"]] != list(CONTENT_FILES):
        raise OfficialMiddleEastTurkiyeGapError("manifest file order differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (row["bytes"], row["sha256"]):
            raise OfficialMiddleEastTurkiyeGapError(f"manifest file pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != f"{_sha256_bytes(manifest_raw)}  manifest.json\n":
        raise OfficialMiddleEastTurkiyeGapError("manifest checksum differs")
    expected = _artifact_documents(manifest["recorded_at"], expected_source_documents())
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected[name]:
            raise OfficialMiddleEastTurkiyeGapError(f"artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records:
        raise OfficialMiddleEastTurkiyeGapError("artifact source pins differ")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise OfficialMiddleEastTurkiyeGapError("validation wall clock lacks timezone")
    if require_live:
        if now.astimezone(UTC) < target:
            raise OfficialMiddleEastTurkiyeGapError("artifact recorded_at is not live")
        _assert_final_ctimes((*paths.values(), path), target)
    for capture in CAPTURES.values():
        if _instant(capture["retrieved_at"]) > target:
            raise OfficialMiddleEastTurkiyeGapError("capture retrieval post-dates recorded_at")
    return manifest


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise OfficialMiddleEastTurkiyeGapError(f"active publication lock exists: {PUBLICATION_LOCK}") from error
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            PUBLICATION_LOCK.unlink()
        except FileNotFoundError:
            pass


def _all_stage_paths(source_stage: Path, artifact_stage: Path) -> tuple[Path, ...]:
    return (source_stage, *sorted(source_stage.iterdir(), key=lambda item: item.name), artifact_stage, *sorted(artifact_stage.iterdir(), key=lambda item: item.name))


@dataclass(frozen=True)
class _PreparedPublication:
    recorded_at: str
    target: datetime
    source_stage: Path
    source_stage_identity: tuple[int, int]
    source_identities: Mapping[str, tuple[int, int]]
    artifact_stage: Path
    artifact_identity: tuple[int, int]
    artifact_member_identities: Mapping[str, tuple[int, int]]


def _prepare_publication(recorded_at: str) -> _PreparedPublication:
    target = _instant(recorded_at)
    if datetime.now(UTC) >= target:
        raise OfficialMiddleEastTurkiyeGapError("recorded_at must be future before staging")
    source_stage = Path(tempfile.mkdtemp(prefix=".official-builds-middle-east-turkiye-gap.", dir=SOURCES_ROOT))
    artifact_stage = Path(tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT))
    source_stage_identity = _identity(source_stage, directory=True)
    artifact_identity = _identity(artifact_stage, directory=True)
    try:
        documents = expected_source_documents()
        _write_source_stage(source_stage, documents)
        _write_artifact_stage(artifact_stage, recorded_at, documents)
        source_paths = _source_paths(source_stage)
        _validate_sources(source_paths)
        _offline_import(source_paths, recorded_at)
        validate_artifact(artifact_stage, source_paths=source_paths, require_live=False, wall_clock=datetime.now(UTC))
        finals = tuple(SOURCES_ROOT / name for name in SOURCE_FILENAMES) + (ARTIFACT,)
        _require_finals_absent(finals, "staging")
        _assert_stage_precedes_target(_all_stage_paths(source_stage, artifact_stage), target)
        if datetime.now(UTC) >= target:
            raise OfficialMiddleEastTurkiyeGapError("private staging did not finish before recorded_at")
        return _PreparedPublication(
            recorded_at=recorded_at,
            target=target,
            source_stage=source_stage,
            source_stage_identity=source_stage_identity,
            source_identities={name: _identity(source_stage / name, directory=False) for name in SOURCE_FILENAMES},
            artifact_stage=artifact_stage,
            artifact_identity=artifact_identity,
            artifact_member_identities={name: _identity(artifact_stage / name, directory=False) for name in CLOSED_FILES},
        )
    except BaseException as primary_error:
        try:
            if artifact_stage.exists():
                members = {entry.name: _identity(entry, directory=False) for entry in artifact_stage.iterdir()}
                _discard_owned_directory(artifact_stage, artifact_identity, members)
            if source_stage.exists():
                members = {entry.name: _identity(entry, directory=False) for entry in source_stage.iterdir()}
                _discard_owned_directory(source_stage, source_stage_identity, members)
        except Exception as cleanup_error:
            primary_error.add_note(f"private-stage cleanup failed: {cleanup_error}")
        raise


def _publish(prepared: _PreparedPublication) -> None:
    final_sources = {name: SOURCES_ROOT / name for name in SOURCE_FILENAMES}
    finals = tuple(final_sources.values()) + (ARTIFACT,)
    _require_finals_absent(finals, "pre-wait")
    _wait_until(prepared.target.timestamp())
    _require_finals_absent(finals, "publication")
    _assert_stage_precedes_target(_all_stage_paths(prepared.source_stage, prepared.artifact_stage), prepared.target)
    promoted: list[tuple[Path, Path, tuple[int, int], bool]] = []
    try:
        for name in SOURCE_FILENAMES:
            stage = prepared.source_stage / name
            final = final_sources[name]
            identity = prepared.source_identities[name]
            _promote_noreplace(stage, final)
            promoted.append((stage, final, identity, False))
            if not _has_identity(final, identity, directory=False):
                raise OfficialMiddleEastTurkiyeGapError(f"source identity changed on promotion: {name}")
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        promoted.append((prepared.artifact_stage, ARTIFACT, prepared.artifact_identity, True))
        if not _has_identity(ARTIFACT, prepared.artifact_identity, directory=True):
            raise OfficialMiddleEastTurkiyeGapError("artifact identity changed on promotion")
        _assert_final_ctimes(finals, prepared.target)
    except BaseException as primary_error:
        try:
            _rollback_promotions(promoted)
        except Exception as rollback_error:
            primary_error.add_note(f"identity-safe rollback failed: {rollback_error}")
        raise


def _cleanup_prepared(prepared: _PreparedPublication) -> None:
    if prepared.artifact_stage.exists():
        _discard_owned_directory(prepared.artifact_stage, prepared.artifact_identity, prepared.artifact_member_identities)
    if prepared.source_stage.exists():
        _discard_owned_directory(prepared.source_stage, prepared.source_stage_identity, prepared.source_identities)


def _move_capture_to_trash() -> None:
    if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
        raise OfficialMiddleEastTurkiyeGapError("both capture origin and Trash destination exist")
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(CAPTURE_TRASH)


def _default_recorded_at() -> str:
    target = math.ceil(time.time() + 25.0)
    return datetime.fromtimestamp(target, UTC).isoformat().replace("+00:00", "Z")


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    """Publish five source records and the full bounded candidate assessment."""

    target_text = recorded_at or _default_recorded_at()
    finals = tuple(SOURCES_ROOT / name for name in SOURCE_FILENAMES) + (ARTIFACT,)
    _require_finals_absent(finals, "initial")
    _validate_source_collisions()
    _validate_v79_nonmutation()
    capture_directory = CAPTURE_ORIGIN if CAPTURE_ORIGIN.exists() else CAPTURE_TRASH
    _validate_capture_directory(capture_directory)
    with _publication_lock():
        _require_finals_absent(finals, "locked initial")
        prepared = _prepare_publication(target_text)
        published = False
        try:
            _move_capture_to_trash()
            _publish(prepared)
            published = True
        finally:
            if not published:
                _cleanup_prepared(prepared)
        if prepared.source_stage.exists():
            _discard_owned_directory(prepared.source_stage, prepared.source_stage_identity, prepared.source_identities)
    _validate_capture_directory(CAPTURE_TRASH)
    _validate_v79_nonmutation()
    manifest = validate_artifact(ARTIFACT)
    source_records = _validate_sources(_source_paths(SOURCES_ROOT))
    return {
        "artifact_id": ARTIFACT_ID,
        "recorded_at": manifest["recorded_at"],
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "logical_tree_sha256": manifest["tree_sha256"],
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "source_records": source_records,
        "counts": {
            "candidates": 22,
            "source_records": 5,
            "seed_eligible": 5,
            "review_only_or_already_covered": 17,
            "evidence": 13,
            "entities": 10,
            "lifecycle": 5,
            "operating_models": 1,
            "workloads": 0,
            "capacities": 1,
            "coordinates": 0,
            "geometry": 0,
            "placements": 0,
        },
        "capture_directory": str(CAPTURE_TRASH),
        "open_seed_successor_created": False,
        "release_integration": "none",
    }


def main() -> int:
    print(json.dumps(build(), indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
