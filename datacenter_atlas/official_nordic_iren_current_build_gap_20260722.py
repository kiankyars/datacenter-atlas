"""Publish four governed official current-build source records.

The tranche covers Nscale Kvandal, NorthC Aalsmeer phase 2, IREN Childress
Horizons 1-4, and Bitzero Namsskogan power-infrastructure foundations. Raw
all-rights-reserved response bytes remain private and are represented in the
public artifact only by exact pins and compact factual extracts. No open-seed
or downstream integration is performed.
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
from . import global_official_builds_six_candidate_20260721 as publication
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "official-nordic-iren-current-build-gap-2026-07-22-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".official-nordic-iren-current-build-gap.lock"

CAPTURE_ORIGIN = Path("/private/tmp/dc-nordic-iren-20260722.ekekNb")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-nordic-iren-20260722.ekekNb")
CAPTURE_FILE_COUNT = 34
CAPTURE_TOTAL_BYTES = 31_806_253
CAPTURE_TREE_SHA256 = "b64ecffa4ca2324e738dd85e8d2171d6e1fe0facc0b0540a955661f6942640fc"
RETRIEVED_AT = "2026-07-22T03:29:10Z"

V93_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v93.json"
V93_RELEASE = ROOT / "releases/2026-07-21-open-seed-v93"
V93_MANIFEST = V93_RELEASE / "manifest.json"
V93_ENTITIES = V93_RELEASE / "entities.csv"
V93_SOURCE_INPUTS = V93_RELEASE / "source_inputs.json"
V93_PINS = {
    V93_DEFINITION: (
        110_743,
        "cf8ed21cd0816f457fa2cede36fbf1bf012d62ed61d03a5e3213de9946394e9c",
    ),
    V93_MANIFEST: (
        16_832,
        "9a5b39004ab1a4c7994ad653d5d9603572b4a47a3c502ea222eeae38d32fa05c",
    ),
    V93_ENTITIES: (
        1_029_791,
        "f690d838165ced6822b891f5099adea82db46fba97e53dbcb462328b5af6628b",
    ),
    V93_SOURCE_INPUTS: (
        414_095,
        "81cf558da4aef80bdc957116ceda84cd565960b6471db0ada95cddd02e0f483e",
    ),
}
V93_TREE_SHA256 = "71c531ffa7f8383e2ae553a71abe15e940e8d6251acccbf17556bc492df78f0d"
V93_INPUT_COUNT = 488
V93_ENTITY_COUNT = 994

KNOWN_V94_SOURCE_FILENAMES = (
    "curated-official-2026-07-22-beale-pima-project-blue-bobcat-site-preparation-v2.json",
    "curated-official-2026-07-22-beale-tulsa-project-clydesdale-initial-phase-current-build-v2.json",
    "curated-official-2026-07-22-cyrusone-fra5-hanau-halls-2-3-current-build.json",
    "curated-official-2026-07-22-cyrusone-wood-dale-phase-1-current-build.json",
    "curated-official-2026-07-22-merlin-bilbao-arasur-building-2-current-build.json",
    "curated-official-2026-07-22-merlin-bilbao-arasur-building-3-current-build.json",
    "curated-official-2026-07-22-bitdeer-wenatchee-ai-conversion-current-build.json",
    "curated-official-2026-07-22-bitdeer-massillon-reconstruction-current-build.json",
    "curated-official-2026-07-22-hut8-river-bend-current-build.json",
    "curated-official-2026-07-22-goodman-databank-lax01-enrichment.json",
)

_canonical = publication._canonical
_sha256 = publication._sha256
_sha256_bytes = publication._sha256_bytes
_instant = publication._instant
_pin = publication._pin
_fsync_regular = publication._fsync_regular
_fsync_directory = publication._fsync_directory
_promote_noreplace = publication._promote_noreplace
_identity = publication._identity


def _has_identity(path: Path, identity: tuple[int, int], *, directory: bool) -> bool:
    try:
        metadata = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return False
    correct_type = (
        stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    )
    return correct_type and (metadata.st_dev, metadata.st_ino) == identity


CAPTURE_FILE_PINS: Mapping[str, tuple[int, str]] = {
    "bitzero.headers": (
        1_728,
        "1fd1f1b7fb19c9f2461afbbddb60bc6865590c3ce43651fc311894da8b0a35f4",
    ),
    "bitzero.html": (
        39_346,
        "402e9589e0cf82c663020a5d98352545e6b1ca582e5e835cd5f8f55ccd4be852",
    ),
    "bitzero_april.headers": (
        1_728,
        "38c0541b3a1cdfe0eb962087e7513a8eb9da46e564c6096b5915c151be3e745d",
    ),
    "bitzero_april.html": (
        38_558,
        "8b4c0d6d53bd312874c55bef90d10c4c7d998ec8cb4f664ff4e201f2133f964d",
    ),
    "iren_10q.headers": (
        570,
        "d727edb6bc988eab54364a5ad5cbe7b7acab2e09e59c3fc81ccca2365cad7f85",
    ),
    "iren_10q.htm": (
        1_959_789,
        "3d59f51f926263a28997dc3647d97dd9312febcb7a4611e809bcfc498dcafd27",
    ),
    "iren_10q_index.headers": (
        270,
        "3b0d1500c4ba74aa2492d850865b077439747622329b2cce148fe438e210674a",
    ),
    "iren_10q_index.json": (
        17_944,
        "659c365c5db4720496c0aee414df15f30c2f6cbacc95374b8c0c330740b35760",
    ),
    "iren_10q_submission.headers": (
        638,
        "00387b18e2c967e39895383620c5d080d82375d533094af0926edfd433229f00",
    ),
    "iren_10q_submission.txt": (
        23_700_666,
        "a81a5b2d28b552cbbea12477cd9f26ccdb6c31adbdd72fc5479cc384db1916af",
    ),
    "iren_exhibit.headers": (
        613,
        "b3d0a21f4f161167858a293bd4cf98d5d133749e96e97f5e209c6eb0df123018",
    ),
    "iren_exhibit.htm": (
        35_251,
        "7c46f52102333e8afde1b8e68580930544eac0eebb913a24eda7fa169870b06b",
    ),
    "iren_microsoft_8k.headers": (
        593,
        "e6ccc74e71e86801c0b07be9c9b4f086d9937cd1d7f5523a3ad712af5cc50280",
    ),
    "iren_microsoft_8k.htm": (
        35_588,
        "12f8b3ebff00d59612bba7a1b38a6e4a1ca89fd03ba8bc27e36e017f75180802",
    ),
    "iren_microsoft_exhibit.headers": (
        593,
        "ac7aab87c4da5e7dc9a98c1ff54f10f9f51d3eef7ce6f9ebfe314086708f8b66",
    ),
    "iren_microsoft_exhibit.htm": (
        17_695,
        "b4da17d8b074b4d2d6e47365fa0227438ff5887072e4066f40dbbf41b00027f0",
    ),
    "iren_microsoft_index.headers": (
        269,
        "5330265c51cb151c6f50dfd91b81b6dc6ed53f0e4da036319e86a838c72928bd",
    ),
    "iren_microsoft_index.json": (
        2_890,
        "d60f090eaa9b8886a5256202dad6fdd260437dc89be88ca7e1c5cc1457282fc1",
    ),
    "iren_microsoft_submission.headers": (
        618,
        "2565745eaabe7ac31afe9e59bed99e295c58363f98f83927f951991c221f45b9",
    ),
    "iren_microsoft_submission.txt": (
        2_571_389,
        "ef6e4dd0f8ec2284e8f2477514c4c60c4bd105dc64b26a4cfff2a8f6362e4806",
    ),
    "iren_q3_index.headers": (
        269,
        "14d6c773da3034d3250ced99f49ec7cf9580eb839613e9bbbdb36b5461e8608b",
    ),
    "iren_q3_index.json": (
        2_978,
        "a6fabda1afe871bb51544340f001ea5d01707cde86a64d3004b13895711f8f2e",
    ),
    "iren_q3_submission.headers": (
        618,
        "616d64cf60fe6a0256e993694a70860c661fd9a93fdac21cda85b5a8342c0c03",
    ),
    "iren_q3_submission.txt": (
        2_607_307,
        "7cf9bb2a9232c6f5a2e7fa7721bb916a053d2d02cccd13f7358f092411f48f88",
    ),
    "iren_submissions.headers": (
        447,
        "65d9568082e58170cb69d9aec6c82d80cc1979100f11bb6362a826f5b7680bda",
    ),
    "iren_submissions.json": (
        52_021,
        "a7a8f8a9a3a6be0574e50e442c388a2042c328ec1f8bd63ba60f9b1a4c0afdc3",
    ),
    "northc.headers": (
        848,
        "656417f25a6ec1b262384dbc2ebba03f424dffa34e893e0b80b419e80546c973",
    ),
    "northc.html": (
        256_286,
        "8f79370d78113eb043e1b8bdd1cac05b4b21a053c936488593f70b42e9f48acc",
    ),
    "northc_aalsmeer.headers": (
        846,
        "b9c07436917b25c1f56387b8c492e80d554a29d1204387eba390d0f600255a51",
    ),
    "northc_aalsmeer.html": (
        325_300,
        "af2e5c3b7d06139a46aa2dce451084c2b9c9ecc88e18b65dfe0a37f1557b132f",
    ),
    "nscale.headers": (
        1_221,
        "901667e0a809af53709da8b63a3d652ee55c07509b4d8eb3db1a7e65c4acebdb",
    ),
    "nscale.html": (
        59_034,
        "80083854496ae0b2952d0ccff49a3f6a85d33a9c6fa41c7caef55050a117e619",
    ),
    "sentia.headers": (
        865,
        "2cb023893c4cb14b39680a03ead839fff69fb8eb26925012d7bf7567e78c2da0",
    ),
    "sentia.html": (
        71_477,
        "46c3638ba88f1fd03cb3abfa1861233e40d675351fcef66da73e756407b99dbb",
    ),
}


@dataclass(frozen=True)
class Capture:
    capture_id: str
    body_name: str
    header_name: str
    url: str
    content_type: str
    claim_use: str


CAPTURES = (
    Capture(
        "sentia_epc",
        "sentia.html",
        "sentia.headers",
        "https://www.sentiagruppen.no/press/hent-et-selskap-i-sentia-konsernet-inngar-avtale-for-bygging-av-nytt-datasenteranlegg-i-narvik-regionen",
        "text/html; charset=utf-8",
        "nscale_epc_and_physical_start_authority",
    ),
    Capture(
        "nscale_nordscale",
        "nscale.html",
        "nscale.headers",
        "https://www.nscale.com/press-releases/nordscale",
        "text/html; charset=utf-8",
        "nscale_current_construction_phase_authority",
    ),
    Capture(
        "northc_expansion",
        "northc.html",
        "northc.headers",
        "https://www.northcdatacenters.com/nieuws/update-uitbreidingen-datacenter-april26/",
        "text/html; charset=UTF-8",
        "northc_phase_2_status_and_capacity_authority",
    ),
    Capture(
        "northc_aalsmeer_facility",
        "northc_aalsmeer.html",
        "northc_aalsmeer.headers",
        "https://www.northcdatacenters.com/northc-datacenters/aalsmeer/",
        "text/html; charset=UTF-8",
        "northc_address_and_whole_facility_context",
    ),
    Capture(
        "iren_q3_results",
        "iren_exhibit.htm",
        "iren_exhibit.headers",
        "https://www.sec.gov/Archives/edgar/data/1878848/000187884826000025/irenreportsq3fy26results.htm",
        "text/html",
        "iren_horizons_current_status_authority",
    ),
    Capture(
        "iren_q3_accession_index",
        "iren_q3_index.json",
        "iren_q3_index.headers",
        "https://www.sec.gov/Archives/edgar/data/1878848/000187884826000025/index.json",
        "text/html",
        "iren_q3_accession_closed_inventory",
    ),
    Capture(
        "iren_q3_complete_submission",
        "iren_q3_submission.txt",
        "iren_q3_submission.headers",
        "https://www.sec.gov/Archives/edgar/data/1878848/000187884826000025/0001878848-26-000025.txt",
        "text/plain",
        "iren_q3_accession_lineage",
    ),
    Capture(
        "iren_2026_q3_10q",
        "iren_10q.htm",
        "iren_10q.headers",
        "https://www.sec.gov/Archives/edgar/data/1878848/000187884826000026/iren-20260331.htm",
        "text/html",
        "iren_construction_in_progress_and_contract_corroboration",
    ),
    Capture(
        "iren_10q_accession_index",
        "iren_10q_index.json",
        "iren_10q_index.headers",
        "https://www.sec.gov/Archives/edgar/data/1878848/000187884826000026/index.json",
        "text/html",
        "iren_10q_accession_closed_inventory",
    ),
    Capture(
        "iren_10q_complete_submission",
        "iren_10q_submission.txt",
        "iren_10q_submission.headers",
        "https://www.sec.gov/Archives/edgar/data/1878848/000187884826000026/0001878848-26-000026.txt",
        "text/plain",
        "iren_10q_accession_lineage",
    ),
    Capture(
        "iren_microsoft_8k",
        "iren_microsoft_8k.htm",
        "iren_microsoft_8k.headers",
        "https://www.sec.gov/Archives/edgar/data/1878848/000114036125040072/ef20058139_8k.htm",
        "text/html",
        "iren_binding_microsoft_contract_and_capacity_authority",
    ),
    Capture(
        "iren_microsoft_exhibit",
        "iren_microsoft_exhibit.htm",
        "iren_microsoft_exhibit.headers",
        "https://www.sec.gov/Archives/edgar/data/1878848/000114036125040072/ef20058139_ex99-1.htm",
        "text/html",
        "iren_critical_it_capacity_corroboration",
    ),
    Capture(
        "iren_microsoft_accession_index",
        "iren_microsoft_index.json",
        "iren_microsoft_index.headers",
        "https://www.sec.gov/Archives/edgar/data/1878848/000114036125040072/index.json",
        "text/html",
        "iren_microsoft_accession_closed_inventory",
    ),
    Capture(
        "iren_microsoft_complete_submission",
        "iren_microsoft_submission.txt",
        "iren_microsoft_submission.headers",
        "https://www.sec.gov/Archives/edgar/data/1878848/000114036125040072/0001140361-25-040072.txt",
        "text/plain",
        "iren_microsoft_accession_lineage",
    ),
    Capture(
        "iren_issuer_submissions",
        "iren_submissions.json",
        "iren_submissions.headers",
        "https://data.sec.gov/submissions/CIK0001878848.json",
        "application/json",
        "iren_issuer_and_filing_metadata",
    ),
    Capture(
        "bitzero_june_update",
        "bitzero.html",
        "bitzero.headers",
        "https://www.newsfilecorp.com/release/301582",
        "text/html; charset=UTF-8",
        "bitzero_foundations_status_authority",
    ),
    Capture(
        "bitzero_april_update",
        "bitzero_april.html",
        "bitzero_april.headers",
        "https://www.newsfilecorp.com/release/294165/Bitzero-Holdings-Inc.-Provides-Engineering-Update-at-its-Finland-and-Norway-Sites",
        "text/html; charset=UTF-8",
        "bitzero_untyped_70mw_context_only",
    ),
)
CAPTURE_BY_ID = {capture.capture_id: capture for capture in CAPTURES}

NSCALE_FILENAME = "curated-official-2026-07-22-nscale-kvandal-narvik-current-build.json"
NORTHC_FILENAME = "curated-official-2026-07-22-northc-aalsmeer-phase-2-expansion.json"
IREN_FILENAME = (
    "curated-official-2026-07-22-iren-childress-horizons-1-4-current-build.json"
)
BITZERO_FILENAME = (
    "curated-official-2026-07-22-bitzero-namsskogan-power-expansion-foundations.json"
)
SOURCE_FILENAMES = (
    NSCALE_FILENAME,
    NORTHC_FILENAME,
    IREN_FILENAME,
    BITZERO_FILENAME,
)

CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

NSCALE_SENTIA_EVIDENCE = "sentia-hent-nscale-kvandal-epc-2025-12-23"
NSCALE_UPDATE_EVIDENCE = "nscale-nordscale-kvandal-construction-2026-07-06"
NORTHC_EXPANSION_EVIDENCE = "northc-aalsmeer-phase-2-expansion-2026-04-01"
NORTHC_FACILITY_EVIDENCE = "northc-aalsmeer-facility-captured-2026-07-22"
IREN_CONTRACT_EVIDENCE = "iren-microsoft-horizons-1-4-contract-2025-11-02"
IREN_UPDATE_EVIDENCE = "iren-horizons-1-4-progress-update-2026-05-07"
IREN_10Q_EVIDENCE = "iren-q3-fy26-10q-childress-cip-2026-05-08"
BITZERO_FOUNDATIONS_EVIDENCE = "bitzero-namsskogan-transformer-foundations-2026-06-15"
BITZERO_APRIL_EVIDENCE = "bitzero-namsskogan-energization-context-2026-04-24"

NSCALE_CAMPUS = "curated:nscale-kvandal-narvik-ai-data-center-campus"
NSCALE_PROJECT = f"{NSCALE_CAMPUS}:initial-25mw-epc-current-build"
NORTHC_CAMPUS = "curated:northc-aalsmeer-data-center"
NORTHC_PROJECT = f"{NORTHC_CAMPUS}:phase-2-first-floor-expansion"
IREN_CAMPUS = "curated:iren-childress-ai-data-center-campus"
IREN_PROJECT = f"{IREN_CAMPUS}:horizons-1-4-current-build"
BITZERO_CAMPUS = "curated:bitzero-namsskogan-data-center-campus"
BITZERO_PROJECT = f"{BITZERO_CAMPUS}:2026-power-infrastructure-expansion"


def _capture_metadata(capture_id: str) -> dict[str, Any]:
    capture = CAPTURE_BY_ID[capture_id]
    body_size, body_hash = CAPTURE_FILE_PINS[capture.body_name]
    header_size, header_hash = CAPTURE_FILE_PINS[capture.header_name]
    return {
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture_id,
        "capture_method": "credential_free_single_http_capture_no_retry",
        "requested_url": capture.url,
        "effective_url": capture.url,
        "request_credentials_supplied": False,
        "http_status": 200,
        "content_type": capture.content_type,
        "content_hash_scope": (
            f"SHA-256 of the exact {body_size}-byte publisher response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_body_bytes": body_size,
        "capture_body_sha256": body_hash,
        "capture_headers_bytes": header_size,
        "capture_headers_sha256": header_hash,
        "retrieved_at_semantics": (
            "All evidence records use the bounded capture session's latest "
            f"whole-second completion time, {RETRIEVED_AT}."
        ),
        "rights_scope": (
            "Compact factual extraction from an all-rights-reserved official "
            "publisher page or issuer filing; raw body and headers are not "
            "redistributed."
        ),
        "status_semantics": "dated_last_observed_current_status_unknown",
        "visual_guardrail": (
            "No publisher image, map, satellite imagery, aerial imagery, computer "
            "vision, inferred coordinate, or geometry supplies any normalized fact."
        ),
    }


def _evidence(
    *,
    key: str,
    capture_id: str,
    title: str,
    publisher: str,
    source_family: str,
    published_at: str | None,
    excerpt: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    capture = CAPTURE_BY_ID[capture_id]
    return {
        "key": key,
        "kind": "company_disclosure",
        "title": title,
        "source_url": capture.url,
        "publisher": publisher,
        "source_family": source_family,
        "published_at": published_at,
        "retrieved_at": RETRIEVED_AT,
        "license": "all-rights-reserved",
        "attribution": publisher,
        "excerpt": excerpt,
        "content_hash": CAPTURE_FILE_PINS[capture.body_name][1],
        "metadata": {**_capture_metadata(capture_id), **metadata},
    }


def _entity(
    *,
    stable_key: str,
    name: str,
    country: str,
    address: str,
    roles: Mapping[str, Sequence[str]],
    evidence_key: str,
    as_of_date: str,
) -> dict[str, Any]:
    return {
        "stable_key": stable_key,
        "name": name,
        "country": country,
        "address": address,
        "roles": {role: list(names) for role, names in roles.items()},
        "coordinates": None,
        "geometry": None,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": "authoritative_locality",
        "confidence": 0.99,
    }


def _nscale_source() -> dict[str, Any]:
    sentia = _evidence(
        key=NSCALE_SENTIA_EVIDENCE,
        capture_id="sentia_epc",
        title="HENT signs final EPC contract for a new Kvandal data center",
        publisher="Sentia ASA",
        source_family="sentia_press_releases",
        published_at="2025-12-23",
        excerpt=(
            "Sentia reports a final HENT EPC contract for a 25 MW data center at "
            "Kvandal outside Narvik and says work has begun for 2026 completion."
        ),
        metadata={
            "location_scope": (
                "Kvandal outside Narvik is an authoritative locality, not a "
                "street address, parcel, point, footprint, or geometry."
            ),
            "physical_status_scope": (
                "The Norwegian source says the works have begun. The later Nscale "
                "capture supplies the newest dated construction-phase support."
            ),
            "epc_capacity_as_reported": "25 MW",
            "capacity_exclusion": (
                "The EPC page calls the data center 25 MW without typing the figure "
                "as critical IT, gross-facility demand, or grid connection. It is "
                "metadata only and creates no normalized capacity."
            ),
            "future_capacity_guardrail": (
                "No 230 MW designed scope or 290 MW future scope is normalized."
            ),
            "classification_guardrail": (
                "A planned AI positioning or data-center label does not establish "
                "an actual workload or operating model."
            ),
        },
    )
    update = _evidence(
        key=NSCALE_UPDATE_EVIDENCE,
        capture_id="nscale_nordscale",
        title="Nscale and Nordkraft establish Nordscale Operations",
        publisher="Nscale",
        source_family="nscale_press_releases",
        published_at="2026-07-06",
        excerpt=(
            "Nscale says Nordkraft has delivered operational services during the "
            "construction phase at Nscale's Kvandal data center."
        ),
        metadata={
            "status_scope": (
                "Operational services during the construction phase support one "
                "under-construction observation dated 2026-07-06; they do not prove "
                "completion, commissioning, occupancy, or operation."
            ),
            "identity_scope": (
                "The capture identifies Nscale's AI data center at Kvandal in the "
                "Narvik region. Identity is not anchored to Stargate, OpenAI, "
                "Microsoft, a tenant, or an accelerator deployment."
            ),
            "workload_guardrail": (
                "The AI data-center description is positioning only in this tranche "
                "and creates no workload observation."
            ),
        },
    )
    roles = {"developer": ["Nscale"], "contractor": ["HENT"]}
    return {
        "schema_version": "1.1",
        "evidence": [sentia, update],
        "campus": _entity(
            stable_key=NSCALE_CAMPUS,
            name="Nscale Kvandal Narvik AI Data Center Campus",
            country="Norway",
            address="Kvandal, outside Narvik, Norway",
            roles=roles,
            evidence_key=NSCALE_UPDATE_EVIDENCE,
            as_of_date="2026-07-06",
        ),
        "project": _entity(
            stable_key=NSCALE_PROJECT,
            name="Nscale Kvandal Initial 25 MW EPC Current Build",
            country="Norway",
            address="Kvandal, outside Narvik, Norway",
            roles=roles,
            evidence_key=NSCALE_UPDATE_EVIDENCE,
            as_of_date="2026-07-06",
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": NSCALE_UPDATE_EVIDENCE,
                "as_of_date": "2026-07-06",
                "method": "authoritative_physical_status_update",
                "confidence": 0.99,
            }
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _northc_source() -> dict[str, Any]:
    expansion = _evidence(
        key=NORTHC_EXPANSION_EVIDENCE,
        capture_id="northc_expansion",
        title="Update over de uitbreiding van onze datacenters",
        publisher="NorthC Datacenters",
        source_family="northc_news",
        published_at="2026-04-01",
        excerpt=(
            "NorthC says Aalsmeer phase 2 has started, expands the first floor, and "
            "will add 2.4 MW of IT load and 1,800 square metres of data floor."
        ),
        metadata={
            "article_published_time": "2026-04-01T08:04:13+00:00",
            "article_modified_time_at_capture": "2026-07-21T12:35:05+00:00",
            "status_scope": (
                "The explicit statement that phase 2 has started supports one "
                "expansion observation dated to the article's publication date."
            ),
            "capacity_scope": (
                "The second 2.4 MW IT-load figure is textually scoped to phase 2 and "
                "normalized once as planned project critical IT capacity."
            ),
            "floor_area_metadata": "1,800 m2 extra data floor for phase 2",
            "phase_1_nonadditivity_guardrail": (
                "The completed phase-1 2.4 MW and 1,800 m2 are predecessor context "
                "and are not added to phase 2."
            ),
            "forecast_guardrail": (
                "Q1 2027 connection to existing infrastructure is a forecast, not "
                "an actual connection, energization, commissioning, or operation."
            ),
        },
    )
    facility = _evidence(
        key=NORTHC_FACILITY_EVIDENCE,
        capture_id="northc_aalsmeer_facility",
        title="Datacenter Aalsmeer",
        publisher="NorthC Datacenters",
        source_family="northc_facility_pages",
        published_at=None,
        excerpt=(
            "NorthC's facility page identifies the Aalsmeer address as "
            "Lakenblekerstraat 13, 1431 GE Aalsmeer and reports 14 MW installed "
            "electrical power for the whole facility."
        ),
        metadata={
            "address_as_reported": "Lakenblekerstraat 13, 1431 GE Aalsmeer",
            "address_scope": (
                "The facility page supports the exact address string. It supplies "
                "no coordinate, parcel, footprint, or geometry."
            ),
            "whole_facility_electrical_power_as_reported": "14 MW",
            "capacity_exclusion": (
                "The 14 MW installed electrical power is whole-facility context, "
                "not phase-2 critical IT or an additive project capacity. It creates "
                "no normalized row in this tranche."
            ),
            "operating_model_guardrail": (
                "The page's general solutions section is not converted into a "
                "phase-2 operating-model observation."
            ),
        },
    )
    roles = {"operator": ["NorthC"]}
    address = "Lakenblekerstraat 13, 1431 GE Aalsmeer, Netherlands"
    return {
        "schema_version": "1.1",
        "evidence": [expansion, facility],
        "campus": _entity(
            stable_key=NORTHC_CAMPUS,
            name="NorthC Aalsmeer Data Center",
            country="Netherlands",
            address=address,
            roles=roles,
            evidence_key=NORTHC_FACILITY_EVIDENCE,
            as_of_date="2026-07-22",
        ),
        "project": _entity(
            stable_key=NORTHC_PROJECT,
            name="NorthC Aalsmeer Phase 2 First-Floor Expansion",
            country="Netherlands",
            address=address,
            roles=roles,
            evidence_key=NORTHC_FACILITY_EVIDENCE,
            as_of_date="2026-07-22",
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": "expansion",
                "evidence_key": NORTHC_EXPANSION_EVIDENCE,
                "as_of_date": "2026-04-01",
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
                "low": 2.4,
                "base": 2.4,
                "high": 2.4,
                "method": "reported",
                "confidence": 0.99,
                "evidence_key": NORTHC_EXPANSION_EVIDENCE,
                "as_of_date": "2026-04-01",
                "target_date": None,
                "notes": (
                    "Phase-2 IT-load capacity only. It excludes phase 1 and the "
                    "facility page's 14 MW installed whole-facility electrical power."
                ),
            }
        ],
    }


def _iren_source() -> dict[str, Any]:
    contract = _evidence(
        key=IREN_CONTRACT_EVIDENCE,
        capture_id="iren_microsoft_8k",
        title="IREN Form 8-K - Microsoft commercial agreement",
        publisher="IREN Limited",
        source_family="sec_edgar_iren_filings",
        published_at="2025-11-03",
        excerpt=(
            "IREN reports a Microsoft GPU-services agreement across Horizon 1-4 at "
            "Childress, representing approximately 200 MW combined IT load."
        ),
        metadata={
            "sec_accession": "0001140361-25-040072",
            "contract_effective_date": "2025-11-02",
            "contract_scope": (
                "The material definitive agreement provides Microsoft dedicated GPU "
                "infrastructure in tranches across Horizon 1-4 over an average "
                "five-year term."
            ),
            "capacity_scope": (
                "The filing explicitly types the grouped Horizon 1-4 capacity as "
                "approximately 200 MW combined IT load. The issuer exhibit further "
                "calls it critical IT load. One contracted critical_it_mw row is "
                "created for the grouped project."
            ),
            "grouped_boundary_guardrail": (
                "The official evidence does not allocate capacity or status across "
                "four individual buildings. No per-Horizon entity or allocation is "
                "invented."
            ),
            "customer_scope": (
                "Microsoft is retained only as the contract customer. This is not "
                "treated as a real-estate lease or hyperscale-lease model."
            ),
            "workload_guardrail": (
                "GPU and AI-cloud contract context remains metadata; this tranche "
                "creates no standardized workload observation."
            ),
        },
    )
    update = _evidence(
        key=IREN_UPDATE_EVIDENCE,
        capture_id="iren_q3_results",
        title="IREN Business Update and Q3 FY26 Results",
        publisher="IREN Limited",
        source_family="sec_edgar_iren_exhibits",
        published_at="2026-05-07",
        excerpt=(
            "IREN says it advanced the Horizon 1-4 liquid-cooled data centers at "
            "Childress and that the group is on track for year-end delivery."
        ),
        metadata={
            "sec_accession": "0001878848-26-000025",
            "issuer_release_date": "2026-05-07",
            "sec_filing_date": "2026-05-08",
            "sec_acceptance_datetime": "2026-05-08T01:05:29.000Z",
            "status_scope": (
                "Advancing the named liquid-cooled data centers, corroborated by "
                "construction-in-progress disclosure, supports one grouped "
                "under-construction observation dated 2026-05-07."
            ),
            "delivery_guardrail": (
                "On-track year-end delivery is a forecast and does not establish "
                "completion, energization, commissioning, acceptance, or operation."
            ),
            "broader_deployment_exclusion": (
                "The 480 MW 2026 expansion and broader 300 MW deployment language "
                "are not scoped to Horizon 1-4 critical IT and create no row."
            ),
        },
    )
    filing = _evidence(
        key=IREN_10Q_EVIDENCE,
        capture_id="iren_2026_q3_10q",
        title="IREN Quarterly Report for the Quarter Ended March 31, 2026",
        publisher="IREN Limited",
        source_family="sec_edgar_iren_filings",
        published_at="2026-05-08",
        excerpt=(
            "IREN reports construction-in-progress costs for Childress data-center "
            "infrastructure and continuing expansion including Horizons 1-4."
        ),
        metadata={
            "sec_accession": "0001878848-26-000026",
            "sec_filing_date": "2026-05-08",
            "sec_acceptance_datetime": "2026-05-08T01:12:37.000Z",
            "construction_in_progress_scope": (
                "The filing corroborates physical data-center infrastructure work at "
                "Childress and specifically identifies continuing expansion including "
                "Horizons 1-4. It does not create a second lifecycle row."
            ),
            "contract_corroboration_scope": (
                "The filing restates the Microsoft agreement and Horizon 1-4 use. "
                "It does not create a second capacity or customer observation."
            ),
            "campus_capacity_exclusion": (
                "The 750 MW Childress whole-site power figure is not Horizon 1-4 "
                "critical IT and creates no normalized capacity in this tranche."
            ),
        },
    )
    roles = {"developer": ["IREN"], "operator": ["IREN"], "customer": ["Microsoft"]}
    address = "Childress, Texas, United States"
    return {
        "schema_version": "1.1",
        "evidence": [contract, update, filing],
        "campus": _entity(
            stable_key=IREN_CAMPUS,
            name="IREN Childress AI Data Center Campus",
            country="United States",
            address=address,
            roles=roles,
            evidence_key=IREN_UPDATE_EVIDENCE,
            as_of_date="2026-05-07",
        ),
        "project": _entity(
            stable_key=IREN_PROJECT,
            name="IREN Childress Horizons 1-4 Current Build",
            country="United States",
            address=address,
            roles=roles,
            evidence_key=IREN_UPDATE_EVIDENCE,
            as_of_date="2026-05-07",
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": IREN_UPDATE_EVIDENCE,
                "as_of_date": "2026-05-07",
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
                "stage": "contracted",
                "unit": "MW",
                "low": 200.0,
                "base": 200.0,
                "high": 200.0,
                "method": "reported",
                "confidence": 0.99,
                "evidence_key": IREN_CONTRACT_EVIDENCE,
                "as_of_date": "2025-11-02",
                "target_date": None,
                "notes": (
                    "Binding Microsoft-agreement aggregate critical IT for grouped "
                    "Horizons 1-4. No per-building allocation; excludes 750 MW "
                    "whole-site power and broader deployment totals."
                ),
            }
        ],
    }


def _bitzero_source() -> dict[str, Any]:
    foundations = _evidence(
        key=BITZERO_FOUNDATIONS_EVIDENCE,
        capture_id="bitzero_june_update",
        title="Bitzero Nordic infrastructure update",
        publisher="Bitzero Holdings Inc.",
        source_family="bitzero_newsfile_releases",
        published_at="2026-06-15",
        excerpt=(
            "Bitzero says construction is underway on foundations for two new "
            "60 MW transformers at its Namsskogan data-center campus."
        ),
        metadata={
            "physical_status_scope": (
                "The foundations observation is scoped only to two transformer "
                "foundations supporting the site's power-infrastructure expansion. "
                "It is not a data-hall shell, building foundation, fit-out, "
                "commissioning, or operational claim."
            ),
            "transformer_nameplates_as_reported": "two new 60 MW transformers",
            "transformer_capacity_exclusion": (
                "Transformer nameplates are not data-center load, critical IT, gross "
                "facility demand, or contracted grid capacity. They are not summed "
                "and create no normalized capacity."
            ),
            "campus_capacity_context": "110 MW data center campus",
            "campus_capacity_exclusion": (
                "The 110 MW whole-campus figure and proposed lease scope are future "
                "commercial context, not this foundation project's typed capacity."
            ),
            "lease_guardrail": (
                "A definitive OneQode lease had not been executed. No tenant, user, "
                "customer, operating model, or workload observation is created."
            ),
            "forecast_guardrail": (
                "Transformer delivery and 2027 service timing are forecasts, not "
                "actual delivery, energization, commissioning, or operation."
            ),
        },
    )
    april = _evidence(
        key=BITZERO_APRIL_EVIDENCE,
        capture_id="bitzero_april_update",
        title="Bitzero engineering update at Finland and Norway sites",
        publisher="Bitzero Holdings Inc.",
        source_family="bitzero_newsfile_releases",
        published_at="2026-04-24",
        excerpt=(
            "Bitzero says it has a confirmed 70 MW expected to be energized in "
            "Q4 2026 at Namsskogan."
        ),
        metadata={
            "energization_language_as_reported": (
                "confirmed 70MW expected to be energized in Q4 2026"
            ),
            "capacity_exclusion": (
                "The release does not unambiguously type 70 MW as grid-connection, "
                "gross-facility, or critical-IT capacity for the June transformer-"
                "foundation project, and expressly treats energization as forward-"
                "looking. It remains metadata only and creates no capacity row."
            ),
            "design_exclusions": (
                "The designed 5 MW self-hosting cluster and two 50 MW colocation "
                "spaces are design/commercial context and create no entity, "
                "capacity, operating model, workload, or physical-status claim."
            ),
        },
    )
    roles = {"developer": ["Bitzero"]}
    address = "Namsskogan, Norway"
    return {
        "schema_version": "1.1",
        "evidence": [foundations, april],
        "campus": _entity(
            stable_key=BITZERO_CAMPUS,
            name="Bitzero Namsskogan Data Center Campus",
            country="Norway",
            address=address,
            roles=roles,
            evidence_key=BITZERO_FOUNDATIONS_EVIDENCE,
            as_of_date="2026-06-15",
        ),
        "project": _entity(
            stable_key=BITZERO_PROJECT,
            name="Bitzero Namsskogan 2026 Power Infrastructure Expansion",
            country="Norway",
            address=address,
            roles=roles,
            evidence_key=BITZERO_FOUNDATIONS_EVIDENCE,
            as_of_date="2026-06-15",
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": "foundations",
                "evidence_key": BITZERO_FOUNDATIONS_EVIDENCE,
                "as_of_date": "2026-06-15",
                "method": "authoritative_physical_status_update",
                "confidence": 0.99,
            }
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    return {
        NSCALE_FILENAME: _nscale_source(),
        NORTHC_FILENAME: _northc_source(),
        IREN_FILENAME: _iren_source(),
        BITZERO_FILENAME: _bitzero_source(),
    }


REVIEW_ONLY = (
    {
        "candidate_id": "nscale-25mw-untyped-capacity",
        "site": "Kvandal, Norway",
        "source_language": "new data center with capacity of 25 MW",
        "exclusion": "Untyped EPC capacity; no normalized capacity row.",
    },
    {
        "candidate_id": "nscale-230mw-290mw-future-scopes",
        "site": "Kvandal, Norway",
        "source_language": "designed and future expansion capacities",
        "exclusion": "Designed/future scopes; no current-build capacity row.",
    },
    {
        "candidate_id": "northc-aalsmeer-existing-14mw",
        "site": "Aalsmeer, Netherlands",
        "source_language": "14 MW installed electrical power",
        "exclusion": "Whole-facility context; not phase-2 capacity or additive.",
    },
    {
        "candidate_id": "iren-childress-750mw-campus-power",
        "site": "Childress, Texas",
        "source_language": "750 MW Childress site",
        "exclusion": "Whole-site power; not Horizon 1-4 critical IT.",
    },
    {
        "candidate_id": "iren-broader-300mw-deployment",
        "site": "Childress, Texas",
        "source_language": "broader deployment wording",
        "exclusion": "Not allocated to grouped Horizons 1-4.",
    },
    {
        "candidate_id": "bitzero-transformer-nameplates",
        "site": "Namsskogan, Norway",
        "source_language": "two new 60 MW transformers",
        "exclusion": "Equipment nameplates; not data-center capacity and not summed.",
    },
    {
        "candidate_id": "bitzero-70mw-expected-energization",
        "site": "Namsskogan, Norway",
        "source_language": "confirmed 70MW expected to be energized in Q4 2026",
        "exclusion": (
            "Forward-looking and not unambiguously typed to an ontology metric."
        ),
    },
    {
        "candidate_id": "bitzero-110mw-proposed-lease",
        "site": "Namsskogan, Norway",
        "source_language": "binding letter for full 110MW capacity",
        "exclusion": (
            "Definitive lease not executed; no tenant/model/workload or project capacity."
        ),
    },
)


def _source_records(
    documents: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for name in SOURCE_FILENAMES:
        document = documents[name]
        payload = _canonical(document)
        rows.append(
            {
                "path": f"sources/{name}",
                "bytes": len(payload),
                "sha256": _sha256_bytes(payload),
                "schema_version": "1.1",
                "country": document["campus"]["country"],
                "campus_stable_key": document["campus"]["stable_key"],
                "project_stable_key": document["project"]["stable_key"],
                "evidence_records": len(document["evidence"]),
                "lifecycle_observations": len(document["lifecycle"]),
                "capacity_estimates": len(document["capacities"]),
                "operating_model_observations": 0,
                "workload_observations": 0,
                "coordinates_present": 0,
                "geometry_present": 0,
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
        row["key"] for document in documents.values() for row in document["evidence"]
    }
    return stable, evidence


def _known_v94_witness(
    planned_stable: set[str], planned_evidence: set[str]
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for name in KNOWN_V94_SOURCE_FILENAMES:
        path = SOURCES_ROOT / name
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"known v94-bound source is absent or unsafe: {name}")
        document = json.loads(path.read_text(encoding="utf-8"))
        stable = {
            row.get("stable_key")
            for key in ("campus", "facility", "building", "project")
            if isinstance((row := document.get(key)), dict)
        }
        evidence = {
            row.get("key")
            for row in document.get("evidence", [])
            if isinstance(row, dict)
        }
        stable_collision = sorted(planned_stable & stable)
        evidence_collision = sorted(planned_evidence & evidence)
        if stable_collision or evidence_collision:
            raise RuntimeError(f"known v94-bound source collision: {name}")
        rows.append(
            {
                "path": f"sources/{name}",
                "stable_key_collisions": stable_collision,
                "evidence_key_collisions": evidence_collision,
                "bytes_or_hash_dependency": False,
            }
        )
    return {
        "known_source_count": len(rows),
        "unfinished_open_seed_v94_bytes_required": False,
        "sources": rows,
    }


def _collision_witness(
    documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    for path, pin in V93_PINS.items():
        _pin(path, pin)
    if tree_digest(V93_RELEASE) != V93_TREE_SHA256:
        raise RuntimeError("v93 release tree differs")
    definition = json.loads(V93_DEFINITION.read_text())
    selected = definition.get("curated_inputs")
    if not isinstance(selected, list) or len(selected) != V93_INPUT_COUNT:
        raise RuntimeError("v93 selected inputs differ")
    with V93_ENTITIES.open(encoding="utf-8", newline="") as stream:
        entity_rows = list(csv.DictReader(stream))
    if len(entity_rows) != V93_ENTITY_COUNT:
        raise RuntimeError("v93 entity count differs")
    planned_stable, planned_evidence = _planned_keys(documents)
    base_stable = {row["stable_key"] for row in entity_rows}
    if planned_stable & base_stable:
        raise RuntimeError("official tranche stable key collides with v93")
    source_inputs = json.loads(V93_SOURCE_INPUTS.read_text())
    base_evidence = {
        key
        for row in source_inputs.get("sources", [])
        if isinstance(row, dict)
        for key in [row.get("provenance", {}).get("curated_record_key")]
        if isinstance(key, str)
    }
    if planned_evidence & base_evidence:
        raise RuntimeError("official tranche evidence key collides with v93")
    known_v94 = _known_v94_witness(planned_stable, planned_evidence)
    source_names = set(SOURCE_FILENAMES)
    collisions: dict[str, Any] = {}
    for path in SOURCES_ROOT.glob("*.json"):
        if path.name in source_names:
            continue
        try:
            document = json.loads(path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        stable = {
            row.get("stable_key")
            for key in ("campus", "facility", "building", "project")
            if isinstance((row := document.get(key)), dict)
        }
        evidence = {
            row.get("key")
            for row in document.get("evidence", [])
            if isinstance(row, dict)
        }
        if planned_stable & stable or planned_evidence & evidence:
            collisions[str(path.relative_to(ROOT))] = {
                "stable_keys": sorted(planned_stable & stable),
                "evidence_keys": sorted(planned_evidence & evidence),
            }
    if collisions:
        raise RuntimeError(f"official tranche source collision: {collisions!r}")
    return {
        "v93_selected_input_count": len(selected),
        "v93_entity_count": len(entity_rows),
        "planned_distinct_stable_keys": len(planned_stable),
        "planned_distinct_evidence_keys": len(planned_evidence),
        "exact_v93_stable_key_collisions": [],
        "exact_v93_evidence_key_collisions": [],
        "unexpected_source_collisions": {},
        "known_v94_noncollision": known_v94,
    }


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    normalized = [
        {
            "candidate_id": "nscale-kvandal-initial-epc-build",
            "decision": "seed_eligible_direct_authoritative_physical_update",
            "source_paths": [f"sources/{NSCALE_FILENAME}"],
            "campus_stable_key": NSCALE_CAMPUS,
            "project_stable_key": NSCALE_PROJECT,
            "lifecycle": "under_construction",
            "as_of_date": "2026-07-06",
            "normalized_capacity": None,
            "capacity_exclusion": (
                "25 MW is not typed as critical IT, gross facility, or grid capacity."
            ),
        },
        {
            "candidate_id": "northc-aalsmeer-phase-2",
            "decision": "seed_eligible_direct_authoritative_physical_update",
            "source_paths": [f"sources/{NORTHC_FILENAME}"],
            "campus_stable_key": NORTHC_CAMPUS,
            "project_stable_key": NORTHC_PROJECT,
            "lifecycle": "expansion",
            "as_of_date": "2026-04-01",
            "normalized_capacity": {
                "metric": "critical_it_mw",
                "stage": "planned",
                "base": 2.4,
            },
            "capacity_exclusion": "14 MW is whole-facility electrical context.",
        },
        {
            "candidate_id": "iren-childress-horizons-1-4",
            "decision": "seed_eligible_direct_authoritative_physical_update",
            "source_paths": [f"sources/{IREN_FILENAME}"],
            "campus_stable_key": IREN_CAMPUS,
            "project_stable_key": IREN_PROJECT,
            "lifecycle": "under_construction",
            "as_of_date": "2026-05-07",
            "normalized_capacity": {
                "metric": "critical_it_mw",
                "stage": "contracted",
                "base": 200.0,
            },
            "capacity_exclusions": [
                "no per-Horizon allocation",
                "750 MW whole-site power excluded",
                "broader deployment totals excluded",
            ],
        },
        {
            "candidate_id": "bitzero-namsskogan-transformer-foundations",
            "decision": "seed_eligible_direct_authoritative_physical_update",
            "source_paths": [f"sources/{BITZERO_FILENAME}"],
            "campus_stable_key": BITZERO_CAMPUS,
            "project_stable_key": BITZERO_PROJECT,
            "lifecycle": "foundations",
            "as_of_date": "2026-06-15",
            "normalized_capacity": None,
            "capacity_exclusions": [
                "two 60 MW transformer nameplates excluded",
                "70 MW expected energization is untyped and forward-looking",
                "110 MW whole-campus/proposed lease context excluded",
            ],
        },
    ]
    review = [
        {
            **row,
            "decision": "review_only_no_direct_physical_data_center_observation",
            "source_paths": [],
            "source_authority": "captured official sources in retrieval-inventory.json",
            "normalized_entity": None,
            "normalized_lifecycle": None,
            "normalized_capacity": None,
        }
        for row in REVIEW_ONLY
    ]
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-current-build-assessment-v1",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "candidate_count": 12,
        "seed_eligible_candidate_count": 4,
        "seed_eligible_source_record_count": 4,
        "review_only_count": 8,
        "regional_completeness_claimed": False,
        "candidates": [*normalized, *review],
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "request_credentials_supplied": False,
        "successful_http_200_body_captures": 17,
        "failed_http_body_captures": 0,
        "failed_capture_inventory_complete": True,
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
                "retrieved_at": RETRIEVED_AT,
                "http_status": 200,
                "content_type": capture.content_type,
                "claim_use": capture.claim_use,
                "body": {
                    "path": capture.body_name,
                    "bytes": CAPTURE_FILE_PINS[capture.body_name][0],
                    "sha256": CAPTURE_FILE_PINS[capture.body_name][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "headers": {
                    "path": capture.header_name,
                    "bytes": CAPTURE_FILE_PINS[capture.header_name][0],
                    "sha256": CAPTURE_FILE_PINS[capture.header_name][1],
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
    recorded_at: str, documents: Mapping[str, Mapping[str, Any]]
) -> dict[str, bytes]:
    collision = _collision_witness(documents)
    records = _source_records(documents)
    totals = {
        "candidate_assessments": 12,
        "source_records": 4,
        "seed_eligible_candidates": 4,
        "review_only_candidates": 8,
        "distinct_campuses": 4,
        "projects": 4,
        "distinct_entities": 8,
        "unique_imported_entity_snapshots": 8,
        "unique_evidence_records": 9,
        "lifecycle_observations": 4,
        "capacity_estimates": 2,
        "planned_critical_it_mw_sum": 2.4,
        "contracted_critical_it_mw_sum": 200.0,
        "operating_model_observations": 0,
        "workload_observations": 0,
        "coordinates_present": 0,
        "geometry_present": 0,
    }
    readme = f"""# Official Nordic and IREN current-build source tranche

This immutable artifact publishes exactly four schema-1.1 campus/project records from captured official publisher pages and SEC-hosted issuer filings: Nscale Kvandal outside Narvik, NorthC Aalsmeer phase 2, IREN Childress Horizons 1-4, and Bitzero Namsskogan's 2026 power-infrastructure expansion. It performs no open-seed or downstream integration.

Nscale receives one `under_construction` observation dated 2026-07-06. Sentia says HENT's final EPC works at Kvandal had begun, and Nscale later says Nordkraft supplied operational services during the construction phase. The EPC source's 25 MW is untyped and remains metadata; no 230 MW or 290 MW scope is normalized. Planned AI positioning creates no workload, customer, tenant, or operating-model row.

NorthC Aalsmeer phase 2 receives one `expansion` observation dated 2026-04-01 and exactly one planned 2.4 MW `critical_it_mw` row. The same official article scopes 1,800 square metres of additional data floor to phase 2 as metadata. NorthC's facility page corroborates `Lakenblekerstraat 13, 1431 GE Aalsmeer, Netherlands`; its 14 MW installed electrical power is whole-facility context and is neither normalized nor added to phase 2. No colocation model is inferred from the page's general solutions section.

IREN Childress Horizons 1-4 remain one grouped project because the official evidence does not allocate facts across four separate buildings. The May 7 update and 10-Q support one `under_construction` observation. The binding Microsoft agreement and SEC exhibit support exactly one contracted 200 MW `critical_it_mw` row for the group. The 750 MW whole-site power figure, broader deployment totals, and per-Horizon allocations are excluded. Microsoft remains only a directly disclosed contract customer; no hyperscale-lease model or workload row is created.

Bitzero Namsskogan receives one `foundations` observation dated 2026-06-15, scoped only to foundations for two transformers supporting power-infrastructure expansion. It is not a data-hall or building-shell claim. The two 60 MW transformer nameplates are equipment values, not data-center capacity. An April release's 70 MW expected energization is both forward-looking and not unambiguously typed to an atlas capacity metric, so it remains metadata. The 110 MW campus, proposed lease, and 2027 timing create no capacity, tenant, model, workload, or operating-status row.

No record contains coordinates, geometry, PUE, WUE, measured energy, generation, current load, or current-status persistence. Satellite imagery, aerial imagery, maps, computer vision, and publisher graphics supply no normalized fact. All four source files and all seven artifact members received frozen modes at or after {recorded_at}; the artifact root did as well. Final paths were absent before the barrier and promoted without replacement with identity-protected rollback. The complete 34-file, {CAPTURE_TOTAL_BYTES}-byte private capture is moved intact to recoverable Trash only after successful live validation; raw bodies, headers, cookies, and publisher content are not redistributed.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "source_records": records,
        "totals": totals,
        "official_lineage": {
            "capture_count": len(CAPTURES),
            "evidence_capture_ids": [
                "sentia_epc",
                "nscale_nordscale",
                "northc_expansion",
                "northc_aalsmeer_facility",
                "iren_q3_results",
                "iren_2026_q3_10q",
                "iren_microsoft_8k",
                "bitzero_june_update",
                "bitzero_april_update",
            ],
            "sec_accessions": [
                "0001140361-25-040072",
                "0001878848-26-000025",
                "0001878848-26-000026",
            ],
            "closed_private_capture_inventory": True,
            "raw_capture_tree_sha256": CAPTURE_TREE_SHA256,
        },
        "capacity_boundary": {
            "normalized": [
                {
                    "entity": NORTHC_PROJECT,
                    "metric": "critical_it_mw",
                    "stage": "planned",
                    "base": 2.4,
                },
                {
                    "entity": IREN_PROJECT,
                    "metric": "critical_it_mw",
                    "stage": "contracted",
                    "base": 200.0,
                },
            ],
            "withheld": {
                "nscale_untyped_epc_mw": 25,
                "northc_whole_facility_electrical_mw": 14,
                "iren_whole_site_power_mw": 750,
                "bitzero_transformer_nameplates_mw_each": 60,
                "bitzero_untyped_expected_energization_mw": 70,
                "bitzero_future_campus_mw": 110,
            },
            "gross_facility_rows": 0,
            "grid_connection_rows": 0,
            "current_consumption_or_draw_rows": 0,
            "generation_rows": 0,
            "annual_energy_rows": 0,
        },
        "frozen_v93_and_known_v94_noncollision_witness": {
            "release_tree_sha256": V93_TREE_SHA256,
            **collision,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v93_mutated": False,
            "unfinished_open_seed_v94_bytes_used": False,
            "release_integration": "none",
            "construction_master_integration": "none",
            "map_integration": "none",
            "federation_integration": "none",
            "coverage_integration": "none",
            "review_integration": "none",
        },
        "publication_contract": {
            "version": 2,
            "all_source_and_artifact_member_ctimes_at_or_after_recorded_at": True,
            "artifact_root_ctime_at_or_after_recorded_at": True,
            "final_paths_absent_before_recorded_at": True,
            "publication_waited_until_recorded_at": True,
            "no_replace_promotion": True,
            "identity_checked_rollback_on_late_collision": True,
            "raw_capture_moved_after_successful_live_validation": True,
            "source_file_mode": "0444",
            "artifact_directory_mode": "0555",
            "artifact_file_mode": "0444",
        },
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-disposition-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "source_rights": (
            "Compact factual extraction from all-rights-reserved official company "
            "pages, publisher-distributed issuer releases, and SEC-hosted issuer "
            "filings. No redistribution license is relied on."
        ),
        "raw_capture_redistributed": False,
        "raw_response_bodies_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "cookies_retained_in_artifact": False,
        "publisher_images_retained_in_artifact": False,
        "raw_capture_tree_sha256": CAPTURE_TREE_SHA256,
        "raw_capture_file_count": CAPTURE_FILE_COUNT,
        "raw_capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "raw_capture_original_path": str(CAPTURE_ORIGIN),
        "raw_capture_recoverable_trash_path": str(CAPTURE_TRASH),
        "deletion_performed": False,
    }
    return {
        "README.md": readme.encode(),
        "candidate-assessment.json": _canonical(_candidate_assessment(recorded_at)),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _validate_sources(
    paths: Mapping[str, Path], *, require_frozen: bool
) -> list[dict[str, Any]]:
    expected = expected_source_documents()
    if set(paths) != set(SOURCE_FILENAMES):
        raise RuntimeError("official tranche source path inventory differs")
    wanted_mode = 0o444 if require_frozen else 0o600
    for name in SOURCE_FILENAMES:
        path = paths[name]
        if (
            path.is_symlink()
            or not path.is_file()
            or path.read_bytes() != _canonical(expected[name])
            or stat.S_IMODE(path.stat().st_mode) != wanted_mode
        ):
            raise RuntimeError(f"official tranche source differs: {name}")
    documents = list(expected.values())
    if any(
        document[entity][field] is not None
        for document in documents
        for entity in ("campus", "project")
        for field in ("coordinates", "geometry")
    ):
        raise RuntimeError("official tranche invented coordinates or geometry")
    if any(
        document[key]
        for document in documents
        for key in ("operating_models", "workloads")
    ):
        raise RuntimeError("official tranche invented classification observations")
    lifecycle = [
        (document["project"]["stable_key"], row["value"], row["as_of_date"])
        for document in documents
        for row in document["lifecycle"]
    ]
    if lifecycle != [
        (NSCALE_PROJECT, "under_construction", "2026-07-06"),
        (NORTHC_PROJECT, "expansion", "2026-04-01"),
        (IREN_PROJECT, "under_construction", "2026-05-07"),
        (BITZERO_PROJECT, "foundations", "2026-06-15"),
    ]:
        raise RuntimeError("official tranche lifecycle contract differs")
    capacities = [row for document in documents for row in document["capacities"]]
    if [
        (row["entity"], row["metric"], row["stage"], row["base"]) for row in capacities
    ] != [
        ("project", "critical_it_mw", "planned", 2.4),
        ("project", "critical_it_mw", "contracted", 200.0),
    ]:
        raise RuntimeError("official tranche capacity contract differs")
    serialized = json.dumps(documents, sort_keys=True)
    required_guardrails = (
        "25 MW",
        "14 MW",
        "750 MW",
        "two new 60 MW",
        "70 MW",
        "110 MW",
        "no normalized capacity",
        "no workload observation",
    )
    if any(fragment not in serialized for fragment in required_guardrails):
        raise RuntimeError("official tranche exclusion guardrails differ")
    if any(
        row["metric"]
        in {"gross_facility_mw", "grid_connection_mw", "annual_energy_mwh"}
        for row in capacities
    ):
        raise RuntimeError("official tranche normalized a forbidden capacity metric")
    return _source_records(expected)


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("official tranche capture directory absent or unsafe")
    entries = list(directory.iterdir())
    if (
        len(entries) != CAPTURE_FILE_COUNT
        or {entry.name for entry in entries} != set(CAPTURE_FILE_PINS)
        or any(entry.is_symlink() or not entry.is_file() for entry in entries)
    ):
        raise RuntimeError("official tranche capture closed set differs")
    if (
        sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES
        or tree_digest(directory) != CAPTURE_TREE_SHA256
    ):
        raise RuntimeError("official tranche capture aggregate differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(directory / name, pin)


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="official-nordic-iren-import-", dir="/private/tmp"
    ) as temporary:
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
            "entities": 8,
            "entity_snapshots": 8,
            "evidence": 9,
            "lifecycle_observations": 4,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 2,
        }
        if counts != expected:
            raise RuntimeError(f"official tranche import counts differ: {counts!r}")
        return counts


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def _assert_chronology(paths: Sequence[Path], recorded_at: str) -> None:
    threshold = _instant(recorded_at).timestamp()
    for path in paths:
        if path.stat(follow_symlinks=False).st_ctime + 0.000_001 < threshold:
            raise RuntimeError(f"official member ctime predates recorded_at: {path}")


def validate_artifact(
    path: Path = ARTIFACT,
    *,
    source_paths: Mapping[str, Path] | None = None,
    require_live: bool = True,
    require_frozen: bool = True,
    wall_clock: datetime | None = None,
) -> dict[str, Any]:
    paths = source_paths or _source_paths(SOURCES_ROOT)
    records = _validate_sources(paths, require_frozen=require_frozen)
    _collision_witness(expected_source_documents())
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError("official artifact must be an ordinary directory")
    wanted_root = 0o555 if require_frozen else 0o700
    if stat.S_IMODE(path.stat().st_mode) != wanted_root:
        raise RuntimeError("official artifact root mode differs")
    entries = {entry.name: entry for entry in path.iterdir()}
    wanted_member = 0o444 if require_frozen else 0o600
    if set(entries) != CLOSED_FILES or any(
        entry.is_symlink()
        or not entry.is_file()
        or stat.S_IMODE(entry.stat().st_mode) != wanted_member
        for entry in entries.values()
    ):
        raise RuntimeError("official artifact member contract differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if (
        manifest_raw != _canonical(manifest)
        or manifest.get("artifact_id") != ARTIFACT_ID
        or manifest.get("curated_source_records") != 4
        or manifest.get("candidate_assessments") != 12
        or manifest.get("review_only_candidates") != 8
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise RuntimeError("official manifest contract differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (
            row["bytes"],
            row["sha256"],
        ):
            raise RuntimeError(f"official manifest pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text() != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise RuntimeError("official manifest checksum differs")
    expected_payloads = _artifact_documents(
        manifest["recorded_at"], expected_source_documents()
    )
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected_payloads[name]:
            raise RuntimeError(f"official artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text())
    if snapshot["source_records"] != records:
        raise RuntimeError("official source pins differ")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise RuntimeError("wall clock must be timezone aware")
    if require_live and now.astimezone(UTC) < target:
        raise RuntimeError("official recorded_at is not live")
    if _instant(RETRIEVED_AT) > target:
        raise RuntimeError("official capture post-dates recorded_at")
    replay = [_offline_import(paths, manifest["recorded_at"]) for _ in range(2)]
    if replay[0] != replay[1]:
        raise RuntimeError("official offline replay differs")
    if require_frozen:
        _assert_chronology(
            [path, *entries.values(), *paths.values()], manifest["recorded_at"]
        )
    return manifest


def _write_source_stage(
    stage: Path, documents: Mapping[str, Mapping[str, Any]]
) -> None:
    for name in SOURCE_FILENAMES:
        path = stage / name
        path.write_bytes(_canonical(documents[name]))
        path.chmod(0o600)
        _fsync_regular(path)
    _fsync_directory(stage)


def _write_artifact_stage(
    stage: Path, recorded_at: str, documents: Mapping[str, Mapping[str, Any]]
) -> None:
    payloads = _artifact_documents(recorded_at, documents)
    for name in CONTENT_FILES:
        path = stage / name
        path.write_bytes(payloads[name])
        path.chmod(0o600)
        _fsync_regular(path)
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
        "candidate_assessments": 12,
        "curated_source_records": 4,
        "seed_eligible_candidates": 4,
        "review_only_candidates": 8,
        "successful_http_200_body_captures": 17,
        "raw_capture_redistributed": False,
        "raw_capture_moved_after_successful_live_validation": True,
        "all_member_and_root_ctimes_at_or_after_recorded_at": True,
        "regional_completeness_claimed": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
    }
    manifest_path = stage / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    manifest_path.chmod(0o600)
    _fsync_regular(manifest_path)
    sidecar = stage / "manifest.sha256"
    sidecar.write_text(f"{_sha256(manifest_path)}  manifest.json\n")
    sidecar.chmod(0o600)
    _fsync_regular(sidecar)
    stage.chmod(0o700)
    _fsync_directory(stage)


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise RuntimeError("active official publication lock exists") from error
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
            if (current.st_dev, current.st_ino) != identity:
                raise RuntimeError("refusing substituted official lock cleanup")
            PUBLICATION_LOCK.unlink()


@dataclass(frozen=True)
class _Prepared:
    source_stage: Path
    artifact_stage: Path
    recorded_at: str


def _prepare(recorded_at: str) -> _Prepared:
    if (
        ARTIFACT.exists()
        or ARTIFACT.is_symlink()
        or any(
            (SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
    ):
        raise RuntimeError("official tranche final-path collision")
    capture = resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(capture)
    documents = expected_source_documents()
    _collision_witness(documents)
    source_stage = Path(
        tempfile.mkdtemp(prefix=".official-nordic-iren-sources.", dir=SOURCES_ROOT)
    )
    artifact_stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT)
    )
    try:
        _write_source_stage(source_stage, documents)
        _write_artifact_stage(artifact_stage, recorded_at, documents)
        validate_artifact(
            artifact_stage,
            source_paths=_source_paths(source_stage),
            require_live=False,
            require_frozen=False,
            wall_clock=_instant(recorded_at),
        )
        return _Prepared(source_stage, artifact_stage, recorded_at)
    except Exception:
        if source_stage.exists():
            shutil.rmtree(source_stage)
        if artifact_stage.exists():
            shutil.rmtree(artifact_stage)
        raise


def _freeze_after_barrier(prepared: _Prepared) -> None:
    target = _instant(prepared.recorded_at)
    while datetime.now(UTC) < target:
        time.sleep(min(0.25, (target - datetime.now(UTC)).total_seconds()))
    for name in SOURCE_FILENAMES:
        path = prepared.source_stage / name
        path.chmod(0o444)
        _fsync_regular(path)
    for path in prepared.artifact_stage.iterdir():
        path.chmod(0o444)
        _fsync_regular(path)
    prepared.artifact_stage.chmod(0o555)
    _fsync_directory(prepared.source_stage)
    _fsync_directory(prepared.artifact_stage)
    _assert_chronology(
        [
            prepared.artifact_stage,
            *prepared.artifact_stage.iterdir(),
            *prepared.source_stage.iterdir(),
        ],
        prepared.recorded_at,
    )


def _publish(prepared: _Prepared) -> None:
    _freeze_after_barrier(prepared)
    if (
        ARTIFACT.exists()
        or ARTIFACT.is_symlink()
        or any(
            (SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
    ):
        raise RuntimeError("late official tranche final-path collision")
    promoted: list[tuple[Path, Path, tuple[int, int], bool]] = []
    try:
        for name in SOURCE_FILENAMES:
            staged = prepared.source_stage / name
            final = SOURCES_ROOT / name
            identity = _identity(staged, directory=False)
            _promote_noreplace(staged, final)
            if not _has_identity(final, identity, directory=False):
                raise RuntimeError(f"promoted source identity differs: {final}")
            promoted.append((final, staged, identity, False))
        identity = _identity(prepared.artifact_stage, directory=True)
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        if not _has_identity(ARTIFACT, identity, directory=True):
            raise RuntimeError("promoted artifact identity differs")
        promoted.append((ARTIFACT, prepared.artifact_stage, identity, True))
    except BaseException as error:
        for final, staged, identity, directory in reversed(promoted):
            try:
                if not _has_identity(final, identity, directory=directory):
                    raise RuntimeError(
                        f"refusing identity-mismatched rollback: {final}"
                    )
                _promote_noreplace(final, staged)
            except Exception as rollback_error:
                error.add_note(
                    f"official rollback failed for {final}: {rollback_error}"
                )
        raise


def _move_capture_to_trash() -> None:
    if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
        raise RuntimeError("both raw origin and Trash destination exist")
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH))


def _result(manifest: Mapping[str, Any], status_value: str) -> dict[str, Any]:
    return {
        "artifact": str(ARTIFACT),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "capture_trash": str(CAPTURE_TRASH),
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "recorded_at": manifest["recorded_at"],
        "source_records": 4,
        "unique_entities": 8,
        "evidence_records": 9,
        "lifecycle_observations": 4,
        "capacity_estimates": 2,
        "operating_model_observations": 0,
        "workload_observations": 0,
        "review_only_candidates": 8,
        "status": status_value,
    }


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    if ARTIFACT.exists() and all(
        (SOURCES_ROOT / name).exists() for name in SOURCE_FILENAMES
    ):
        manifest = validate_artifact()
        _move_capture_to_trash()
        return _result(manifest, "existing-identical")
    if (
        ARTIFACT.exists()
        or ARTIFACT.is_symlink()
        or any(
            (SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
    ):
        raise RuntimeError("partial official tranche final-path collision")
    target = (
        _instant(recorded_at)
        if recorded_at
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise RuntimeError("official recorded_at must be future before staging")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    with _publication_lock():
        prepared = _prepare(timestamp)
        _publish(prepared)
        manifest = validate_artifact()
        _move_capture_to_trash()
        manifest = validate_artifact()
        if any(prepared.source_stage.iterdir()):
            raise RuntimeError("official source stage not empty")
        prepared.source_stage.rmdir()
    return _result(manifest, "published")


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
