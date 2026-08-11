"""Publish a bounded CEE official-build gap source artifact.

Five source records retain direct status observations without turning ambiguous
power labels, design capabilities, or identity candidates into normalized facts.
The artifact is independent of accepted open seed v80 and every downstream
product.
"""

from __future__ import annotations

import csv
from contextlib import contextmanager
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

from .external_captures import resolve_external_capture
from . import global_official_builds_next_tranche_20260721 as publication
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "global-official-builds-cee-gap-2026-07-21-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".global-official-builds-cee-gap-20260721.lock"
CAPTURE_ORIGIN = Path("/private/tmp/dc-official-cee-20260721.z5x8RN")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-official-cee-20260721.z5x8RN")

V80_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v80.json"
V80_RELEASE = ROOT / "releases/2026-07-21-open-seed-v80"
V80_MANIFEST = V80_RELEASE / "manifest.json"
V80_ENTITIES = V80_RELEASE / "entities.csv"
V80_EVIDENCE = V80_RELEASE / "evidence.csv"
V80_PINS = {
    V80_DEFINITION: (
        94_529,
        "fb4e3fbcc1ec65a5abb516dbf1d71bf68c6a4d714374126f25f87ba78cc51548",
    ),
    V80_MANIFEST: (
        14_003,
        "a9a89bb89aa0febd32a90b7fb30134f499ad360e08e28eb358bcfd9fe74934d1",
    ),
    V80_ENTITIES: (
        928_628,
        "9db1223c6b847509cf0b4bf1e88e0878bf8b37e9312120956b0c7e839760c9cd",
    ),
    V80_EVIDENCE: (
        220_720,
        "d96b4033290731e491efe91d8c28338534419c38b174fcb74b3d1d3e73cca26c",
    ),
}
V80_TREE_SHA256 = "0215181c22ab0613b77820215fd98098c3c43c9b03ae40f88bd36acb2dec96ca"
V80_INPUT_COUNT = 423
V80_RECORDED_AT = "2026-07-21T17:05:11Z"

DISCOVERY_SNAPSHOT = (
    ARTIFACT_ROOT
    / "europe-latam-official-discovery-2026-07-21-v2/source-snapshot.json"
)
DISCOVERY_SNAPSHOT_PIN = (
    9_104,
    "7e7bea36a6cdadf398dd83524e05c7f8ff0bee495f094c863d0fe1ae6809f65a",
)
DISCOVERY_MANIFEST = (
    ARTIFACT_ROOT / "europe-latam-official-discovery-2026-07-21-v2/manifest.json"
)
DISCOVERY_MANIFEST_PIN = (
    2_237,
    "8e5eb78bd273bdbe9521ba7ef52f60bb9b4eab89d8d208c9fef6569aecba313c",
)

SOURCE_FILENAMES = (
    "curated-official-2026-07-21-microsoft-ath04-spata-current-build.json",
    "curated-official-2026-07-21-tet-dc7-salaspils-phase1-current-build.json",
    "curated-official-2026-07-21-ten-brinke-spata-current-build.json",
    "curated-official-2026-07-21-ast-janciems-shell-fit-out.json",
    "curated-official-2026-07-21-serbia-state-dc-kragujevac-modules-3-4-operational.json",
)
CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

OfficialCeeGapError = publication.OfficialTrancheError
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


CAPTURE_TREE_SHA256 = "628ce85aba4cb295a434aeb4cd1bd3b319f414445ac92e94750661232290a37c"
CAPTURE_FILE_COUNT = 83
CAPTURE_TOTAL_BYTES = 1_664_612


def _capture(
    filename: str,
    url: str,
    size: int,
    digest: str,
    content_type: str,
    *,
    published_at: str | None = None,
) -> dict[str, Any]:
    return {
        "filename": filename,
        "url": url,
        "published_at": published_at,
        "retrieved_at": "2026-07-21T17:05:00Z",
        "http_status": 200,
        "bytes": size,
        "sha256": digest,
        "content_type": content_type,
    }


CAPTURES = {
    "microsoft_backlog": _capture(
        "renco_q1_2026.body",
        "https://www.renco.it/sites/default/files/2026-06/REPORTING%20INVESTORS%201%C2%B0Q%202026.pdf",
        533_272,
        "98ca5031b6d9f7501b083fd9399d6529d94a3c8e04f36949dba97697240b09ac",
        "application/pdf",
        published_at="2026-05-27",
    ),
    "microsoft_gek": _capture(
        "gek_terna_ath04.body",
        "https://www.gekterna.com/erection-of-data-building-athens/",
        300_562,
        "283cfe061eb0d780573d182d375d653af666ef848646f66ba0ef3de48b25410d",
        "text/html; charset=UTF-8",
        published_at="2024-06-30",
    ),
    "microsoft_renco": _capture(
        "renco_microsoft_dc.body",
        "https://www.renco.it/projects/microsoft-data-center",
        39_778,
        "104f5c70e1a318c54d93af6f94df291511c1714f2ec5db297a5ee972877e5078",
        "text/html; charset=UTF-8",
    ),
    "tet_citrus": _capture(
        "citrus_tet_dc7.body",
        "https://www.citrus.lv/en/projects/building-engineering/design-and-construction-of-tet-data-center-dc7/",
        56_931,
        "6e22237722ab1baa2c2cec48688e6a21fadcfd9cdab1f76318b17707a0ced644",
        "text/html; charset=UTF-8",
        published_at="2024-09-11",
    ),
    "tet_enersense": _capture(
        "enersense_latvia.body",
        "https://enersense.com/releases/enersense-signs-data-centre-infrastructure-agreements-in-latvia/",
        72_343,
        "e4fcf18250666f21603c407f433be9860bd2bb048d01446859103756563439b8",
        "text/html; charset=UTF-8",
        published_at="2026-02-11",
    ),
    "ten_brinke": _capture(
        "ten_brinke_spata_browser.body",
        "https://www.tenbrinke.com/en/projects/current-projects/current-projects-details/data-center-spata-26-1052-gr.html",
        35_413,
        "9ef57bbcb1517843d3e2e0f399d645147433f9896b1ece41f062cff8c5273c1a",
        "text/html; charset=UTF-8",
    ),
    "serbia": _capture(
        "serbia_kragujevac.body",
        "https://ite.gov.rs/vest/12291/srbija-unapredjuje-digitalnu-infrastrukturu-pusteni-u-rad-novi-kapaciteti-data-centra-u-kragujevcu.php",
        86_513,
        "c6b3808ee7b30f7817dbc639809afdfbd1b60e254ba497974ee143228ca8ed1f",
        "text/html; charset=UTF-8",
        published_at="2026-04-30",
    ),
}

AST_URL = (
    "https://www.ast.lv/en/events/commissioning-new-building-latvias-power-system-"
    "main-dispatcher-control-and-data-centre"
)
PPC_PRESENTATION_URL = (
    "https://www.ppcgroup.com/media/ipejbw30/"
    "corporate-presentation_18052026_vf.pdf"
)
PPC_ANNOUNCEMENT_URL = (
    "https://www.ppcgroup.com/en/investor-relations/announcements/stock-news/"
    "stock-news-2024/edgnex-data-centers-by-damac-and-ppc-group-announce-new-"
    "data-center-in-attica-greece/"
)

PLANNED_ALIASES = frozenset(
    {
        "Microsoft ATH04 Spata Data Center",
        "ATH04 Building",
        "Tet DC7 Salaspils",
        "DC7 Data Center",
        "Ten Brinke Data Center Spata",
        "AST Jāņciems Dispatcher Control and Data Centre",
        "Serbia State Data Center Kragujevac Modules 3 and 4",
    }
)
PLANNED_URLS = frozenset(
    {
        *(capture["url"] for capture in CAPTURES.values()),
        AST_URL,
        PPC_PRESENTATION_URL,
        PPC_ANNOUNCEMENT_URL,
    }
)


def _captured_evidence(
    capture_id: str,
    *,
    key: str,
    kind: str,
    title: str,
    publisher: str,
    source_family: str,
    excerpt: str,
    metadata: Mapping[str, Any],
    license_name: str = "all-rights-reserved",
    attribution: str | None = None,
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
        "content_type": capture["content_type"],
        "request_credentials_supplied": False,
        "rights_scope": (
            "Only compact factual extraction is released. Raw response bytes, "
            "headers, telemetry, and publisher media are not redistributed."
        ),
        "imagery_guardrail": (
            "No publisher image, map coordinate, satellite image, aerial image, "
            "computer vision, or analyst geolocation contributes to this record."
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
        "license": license_name,
        "attribution": attribution or publisher,
        "excerpt": excerpt,
        "content_hash": capture["sha256"],
        "metadata": common,
    }


def _indexed_evidence(
    *,
    key: str,
    kind: str,
    title: str,
    source_url: str,
    publisher: str,
    source_family: str,
    published_at: str,
    excerpt: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    assertion = f"{source_url}\n{published_at}\n{excerpt}\n"
    common = {
        "content_hash_scope": (
            "SHA-256 of the exact normalized URL, publication date, and compact "
            "claim text transcribed from an indexed official page; not source bytes"
        ),
        "content_hash_verification": "unverified_assertion",
        "capture_artifact_id": ARTIFACT_ID,
        "capture_method": "indexed_official_page_fallback_after_direct_fetch_block",
        "network_timeout_contract": "connect_timeout_10s_wall_clock_timeout_45s",
        "request_credentials_supplied": False,
        "direct_response_claim_bearing": False,
        "rights_scope": (
            "No indexed page body or search-result body is redistributed; only the "
            "compact assertion hash and provenance are released."
        ),
        "imagery_guardrail": (
            "No publisher image, map coordinate, satellite image, aerial image, "
            "computer vision, or analyst geolocation contributes to this record."
        ),
    }
    common.update(metadata)
    return {
        "key": key,
        "kind": kind,
        "title": title,
        "source_url": source_url,
        "publisher": publisher,
        "source_family": source_family,
        "published_at": published_at,
        "retrieved_at": "2026-07-21T17:05:00Z",
        "license": "all-rights-reserved",
        "attribution": publisher,
        "excerpt": excerpt,
        "content_hash": _sha256_bytes(assertion.encode()),
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


def _lifecycle(value: str, evidence_key: str, as_of_date: str) -> dict[str, Any]:
    return {
        "entity": "project",
        "value": value,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": "authoritative_physical_status_update",
        "confidence": 0.99,
    }


def _classification(value: str, evidence_key: str, as_of_date: str) -> dict[str, Any]:
    return {
        "entity": "project",
        "value": value,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": "company_disclosure",
        "confidence": 0.99,
    }


def _generation_capacity(evidence_key: str) -> dict[str, Any]:
    return {
        "entity": "project",
        "metric": "generation_nameplate_mw",
        "stage": "operational",
        "unit": "MW",
        "low": 0.3,
        "base": 0.3,
        "high": 0.3,
        "method": "reported",
        "confidence": 0.99,
        "evidence_key": evidence_key,
        "as_of_date": "2026-04-30",
        "target_date": None,
        "notes": (
            "300 kW installed rooftop solar generation only. It is not data-center "
            "load, IT capacity, gross demand, consumption, or annual energy."
        ),
    }


def _microsoft_source() -> dict[str, Any]:
    backlog_key = "microsoft-ath04-renco-q1-2026-backlog-captured-2026-07-21"
    gek_key = "microsoft-ath04-gek-terna-project-page-captured-2026-07-21"
    renco_key = "microsoft-ath04-renco-project-page-captured-2026-07-21"
    evidence = [
        _captured_evidence(
            "microsoft_backlog",
            key=backlog_key,
            kind="company_disclosure",
            title="Renco Q1 2026 backlog: DATA CENTER ATH04 MICROSOFT",
            publisher="RENCO S.p.A.",
            source_family="renco_investor_reporting",
            excerpt=(
                "Renco's Q1 2026 backlog lists DATA CENTER ATH04 MICROSOFT in "
                "Greece, client Microsoft, with year end 2027 and work remaining."
            ),
            metadata={
                "observation_period_end": "2026-03-31",
                "status_scope": (
                    "The live Q1 backlog supplies current-period continuity; the "
                    "separate GEK TERNA and Renco project pages provide the explicit "
                    "Under Construction and In progress physical-status wording."
                ),
                "contract_value_eur_millions_as_reported": 54.6,
                "to_be_produced_eur_millions_as_reported": 29.0,
                "financial_values_normalized_as_capacity": False,
            },
        ),
        _captured_evidence(
            "microsoft_gek",
            key=gek_key,
            kind="company_disclosure",
            title="GEK TERNA ATH04 project page",
            publisher="GEK TERNA",
            source_family="gek_terna_project_pages",
            excerpt=(
                "GEK TERNA labels the Microsoft ATH04 data-building project in Spata "
                "Under Construction and describes cloud data processing."
            ),
            metadata={
                "page_status_as_reported": "Under Construction",
                "page_modified_at": "2025-01-26T10:48:26Z",
                "reported_total_installed_capacity_mw": 19.2,
                "capacity_disposition": (
                    "Total installed capacity is basis-ambiguous and creates no "
                    "critical IT, grid, gross, generation, current-load, consumption, "
                    "annual-energy, or PUE row."
                ),
                "workload_scope": (
                    "Cloud describes facility design/purpose, not an active tenant, "
                    "customer contract, installed hardware, or current load."
                ),
            },
        ),
        _captured_evidence(
            "microsoft_renco",
            key=renco_key,
            kind="company_disclosure",
            title="Renco Microsoft Data Center project page",
            publisher="RENCO S.p.A.",
            source_family="renco_project_pages",
            excerpt=(
                "Renco labels the Microsoft Data Center in Spata In progress and "
                "describes a main building containing cloud-storage equipment."
            ),
            metadata={
                "page_status_as_reported": "In progress",
                "stale_end_2025_label_retained": True,
                "stale_end_2025_label_used_for_status": False,
                "reported_total_installed_capacity_mw": 19.2,
                "capacity_rows_created": 0,
            },
        ),
    ]
    roles = {
        "owner": ["Microsoft"],
        "operator": ["Microsoft"],
        "contractor": ["RENCO S.p.A.", "TERNA S.A."],
    }
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key="curated:microsoft-ath04-spata-data-center",
            name="Microsoft ATH04 Spata Data Center",
            country="Greece",
            address="Spata, Athens, Greece",
            roles=roles,
            evidence_key=gek_key,
            as_of_date="2026-03-31",
        ),
        "project": _entity(
            stable_key="curated:microsoft-ath04-spata-data-center:active-construction",
            name="Microsoft ATH04 Spata Active Construction",
            country="Greece",
            address="Spata, Athens, Greece",
            roles=roles,
            evidence_key=gek_key,
            as_of_date="2026-03-31",
        ),
        "lifecycle": [_lifecycle("under_construction", backlog_key, "2026-03-31")],
        "operating_models": [
            _classification("hyperscale_self_build", gek_key, "2026-03-31")
        ],
        "workloads": [_classification("general_cloud", gek_key, "2026-03-31")],
        "capacities": [],
    }


def _tet_source() -> dict[str, Any]:
    identity_key = "tet-dc7-citrus-project-page-captured-2026-07-21"
    status_key = "tet-dc7-enersense-salaspils-status-captured-2026-07-21"
    evidence = [
        _captured_evidence(
            "tet_citrus",
            key=identity_key,
            kind="company_disclosure",
            title="Citrus Solutions Tet DC7 project page",
            publisher="Citrus Solutions",
            source_family="citrus_solutions_project_pages",
            excerpt=(
                "Citrus says it is implementing construction of Tet's DC7 at Krasta "
                "2/1 in Salaspils, with an August 2024 to December 2028 period and "
                "two 112-rack phases."
            ),
            metadata={
                "page_modified_at": "2026-03-12T09:22:14Z",
                "physical_status_as_reported": (
                    "SIA Citrus Solutions is implementing the construction of the "
                    "DC7 data center."
                ),
                "construction_period_as_reported": "08/2024 - 12/2028",
                "phase_1_racks_as_reported": 112,
                "phase_1_target_as_reported": "Q3 2026",
                "phase_2_additional_racks_as_reported": 112,
                "phase_2_target_as_reported": "end of 2028",
                "tier_target_as_reported": "Uptime Institute TIER III",
                "facility_purpose_scope": (
                    "Hosting critical IT for government and business clients is a "
                    "design/customer-purpose statement, not an active tenant or load."
                ),
                "ai_scope": (
                    "Ability to operate powerful AI equipment is capability only and "
                    "creates no AI workload row."
                ),
                "carrier_neutral_or_colocation_directly_stated": False,
            },
        ),
        _captured_evidence(
            "tet_enersense",
            key=status_key,
            kind="company_disclosure",
            title="Enersense Salaspils data-centre infrastructure agreements",
            publisher="Enersense International Plc",
            source_family="enersense_press_releases",
            excerpt=(
                "Enersense reports a new large-scale data centre currently under "
                "construction in Salaspils and contracted fibre and power-line works."
            ),
            metadata={
                "identity_scope": (
                    "Enersense does not name Tet or DC7. It is not used alone to bridge "
                    "identity and does not anchor the DC7 lifecycle observation. It is "
                    "retained only as corroborating Salaspils-area infrastructure "
                    "evidence alongside Citrus's direct Tet/DC7 construction evidence."
                ),
                "status_scope": "Current physical construction in Salaspils on 2026-02-11.",
                "electrical_scope": (
                    "Medium- and low-voltage line construction is supporting "
                    "infrastructure, not facility MW, current draw, or annual energy."
                ),
            },
        ),
    ]
    roles = {"owner": ["Tet"], "operator": ["Tet"], "contractor": ["Citrus Solutions"]}
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key="curated:tet-dc7-salaspils-data-center",
            name="Tet DC7 Salaspils Data Center",
            country="Latvia",
            address="Krasta 2/1, Salaspils, Latvia",
            roles=roles,
            evidence_key=identity_key,
            as_of_date="2026-03-12",
        ),
        "project": _entity(
            stable_key="curated:tet-dc7-salaspils-data-center:phase-1-current-build",
            name="Tet DC7 Salaspils Phase 1 Current Build",
            country="Latvia",
            address="Krasta 2/1, Salaspils, Latvia",
            roles=roles,
            evidence_key=identity_key,
            as_of_date="2026-03-12",
        ),
        "lifecycle": [_lifecycle("under_construction", identity_key, "2026-03-12")],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _ten_brinke_source() -> dict[str, Any]:
    status_key = "ten-brinke-spata-current-project-captured-2026-07-21"
    ppc_current_key = "ppc-spata-current-development-indexed-2026-07-21"
    ppc_launch_key = "ppc-data-in-scale-spata-launch-indexed-2026-07-21"
    evidence = [
        _captured_evidence(
            "ten_brinke",
            key=status_key,
            kind="company_disclosure",
            title="Ten Brinke Data Center Spata current-project page",
            publisher="Ten Brinke Group",
            source_family="ten_brinke_current_project_pages",
            excerpt=(
                "Ten Brinke lists Data Center Spata as a current project with "
                "construction year 2026 and scheduled completion in 2026."
            ),
            metadata={
                "status_as_of_semantics": (
                    "No publication date is exposed; 2026-07-21 is the access date of "
                    "the live page classified by the publisher as Current projects."
                ),
                "address_as_reported": "ΑΓΙΟΥ ΔΗΜΗΤΡΙΟΥ, 19004 ΣΠΑΤΑ, Greece",
                "building_area_sqm_approximate_as_reported": 11_000,
                "plot_area_sqm_as_reported": 32_000,
                "commercial_scope": (
                    "The page describes demand for data storage and management; it "
                    "does not establish an AI-exclusive workload or active tenants."
                ),
            },
        ),
        _indexed_evidence(
            key=ppc_current_key,
            kind="company_disclosure",
            title="PPC May 2026 corporate presentation: Spata development",
            source_url=PPC_PRESENTATION_URL,
            publisher="PPC Group",
            source_family="ppc_investor_presentations",
            published_at="2026-05-18",
            excerpt=(
                "PPC says it continues to develop its data center in Spata, expects "
                "the first 12.5 MW phase operational by end-2027, and plans 25 MW later."
            ),
            metadata={
                "resolution_candidate_only": (
                    "This record does not assert that PPC/Data In Scale and the Ten "
                    "Brinke physical project are the same project."
                ),
                "resolution_candidate_stable_key": (
                    "curated:data-in-scale-spata-campus:phase-1-current-build"
                ),
                "capacity_disposition": (
                    "12.5 MW and 25 MW are basis-ambiguous and create no normalized row."
                ),
            },
        ),
        _indexed_evidence(
            key=ppc_launch_key,
            kind="company_disclosure",
            title="PPC and EDGNEX launch Data In Scale in Spata",
            source_url=PPC_ANNOUNCEMENT_URL,
            publisher="PPC Group",
            source_family="ppc_stock_news",
            published_at="2024-12-04",
            excerpt=(
                "PPC and EDGNEX announced Data In Scale for a data center in Spata, "
                "with a 12.5 MW first phase and 25 MW later plan."
            ),
            metadata={
                "resolution_candidate_only": True,
                "identity_link_asserted": False,
                "role_link_asserted": False,
                "capacity_rows_created": 0,
            },
        ),
    ]
    roles = {"developer": ["Ten Brinke Group"], "contractor": ["TenTec", "Ten Brinke Hellas"]}
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key="curated:ten-brinke-spata-data-center",
            name="Ten Brinke Spata Data Center",
            country="Greece",
            address="ΑΓΙΟΥ ΔΗΜΗΤΡΙΟΥ, 19004 ΣΠΑΤΑ, Greece",
            roles=roles,
            evidence_key=status_key,
            as_of_date="2026-07-21",
        ),
        "project": _entity(
            stable_key="curated:ten-brinke-spata-data-center:active-construction",
            name="Ten Brinke Spata Data Center Active Construction",
            country="Greece",
            address="ΑΓΙΟΥ ΔΗΜΗΤΡΙΟΥ, 19004 ΣΠΑΤΑ, Greece",
            roles=roles,
            evidence_key=status_key,
            as_of_date="2026-07-21",
        ),
        "lifecycle": [_lifecycle("under_construction", status_key, "2026-07-21")],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _ast_source() -> dict[str, Any]:
    status_key = "ast-janciems-building-complete-fitout-started-indexed-2026-07-21"
    evidence = [
        _indexed_evidence(
            key=status_key,
            kind="company_disclosure",
            title="AST Jāņciems building completion and fitting-out start",
            source_url=AST_URL,
            publisher='AS "Augstsprieguma tīkls"',
            source_family="ast_official_events",
            published_at="2026-06-27",
            excerpt=(
                "AST reports that construction of the Jāņciems dispatcher control "
                "and data-centre building is complete and fitting-out works have begun."
            ),
            metadata={
                "lifecycle_scope": (
                    "Shell records building completion plus fit-out. It does not assert "
                    "MEP completion, commissioning, data-center operation, or service."
                ),
                "facility_type": "sovereign_transmission_control_and_data_center",
                "direct_fetch_incident": (
                    "The official page returned an access-control response to the "
                    "credential-free capture IP; the indexed official-page assertion "
                    "is retained as unverified_assertion rather than source-byte hash."
                ),
                "independent_live_page_open_verification": {
                    "verified_at": "2026-07-21",
                    "scope": (
                        "A separate live open of the same first-party AST page verified "
                        "the exact building-complete, fit-out-begun claim and the listed "
                        "address Dārzciema iela 86, Rīga. No page bytes are represented "
                        "as captured by this artifact."
                    ),
                    "source_byte_hash_claimed": False,
                },
            },
        )
    ]
    roles = {"owner": ['AS "Augstsprieguma tīkls"'], "operator": ['AS "Augstsprieguma tīkls"']}
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key="curated:ast-janciems-dispatcher-control-data-center",
            name="AST Jāņciems Dispatcher Control and Data Centre",
            country="Latvia",
            address="Dārzciema iela 86, Rīga",
            roles=roles,
            evidence_key=status_key,
            as_of_date="2026-06-27",
        ),
        "project": _entity(
            stable_key=(
                "curated:ast-janciems-dispatcher-control-data-center:"
                "fit-out-after-building-completion"
            ),
            name="AST Jāņciems Fit-out After Building Completion",
            country="Latvia",
            address="Dārzciema iela 86, Rīga",
            roles=roles,
            evidence_key=status_key,
            as_of_date="2026-06-27",
        ),
        "lifecycle": [_lifecycle("shell", status_key, "2026-06-27")],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _serbia_source() -> dict[str, Any]:
    status_key = "serbia-state-dc-kragujevac-modules-3-4-live-captured-2026-07-21"
    evidence = [
        _captured_evidence(
            "serbia",
            key=status_key,
            kind="government_record",
            title="Kragujevac State Data Center modules 3 and 4 put into operation",
            publisher="Office for IT and eGovernment, Republic of Serbia",
            source_family="serbia_ite_government_news",
            excerpt=(
                "The Serbian government reports modules 3 and 4 put into operation, "
                "a second NVIDIA-GPU supercomputer activated, and 300 kW rooftop solar."
            ),
            license_name=(
                "Creative Commons Attribution-NonCommercial-NoDerivatives 3.0 Serbia "
                "(CC BY-NC-ND 3.0 RS)"
            ),
            attribution="Office for IT and eGovernment, Republic of Serbia; ite.gov.rs",
            metadata={
                "license_url": "https://creativecommons.org/licenses/by-nc-nd/3.0/rs/",
                "license_terms_as_displayed": (
                    "Ауторство-Некомерцијално-Без прерада 3.0 Србија"
                ),
                "facility_type": "sovereign_government_data_center",
                "reported_modules": [3, 4],
                "reported_module_energy_capacity_mw": 8,
                "reported_total_energy_capacity_mw": 14,
                "load_capacity_disposition": (
                    "Both energy-capacity labels are basis-ambiguous and create no "
                    "grid, gross, critical-IT, current-load, consumption, or annual-"
                    "energy row."
                ),
                "gpu_scope": (
                    "The source directly reports activation of the second NVIDIA-GPU "
                    "supercomputer; ai_specialized_unspecified does not infer tenants, "
                    "training, inference, utilization, or chip count at this module."
                ),
                "solar_scope": (
                    "Installed 300 kW rooftop panels and energy produced from them "
                    "support one operational generation-nameplate row only."
                ),
                "prior_discovery_reconciliation": {
                    "artifact_id": "europe-latam-official-discovery-2026-07-21-v2",
                    "prior_candidate": "Kragujevac State Data Center Block 2",
                    "prior_decision": "not_promoted_planned_only",
                    "new_scope": "modules_3_and_4_recently_operational_expansion",
                    "block_2_identity_asserted": False,
                    "resolution_disposition": (
                        "The April 30 source closes an operational modules 3/4 scope. "
                        "It does not say modules 3/4 equal the earlier planned Block 2."
                    ),
                },
            },
        )
    ]
    roles = {
        "owner": ["Republic of Serbia"],
        "operator": ["Office for IT and eGovernment, Republic of Serbia"],
        "user": ["Republic of Serbia"],
    }
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key="curated:serbia-state-data-center-kragujevac",
            name="Serbia State Data Center Kragujevac",
            country="Serbia",
            address="Kragujevac, Serbia",
            roles=roles,
            evidence_key=status_key,
            as_of_date="2026-04-30",
        ),
        "project": _entity(
            stable_key=(
                "curated:serbia-state-data-center-kragujevac:"
                "modules-3-4-commissioned-2026"
            ),
            name="Serbia State Data Center Kragujevac Modules 3 and 4",
            country="Serbia",
            address="Kragujevac, Serbia",
            roles=roles,
            evidence_key=status_key,
            as_of_date="2026-04-30",
        ),
        "lifecycle": [_lifecycle("operational", status_key, "2026-04-30")],
        "operating_models": [
            _classification("sovereign_research", status_key, "2026-04-30")
        ],
        "workloads": [
            _classification("ai_specialized_unspecified", status_key, "2026-04-30")
        ],
        "capacities": [_generation_capacity(status_key)],
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    """Return the exact five schema-1.1 source documents."""

    builders = (
        _microsoft_source,
        _tet_source,
        _ten_brinke_source,
        _ast_source,
        _serbia_source,
    )
    return {
        name: builder()
        for name, builder in zip(SOURCE_FILENAMES, builders, strict=True)
    }


def _source_records(
    documents: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    records = []
    for name in SOURCE_FILENAMES:
        document = documents[name]
        payload = _canonical(document)
        lifecycle = document["lifecycle"][0]["value"]
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
                "disposition": (
                    "seed_eligible_recent_operational_completion"
                    if lifecycle == "operational"
                    else "seed_eligible_official_physical_observation"
                ),
                "seed_eligible": True,
                "seeded": False,
            }
        )
    return records


def _review_candidates() -> list[dict[str, Any]]:
    rows = [
        ("data4-jawczyce", "Poland", "review_only_operational", "The facility is now operational, not a current build."),
        ("atman-waw3", "Poland", "review_only_operational", "WAW-3 is now operational, not a current build."),
        ("wbs-lublewo-choczewo", "Poland", "review_only_grid_and_preparation", "The 3.2 GW program is grid or preparatory work with a 2028/2029 data-center horizon, not physical data-center construction."),
        ("vantage-poland-current-build-screen", "Poland", "review_only_no_current_evidence", "The bounded screen found no current site-specific Vantage physical evidence."),
        ("clusterpower-romania", "Romania", "review_only_old_or_plan", "Available official material was old, planned, or insufficiently phase-specific."),
        ("hungary-unnamed-relative-expansion", "Hungary", "review_only_unnamed_relative_expansion", "Relative expansion language did not identify a distinct current physical project."),
        ("slovakia-bounded-screen", "Slovakia", "review_only_no_qualifying_candidate", "The bounded screen found no qualifying current physical project."),
        ("pantheon-croatia", "Croatia", "review_only_mou_future", "The evidence is an LOI or MOU with a future 2027 horizon."),
        ("radomir-bulgaria-nis-serbia", "Bulgaria and Serbia", "review_only_contract_or_future", "Contract and future-development language does not establish current physical data-center work."),
        ("ppc-kozani", "Greece", "review_only_permits_design_grid", "Permit pre-approval, engineering, grid application, and expected future start do not prove physical construction."),
        ("cyprus-regulatory-screen", "Cyprus", "review_only_regulatory", "Regulatory material did not establish a distinct current physical project."),
        ("ixcellerate-mos7", "Russia", "review_only_old_start", "The last physical event was December 2025 and does not establish current July 2026 status."),
        ("ixcellerate-mos11", "Russia", "review_only_planning", "Planning evidence does not establish physical construction."),
        ("sunly-risti", "Estonia", "review_only_substation_or_planning", "Substation and planning activity is not physical data-center construction."),
        ("cra-prague", "Czechia", "already_represented_in_v80", "Accepted v80 already contains the candidate; no duplicate is created."),
        ("pozitrons", "Latvia", "already_represented_in_v80", "Accepted v80 already contains the candidate; no duplicate is created."),
        ("telia-vilnius", "Lithuania", "already_represented_in_v80", "Accepted v80 already contains the candidate; no duplicate is created."),
        ("data4-ath1", "Greece", "already_represented_in_v80", "Accepted v80 already contains the candidate; no duplicate is created."),
        ("arnes-maribor", "Slovenia", "already_represented_in_v80", "Accepted v80 already contains the candidate; no duplicate is created."),
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
    documents = expected_source_documents()
    seed_rows = []
    decisions = (
        "seed_eligible_current_under_construction",
        "seed_eligible_current_under_construction",
        "seed_eligible_current_under_construction_identity_unresolved_to_data_in_scale",
        "seed_eligible_shell_fit_out_after_building_completion",
        "seed_eligible_recent_operational_completion_not_current_construction",
    )
    for name, decision in zip(SOURCE_FILENAMES, decisions, strict=True):
        document = documents[name]
        row = {
            "candidate_id": document["project"]["stable_key"],
            "country": document["project"]["country"],
            "decision": decision,
            "source_record_created": True,
            "source_path": f"sources/{name}",
            "seed_eligible": True,
            "lifecycle": document["lifecycle"][0]["value"],
            "lifecycle_as_of": document["lifecycle"][0]["as_of_date"],
            "capacity_estimates": len(document["capacities"]),
            "operating_model_observations": len(document["operating_models"]),
            "workload_observations": len(document["workloads"]),
            "coordinates_created": 0,
        }
        if name == SOURCE_FILENAMES[4]:
            row["prior_discovery_reconciliation"] = {
                "prior_candidate": "Kragujevac State Data Center Block 2",
                "prior_scope": "planned_only_not_promoted",
                "new_scope": "modules_3_and_4_recently_operational_expansion",
                "same_project_asserted": False,
                "stable_key_collision_with_v80": 0,
                "evidence_key_collision_with_v80": 0,
            }
        seed_rows.append(row)
    reviews = _review_candidates()
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-cee-official-gap-assessment-v1",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "candidate_count": len(seed_rows) + len(reviews),
        "seed_eligible_count": len(seed_rows),
        "review_only_count": len(reviews),
        "regional_completeness_claimed": False,
        "candidates": [*seed_rows, *reviews],
    }


def _capture_directory() -> Path:
    if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
        raise OfficialCeeGapError("both capture origin and Trash destination exist")
    if CAPTURE_ORIGIN.exists():
        return CAPTURE_ORIGIN
    return resolve_external_capture(CAPTURE_TRASH)


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise OfficialCeeGapError(f"capture directory is absent or unsafe: {directory}")
    entries = list(directory.iterdir())
    if len(entries) != CAPTURE_FILE_COUNT:
        raise OfficialCeeGapError("capture directory file count differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise OfficialCeeGapError("capture directory contains a non-file")
    if sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES:
        raise OfficialCeeGapError("capture directory total bytes differs")
    if tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise OfficialCeeGapError("capture directory tree differs")


def _private_capture_inventory() -> list[dict[str, Any]]:
    directory = _capture_directory()
    _validate_capture_directory(directory)
    return [
        {
            "path": item.name,
            "bytes": item.stat().st_size,
            "sha256": _sha256(item),
        }
        for item in sorted(directory.iterdir(), key=lambda entry: entry.name)
    ]


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "capture_protocol": (
            "Credential-free curl GETs with explicit 10-second connect and "
            "45-second wall-clock timeouts."
        ),
        "successful_http_200_body_captures": len(CAPTURES),
        "indexed_official_page_assertions": 3,
        "indexed_assertions_with_source_byte_hash": 0,
        "failed_or_partial_capture_claims_released_as_fetched_bytes": 0,
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
                "content_type": capture["content_type"],
                "body": {
                    "path": capture["filename"],
                    "bytes": capture["bytes"],
                    "sha256": capture["sha256"],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "capture_method": "credential_free_curl_location_compressed",
                "network_timeout_contract": (
                    "connect_timeout_10s_wall_clock_timeout_45s"
                ),
                "request_credentials_supplied": False,
                "used_for_normalized_claims": True,
            }
            for capture_id, capture in sorted(CAPTURES.items())
        ],
        "indexed_assertions": [
            {
                "source_url": AST_URL,
                "publisher": 'AS "Augstsprieguma tīkls"',
                "used_for_normalized_claims": True,
                "content_hash_verification": "unverified_assertion",
                "direct_capture_disposition": "access_control_response",
            },
            {
                "source_url": PPC_PRESENTATION_URL,
                "publisher": "PPC Group",
                "used_for_normalized_claims": False,
                "content_hash_verification": "unverified_assertion",
                "direct_capture_disposition": "redirect_loop",
            },
            {
                "source_url": PPC_ANNOUNCEMENT_URL,
                "publisher": "PPC Group",
                "used_for_normalized_claims": False,
                "content_hash_verification": "unverified_assertion",
                "direct_capture_disposition": "redirect_loop",
            },
        ],
        "complete_private_file_inventory": _private_capture_inventory(),
        "technical_incidents": [
            {
                "incident": "AST direct access-control response",
                "normalized_scope": "indexed official-page assertion only",
                "source_byte_hash_claimed": False,
            },
            {
                "incident": "PPC self-redirect loops",
                "normalized_scope": "identity-resolution narrative only",
                "source_byte_hash_claimed": False,
            },
            {
                "incident": "anonymous Jina reader blocked by network reputation",
                "normalized_scope": "none",
                "source_byte_hash_claimed": False,
            },
        ],
    }


def _artifact_documents(
    recorded_at: str,
    source_documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    source_records = _source_records(source_documents)
    review_count = len(_review_candidates())
    assessment_count = len(source_records) + review_count
    duplicate_witness = _v80_duplicate_witness(source_documents)
    readme = f"""# CEE official-build gap assessment

This immutable artifact records {assessment_count} bounded candidate dispositions researched on 2026-07-21: five seed-eligible source records and {review_count} assessment-only reviews or accepted-v80 duplicates. It makes no regional-completeness claim.

Microsoft ATH04, Tet DC7, and the physical Ten Brinke Spata project carry dated `under_construction` observations. AST Jāņciems carries `shell` because the building is complete and fit-out has begun; that is not MEP completion, commissioning, or operation. Serbia's Kragujevac modules 3 and 4 carry `operational` as a recent completion, not a current-construction claim.

The Ten Brinke physical project is not hard-linked to PPC/Data In Scale. The PPC evidence is retained only as an unresolved resolution candidate. Its 12.5 MW first-phase and 25 MW campus labels, Microsoft's 19.2 MW installed-capacity label, and Serbia's 8 MW and 14 MW energy-capacity labels are basis-ambiguous and create no data-center load, consumption, or annual-energy row.

Serbia's directly reported installed 300 kW rooftop solar creates exactly one 0.3 MW operational `generation_nameplate_mw` row. It is never treated as grid connection, gross facility capacity, critical IT, current draw, consumption, or annual energy. The active NVIDIA-GPU supercomputer supports `ai_specialized_unspecified` only; no tenant, training, inference, utilization, or chip-count claim is inferred.

The earlier `europe-latam-official-discovery-2026-07-21-v2` review retained “Kragujevac State Data Center Block 2” as planned-only. The April 30 source establishes a distinct modules-3-and-4 recently operational expansion/state closure. This artifact does not assert that modules 3 and 4 equal the earlier Block 2 label. The new stable keys and evidence key have zero collision with accepted v80.

Tet identity and address come from Citrus. Enersense independently supplies a current Salaspils physical-status observation but does not name Tet or DC7, so it is never used alone as an identity bridge. AI-equipment support remains capability only. No coordinate is released from any source page or map.

All planned names, source URLs, stable keys, and evidence keys were checked for exact normalized absence from accepted v80. Accepted v80 and all downstream products remain unchanged. Raw all-rights-reserved captures are not redistributed. The Serbian page's CC BY-NC-ND 3.0 Serbia terms and attribution are preserved, but its raw bytes are also withheld.

All source and artifact bytes were complete in private staging before `{recorded_at}`. Final paths remained absent until the declared instant and were promoted without replacement with identity-checked rollback. Source and artifact files are frozen mode 0444; the artifact directory is mode 0555.
"""
    totals = {
        "candidate_assessments": assessment_count,
        "source_records": 5,
        "seed_eligible_source_records": 5,
        "review_only_candidates": review_count,
        "distinct_campuses": 5,
        "projects": 5,
        "entity_snapshots": 10,
        "unique_evidence_records": 10,
        "lifecycle_observations": 5,
        "operating_model_observations": 2,
        "workload_observations": 2,
        "capacity_estimates": 1,
        "generation_nameplate_capacity_estimates": 1,
        "data_center_load_capacity_estimates": 0,
        "coordinates_present": 0,
        "geometry_present": 0,
        "placement_observations": 0,
        "energy_consumption_observations": 0,
        "pue_observations": 0,
    }
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "regional_completeness_claimed": False,
        "source_records": source_records,
        "totals": totals,
        "frozen_v80_non_mutation_witness": {
            "recorded_at": V80_RECORDED_AT,
            "definition": {
                "path": "sources/open-seed-2026-07-21-v80.json",
                "bytes": V80_PINS[V80_DEFINITION][0],
                "sha256": V80_PINS[V80_DEFINITION][1],
            },
            "release_manifest": {
                "path": "releases/2026-07-21-open-seed-v80/manifest.json",
                "bytes": V80_PINS[V80_MANIFEST][0],
                "sha256": V80_PINS[V80_MANIFEST][1],
            },
            "release_tree_sha256": V80_TREE_SHA256,
            "v80_selected_input_count": V80_INPUT_COUNT,
            "new_source_paths_selected_by_v80": False,
            **duplicate_witness,
        },
        "kragujevac_prior_discovery_reconciliation": {
            "prior_snapshot": {
                "path": str(DISCOVERY_SNAPSHOT.relative_to(ROOT)),
                "bytes": DISCOVERY_SNAPSHOT_PIN[0],
                "sha256": DISCOVERY_SNAPSHOT_PIN[1],
            },
            "prior_candidate": "Kragujevac State Data Center Block 2",
            "prior_decision": "not_promoted_planned_only",
            "new_project_stable_key": (
                "curated:serbia-state-data-center-kragujevac:"
                "modules-3-4-commissioned-2026"
            ),
            "identity_with_prior_block_2_asserted": False,
            "new_scope": "modules_3_and_4_recently_operational_expansion",
            "stable_key_collision_with_v80": 0,
            "evidence_key_collision_with_v80": 0,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v80_mutated": False,
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
        "all_rights_reserved_source_count": 9,
        "cc_by_nc_nd_3_0_serbia_source_count": 1,
        "serbia_license": {
            "name": (
                "Creative Commons Attribution-NonCommercial-NoDerivatives 3.0 "
                "Serbia (CC BY-NC-ND 3.0 RS)"
            ),
            "displayed_terms": "Ауторство-Некомерцијално-Без прерада 3.0 Србија",
            "url": "https://creativecommons.org/licenses/by-nc-nd/3.0/rs/",
            "attribution": (
                "Office for IT and eGovernment, Republic of Serbia; ite.gov.rs"
            ),
            "raw_redistributed": False,
        },
        "artifact_is_hash_and_fact_only": True,
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
        "candidate_dispositions": {
            "seed_eligible": 5,
            "review_only_or_already_covered": review_count,
        },
    }
    return {
        "README.md": readme.encode(),
        "candidate-assessment.json": _canonical(
            _candidate_assessments(recorded_at)
        ),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _file_tree(rows: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_bytes((json.dumps(rows, indent=2, sort_keys=True) + "\n").encode())


def _write_source_stage(
    stage: Path,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    for name in SOURCE_FILENAMES:
        output = stage / name
        output.write_bytes(_canonical(documents[name]))
        output.chmod(0o444)
        _fsync_regular(output)
    _fsync_directory(stage)


def _write_artifact_stage(
    stage: Path,
    recorded_at: str,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    payloads = _artifact_documents(recorded_at, documents)
    for name in CONTENT_FILES:
        output = stage / name
        output.write_bytes(payloads[name])
        output.chmod(0o444)
        _fsync_regular(output)
    rows = [
        {
            "bytes": (stage / name).stat().st_size,
            "path": name,
            "sha256": _sha256(stage / name),
        }
        for name in CONTENT_FILES
    ]
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
        "indexed_official_page_assertions": 3,
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
    sidecar.write_text(
        f"{_sha256(manifest_path)}  manifest.json\n",
        encoding="utf-8",
    )
    sidecar.chmod(0o444)
    _fsync_regular(sidecar)
    stage.chmod(0o555)
    _fsync_directory(stage)


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def _validate_sources(paths: Mapping[str, Path]) -> list[dict[str, Any]]:
    expected = expected_source_documents()
    if set(paths) != set(SOURCE_FILENAMES):
        raise OfficialCeeGapError("source path inventory differs")
    for name in SOURCE_FILENAMES:
        source = paths[name]
        if source.is_symlink() or not source.is_file():
            raise OfficialCeeGapError(f"curated source is absent: {source}")
        if source.read_bytes() != _canonical(expected[name]):
            raise OfficialCeeGapError(f"curated source differs: {name}")
        if stat.S_IMODE(source.stat().st_mode) != 0o444:
            raise OfficialCeeGapError(f"curated source mode differs: {name}")
    documents = list(expected.values())
    if any(
        document[entity]["coordinates"] is not None
        or document[entity]["geometry"] is not None
        for document in documents
        for entity in ("campus", "project")
    ):
        raise OfficialCeeGapError("source invented coordinates or geometry")
    if [document["lifecycle"][0]["value"] for document in documents] != [
        "under_construction",
        "under_construction",
        "under_construction",
        "shell",
        "operational",
    ]:
        raise OfficialCeeGapError("lifecycle boundary differs")
    if sum(len(document["evidence"]) for document in documents) != 10:
        raise OfficialCeeGapError("evidence boundary differs")
    if sum(len(document["operating_models"]) for document in documents) != 2:
        raise OfficialCeeGapError("operating-model boundary differs")
    if sum(len(document["workloads"]) for document in documents) != 2:
        raise OfficialCeeGapError("workload boundary differs")
    if sum(len(document["capacities"]) for document in documents) != 1:
        raise OfficialCeeGapError("capacity boundary differs")
    capacity = documents[4]["capacities"][0]
    if (
        capacity["metric"] != "generation_nameplate_mw"
        or capacity["stage"] != "operational"
        or capacity["base"] != 0.3
    ):
        raise OfficialCeeGapError("Serbia generation capacity differs")
    if documents[0]["workloads"][0]["value"] != "general_cloud":
        raise OfficialCeeGapError("Microsoft design-purpose workload differs")
    if documents[4]["workloads"][0]["value"] != "ai_specialized_unspecified":
        raise OfficialCeeGapError("Serbia active-GPU workload differs")
    joined = json.dumps(documents, ensure_ascii=False)
    for text in ("19.2", "12.5", "25 MW", "8", "14"):
        if text not in joined:
            raise OfficialCeeGapError(f"ambiguous narrative amount absent: {text}")
    if "curated:data-in-scale-spata-campus:phase-1-current-build" not in joined:
        raise OfficialCeeGapError("Spata resolution candidate is absent")
    stable_keys = {
        document[entity]["stable_key"]
        for document in documents
        for entity in ("campus", "project")
    }
    if "curated:data-in-scale-spata-campus:phase-1-current-build" in stable_keys:
        raise OfficialCeeGapError("Spata resolution candidate became identity")
    return _source_records(expected)


def _validate_source_collisions() -> None:
    planned = expected_source_documents()
    stable_keys = {
        document[entity]["stable_key"]
        for document in planned.values()
        for entity in ("campus", "project")
    }
    evidence_keys = {
        evidence["key"]
        for document in planned.values()
        for evidence in document["evidence"]
    }
    if len(stable_keys) != 10 or len(evidence_keys) != 10:
        raise OfficialCeeGapError("planned source keys are not unique")
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
        other_stable = {
            record.get("stable_key")
            for key in ("campus", "project")
            if isinstance((record := document.get(key)), dict)
        }
        other_evidence = {
            row.get("key")
            for row in document.get("evidence", [])
            if isinstance(row, dict)
        }
        stable_overlap = sorted(stable_keys & other_stable)
        evidence_overlap = sorted(evidence_keys & other_evidence)
        if stable_overlap or evidence_overlap:
            collisions[source.name] = {
                "stable_keys": stable_overlap,
                "evidence_keys": evidence_overlap,
            }
    if collisions:
        raise OfficialCeeGapError(f"curated source collision: {collisions!r}")


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split()).rstrip("/")


def _selected_v80_documents() -> list[Mapping[str, Any]]:
    definition = json.loads(V80_DEFINITION.read_text(encoding="utf-8"))
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


def _v80_duplicate_witness(
    planned: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    documents = list((planned or expected_source_documents()).values())
    planned_stable = {
        document[entity]["stable_key"]
        for document in documents
        for entity in ("campus", "project")
    }
    planned_evidence = {
        row["key"] for document in documents for row in document["evidence"]
    }
    existing_stable: set[str] = set()
    existing_evidence: set[str] = set()
    existing_names: set[str] = set()
    existing_urls: set[str] = set()
    for document in _selected_v80_documents():
        existing_names.update(
            _normalize_text(text)
            for text in _strings_for_key(document, "alias")
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
    with V80_ENTITIES.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("name"):
                existing_names.add(_normalize_text(row["name"]))
            if row.get("source_url"):
                existing_urls.add(_normalize_text(row["source_url"]))
    alias_overlap = sorted(
        alias
        for alias in PLANNED_ALIASES
        if _normalize_text(alias) in existing_names
    )
    url_overlap = sorted(
        url for url in PLANNED_URLS if _normalize_text(url) in existing_urls
    )
    stable_overlap = sorted(planned_stable & existing_stable)
    evidence_overlap = sorted(planned_evidence & existing_evidence)
    if alias_overlap or url_overlap or stable_overlap or evidence_overlap:
        raise OfficialCeeGapError(
            "planned candidates duplicate accepted v80: "
            f"aliases={alias_overlap!r}, urls={url_overlap!r}, "
            f"stable={stable_overlap!r}, evidence={evidence_overlap!r}"
        )
    return {
        "planned_identity_aliases_checked": len(PLANNED_ALIASES),
        "planned_source_urls_checked": len(PLANNED_URLS),
        "planned_stable_keys_checked": len(planned_stable),
        "planned_evidence_keys_checked": len(planned_evidence),
        "v80_name_or_alias_exact_normalized_collisions": 0,
        "v80_source_url_exact_normalized_collisions": 0,
        "v80_stable_key_collisions": 0,
        "v80_evidence_key_collisions": 0,
    }


def _validate_discovery_reconciliation() -> None:
    _pin(DISCOVERY_SNAPSHOT, DISCOVERY_SNAPSHOT_PIN)
    _pin(DISCOVERY_MANIFEST, DISCOVERY_MANIFEST_PIN)
    snapshot = json.loads(DISCOVERY_SNAPSHOT.read_text(encoding="utf-8"))
    matches = [
        row
        for row in snapshot.get("country_screen", [])
        if isinstance(row, dict)
        and row.get("candidate") == "Kragujevac State Data Center Block 2"
    ]
    if len(matches) != 1:
        raise OfficialCeeGapError("prior Kragujevac review witness differs")
    row = matches[0]
    if row.get("decision") != "not_promoted" or "remained planned" not in row.get(
        "basis", ""
    ):
        raise OfficialCeeGapError("prior Kragujevac disposition differs")


def _validate_v80_nonmutation() -> None:
    for source, pin in V80_PINS.items():
        _pin(source, pin)
    if tree_digest(V80_RELEASE) != V80_TREE_SHA256:
        raise OfficialCeeGapError("accepted v80 release tree differs")
    manifest = json.loads(V80_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("recorded_at") != V80_RECORDED_AT:
        raise OfficialCeeGapError("accepted v80 recording instant differs")
    definition = json.loads(V80_DEFINITION.read_text(encoding="utf-8"))
    if len(definition.get("curated_inputs", [])) != V80_INPUT_COUNT:
        raise OfficialCeeGapError("accepted v80 input count differs")
    selected = {row["path"] for row in definition["curated_inputs"]}
    planned_paths = {f"sources/{name}" for name in SOURCE_FILENAMES}
    if selected & planned_paths:
        raise OfficialCeeGapError("v80 unexpectedly selects a new source path")
    witness = _v80_duplicate_witness()
    if (
        witness["v80_stable_key_collisions"] != 0
        or witness["v80_evidence_key_collisions"] != 0
    ):
        raise OfficialCeeGapError("v80 key absence witness differs")
    _validate_discovery_reconciliation()


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory() as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
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
            "entities": 10,
            "entity_snapshots": 10,
            "evidence": 10,
            "lifecycle_observations": 5,
            "operating_model_observations": 2,
            "workload_observations": 2,
            "capacity_estimates": 1,
        }
        if counts != expected:
            raise OfficialCeeGapError(f"offline import counts differ: {counts!r}")
        capacity = tuple(
            connection.execute(
                "SELECT e.stable_key, c.metric, c.stage, c.unit, c.base "
                "FROM capacity_estimates AS c JOIN entities AS e "
                "ON e.id=c.entity_id"
            ).fetchone()
        )
        expected_capacity = (
            "curated:serbia-state-data-center-kragujevac:"
            "modules-3-4-commissioned-2026",
            "generation_nameplate_mw",
            "operational",
            "MW",
            0.3,
        )
        if capacity != expected_capacity:
            raise OfficialCeeGapError(f"offline capacity row differs: {capacity!r}")
        return counts


def validate_artifact(
    path: Path = ARTIFACT,
    *,
    source_paths: Mapping[str, Path] | None = None,
    require_live: bool = True,
    wall_clock: datetime | None = None,
) -> dict[str, Any]:
    _validate_v80_nonmutation()
    _validate_capture_directory(_capture_directory())
    paths = source_paths or _source_paths(SOURCES_ROOT)
    source_records = _validate_sources(paths)
    if path.is_symlink() or not path.is_dir():
        raise OfficialCeeGapError("artifact must be an ordinary directory")
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise OfficialCeeGapError("artifact closed file set differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries.values()):
        raise OfficialCeeGapError("artifact contains a non-ordinary file")
    if stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise OfficialCeeGapError("artifact directory mode differs")
    if any(
        stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries.values()
    ):
        raise OfficialCeeGapError("artifact file mode differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest):
        raise OfficialCeeGapError("manifest JSON is not canonical")
    if (
        manifest.get("artifact_id") != ARTIFACT_ID
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or manifest.get("candidate_assessments") != 24
        or manifest.get("curated_source_records") != 5
        or manifest.get("seed_eligible_source_records") != 5
        or manifest.get("review_only_candidates") != 19
        or manifest.get("successful_http_200_body_captures") != 7
        or manifest.get("indexed_official_page_assertions") != 3
        or manifest.get("regional_completeness_claimed") is not False
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise OfficialCeeGapError("manifest contract differs")
    if [row["path"] for row in manifest["files"]] != list(CONTENT_FILES):
        raise OfficialCeeGapError("manifest file order differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (
            row["bytes"],
            row["sha256"],
        ):
            raise OfficialCeeGapError(f"manifest file pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise OfficialCeeGapError("manifest checksum differs")
    expected = _artifact_documents(
        manifest["recorded_at"],
        expected_source_documents(),
    )
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected[name]:
            raise OfficialCeeGapError(f"artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records:
        raise OfficialCeeGapError("artifact source pins differ")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise OfficialCeeGapError("validation wall clock lacks timezone")
    if require_live:
        if now.astimezone(UTC) < target:
            raise OfficialCeeGapError("artifact recorded_at is not live")
        _assert_final_ctimes((*paths.values(), path), target)
    for capture in CAPTURES.values():
        if _instant(capture["retrieved_at"]) > target:
            raise OfficialCeeGapError("capture retrieval post-dates recorded_at")
    return manifest


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError as error:
        raise OfficialCeeGapError(
            f"active publication lock exists: {PUBLICATION_LOCK}"
        ) from error
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


def _all_stage_paths(
    source_stage: Path,
    artifact_stage: Path,
) -> tuple[Path, ...]:
    return (
        source_stage,
        *sorted(source_stage.iterdir(), key=lambda item: item.name),
        artifact_stage,
        *sorted(artifact_stage.iterdir(), key=lambda item: item.name),
    )


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
        raise OfficialCeeGapError("recorded_at must be future before staging")
    source_stage = Path(
        tempfile.mkdtemp(prefix=".official-builds-cee-gap.", dir=SOURCES_ROOT)
    )
    artifact_stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT)
    )
    source_stage_identity = _identity(source_stage, directory=True)
    artifact_identity = _identity(artifact_stage, directory=True)
    try:
        documents = expected_source_documents()
        _write_source_stage(source_stage, documents)
        _write_artifact_stage(artifact_stage, recorded_at, documents)
        source_paths = _source_paths(source_stage)
        _validate_sources(source_paths)
        _offline_import(source_paths, recorded_at)
        validate_artifact(
            artifact_stage,
            source_paths=source_paths,
            require_live=False,
            wall_clock=datetime.now(UTC),
        )
        finals = tuple(SOURCES_ROOT / name for name in SOURCE_FILENAMES) + (ARTIFACT,)
        _require_finals_absent(finals, "staging")
        _assert_stage_precedes_target(
            _all_stage_paths(source_stage, artifact_stage),
            target,
        )
        if datetime.now(UTC) >= target:
            raise OfficialCeeGapError(
                "private staging did not finish before recorded_at"
            )
        return _PreparedPublication(
            recorded_at=recorded_at,
            target=target,
            source_stage=source_stage,
            source_stage_identity=source_stage_identity,
            source_identities={
                name: _identity(source_stage / name, directory=False)
                for name in SOURCE_FILENAMES
            },
            artifact_stage=artifact_stage,
            artifact_identity=artifact_identity,
            artifact_member_identities={
                name: _identity(artifact_stage / name, directory=False)
                for name in CLOSED_FILES
            },
        )
    except BaseException as primary_error:
        try:
            if artifact_stage.exists():
                members = {
                    entry.name: _identity(entry, directory=False)
                    for entry in artifact_stage.iterdir()
                }
                _discard_owned_directory(
                    artifact_stage,
                    artifact_identity,
                    members,
                )
            if source_stage.exists():
                members = {
                    entry.name: _identity(entry, directory=False)
                    for entry in source_stage.iterdir()
                }
                _discard_owned_directory(
                    source_stage,
                    source_stage_identity,
                    members,
                )
        except Exception as cleanup_error:
            primary_error.add_note(f"private-stage cleanup failed: {cleanup_error}")
        raise


def _publish(prepared: _PreparedPublication) -> None:
    final_sources = {name: SOURCES_ROOT / name for name in SOURCE_FILENAMES}
    finals = tuple(final_sources.values()) + (ARTIFACT,)
    _require_finals_absent(finals, "pre-wait")
    _wait_until(prepared.target.timestamp())
    _require_finals_absent(finals, "publication")
    _assert_stage_precedes_target(
        _all_stage_paths(prepared.source_stage, prepared.artifact_stage),
        prepared.target,
    )
    promoted: list[tuple[Path, Path, tuple[int, int], bool]] = []
    try:
        for name in SOURCE_FILENAMES:
            stage = prepared.source_stage / name
            final = final_sources[name]
            identity = prepared.source_identities[name]
            _promote_noreplace(stage, final)
            promoted.append((stage, final, identity, False))
            if not _has_identity(final, identity, directory=False):
                raise OfficialCeeGapError(
                    f"source identity changed on promotion: {name}"
                )
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        promoted.append(
            (prepared.artifact_stage, ARTIFACT, prepared.artifact_identity, True)
        )
        if not _has_identity(ARTIFACT, prepared.artifact_identity, directory=True):
            raise OfficialCeeGapError("artifact identity changed on promotion")
        _assert_final_ctimes(finals, prepared.target)
    except BaseException as primary_error:
        try:
            _rollback_promotions(promoted)
        except Exception as rollback_error:
            primary_error.add_note(
                f"identity-safe rollback failed: {rollback_error}"
            )
        raise


def _cleanup_prepared(prepared: _PreparedPublication) -> None:
    if prepared.artifact_stage.exists():
        _discard_owned_directory(
            prepared.artifact_stage,
            prepared.artifact_identity,
            prepared.artifact_member_identities,
        )
    if prepared.source_stage.exists():
        _discard_owned_directory(
            prepared.source_stage,
            prepared.source_stage_identity,
            prepared.source_identities,
        )


def _move_capture_to_trash() -> None:
    if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
        raise OfficialCeeGapError("both capture origin and Trash destination exist")
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH))


def _default_recorded_at() -> str:
    target = math.ceil(time.time() + 25.0)
    return datetime.fromtimestamp(target, UTC).isoformat().replace("+00:00", "Z")


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    """Publish five source records and the bounded CEE gap assessment."""

    target_text = recorded_at or _default_recorded_at()
    finals = tuple(SOURCES_ROOT / name for name in SOURCE_FILENAMES) + (ARTIFACT,)
    _require_finals_absent(finals, "initial")
    _validate_source_collisions()
    _validate_v80_nonmutation()
    _validate_capture_directory(_capture_directory())
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
            _discard_owned_directory(
                prepared.source_stage,
                prepared.source_stage_identity,
                prepared.source_identities,
            )
    _validate_capture_directory(resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH))
    _validate_v80_nonmutation()
    manifest = validate_artifact(ARTIFACT)
    source_records = _validate_sources(_source_paths(SOURCES_ROOT))
    return {
        "artifact_id": ARTIFACT_ID,
        "recorded_at": manifest["recorded_at"],
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "manifest_logical_tree_sha256": manifest["tree_sha256"],
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "source_records": source_records,
        "counts": {
            "candidates": 24,
            "source_records": 5,
            "seed_eligible": 5,
            "review_only": 19,
            "evidence": 10,
            "entities": 10,
            "entity_snapshots": 10,
            "lifecycle": 5,
            "operating_models": 2,
            "workloads": 2,
            "capacities": 1,
            "generation_nameplate_capacities": 1,
            "data_center_load_capacities": 0,
            "coordinates": 0,
            "geometry": 0,
            "placements": 0,
            "energy_consumption": 0,
            "pue": 0,
        },
        "capture_directory": str(CAPTURE_TRASH),
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "v80_tree_sha256": V80_TREE_SHA256,
        "open_seed_successor_created": False,
        "release_integration": "none",
    }


def main() -> int:
    print(json.dumps(build(), indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
