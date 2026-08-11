"""Build, but never publish, the CtrlS/NTT India/AdaniConneX review tranche.

Only two candidates cross the physical-build boundary: the named CtrlS
Chandanvelly and Pharmacity campuses.  CtrlS's Hyderabad page was modified on
2026-07-21 and directly says that the company is building both campuses.  The
tranche deliberately keeps every other reviewed signal out of normalized
output: announcements, upcoming listings, a virtual ceremony, planned edge
sites, NTT's unnamed aggregate India construction count, operational openings,
and AdaniConneX's phase-ambiguous Hyderabad and Noida updates.

The builder exposes no publisher or promotion function.  It writes only
private mode-0600 source and artifact stages inside mode-0700 directories.
Raw all-rights-reserved captures stay in a frozen private Trash directory and
are represented in the artifact only by factual extracts and hashes.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any, Mapping

from .external_captures import resolve_external_capture
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "ctrls-ntt-india-adaniconnex-prepublication-2026-07-22-v1"
PROSPECTIVE_ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID

CHANDANVELLY_SOURCE_FILENAME = (
    "curated-official-2026-07-22-ctrls-chandanvelly-current-build.json"
)
PHARMACITY_SOURCE_FILENAME = (
    "curated-official-2026-07-22-ctrls-pharmacity-current-build.json"
)
SOURCE_FILENAMES = (
    CHANDANVELLY_SOURCE_FILENAME,
    PHARMACITY_SOURCE_FILENAME,
)

V95_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-22-v95.json"
V95_ENTITIES = ROOT / "releases/2026-07-22-open-seed-v95/entities.csv"
V95_EVIDENCE = ROOT / "releases/2026-07-22-open-seed-v95/evidence.csv"
V95_MANIFEST = ROOT / "releases/2026-07-22-open-seed-v95/manifest.json"
V95_DEFINITION_PIN = (
    117_088,
    "e28cc9ad10229cbf718314f1bd1a4306e02faee1166dcbfbf93c01a1c82e8e15",
)
V95_ENTITIES_PIN = (
    1_058_933,
    "038bfa4ef15e4e6494ac91fa835671105d45662c0acd6b6f5c3a5e750ad3e09d",
)
V95_EVIDENCE_PIN = (
    266_383,
    "19cdd6143e891751c6f49a98754e8aa24a883f416a1001091b3e62175c9e0dac",
)
V95_MANIFEST_PIN = (
    19_195,
    "1181fa215be08c130bf237107c68a461a4762e020b7120041f19cd705b6b7af6",
)

CAPTURE_ORIGIN = Path("/Users/kian/.Trash/dc-india-build-gap.0X6WIC")
CAPTURE_RETRIEVED_AT = "2026-07-22T04:52:33Z"
CAPTURE_FILE_COUNT = 30
CAPTURE_TOTAL_BYTES = 3_431_628
CAPTURE_TREE_SHA256 = "702b3c5257c81b60d2d5b16df0cf9c41df826012018bbe72d5f79942255bbecc"
CAPTURE_FILE_PINS: Mapping[str, tuple[int, str]] = {
    "adani_data_centers.body": (
        48_315,
        "9f885f27c360c57287ffc1374447a9874a1bba2f6f0e6035792e684ab8fbbac5",
    ),
    "adani_data_centers.headers": (
        3_857,
        "969029707d759bffffeed7596d35bdd85995d96414c4e033527b28ff4fcb65a2",
    ),
    "adani_hyderabad_safety.body": (
        27_808,
        "0b9f17743a4f17bc7be49425a1c93c9b10adcb16c0de2e5b0dbe6ff6eca74f6d",
    ),
    "adani_hyderabad_safety.headers": (
        3_857,
        "3cb9dd869c90e8c40e531815b901d74132c87b251eb2c04b3e579d9d6071537f",
    ),
    "adani_phased_development.body": (
        69_731,
        "ec057dbf5efe7c0b5f8344cbdd7e74b1cf1d208c8ff2545c1f4f4dc45b6721ff",
    ),
    "adani_phased_development.headers": (
        2_617,
        "a2526763e45a0528ace7d01c046bf4ae59ccd4f9bea0270af4cdd9c3aff1ce6e",
    ),
    "ctrls_bhopal_virtual_groundbreaking.body": (
        160_538,
        "96616ad47ddc748e45bc99e01642bde87ab5dc230e864e6d1381bb043ba2d09f",
    ),
    "ctrls_bhopal_virtual_groundbreaking.headers": (
        3_594,
        "a269bee4ee37fb04d953e74c14cb5ec6f20da992d1f48ce1c6aea92f83d71942",
    ),
    "ctrls_chandanvelly_announcement.body": (
        162_353,
        "e88ccabf6f5b1d6afc8d52b04ab0a02c321b2eb9248c91994c3683da1e5c7246",
    ),
    "ctrls_chandanvelly_announcement.headers": (
        3_594,
        "5e3164020d3ff384e737ee8aab8199e1a9e83258bb3046d73793b5612896592b",
    ),
    "ctrls_current_india_linkedin.body": (
        311_176,
        "f98ba2fa19228243287a2845c0bdce83d6399864b447799c280791afc131cfa2",
    ),
    "ctrls_current_india_linkedin.headers": (
        5_301,
        "52cab4ee92fbd6ec46ffe10f1245a3e5d98c07559308851ae304f53fea521dd6",
    ),
    "ctrls_hyderabad.body": (
        272_884,
        "1822fb3465dd181fd8329f6d8b043a6e4c2bdf8eb1ba6e92633398095f0290fe",
    ),
    "ctrls_hyderabad.headers": (
        3_594,
        "a8e0037cf5282cf92aa95d02bb4a32a8704db7d7d219b169dd8c5c512ec59874",
    ),
    "ctrls_mumbai.body": (
        268_743,
        "4e29df9b315373330e27a4a8c3e141b6e502738088455943daf4ac0c5060636d",
    ),
    "ctrls_mumbai.headers": (
        3_594,
        "e74634c02e1eb86170c0db57ff35d3851a3fc6d0aaf893f475f52110e1ee204c",
    ),
    "ctrls_patna.body": (
        344_865,
        "083c3b4abe5179b2ceae984360442c9578f2ad44e091350f7175e193b6f1d5c9",
    ),
    "ctrls_patna.headers": (
        3_594,
        "9f792dd04733f0d7c70c020a0baec51dd7d7bfbe284e4f85c2915d2bebb69974",
    ),
    "ctrls_thailand_future.body": (
        133_075,
        "b7732ab9b141dced06cea5a3770542060232ae74b2992ccbb9db5443072c44a6",
    ),
    "ctrls_thailand_future.headers": (
        5_568,
        "ecf867d1752c20727a97525aa73b8d7ec3f7d0bcf3f22a5c9486b064cce415de",
    ),
    "ctrls_tier2_plans.body": (
        164_175,
        "610fc414f324b6730693da25ffbaad93f1e3b6b54b4fe51c5299f3b89241a2b3",
    ),
    "ctrls_tier2_plans.headers": (
        3_594,
        "967a5ecf450d91f3b9cb1e65e44b8e6319630c49829fd54915bcda2f94682b08",
    ),
    "ntt_bengaluru4.body": (
        403_449,
        "f2f0ac963a4e273d6840bdc31f50b331d8e41690055313320c976c295dbba379",
    ),
    "ntt_bengaluru4.headers": (
        19_099,
        "6f3b9e43061d3b94396394246aa22104d0256a00a25a9b83113357d6a0c5958f",
    ),
    "ntt_india_current_builds_linkedin.body": (
        161_718,
        "103fd3558df637bdf910d6873636b20a049c8d70a7bf4feebbd58bca51a65243",
    ),
    "ntt_india_current_builds_linkedin.headers": (
        5_301,
        "8ee0aec4ed08ddbaebf9f4145368fd8b3c1897150213588df187304763e00fb9",
    ),
    "ntt_india_locations.body": (
        399_226,
        "d11aeb900928e2d5c93a9f7a13d5694c8937cde488ba38ad1e4e69a72bb7866c",
    ),
    "ntt_india_locations.headers": (
        19_099,
        "f84f0d5868067ca68da46282a23093ca1a8ed3fc8831ac5651cd51c3247c6823",
    ),
    "ntt_noida2.body": (
        398_212,
        "d5ad2aaad2c7f3b40666cf94203efb75dc513300e90f64fc5150a73b9e448355",
    ),
    "ntt_noida2.headers": (
        19_097,
        "3241d8d1a8d67416eacea2dee5b6ae24dd45d1ba2d44e47ee92f8c1319c19f64",
    ),
}

CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

CHANDANVELLY_CAMPUS_KEY = "curated:ctrls-chandanvelly-datacenter-campus"
CHANDANVELLY_PROJECT_KEY = f"{CHANDANVELLY_CAMPUS_KEY}:current-build"
PHARMACITY_CAMPUS_KEY = "curated:ctrls-pharmacity-datacenter-campus"
PHARMACITY_PROJECT_KEY = f"{PHARMACITY_CAMPUS_KEY}:current-build"

CHANDANVELLY_STATUS_EVIDENCE_KEY = (
    "ctrls-chandanvelly-building-page-modified-2026-07-21-captured-2026-07-22"
)
CHANDANVELLY_ANNOUNCEMENT_EVIDENCE_KEY = (
    "ctrls-chandanvelly-announcement-2025-01-20-captured-2026-07-22"
)
PHARMACITY_STATUS_EVIDENCE_KEY = (
    "ctrls-pharmacity-building-page-modified-2026-07-21-captured-2026-07-22"
)


@dataclass(frozen=True)
class Capture:
    capture_id: str
    stem: str
    url: str
    publisher: str
    published_at: str | None
    response_date_header: str
    content_type: str
    claim_use: str


CAPTURES = (
    Capture(
        "ctrls_hyderabad",
        "ctrls_hyderabad",
        "https://www.ctrls.com/datacenter-hyderabad/",
        "CtrlS Datacenters Ltd",
        None,
        "2026-07-22T04:50:38Z",
        "text/html; charset=UTF-8",
        "normalized_named_current_build_status_and_identity",
    ),
    Capture(
        "ctrls_chandanvelly_announcement",
        "ctrls_chandanvelly_announcement",
        "https://www.ctrls.com/press-release-ctrls-unveils-plans-for-new-datacenter-park-on-a-40-acre-land-parcel-near-hyderabad/",
        "CtrlS Datacenters Ltd",
        "2025-01-20",
        "2026-07-22T04:50:40Z",
        "text/html; charset=UTF-8",
        "identity_locality_and_open_bound_capacity_metadata_only",
    ),
    Capture(
        "ctrls_current_india_linkedin",
        "ctrls_current_india_linkedin",
        "https://www.linkedin.com/posts/ctrls-datacenters-ltd_how-india-is-scaling-to-3-gw-of-datacenter-activity-7468186839968034816-aHQ6",
        "CtrlS Datacenters Ltd via LinkedIn",
        "2026-06-04",
        "2026-07-22T04:50:42Z",
        "text/html; charset=utf-8",
        "aggregate_design_and_construction_context_only",
    ),
    Capture(
        "ntt_india_current_builds_linkedin",
        "ntt_india_current_builds_linkedin",
        "https://www.linkedin.com/posts/ntt-global-data-centers_digitalinfrastructure-digitaltransformation-activity-7404225841762910208-nZV-",
        "NTT Global Data Centers via LinkedIn",
        "2025-12-09",
        "2026-07-22T04:50:43Z",
        "text/html; charset=utf-8",
        "review_only_unnamed_aggregate_construction_count",
    ),
    Capture(
        "ntt_india_locations",
        "ntt_india_locations",
        "https://services.global.ntt/en-us/services-and-products/global-data-centers/global-locations/india",
        "NTT DATA, Inc.",
        None,
        "2026-07-22T04:50:44Z",
        "text/html; charset=utf-8",
        "review_only_current_facility_inventory",
    ),
    Capture(
        "ntt_bengaluru4",
        "ntt_bengaluru4",
        "https://services.global.ntt/en-us/services-and-products/global-data-centers/global-locations/india/bengaluru-4-campus",
        "NTT DATA, Inc.",
        None,
        "2026-07-22T04:50:45Z",
        "text/html; charset=utf-8",
        "review_only_planned_capacity_without_building_specific_status",
    ),
    Capture(
        "ntt_noida2",
        "ntt_noida2",
        "https://services.global.ntt/en-us/services-and-products/global-data-centers/global-locations/india/noida-2-data-center",
        "NTT DATA, Inc.",
        None,
        "2026-07-22T04:50:46Z",
        "text/html; charset=utf-8",
        "review_only_future_building_capacity_without_current_physical_status",
    ),
    Capture(
        "adani_phased_development",
        "adani_phased_development",
        "https://resources.adaniconnex.com/blog/scaling-indias-data-centres-responsibly-for-the-ai-era-bridging-people-planet-and-growth",
        "AdaniConneX",
        "2026-06-01",
        "2026-07-22T04:50:47Z",
        "text/html; charset=UTF-8",
        "review_only_phase_ambiguous_hyderabad_and_noida_update",
    ),
    Capture(
        "adani_data_centers",
        "adani_data_centers",
        "https://www.adaniconnex.com/data-centers",
        "AdaniConneX",
        None,
        "2026-07-22T04:50:48Z",
        "text/html; charset=utf-8",
        "review_only_current_identity_capacity_and_stale_rfs_context",
    ),
    Capture(
        "adani_hyderabad_safety",
        "adani_hyderabad_safety",
        "https://www.adaniconnex.com/resources/All-Resources/Press-Release/AdaniConneXs-Hyderabad-Site-Gets-Five-Star--Grading-from-British-Safety-Council",
        "AdaniConneX",
        "2024-03-13",
        "2026-07-22T04:50:49Z",
        "text/html; charset=utf-8",
        "review_only_older_site_safety_evidence",
    ),
    Capture(
        "ctrls_mumbai",
        "ctrls_mumbai",
        "https://www.ctrls.com/datacenter-mumbai/",
        "CtrlS Datacenters Ltd",
        None,
        "2026-07-22T04:52:26Z",
        "text/html; charset=UTF-8",
        "review_only_upcoming_dc6_dc7_listing",
    ),
    Capture(
        "ctrls_bhopal_virtual_groundbreaking",
        "ctrls_bhopal_virtual_groundbreaking",
        "https://www.ctrls.com/press-release-ctrls-datacenters-to-invest-500-crore-in-bhopal/",
        "CtrlS Datacenters Ltd",
        "2025-04-28",
        "2026-07-22T04:52:28Z",
        "text/html; charset=UTF-8",
        "review_only_off_site_virtual_ceremony_and_upcoming_language",
    ),
    Capture(
        "ctrls_patna",
        "ctrls_patna",
        "https://www.ctrls.com/patna-datacenter/",
        "CtrlS Datacenters Ltd",
        None,
        "2026-07-22T04:52:29Z",
        "text/html; charset=UTF-8",
        "review_only_current_listing_without_lifecycle_status",
    ),
    Capture(
        "ctrls_tier2_plans",
        "ctrls_tier2_plans",
        "https://www.ctrls.com/blog-tier2-cities-india-hyperscale-datacenters/",
        "CtrlS Datacenters Ltd",
        "2025-10-23",
        "2026-07-22T04:52:31Z",
        "text/html; charset=UTF-8",
        "review_only_planned_edge_sites_and_patna_status_ambiguity",
    ),
    Capture(
        "ctrls_thailand_future",
        "ctrls_thailand_future",
        "https://www.linkedin.com/posts/ctrls-datacenters-ltd_bangkok-datacenters-ctrls-activity-7132241895790944256-BV5K",
        "CtrlS Datacenters Ltd via LinkedIn",
        "2023-11-20",
        "2026-07-22T04:52:33Z",
        "text/html; charset=utf-8",
        "review_only_future_chonburi_language_without_current_physical_update",
    ),
)
CAPTURE_BY_ID = {capture.capture_id: capture for capture in CAPTURES}


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _pin(path: Path, expected: tuple[int, str]) -> None:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"missing or unsafe pinned file: {path}")
    actual = (path.stat().st_size, _sha256(path))
    if actual != expected:
        raise RuntimeError(f"pin differs for {path}: {actual!r}")


def _capture_metadata(capture_id: str) -> dict[str, Any]:
    capture = CAPTURE_BY_ID[capture_id]
    body = CAPTURE_FILE_PINS[f"{capture.stem}.body"]
    return {
        "content_hash_scope": (
            f"SHA-256 of the exact {body[0]}-byte captured public response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "private_capture": {
            "body_path": f"{capture.stem}.body",
            "body_bytes": CAPTURE_FILE_PINS[f"{capture.stem}.body"][0],
            "body_sha256": CAPTURE_FILE_PINS[f"{capture.stem}.body"][1],
            "headers_path": f"{capture.stem}.headers",
            "headers_bytes": CAPTURE_FILE_PINS[f"{capture.stem}.headers"][0],
            "headers_sha256": CAPTURE_FILE_PINS[f"{capture.stem}.headers"][1],
            "response_date_header": capture.response_date_header,
            "retrieved_at_semantics": (
                "The package capture-completion timestamp is used for all files; "
                "the captured response Date header preserves per-response timing."
            ),
            "retained_private": True,
            "redistributed": False,
        },
        "rights_scope": (
            "Compact factual extraction from an all-rights-reserved publisher "
            "page; captured HTML and publisher media are not redistributed."
        ),
    }


def _evidence(
    *,
    key: str,
    capture_id: str,
    title: str,
    excerpt: str,
    source_family: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    capture = CAPTURE_BY_ID[capture_id]
    return {
        "key": key,
        "kind": "company_disclosure",
        "title": title,
        "source_url": capture.url,
        "publisher": capture.publisher,
        "source_family": source_family,
        "published_at": capture.published_at,
        "retrieved_at": CAPTURE_RETRIEVED_AT,
        "license": "all-rights-reserved",
        "attribution": capture.publisher,
        "excerpt": excerpt,
        "content_hash": CAPTURE_FILE_PINS[f"{capture.stem}.body"][1],
        "metadata": {**_capture_metadata(capture_id), **metadata},
    }


def _entity(
    *,
    stable_key: str,
    name: str,
    address: str,
    evidence_key: str,
    confidence: float,
) -> dict[str, Any]:
    return {
        "stable_key": stable_key,
        "name": name,
        "country": "India",
        "address": address,
        "roles": {"developer": ["CtrlS Datacenters Ltd"]},
        "coordinates": None,
        "geometry": None,
        "evidence_key": evidence_key,
        "as_of_date": "2026-07-21",
        "method": "authoritative_locality",
        "confidence": confidence,
    }


def _chandanvelly_document() -> dict[str, Any]:
    current = _evidence(
        key=CHANDANVELLY_STATUS_EVIDENCE_KEY,
        capture_id="ctrls_hyderabad",
        title="CtrlS Hyderabad data centers — Chandanvelly campus",
        excerpt=(
            "CtrlS's dated current Hyderabad page says it is building two named "
            "campuses and identifies one as Chandanvelly."
        ),
        source_family="ctrls_current_location_pages",
        metadata={
            "page_date_published_as_reported": "2024-01-11T07:01:18+05:30",
            "page_date_modified_as_reported": "2026-07-21T12:24:34+05:30",
            "status_wording_as_reported": (
                "We’re building two of India’s largest AI-ready datacenter campuses."
            ),
            "identity_binding": (
                "Chandanvelly Datacenter Campus is one of the two immediately "
                "named campus sections beneath the publisher's build statement."
            ),
            "normalized_lifecycle": "under_construction",
            "physical_stage_guardrail": (
                "The page supports only generic under_construction; it does not "
                "identify site preparation, foundations, shell, fit-out, MEP, "
                "commissioning, energization, or operation."
            ),
            "current_page_capacity_not_normalized": {
                "wording": "Over 700 MW Capacity Scalable to 1.4GW",
                "reason": (
                    "The current page does not type the displayed capacity as IT, "
                    "gross facility, grid connection, generation, or current draw."
                ),
                "capacity_row_created": False,
            },
            "sanctioned_power_not_normalized": {
                "wording": "Approved Sanction Power of 700 MVA",
                "reason": (
                    "MVA is not converted to MW and does not establish current "
                    "draw, consumption, energization, or an IT-load value."
                ),
                "capacity_row_created": False,
            },
            "classification_guardrail": (
                "AI-ready is publisher marketing context only; no facility-type, "
                "operating-model, workload, tenant, or user row is created."
            ),
            "spatial_guardrail": (
                "No map link, image, geocoder, parcel, footprint, centroid, or "
                "coordinate inference is used."
            ),
        },
    )
    announcement = _evidence(
        key=CHANDANVELLY_ANNOUNCEMENT_EVIDENCE_KEY,
        capture_id="ctrls_chandanvelly_announcement",
        title=(
            "CtrlS unveils plans for a Chandanvelly datacenter park near Hyderabad"
        ),
        excerpt=(
            "The older CtrlS release identifies the 40-acre Chandanvelly Industrial "
            "Park site near Hyderabad; it is not used as physical-status evidence."
        ),
        source_family="ctrls_press_releases",
        metadata={
            "identity_and_locality_as_reported": (
                "Chandanvelly Industrial Park near Hyderabad"
            ),
            "announcement_only": True,
            "lifecycle_claim_from_this_evidence": False,
            "reported_potential_it_load": {
                "wording": "over 600 MW IT load when fully developed",
                "scope": "planned_full_campus_potential",
                "capacity_row_created": False,
                "reason": (
                    "The schema has no open-lower-bound qualifier; encoding over "
                    "600 MW as exactly 600 MW would create false precision."
                ),
            },
            "reported_phase_1_sanctioned_power": {
                "value": 250,
                "unit": "MW",
                "capacity_row_created": False,
                "reason": (
                    "The announcement does not identify this as contracted grid "
                    "connection, current draw, energization, or IT load."
                ),
            },
            "design_pue_not_normalized": {
                "range": [1.12, 1.32],
                "measured": False,
                "efficiency_row_created": False,
            },
        },
    )
    return {
        "schema_version": "1.1",
        "evidence": [current, announcement],
        "campus": _entity(
            stable_key=CHANDANVELLY_CAMPUS_KEY,
            name="CtrlS Chandanvelly Datacenter Campus",
            address="Chandanvelly Industrial Park near Hyderabad, India",
            evidence_key=CHANDANVELLY_STATUS_EVIDENCE_KEY,
            confidence=0.99,
        ),
        "project": _entity(
            stable_key=CHANDANVELLY_PROJECT_KEY,
            name="CtrlS Chandanvelly Datacenter Campus Current Build",
            address="Chandanvelly Industrial Park near Hyderabad, India",
            evidence_key=CHANDANVELLY_STATUS_EVIDENCE_KEY,
            confidence=0.99,
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": CHANDANVELLY_STATUS_EVIDENCE_KEY,
                "as_of_date": "2026-07-21",
                "method": "authoritative_physical_status_update",
                "confidence": 0.99,
            }
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _pharmacity_document() -> dict[str, Any]:
    evidence = _evidence(
        key=PHARMACITY_STATUS_EVIDENCE_KEY,
        capture_id="ctrls_hyderabad",
        title="CtrlS Hyderabad data centers — Pharmacity campus",
        excerpt=(
            "CtrlS's dated current Hyderabad page says it is building two named "
            "campuses and identifies one as Pharmacity."
        ),
        source_family="ctrls_current_location_pages",
        metadata={
            "page_date_published_as_reported": "2024-01-11T07:01:18+05:30",
            "page_date_modified_as_reported": "2026-07-21T12:24:34+05:30",
            "status_wording_as_reported": (
                "We’re building two of India’s largest AI-ready datacenter campuses."
            ),
            "identity_binding": (
                "Pharmacity Datacenter Campus is one of the two immediately named "
                "campus sections beneath the publisher's build statement."
            ),
            "normalized_lifecycle": "under_construction",
            "physical_stage_guardrail": (
                "The page supports only generic under_construction; it does not "
                "identify site preparation, foundations, shell, fit-out, MEP, "
                "commissioning, energization, or operation."
            ),
            "capacity_not_normalized": {
                "wording": "Up to 750 MW Capacity Scalable to 1.2GW",
                "reason": (
                    "The page does not type either value as IT, gross facility, "
                    "grid connection, generation, or current draw."
                ),
                "capacity_row_created": False,
            },
            "green_power_not_normalized": {
                "wording": "100% Green Power Project",
                "reason": (
                    "The label supplies no measured or contracted renewable share, "
                    "annual energy, consumption, grid draw, or commissioning fact."
                ),
                "energy_or_efficiency_row_created": False,
            },
            "classification_guardrail": (
                "AI-ready is publisher marketing context only; no facility-type, "
                "operating-model, workload, tenant, or user row is created."
            ),
            "locality_guardrail": (
                "The current page binds the named campus only to Hyderabad; no "
                "more specific address or coordinate is inferred."
            ),
            "spatial_guardrail": (
                "No map link, image, geocoder, parcel, footprint, centroid, or "
                "coordinate inference is used."
            ),
        },
    )
    return {
        "schema_version": "1.1",
        "evidence": [evidence],
        "campus": _entity(
            stable_key=PHARMACITY_CAMPUS_KEY,
            name="CtrlS Pharmacity Datacenter Campus",
            address="Hyderabad, India",
            evidence_key=PHARMACITY_STATUS_EVIDENCE_KEY,
            confidence=0.98,
        ),
        "project": _entity(
            stable_key=PHARMACITY_PROJECT_KEY,
            name="CtrlS Pharmacity Datacenter Campus Current Build",
            address="Hyderabad, India",
            evidence_key=PHARMACITY_STATUS_EVIDENCE_KEY,
            confidence=0.98,
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": PHARMACITY_STATUS_EVIDENCE_KEY,
                "as_of_date": "2026-07-21",
                "method": "authoritative_physical_status_update",
                "confidence": 0.98,
            }
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    documents = {
        CHANDANVELLY_SOURCE_FILENAME: _chandanvelly_document(),
        PHARMACITY_SOURCE_FILENAME: _pharmacity_document(),
    }
    if tuple(documents) != SOURCE_FILENAMES:
        raise RuntimeError("CtrlS source inventory differs")
    if sum(len(document["evidence"]) for document in documents.values()) != 3:
        raise RuntimeError("CtrlS evidence count differs")
    for document in documents.values():
        if (
            document["schema_version"] != "1.1"
            or len(document["lifecycle"]) != 1
            or document["operating_models"]
            or document["workloads"]
            or document["capacities"]
        ):
            raise RuntimeError("CtrlS normalization boundary differs")
        for entity in ("campus", "project"):
            if (
                document[entity]["coordinates"] is not None
                or document[entity]["geometry"] is not None
            ):
                raise RuntimeError("CtrlS spatial boundary differs")
    return documents


def _validate_capture_directory(
    directory: Path | None = None,
) -> None:
    if directory is None:
        directory = resolve_external_capture(CAPTURE_ORIGIN)
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("private CtrlS/NTT/Adani capture directory is unsafe")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555:
        raise RuntimeError("private capture directory is not frozen")
    entries = {path.name: path for path in directory.iterdir()}
    if set(entries) != set(CAPTURE_FILE_PINS):
        raise RuntimeError("private capture inventory differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(entries[name], pin)
        if stat.S_IMODE(entries[name].stat().st_mode) != 0o444:
            raise RuntimeError(f"private capture is not frozen: {name}")
    if sum(pin[0] for pin in CAPTURE_FILE_PINS.values()) != CAPTURE_TOTAL_BYTES:
        raise RuntimeError("private capture byte total differs")
    if tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise RuntimeError("private capture tree differs")


def _planned_keys() -> tuple[set[str], set[str], set[str]]:
    stable = {
        CHANDANVELLY_CAMPUS_KEY,
        CHANDANVELLY_PROJECT_KEY,
        PHARMACITY_CAMPUS_KEY,
        PHARMACITY_PROJECT_KEY,
    }
    evidence = {
        CHANDANVELLY_STATUS_EVIDENCE_KEY,
        CHANDANVELLY_ANNOUNCEMENT_EVIDENCE_KEY,
        PHARMACITY_STATUS_EVIDENCE_KEY,
    }
    paths = {f"sources/{name}" for name in SOURCE_FILENAMES}
    return stable, evidence, paths


def _v95_witness() -> dict[str, Any]:
    _pin(V95_DEFINITION, V95_DEFINITION_PIN)
    _pin(V95_ENTITIES, V95_ENTITIES_PIN)
    _pin(V95_EVIDENCE, V95_EVIDENCE_PIN)
    _pin(V95_MANIFEST, V95_MANIFEST_PIN)
    definition = json.loads(V95_DEFINITION.read_text(encoding="utf-8"))
    manifest = json.loads(V95_MANIFEST.read_text(encoding="utf-8"))
    selected = definition.get("curated_inputs")
    if (
        definition.get("release_id") != "2026-07-22-open-seed-v95"
        or not isinstance(selected, list)
        or len(selected) != 507
        or manifest.get("entities") != 1_029
        or manifest.get("evidence_records") != 678
        or manifest.get("recorded_at") != "2026-07-22T04:21:58Z"
    ):
        raise RuntimeError("v95 contract differs")
    with V95_ENTITIES.open(encoding="utf-8", newline="") as stream:
        entities = list(csv.DictReader(stream))
    with V95_EVIDENCE.open(encoding="utf-8", newline="") as stream:
        evidence_rows = list(csv.DictReader(stream))
    if len(entities) != 1_029 or len(evidence_rows) != 678:
        raise RuntimeError("v95 row counts differ")
    selected_paths = {row["path"] for row in selected}
    selected_evidence: set[str] = set()
    for row in selected:
        document = json.loads((ROOT / row["path"]).read_text(encoding="utf-8"))
        selected_evidence.update(item["key"] for item in document["evidence"])
    planned_stable, planned_evidence, planned_paths = _planned_keys()
    stable_collisions = sorted(
        planned_stable & {row["stable_key"] for row in entities}
    )
    evidence_collisions = sorted(planned_evidence & selected_evidence)
    path_collisions = sorted(planned_paths & selected_paths)
    if stable_collisions or evidence_collisions or path_collisions:
        raise RuntimeError("planned CtrlS records collide with v95")
    return {
        "release_id": "2026-07-22-open-seed-v95",
        "recorded_at": "2026-07-22T04:21:58Z",
        "selected_input_count": 507,
        "entity_count": 1_029,
        "public_evidence_count": 678,
        "planned_stable_key_collisions": stable_collisions,
        "planned_evidence_key_collisions": evidence_collisions,
        "planned_selected_path_collisions": path_collisions,
        "pins": {
            "definition_sha256": V95_DEFINITION_PIN[1],
            "entities_sha256": V95_ENTITIES_PIN[1],
            "evidence_sha256": V95_EVIDENCE_PIN[1],
            "manifest_sha256": V95_MANIFEST_PIN[1],
        },
    }


def _current_source_collision_witness() -> dict[str, Any]:
    planned_stable, planned_evidence, _ = _planned_keys()
    stable_hits: list[dict[str, str]] = []
    evidence_hits: list[dict[str, str]] = []
    identity_hits: list[dict[str, str]] = []
    for path in sorted(SOURCES_ROOT.glob("curated-*.json")):
        if path.name in SOURCE_FILENAMES:
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        for entity_name in ("campus", "project"):
            entity = document.get(entity_name)
            if not isinstance(entity, dict):
                continue
            key = entity.get("stable_key")
            if key in planned_stable:
                stable_hits.append({"path": path.name, "stable_key": key})
            identity_text = " ".join(
                str(entity.get(field, "")) for field in ("name", "address")
            ).lower()
            if "chandanvelly" in identity_text or "pharmacity" in identity_text:
                identity_hits.append(
                    {"path": path.name, "identity": identity_text.strip()}
                )
        for item in document.get("evidence", []):
            if isinstance(item, dict) and item.get("key") in planned_evidence:
                evidence_hits.append(
                    {"path": path.name, "evidence_key": item["key"]}
                )
    filename_hits = [
        str(SOURCES_ROOT / name)
        for name in SOURCE_FILENAMES
        if (SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink()
    ]
    if stable_hits or evidence_hits or identity_hits or filename_hits:
        raise RuntimeError(
            "planned CtrlS records collide with a source added after v95: "
            f"{stable_hits!r}, {evidence_hits!r}, {identity_hits!r}, "
            f"{filename_hits!r}"
        )
    return {
        "scan_pattern": "sources/curated-*.json",
        "planned_source_filename_collisions": filename_hits,
        "planned_stable_key_collisions": stable_hits,
        "planned_evidence_key_collisions": evidence_hits,
        "planned_identity_collisions": identity_hits,
    }


def _source_records(
    documents: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "path": f"prospective-sources/{name}",
            "bytes": len(_canonical(documents[name])),
            "sha256": _sha256_bytes(_canonical(documents[name])),
            "schema_version": "1.1",
            "campus_stable_key": documents[name]["campus"]["stable_key"],
            "project_stable_key": documents[name]["project"]["stable_key"],
            "evidence_records": len(documents[name]["evidence"]),
            "lifecycle_observations": 1,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
            "coordinate_observations": 0,
            "geometry_observations": 0,
            "disposition": "governed_prepublication_current_physical_build",
            "published": False,
            "seeded": False,
        }
        for name in SOURCE_FILENAMES
    ]


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-prepublication-assessment-v1",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "candidate_count": 12,
        "governed_source_candidate_count": 2,
        "review_only_count": 10,
        "operator_completeness_claimed": False,
        "candidates": [
            {
                "candidate_id": "ctrls-chandanvelly-current-build",
                "operator": "CtrlS Datacenters Ltd",
                "decision": "governed_prepublication_current_physical_build",
                "source_paths": [
                    f"prospective-sources/{CHANDANVELLY_SOURCE_FILENAME}"
                ],
                "campus_stable_key": CHANDANVELLY_CAMPUS_KEY,
                "project_stable_key": CHANDANVELLY_PROJECT_KEY,
                "lifecycle": "under_construction",
                "as_of_date": "2026-07-21",
                "basis": "dated_current_page_directly_says_building_named_campus",
                "capacity_rows_created": 0,
                "energy_rows_created": 0,
                "coordinate_rows_created": 0,
            },
            {
                "candidate_id": "ctrls-pharmacity-current-build",
                "operator": "CtrlS Datacenters Ltd",
                "decision": "governed_prepublication_current_physical_build",
                "source_paths": [
                    f"prospective-sources/{PHARMACITY_SOURCE_FILENAME}"
                ],
                "campus_stable_key": PHARMACITY_CAMPUS_KEY,
                "project_stable_key": PHARMACITY_PROJECT_KEY,
                "lifecycle": "under_construction",
                "as_of_date": "2026-07-21",
                "basis": "dated_current_page_directly_says_building_named_campus",
                "capacity_rows_created": 0,
                "energy_rows_created": 0,
                "coordinate_rows_created": 0,
            },
            {
                "candidate_id": "ctrls-mumbai-dc6-dc7",
                "operator": "CtrlS Datacenters Ltd",
                "decision": "review_only_upcoming_and_aggregate_stage_ambiguity",
                "source_paths": [],
                "stable_key_created": False,
                "lifecycle_claim_created": False,
                "reason": (
                    "The current Mumbai page labels DC6 and DC7 upcoming. The "
                    "June 2026 company post mixes datacenters in design and "
                    "construction and does not assign a physical stage to DC6/DC7."
                ),
            },
            {
                "candidate_id": "ctrls-bhopal-greenfield",
                "operator": "CtrlS Datacenters Ltd",
                "decision": "review_only_virtual_ceremony_without_site_activity",
                "source_paths": [],
                "stable_key_created": False,
                "lifecycle_claim_created": False,
                "reason": (
                    "The 2025 event was explicitly a virtual groundbreaking in "
                    "Indore and the release calls the Bhopal facility upcoming; no "
                    "post-event onsite physical-build update was captured."
                ),
            },
            {
                "candidate_id": "ctrls-patna-edge-dc2",
                "operator": "CtrlS Datacenters Ltd",
                "decision": "review_only_current_state_ambiguous",
                "source_paths": [],
                "stable_key_created": False,
                "lifecycle_claim_created": False,
                "reason": (
                    "The current page lists Patna Edge DC2 without a lifecycle "
                    "label, while the late-2025 blog said it would soon be "
                    "operational. Construction versus operation is unresolved."
                ),
            },
            {
                "candidate_id": "ctrls-tier2-planned-sites",
                "operator": "CtrlS Datacenters Ltd",
                "decision": "review_only_planned_portfolio",
                "source_paths": [],
                "stable_key_created": False,
                "lifecycle_claim_created": False,
                "reason": (
                    "Ahmedabad/GIFT City, Bhubaneswar, Bhopal, Lucknow, Kochi, "
                    "and Guwahati are described as planned in the captured current "
                    "company material, not as site-specific physical builds."
                ),
            },
            {
                "candidate_id": "ctrls-thailand-chonburi-campus",
                "operator": "CtrlS Datacenters Ltd",
                "decision": "review_only_future_language_without_current_update",
                "source_paths": [],
                "stable_key_created": False,
                "lifecycle_claim_created": False,
                "reason": (
                    "The captured 2023 first-party transcript says the facility is "
                    "going to be built; no current site-specific physical update was "
                    "found in this bounded tranche."
                ),
            },
            {
                "candidate_id": "ntt-india-four-unnamed-builds",
                "operator": "NTT Global Data Centers India",
                "decision": "review_only_aggregate_identity_unresolved",
                "source_paths": [],
                "stable_key_created": False,
                "lifecycle_claim_created": False,
                "capacity_claim_created": False,
                "reason": (
                    "NTT's December 2025 post reports four data centers and more "
                    "than 90 MW under construction, but it does not name the four."
                ),
            },
            {
                "candidate_id": "ntt-bengaluru-4b-4c",
                "operator": "NTT Global Data Centers India",
                "decision": "review_only_planned_capacity_without_physical_status",
                "source_paths": [],
                "stable_key_created": False,
                "lifecycle_claim_created": False,
                "reason": (
                    "The launch post identifies only 4A as live and the current "
                    "campus page reports planned capacity across 4A, 4B, and 4C; "
                    "neither source assigns physical-build status to 4B or 4C."
                ),
            },
            {
                "candidate_id": "ntt-noida-2-building-b",
                "operator": "NTT Global Data Centers India",
                "decision": "review_only_future_capacity_without_current_status",
                "source_paths": [],
                "stable_key_created": False,
                "lifecycle_claim_created": False,
                "reason": (
                    "The current page says Building B will support 30.4 MW, while "
                    "the 2024 opening covered Building A. No current physical-build "
                    "status for Building B was captured."
                ),
            },
            {
                "candidate_id": "adaniconnex-hyderabad-future-phases",
                "operator": "AdaniConneX",
                "decision": "review_only_no_distinct_physical_successor",
                "source_paths": [],
                "stable_key_created": False,
                "lifecycle_claim_created": False,
                "reason": (
                    "The June 2026 update says Hyderabad is advancing through "
                    "phased development, but the same material contains operational "
                    "signals and does not identify a distinct physical new phase."
                ),
                "prior_review_alignment": (
                    "Matches the explicit review-only disposition in the 2026-07-21 "
                    "Asia official-build artifact."
                ),
            },
            {
                "candidate_id": "adaniconnex-noida-future-phases",
                "operator": "AdaniConneX",
                "decision": "review_only_no_distinct_physical_successor",
                "source_paths": [],
                "stable_key_created": False,
                "lifecycle_claim_created": False,
                "reason": (
                    "The June 2026 update says Noida is advancing through phased "
                    "development but also calls Noida operational and does not "
                    "identify a distinct physical new phase."
                ),
                "prior_review_alignment": (
                    "Matches the explicit review-only disposition in the 2026-07-21 "
                    "Asia official-build artifact."
                ),
            },
        ],
        "out_of_scope_already_in_v95": [
            "AdaniConneX Navi Mumbai Current Phased Development",
            "AdaniConneX Pune PNQ04 Current Build",
        ],
        "operational_openings_not_candidate_records": [
            "CtrlS Chennai DC1",
            "CtrlS Kolkata DC1",
            "NTT Bengaluru 4A",
            "NTT Noida 2 Building A",
            "NTT NAV2 live facilities",
        ],
    }


def _retrieval_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "capture_completion_timestamp": CAPTURE_RETRIEVED_AT,
        "successful_http_200_body_captures": len(CAPTURES),
        "request_credentials_supplied": False,
        "raw_capture_redistributed": False,
        "capture_directory": str(CAPTURE_ORIGIN),
        "capture_directory_retained_private": True,
        "capture_directory_mode": "0555",
        "capture_file_mode": "0444",
        "capture_file_count": CAPTURE_FILE_COUNT,
        "capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "captures": [
            {
                "capture_id": capture.capture_id,
                "publisher": capture.publisher,
                "requested_url": capture.url,
                "effective_url": capture.url,
                "published_at": capture.published_at,
                "retrieved_at": CAPTURE_RETRIEVED_AT,
                "response_date_header": capture.response_date_header,
                "http_status": 200,
                "content_type": capture.content_type,
                "claim_use": capture.claim_use,
                "body": {
                    "path": f"{capture.stem}.body",
                    "bytes": CAPTURE_FILE_PINS[f"{capture.stem}.body"][0],
                    "sha256": CAPTURE_FILE_PINS[f"{capture.stem}.body"][1],
                },
                "headers": {
                    "path": f"{capture.stem}.headers",
                    "bytes": CAPTURE_FILE_PINS[f"{capture.stem}.headers"][0],
                    "sha256": CAPTURE_FILE_PINS[f"{capture.stem}.headers"][1],
                },
            }
            for capture in CAPTURES
        ],
        "complete_private_file_inventory": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in sorted(CAPTURE_FILE_PINS.items())
        ],
    }


def _artifact_documents(
    recorded_at: str,
    documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    assessment = _candidate_assessment(recorded_at)
    v95 = _v95_witness()
    current_sources = _current_source_collision_witness()
    source_records = _source_records(documents)
    readme = f"""# CtrlS / NTT India / AdaniConneX tranche — prepublication only

Built at {recorded_at}; not published or integrated.

Only CtrlS Chandanvelly and CtrlS Pharmacity cross the physical-build boundary. CtrlS's current Hyderabad page was modified on 2026-07-21 and directly says it is building the two immediately named campuses. The normalized result is four entity snapshots, three evidence records, two generic `under_construction` lifecycle observations, and zero operating-model, workload, facility-type, capacity, energy, efficiency, coordinate, or geometry rows.

The current Chandanvelly page does not type its 700 MW display; its 700 MVA sanctioned-power value is not converted to MW. The older release's potential IT load is an open lower bound above 600 MW, which this schema cannot encode without false precision. Pharmacity's 750 MW and 1.2 GW displays are untyped. Its `100% Green Power Project` label is not measured consumption or a contracted renewable share. All remain evidence metadata only.

The rejection ledger preserves CtrlS upcoming, virtual-ceremony, planned, and state-ambiguous candidates; NTT's four unnamed India builds and unproven 4B/4C/Noida-B identities; and AdaniConneX Hyderabad/Noida phase ambiguity. Operational openings are not converted into construction records. AdaniConneX Navi Mumbai and Pune are already in v95 and are outside this tranche.

Raw captures remain private and frozen. No map, image, satellite, aerial, computer-vision, geocoder, parcel, footprint, or coordinate inference contributes. No final source, final artifact, open-seed successor, release, federation, identity, timeline, construction-master, map, or coverage file is created.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "operator_completeness_claimed": False,
        "source_records": source_records,
        "totals": {
            "candidate_assessments": 12,
            "source_records": 2,
            "governed_prepublication_candidates": 2,
            "review_only_candidates": 10,
            "distinct_campuses_in_source_records": 2,
            "projects": 2,
            "distinct_entity_snapshots": 4,
            "new_entities_against_v95": 4,
            "evidence_records": 3,
            "lifecycle_observations": 2,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
            "energy_consumption_observations": 0,
            "facility_type_observations": 0,
            "coordinate_observations": 0,
            "geometry_observations": 0,
            "satellite_observations": 0,
        },
        "v95_collision_witness": v95,
        "accepted_later_source_collision_witness": current_sources,
        "integration": {
            "published": False,
            "final_source_paths_created": False,
            "final_artifact_path_created": False,
            "open_seed_successor_created": False,
            "release_integration": "none",
            "federation_integration": "none",
            "identity_integration": "none",
            "timeline_integration": "none",
            "construction_master_integration": "none",
            "map_integration": "none",
            "coverage_integration": "none",
        },
        "prepublication_contract": {
            "version": 1,
            "publisher_function_present": False,
            "promotion_function_present": False,
            "source_stage_file_mode": "0600",
            "source_stage_directory_mode": "0700",
            "artifact_stage_file_mode": "0600",
            "artifact_stage_directory_mode": "0700",
            "raw_capture_file_mode": "0444",
            "raw_capture_directory_mode": "0555",
            "raw_capture_retained_private": True,
        },
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-disposition-v3",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "source_rights": (
            "Captured official and publisher-authored response bodies are treated "
            "as all-rights-reserved; no redistribution license was relied on."
        ),
        "artifact_is_hash_and_factual_extract_only": True,
        "raw_capture_redistributed": False,
        "raw_response_bodies_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "publisher_media_retained_in_artifact": False,
        "request_credentials_supplied": False,
        "private_capture_directory": str(CAPTURE_ORIGIN),
        "private_capture_directory_retained": True,
        "private_capture_directory_mode": "0555",
        "private_capture_file_mode": "0444",
        "private_capture_file_count": CAPTURE_FILE_COUNT,
        "private_capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "private_capture_tree_sha256": CAPTURE_TREE_SHA256,
        "deletion_performed": False,
        "publication_performed": False,
    }
    return {
        "README.md": readme.encode("utf-8"),
        "candidate-assessment.json": _canonical(assessment),
        "retrieval-inventory.json": _canonical(_retrieval_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="ctrls-ntt-adani-prepublication-import-", dir="/private/tmp"
    ) as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            for name in SOURCE_FILENAMES:
                adapter.import_file(connection, paths[name], recorded_at=recorded_at)
        errors = validate_database(connection)
        if errors:
            raise RuntimeError(f"offline database validation failed: {errors!r}")
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
            "entities": 4,
            "entity_snapshots": 4,
            "evidence": 3,
            "lifecycle_observations": 2,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
        }
        if counts != expected:
            raise RuntimeError(f"offline import counts differ: {counts!r}")
        return counts


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def _write_sources(
    directory: Path, documents: Mapping[str, Mapping[str, Any]]
) -> None:
    for name in SOURCE_FILENAMES:
        path = directory / name
        path.write_bytes(_canonical(documents[name]))
        path.chmod(0o600)


def _validate_sources(paths: Mapping[str, Path]) -> list[dict[str, Any]]:
    expected = expected_source_documents()
    if set(paths) != set(SOURCE_FILENAMES):
        raise RuntimeError("staged source inventory differs")
    for name in SOURCE_FILENAMES:
        path = paths[name]
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"missing or unsafe staged source: {name}")
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise RuntimeError(f"staged source mode differs: {name}")
        if path.read_bytes() != _canonical(expected[name]):
            raise RuntimeError(f"staged source differs: {name}")
    first = _offline_import(paths, "2026-07-22T05:00:00Z")
    second = _offline_import(paths, "2026-07-22T05:00:00Z")
    if first != second:
        raise RuntimeError("offline replay differs")
    return _source_records(expected)


def _write_artifact(
    directory: Path,
    recorded_at: str,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    payloads = _artifact_documents(recorded_at, documents)
    for name in CONTENT_FILES:
        path = directory / name
        path.write_bytes(payloads[name])
        path.chmod(0o600)
    rows = [
        {
            "path": name,
            "bytes": (directory / name).stat().st_size,
            "sha256": _sha256(directory / name),
        }
        for name in CONTENT_FILES
    ]
    manifest = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-prepublication-manifest-v1",
        "recorded_at": recorded_at,
        "files": rows,
        "tree_sha256": _sha256_bytes(_canonical(rows)),
        "closed_file_set": sorted(CLOSED_FILES),
        "candidate_assessments": 12,
        "curated_source_candidates": 2,
        "review_only_candidates": 10,
        "raw_capture_redistributed": False,
        "published": False,
        "publisher_function_present": False,
        "operator_completeness_claimed": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
    }
    manifest_path = directory / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    manifest_path.chmod(0o600)
    sidecar = directory / "manifest.sha256"
    sidecar.write_text(f"{_sha256(manifest_path)}  manifest.json\n", encoding="utf-8")
    sidecar.chmod(0o600)


def _assert_no_publication() -> None:
    final_paths = [PROSPECTIVE_ARTIFACT]
    final_paths.extend(SOURCES_ROOT / name for name in SOURCE_FILENAMES)
    collisions = [
        str(path)
        for path in final_paths
        if path.exists() or path.is_symlink()
    ]
    if collisions:
        raise RuntimeError(f"prospective final-path collision: {collisions!r}")


def validate_candidate(artifact_stage: Path, source_stage: Path) -> dict[str, Any]:
    _assert_no_publication()
    _validate_capture_directory()
    _v95_witness()
    _current_source_collision_witness()
    for directory in (artifact_stage, source_stage):
        if directory.is_symlink() or not directory.is_dir():
            raise RuntimeError("candidate stage is missing or unsafe")
        if stat.S_IMODE(directory.stat().st_mode) != 0o700:
            raise RuntimeError("candidate stage directory mode differs")
    entries = {path.name: path for path in artifact_stage.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise RuntimeError("candidate artifact closed file set differs")
    if any(path.is_symlink() or not path.is_file() for path in entries.values()):
        raise RuntimeError("candidate artifact contains an unsafe member")
    if any(stat.S_IMODE(path.stat().st_mode) != 0o600 for path in entries.values()):
        raise RuntimeError("candidate artifact member mode differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if (
        manifest.get("artifact_id") != ARTIFACT_ID
        or manifest.get("published") is not False
        or manifest.get("publisher_function_present") is not False
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
    ):
        raise RuntimeError("candidate manifest contract differs")
    rows = manifest.get("files")
    if not isinstance(rows, list) or [row.get("path") for row in rows] != list(
        CONTENT_FILES
    ):
        raise RuntimeError("candidate manifest inventory differs")
    for row in rows:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (
            row["bytes"],
            row["sha256"],
        ):
            raise RuntimeError(f"candidate manifest pin differs: {row['path']}")
    if manifest["tree_sha256"] != _sha256_bytes(_canonical(rows)):
        raise RuntimeError("candidate manifest tree differs")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise RuntimeError("candidate manifest sidecar differs")
    documents = expected_source_documents()
    expected_payloads = _artifact_documents(manifest["recorded_at"], documents)
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected_payloads[name]:
            raise RuntimeError(f"candidate artifact content differs: {name}")
    records = _validate_sources(_source_paths(source_stage))
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != records:
        raise RuntimeError("candidate source pins differ")
    assessment = json.loads(
        entries["candidate-assessment.json"].read_text(encoding="utf-8")
    )
    accepted = [
        row
        for row in assessment["candidates"]
        if row["decision"] == "governed_prepublication_current_physical_build"
    ]
    rejected = [row for row in assessment["candidates"] if row not in accepted]
    if len(accepted) != 2 or len(rejected) != 10:
        raise RuntimeError("candidate disposition counts differ")
    if any(row.get("stable_key_created") for row in rejected):
        raise RuntimeError("review-only stable-key boundary differs")
    return manifest


@dataclass(frozen=True)
class PreparedCandidate:
    source_stage: Path
    artifact_stage: Path
    recorded_at: str


def prepare_candidate(
    *,
    recorded_at: str | None = None,
    source_parent: Path = SOURCES_ROOT,
    artifact_parent: Path = ARTIFACT_ROOT,
) -> PreparedCandidate:
    """Create validated private stages; intentionally never promote them."""

    _assert_no_publication()
    _validate_capture_directory()
    _v95_witness()
    _current_source_collision_witness()
    documents = expected_source_documents()
    instant = recorded_at or datetime.now(UTC).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")
    source_stage = Path(
        tempfile.mkdtemp(prefix=".ctrls-ntt-adani-sources.", dir=source_parent)
    )
    artifact_stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=artifact_parent)
    )
    source_stage.chmod(0o700)
    artifact_stage.chmod(0o700)
    try:
        _write_sources(source_stage, documents)
        _write_artifact(artifact_stage, instant, documents)
        validate_candidate(artifact_stage, source_stage)
        return PreparedCandidate(source_stage, artifact_stage, instant)
    except BaseException:
        if source_stage.exists():
            shutil.rmtree(source_stage)
        if artifact_stage.exists():
            shutil.rmtree(artifact_stage)
        raise


def candidate_result(prepared: PreparedCandidate) -> dict[str, Any]:
    manifest = validate_candidate(prepared.artifact_stage, prepared.source_stage)
    return {
        "status": "PREPUBLICATION_CANDIDATE_BUILT_NOT_PUBLISHED",
        "recorded_at": prepared.recorded_at,
        "artifact_stage": str(prepared.artifact_stage),
        "artifact_manifest_sha256": _sha256(
            prepared.artifact_stage / "manifest.json"
        ),
        "artifact_tree_sha256": tree_digest(prepared.artifact_stage),
        "source_stage": str(prepared.source_stage),
        "source_pins": [
            {
                "path": str(prepared.source_stage / name),
                "bytes": (prepared.source_stage / name).stat().st_size,
                "sha256": _sha256(prepared.source_stage / name),
            }
            for name in SOURCE_FILENAMES
        ],
        "candidate_assessments": manifest["candidate_assessments"],
        "curated_source_candidates": manifest["curated_source_candidates"],
        "review_only_candidates": manifest["review_only_candidates"],
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "v95_definition_sha256": V95_DEFINITION_PIN[1],
        "v95_entities_sha256": V95_ENTITIES_PIN[1],
        "v95_evidence_sha256": V95_EVIDENCE_PIN[1],
        "v95_manifest_sha256": V95_MANIFEST_PIN[1],
        "published": False,
        "prospective_final_artifact_exists": PROSPECTIVE_ARTIFACT.exists(),
        "prospective_final_source_exists": any(
            (SOURCES_ROOT / name).exists() for name in SOURCE_FILENAMES
        ),
    }


def main() -> int:
    prepared = prepare_candidate()
    print(json.dumps(candidate_result(prepared), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
