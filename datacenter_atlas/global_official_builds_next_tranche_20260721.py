"""Publish the next bounded official-build assessment.

The carrier is independent of open-seed and downstream publication.  It stages
every source and artifact byte before the declared recording instant, waits for
that instant, and performs no-replace promotion with identity-safe rollback.
"""

from __future__ import annotations

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

from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from . import global_official_builds_six_candidate_20260721 as publication
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "global-official-builds-next-tranche-2026-07-21-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".global-official-builds-next-tranche-20260721.lock"
CAPTURE_ORIGIN = Path("/private/tmp/dc-global-official-next-20260721.umOnmx")
CAPTURE_TRASH = Path(
    "/Users/kian/.Trash/dc-global-official-next-20260721.umOnmx"
)
CAPTURE_TREE_SHA256 = (
    "e4fa9ed85eddf1e03faadc3750b29c3c9eabc2178eb75d2ceca810e7b4e05aaa"
)
CAPTURE_FILE_COUNT = 43

V73_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v73.json"
V73_RELEASE = ROOT / "releases/2026-07-21-open-seed-v73"
V73_MANIFEST = V73_RELEASE / "manifest.json"
V73_ENTITIES = V73_RELEASE / "entities.csv"
V73_PINS = {
    V73_DEFINITION: (
        88_004,
        "cf8a4cfb8861ab732cdb9e72a01cbdd01d0e435102c47fd6d92bc30ebf11f97d",
    ),
    V73_MANIFEST: (
        12_814,
        "229c572759ab493448b788946a0c8a61ff6995d0ab505bea2af08860a19e204d",
    ),
    V73_ENTITIES: (
        887_459,
        "8c50475f1a58a7f7623a4eef2706be3f63bca0175a5fe4fffecdd548442944e7",
    ),
}
V73_TREE_SHA256 = (
    "692583b86324b746fd6edf0ec2dc5101efa86ce0f08e04831e0d471e767a6394"
)
V73_INPUT_COUNT = 397

SOURCE_FILENAMES = (
    "curated-official-2026-07-21-omnia-pecem-current-build.json",
    "curated-official-2026-07-21-nxdata3-bucharest-source-scoped.json",
    "curated-official-2026-07-21-cirion-rio2-current-build.json",
    "curated-official-2026-07-21-cote-divoire-national-dc-vitib-current-build.json",
)

CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

OfficialTrancheError = publication.OfficialBuildsError
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


CAPTURE_BODIES: dict[str, dict[str, Any]] = {
    "aligned_sp04": {
        "filename": "aligned_sp04.body",
        "url": "https://aligneddc.com/press-release/odata-announces-new-data-center-in-sao-paulo-brazil/",
        "retrieved_at": "2026-07-21T15:37:46Z",
        "bytes": 221_117,
        "sha256": "f966d126f047ddcb3437125a4c44f3f34280438b02f746c95832ed677598c4be",
        "content_type": "text/html; charset=UTF-8",
    },
    "cirion_rio2_2024": {
        "filename": "cirion_rio2_2024.body",
        "url": "https://press.ciriontechnologies.com/en/2024/08/01/cirion-ampliara-data-center-rio-de-janeiro/",
        "retrieved_at": "2026-07-21T15:37:46Z",
        "bytes": 83_822,
        "sha256": "04dea52d6a97f70199e49ab1ee2b54eb557f43d82a40f3e382707ccfb8652d7d",
        "content_type": "text/html; charset=UTF-8",
    },
    "cirion_rio2_2026": {
        "filename": "cirion_rio2_2026.body",
        "url": "https://press.ciriontechnologies.com/en/2026/03/25/data-center-day-south-america-center-digital-geopolitics/",
        "retrieved_at": "2026-07-21T15:37:46Z",
        "bytes": 84_839,
        "sha256": "264abcc35d9ea48baf1219d8120a08905cbd984d27a491caae1ce3c7a2f42944",
        "content_type": "text/html; charset=UTF-8",
    },
    "cirion_rio2_pdf": {
        "filename": "cirion_rio2_pdf.body",
        "url": "https://lp.ciriontechnologies.com/hubfs/Other%20Files/Downloadable%20Assets/data-sheet-web/cirion-technologies-data-center-spec-sheet-rio2-eng.pdf",
        "retrieved_at": "2026-07-21T15:37:46Z",
        "bytes": 1_406_365,
        "sha256": "c8dd76384a603603c83b7b5594c73359052cd1ee3f10bd2a11e720b9ea903d64",
        "content_type": "application/pdf",
    },
    "civ_gov_earlier": {
        "filename": "civ_gov_earlier.body",
        "url": "https://www.telecom.gouv.ci/new/index.php/actualite/73",
        "retrieved_at": "2026-07-21T15:37:48Z",
        "bytes": 111_532,
        "sha256": "ae456e26d27b03caf37722ad16ae2f2507afa772b607bb0e4cb17aa072ad9995",
        "content_type": "text/html; charset=UTF-8",
    },
    "civ_gov_progress": {
        "filename": "civ_gov_progress.body",
        "url": "https://www.telecom.gouv.ci/new/index.php/actualite/152",
        "retrieved_at": "2026-07-21T15:37:48Z",
        "bytes": 111_622,
        "sha256": "3cceefd1d901ad9e320f1505484b879d34f782a31388f9f542a83060a052e10a",
        "content_type": "text/html; charset=UTF-8",
    },
    "nxdata3_home": {
        "filename": "nxdata3_home.body",
        "url": "https://nxdata3.com/",
        "retrieved_at": "2026-07-21T15:37:48Z",
        "bytes": 158_707,
        "sha256": "fbf89b64ce114cf817eb2d95190bc45a33a990e0af39d7810486045089854080",
        "content_type": "text/html; charset=UTF-8",
    },
    "omnia_local_contractors": {
        "filename": "omnia_local_contractors.body",
        "url": "https://omniadc.com/pt/omnia-prioriza-empresas-cearenses-na-implantacao-do-data-center-do-pecem-e-fortalece-a-economia-local/",
        "retrieved_at": "2026-07-21T15:41:52Z",
        "bytes": 90_599,
        "sha256": "bfe24a462d9031ff37ed30263d130714734a5fe35566e8b1b9f93fc5c24c28fe",
        "content_type": "text/html; charset=UTF-8",
    },
    "omnia_renewables": {
        "filename": "omnia_renewables.body",
        "url": "https://omniadc.com/pt/omnia-e-casa-dos-ventos-firmam-maior-contrato-de-autoproducao-de-energia-renovavel-da-america-latina-para-data-centers/",
        "retrieved_at": "2026-07-21T15:37:47Z",
        "bytes": 91_977,
        "sha256": "f8f6dc3f8c42f958fda3b397efcab5cc7f4dec880be1d07d2ba88a6477b7ab3f",
        "content_type": "text/html; charset=UTF-8",
    },
    "patria_pecem_cffi": {
        "filename": "patria_pecem_cffi.body",
        "url": "https://ir.patria.com/static-files/3aa8254f-dc35-4724-aae5-d88e4827dfee",
        "retrieved_at": "2026-07-21T15:41:02Z",
        "bytes": 341_529,
        "sha256": "38c6303b9e228e4540e34ed24073fcb7c7b8c261d9f3b734ffd4baf0897ba03c",
        "content_type": "application/pdf",
        "capture_method": "curl_cffi_chrome136_browser_compatible_tls",
    },
    "syntys_qdata": {
        "filename": "syntys_qdata.body",
        "url": "https://syntys.com/newsroom/ooredoo-group-announces-syntys-acquisition-of-q-data-facilities-in-qatar",
        "retrieved_at": "2026-07-21T15:37:46Z",
        "bytes": 244_018,
        "sha256": "e713433f8492d3de0057e95dc8665d5e84aa246f7fef739e7f02c13fe3de6bfe",
        "content_type": "text/html",
    },
    "tiktok_pecem": {
        "filename": "tiktok_pecem.body",
        "url": "https://newsroom.tiktok.com/tiktok-anuncia-seu-primeiro-data-center-na-america-latina-com-investimento-superior-a-200-billhoes?lang=pt-BR",
        "retrieved_at": "2026-07-21T15:37:47Z",
        "bytes": 83_778,
        "sha256": "e27f59c46a17d2c4768db5b06b6db0637f22df2ea5ba61622a897cdea0cb6f79",
        "content_type": "text/html; charset=utf-8",
    },
    "wingu_tanzania": {
        "filename": "wingu_tanzania.body",
        "url": "https://www.wingu.africa/latest-news/wingu-unveils-next-generation-carrier-neutral-data-centre-expansion",
        "retrieved_at": "2026-07-21T15:37:46Z",
        "bytes": 77_045,
        "sha256": "90da15cbf85c1935b97e47665dbe3fa4abcbaa48759b9cdef2bdb2dbcdbc32f2",
        "content_type": "text/html; charset=utf-8",
    },
}


def _evidence(
    capture_id: str,
    *,
    key: str,
    kind: str,
    title: str,
    publisher: str,
    source_family: str,
    published_at: str | None,
    excerpt: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    capture = CAPTURE_BODIES[capture_id]
    capture_method = capture.get("capture_method", "curl_location_compressed")
    common = {
        "content_hash_scope": (
            f"SHA-256 of the exact {capture['bytes']}-byte content-decoded "
            "official response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture_id,
        "capture_method": capture_method,
        "http_status": 200,
        "content_type": capture["content_type"],
        "request_credentials_supplied": False,
        "rights_scope": (
            "Compact factual extraction from all-rights-reserved official bytes; "
            "the response body and publisher media are not redistributed."
        ),
        "imagery_guardrail": (
            "No publisher image, satellite image, aerial image, computer vision, "
            "or analyst geolocation contributes to this record."
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
        "published_at": published_at,
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
    confidence: float,
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
        "confidence": confidence,
    }


def _lifecycle(
    value: str,
    evidence_key: str,
    as_of_date: str,
    *,
    confidence: float = 0.99,
) -> dict[str, Any]:
    return {
        "entity": "project",
        "value": value,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": "authoritative_physical_status_update",
        "confidence": confidence,
    }


def _operating_model(
    evidence_key: str,
    as_of_date: str,
    *,
    confidence: float,
) -> dict[str, Any]:
    return {
        "entity": "project",
        "value": "colocation",
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": "company_disclosure",
        "confidence": confidence,
    }


def _capacity(
    *,
    metric: str,
    stage: str,
    unit: str,
    value: float,
    evidence_key: str,
    as_of_date: str,
    confidence: float,
    notes: str,
) -> dict[str, Any]:
    return {
        "entity": "project",
        "metric": metric,
        "stage": stage,
        "unit": unit,
        "low": value,
        "base": value,
        "high": value,
        "method": "reported",
        "confidence": confidence,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "target_date": None,
        "notes": notes,
    }


def _omnia_source() -> dict[str, Any]:
    works_key = "brazil-omnia-pecem-local-contractors-captured-2026-07-21"
    patria_key = "brazil-patria-q1-2026-pecem-construction-captured-2026-07-21"
    tiktok_key = "brazil-tiktok-pecem-project-announcement-captured-2026-07-21"
    renewable_key = "brazil-omnia-pecem-renewable-contract-captured-2026-07-21"
    omnia = "OMNIA Data Centers"
    evidence = [
        _evidence(
            "omnia_local_contractors",
            key=works_key,
            kind="company_disclosure",
            title=(
                "OMNIA prioriza empresas cearenses na implantação do Data Center "
                "do Pecém e fortalece a economia local"
            ),
            publisher=omnia,
            source_family="omnia_pecem_updates",
            published_at="2026-02-25",
            excerpt=(
                "OMNIA reports phase-one local contracts for prefabricated concrete "
                "fabrication and assembly and for vegetation clearing and earthworks."
            ),
            metadata={
                "source_dateline": "2026-02-23",
                "status_wording_as_reported": (
                    "Phase 1 implementation includes contracted prefabricated-concrete "
                    "fabrication and assembly, vegetation clearing, and earthworks; "
                    "the source says works are advancing."
                ),
                "physical_status_scope": (
                    "The contractor scopes establish physical site work by 2026-02-23. "
                    "No completion percentage, foundations, shell, MEP, commissioning, "
                    "energization, or operation is inferred."
                ),
                "contractors_as_reported": [
                    "T&A Construção Pré-Fabricada S/A",
                    "SS&B Construtora LTDA",
                ],
                "role_scope": (
                    "Contractor names are retained as source metadata rather than "
                    "normalized project roles because the record's primary role scope "
                    "is OMNIA, TikTok, and the facility identity."
                ),
            },
        ),
        _evidence(
            "patria_pecem_cffi",
            key=patria_key,
            kind="company_disclosure",
            title="Patria Investments Q1 2026 Earnings Call Prepared Remarks",
            publisher="Patria Investments Limited",
            source_family="patria_investor_relations",
            published_at="2026-05-07",
            excerpt=(
                "Patria says the data-center project announced with ByteDance was "
                "advancing through its construction phase in Q1 2026."
            ),
            metadata={
                "selected_pdf_page": 3,
                "pdf_pages": 6,
                "physical_status_scope": (
                    "The dated issuer wording supports a generic under_construction "
                    "observation as of 2026-05-07. It does not establish a finer stage, "
                    "percentage, completion, commissioning, or operation."
                ),
                "identity_bridge": (
                    "The TikTok and OMNIA pages identify the Pecém project as the "
                    "TikTok/ByteDance partnership with OMNIA; the Patria wording is not "
                    "used to create a second unidentified project."
                ),
                "capture_guardrail": (
                    "Two command-line attempts failed before response headers. The "
                    "evidence body is the later credential-free browser-compatible TLS "
                    "200 response, not either failed attempt."
                ),
            },
        ),
        _evidence(
            "tiktok_pecem",
            key=tiktok_key,
            kind="company_disclosure",
            title=(
                "TikTok anuncia seu primeiro data center na América Latina com "
                "investimento superior a R$ 200 bilhões"
            ),
            publisher="TikTok",
            source_family="tiktok_newsroom",
            published_at="2025-12-04",
            excerpt=(
                "TikTok identifies its first Latin American data center at the Pecém "
                "industrial and port complex and names OMNIA and Casa dos Ventos as "
                "initial-phase partners."
            ),
            metadata={
                "location_as_reported": (
                    "Complexo Industrial e Portuário do Pecém (CIPP), Ceará, Brazil"
                ),
                "identity_scope": (
                    "The announcement binds TikTok, OMNIA, and Pecém identity. Its "
                    "future-tense construction language is not itself treated as a "
                    "physical start; later physical evidence supplies lifecycle."
                ),
                "role_scope": (
                    "TikTok is retained as user and OMNIA as developer/operator. Casa "
                    "dos Ventos and ByteDance remain named partner context rather than "
                    "invented owner, tenant, utility, or contractor roles."
                ),
                "schedule_guardrail": (
                    "The 2027 initial-operation forecast creates no completion, "
                    "commissioning, or operational observation."
                ),
            },
        ),
        _evidence(
            "omnia_renewables",
            key=renewable_key,
            kind="company_disclosure",
            title=(
                "OMNIA e Casa dos Ventos firmam maior contrato de autoprodução de "
                "energia renovável da América Latina para data centers"
            ),
            publisher=omnia,
            source_family="omnia_pecem_updates",
            published_at="2026-05-18",
            excerpt=(
                "OMNIA describes itself as developer, builder, investor, and intended "
                "operator of the Pecém data center and reports a renewable-energy "
                "autoproduction agreement."
            ),
            metadata={
                "reported_data_center_capacity_mw_untyped": 200,
                "reported_renewable_supply_mw_average": 300,
                "capacity_guardrail": (
                    "The 200 MW value is not normalized because this captured page does "
                    "not type it as critical IT, gross facility, grid connection, or "
                    "generation. The 300 MW value is contracted renewable supply, not "
                    "data-center load or consumption, and creates no capacity row."
                ),
                "unresolved_1_2_gw_claim_guardrail": (
                    "A separately surfaced 1.2 GW scope is not safely resolved to this "
                    "phase in the captured primary bytes and remains review-only. It is "
                    "not normalized, summed, or substituted for 200 MW or 300 MW."
                ),
                "energy_guardrail": (
                    "Renewable sourcing and autoproduction language creates no current "
                    "load, measured consumption, annual energy, generation, PUE, "
                    "commissioning, or operation observation."
                ),
            },
        ),
    ]
    campus_key = "curated:omnia-pecem-data-center-campus"
    project_key = f"{campus_key}:initial-tiktok-bytedance-build"
    roles = {
        "developer": [omnia],
        "contractor": [omnia],
        "operator": [omnia],
        "user": ["TikTok"],
    }
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="OMNIA Pecém Data Center Campus",
            country="Brazil",
            address="Complexo Industrial e Portuário do Pecém, Ceará, Brazil",
            roles=roles,
            evidence_key=tiktok_key,
            as_of_date="2026-05-07",
            confidence=0.99,
        ),
        "project": _entity(
            stable_key=project_key,
            name="OMNIA Pecém Initial TikTok ByteDance Build",
            country="Brazil",
            address="Complexo Industrial e Portuário do Pecém, Ceará, Brazil",
            roles=roles,
            evidence_key=tiktok_key,
            as_of_date="2026-05-07",
            confidence=0.99,
        ),
        "lifecycle": [_lifecycle("under_construction", patria_key, "2026-05-07")],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _nxdata_source() -> dict[str, Any]:
    evidence_key = "romania-nxdata3-current-project-page-captured-2026-07-21"
    publisher = "NXDATA SRL"
    evidence = [
        _evidence(
            "nxdata3_home",
            key=evidence_key,
            kind="company_disclosure",
            title="NXDATA-3 Bucharest Data Center",
            publisher=publisher,
            source_family="nxdata3_project_pages",
            published_at="2025-06-26",
            excerpt=(
                "NXDATA's current project page reports 5 MW total electrical capacity, "
                "3 MW for customer IT equipment, design annual PUE about 1.3, and a "
                "carrier-neutral colocation facility at 38 Bucharest Ring Road."
            ),
            metadata={
                "official_page_modified_at": "2026-05-05T08:54:21Z",
                "aliases_as_reported": ["NXDATA-3", "NX-3", "BUH3"],
                "address_as_reported": (
                    "38 Bucharest Ring Road, Tunari, Ilfov, Romania"
                ),
                "total_electrical_capacity_mw_as_reported": 5,
                "customer_it_capacity_mw_as_reported": 3,
                "design_annual_pue_as_reported": 1.3,
                "data_halls_as_reported": 4,
                "up_to_it_mw_per_hall_as_reported": 1,
                "nonadditive_hall_guardrail": (
                    "The four up-to-1 MW hall values describe allocation ceilings "
                    "inside the reported 3 MW facility IT total. They are not summed to "
                    "4 MW or added to the 3 MW or 5 MW rows."
                ),
                "lifecycle_guardrail": (
                    "The captured page describes a future facility and forecast Q4 2026 "
                    "opening, but does not textually establish physical works. No "
                    "lifecycle observation is emitted."
                ),
                "manual_capture_follow_up": {
                    "source_url": (
                        "https://www.linkedin.com/posts/nxdata_nxdata-nxdata3-"
                        "datacenter-activity-7467582788171616256-fwVo"
                    ),
                    "publisher_body_captured": False,
                    "used_for_normalized_claims": False,
                    "required_to_unlock_lifecycle": True,
                },
                "imagery_specific_guardrail": (
                    "Project renderings and construction-update imagery do not establish "
                    "status without a governed image-review record."
                ),
            },
        )
    ]
    campus_key = "curated:nxdata3-bucharest-ring-road-campus"
    project_key = f"{campus_key}:nxdata3-buh3"
    roles = {"developer": [publisher], "operator": [publisher]}
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="NXDATA-3 Bucharest Ring Road Campus",
            country="Romania",
            address="38 Bucharest Ring Road, Tunari, Ilfov, Romania",
            roles=roles,
            evidence_key=evidence_key,
            as_of_date="2026-05-05",
            confidence=0.99,
        ),
        "project": _entity(
            stable_key=project_key,
            name="NXDATA-3 / NX-3 / BUH3",
            country="Romania",
            address="38 Bucharest Ring Road, Tunari, Ilfov, Romania",
            roles=roles,
            evidence_key=evidence_key,
            as_of_date="2026-05-05",
            confidence=0.99,
        ),
        "lifecycle": [],
        "operating_models": [
            _operating_model(evidence_key, "2026-05-05", confidence=0.99)
        ],
        "workloads": [],
        "capacities": [
            _capacity(
                metric="gross_facility_mw",
                stage="planned",
                unit="MW",
                value=5,
                evidence_key=evidence_key,
                as_of_date="2026-05-05",
                confidence=0.99,
                notes=(
                    "Reported total electrical capacity retained at planned stage; not "
                    "grid connection, generation, current demand, consumption, or IT."
                ),
            ),
            _capacity(
                metric="critical_it_mw",
                stage="planned",
                unit="MW",
                value=3,
                evidence_key=evidence_key,
                as_of_date="2026-05-05",
                confidence=0.99,
                notes=(
                    "Reported capacity dedicated to customer IT&C equipment, retained "
                    "at planned stage and not summed with hall ceilings."
                ),
            ),
            _capacity(
                metric="pue",
                stage="design",
                unit="ratio",
                value=1.3,
                evidence_key=evidence_key,
                as_of_date="2026-05-05",
                confidence=0.98,
                notes=(
                    "Approximate design annual PUE; not measured, accepted, commissioned, "
                    "or operating performance."
                ),
            ),
        ],
    }


def _cirion_source() -> dict[str, Any]:
    status_key = "brazil-cirion-rio2-march-2026-build-captured-2026-07-21"
    land_key = "brazil-cirion-rio2-august-2024-land-captured-2026-07-21"
    sheet_key = "brazil-cirion-rio2-datasheet-captured-2026-07-21"
    publisher = "Cirion Technologies"
    evidence = [
        _evidence(
            "cirion_rio2_2026",
            key=status_key,
            kind="company_disclosure",
            title=(
                "International Data Center Day: South America at the center of the "
                "new digital geopolitics"
            ),
            publisher=publisher,
            source_family="cirion_press_releases",
            published_at="2026-03-25",
            excerpt=(
                "Cirion says RIO2 is a new Rio de Janeiro site being built in phases "
                "according to demand and separately labels it under development."
            ),
            metadata={
                "status_wording_as_reported": (
                    "A new 80 MW RIO2 site is being built in phases according to demand."
                ),
                "physical_status_scope": (
                    "The explicit being-built wording supports generic "
                    "under_construction as of 2026-03-25. It does not establish a finer "
                    "stage, completion percentage, commissioning, or operation."
                ),
                "reported_site_mw_untyped": 80,
                "capacity_guardrail": (
                    "The 80 MW site statement conflicts with other first-party values "
                    "and is not explicitly typed. No normalized capacity row is emitted."
                ),
                "operating_model_scope": (
                    "Cirion describes its carrier-neutral platform and colocation service."
                ),
            },
        ),
        _evidence(
            "cirion_rio2_2024",
            key=land_key,
            kind="company_disclosure",
            title="Cirion to expand its data center presence in Rio de Janeiro",
            publisher=publisher,
            source_family="cirion_press_releases",
            published_at="2024-08-01",
            excerpt=(
                "Cirion's land-acquisition announcement described a future up-to-60 MW "
                "carrier-neutral RIO2 adjacent to RIO1."
            ),
            metadata={
                "reported_future_mw_untyped": 60,
                "status_guardrail": (
                    "Land acquisition and once-constructed wording did not establish a "
                    "physical start in 2024; lifecycle comes only from the 2026 update."
                ),
                "capacity_guardrail": (
                    "The up-to-60 MW value conflicts with later 80 MW, 81 MW IT, and "
                    "60 MW power claims and creates no normalized capacity row."
                ),
            },
        ),
        _evidence(
            "cirion_rio2_pdf",
            key=sheet_key,
            kind="company_disclosure",
            title="RIO2 Rio de Janeiro - Cirion Data Center Technical Specifications",
            publisher=publisher,
            source_family="cirion_data_sheets",
            published_at=None,
            excerpt=(
                "Cirion's RIO2 sheet gives the address Avenida Pedro II 283 and "
                "internally presents 81 MW IT capacity alongside 60 MW power."
            ),
            metadata={
                "publication_period_as_reported_by_audit": "September 2025",
                "exact_publication_day_verified": False,
                "selected_pdf_pages": [1, 2],
                "address_as_reported": (
                    "Avenida Pedro II, 283, São Cristóvão, Rio de Janeiro, Brasil"
                ),
                "it_capacity_mw_as_reported": 81,
                "power_mw_as_reported": 60,
                "capacity_conflict": True,
                "capacity_guardrail": (
                    "The sheet's 81 MW IT value exceeds its 60 MW power value and "
                    "conflicts with the 2024 up-to-60 MW and 2026 80 MW site claims. "
                    "Every RIO2 capacity claim is quarantined; none is normalized."
                ),
                "schedule_guardrail": (
                    "The 2026 launch schedule is a forecast and creates no completion, "
                    "commissioning, energization, or operational observation."
                ),
            },
        ),
    ]
    campus_key = "curated:cirion-rio-campus-rio-de-janeiro"
    project_key = f"{campus_key}:rio2-current-build"
    roles = {"developer": [publisher], "operator": [publisher]}
    address = "Avenida Pedro II, 283, São Cristóvão, Rio de Janeiro, Brazil"
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="Cirion Rio de Janeiro Campus",
            country="Brazil",
            address=address,
            roles=roles,
            evidence_key=sheet_key,
            as_of_date="2026-03-25",
            confidence=0.99,
        ),
        "project": _entity(
            stable_key=project_key,
            name="Cirion RIO2 Current Build",
            country="Brazil",
            address=address,
            roles=roles,
            evidence_key=sheet_key,
            as_of_date="2026-03-25",
            confidence=0.99,
        ),
        "lifecycle": [_lifecycle("under_construction", status_key, "2026-03-25")],
        "operating_models": [
            _operating_model(status_key, "2026-03-25", confidence=0.99)
        ],
        "workloads": [],
        "capacities": [],
    }


def _cote_divoire_source() -> dict[str, Any]:
    progress_key = "cote-divoire-national-dc-vitib-progress-captured-2026-07-21"
    earlier_key = "cote-divoire-national-dc-anoumambo-earlier-captured-2026-07-21"
    publisher = (
        "Ministère de la Transition Numérique et de la Digitalisation de Côte d’Ivoire"
    )
    evidence = [
        _evidence(
            "civ_gov_progress",
            key=progress_key,
            kind="government_record",
            title=(
                "Le Ministre Kalil Konate visite le chantier du Data center national "
                "au VITIB de Grand-Bassam, plus de 20 % de taux d'exécution"
            ),
            publisher=publisher,
            source_family="cote_divoire_digital_ministry_updates",
            published_at="2025-12-09",
            excerpt=(
                "The digital ministry reports a visit to the National Data Center "
                "worksite at VITIB Grand-Bassam and execution above 20 percent."
            ),
            metadata={
                "status_wording_as_reported": (
                    "The minister visited the chantier at VITIB Grand-Bassam; execution "
                    "exceeded 20 percent and works were evolving."
                ),
                "physical_status_scope": (
                    "The dated worksite update supports generic under_construction as of "
                    "2025-12-09. The percentage is not converted to a finer physical "
                    "stage, and earthworks or pile-foundation detail is not inferred "
                    "from publisher imagery."
                ),
                "state_role_scope": (
                    "The State is the disclosed beneficiary and data custodian context; "
                    "no legal owner or operator role is inferred."
                ),
                "project_participants_as_reported": ["CYBASTION", "BNETD", "APL"],
                "participant_scope": (
                    "CYBASTION is retained as project lead/contractor. BNETD and APL "
                    "remain technical-participant metadata because the page does not "
                    "safely type their contractual roles."
                ),
                "capacity_guardrail": (
                    "The update reports no load, grid capacity, generation, energy, PUE, "
                    "rack count, or current consumption."
                ),
            },
        ),
        _evidence(
            "civ_gov_earlier",
            key=earlier_key,
            kind="government_record",
            title=(
                "Kalil Konaté sur le site de construction du premier Data Center "
                "national à Anoumambo"
            ),
            publisher=publisher,
            source_family="cote_divoire_digital_ministry_updates",
            published_at="2024-05-16",
            excerpt=(
                "An earlier ministry update placed the National Data Center worksite at "
                "Anoumambo and named Cybastion and PORTEO."
            ),
            metadata={
                "relocation_or_rescope_unresolved": True,
                "identity_guardrail": (
                    "The later official source places the project at VITIB Grand-Bassam. "
                    "The relationship between the Anoumambo and VITIB scopes is not "
                    "resolved as relocation, replacement, or redesign."
                ),
                "legacy_values_excluded": {
                    "it_capacity_mw": 1,
                    "rack_count": 800,
                    "area_square_metres": 20_000,
                    "reason": (
                        "Earlier Anoumambo values are not carried into the later VITIB "
                        "record until relocation and rescope are independently resolved."
                    ),
                },
                "status_scope": (
                    "The 2024 visit is historical context; the normalized lifecycle "
                    "observation is tied to the later 2025 VITIB source."
                ),
            },
        ),
    ]
    campus_key = "curated:cote-divoire-national-data-center-vitib"
    project_key = f"{campus_key}:grand-bassam-current-build"
    roles = {"contractor": ["CYBASTION"]}
    address = "VITIB, Grand-Bassam, Côte d’Ivoire"
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="Côte d’Ivoire National Data Center at VITIB",
            country="Côte d’Ivoire",
            address=address,
            roles=roles,
            evidence_key=progress_key,
            as_of_date="2025-12-09",
            confidence=0.99,
        ),
        "project": _entity(
            stable_key=project_key,
            name="Côte d’Ivoire National Data Center Grand-Bassam Current Build",
            country="Côte d’Ivoire",
            address=address,
            roles=roles,
            evidence_key=progress_key,
            as_of_date="2025-12-09",
            confidence=0.99,
        ),
        "lifecycle": [
            _lifecycle("under_construction", progress_key, "2025-12-09")
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    """Return the four exact schema-1.1 source documents."""

    builders = (_omnia_source, _nxdata_source, _cirion_source, _cote_divoire_source)
    return {
        name: builder() for name, builder in zip(SOURCE_FILENAMES, builders, strict=True)
    }


SOURCE_DISPOSITIONS = {
    SOURCE_FILENAMES[0]: "seed_eligible_fresh_official_physical_update",
    SOURCE_FILENAMES[1]: "identity_capacity_only_no_governed_physical_update",
    SOURCE_FILENAMES[2]: "seed_eligible_fresh_official_physical_update",
    SOURCE_FILENAMES[3]: "seed_eligible_source_scoped_official_physical_update",
}


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
                "disposition": SOURCE_DISPOSITIONS[name],
                "seed_eligible": name != SOURCE_FILENAMES[1],
                "seeded": False,
            }
        )
    return records


def _candidate_assessments(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-seven-candidate-official-build-assessment-v1",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "candidate_count": 7,
        "seed_eligible_count": 3,
        "identity_capacity_only_count": 1,
        "review_only_count": 2,
        "historical_operational_count": 1,
        "candidates": [
            {
                "candidate_id": "omnia-tiktok-pecem",
                "country": "Brazil",
                "decision": "seed_eligible_fresh_official_physical_update",
                "source_record_created": True,
                "seed_eligible": True,
                "basis": (
                    "Direct OMNIA contractor scopes and Patria's later ByteDance-project "
                    "construction-phase statement establish physical work."
                ),
                "capacity_disposition": {
                    "200_mw": "untyped_not_normalized",
                    "300_mw": "renewable_supply_not_load",
                    "1_2_gw": "unresolved_review_only",
                },
            },
            {
                "candidate_id": "odata-sp04-phase-2",
                "country": "Brazil",
                "decision": "review_only_manual_publisher_capture_required",
                "source_record_created": False,
                "seed_eligible": False,
                "captured_context": {
                    "source_url": CAPTURE_BODIES["aligned_sp04"]["url"],
                    "body_bytes": CAPTURE_BODIES["aligned_sp04"]["bytes"],
                    "body_sha256": CAPTURE_BODIES["aligned_sp04"]["sha256"],
                    "scope": (
                        "The captured 2025 Aligned page identifies the 48 MW DC SP04 "
                        "facility but does not establish 2026 phase-two physical work."
                    ),
                },
                "manual_capture_follow_up": {
                    "source_url": (
                        "https://pt.linkedin.com/posts/odata_odata-dcsp04-datacenters-"
                        "activity-7473377620018077696-WDvR"
                    ),
                    "publisher_body_captured": False,
                    "automated_linkedin_capture_performed": False,
                    "claims_not_normalized": [
                        "site mobilization",
                        "equipment receipt",
                        "seven generators",
                        "24 MW phase-two value",
                        "48 MW campus IT destination",
                    ],
                    "required_to_unlock_seed_eligibility": True,
                },
            },
            {
                "candidate_id": "nxdata3-buh3",
                "country": "Romania",
                "decision": "identity_capacity_only_no_governed_physical_update",
                "source_record_created": True,
                "seed_eligible": False,
                "basis": (
                    "The direct NXDATA page supports identity, address, colocation, "
                    "5 MW total electrical, 3 MW IT, and design PUE about 1.3, but no "
                    "textual physical-work observation."
                ),
            },
            {
                "candidate_id": "cirion-rio2",
                "country": "Brazil",
                "decision": "seed_eligible_capacity_quarantined",
                "source_record_created": True,
                "seed_eligible": True,
                "basis": (
                    "Cirion says RIO2 is being built in phases as of 2026-03-25."
                ),
                "capacity_disposition": (
                    "All 60 MW, 80 MW, 81 MW IT, and 60 MW power claims are quarantined "
                    "because the first-party claims conflict, including internally."
                ),
            },
            {
                "candidate_id": "cote-divoire-national-dc-vitib-grand-bassam",
                "country": "Côte d’Ivoire",
                "decision": "seed_eligible_source_scoped_official_physical_update",
                "source_record_created": True,
                "seed_eligible": True,
                "basis": (
                    "The ministry reports a VITIB Grand-Bassam worksite above 20 percent "
                    "execution on 2025-12-09."
                ),
                "capacity_disposition": (
                    "No current capacity is emitted; earlier Anoumambo 1 MW, 800-rack, "
                    "and 20,000 m² values remain excluded pending relocation/rescope "
                    "resolution."
                ),
            },
            {
                "candidate_id": "syntys-qdata-qatar-two-facility-aggregate",
                "country": "Qatar",
                "decision": "review_only_aggregate_unallocated",
                "source_record_created": False,
                "seed_eligible": False,
                "basis": (
                    "The direct Syntys page reports 5 MW live and 7.5 MW under "
                    "development across two unnamed Qatar Free Zone facilities, with no "
                    "facility or phase allocation."
                ),
                "captured_source": {
                    "source_url": CAPTURE_BODIES["syntys_qdata"]["url"],
                    "body_bytes": CAPTURE_BODIES["syntys_qdata"]["bytes"],
                    "body_sha256": CAPTURE_BODIES["syntys_qdata"]["sha256"],
                },
            },
            {
                "candidate_id": "wingu-tanzania-phase-2",
                "country": "Tanzania",
                "decision": "historical_operational_not_current_construction",
                "source_record_created": False,
                "seed_eligible": False,
                "basis": (
                    "Wingu says phase two was successfully launched on 2025-03-18; the "
                    "source supports historical completion/operation, not a current build."
                ),
                "captured_source": {
                    "source_url": CAPTURE_BODIES["wingu_tanzania"]["url"],
                    "body_bytes": CAPTURE_BODIES["wingu_tanzania"]["bytes"],
                    "body_sha256": CAPTURE_BODIES["wingu_tanzania"]["sha256"],
                },
            },
        ],
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    captured = [
        {
            "capture_id": capture_id,
            "requested_url": spec["url"],
            "effective_url": spec["url"],
            "retrieved_at": spec["retrieved_at"],
            "http_status": 200,
            "content_type": spec["content_type"],
            "body": {
                "bytes": spec["bytes"],
                "sha256": spec["sha256"],
                "retained_in_artifact": False,
                "moved_to_trash": True,
            },
            "capture_method": spec.get(
                "capture_method", "curl_location_compressed"
            ),
            "request_credentials_supplied": False,
        }
        for capture_id, spec in sorted(CAPTURE_BODIES.items())
    ]
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "capture_protocol": (
            "Credential-free public HTTP GETs with a transparent research User-Agent. "
            "Successful response bodies, headers, and response facts were retained in a "
            "private capture directory. One Patria response used a browser-compatible "
            "TLS client after two curl attempts and wget timed out before headers."
        ),
        "successful_body_captures": len(CAPTURE_BODIES),
        "selected_source_evidence_bodies": 10,
        "assessment_only_bodies": 3,
        "failed_patria_transport_attempts_retained": 3,
        "linkedin_publisher_bodies_captured": 0,
        "request_credentials_supplied": False,
        "raw_capture_redistributed": False,
        "capture_file_count": CAPTURE_FILE_COUNT,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "controlled_captures": captured,
        "manual_capture_follow_ups": [
            {
                "candidate": "ODATA SP04 phase 2",
                "url": (
                    "https://pt.linkedin.com/posts/odata_odata-dcsp04-datacenters-"
                    "activity-7473377620018077696-WDvR"
                ),
                "automated_capture_performed": False,
                "used_for_normalized_claims": False,
            },
            {
                "candidate": "NXDATA-3 construction update",
                "url": (
                    "https://www.linkedin.com/posts/nxdata_nxdata-nxdata3-datacenter-"
                    "activity-7467582788171616256-fwVo"
                ),
                "automated_capture_performed": False,
                "used_for_normalized_claims": False,
            },
        ],
    }


def _artifact_documents(
    recorded_at: str,
    source_documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    source_records = _source_records(source_documents)
    readme = f"""# Global official-build next-tranche assessment

This immutable artifact records seven bounded candidate dispositions researched on 2026-07-21. Three direct-source candidates pass the physical-construction boundary: OMNIA/TikTok Pecém, Cirion RIO2, and the Côte d’Ivoire National Data Center at VITIB Grand-Bassam. Their lifecycle rows are dated observations, not timeless current-status claims.

NXDATA-3 contributes source-scoped identity, address, carrier-neutral colocation, 5 MW total electrical capacity, 3 MW planned IT capacity, and design PUE about 1.3. It contributes no lifecycle row because the directly captured project page does not textually establish physical work; publisher imagery and an uncaptured LinkedIn update are insufficient. ODATA SP04 phase two likewise remains review-only until its official LinkedIn post is captured through a governed manual path. No LinkedIn page was fetched automatically.

Pecém's 200 MW remains untyped, its 300 MW renewable contract is supply rather than data-center load, and a separately surfaced 1.2 GW scope remains unresolved and review-only. NXDATA hall ceilings are not summed. Every RIO2 capacity claim is quarantined because first-party sources conflict: up to 60 MW, 80 MW site, and a sheet that internally pairs 81 MW IT with 60 MW power. Côte d’Ivoire contributes no current capacity, and earlier Anoumambo values are not carried into the later VITIB scope.

Syntys/Q Data remains an unallocated two-facility Qatar aggregate: 5 MW live and 7.5 MW under development cannot be split into map entities. Wingu Tanzania phase two is historical/operational because Wingu says it launched on 2025-03-18, not current construction.

No source has coordinates or geometry. No publisher imagery, satellite imagery, aerial imagery, computer vision, or analyst geolocation contributes to identity, status, capacity, type, or roles.

All source and artifact bytes were completed in private staging before `{recorded_at}`. Final paths remained absent until that instant and were promoted without replacement as one rollback-protected set. The accepted v73 seed and every downstream artifact remain unchanged. Raw all-rights-reserved captures are not redistributed; the complete 43-file capture directory was moved intact to the recoverable Trash path in the rights inventory.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "source_records": source_records,
        "totals": {
            "candidate_assessments": 7,
            "source_records": 4,
            "seed_eligible_source_records": 3,
            "identity_capacity_only_source_records": 1,
            "review_only_candidates": 2,
            "historical_operational_candidates": 1,
            "distinct_campuses": 4,
            "projects": 4,
            "entity_snapshots": 8,
            "unique_evidence_records": 10,
            "lifecycle_observations": 3,
            "operating_model_observations": 2,
            "workload_observations": 0,
            "capacity_estimates": 3,
            "coordinates_present": 0,
            "geometry_present": 0,
        },
        "frozen_v73_non_mutation_witness": {
            "definition": {
                "path": "sources/open-seed-2026-07-21-v73.json",
                "bytes": V73_PINS[V73_DEFINITION][0],
                "sha256": V73_PINS[V73_DEFINITION][1],
            },
            "release_manifest": {
                "path": "releases/2026-07-21-open-seed-v73/manifest.json",
                "bytes": V73_PINS[V73_MANIFEST][0],
                "sha256": V73_PINS[V73_MANIFEST][1],
            },
            "release_tree_sha256": V73_TREE_SHA256,
            "v73_selected_input_count": V73_INPUT_COUNT,
            "new_source_paths_selected_by_v73": False,
            "new_stable_key_collisions": 0,
            "new_evidence_key_collisions": 0,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v73_mutated": False,
            "release_integration": "none",
            "construction_timeline_integration": "none",
            "federation_integration": "none",
            "identity_integration": "none",
            "coordinate_integration": "none",
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
            "source_file_mode": "0644",
            "artifact_directory_mode": "0555",
            "artifact_file_mode": "0444",
        },
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-disposition-v3",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "source_rights": (
            "Captured publisher response bodies are treated as all-rights-reserved; "
            "no redistribution license was relied on."
        ),
        "artifact_is_hash_only": True,
        "raw_capture_redistributed": False,
        "raw_response_bodies_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "response_facts_retained_in_artifact": False,
        "publisher_media_retained_in_artifact": False,
        "request_credentials_supplied": False,
        "automated_linkedin_capture_performed": False,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "temporary_capture_file_count": CAPTURE_FILE_COUNT,
        "temporary_capture_tree_sha256": CAPTURE_TREE_SHA256,
        "deletion_performed": False,
        "candidate_dispositions": {
            "seed_eligible": 3,
            "identity_capacity_only": 1,
            "review_only": 2,
            "historical_operational": 1,
        },
    }
    return {
        "README.md": readme.encode(),
        "candidate-assessment.json": _canonical(_candidate_assessments(recorded_at)),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _file_tree(rows: Sequence[Mapping[str, Any]]) -> str:
    payload = (json.dumps(rows, indent=2, sort_keys=True) + "\n").encode()
    return _sha256_bytes(payload)


def _write_source_stage(
    stage: Path,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    for name in SOURCE_FILENAMES:
        output = stage / name
        output.write_bytes(_canonical(documents[name]))
        output.chmod(0o644)
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
        "candidate_assessments": 7,
        "curated_source_records": 4,
        "seed_eligible_source_records": 3,
        "identity_capacity_only_source_records": 1,
        "review_only_candidates": 2,
        "historical_operational_candidates": 1,
        "successful_raw_captures": len(CAPTURE_BODIES),
        "raw_capture_redistributed": False,
        "raw_capture_directory_moved_intact_to_trash": True,
        "automated_linkedin_capture_performed": False,
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
        raise OfficialTrancheError("source path inventory differs")
    for name in SOURCE_FILENAMES:
        source = paths[name]
        if source.is_symlink() or not source.is_file():
            raise OfficialTrancheError(f"curated source is absent: {source}")
        raw = source.read_bytes()
        if raw != _canonical(expected[name]):
            raise OfficialTrancheError(f"curated source differs: {name}")
        if stat.S_IMODE(source.stat().st_mode) != 0o644:
            raise OfficialTrancheError(f"curated source mode differs: {name}")
        document = json.loads(raw)
        for entity in ("campus", "project"):
            if document[entity]["coordinates"] is not None:
                raise OfficialTrancheError(f"source invented coordinates: {name}")
            if document[entity]["geometry"] is not None:
                raise OfficialTrancheError(f"source invented geometry: {name}")
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
    if len(stable_keys) != 8 or len(evidence_keys) != 10:
        raise OfficialTrancheError("planned source keys are not unique")
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
        raise OfficialTrancheError(f"curated source collision: {collisions!r}")


def _validate_v73_nonmutation() -> None:
    for source, pin in V73_PINS.items():
        _pin(source, pin)
    if tree_digest(V73_RELEASE) != V73_TREE_SHA256:
        raise OfficialTrancheError("accepted v73 release tree differs")
    definition = json.loads(V73_DEFINITION.read_text(encoding="utf-8"))
    if len(definition.get("curated_inputs", [])) != V73_INPUT_COUNT:
        raise OfficialTrancheError("accepted v73 input count differs")
    selected = {row["path"] for row in definition["curated_inputs"]}
    planned_paths = {f"sources/{name}" for name in SOURCE_FILENAMES}
    if selected & planned_paths:
        raise OfficialTrancheError("v73 unexpectedly selects a new source path")
    entities_text = V73_ENTITIES.read_text(encoding="utf-8")
    for document in expected_source_documents().values():
        for entity in ("campus", "project"):
            if document[entity]["stable_key"] in entities_text:
                raise OfficialTrancheError("new source stable key collides with v73")


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise OfficialTrancheError(f"capture directory is absent or unsafe: {directory}")
    entries = list(directory.iterdir())
    if len(entries) != CAPTURE_FILE_COUNT:
        raise OfficialTrancheError("capture directory file count differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise OfficialTrancheError("capture directory contains a non-ordinary file")
    if tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise OfficialTrancheError("capture directory tree differs")
    for spec in CAPTURE_BODIES.values():
        _pin(directory / spec["filename"], (spec["bytes"], spec["sha256"]))


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
            "entities": 8,
            "entity_snapshots": 8,
            "evidence": 10,
            "lifecycle_observations": 3,
            "operating_model_observations": 2,
            "workload_observations": 0,
            "capacity_estimates": 3,
        }
        if counts != expected:
            raise OfficialTrancheError(f"offline import counts differ: {counts!r}")
        capacities = [
            tuple(row)
            for row in connection.execute(
                "SELECT metric, stage, unit, base FROM capacity_estimates "
                "ORDER BY metric, stage"
            )
        ]
        if capacities != [
            ("critical_it_mw", "planned", "MW", 3.0),
            ("gross_facility_mw", "planned", "MW", 5.0),
            ("pue", "design", "ratio", 1.3),
        ]:
            raise OfficialTrancheError(
                f"offline capacity rows differ: {capacities!r}"
            )
        return counts


def validate_artifact(
    path: Path = ARTIFACT,
    *,
    source_paths: Mapping[str, Path] | None = None,
    require_live: bool = True,
    wall_clock: datetime | None = None,
) -> dict[str, Any]:
    paths = source_paths or _source_paths(SOURCES_ROOT)
    source_records = _validate_sources(paths)
    if path.is_symlink() or not path.is_dir():
        raise OfficialTrancheError("artifact must be an ordinary directory")
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise OfficialTrancheError("artifact closed file set differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries.values()):
        raise OfficialTrancheError("artifact contains a non-ordinary file")
    if stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise OfficialTrancheError("artifact directory mode differs")
    if any(stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries.values()):
        raise OfficialTrancheError("artifact file mode differs")
    for name in CONTENT_FILES[1:]:
        raw = entries[name].read_bytes()
        if raw != _canonical(json.loads(raw)):
            raise OfficialTrancheError(f"artifact JSON is not canonical: {name}")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest):
        raise OfficialTrancheError("manifest JSON is not canonical")
    if (
        manifest.get("artifact_id") != ARTIFACT_ID
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or manifest.get("candidate_assessments") != 7
        or manifest.get("curated_source_records") != 4
        or manifest.get("seed_eligible_source_records") != 3
        or manifest.get("identity_capacity_only_source_records") != 1
        or manifest.get("review_only_candidates") != 2
        or manifest.get("historical_operational_candidates") != 1
        or manifest.get("automated_linkedin_capture_performed") is not False
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise OfficialTrancheError("manifest contract differs")
    if [row["path"] for row in manifest["files"]] != list(CONTENT_FILES):
        raise OfficialTrancheError("manifest file order differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (row["bytes"], row["sha256"]):
            raise OfficialTrancheError(f"manifest file pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise OfficialTrancheError("manifest checksum differs")
    expected = _artifact_documents(manifest["recorded_at"], expected_source_documents())
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected[name]:
            raise OfficialTrancheError(f"artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records:
        raise OfficialTrancheError("artifact source pins differ")
    assessment = json.loads(
        entries["candidate-assessment.json"].read_text(encoding="utf-8")
    )
    rows = {row["candidate_id"]: row for row in assessment["candidates"]}
    for candidate_id in (
        "odata-sp04-phase-2",
        "syntys-qdata-qatar-two-facility-aggregate",
        "wingu-tanzania-phase-2",
    ):
        if rows[candidate_id]["source_record_created"]:
            raise OfficialTrancheError(f"non-source candidate promoted: {candidate_id}")
    if rows["nxdata3-buh3"]["seed_eligible"]:
        raise OfficialTrancheError("NXDATA lifecycle boundary differs")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise OfficialTrancheError("validation wall clock lacks timezone")
    if require_live:
        if now.astimezone(UTC) < target:
            raise OfficialTrancheError("artifact recorded_at is not live")
        _assert_final_ctimes((*paths.values(), path), target)
    for document in expected_source_documents().values():
        for evidence in document["evidence"]:
            if _instant(evidence["retrieved_at"]) > target:
                raise OfficialTrancheError("evidence retrieval post-dates recorded_at")
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
        raise OfficialTrancheError(
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


def _all_stage_paths(source_stage: Path, artifact_stage: Path) -> tuple[Path, ...]:
    source_members = sorted(source_stage.iterdir(), key=lambda item: item.name)
    artifact_members = sorted(artifact_stage.iterdir(), key=lambda item: item.name)
    return (source_stage, *source_members, artifact_stage, *artifact_members)


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
        raise OfficialTrancheError("recorded_at must be future before staging")
    source_stage = Path(
        tempfile.mkdtemp(prefix=".official-builds-next.", dir=SOURCES_ROOT)
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
            raise OfficialTrancheError("private staging did not finish before recorded_at")
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
                raise OfficialTrancheError(
                    f"source identity changed on promotion: {name}"
                )
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        promoted.append(
            (
                prepared.artifact_stage,
                ARTIFACT,
                prepared.artifact_identity,
                True,
            )
        )
        if not _has_identity(ARTIFACT, prepared.artifact_identity, directory=True):
            raise OfficialTrancheError("artifact identity changed on promotion")
        _assert_final_ctimes(finals, prepared.target)
    except BaseException as primary_error:
        try:
            _rollback_promotions(promoted)
        except Exception as rollback_error:
            primary_error.add_note(f"identity-safe rollback failed: {rollback_error}")
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
        raise OfficialTrancheError("both capture origin and Trash destination exist")
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(CAPTURE_TRASH)


def _default_recorded_at() -> str:
    target = math.ceil(time.time() + 20.0)
    return datetime.fromtimestamp(target, UTC).isoformat().replace("+00:00", "Z")


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    """Publish four source records and the seven-candidate assessment."""

    target_text = recorded_at or _default_recorded_at()
    finals = tuple(SOURCES_ROOT / name for name in SOURCE_FILENAMES) + (ARTIFACT,)
    _require_finals_absent(finals, "initial")
    _validate_source_collisions()
    _validate_v73_nonmutation()
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
            _discard_owned_directory(
                prepared.source_stage,
                prepared.source_stage_identity,
                prepared.source_identities,
            )
    _validate_capture_directory(CAPTURE_TRASH)
    _validate_v73_nonmutation()
    manifest = validate_artifact(ARTIFACT)
    source_records = _validate_sources(_source_paths(SOURCES_ROOT))
    return {
        "artifact_id": ARTIFACT_ID,
        "recorded_at": manifest["recorded_at"],
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "source_records": source_records,
        "counts": {
            "candidates": 7,
            "source_records": 4,
            "seed_eligible": 3,
            "identity_capacity_only": 1,
            "review_only": 2,
            "historical_operational": 1,
            "evidence": 10,
            "entities": 8,
            "lifecycle": 3,
            "operating_models": 2,
            "workloads": 0,
            "capacities": 3,
            "coordinates": 0,
            "geometry": 0,
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
