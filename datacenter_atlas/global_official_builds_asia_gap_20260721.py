"""Publish a bounded Asia official-build gap assessment.

The carrier is independent of open-seed and downstream publication. It stages
all source and artifact bytes before the declared recording instant, waits for
that instant, and promotes the complete set without replacement.
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

from . import global_official_builds_next_tranche_20260721 as publication
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "global-official-builds-asia-gap-2026-07-21-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".global-official-builds-asia-gap-20260721.lock"
CAPTURE_ORIGIN = Path("/private/tmp/dc-global-official-asia-20260721.mSVmaD")
CAPTURE_TRASH = Path(
    "/Users/kian/.Trash/dc-global-official-asia-20260721.mSVmaD"
)
CAPTURE_TREE_SHA256 = (
    "ef16316509c87c72e5423e930d49eaed02389d578e160e90ffbfcc7324aacf03"
)
CAPTURE_FILE_COUNT = 35
CAPTURE_TOTAL_BYTES = 21_357_081

V75_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v75.json"
V75_RELEASE = ROOT / "releases/2026-07-21-open-seed-v75"
V75_MANIFEST = V75_RELEASE / "manifest.json"
V75_ENTITIES = V75_RELEASE / "entities.csv"
V75_PINS = {
    V75_DEFINITION: (
        89_129,
        "69faaee57c8e4d889d91bfcb5513141d7e19d1377b77d913ee8aa8d29189383f",
    ),
    V75_MANIFEST: (
        13_106,
        "7f121051b6af6c82a1c48011e7c471153b5047dd428addd7662dccb0c3a232de",
    ),
    V75_ENTITIES: (
        893_070,
        "67cb8222b76f9b5a2ace738b1dc0451d8d89b66ef6b6911acece485b37dffd0b",
    ),
}
V75_TREE_SHA256 = (
    "bcc09e206798788d780b4cea2166aa91631f901bc970681f7f505f2282318c5d"
)
V75_INPUT_COUNT = 400

SOURCE_FILENAMES = (
    "curated-official-2026-07-21-bcc-jashore-dr-data-center-current-build.json",
    "curated-official-2026-07-21-adaniconnex-navi-mumbai-current-development.json",
    "curated-official-2026-07-21-adaniconnex-pune-pnq04-current-build.json",
)

CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

OfficialAsiaGapError = publication.OfficialTrancheError
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


CAPTURES: dict[str, dict[str, Any]] = {
    "bcc_ictd_jashore": {
        "filename": "bcc_ictd_jashore.body",
        "url": (
            "https://ictd.gov.bd/pages/news/%E0%A6%AF%E0%A6%B6%E0%A7%8B%E0%A6%B0"
            "%E0%A6%95%E0%A7%87-%E0%A6%A1%E0%A6%BF%E0%A6%9C%E0%A6%BF%E0%A6%9F"
            "%E0%A6%BE%E0%A6%B2-%E0%A6%B9%E0%A6%BE%E0%A6%AC-%E0%A6%B9%E0%A6%BF"
            "%E0%A6%B8%E0%A7%87%E0%A6%AC%E0%A7%87-%E0%A6%97%E0%A6%A1%E0%A6%BC"
            "%E0%A7%87-%E0%A6%A4%E0%A7%8B%E0%A6%B2%E0%A6%BE%E0%A6%B0-%E0%A6%89"
            "%E0%A6%A6%E0%A7%8D%E0%A6%AF%E0%A7%8B%E0%A6%97-%E0%A6%85%E0%A6%AC"
            "%E0%A7%8D%E0%A6%AF%E0%A6%BE%E0%A6%B9%E0%A6%A4-%E0%A6%A5%E0%A6%BE"
            "%E0%A6%95%E0%A6%AC%E0%A7%87-%E0%A6%AB%E0%A6%AF%E0%A6%BC%E0%A7%87"
            "%E0%A6%9C-%E0%A6%86%E0%A6%B9%E0%A6%AE%E0%A6%A6-%E0%A6%A4%E0%A7%88"
            "%E0%A6%AF%E0%A6%BC%E0%A7%8D%E0%A6%AF%E0%A6%AC-lur5zd-"
            "69784fa8027fd5c8b7be3426"
        ),
        "retrieved_at": "2026-07-21T16:12:10Z",
        "http_status": 404,
        "bytes": 55_626,
        "sha256": "6e11b87f06e01a3b8e1db047d0072cce6c381f16e7db125467972692f237057b",
        "content_type": "text/html; charset=utf-8",
        "used_for_claims": False,
    },
    "bcc_pid_handout": {
        "filename": "bcc_pid_handout.body",
        "url": (
            "https://pressinform.gov.bd/pages/all-notes/"
            "handout-25-january-2026-tp2bbq-6975e2378c3f7fde7ba4f3e0"
        ),
        "retrieved_at": "2026-07-21T16:10:56Z",
        "http_status": 200,
        "bytes": 291_030,
        "sha256": "148ee7bc6acabc2d4f4c6cb15c1c965969ba806c6a3f8b72d2b0c59c2e331b5f",
        "content_type": "text/html; charset=utf-8",
        "used_for_claims": True,
    },
    "bcc_edge_rfp": {
        "filename": "bcc_edge_rfp.body",
        "url": (
            "https://edge.gov.bd/wp-content/uploads/2024/12/"
            "RFP-Document-EDGE-G10-Unofficial-Copy.pdf"
        ),
        "retrieved_at": "2026-07-21T16:11:00Z",
        "http_status": 200,
        "bytes": 8_838_522,
        "sha256": "af3ee95624bedc94cfaed07e69bb9639528fa213b949f8fdc0ea0e5595f7e202",
        "content_type": "application/pdf",
        "used_for_claims": True,
    },
    "adani_blog_20260601": {
        "filename": "adani_blog_20260601.body",
        "url": (
            "https://resources.adaniconnex.com/blog/"
            "scaling-indias-data-centres-responsibly-for-the-ai-era-"
            "bridging-people-planet-and-growth"
        ),
        "retrieved_at": "2026-07-21T16:11:00Z",
        "http_status": 200,
        "bytes": 69_731,
        "sha256": "ec057dbf5efe7c0b5f8344cbdd7e74b1cf1d208c8ff2545c1f4f4dc45b6721ff",
        "content_type": "text/html; charset=UTF-8",
        "used_for_claims": True,
    },
    "adani_facilities": {
        "filename": "adani_facilities.body",
        "url": "https://www.adaniconnex.com/data-centers",
        "retrieved_at": "2026-07-21T16:11:02Z",
        "http_status": 200,
        "bytes": 48_315,
        "sha256": "8daf38012bc4a1cedae8b494b1c998f66556d0197bab98c992771c7c8729f347",
        "content_type": "text/html; charset=utf-8",
        "used_for_claims": True,
    },
    "ael_fy25_md": {
        "filename": "ael_fy25_md.body",
        "url": (
            "https://connect.adani.com/annual_report/2025/ael/"
            "message-from-managing-director.html"
        ),
        "retrieved_at": "2026-07-21T16:11:03Z",
        "http_status": 200,
        "bytes": 42_890,
        "sha256": "7f0747ee57431931e9f84432db7f191a3506487ff5906016935bb4f553494c15",
        "content_type": "text/html",
        "used_for_claims": True,
    },
    "adani_pune_compliance": {
        "filename": "adani_pune_compliance.body",
        "url": (
            "https://www.adaniconnex.com/-/media/Project/AdaniConneX/"
            "AdaniConneX-AboutUs-Assets/Certifications/"
            "Post-EC-compliance-report-PNQ26--with-Anneure.pdf"
        ),
        "retrieved_at": "2026-07-21T16:11:57Z",
        "http_status": 200,
        "bytes": 5_748_254,
        "sha256": "406e7134f896a916f6ac978a888183f67de62218cbfbd24a90248af52af544f4",
        "content_type": "application/pdf",
        "used_for_claims": True,
    },
    "via_evolution": {
        "filename": "via_evolution.body",
        "url": (
            "https://via.gov.vn//tin-tuc/t12612/"
            "tphcm-trao-giay-chung-nhan-dau-tu-cho-4-du-an-cong-nghe-cao-chien-luoc"
        ),
        "retrieved_at": "2026-07-21T16:12:11Z",
        "http_status": 200,
        "bytes": 37_367,
        "sha256": "cee8ac3b80f33b0ab02f04c6bd505066d1b6da964a68a11b3b31a0ed94c302d7",
        "content_type": "text/html; charset=utf-8",
        "used_for_claims": False,
    },
    "evolution_markets": {
        "filename": "evolution_markets.body",
        "url": "https://evolutiondatacentres.com/markets/",
        "retrieved_at": "2026-07-21T16:12:12Z",
        "http_status": 200,
        "bytes": 120_907,
        "sha256": "d3451b0c568c5ee7874912c9163961d121491a5df69dab94b07f3f4128378207",
        "content_type": "text/html; charset=UTF-8",
        "used_for_claims": False,
    },
    "kbc_aic_mou": {
        "filename": "kbc_aic_mou.body",
        "url": "https://kinhbaccity.vn/en/press-release-11-03-2026.htm",
        "retrieved_at": "2026-07-21T16:12:16Z",
        "http_status": 200,
        "bytes": 150_345,
        "sha256": "509ca54992ca556cfe27e774e87f6b88c96a387b89d596a31445b33e244ed6fa",
        "content_type": "text/html; charset=utf-8",
        "used_for_claims": False,
    },
}

INCIDENT_FILE_PINS = {
    "bcc_ictd_jashore_attempt1.headers": (
        1_999,
        "ed85c6b7f0692aeb09827539362286e52e483955d1b13896a9a982d159499ee1",
    ),
    "bcc_ictd_jashore_attempt1.facts": (
        18_681,
        "28ac9b4c843b282686f2e7105a801cff5d0007155df61e93cca32ea2a77e3136",
    ),
}
REPEATED_CAPTURE_PINS = {
    "adani_pune_compliance_attempt1.body": (
        5_748_254,
        "406e7134f896a916f6ac978a888183f67de62218cbfbd24a90248af52af544f4",
    ),
    "adani_pune_compliance_attempt1.headers": (
        1_766,
        "368c625921849710a3ef1af90c6ab7bf5f4a40b8d333cf508d6d096866a6014a",
    ),
    "adani_pune_compliance_attempt1.facts": (
        17_247,
        "1c510b8670664c382d0d0c445dbfba1e3645a5b3e4c33739d5d986771fcf88af",
    ),
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
    capture = CAPTURES[capture_id]
    if capture["http_status"] != 200:
        raise OfficialAsiaGapError("non-200 capture cannot become evidence")
    common = {
        "content_hash_scope": (
            f"SHA-256 of the exact {capture['bytes']}-byte content-decoded "
            "official response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture_id,
        "capture_method": "credential_free_curl_location_compressed",
        "http_status": 200,
        "content_type": capture["content_type"],
        "request_credentials_supplied": False,
        "rights_scope": (
            "Compact factual extraction from all-rights-reserved official bytes; "
            "response bodies, headers, telemetry, and publisher media are not redistributed."
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
    evidence_key: str,
    as_of_date: str,
    coordinates: dict[str, float] | None = None,
    geometry: dict[str, Any] | None = None,
    method: str = "authoritative_locality",
    confidence: float = 0.99,
) -> dict[str, Any]:
    return {
        "stable_key": stable_key,
        "name": name,
        "country": country,
        "address": address,
        "roles": {},
        "coordinates": coordinates,
        "geometry": geometry,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": method,
        "confidence": confidence,
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


def _campus_capacity(
    value: float,
    evidence_key: str,
    as_of_date: str,
    notes: str,
) -> dict[str, Any]:
    return {
        "entity": "campus",
        "metric": "critical_it_mw",
        "stage": "planned",
        "unit": "MW",
        "low": value,
        "base": value,
        "high": value,
        "method": "reported",
        "confidence": 0.99,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "target_date": None,
        "notes": notes,
    }


def _jashore_source() -> dict[str, Any]:
    status_key = "bangladesh-bcc-jashore-dr-pid-handout-captured-2026-07-21"
    rfp_key = "bangladesh-bcc-jashore-dr-edge-rfp-captured-2026-07-21"
    evidence = [
        _evidence(
            "bcc_pid_handout",
            key=status_key,
            kind="government_record",
            title="Handout 25 January 2026",
            publisher="Press Information Department, Government of Bangladesh",
            source_family="bangladesh_government_pid_handouts",
            published_at="2026-01-25",
            excerpt=(
                "The government handout says construction is ongoing on a new "
                "three-story Tier-3-certified disaster-recovery data center at "
                "Jashore Software Technology Park, designed for more than 200 IT "
                "cabinets and racks."
            ),
            metadata={
                "status_wording_as_reported": "construction activity is ongoing",
                "location_as_reported": "Jashore Software Technology Park",
                "reported_building_form": "new three-story facility",
                "reported_resilience": "Tier-3 certified",
                "reported_it_cabinet_and_rack_count_lower_bound_exclusive": 200,
                "reported_future_workload_capability": [
                    "computing workloads",
                    "AI workloads",
                ],
                "physical_status_scope": (
                    "This supports one generic under_construction observation on "
                    "2026-01-25, not a finer stage, completion percentage, "
                    "commissioning, energization, operation, or status persistence."
                ),
                "rack_capacity_guardrail": (
                    "The more-than-200 cabinet/rack design is retained as narrative "
                    "rescope evidence only. It is not converted to MW or energy."
                ),
                "workload_guardrail": (
                    "Capability to host future AI workloads creates no active workload, "
                    "tenant, installed accelerator, utilization, or workload row."
                ),
                "resilience_guardrail": (
                    "Tier-3 wording is resilience context, not capacity, PUE, "
                    "certification verification, or operating status."
                ),
            },
        ),
        _evidence(
            "bcc_edge_rfp",
            key=rfp_key,
            kind="government_record",
            title=(
                "RFP EDGE-G10: Supply, Installation and Commissioning for IT "
                "Hardware, Software and Related Services of BCC DR Cloud"
            ),
            publisher="Bangladesh Computer Council",
            source_family="bangladesh_edge_procurement",
            published_at="2024-12-23",
            excerpt=(
                "The official RFP locates the project at 23.156275210272007, "
                "89.22246834914694, says three containers occupy the existing DR "
                "plot, and describes reconstruction and expansion."
            ),
            metadata={
                "selected_pdf_pages": [128, 129, 130],
                "project_coordinate_wgs84": {
                    "latitude": 23.156275210272007,
                    "longitude": 89.22246834914694,
                },
                "reported_existing_containers": 3,
                "reported_scope": "reconstruct and expand the existing DR center",
                "reported_phase_1_server_racks": 46,
                "reported_phase_1_network_racks": 4,
                "reported_expandability_racks": 150,
                "reported_phase_1_it_loading_kva_approximate": 600,
                "coordinate_scope": (
                    "Exact official project-site point. It is not a parcel boundary, "
                    "building footprint, or container position."
                ),
                "procurement_status_guardrail": (
                    "The 2024 RFP supplies identity, site coordinate, existing-scope, "
                    "and design context only. It creates no construction lifecycle row."
                ),
                "rescope_guardrail": (
                    "The RFP's 50-rack first phase, 150-rack expandability, and around "
                    "600 kVA differ from the January 2026 handout's more-than-200 "
                    "cabinet/rack design. All remain narrative; no rack-derived MW, "
                    "kVA-to-MW conversion, energy, or capacity row is emitted."
                ),
            },
        ),
    ]
    campus_key = "curated:bcc-jashore-software-technology-park-dr-data-center"
    project_key = f"{campus_key}:rebuild-expansion-current-build"
    coordinates = {
        "latitude": 23.156275210272007,
        "longitude": 89.22246834914694,
    }
    geometry = {
        "type": "Point",
        "coordinates": [89.22246834914694, 23.156275210272007],
    }
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="BCC Jashore Disaster Recovery Data Center",
            country="Bangladesh",
            address="Software Technology Park, Jashore, Bangladesh",
            evidence_key=rfp_key,
            as_of_date="2024-12-23",
            coordinates=coordinates,
            geometry=geometry,
            method="authoritative_site_plan",
        ),
        "project": _entity(
            stable_key=project_key,
            name="BCC Jashore DR Data Center Rebuild and Expansion",
            country="Bangladesh",
            address="Software Technology Park, Jashore, Bangladesh",
            evidence_key=rfp_key,
            as_of_date="2026-01-25",
            coordinates=coordinates,
            geometry=geometry,
            method="authoritative_site_plan",
        ),
        "lifecycle": [_lifecycle(status_key, "2026-01-25")],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _adani_blog_evidence(*, site: str, key: str) -> dict[str, Any]:
    return _evidence(
        "adani_blog_20260601",
        key=key,
        kind="company_disclosure",
        title=(
            "Scaling India's data centres responsibly for the AI Era: "
            "Bridging People, Planet and Growth"
        ),
        publisher="AdaniConneX",
        source_family="adaniconnex_current_development_updates",
        published_at="2026-06-01",
        excerpt=(
            f"AdaniConneX names {site} among four new campuses advancing through "
            "phased development."
        ),
        metadata={
            "campuses_named_as_reported": [
                "Hyderabad",
                "Noida",
                "Navi Mumbai",
                "Pune",
            ],
            "selected_site": site,
            "status_wording_as_reported": (
                "new campuses are advancing through phased development"
            ),
            "physical_status_scope": (
                "Combined with the site-specific older physical record, the dated "
                "company wording supports one generic under_construction observation "
                "for the selected site as of 2026-06-01. It does not allocate a finer "
                "phase, building, progress percentage, completion, commissioning, "
                "energization, operation, or current load."
            ),
            "aggregate_guardrail": (
                "The four-campus sentence is not split into capacity, phase, building, "
                "tenant, workload, or energy claims beyond the named-site status scope."
            ),
        },
    )


def _adani_facility_evidence(
    *,
    site: str,
    key: str,
    potential_it_mw: int,
    rfs: str,
) -> dict[str, Any]:
    return _evidence(
        "adani_facilities",
        key=key,
        kind="company_disclosure",
        title=f"AdaniConneX data centers — {site}",
        publisher="AdaniConneX",
        source_family="adaniconnex_facility_pages",
        published_at=None,
        excerpt=(
            f"The current company page calls the {site} facility soon to be launched "
            f"and reports potential capacity of {potential_it_mw} MW IT load."
        ),
        metadata={
            "selected_site": site,
            "reported_potential_it_load_mw": potential_it_mw,
            "reported_rfs": rfs,
            "reported_availability_design": "99.999%",
            "reported_renewable_energy_marketing_ceiling": "up to 100%",
            "capacity_scope": (
                "Potential IT load is normalized once as planned full-campus critical "
                "IT capacity. It is not allocated to the child project or any phase and "
                "is not current load, installed or energized capacity, gross facility "
                "demand, grid connection, generation, or measured consumption."
            ),
            "schedule_guardrail": (
                "RFS and soon-to-launch wording are forecasts or marketing context; "
                "they create no completion, commissioning, or operational observation."
            ),
            "energy_guardrail": (
                "Up-to renewable wording creates no current renewable share, supply, "
                "load, consumption, annual energy, generation, PUE, or emissions row."
            ),
            "classification_guardrail": (
                "Facility marketing creates no operating-model, tenant, customer, "
                "active AI workload, cloud workload, or utilization observation."
            ),
        },
    )


def _navi_source() -> dict[str, Any]:
    blog_key = "india-adaniconnex-navi-mumbai-phased-development-captured-2026-07-21"
    facility_key = "india-adaniconnex-navi-mumbai-facility-page-captured-2026-07-21"
    annual_key = "india-ael-fy25-navi-mumbai-construction-captured-2026-07-21"
    evidence = [
        _adani_blog_evidence(site="Navi Mumbai", key=blog_key),
        _adani_facility_evidence(
            site="Navi Mumbai",
            key=facility_key,
            potential_it_mw=1000,
            rfs="December 2026 onwards",
        ),
        _evidence(
            "ael_fy25_md",
            key=annual_key,
            kind="company_disclosure",
            title="Adani Enterprises Integrated Annual Report 2024-25 — MD message",
            publisher="Adani Enterprises Limited",
            source_family="adani_enterprises_annual_reports",
            published_at=None,
            excerpt=(
                "The FY2024-25 annual report says construction was underway at the "
                "Navi Mumbai Data Centre and directly associates 30 MW with it."
            ),
            metadata={
                "reporting_period_end": "2025-03-31",
                "reported_project_capacity_mw_untyped": 30,
                "reported_status_wording": "construction is underway",
                "identity_scope": (
                    "The report directly allocates the 30 MW wording to the physical "
                    "Navi Mumbai Data Centre, corroborating the site-specific project."
                ),
                "capacity_guardrail": (
                    "The 30 MW value is exact and project-allocated but not typed as "
                    "critical IT, gross facility, grid connection, or generation. It is "
                    "retained as narrative metadata and creates no capacity row."
                ),
                "continuity_guardrail": (
                    "The older report alone does not prove current status; the June "
                    "2026 company update supplies the later phased-development observation."
                ),
            },
        ),
    ]
    campus_key = "curated:adaniconnex-navi-mumbai-data-center-campus"
    project_key = f"{campus_key}:current-phased-development"
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="AdaniConneX Navi Mumbai Data Center Campus",
            country="India",
            address="Navi Mumbai, Maharashtra, India",
            evidence_key=facility_key,
            as_of_date="2026-07-21",
        ),
        "project": _entity(
            stable_key=project_key,
            name="AdaniConneX Navi Mumbai Current Phased Development",
            country="India",
            address="Navi Mumbai, Maharashtra, India",
            evidence_key=blog_key,
            as_of_date="2026-06-01",
        ),
        "lifecycle": [_lifecycle(blog_key, "2026-06-01")],
        "operating_models": [],
        "workloads": [],
        "capacities": [
            _campus_capacity(
                1000,
                facility_key,
                "2026-07-21",
                (
                    "AdaniConneX-reported potential IT load for the full Navi Mumbai "
                    "campus; planned campus scope, not current phase capacity or draw."
                ),
            )
        ],
    }


def _pune_source() -> dict[str, Any]:
    blog_key = "india-adaniconnex-pune-phased-development-captured-2026-07-21"
    facility_key = "india-adaniconnex-pune-facility-page-captured-2026-07-21"
    compliance_key = "india-adaniconnex-pune-pnq04-compliance-captured-2026-07-21"
    evidence = [
        _adani_blog_evidence(site="Pune", key=blog_key),
        _adani_facility_evidence(
            site="Pune",
            key=facility_key,
            potential_it_mw=250,
            rfs="Phase 1: H2 2025",
        ),
        _evidence(
            "adani_pune_compliance",
            key=compliance_key,
            kind="company_disclosure",
            title=(
                "Compliance to Stipulated Conditions in Environment Clearance, "
                "October 2024 to March 2025 — Development of Data Center PNQ04"
            ),
            publisher="Pune Data Center Limited",
            source_family="adaniconnex_environmental_compliance_reports",
            published_at=None,
            excerpt=(
                "The hosted compliance report says that by March 2025 the PNQ04 data "
                "center's third-floor slab and ancillary-building superstructure were "
                "complete and STP work was in progress."
            ),
            metadata={
                "reporting_period_end": "2025-03-31",
                "location_as_reported": "BG 80/B, Bhosari, Pune, Maharashtra",
                "reported_dc_building_configuration": "G+4 floors",
                "reported_dc_milestone": "third-floor slab casting completed",
                "reported_ancillary_milestone": "superstructure work completed",
                "reported_stp_status": "work in progress",
                "reported_actual_commencement_date": "2022-07-27",
                "reported_planned_completion_date": "2026-08-21",
                "physical_status_scope": (
                    "This is site-specific physical corroboration as of March 2025. "
                    "It does not by itself prove current status in July 2026."
                ),
                "schedule_guardrail": (
                    "Actual-start and planned-completion dates create no additional "
                    "lifecycle rows, completion, commissioning, or operation."
                ),
                "coordinate_guardrail": (
                    "The report's coordinate is deliberately not normalized in this "
                    "bounded artifact; both entities remain unlocated."
                ),
            },
        ),
    ]
    campus_key = "curated:adaniconnex-pune-data-center-campus"
    project_key = f"{campus_key}:pnq04-current-build"
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="AdaniConneX Pune Data Center Campus",
            country="India",
            address="Bhosari, Pune, Maharashtra, India",
            evidence_key=facility_key,
            as_of_date="2026-07-21",
        ),
        "project": _entity(
            stable_key=project_key,
            name="AdaniConneX Pune PNQ04 Current Build",
            country="India",
            address="BG 80/B, Bhosari, Pune, Maharashtra, India",
            evidence_key=blog_key,
            as_of_date="2026-06-01",
        ),
        "lifecycle": [_lifecycle(blog_key, "2026-06-01")],
        "operating_models": [],
        "workloads": [],
        "capacities": [
            _campus_capacity(
                250,
                facility_key,
                "2026-07-21",
                (
                    "AdaniConneX-reported potential IT load for the full Pune campus; "
                    "planned campus scope, not PNQ04 phase capacity or current draw."
                ),
            )
        ],
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    """Return the three exact schema-1.1 source documents."""

    builders = (_jashore_source, _navi_source, _pune_source)
    return {
        name: builder() for name, builder in zip(SOURCE_FILENAMES, builders, strict=True)
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
                "coordinates_present": sum(
                    document[entity]["coordinates"] is not None
                    for entity in ("campus", "project")
                ),
                "geometry_present": sum(
                    document[entity]["geometry"] is not None
                    for entity in ("campus", "project")
                ),
                "disposition": "seed_eligible_official_physical_update",
                "seed_eligible": True,
                "seeded": False,
            }
        )
    return records


def _capture_reference(capture_id: str) -> dict[str, Any]:
    capture = CAPTURES[capture_id]
    return {
        "source_url": capture["url"],
        "http_status": capture["http_status"],
        "body_bytes": capture["bytes"],
        "body_sha256": capture["sha256"],
    }


def _candidate_assessments(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-seven-candidate-asia-official-gap-assessment-v1",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "candidate_count": 7,
        "seed_eligible_count": 3,
        "review_only_count": 4,
        "candidates": [
            {
                "candidate_id": "bcc-jashore-dr-data-center-rebuild-expansion",
                "country": "Bangladesh",
                "decision": "seed_eligible_official_physical_update",
                "source_record_created": True,
                "seed_eligible": True,
                "basis": (
                    "The January 2026 PID handout directly says construction is ongoing; "
                    "the December 2024 BCC RFP supplies exact project identity and coordinate."
                ),
                "coordinate": {
                    "latitude": 23.156275210272007,
                    "longitude": 89.22246834914694,
                    "source": "official BCC RFP only",
                },
                "capacity_disposition": (
                    "The RFP's 50-rack phase, 150-rack expandability, and around 600 "
                    "kVA conflict with the later more-than-200-cabinet/rack design scope. "
                    "No MW, energy, PUE, or rack-derived capacity is emitted."
                ),
                "workload_disposition": (
                    "Future ability to host AI creates no active AI workload row."
                ),
                "technical_incident": {
                    "source_url": CAPTURES["bcc_ictd_jashore"]["url"],
                    "two_direct_attempts_returned_http_404": True,
                    "used_for_claims": False,
                    "search_transformed_text_used": False,
                    "independent_pid_handout_available": True,
                },
            },
            {
                "candidate_id": "adaniconnex-navi-mumbai-current-development",
                "country": "India",
                "decision": "seed_eligible_current_phased_development",
                "source_record_created": True,
                "seed_eligible": True,
                "basis": (
                    "The June 2026 AdaniConneX update names Navi Mumbai among new "
                    "campuses advancing through phased development; the FY2024-25 "
                    "annual report directly corroborates physical construction."
                ),
                "capacity_disposition": {
                    "1000_mw_it": "planned_full_campus_only",
                    "30_mw": "project_allocated_but_untyped_narrative_only",
                },
            },
            {
                "candidate_id": "adaniconnex-pune-pnq04-current-build",
                "country": "India",
                "decision": "seed_eligible_current_phased_development",
                "source_record_created": True,
                "seed_eligible": True,
                "basis": (
                    "The June 2026 AdaniConneX update names Pune among new campuses "
                    "advancing through phased development; the PNQ04 compliance report "
                    "documents site-specific structural work as of March 2025."
                ),
                "capacity_disposition": {
                    "250_mw_it": "planned_full_campus_only",
                },
                "coordinate_created": False,
            },
            {
                "candidate_id": "adaniconnex-hyderabad-future-phases",
                "country": "India",
                "decision": "review_only_operational_phase_and_unallocated_future_scope",
                "source_record_created": False,
                "seed_eligible": False,
                "basis": (
                    "Phase 1 is operational and the June 2026 aggregate phased-development "
                    "wording does not identify a distinct physical future phase."
                ),
                "captured_sources": [
                    _capture_reference("adani_blog_20260601"),
                    _capture_reference("adani_facilities"),
                ],
                "capacity_disposition": "600 MW potential campus not normalized here",
            },
            {
                "candidate_id": "adaniconnex-noida-future-phases",
                "country": "India",
                "decision": "review_only_operational_phase_and_unallocated_future_scope",
                "source_record_created": False,
                "seed_eligible": False,
                "basis": (
                    "Phase 1 is operational and the June 2026 aggregate phased-development "
                    "wording does not identify a distinct physical future phase."
                ),
                "captured_sources": [
                    _capture_reference("adani_blog_20260601"),
                    _capture_reference("adani_facilities"),
                ],
                "capacity_disposition": "150 MW potential campus not normalized here",
            },
            {
                "candidate_id": "evolution-dc-vn-hcm-vn02",
                "country": "Vietnam",
                "decision": "review_only_investment_certificate_no_physical_start",
                "source_record_created": False,
                "seed_eligible": False,
                "basis": (
                    "The government page records an investment certificate and the "
                    "company markets a 52 MW planned VN02 development, but neither "
                    "captured source establishes post-groundbreaking physical work."
                ),
                "captured_sources": [
                    _capture_reference("via_evolution"),
                    _capture_reference("evolution_markets"),
                ],
                "capacity_disposition": "52 MW design plan not normalized without a source record",
            },
            {
                "candidate_id": "aic-kbc-tan-phu-trung-ai-data-center",
                "country": "Vietnam",
                "decision": "review_only_expected_groundbreaking_no_follow_up",
                "source_record_created": False,
                "seed_eligible": False,
                "basis": (
                    "KBC's March 2026 page records an MOU and an expected April 30 "
                    "groundbreaking. No direct post-groundbreaking physical update was found."
                ),
                "captured_sources": [_capture_reference("kbc_aic_mou")],
                "capacity_disposition": (
                    "50 MW first-phase and 200 MW complex plans are not normalized "
                    "without a physical source record."
                ),
            },
        ],
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    controlled = []
    for capture_id, spec in sorted(CAPTURES.items()):
        controlled.append(
            {
                "capture_id": capture_id,
                "requested_url": spec["url"],
                "effective_url": spec["url"],
                "retrieved_at": spec["retrieved_at"],
                "http_status": spec["http_status"],
                "content_type": spec["content_type"],
                "body": {
                    "bytes": spec["bytes"],
                    "sha256": spec["sha256"],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "capture_method": "credential_free_curl_location_compressed",
                "request_credentials_supplied": False,
                "used_for_normalized_claims": spec["used_for_claims"],
            }
        )
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "capture_protocol": (
            "Credential-free public HTTP GETs with a transparent research User-Agent. "
            "Successful bodies, headers, and curl facts were retained privately."
        ),
        "controlled_endpoint_captures": len(CAPTURES),
        "http_200_endpoint_captures": 9,
        "selected_source_evidence_bodies": 6,
        "assessment_only_bodies": 3,
        "http_404_endpoint_captures": 1,
        "request_credentials_supplied": False,
        "raw_capture_redistributed": False,
        "capture_file_count": CAPTURE_FILE_COUNT,
        "capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "controlled_captures": controlled,
        "technical_incidents": [
            {
                "candidate": "BCC Jashore DR data center",
                "source_url": CAPTURES["bcc_ictd_jashore"]["url"],
                "attempts": 2,
                "result": "HTTP 404 on both direct publisher requests",
                "used_for_claims": False,
                "search_transformed_text_used": False,
                "retained_attempt_file_pins": {
                    name: {"bytes": pin[0], "sha256": pin[1]}
                    for name, pin in sorted(INCIDENT_FILE_PINS.items())
                },
            }
        ],
        "repeat_verification": {
            "capture_id": "adani_pune_compliance",
            "result": "two successful byte-identical PDF captures",
            "retained_repeat_file_pins": {
                name: {"bytes": pin[0], "sha256": pin[1]}
                for name, pin in sorted(REPEATED_CAPTURE_PINS.items())
            },
        },
    }


def _artifact_documents(
    recorded_at: str,
    source_documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    source_records = _source_records(source_documents)
    readme = f"""# Global official-build Asia gap assessment

This immutable artifact records seven bounded Asia candidate dispositions researched on 2026-07-21. Three pass the physical-construction boundary: the BCC Jashore disaster-recovery data-center rebuild/expansion, AdaniConneX Navi Mumbai current phased development, and AdaniConneX Pune PNQ04 current development. Their lifecycle rows are dated observations, not timeless current-status claims.

The Jashore project uses the exact official BCC RFP project point. The RFP's 50-rack first phase, 150-rack expandability, and around 600 kVA conflict with the January 2026 government handout's revised more-than-200-cabinet/rack scope. All remain narrative; no rack-derived MW, kVA conversion, PUE, energy, or active AI workload is emitted.

Navi Mumbai's 1,000 MW IT and Pune's 250 MW IT are planned full-campus potential only, never current phase capacity or draw. Navi Mumbai's annual-report 30 MW is directly project-allocated but untyped, so it remains narrative rather than an invented IT or gross-facility row. Neither India record creates energy, PUE, tenant, workload, or operating-model observations.

AdaniConneX Hyderabad and Noida future phases remain review-only because operational first phases and an aggregate phased-development sentence do not identify distinct physical new phases. Evolution VN02 has an investment certificate and development plan but no captured physical-start proof. AIC/KBC Tan Phu Trung has an MOU and expected April 30 groundbreaking but no direct post-groundbreaking follow-up. Expected dates are not physical construction.

The named ICT Division Jashore page returned HTTP 404 twice during direct capture and contributes no claim. The independent official PID handout supplies construction evidence; no search-engine transformed text is retained or used.

No publisher imagery, satellite imagery, aerial imagery, computer vision, or analyst geolocation asserts identity, lifecycle, capacity, type, roles, or workload.

All source and artifact bytes were completed in private staging before `{recorded_at}`. Final paths remained absent until that instant and were promoted without replacement as one rollback-protected set. Accepted open seed v75 and all downstream artifacts remain unchanged. Raw all-rights-reserved captures are not redistributed; the complete 35-file capture directory was moved intact to the recoverable Trash path in the rights inventory.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "source_records": source_records,
        "totals": {
            "candidate_assessments": 7,
            "source_records": 3,
            "seed_eligible_source_records": 3,
            "review_only_candidates": 4,
            "distinct_campuses": 3,
            "projects": 3,
            "entity_snapshots": 6,
            "unique_evidence_records": 8,
            "lifecycle_observations": 3,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 2,
            "coordinates_present": 2,
            "geometry_present": 2,
        },
        "frozen_v75_non_mutation_witness": {
            "definition": {
                "path": "sources/open-seed-2026-07-21-v75.json",
                "bytes": V75_PINS[V75_DEFINITION][0],
                "sha256": V75_PINS[V75_DEFINITION][1],
            },
            "release_manifest": {
                "path": "releases/2026-07-21-open-seed-v75/manifest.json",
                "bytes": V75_PINS[V75_MANIFEST][0],
                "sha256": V75_PINS[V75_MANIFEST][1],
            },
            "release_tree_sha256": V75_TREE_SHA256,
            "v75_selected_input_count": V75_INPUT_COUNT,
            "new_source_paths_selected_by_v75": False,
            "new_stable_key_collisions": 0,
            "new_evidence_key_collisions": 0,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v75_mutated": False,
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
        "raw_curl_facts_retained_in_artifact": False,
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
        "candidate_dispositions": {"seed_eligible": 3, "review_only": 4},
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
        "curated_source_records": 3,
        "seed_eligible_source_records": 3,
        "review_only_candidates": 4,
        "successful_http_200_endpoint_captures": 9,
        "raw_capture_redistributed": False,
        "raw_capture_directory_moved_intact_to_trash": True,
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
        raise OfficialAsiaGapError("source path inventory differs")
    for name in SOURCE_FILENAMES:
        source = paths[name]
        if source.is_symlink() or not source.is_file():
            raise OfficialAsiaGapError(f"curated source is absent: {source}")
        raw = source.read_bytes()
        if raw != _canonical(expected[name]):
            raise OfficialAsiaGapError(f"curated source differs: {name}")
        if stat.S_IMODE(source.stat().st_mode) != 0o644:
            raise OfficialAsiaGapError(f"curated source mode differs: {name}")
    documents = list(expected.values())
    jashore = documents[0]
    for entity in ("campus", "project"):
        if jashore[entity]["coordinates"] != {
            "latitude": 23.156275210272007,
            "longitude": 89.22246834914694,
        }:
            raise OfficialAsiaGapError("Jashore coordinate differs")
    for document in documents[1:]:
        for entity in ("campus", "project"):
            if document[entity]["coordinates"] is not None:
                raise OfficialAsiaGapError("India source invented coordinates")
            if document[entity]["geometry"] is not None:
                raise OfficialAsiaGapError("India source invented geometry")
    if any(document["operating_models"] for document in documents):
        raise OfficialAsiaGapError("operating model boundary differs")
    if any(document["workloads"] for document in documents):
        raise OfficialAsiaGapError("workload boundary differs")
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
    if len(stable_keys) != 6 or len(evidence_keys) != 8:
        raise OfficialAsiaGapError("planned source keys are not unique")
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
        raise OfficialAsiaGapError(f"curated source collision: {collisions!r}")


def _validate_v75_nonmutation() -> None:
    for source, pin in V75_PINS.items():
        _pin(source, pin)
    if tree_digest(V75_RELEASE) != V75_TREE_SHA256:
        raise OfficialAsiaGapError("accepted v75 release tree differs")
    definition = json.loads(V75_DEFINITION.read_text(encoding="utf-8"))
    if len(definition.get("curated_inputs", [])) != V75_INPUT_COUNT:
        raise OfficialAsiaGapError("accepted v75 input count differs")
    selected = {row["path"] for row in definition["curated_inputs"]}
    planned_paths = {f"sources/{name}" for name in SOURCE_FILENAMES}
    if selected & planned_paths:
        raise OfficialAsiaGapError("v75 unexpectedly selects a new source path")
    entities_text = V75_ENTITIES.read_text(encoding="utf-8")
    for document in expected_source_documents().values():
        for entity in ("campus", "project"):
            if document[entity]["stable_key"] in entities_text:
                raise OfficialAsiaGapError("new source stable key collides with v75")


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise OfficialAsiaGapError(f"capture directory is absent or unsafe: {directory}")
    entries = list(directory.iterdir())
    if len(entries) != CAPTURE_FILE_COUNT:
        raise OfficialAsiaGapError("capture directory file count differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise OfficialAsiaGapError("capture directory contains a non-ordinary file")
    if sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES:
        raise OfficialAsiaGapError("capture directory total bytes differ")
    if tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise OfficialAsiaGapError("capture directory tree differs")
    for spec in CAPTURES.values():
        _pin(directory / spec["filename"], (spec["bytes"], spec["sha256"]))
    for name, pin in {**INCIDENT_FILE_PINS, **REPEATED_CAPTURE_PINS}.items():
        _pin(directory / name, pin)


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
            "entities": 6,
            "entity_snapshots": 6,
            "evidence": 8,
            "lifecycle_observations": 3,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 2,
        }
        if counts != expected:
            raise OfficialAsiaGapError(f"offline import counts differ: {counts!r}")
        capacities = [
            tuple(row)
            for row in connection.execute(
                "SELECT e.stable_key, c.metric, c.stage, c.unit, c.base "
                "FROM capacity_estimates AS c JOIN entities AS e ON e.id=c.entity_id "
                "ORDER BY e.stable_key"
            )
        ]
        if capacities != [
            (
                "curated:adaniconnex-navi-mumbai-data-center-campus",
                "critical_it_mw",
                "planned",
                "MW",
                1000.0,
            ),
            (
                "curated:adaniconnex-pune-data-center-campus",
                "critical_it_mw",
                "planned",
                "MW",
                250.0,
            ),
        ]:
            raise OfficialAsiaGapError(f"offline capacity rows differ: {capacities!r}")
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
        raise OfficialAsiaGapError("artifact must be an ordinary directory")
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise OfficialAsiaGapError("artifact closed file set differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries.values()):
        raise OfficialAsiaGapError("artifact contains a non-ordinary file")
    if stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise OfficialAsiaGapError("artifact directory mode differs")
    if any(stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries.values()):
        raise OfficialAsiaGapError("artifact file mode differs")
    for name in CONTENT_FILES[1:]:
        raw = entries[name].read_bytes()
        if raw != _canonical(json.loads(raw)):
            raise OfficialAsiaGapError(f"artifact JSON is not canonical: {name}")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest):
        raise OfficialAsiaGapError("manifest JSON is not canonical")
    if (
        manifest.get("artifact_id") != ARTIFACT_ID
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or manifest.get("candidate_assessments") != 7
        or manifest.get("curated_source_records") != 3
        or manifest.get("seed_eligible_source_records") != 3
        or manifest.get("review_only_candidates") != 4
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise OfficialAsiaGapError("manifest contract differs")
    if [row["path"] for row in manifest["files"]] != list(CONTENT_FILES):
        raise OfficialAsiaGapError("manifest file order differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (row["bytes"], row["sha256"]):
            raise OfficialAsiaGapError(f"manifest file pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise OfficialAsiaGapError("manifest checksum differs")
    expected = _artifact_documents(manifest["recorded_at"], expected_source_documents())
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected[name]:
            raise OfficialAsiaGapError(f"artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records:
        raise OfficialAsiaGapError("artifact source pins differ")
    assessment = json.loads(
        entries["candidate-assessment.json"].read_text(encoding="utf-8")
    )
    rows = {row["candidate_id"]: row for row in assessment["candidates"]}
    for candidate_id in (
        "adaniconnex-hyderabad-future-phases",
        "adaniconnex-noida-future-phases",
        "evolution-dc-vn-hcm-vn02",
        "aic-kbc-tan-phu-trung-ai-data-center",
    ):
        if rows[candidate_id]["source_record_created"]:
            raise OfficialAsiaGapError(f"review-only candidate promoted: {candidate_id}")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise OfficialAsiaGapError("validation wall clock lacks timezone")
    if require_live:
        if now.astimezone(UTC) < target:
            raise OfficialAsiaGapError("artifact recorded_at is not live")
        _assert_final_ctimes((*paths.values(), path), target)
    for capture in CAPTURES.values():
        if _instant(capture["retrieved_at"]) > target:
            raise OfficialAsiaGapError("capture retrieval post-dates recorded_at")
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
        raise OfficialAsiaGapError(
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
        raise OfficialAsiaGapError("recorded_at must be future before staging")
    source_stage = Path(
        tempfile.mkdtemp(prefix=".official-builds-asia-gap.", dir=SOURCES_ROOT)
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
            _all_stage_paths(source_stage, artifact_stage), target
        )
        if datetime.now(UTC) >= target:
            raise OfficialAsiaGapError("private staging did not finish before recorded_at")
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
                _discard_owned_directory(artifact_stage, artifact_identity, members)
            if source_stage.exists():
                members = {
                    entry.name: _identity(entry, directory=False)
                    for entry in source_stage.iterdir()
                }
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
    _assert_stage_precedes_target(
        _all_stage_paths(prepared.source_stage, prepared.artifact_stage), prepared.target
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
                raise OfficialAsiaGapError(f"source identity changed on promotion: {name}")
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        promoted.append(
            (prepared.artifact_stage, ARTIFACT, prepared.artifact_identity, True)
        )
        if not _has_identity(ARTIFACT, prepared.artifact_identity, directory=True):
            raise OfficialAsiaGapError("artifact identity changed on promotion")
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
        raise OfficialAsiaGapError("both capture origin and Trash destination exist")
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(CAPTURE_TRASH)


def _default_recorded_at() -> str:
    target = math.ceil(time.time() + 25.0)
    return datetime.fromtimestamp(target, UTC).isoformat().replace("+00:00", "Z")


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    """Publish three source records and the seven-candidate assessment."""

    target_text = recorded_at or _default_recorded_at()
    finals = tuple(SOURCES_ROOT / name for name in SOURCE_FILENAMES) + (ARTIFACT,)
    _require_finals_absent(finals, "initial")
    _validate_source_collisions()
    _validate_v75_nonmutation()
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
    _validate_v75_nonmutation()
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
            "source_records": 3,
            "seed_eligible": 3,
            "review_only": 4,
            "evidence": 8,
            "entities": 6,
            "lifecycle": 3,
            "operating_models": 0,
            "workloads": 0,
            "capacities": 2,
            "coordinates": 2,
            "geometry": 2,
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
