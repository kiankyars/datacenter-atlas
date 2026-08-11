"""Publish a governed six-candidate official current-build gap tranche.

Five seed records are emitted from six candidate assessments.  Palm Coast is
held behind a facility-type schema boundary and Fort Worth is held because the
official page supplies only an anonymous count.  Raw response bytes remain
all-rights-reserved and are represented in the artifact only by exact hashes
and compact factual extracts.
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
from . import global_official_builds_six_candidate_20260721 as publication
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "global-official-current-build-gap-2026-07-21-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".global-official-current-build-gap.lock"

CAPTURE_ORIGIN = Path("/private/tmp/dc-official-current-build-20260721.4OxM11")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-official-current-build-20260721.4OxM11")
CAPTURE_FILE_COUNT = 18
CAPTURE_TOTAL_BYTES = 5_041_791
CAPTURE_TREE_SHA256 = "f81abe4c6fe0133242b09f70b28a244b5059c34f34f036ffec55fc57dc06ef21"

V87_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v87.json"
V87_RELEASE = ROOT / "releases/2026-07-21-open-seed-v87"
V87_MANIFEST = V87_RELEASE / "manifest.json"
V87_ENTITIES = V87_RELEASE / "entities.csv"
V87_PINS = {
    V87_DEFINITION: (
        103_031,
        "bf0ef1b6bbe9f4f7edb4525de89d487de1e03ed5eaaccc1a0e122e24d5c9bf08",
    ),
    V87_MANIFEST: (
        15_566,
        "6b2787e982049f1bcab139fce874880499c8610e2e71bb6bde091bcc101abf35",
    ),
    V87_ENTITIES: (
        984_920,
        "1d214eba7d0482dae402930cfa5eb1b6e26b3df6a60c27571670c0929c8f02dc",
    ),
}
V87_TREE_SHA256 = "02be747070df5f998080ca7c54a94146649a54b84078850c4c31522ae05c6185"
V87_INPUT_COUNT = 456

SOURCE_FILENAMES = (
    "curated-official-2026-07-21-dataone-vineland-phase-1-current-build.json",
    "curated-official-2026-07-21-dataone-vineland-phase-2-current-build.json",
    "curated-official-2026-07-21-core-scientific-denton-conversion-current-build.json",
    "curated-official-2026-07-21-webster-county-rifle-range-road-current-build.json",
    "curated-official-2026-07-21-rowan-quantum-frederick-current-build.json",
)
CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

OfficialCurrentBuildGapError = publication.OfficialBuildsError
_canonical = publication._canonical
_sha256 = publication._sha256
_sha256_bytes = publication._sha256_bytes
_instant = publication._instant
_pin = publication._pin
_fsync_regular = publication._fsync_regular
_fsync_directory = publication._fsync_directory
_promote_noreplace = publication._promote_noreplace


CAPTURE_FILE_PINS: dict[str, tuple[int, str]] = {
    "core-denton-headers.txt": (
        841,
        "61f8c0218cbddd5e19ae7f64fc8e77c54a8c3d7b44a574a74f6fa08feb1e91c8",
    ),
    "core-denton-sec-headers.txt": (
        662,
        "47fa60f73004b69cc4612265d5908c5cdddb6acdfea1527e25b65eb9c5046d99",
    ),
    "core-denton-sec.body": (
        110_893,
        "5f4f71a85f2e2c7ec56fdfefd1c78c9fcb96f1887468a1dc71a4b5efdec86068",
    ),
    "core-denton.body": (
        121_439,
        "2796f81902f02bd00d4ea70042c68345bca5196a2ac8d94247ed49d23d160772",
    ),
    "fort-worth-headers.txt": (
        1_100,
        "3d128ea576e0b162c84f0280976c4859373c0a2f168ba4559cfac994ef494663",
    ),
    "fort-worth.body": (
        161_623,
        "afadfe39877209168711cb7245b7eb9372027fbdfcf576c329ecb320bb813492",
    ),
    "maryland-headers.txt": (
        1_712,
        "42fce1c0a892c9d1a450fcd6d383a1687e0bb20ec8a5baf70bac151aa2251cfe",
    ),
    "maryland.body": (
        1_408_338,
        "dcbee96c8d30ffb38e2aa713e98dc45fa505b73163d55f24b0c28bbe25da1168",
    ),
    "nebius-headers.txt": (
        7_525,
        "8a845e1fc7786d01036fa3ad190bd60c342cac726c968911d4844bdb3a1a7017",
    ),
    "nebius.body": (
        298_222,
        "1a636c8260f8af9381a1f6a66bbb25fd5db4ce4f0e9467961ed4e12fa798d315",
    ),
    "palm-coast-headers.txt": (
        138,
        "00752b9e346cab23c1c1f0d3a65c090f5a3062f788a39a08c25861fccd6cbeaf",
    ),
    "palm-coast.body": (
        242_500,
        "421de378926b04907fce54d6200ba40856b2df1a93b9cbb9c0e013812845bc66",
    ),
    "vineland-headers.txt": (
        2_860,
        "6ef36191ff29a704cee12366808816a381dc027bdd0c9318728f3d27365863cb",
    ),
    "vineland-newsletter-headers.txt": (
        2_861,
        "43b5c49624d75a4808aeca1278de7c2f8cb571e6dfe9457eedf95b973ecdf119",
    ),
    "vineland-newsletter.body": (
        2_416_725,
        "9f44e8df4efcfc6ce345e46de9644d56f78d95967ca5c43332982363aeda660b",
    ),
    "vineland.body": (
        172_126,
        "c5ae1163c6f0dca86a81332c45bfedbba5654630ba9f829e44ebfc59fc52ccbe",
    ),
    "webster-headers.txt": (
        820,
        "468c56dad21614ac233ee148d9abe3a3e7fc2860c217387b233b2a691840812b",
    ),
    "webster.body": (
        91_406,
        "c1b2c82372256c25251766d7c55bea5743b2ac65f4b0a6fd996d5cc27d34e3c9",
    ),
}


CAPTURES: dict[str, dict[str, Any]] = {
    "vineland_agenda": {
        "body": "vineland.body",
        "headers": "vineland-headers.txt",
        "url": "https://www.vinelandcity.org/Archive/Planning%20Board/Agendas/2026/Agenda%203-26-26%20%28Special%20Meeting%29.pdf",
        "effective_url": "https://www.vinelandcity.org/Archive/Planning%20Board/Agendas/2026/Agenda%203-26-26%20%28Special%20Meeting%29.pdf",
        "retrieved_at": "2026-07-22T00:26:59Z",
        "published_at": "2026-03-23",
        "http_status": 200,
        "content_type": "application/pdf",
        "use": "normalized",
    },
    "vineland_newsletter": {
        "body": "vineland-newsletter.body",
        "headers": "vineland-newsletter-headers.txt",
        "url": "https://www.vinelandcity.org/wp-content/uploads/2025/04/Vineland-News-April-2025-nc.pdf",
        "effective_url": "https://www.vinelandcity.org/wp-content/uploads/2025/04/Vineland-News-April-2025-nc.pdf",
        "retrieved_at": "2026-07-22T00:30:11Z",
        "published_at": "2025-04-24",
        "http_status": 200,
        "content_type": "application/pdf",
        "use": "normalized_metadata",
    },
    "nebius": {
        "body": "nebius.body",
        "headers": "nebius-headers.txt",
        "url": "https://nebius.com/blog/posts/300-mw-new-jersey-and-iceland-regions",
        "effective_url": "https://nebius.com/blog/posts/300-mw-new-jersey-and-iceland-regions",
        "retrieved_at": "2026-07-22T00:26:59Z",
        "published_at": "2025-03-05",
        "http_status": 200,
        "content_type": "text/html; charset=utf-8",
        "use": "normalized_metadata",
    },
    "core_sec": {
        "body": "core-denton-sec.body",
        "headers": "core-denton-sec-headers.txt",
        "url": "https://www.sec.gov/Archives/edgar/data/1839341/000119312526165121/d149019dex992.htm",
        "effective_url": "https://www.sec.gov/Archives/edgar/data/1839341/000119312526165121/d149019dex992.htm",
        "retrieved_at": "2026-07-22T00:30:43Z",
        "published_at": "2026-04-21",
        "http_status": 200,
        "content_type": "text/html",
        "use": "normalized",
    },
    "core_ir_mirror": {
        "body": "core-denton.body",
        "headers": "core-denton-headers.txt",
        "url": "https://investors.corescientific.com/sec-filings/all-sec-filings/content/0001193125-26-165121/d149019dex992.htm",
        "effective_url": "https://investors.corescientific.com/sec-filings/all-sec-filings/content/0001193125-26-165121/d149019dex992.htm",
        "retrieved_at": "2026-07-22T00:26:59Z",
        "published_at": "2026-04-21",
        "http_status": 200,
        "content_type": "text/html; charset=UTF-8",
        "use": "alternate_hash_witness_only",
    },
    "webster": {
        "body": "webster.body",
        "headers": "webster-headers.txt",
        "url": "https://webstercountymo.gov/commission-data-center-update-may-21/",
        "effective_url": "https://webstercountymo.gov/commission-data-center-update-may-21/",
        "retrieved_at": "2026-07-22T00:26:59Z",
        "published_at": "2026-05-21",
        "http_status": 200,
        "content_type": "text/html; charset=UTF-8",
        "use": "normalized",
    },
    "maryland": {
        "body": "maryland.body",
        "headers": "maryland-headers.txt",
        "url": "https://planning.maryland.gov/SiteAssets/Pages/OurEngagement/PermitCouncil/PermitCouncil-reports/20260415-Permitting-Council-Quarterly-Report-FY26Q3.pdf",
        "effective_url": "https://planning.maryland.gov/SiteAssets/Pages/OurEngagement/PermitCouncil/PermitCouncil-reports/20260415-Permitting-Council-Quarterly-Report-FY26Q3.pdf",
        "retrieved_at": "2026-07-22T00:26:59Z",
        "published_at": "2026-04-15",
        "http_status": 200,
        "content_type": "application/pdf",
        "use": "normalized",
    },
    "palm_coast": {
        "body": "palm-coast.body",
        "headers": "palm-coast-headers.txt",
        "url": "https://www.palmcoast.gov/newsroom/home/details/approved-scope-of-dc-blox",
        "effective_url": "https://www.palmcoast.gov/newsroom/home/details/approved-scope-of-dc-blox",
        "retrieved_at": "2026-07-22T00:26:59Z",
        "published_at": "2026-06-19",
        "http_status": 200,
        "content_type": "text/html; charset=utf-8",
        "use": "review_only",
    },
    "fort_worth": {
        "body": "fort-worth.body",
        "headers": "fort-worth-headers.txt",
        "url": "https://www.fortworthtexas.gov/departments/city-manager/datacenters",
        "effective_url": "https://www.fortworthtexas.gov/departments/city-manager/datacenters",
        "retrieved_at": "2026-07-22T00:26:59Z",
        "published_at": "2026-07-21",
        "http_status": 200,
        "content_type": "text/html; charset=utf-8",
        "use": "review_only",
    },
}


VINELAND_AGENDA_EVIDENCE = "vineland-planning-board-dataone-current-build-captured-2026-07-21"
VINELAND_NEWSLETTER_EVIDENCE = "vineland-newsletter-dataone-nebius-link-captured-2026-07-21"
NEBIUS_EVIDENCE = "nebius-new-jersey-300mw-future-context-captured-2026-07-21"
CORE_DENTON_EVIDENCE = "core-scientific-denton-sec-exhibit-captured-2026-07-21"
WEBSTER_EVIDENCE = "webster-county-rifle-range-current-build-captured-2026-07-21"
ROWAN_EVIDENCE = "maryland-quantum-frederick-rowan-current-build-captured-2026-07-21"

VINELAND_CAMPUS = "curated:dataone-vineland-ai-data-center-campus"
VINELAND_PHASE_1 = f"{VINELAND_CAMPUS}:phase-1-current-build"
VINELAND_PHASE_2 = f"{VINELAND_CAMPUS}:phase-2-expansion-current-build"
DENTON_CAMPUS = "epoch-ai:data-center:9b244849-c931-5ed2-b694-3f43509cf198"
DENTON_PROJECT = f"{DENTON_CAMPUS}:2024-2026-hpc-conversion-current-build"
WEBSTER_CAMPUS = "curated:webster-county-rifle-range-road-unnamed-data-center"
WEBSTER_PROJECT = f"{WEBSTER_CAMPUS}:may-2026-current-build"
ROWAN_CAMPUS = "curated:rowan-quantum-frederick-source-scoped-facility"
ROWAN_PROJECT = f"{ROWAN_CAMPUS}:current-build"


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
    body_bytes, body_sha = CAPTURE_FILE_PINS[capture["body"]]
    header_bytes, header_sha = CAPTURE_FILE_PINS[capture["headers"]]
    record = {
        "content_hash_scope": (
            f"SHA-256 of the exact {body_bytes}-byte content-decoded "
            "credential-free public response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_headers_scope": (
            f"SHA-256 of the exact {header_bytes}-byte raw HTTP response-header capture"
        ),
        "capture_headers_sha256": header_sha,
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture_id,
        "capture_method": "credential_free_curl_location_compressed",
        "http_status": capture["http_status"],
        "content_type": capture["content_type"],
        "requested_url": capture["url"],
        "effective_url": capture["effective_url"],
        "request_credentials_supplied": False,
        "rights_scope": (
            "Compact factual extraction from all-rights-reserved official bytes; "
            "raw bodies, headers, telemetry, and publisher media are not redistributed."
        ),
        "status_semantics": "dated_last_observed_current_status_unknown",
        "imagery_guardrail": (
            "No publisher image, satellite image, aerial image, computer vision, "
            "map click, or analyst geolocation contributes to a normalized claim."
        ),
    }
    record.update(metadata)
    return {
        "key": key,
        "kind": kind,
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
        "metadata": record,
    }


def _vineland_agenda_evidence() -> dict[str, Any]:
    return _evidence(
        "vineland_agenda",
        key=VINELAND_AGENDA_EVIDENCE,
        kind="government_record",
        title="Vineland Planning Board DataOne special-meeting notice",
        publisher="City of Vineland Planning Board",
        source_family="vineland_planning_board",
        excerpt=(
            "The notice describes DataOne USA LLC Phase 1 and Phase 2 data-center "
            "buildings as currently under construction at Lincoln and Sheridan."
        ),
        metadata={
            "http_last_modified": "2026-03-23T20:23:55Z",
            "publication_date_basis": "HTTP Last-Modified; the notice schedules a March 26 hearing.",
            "application_as_reported": "DataOne USA LLC - 2nd Amended, Project PBA-26-00001",
            "parcel_as_reported": "Block 7503, Lots 35.01 and 33.01, Tax Map Sheet 75",
            "location_as_reported": "southeasterly corner of Lincoln Avenue and Sheridan Avenue",
            "phase_1_as_reported": "129,622 square foot AI Data Center Building (currently under construction)",
            "phase_2_as_reported": "587,980 square foot two-story expansion to the existing Phase 1 building (currently under construction)",
            "postponement_guardrail": (
                "The application hearing was postponed tentatively to May 28, 2026. "
                "That procedural notice neither advances nor negates the document's "
                "explicit last-observed physical-status wording."
            ),
            "phase_boundary": "Two distinct project rows share one internal campus container; neither is added to the other.",
            "ancillary_guardrail": (
                "Power-generation, chiller, administration, LNG, water-treatment, and "
                "other ancillary structures create no separate data-center entity, "
                "generation, load, capacity, fuel, energy, PUE, WUE, or geometry row."
            ),
            "classification_guardrail": "AI wording is retained as source text only and creates no normalized workload or facility type.",
            "coordinate_guardrail": "The official intersection and parcel text create no point, polygon, footprint, or coordinate.",
        },
    )


def _vineland_newsletter_evidence() -> dict[str, Any]:
    return _evidence(
        "vineland_newsletter",
        key=VINELAND_NEWSLETTER_EVIDENCE,
        kind="government_record",
        title="Vineland News April 2025 DataOne project article",
        publisher="City of Vineland",
        source_family="city_of_vineland_newsletter",
        excerpt=(
            "The city newsletter links DataOne's South Lincoln and Sheridan project "
            "to a first phase expected to be occupied by Nebius."
        ),
        metadata={
            "http_last_modified": "2025-04-24T17:30:50Z",
            "identity_link_as_reported": (
                "DataOne announced a data center near South Lincoln and Sheridan; "
                "the first phase was expected to be occupied by Nebius."
            ),
            "role_guardrail": (
                "The article supports the cross-source project link only. It creates "
                "no standardized owner, operator, developer, customer, user, or tenant role."
            ),
            "forecast_guardrail": "The forecast first-phase completion and occupancy create no later lifecycle observation.",
            "capacity_guardrail": "The article's 300 MW whole-site label remains non-additive future metadata only.",
        },
    )


def _nebius_evidence() -> dict[str, Any]:
    return _evidence(
        "nebius",
        key=NEBIUS_EVIDENCE,
        kind="company_disclosure",
        title="Nebius 300 MW New Jersey region announcement",
        publisher="Nebius",
        source_family="nebius_blog",
        excerpt=(
            "Nebius describes its DataOne New Jersey collaboration as a phased site "
            "expandable up to a total of 300 MW."
        ),
        metadata={
            "future_untyped_capacity_as_reported": "site expandable up to a total of 300 MW",
            "capacity_guardrail": (
                "The 300 MW label is future whole-site potential without a metric-safe "
                "phase allocation. It creates no capacity, current-load, consumption, "
                "energy, generation, PUE, or WUE row."
            ),
            "workload_guardrail": "AI-cloud and customer language creates no normalized workload, hardware, model, customer, user, or utilization observation.",
            "microsoft_guardrail": "This source creates no Microsoft role or relationship claim.",
            "forecast_guardrail": "Go-live and installed-capacity forecasts create no completion, commissioning, energization, occupancy, or operation observation.",
        },
    )


def _core_denton_evidence() -> dict[str, Any]:
    return _evidence(
        "core_sec",
        key=CORE_DENTON_EVIDENCE,
        kind="company_disclosure",
        title="Core Scientific April 2026 Exhibit 99.2 - Denton Campus",
        publisher="Core Scientific, Inc.",
        source_family="sec_edgar_core_scientific_exhibit",
        excerpt=(
            "The SEC-hosted exhibit identifies the eight-building Denton campus, says "
            "work commenced in Q3 2024, and expects substantial completion in H2 2026."
        ),
        metadata={
            "sec_accession": "0001193125-26-165121",
            "sec_cik": "0001839341",
            "sec_document": "d149019dex992.htm",
            "address_as_reported": "8171 Jim Christal Road, Denton, Texas",
            "building_count_as_reported": 8,
            "physical_status_as_reported": "work commenced in the third quarter of 2024",
            "completion_forecast_as_reported": "substantial completion expected in the second half of 2026",
            "status_scope": (
                "The April 21 disclosure supports one last-observed under-construction "
                "conversion project. It does not confirm current status after that date."
            ),
            "critical_it_as_reported": "262 MW Denton campus allocation within contracted net critical IT capacity",
            "grid_as_reported": "DME Contract for total potential campus load of approximately 394 MW",
            "capacity_scope": (
                "262 MW is normalized once as project critical_it_mw at design stage; "
                "394 MW is normalized once on the exact existing campus as contracted "
                "grid_connection_mw at total-potential-campus scope."
            ),
            "partial_operation_guardrail": (
                "The approximate 132 MW operational subset creates no operational-capacity "
                "row and is not subtracted from either normalized value."
            ),
            "workload_guardrail": "HPC, AI, cryptocurrency, and CoreWeave language creates no normalized workload, tenant, customer, user, hardware, or utilization observation.",
            "collision_resolution": (
                f"The exact v87 address match reuses campus stable key {DENTON_CAMPUS}; "
                "only the conversion work scope is a new project entity."
            ),
            "coordinate_guardrail": "No coordinate or geometry is copied from v87 into the new source record or inferred from the address.",
        },
    )


def _webster_evidence() -> dict[str, Any]:
    return _evidence(
        "webster",
        key=WEBSTER_EVIDENCE,
        kind="government_record",
        title="Webster County Commission data center update - May 21",
        publisher="Webster County Commission",
        source_family="webster_county_commission",
        excerpt=(
            "The county reports an unnamed data center project currently under "
            "construction on Rifle Range Road northeast of Marshfield."
        ),
        metadata={
            "location_as_reported": "Rifle Range Road in rural Webster County, north and east of the City of Marshfield",
            "identity_scope": "A source-scoped generic project identity only; the official page names no operator, owner, developer, campus, or facility code.",
            "collision_scope": "No v87 entity contains Webster County, Rifle Range Road, or Marshfield as a data-center identity or address.",
            "capacity_guardrail": "The page provides no metric-safe capacity, load, energy, generation, PUE, or WUE value.",
            "coordinate_guardrail": "The broad road and county locality create no coordinate, parcel, point, footprint, or geometry.",
        },
    )


def _rowan_evidence() -> dict[str, Any]:
    return _evidence(
        "maryland",
        key=ROWAN_EVIDENCE,
        kind="government_record",
        title="Maryland FY26 Q3 Permitting Council report - Quantum Frederick",
        publisher="Maryland Coordinated Permitting Review Council",
        source_family="maryland_permitting_council",
        excerpt=(
            "The report says Aligned and Rowan facilities at Quantum Frederick are "
            "currently under construction and both companies are actively constructing."
        ),
        metadata={
            "location_as_reported": "Quantum Frederick, a 2,100-acre campus in Frederick County, Maryland",
            "physical_status_as_reported": "Aligned and Rowan facilities are currently under construction",
            "identity_scope": (
                "One generic source-scoped Rowan project is created. Aligned IAD-06 is "
                "already represented and receives no duplicate or lifecycle update."
            ),
            "collision_scope": (
                "No v87 entity contains Rowan as a data-center identity. Existing Aligned "
                "Frederick rows remain distinct and unmerged."
            ),
            "role_guardrail": "The report creates no standardized owner, operator, developer, tenant, customer, or user role for Rowan.",
            "capacity_guardrail": "The report provides no metric-safe Rowan capacity, load, energy, generation, PUE, or WUE value.",
            "coordinate_guardrail": "No coordinate, parcel, point, footprint, or geometry is inferred from Quantum Frederick context.",
        },
    )


def _entity(
    *, stable_key: str, name: str, address: str, evidence_key: str, as_of_date: str
) -> dict[str, Any]:
    return {
        "stable_key": stable_key,
        "name": name,
        "country": "United States",
        "address": address,
        "roles": {},
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


def _capacity(
    *, entity: str, metric: str, stage: str, base: float, evidence_key: str, notes: str
) -> dict[str, Any]:
    return {
        "entity": entity,
        "metric": metric,
        "stage": stage,
        "unit": "MW",
        "low": base,
        "base": base,
        "high": base,
        "method": "reported",
        "confidence": 0.99,
        "evidence_key": evidence_key,
        "as_of_date": "2026-04-21",
        "target_date": None,
        "notes": notes,
    }


def _vineland_source(phase: int) -> dict[str, Any]:
    if phase not in {1, 2}:
        raise OfficialCurrentBuildGapError("unsupported Vineland phase")
    project_key = VINELAND_PHASE_1 if phase == 1 else VINELAND_PHASE_2
    project_name = (
        "DataOne Vineland Phase 1 Current Build"
        if phase == 1
        else "DataOne Vineland Phase 2 Expansion Current Build"
    )
    address = (
        "Southeast corner of Lincoln Avenue and Sheridan Avenue, Block 7503, "
        "Lots 35.01 and 33.01, Vineland, New Jersey, United States"
    )
    return {
        "schema_version": "1.1",
        "evidence": [
            _vineland_agenda_evidence(),
            _vineland_newsletter_evidence(),
            _nebius_evidence(),
        ],
        "campus": _entity(
            stable_key=VINELAND_CAMPUS,
            name="DataOne Vineland Two-Phase AI Data Center Facility",
            address=address,
            evidence_key=VINELAND_AGENDA_EVIDENCE,
            as_of_date="2026-03-23",
        ),
        "project": _entity(
            stable_key=project_key,
            name=project_name,
            address=address,
            evidence_key=VINELAND_AGENDA_EVIDENCE,
            as_of_date="2026-03-23",
        ),
        "lifecycle": [_lifecycle(VINELAND_AGENDA_EVIDENCE, "2026-03-23")],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _denton_source() -> dict[str, Any]:
    address = "8171 Jim Christal Road, Denton, Texas 76207, United States"
    return {
        "schema_version": "1.1",
        "evidence": [_core_denton_evidence()],
        "campus": _entity(
            stable_key=DENTON_CAMPUS,
            name="Core Scientific Denton Campus",
            address=address,
            evidence_key=CORE_DENTON_EVIDENCE,
            as_of_date="2026-04-21",
        ),
        "project": _entity(
            stable_key=DENTON_PROJECT,
            name="Core Scientific Denton Multi-Building HPC Conversion",
            address=address,
            evidence_key=CORE_DENTON_EVIDENCE,
            as_of_date="2026-04-21",
        ),
        "lifecycle": [_lifecycle(CORE_DENTON_EVIDENCE, "2026-04-21")],
        "operating_models": [],
        "workloads": [],
        "capacities": [
            _capacity(
                entity="project",
                metric="critical_it_mw",
                stage="design",
                base=262.0,
                evidence_key=CORE_DENTON_EVIDENCE,
                notes=(
                    "Reported Denton project critical-IT design allocation; not current "
                    "load, measured consumption, gross demand, generation, or remaining MW."
                ),
            ),
            _capacity(
                entity="campus",
                metric="grid_connection_mw",
                stage="contracted",
                base=394.0,
                evidence_key=CORE_DENTON_EVIDENCE,
                notes=(
                    "Approximate reported total-potential-campus load under the DME power "
                    "purchase agreement; the 394 MW anchor is not precision, current draw, "
                    "critical IT, generation, annual energy, or evidence of energization."
                ),
            ),
        ],
    }


def _webster_source() -> dict[str, Any]:
    address = (
        "Rifle Range Road, rural Webster County northeast of Marshfield, "
        "Missouri, United States"
    )
    return {
        "schema_version": "1.1",
        "evidence": [_webster_evidence()],
        "campus": _entity(
            stable_key=WEBSTER_CAMPUS,
            name="Unnamed Webster County Rifle Range Road Data Center",
            address=address,
            evidence_key=WEBSTER_EVIDENCE,
            as_of_date="2026-05-21",
        ),
        "project": _entity(
            stable_key=WEBSTER_PROJECT,
            name="Unnamed Webster County Data Center Current Build",
            address=address,
            evidence_key=WEBSTER_EVIDENCE,
            as_of_date="2026-05-21",
        ),
        "lifecycle": [_lifecycle(WEBSTER_EVIDENCE, "2026-05-21")],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _rowan_source() -> dict[str, Any]:
    address = "Quantum Frederick, Frederick County, Maryland, United States"
    return {
        "schema_version": "1.1",
        "evidence": [_rowan_evidence()],
        "campus": _entity(
            stable_key=ROWAN_CAMPUS,
            name="Rowan Quantum Frederick Source-Scoped Facility",
            address=address,
            evidence_key=ROWAN_EVIDENCE,
            as_of_date="2026-04-15",
        ),
        "project": _entity(
            stable_key=ROWAN_PROJECT,
            name="Rowan Quantum Frederick Facility Current Build",
            address=address,
            evidence_key=ROWAN_EVIDENCE,
            as_of_date="2026-04-15",
        ),
        "lifecycle": [_lifecycle(ROWAN_EVIDENCE, "2026-04-15")],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    builders = (
        lambda: _vineland_source(1),
        lambda: _vineland_source(2),
        _denton_source,
        _webster_source,
        _rowan_source,
    )
    return {
        name: builder()
        for name, builder in zip(SOURCE_FILENAMES, builders, strict=True)
    }


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
                "lifecycle_observations": len(document["lifecycle"]),
                "operating_model_observations": 0,
                "workload_observations": 0,
                "capacity_estimates": len(document["capacities"]),
                "coordinates_present": 0,
                "geometry_present": 0,
                "disposition": (
                    "seed_eligible_exact_existing_campus_bound_project"
                    if name == SOURCE_FILENAMES[2]
                    else "seed_eligible_direct_authoritative_physical_update"
                ),
                "seed_eligible": True,
                "seeded": False,
            }
        )
    return rows


def _v87_entity_rows() -> list[dict[str, str]]:
    with V87_ENTITIES.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


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


def _base_collision_witness(
    documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    for path, pin in V87_PINS.items():
        _pin(path, pin)
    if tree_digest(V87_RELEASE) != V87_TREE_SHA256:
        raise OfficialCurrentBuildGapError("v87 release tree differs")
    definition = json.loads(V87_DEFINITION.read_text(encoding="utf-8"))
    selected = definition.get("curated_inputs")
    if not isinstance(selected, list) or len(selected) != V87_INPUT_COUNT:
        raise OfficialCurrentBuildGapError("v87 selected input inventory differs")
    for row in selected:
        path = ROOT / row["path"]
        if path.is_symlink() or not path.is_file() or _sha256(path) != row["sha256"]:
            raise OfficialCurrentBuildGapError(
                f"v87 selected source pin differs: {row['path']}"
            )

    planned_stable, planned_evidence = _planned_keys(documents)
    rows = _v87_entity_rows()
    base_stable = {row["stable_key"] for row in rows}
    stable_intersection = planned_stable & base_stable
    if stable_intersection != {DENTON_CAMPUS}:
        raise OfficialCurrentBuildGapError(
            f"unexpected v87 semantic collision set: {sorted(stable_intersection)!r}"
        )
    denton = [row for row in rows if row["stable_key"] == DENTON_CAMPUS]
    if len(denton) != 1 or (
        denton[0]["entity_kind"],
        denton[0]["name"],
        denton[0]["address"],
    ) != (
        "campus",
        "CoreWeave Denton TX",
        "8171 Jim Christal Rd, Denton, TX 76207",
    ):
        raise OfficialCurrentBuildGapError("Denton exact-address collision witness differs")

    source_inputs = json.loads(
        (V87_RELEASE / "source_inputs.json").read_text(encoding="utf-8")
    ).get("sources")
    if not isinstance(source_inputs, list):
        raise OfficialCurrentBuildGapError("v87 source-input evidence inventory differs")
    base_evidence = {
        key
        for row in source_inputs
        if isinstance(row, dict)
        for key in [row.get("provenance", {}).get("curated_record_key")]
        if isinstance(key, str)
    }
    evidence_intersection = planned_evidence & base_evidence
    if evidence_intersection:
        raise OfficialCurrentBuildGapError(
            f"planned evidence key collides with v87: {sorted(evidence_intersection)!r}"
        )

    def matches(*needles: str) -> list[str]:
        output = []
        for row in rows:
            haystack = " | ".join(
                (row["stable_key"], row["name"], row["address"])
            ).casefold()
            if any(needle.casefold() in haystack for needle in needles):
                output.append(row["stable_key"])
        return sorted(output)

    aliases = {
        "dataone_vineland": matches(
            "dataone", "vineland", "sheridan avenue", "block 7503"
        ),
        "core_denton_exact_address": matches("8171 jim christal"),
        "webster_county": matches(
            "rifle range road", "webster county", "marshfield"
        ),
        "rowan_identity": matches("rowan"),
        "frederick_location_context": sorted(
            row["stable_key"]
            for row in rows
            if row["address"].casefold()
            == "frederick, maryland, united states"
        ),
        "dc_blox_palm_coast": matches("dc blox", "palm coast"),
    }
    expected = {
        "dataone_vineland": [],
        "core_denton_exact_address": [DENTON_CAMPUS],
        "webster_county": [],
        "rowan_identity": [],
        "frederick_location_context": [
            "curated:aligned-quantum-frederick-campus",
            "curated:aligned-quantum-frederick-campus:iad06",
        ],
        "dc_blox_palm_coast": [],
    }
    if aliases != expected:
        raise OfficialCurrentBuildGapError(
            f"v87 semantic alias witness differs: {aliases!r}"
        )
    return {
        "v87_selected_input_count": len(selected),
        "v87_entity_count": len(rows),
        "planned_distinct_stable_keys": len(planned_stable),
        "planned_distinct_evidence_keys": len(planned_evidence),
        "exact_stable_key_collisions": [DENTON_CAMPUS],
        "exact_evidence_key_collisions": [],
        "collision_resolution": (
            "The official Denton record reuses the exact v87 campus stable key after "
            "an exact 8171 Jim Christal Road address match; it creates one child work-"
            "scope project and no duplicate campus."
        ),
        "candidate_alias_matches": aliases,
        "rowan_boundary": (
            "Two Frederick location-context rows are Aligned-only; neither contains "
            "Rowan. The Rowan project remains distinct and no Aligned row is changed."
        ),
        "webster_boundary": (
            "The generic Webster identity is seed-eligible only because no v87 name, "
            "stable key, or address contains Rifle Range Road, Webster County, or Marshfield."
        ),
    }


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    documents = expected_source_documents()
    core = documents[SOURCE_FILENAMES[2]]
    palm_capture = CAPTURES["palm_coast"]
    fort_capture = CAPTURES["fort_worth"]
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-current-build-assessment-v1",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "candidate_count": 6,
        "seed_eligible_candidate_count": 4,
        "seed_eligible_source_record_count": 5,
        "review_only_count": 2,
        "regional_completeness_claimed": False,
        "candidates": [
            {
                "candidate_id": "dataone-vineland-two-phase-current-build",
                "decision": "seed_eligible_two_phase_direct_authoritative_physical_update",
                "source_records_created": 2,
                "source_paths": [
                    f"sources/{SOURCE_FILENAMES[0]}",
                    f"sources/{SOURCE_FILENAMES[1]}",
                ],
                "project_stable_keys": [VINELAND_PHASE_1, VINELAND_PHASE_2],
                "normalized_lifecycle_observations": 2,
                "normalized_capacities": [],
                "future_untyped_metadata": "Nebius says the whole site is expandable up to 300 MW.",
                "withheld": [
                    "300 MW capacity row",
                    "Microsoft role",
                    "actual workload",
                    "current-status extrapolation",
                    "generation or LNG normalization",
                    "coordinates or geometry",
                ],
            },
            {
                "candidate_id": "core-scientific-denton-conversion-current-build",
                "decision": "seed_eligible_exact_existing_campus_bound_project",
                "source_records_created": 1,
                "source_paths": [f"sources/{SOURCE_FILENAMES[2]}"],
                "project_stable_keys": [DENTON_PROJECT],
                "reused_exact_campus_stable_key": DENTON_CAMPUS,
                "normalized_lifecycle_observations": 1,
                "normalized_capacities": core["capacities"],
                "withheld": [
                    "approximately 132 MW operational subset",
                    "derived remaining MW",
                    "current-status extrapolation",
                    "workload or customer normalization",
                    "coordinates or geometry inheritance",
                ],
            },
            {
                "candidate_id": "webster-county-rifle-range-road-unnamed-current-build",
                "decision": "seed_eligible_generic_identity_after_zero_alias_match",
                "source_records_created": 1,
                "source_paths": [f"sources/{SOURCE_FILENAMES[3]}"],
                "project_stable_keys": [WEBSTER_PROJECT],
                "normalized_lifecycle_observations": 1,
                "normalized_capacities": [],
                "withheld": [
                    "operator, owner, developer, capacity, type, coordinate, and geometry"
                ],
            },
            {
                "candidate_id": "rowan-quantum-frederick-current-build",
                "decision": "seed_eligible_distinct_rowan_project",
                "source_records_created": 1,
                "source_paths": [f"sources/{SOURCE_FILENAMES[4]}"],
                "project_stable_keys": [ROWAN_PROJECT],
                "normalized_lifecycle_observations": 1,
                "normalized_capacities": [],
                "withheld": [
                    "IAD-06 duplicate or update",
                    "ownership or standardized role",
                    "capacity, coordinate, or geometry",
                ],
            },
            {
                "candidate_id": "dc-blox-palm-coast-cable-landing-station",
                "decision": "review_only_facility_type_schema_boundary",
                "source_records_created": 0,
                "source_paths": [],
                "seed_eligible": False,
                "official_factual_extract": {
                    "classification": "cable_landing_station",
                    "building_count": 1,
                    "floor_area_square_feet": 33_760,
                    "permit_issued": "2026-04-08",
                    "physical_status": "construction currently underway",
                    "not_hyperscale_or_large_scale": True,
                    "second_building_approved": False,
                },
                "capture": {
                    "url": palm_capture["effective_url"],
                    "body_bytes": CAPTURE_FILE_PINS[palm_capture["body"]][0],
                    "body_sha256": CAPTURE_FILE_PINS[palm_capture["body"]][1],
                },
                "boundary": (
                    "Schema 1.1 cannot preserve cable_landing_station as a facility type "
                    "without placing it in the general data-center entity model. The "
                    "inaccurate two-building/100,000-square-foot statement is rejected."
                ),
            },
            {
                "candidate_id": "fort-worth-council-district-7-anonymous-current-build",
                "decision": "review_only_anonymous_count_level_evidence",
                "source_records_created": 0,
                "source_paths": [],
                "seed_eligible": False,
                "official_factual_extract": {
                    "count": 1,
                    "status": "currently under construction",
                    "location": "Council District 7, Fort Worth city limits",
                    "exact_identity": None,
                },
                "capture": {
                    "url": fort_capture["effective_url"],
                    "body_bytes": CAPTURE_FILE_PINS[fort_capture["body"]][0],
                    "body_sha256": CAPTURE_FILE_PINS[fort_capture["body"]][1],
                },
                "boundary": "Count-level evidence cannot create an invented project identity.",
            },
        ],
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "request_credentials_supplied": False,
        "successful_http_200_body_captures": len(CAPTURES),
        "http_error_header_only_captures": 0,
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
                "effective_url": capture["effective_url"],
                "retrieved_at": capture["retrieved_at"],
                "published_at": capture["published_at"],
                "http_status": capture["http_status"],
                "content_type": capture["content_type"],
                "body": {
                    "path": capture["body"],
                    "bytes": CAPTURE_FILE_PINS[capture["body"]][0],
                    "sha256": CAPTURE_FILE_PINS[capture["body"]][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "headers": {
                    "path": capture["headers"],
                    "bytes": CAPTURE_FILE_PINS[capture["headers"]][0],
                    "sha256": CAPTURE_FILE_PINS[capture["headers"]][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "request_credentials_supplied": False,
                "claim_use": capture["use"],
            }
            for capture_id, capture in CAPTURES.items()
        ],
        "complete_private_file_inventory": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in sorted(CAPTURE_FILE_PINS.items())
        ],
        "alternate_capture_disposition": {
            "capture_id": "core_ir_mirror",
            "basis": (
                "Retained as a hash witness only. The normalized evidence uses the "
                "canonical SEC archive exhibit."
            ),
        },
    }


def _artifact_documents(
    recorded_at: str, source_documents: Mapping[str, Mapping[str, Any]]
) -> dict[str, bytes]:
    collision = _base_collision_witness(source_documents)
    source_records = _source_records(source_documents)
    readme = f"""# Official current-build gap tranche

This immutable artifact assesses six official-source candidates and publishes five seed-eligible source records: two separately bounded DataOne Vineland phases, one Core Scientific Denton conversion project bound to the exact existing v87 campus, one generic unnamed Webster County project, and one distinct Rowan project at Quantum Frederick.

DC Blox Palm Coast remains review-only because the official city source classifies it as a cable landing station and schema 1.1 cannot preserve that type without recasting it as a general data center. The city explicitly says one 33,760-square-foot building, construction underway, no approved second building, and not hyperscale or large-scale; the inaccurate two-building/100,000-square-foot claim is rejected. Fort Worth Council District 7 remains review-only because the official page supplies only an anonymous count.

DataOne's 300 MW label remains future untyped metadata and creates no capacity row. Denton receives exactly 262 MW critical IT at design scope and approximately 394 MW contracted grid connection at total-potential-campus scope; the approximate 132 MW operational subset is neither normalized nor subtracted. No current-status extrapolation, Microsoft role, workload, energy use, PUE, WUE, generation, coordinate, geometry, satellite, or CV inference is made.

All source and artifact bytes were staged before {recorded_at}; final paths were absent until that instant and promoted without replacement. Raw all-rights-reserved captures are represented only by hashes and retrieval facts. The intact {CAPTURE_FILE_COUNT}-file raw capture directory was moved to recoverable Trash only after successful source publication.
"""
    totals = {
        "candidate_assessments": 6,
        "source_records": 5,
        "seed_eligible_candidates": 4,
        "seed_eligible_source_records": 5,
        "review_only_candidates": 2,
        "distinct_campuses_in_source_records": 4,
        "projects": 5,
        "distinct_entities_in_source_records": 9,
        "new_entities_against_v87": 8,
        "reused_exact_entities": 1,
        "source_document_entity_snapshots": 10,
        "unique_imported_entity_snapshots": 9,
        "unique_evidence_records": 6,
        "source_document_evidence_references": 9,
        "lifecycle_observations": 5,
        "operating_model_observations": 0,
        "workload_observations": 0,
        "capacity_estimates": 2,
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
        "frozen_v87_non_mutation_witness": {
            "definition": {
                "path": "sources/open-seed-2026-07-21-v87.json",
                "bytes": V87_PINS[V87_DEFINITION][0],
                "sha256": V87_PINS[V87_DEFINITION][1],
            },
            "release_manifest": {
                "path": "releases/2026-07-21-open-seed-v87/manifest.json",
                "bytes": V87_PINS[V87_MANIFEST][0],
                "sha256": V87_PINS[V87_MANIFEST][1],
            },
            "release_entities": {
                "path": "releases/2026-07-21-open-seed-v87/entities.csv",
                "bytes": V87_PINS[V87_ENTITIES][0],
                "sha256": V87_PINS[V87_ENTITIES][1],
            },
            "release_tree_sha256": V87_TREE_SHA256,
            "new_source_paths_selected_by_v87": False,
            **collision,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v87_mutated": False,
            "release_integration": "none",
            "construction_map_integration": "none",
            "construction_master_integration": "none",
            "construction_timeline_integration": "none",
            "federation_integration": "none",
            "coverage_ledger_integration": "none",
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
        "source_rights": (
            "All captured official response bodies are treated as all-rights-reserved; "
            "no redistribution license was relied on."
        ),
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
        "candidate_dispositions": {
            "seed_eligible_candidates": 4,
            "seed_eligible_source_records": 5,
            "review_only": 2,
        },
    }
    return {
        "README.md": readme.encode(),
        "candidate-assessment.json": _canonical(_candidate_assessment(recorded_at)),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _file_tree(rows: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_bytes(
        (json.dumps(rows, indent=2, sort_keys=True) + "\n").encode()
    )


def _write_source_stage(
    stage: Path, documents: Mapping[str, Mapping[str, Any]]
) -> None:
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
        "candidate_assessments": 6,
        "curated_source_records": 5,
        "seed_eligible_candidates": 4,
        "seed_eligible_source_records": 5,
        "review_only_candidates": 2,
        "successful_http_200_body_captures": len(CAPTURES),
        "http_error_header_only_captures": 0,
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
    sidecar.write_text(
        f"{_sha256(manifest_path)}  manifest.json\n", encoding="utf-8"
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
        raise OfficialCurrentBuildGapError("source path inventory differs")
    for name in SOURCE_FILENAMES:
        path = paths[name]
        if (
            path.is_symlink()
            or not path.is_file()
            or path.read_bytes() != _canonical(expected[name])
            or stat.S_IMODE(path.stat().st_mode) != 0o444
        ):
            raise OfficialCurrentBuildGapError(f"curated source differs: {name}")
    documents = list(expected.values())
    if any(
        document[entity][field] is not None
        for document in documents
        for entity in ("campus", "project")
        for field in ("coordinates", "geometry")
    ):
        raise OfficialCurrentBuildGapError("source invented coordinates or geometry")
    if any(document["workloads"] for document in documents):
        raise OfficialCurrentBuildGapError("source invented workloads")
    if any(document["operating_models"] for document in documents):
        raise OfficialCurrentBuildGapError("source invented operating models")
    if any(
        document[entity]["roles"]
        for document in documents
        for entity in ("campus", "project")
    ):
        raise OfficialCurrentBuildGapError("source invented standardized roles")
    lifecycle = [
        (
            document["project"]["stable_key"],
            document["lifecycle"][0]["value"],
            document["lifecycle"][0]["as_of_date"],
            document["lifecycle"][0]["method"],
        )
        for document in documents
    ]
    expected_lifecycle = [
        (
            VINELAND_PHASE_1,
            "under_construction",
            "2026-03-23",
            "authoritative_physical_status_update",
        ),
        (
            VINELAND_PHASE_2,
            "under_construction",
            "2026-03-23",
            "authoritative_physical_status_update",
        ),
        (
            DENTON_PROJECT,
            "under_construction",
            "2026-04-21",
            "authoritative_physical_status_update",
        ),
        (
            WEBSTER_PROJECT,
            "under_construction",
            "2026-05-21",
            "authoritative_physical_status_update",
        ),
        (
            ROWAN_PROJECT,
            "under_construction",
            "2026-04-15",
            "authoritative_physical_status_update",
        ),
    ]
    if lifecycle != expected_lifecycle:
        raise OfficialCurrentBuildGapError("lifecycle contract differs")
    capacities = sorted(
        (
            document[row["entity"]]["stable_key"],
            row["metric"],
            row["stage"],
            row["base"],
            row["as_of_date"],
        )
        for document in documents
        for row in document["capacities"]
    )
    if capacities != [
        (
            DENTON_CAMPUS,
            "grid_connection_mw",
            "contracted",
            394.0,
            "2026-04-21",
        ),
        (
            DENTON_PROJECT,
            "critical_it_mw",
            "design",
            262.0,
            "2026-04-21",
        ),
    ]:
        raise OfficialCurrentBuildGapError("capacity contract differs")
    assessment = _candidate_assessment("2026-07-22T00:31:00Z")
    decisions = {
        row["candidate_id"]: row["decision"] for row in assessment["candidates"]
    }
    if (
        decisions["dc-blox-palm-coast-cable-landing-station"]
        != "review_only_facility_type_schema_boundary"
        or decisions["fort-worth-council-district-7-anonymous-current-build"]
        != "review_only_anonymous_count_level_evidence"
    ):
        raise OfficialCurrentBuildGapError("review-only boundary differs")
    return _source_records(expected)


def _validate_source_collisions() -> None:
    planned = expected_source_documents()
    _base_collision_witness(planned)
    source_names = set(SOURCE_FILENAMES)
    planned_stable, planned_evidence = _planned_keys(planned)
    collisions: dict[str, dict[str, list[str]]] = {}
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
        evidence = {
            row.get("key")
            for row in document.get("evidence", [])
            if isinstance(row, dict)
        }
        stable_overlap = (planned_stable & stable) - {DENTON_CAMPUS}
        evidence_overlap = planned_evidence & evidence
        if stable_overlap or evidence_overlap:
            collisions[str(path.relative_to(ROOT))] = {
                "stable_keys": sorted(stable_overlap),
                "evidence_keys": sorted(evidence_overlap),
            }
    if collisions:
        raise OfficialCurrentBuildGapError(
            f"source collision detected: {collisions!r}"
        )


def _validate_frozen_witnesses() -> None:
    for path, pin in V87_PINS.items():
        _pin(path, pin)
    if tree_digest(V87_RELEASE) != V87_TREE_SHA256:
        raise OfficialCurrentBuildGapError("v87 release tree differs")
    _base_collision_witness(expected_source_documents())


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise OfficialCurrentBuildGapError(
            f"capture directory is absent or unsafe: {directory}"
        )
    entries = list(directory.iterdir())
    if len(entries) != CAPTURE_FILE_COUNT or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise OfficialCurrentBuildGapError("capture directory closed file set differs")
    if (
        sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES
        or tree_digest(directory) != CAPTURE_TREE_SHA256
    ):
        raise OfficialCurrentBuildGapError("capture directory aggregate differs")
    if set(CAPTURE_FILE_PINS) != {entry.name for entry in entries}:
        raise OfficialCurrentBuildGapError("capture directory names differ")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(directory / name, pin)


def _offline_import(
    paths: Mapping[str, Path], recorded_at: str
) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="official-current-build-gap-import-", dir="/private/tmp"
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
            "entities": 9,
            "entity_snapshots": 9,
            "evidence": 6,
            "lifecycle_observations": 5,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 2,
        }
        if counts != expected:
            raise OfficialCurrentBuildGapError(
                f"offline import counts differ: {counts!r}"
            )
        capacities = {
            tuple(row)
            for row in connection.execute(
                """
                SELECT entities.stable_key, metric, stage, base, as_of_date
                FROM capacity_estimates
                JOIN entities ON entities.id=entity_id
                """
            )
        }
        if capacities != {
            (
                DENTON_PROJECT,
                "critical_it_mw",
                "design",
                262.0,
                "2026-04-21",
            ),
            (
                DENTON_CAMPUS,
                "grid_connection_mw",
                "contracted",
                394.0,
                "2026-04-21",
            ),
        }:
            raise OfficialCurrentBuildGapError("offline capacity contract differs")
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
    if (
        path.is_symlink()
        or not path.is_dir()
        or stat.S_IMODE(path.stat().st_mode) != 0o555
    ):
        raise OfficialCurrentBuildGapError(
            "artifact must be a frozen ordinary directory"
        )
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES or any(
        entry.is_symlink()
        or not entry.is_file()
        or stat.S_IMODE(entry.stat().st_mode) != 0o444
        for entry in entries.values()
    ):
        raise OfficialCurrentBuildGapError("artifact closed frozen file set differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if (
        manifest_raw != _canonical(manifest)
        or manifest.get("artifact_id") != ARTIFACT_ID
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or manifest.get("candidate_assessments") != 6
        or manifest.get("curated_source_records") != 5
        or manifest.get("seed_eligible_candidates") != 4
        or manifest.get("seed_eligible_source_records") != 5
        or manifest.get("review_only_candidates") != 2
        or manifest.get("successful_http_200_body_captures") != len(CAPTURES)
        or manifest.get("http_error_header_only_captures") != 0
        or manifest.get("raw_capture_moved_after_source_publication") is not True
        or manifest.get("regional_completeness_claimed") is not False
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise OfficialCurrentBuildGapError("manifest contract differs")
    if [row["path"] for row in manifest["files"]] != list(CONTENT_FILES):
        raise OfficialCurrentBuildGapError("manifest file order differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (
            row["bytes"],
            row["sha256"],
        ):
            raise OfficialCurrentBuildGapError(
                f"manifest file pin differs: {row['path']}"
            )
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise OfficialCurrentBuildGapError("manifest checksum differs")
    expected = _artifact_documents(
        manifest["recorded_at"], expected_source_documents()
    )
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected[name]:
            raise OfficialCurrentBuildGapError(f"artifact content differs: {name}")
    snapshot = json.loads(
        entries["source-snapshot.json"].read_text(encoding="utf-8")
    )
    if snapshot["source_records"] != source_records:
        raise OfficialCurrentBuildGapError("artifact source pins differ")
    assessment = json.loads(
        entries["candidate-assessment.json"].read_text(encoding="utf-8")
    )
    if (
        assessment.get("candidate_count") != 6
        or assessment.get("seed_eligible_candidate_count") != 4
        or assessment.get("seed_eligible_source_record_count") != 5
        or assessment.get("review_only_count") != 2
    ):
        raise OfficialCurrentBuildGapError("candidate assessment counts differ")

    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise OfficialCurrentBuildGapError("validation wall clock lacks timezone")
    if require_live and now.astimezone(UTC) < target:
        raise OfficialCurrentBuildGapError("artifact recorded_at is not live")
    for capture in CAPTURES.values():
        if _instant(capture["retrieved_at"]) > target:
            raise OfficialCurrentBuildGapError(
                "capture retrieval post-dates recorded_at"
            )
    if require_live:
        for final in (*paths.values(), path):
            if final.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
                raise OfficialCurrentBuildGapError(
                    f"final ctime predates recorded_at: {final.name}"
                )
    replay_counts = [_offline_import(paths, manifest["recorded_at"]) for _ in range(2)]
    if replay_counts[0] != replay_counts[1]:
        raise OfficialCurrentBuildGapError("two offline source replays differ")
    return manifest


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise OfficialCurrentBuildGapError(
            "active current-build-gap publication lock exists"
        ) from error
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
            if not stat.S_ISREG(current.st_mode) or (
                current.st_dev,
                current.st_ino,
            ) != identity:
                raise OfficialCurrentBuildGapError(
                    "refusing substituted publication-lock cleanup"
                )
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
    if (
        any(
            (SOURCES_ROOT / name).exists()
            or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
        or ARTIFACT.exists()
        or ARTIFACT.is_symlink()
    ):
        raise OfficialCurrentBuildGapError("current-build-gap final path collision")
    _validate_frozen_witnesses()
    _validate_source_collisions()
    capture_directory = resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(capture_directory)
    documents = expected_source_documents()
    source_stage = Path(
        tempfile.mkdtemp(prefix=".official-current-build-gap-sources.", dir=SOURCES_ROOT)
    )
    artifact_stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT)
    )
    try:
        _write_source_stage(source_stage, documents)
        _write_artifact_stage(artifact_stage, recorded_at, documents)
        paths = _source_paths(source_stage)
        _validate_sources(paths)
        validate_artifact(
            artifact_stage,
            source_paths=paths,
            require_live=False,
            wall_clock=_instant(recorded_at),
        )
        target = _instant(recorded_at).timestamp()
        for path in (*paths.values(), artifact_stage, *artifact_stage.iterdir()):
            metadata = path.stat(follow_symlinks=False)
            if max(metadata.st_birthtime, metadata.st_mtime) > target + 1e-6:
                raise OfficialCurrentBuildGapError(
                    f"stage post-dates recorded_at: {path.name}"
                )
        return _Prepared(
            source_stage=source_stage,
            artifact_stage=artifact_stage,
            source_identities={
                name: _identity(path) for name, path in paths.items()
            },
            artifact_identity=_identity(artifact_stage),
            artifact_members={
                path.name: _identity(path) for path in artifact_stage.iterdir()
            },
            recorded_at=recorded_at,
        )
    except Exception:
        if source_stage.exists():
            shutil.rmtree(source_stage)
        if artifact_stage.exists():
            artifact_stage.chmod(0o700)
            shutil.rmtree(artifact_stage)
        raise


def _assert_prepared(prepared: _Prepared) -> None:
    if _identity(prepared.artifact_stage) != prepared.artifact_identity:
        raise OfficialCurrentBuildGapError("private artifact stage identity changed")
    if {
        path.name: _identity(path) for path in prepared.artifact_stage.iterdir()
    } != dict(prepared.artifact_members):
        raise OfficialCurrentBuildGapError("artifact-stage member identity changed")
    for name, identity in prepared.source_identities.items():
        if _identity(prepared.source_stage / name) != identity:
            raise OfficialCurrentBuildGapError("source-stage member identity changed")


def _publish(prepared: _Prepared) -> None:
    target = _instant(prepared.recorded_at)
    while datetime.now(UTC) < target:
        time.sleep(min(0.25, (target - datetime.now(UTC)).total_seconds()))
    _assert_prepared(prepared)
    if (
        any(
            (SOURCES_ROOT / name).exists()
            or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
        or ARTIFACT.exists()
        or ARTIFACT.is_symlink()
    ):
        raise OfficialCurrentBuildGapError(
            "late current-build-gap final path collision"
        )
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
            raise OfficialCurrentBuildGapError(
                "source stage not empty after publication"
            )
        prepared.source_stage.rmdir()


def _move_capture_to_trash() -> None:
    if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
        raise OfficialCurrentBuildGapError(
            "both capture origin and Trash destination exist"
        )
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH))


def _rollback_published(prepared: _Prepared) -> None:
    if ARTIFACT.exists():
        if _identity(ARTIFACT) != prepared.artifact_identity:
            raise OfficialCurrentBuildGapError(
                "refusing rollback of substituted artifact"
            )
        _promote_noreplace(ARTIFACT, prepared.artifact_stage)
    for name in reversed(SOURCE_FILENAMES):
        final = SOURCES_ROOT / name
        if final.exists():
            if _identity(final) != prepared.source_identities[name]:
                raise OfficialCurrentBuildGapError(
                    f"refusing rollback of substituted source: {name}"
                )
            _promote_noreplace(final, prepared.source_stage / name)


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    if ARTIFACT.exists() and all(
        (SOURCES_ROOT / name).exists() for name in SOURCE_FILENAMES
    ):
        manifest = validate_artifact()
        _move_capture_to_trash()
        return {
            "artifact": str(ARTIFACT),
            "artifact_tree_sha256": tree_digest(ARTIFACT),
            "capture_trash": str(CAPTURE_TRASH),
            "capture_recoverable": True,
            "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
            "recorded_at": manifest["recorded_at"],
            "source_records": len(SOURCE_FILENAMES),
            "status": "existing-identical",
        }
    if (
        ARTIFACT.exists()
        or ARTIFACT.is_symlink()
        or any(
            (SOURCES_ROOT / name).exists()
            or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
    ):
        raise OfficialCurrentBuildGapError(
            "partial current-build-gap final-path collision"
        )
    target = (
        _instant(recorded_at)
        if recorded_at
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise OfficialCurrentBuildGapError(
            "recorded_at must be future before staging"
        )
    recorded_at = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    with _publication_lock():
        prepared = _prepare(recorded_at)
        published = False
        try:
            _publish(prepared)
            published = True
            _move_capture_to_trash()
            manifest = validate_artifact()
            _cleanup(prepared)
        except BaseException as error:
            if published:
                try:
                    _rollback_published(prepared)
                    published = False
                except Exception as rollback_error:
                    error.add_note(
                        f"identity-safe rollback failed: {rollback_error}"
                    )
            if prepared.source_stage.exists():
                shutil.rmtree(prepared.source_stage)
            if prepared.artifact_stage.exists():
                prepared.artifact_stage.chmod(0o700)
                shutil.rmtree(prepared.artifact_stage)
            raise
    return {
        "artifact": str(ARTIFACT),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "capture_trash": str(CAPTURE_TRASH),
        "capture_recoverable": True,
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "recorded_at": manifest["recorded_at"],
        "source_records": len(SOURCE_FILENAMES),
        "status": "published",
    }


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
