"""Build, but never publish, the bounded CEE NXDATA-3 gap candidate.

NXDATA-3 / BUH3 is represented as an evidence successor to the existing
identity-and-design-only source record.  A dated first-party NXDATA post
supplies the physical-status observation.  Marketing-page opening dates and
publisher imagery do not supply lifecycle truth.  The three technical values
are retained only as design metrics, never as current demand or consumption.

The accompanying audit also closes the anonymous PORR February 2025 lead:
PORR's WAW 11.1 page identifies an already-completed Vantage project, while
DATA4's official April 2026 material identifies its second Jawczyce facility as
operational.  No source bridges PORR's anonymous eighth project to either one,
so neither creates a current-build record here.
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

from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"

ARTIFACT_ID = "official-cee-nxdata-gap-prepublication-2026-07-22-v1"
PROSPECTIVE_ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
SOURCE_FILENAME = (
    "curated-official-2026-07-22-nxdata3-bucharest-"
    "current-build-successor.json"
)
PROSPECTIVE_SOURCE = SOURCES_ROOT / SOURCE_FILENAME

PREDECESSOR_FILENAME = (
    "curated-official-2026-07-21-nxdata3-bucharest-source-scoped.json"
)
PREDECESSOR = SOURCES_ROOT / PREDECESSOR_FILENAME
PREDECESSOR_PIN = (
    5_945,
    "5f99c454a53c26cb9c0f01cade1e90baabe2c7b86ddf1dcf7002360fad33b1c4",
)

V95_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-22-v95.json"
V95_ENTITIES = ROOT / "releases/2026-07-22-open-seed-v95/entities.csv"
V95_RELEASE = ROOT / "releases/2026-07-22-open-seed-v95"
V95_DEFINITION_PIN = (
    117_088,
    "e28cc9ad10229cbf718314f1bd1a4306e02faee1166dcbfbf93c01a1c82e8e15",
)
V95_ENTITIES_PIN = (
    1_058_933,
    "038bfa4ef15e4e6494ac91fa835671105d45662c0acd6b6f5c3a5e750ad3e09d",
)
V95_RELEASE_TREE_SHA256 = (
    "752593650007f602f2bd13f2bd0c3ac8702cdd74c4b6103ec2bdaa348c6ef17a"
)

PREDECESSOR_ARTIFACT = (
    ARTIFACT_ROOT / "global-official-builds-next-tranche-2026-07-21-v1"
)
PREDECESSOR_ARTIFACT_MANIFEST_PIN = (
    1_791,
    "5cdf7bba0090ee2a67af2699257a6557ee1be16dcafb9d8560993127b714cce7",
)
PREDECESSOR_ARTIFACT_TREE_SHA256 = (
    "2aaa975a538d088c81e1f3fe313042b2b58b0a3dfc815dec526c72a90cd3cacc"
)

CEE_GAP_ARTIFACT = ARTIFACT_ROOT / "global-official-builds-cee-gap-2026-07-21-v1"
CEE_GAP_MANIFEST_PIN = (
    1_744,
    "13ffdc16826e4fc1caf75b3b9c97fe8f2176193247512992254bd8ae114bc4f9",
)
CEE_GAP_ASSESSMENT_PIN = (
    10_003,
    "0a5890b11b5b9b59bd353a1cbe9390941f36079cafa65f72351e700421e0dafd",
)
CEE_GAP_TREE_SHA256 = (
    "e23ecade126ad455d9b2819b614c7b45574f099c419f73cf3457adbb7091e91e"
)

CAPTURE_ORIGIN = Path("/private/tmp/dc-cee-nxdata-gap-20260722.sMJBya")
CAPTURE_FILE_COUNT = 26
CAPTURE_TOTAL_BYTES = 10_155_285
CAPTURE_TREE_SHA256 = (
    "35e83df4b1479170ee231e013d8a4e35da481e08a6d4689521f592a892fd4267"
)

CAPTURE_FILE_PINS: Mapping[str, tuple[int, str]] = {
    "data4_opening_video_linkedin.body": (
        109_321,
        "dec84bdfb10d7c451be841ab0f5977872de2a42a63d157a3634643fdd42f8605",
    ),
    "data4_opening_video_linkedin.headers": (
        5_348,
        "4d6cd2445b3e24de10f85d2fd116ff1b6191e0a9ec379152023eef5479e927b5",
    ),
    "data4_operational_blog.body": (
        20_214,
        "38367150c2a778e73488e0553e6d166b683971a87f6bbc506f5b97d3bd285668",
    ),
    "data4_operational_blog.headers": (
        2_892,
        "1f2d7c0c22ecfc6b5f541eba00e72ba7471c4ce22aab9b239660ffd1f3bef4e7",
    ),
    "data4_operational_linkedin.body": (
        184_106,
        "d735a31236bcdae4d15816879527942b449895e815d648cd483cca461409bd51",
    ),
    "data4_operational_linkedin.headers": (
        5_348,
        "6da8270cb9f5945fa4921341b272cd6ae35a210190b1adcc18225436dfbe2eae",
    ),
    "data4_operational_page.body": (
        129_214,
        "2ad05703113631a7e3f6d9d549bc838b2305129150357d8fb9024082763fe9df",
    ),
    "data4_operational_page.headers": (
        571,
        "af6844284cee32bc1ddc099a9fe211f2e0dc294fa344514a551ca54adfc6a78f",
    ),
    "data4_operational_pdf.body": (
        427_020,
        "80ff5dcba4f37e7536d3e8b05747dbb40535d54e37dea49236408f5ae53935aa",
    ),
    "data4_operational_pdf.headers": (
        319,
        "c26cf21adb81630f26913beb16dd43d27292195c68ae9a9e37b3ace92d185373",
    ),
    "nxdata3_brochure.body": (
        7_953_295,
        "42aa4b2aa2951763d412d15a675deca45c0fd11f72ceb005e084d311d4be0b9a",
    ),
    "nxdata3_brochure.headers": (
        260,
        "866ca5ec3cc952eb68d2754530ae978c22039fb829cec5275625e83e96e9f41d",
    ),
    "nxdata3_home.body": (
        158_707,
        "26c2e1cc1fb21ad42575e0cf022cff148da4a13ef396abc216223385ed6827fd",
    ),
    "nxdata3_home.headers": (
        575,
        "9c6046096bfa74622a446132693b60976f0262bf82070b68499fdfef9488e133",
    ),
    "nxdata_linkedin_company.body": (
        315_410,
        "7b25ab236f35734802d368378cde354f96cc67b992ce42c58cbf4db1f1c27afc",
    ),
    "nxdata_linkedin_company.headers": (
        5_303,
        "3dd4951672ac9322442fcb15458422c0f03348cb8099f6324f8ac7f4ee96e0cd",
    ),
    "nxdata_linkedin_construction.body": (
        381_712,
        "223500aa0494aed1c10a6518b1946feb042244390eaf720e0069a12c9c4422f2",
    ),
    "nxdata_linkedin_construction.headers": (
        5_348,
        "91596527efdf301b091f7164ecd495b9eabe20cf62b15cd524d000db69e2b277",
    ),
    "nxdata_linkedin_construction_image.body": (
        97_345,
        "ea996486ca2b3dbed0a21a9149da4f1c94926e2b61c7685841ca242ee1d20179",
    ),
    "nxdata_linkedin_construction_image.headers": (
        748,
        "fab75d7104d19baf5ca5d70b4fe14b12d00fce882dba56295c3dc1ccc117ad5a",
    ),
    "porr_eighth.body": (
        75_514,
        "739bf874641bd8684da7bef5021c3603881a2f9d329c571bf16e37df6c852f16",
    ),
    "porr_eighth.headers": (
        966,
        "c8fc27de6bbf7c9d5d13de1ccaa38b72d188ce298cb5a40c9d7d095f8957dc7d",
    ),
    "porr_eighth_pdf.body": (
        241_896,
        "2d48092c4ba1758de725d5b76150ec814a09923f4685239e78f3c4cb44d78b57",
    ),
    "porr_eighth_pdf.headers": (
        849,
        "2d5ca4f8277fac47577e7e602389040804c0d8267a169162c949b0cf45a603c9",
    ),
    "porr_waw111.body": (
        32_038,
        "1b7c6fdecc06bbdd94fb5f52a2c793cdb892867da6d8e7f33714d96c7f1c5034",
    ),
    "porr_waw111.headers": (
        966,
        "83c462b6ecc2b0306154a781b886d2acb50c480149a53c3a549a7d3bdfacb1f3",
    ),
}


@dataclass(frozen=True)
class Capture:
    capture_id: str
    stem: str
    requested_url: str
    publisher: str
    retrieved_at: str
    content_type: str
    disposition: str
    published_at: str | None = None
    effective_url: str | None = None


CAPTURES = (
    Capture(
        "nxdata3_home",
        "nxdata3_home",
        "https://nxdata3.com/",
        "NXDATA SRL",
        "2026-07-22T04:32:17Z",
        "text/html; charset=UTF-8",
        "normalized_identity_address_design_metrics_and_colocation",
        "2025-06-26T11:02:06Z",
    ),
    Capture(
        "nxdata3_brochure",
        "nxdata3_brochure",
        "https://nxdata3.com/wp-content/uploads/2025/07/"
        "NXDATA-3-DATA-CENTER-BUCHAREST-TECHNICAL-BROCHURE.pdf",
        "NXDATA SRL",
        "2026-07-22T04:32:19Z",
        "application/pdf",
        "normalized_design_metrics_and_colocation",
    ),
    Capture(
        "nxdata_linkedin_construction",
        "nxdata_linkedin_construction",
        "https://www.linkedin.com/posts/nxdata_nxdata-nxdata3-datacenter-"
        "activity-7467582788171616256-fwVo",
        "NXDATA",
        "2026-07-22T04:32:14Z",
        "text/html; charset=utf-8",
        "normalized_dated_first_party_physical_status",
        "2026-06-02T14:27:57.661Z",
    ),
    Capture(
        "nxdata_linkedin_company",
        "nxdata_linkedin_company",
        "https://www.linkedin.com/company/nxdata",
        "NXDATA",
        "2026-07-22T04:32:15Z",
        "text/html; charset=utf-8",
        "first_party_current_profile_corroboration_only",
    ),
    Capture(
        "nxdata_linkedin_construction_image",
        "nxdata_linkedin_construction_image",
        "https://media.licdn.com/dms/image/v2/D4D22AQFwcSPVT7N-4w/"
        "feedshare-shrink_800/B4DZ6Iu.LfIQAg-/0/1780410476532",
        "NXDATA via LinkedIn",
        "2026-07-22T04:32:31Z",
        "image/jpeg",
        "corroborative_visual_description_only_no_normalized_claim",
    ),
    Capture(
        "porr_eighth",
        "porr_eighth",
        "https://www.porr-group.com/en/press/press-releases/detail/"
        "rise-of-ai-is-driving-data-centre-construction",
        "PORR AG",
        "2026-07-22T04:32:16Z",
        "text/html; charset=utf-8",
        "audit_anonymous_current_build_claim_only",
        "2025-02-10T08:00:00+01:00",
    ),
    Capture(
        "porr_eighth_pdf",
        "porr_eighth_pdf",
        "https://www.porr-group.com/fileadmin/s_porr-group/Presse/2025/"
        "250210_Datencenter_EN.pdf",
        "PORR AG",
        "2026-07-22T04:33:49Z",
        "application/pdf",
        "same_publisher_pdf_duplicate_audit",
        "2025-02-10",
    ),
    Capture(
        "porr_waw111",
        "porr_waw111",
        "https://www.porr-group.com/en/projects/detail/waw-111-data-center",
        "PORR AG",
        "2026-07-22T04:32:16Z",
        "text/html; charset=utf-8",
        "audit_completed_vantage_project_exclusion",
    ),
    Capture(
        "data4_operational_linkedin",
        "data4_operational_linkedin",
        "https://www.linkedin.com/posts/data4-group_warsaw-ai-"
        "activity-7448033338176532480-vzAO",
        "Data4",
        "2026-07-22T04:32:17Z",
        "text/html; charset=utf-8",
        "audit_operational_closure",
        "2026-04-09T15:45:25.563Z",
    ),
    Capture(
        "data4_opening_video_linkedin",
        "data4_opening_video_linkedin",
        "https://www.linkedin.com/posts/data4-group_data4-opens-a-second-"
        "data-center-in-poland-activity-7455192176118046720--JcS",
        "Data4",
        "2026-07-22T04:32:17Z",
        "text/html; charset=utf-8",
        "audit_operational_closure_corroboration",
        "2026-04-29T09:52:05.534Z",
    ),
    Capture(
        "data4_operational_page",
        "data4_operational_page",
        "https://www.data4group.com/en/news-data4/"
        "data4-expands-in-poland-with-second-data-center-near-warsaw/",
        "Data4",
        "2026-07-22T04:33:47Z",
        "text/html; charset=UTF-8",
        "audit_operational_closure",
        "2026-04-09",
    ),
    Capture(
        "data4_operational_pdf",
        "data4_operational_pdf",
        "https://www.data4group.com/wp-content/uploads/2026/04/"
        "Data4-launches-second-data-center-at-its-campus-near-Warsaw.pdf",
        "Data4",
        "2026-07-22T04:33:48Z",
        "application/pdf",
        "audit_operational_closure",
        "2026-04-09",
    ),
    Capture(
        "data4_operational_blog_challenge",
        "data4_operational_blog",
        "https://lnkd.in/eWSf3WwX",
        "LinkedIn short-link service",
        "2026-07-22T04:33:21Z",
        "text/html; charset=utf-8",
        "recaptcha_challenge_not_source_not_used",
        effective_url="https://lnkd.in/eWSf3WwX",
    ),
)
CAPTURE_BY_ID = {capture.capture_id: capture for capture in CAPTURES}

CAMPUS_KEY = "curated:nxdata3-bucharest-ring-road-campus"
PROJECT_KEY = f"{CAMPUS_KEY}:nxdata3-buh3"
HOME_EVIDENCE_KEY = "nxdata3-project-page-design-captured-2026-07-22"
BROCHURE_EVIDENCE_KEY = "nxdata3-technical-brochure-captured-2026-07-22"
STATUS_EVIDENCE_KEY = (
    "nxdata3-official-foundation-progress-2026-06-02-captured-2026-07-22"
)
PROFILE_EVIDENCE_KEY = "nxdata-current-company-profile-captured-2026-07-22"

CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


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
    headers = CAPTURE_FILE_PINS[f"{capture.stem}.headers"]
    return {
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture.capture_id,
        "capture_method": (
            "credential_free_curl_fail_location_compressed_desktop_user_agent"
        ),
        "requested_url": capture.requested_url,
        "effective_url": capture.effective_url or capture.requested_url,
        "request_credentials_supplied": False,
        "http_status": 200,
        "content_type": capture.content_type,
        "content_hash_scope": (
            f"SHA-256 of the exact {body[0]}-byte captured response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_headers_bytes": headers[0],
        "capture_headers_sha256": headers[1],
        "raw_capture_redistributed": False,
        "rights_scope": (
            "Compact factual extraction from all-rights-reserved official bytes; "
            "raw bodies, headers, scripts, PDFs, and publisher media are not "
            "redistributed."
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
        "source_url": capture.effective_url or capture.requested_url,
        "publisher": capture.publisher,
        "source_family": source_family,
        "published_at": capture.published_at,
        "retrieved_at": capture.retrieved_at,
        "license": "all-rights-reserved",
        "attribution": capture.publisher,
        "excerpt": excerpt,
        "content_hash": CAPTURE_FILE_PINS[f"{capture.stem}.body"][1],
        "metadata": {**_capture_metadata(capture_id), **metadata},
    }


def expected_source_document() -> dict[str, Any]:
    home = _evidence(
        key=HOME_EVIDENCE_KEY,
        capture_id="nxdata3_home",
        title="NXDATA-3 Bucharest Data Center",
        excerpt=(
            "NXDATA identifies NXDATA-3 / NX-3 / BUH3 at 38 Bucharest Ring "
            "Road and describes carrier-neutral colocation and facility design."
        ),
        source_family="nxdata3_project_pages",
        metadata={
            "page_date_modified": "2026-05-05T08:54:21Z",
            "aliases_as_reported": ["NXDATA-3", "NX-3", "BUH3"],
            "address_as_reported": (
                "38 Bucharest Ring Road, Tunari, Ilfov, Romania"
            ),
            "design_metrics_as_reported": {
                "total_electrical_capacity_mw": 5,
                "customer_it_capacity_mw": 3,
                "design_annual_pue": 1.3,
            },
            "opening_schedule_only": "Estimated site opening Q4 2026.",
            "opening_schedule_lifecycle_claim_created": False,
            "marketing_page_physical_status_claim_created": False,
            "energy_guardrail": (
                "No value is current draw, current consumption, annual energy, "
                "grid connection, generation, or operating performance."
            ),
            "spatial_guardrail": (
                "No map, geocoder, coordinate, parcel, imagery, or analyst "
                "geolocation contributes."
            ),
        },
    )
    brochure = _evidence(
        key=BROCHURE_EVIDENCE_KEY,
        capture_id="nxdata3_brochure",
        title="NXDATA-3 Data Center Bucharest Technical Brochure",
        excerpt=(
            "The nine-page NXDATA brochure reports 5 MW total electrical design, "
            "3 MW customer IT design, design PUE about 1.3, and carrier-neutral "
            "colocation."
        ),
        source_family="nxdata3_technical_brochures",
        metadata={
            "pdf_pages": 9,
            "pdf_creation_at": "2025-07-11T12:44:28Z",
            "pdf_modified_at": "2025-07-11T13:21:49Z",
            "http_last_modified_at": "2025-07-11T13:23:32Z",
            "design_metric_normalization": {
                "gross_facility_mw": 5,
                "critical_it_mw": 3,
                "pue": 1.3,
                "stage_for_all": "design",
            },
            "future_facility_guardrail": (
                "The brochure describes a future facility and an estimated 2026 "
                "opening. The word installed does not convert 5 MW into operating "
                "load while the facility remains under construction."
            ),
            "hall_guardrail": (
                "Four up-to-1 MW hall ceilings are allocation ceilings inside the "
                "reported 3 MW customer-IT design and are not summed to 4 MW."
            ),
            "rendering_guardrail": (
                "Brochure maps and 3D renderings establish no coordinate, geometry, "
                "lifecycle, or as-built condition."
            ),
        },
    )
    status = _evidence(
        key=STATUS_EVIDENCE_KEY,
        capture_id="nxdata_linkedin_construction",
        title="From vision to reality, NXDATA-3 is taking shape",
        excerpt=(
            "NXDATA says NXDATA-3 is taking shape, that the design is steadily "
            "becoming part of the foundation, and that it is building that "
            "foundation today."
        ),
        source_family="nxdata_official_linkedin_company_posts",
        metadata={
            "schema_org_date_published": "2026-06-02T14:27:57.661Z",
            "physical_status_as_reported": [
                "NXDATA-3 is taking shape.",
                "The design is steadily becoming part of the foundation.",
                "NXDATA-3 is helping build that foundation today.",
            ],
            "normalized_lifecycle": "under_construction",
            "normalized_lifecycle_method": (
                "authoritative_physical_status_update"
            ),
            "opening_schedule_used_for_status": False,
            "publisher_photo": {
                "capture_id": "nxdata_linkedin_construction_image",
                "bytes": CAPTURE_FILE_PINS[
                    "nxdata_linkedin_construction_image.body"
                ][0],
                "sha256": CAPTURE_FILE_PINS[
                    "nxdata_linkedin_construction_image.body"
                ][1],
                "dimensions_px": [800, 449],
                "manual_visual_description": (
                    "The image visibly depicts a large rectangular works area with "
                    "concrete foundation or slab sections, formwork or rebar, "
                    "workers, excavators, and a crane."
                ),
                "description_only": True,
                "identity_claim_created": False,
                "location_claim_created": False,
                "lifecycle_claim_created": False,
                "capacity_claim_created": False,
                "computer_vision_is_construction_truth": False,
            },
            "workload_guardrail": (
                "Demand language mentioning AI creates no installed workload, "
                "tenant, customer, training, inference, or utilization row."
            ),
        },
    )
    profile = _evidence(
        key=PROFILE_EVIDENCE_KEY,
        capture_id="nxdata_linkedin_company",
        title="NXDATA company profile",
        excerpt=(
            "NXDATA's current public company profile says it has begun construction "
            "of its third facility, NXDATA-3."
        ),
        source_family="nxdata_official_linkedin_company_profile",
        metadata={
            "current_profile_wording": (
                "has begun the construction of its third facility, NXDATA-3"
            ),
            "corroborates_dated_post": True,
            "separate_lifecycle_row_created": False,
            "profile_edit_date_inferred": False,
        },
    )
    entity_common = {
        "country": "Romania",
        "address": "38 Bucharest Ring Road, Tunari, Ilfov, Romania",
        "roles": {"developer": ["NXDATA SRL"], "operator": ["NXDATA SRL"]},
        "coordinates": None,
        "geometry": None,
        "evidence_key": HOME_EVIDENCE_KEY,
        "as_of_date": "2026-05-05",
        "method": "authoritative_locality",
        "confidence": 0.99,
    }
    capacities = [
        {
            "entity": "project",
            "metric": "gross_facility_mw",
            "stage": "design",
            "unit": "MW",
            "low": 5,
            "base": 5,
            "high": 5,
            "method": "reported",
            "confidence": 0.99,
            "evidence_key": BROCHURE_EVIDENCE_KEY,
            "as_of_date": "2025-07-11",
            "target_date": None,
            "notes": (
                "Total electrical or gross-facility design only; not current draw, "
                "consumption, grid connection, generation, or operating capacity."
            ),
        },
        {
            "entity": "project",
            "metric": "critical_it_mw",
            "stage": "design",
            "unit": "MW",
            "low": 3,
            "base": 3,
            "high": 3,
            "method": "reported",
            "confidence": 0.99,
            "evidence_key": BROCHURE_EVIDENCE_KEY,
            "as_of_date": "2025-07-11",
            "target_date": None,
            "notes": (
                "Customer IT&C design only; not installed load, current demand, "
                "consumption, or a sum of per-hall ceilings."
            ),
        },
        {
            "entity": "project",
            "metric": "pue",
            "stage": "design",
            "unit": "ratio",
            "low": 1.3,
            "base": 1.3,
            "high": 1.3,
            "method": "reported",
            "confidence": 0.98,
            "evidence_key": BROCHURE_EVIDENCE_KEY,
            "as_of_date": "2025-07-11",
            "target_date": None,
            "notes": (
                "Approximate design PUE only; not measured, accepted, commissioned, "
                "or operating performance."
            ),
        },
    ]
    return {
        "schema_version": "1.1",
        "evidence": [home, brochure, status, profile],
        "campus": {
            "stable_key": CAMPUS_KEY,
            "name": "NXDATA-3 Bucharest Ring Road Campus",
            **entity_common,
        },
        "project": {
            "stable_key": PROJECT_KEY,
            "name": "NXDATA-3 / NX-3 / BUH3",
            **entity_common,
        },
        "lifecycle": [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": STATUS_EVIDENCE_KEY,
                "as_of_date": "2026-06-02",
                "method": "authoritative_physical_status_update",
                "confidence": 0.99,
            }
        ],
        "operating_models": [
            {
                "entity": "project",
                "value": "colocation",
                "evidence_key": BROCHURE_EVIDENCE_KEY,
                "as_of_date": "2025-07-11",
                "method": "company_disclosure",
                "confidence": 0.99,
            }
        ],
        "workloads": [],
        "capacities": capacities,
    }


def _validate_capture_directory(directory: Path = CAPTURE_ORIGIN) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("private CEE capture directory is missing or unsafe")
    entries = {path.name: path for path in directory.iterdir()}
    if set(entries) != set(CAPTURE_FILE_PINS):
        raise RuntimeError("private CEE capture inventory differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(entries[name], pin)
        if stat.S_IMODE(entries[name].stat().st_mode) != 0o444:
            raise RuntimeError(f"private CEE capture is not frozen: {name}")
    if sum(pin[0] for pin in CAPTURE_FILE_PINS.values()) != CAPTURE_TOTAL_BYTES:
        raise RuntimeError("private CEE capture byte total differs")
    if tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise RuntimeError("private CEE capture tree differs")


def _collision_witness() -> dict[str, Any]:
    _pin(PREDECESSOR, PREDECESSOR_PIN)
    _pin(V95_DEFINITION, V95_DEFINITION_PIN)
    _pin(V95_ENTITIES, V95_ENTITIES_PIN)
    _pin(
        PREDECESSOR_ARTIFACT / "manifest.json",
        PREDECESSOR_ARTIFACT_MANIFEST_PIN,
    )
    _pin(CEE_GAP_ARTIFACT / "manifest.json", CEE_GAP_MANIFEST_PIN)
    _pin(
        CEE_GAP_ARTIFACT / "candidate-assessment.json",
        CEE_GAP_ASSESSMENT_PIN,
    )
    if tree_digest(V95_RELEASE) != V95_RELEASE_TREE_SHA256:
        raise RuntimeError("v95 release tree differs")
    if tree_digest(PREDECESSOR_ARTIFACT) != PREDECESSOR_ARTIFACT_TREE_SHA256:
        raise RuntimeError("NXDATA predecessor artifact tree differs")
    if tree_digest(CEE_GAP_ARTIFACT) != CEE_GAP_TREE_SHA256:
        raise RuntimeError("CEE gap artifact tree differs")

    predecessor = json.loads(PREDECESSOR.read_text(encoding="utf-8"))
    if (
        predecessor.get("schema_version") != "1.1"
        or predecessor.get("campus", {}).get("stable_key") != CAMPUS_KEY
        or predecessor.get("project", {}).get("stable_key") != PROJECT_KEY
        or predecessor.get("lifecycle") != []
    ):
        raise RuntimeError("NXDATA predecessor boundary differs")

    definition = json.loads(V95_DEFINITION.read_text(encoding="utf-8"))
    selected = definition.get("curated_inputs")
    if not isinstance(selected, list) or len(selected) != 507:
        raise RuntimeError("v95 curated input inventory differs")
    selected_paths = [row.get("path") for row in selected]
    predecessor_path = f"sources/{PREDECESSOR_FILENAME}"
    successor_path = f"sources/{SOURCE_FILENAME}"
    if predecessor_path in selected_paths or successor_path in selected_paths:
        raise RuntimeError("NXDATA unexpectedly selected by v95")

    with V95_ENTITIES.open(encoding="utf-8", newline="") as stream:
        entity_rows = list(csv.DictReader(stream))
    if len(entity_rows) != 1_029:
        raise RuntimeError("v95 entity count differs")
    v95_keys = {row["stable_key"] for row in entity_rows}
    if {CAMPUS_KEY, PROJECT_KEY} & v95_keys:
        raise RuntimeError("NXDATA keys unexpectedly present in v95 release")

    predecessor_snapshot = json.loads(
        (PREDECESSOR_ARTIFACT / "source-snapshot.json").read_text(
            encoding="utf-8"
        )
    )
    nxdata_rows = [
        row
        for row in predecessor_snapshot.get("source_records", [])
        if row.get("path") == predecessor_path
    ]
    if len(nxdata_rows) != 1 or nxdata_rows[0].get("seeded") is not False:
        raise RuntimeError("NXDATA predecessor artifact record differs")

    cee_assessment = json.loads(
        (CEE_GAP_ARTIFACT / "candidate-assessment.json").read_text(
            encoding="utf-8"
        )
    )
    data4_rows = [
        row
        for row in cee_assessment.get("candidates", [])
        if row.get("candidate_id") == "data4-jawczyce"
    ]
    if len(data4_rows) != 1 or data4_rows[0].get("decision") != (
        "review_only_operational"
    ):
        raise RuntimeError("prior DATA4 Jawczyce disposition differs")

    return {
        "v95_definition": {
            "path": "sources/open-seed-2026-07-22-v95.json",
            "bytes": V95_DEFINITION_PIN[0],
            "sha256": V95_DEFINITION_PIN[1],
            "curated_input_count": len(selected),
        },
        "v95_release": {
            "path": "releases/2026-07-22-open-seed-v95",
            "tree_sha256": V95_RELEASE_TREE_SHA256,
            "entity_count": len(entity_rows),
        },
        "predecessor": {
            "path": predecessor_path,
            "bytes": PREDECESSOR_PIN[0],
            "sha256": PREDECESSOR_PIN[1],
            "artifact_tree_sha256": PREDECESSOR_ARTIFACT_TREE_SHA256,
            "same_stable_keys_reused": [CAMPUS_KEY, PROJECT_KEY],
            "selected_by_v95": False,
            "seeded_by_predecessor_artifact": False,
        },
        "successor": {
            "prospective_path": successor_path,
            "new_entity_created": False,
            "new_phase_created": False,
            "selected_by_v95": False,
            "v95_release_stable_key_collisions": 0,
        },
        "prior_cee_gap_artifact": {
            "tree_sha256": CEE_GAP_TREE_SHA256,
            "data4_jawczyce_decision": "review_only_operational",
        },
    }


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-cee-current-build-gap-assessment-v1",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "candidate_count": 4,
        "governed_source_candidate_count": 1,
        "review_only_count": 3,
        "regional_completeness_claimed": False,
        "candidates": [
            {
                "candidate_id": "nxdata3-buh3",
                "country": "Romania",
                "decision": (
                    "governed_prepublication_existing_identity_current_build_"
                    "successor"
                ),
                "source_paths": [f"prospective-sources/{SOURCE_FILENAME}"],
                "campus_stable_key": CAMPUS_KEY,
                "project_stable_key": PROJECT_KEY,
                "lifecycle": "under_construction",
                "lifecycle_as_of": "2026-06-02",
                "lifecycle_evidence": STATUS_EVIDENCE_KEY,
                "opening_q4_2026_used_for_status": False,
                "official_photo_used_for_status": False,
                "capacity_metrics": [
                    ["gross_facility_mw", "design", 5, "MW"],
                    ["critical_it_mw", "design", 3, "MW"],
                    ["pue", "design", 1.3, "ratio"],
                ],
                "current_consumption_claim_created": False,
                "annual_energy_claim_created": False,
                "coordinate_claim_created": False,
                "geometry_claim_created": False,
                "v95_entity_collision": False,
                "predecessor_source_collision_resolved_as_successor": True,
                "published": False,
                "seeded": False,
                "open_seed_integration": False,
            },
            {
                "candidate_id": "porr-anonymous-eighth-february-2025",
                "country": "Poland or Germany",
                "decision": "review_only_anonymous_identity_unresolved",
                "source_paths": [],
                "source_record_created": False,
                "stable_key_created": False,
                "lifecycle_claim_created": False,
                "basis": (
                    "PORR says only that an eighth data centre was under "
                    "construction. It gives no operator, site, project name, or "
                    "identity bridge."
                ),
                "identity_with_waw_11_1_asserted": False,
                "identity_with_data4_jawczyce_asserted": False,
                "current_construction_seed_created": False,
            },
            {
                "candidate_id": "porr-waw-11-1",
                "country": "Poland",
                "decision": "review_only_completed_2022_not_current",
                "source_paths": [],
                "source_record_created": False,
                "stable_key_created": False,
                "lifecycle_claim_created": False,
                "principal_as_reported": "Vantage",
                "construction_runtime_as_reported": "2021-03 to 2022-04",
                "basis": (
                    "PORR identifies WAW 11.1 as a Vantage project built from "
                    "March 2021 through April 2022. It cannot be PORR's anonymous "
                    "eighth project still under construction in February 2025."
                ),
                "same_asset_as_data4_jawczyce_asserted": False,
                "current_construction_seed_created": False,
            },
            {
                "candidate_id": "data4-jawczyce-second-data-center",
                "country": "Poland",
                "decision": "review_only_operational_2026_04_09",
                "source_paths": [],
                "source_record_created": False,
                "stable_key_created": False,
                "lifecycle_claim_created": False,
                "operator_as_reported": "Data4",
                "campus_as_reported": "Jawczyce / WAW01",
                "official_opening_date": "2026-04-09",
                "basis": (
                    "Data4's official page, press-release PDF, and public company "
                    "post say its second Jawczyce facility was inaugurated on "
                    "April 9, 2026. It is not a current-build seed."
                ),
                "identity_with_porr_anonymous_eighth_asserted": False,
                "same_asset_as_porr_waw_11_1_asserted": False,
                "current_construction_seed_created": False,
            },
        ],
    }


def _retrieval_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "capture_protocol": (
            "Credential-free curl GETs with redirects, content decoding, explicit "
            "connection and wall-clock timeouts, and a desktop user agent."
        ),
        "controlled_capture_count": len(CAPTURES),
        "successful_http_200_body_captures": len(CAPTURES),
        "normalized_nxdata_claim_capture_count": 4,
        "audit_disposition_capture_count": 7,
        "corroborative_media_capture_count": 1,
        "challenge_capture_count": 1,
        "request_credentials_supplied": False,
        "raw_capture_redistributed": False,
        "capture_directory": str(CAPTURE_ORIGIN),
        "capture_directory_retained_private": True,
        "capture_file_count": CAPTURE_FILE_COUNT,
        "capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "captures": [
            {
                "capture_id": capture.capture_id,
                "publisher": capture.publisher,
                "requested_url": capture.requested_url,
                "effective_url": capture.effective_url or capture.requested_url,
                "published_at": capture.published_at,
                "retrieved_at": capture.retrieved_at,
                "http_status": 200,
                "content_type": capture.content_type,
                "disposition": capture.disposition,
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


def _source_record(document: Mapping[str, Any]) -> dict[str, Any]:
    payload = _canonical(document)
    return {
        "path": f"prospective-sources/{SOURCE_FILENAME}",
        "bytes": len(payload),
        "sha256": _sha256_bytes(payload),
        "schema_version": "1.1",
        "country": "Romania",
        "campus_stable_key": CAMPUS_KEY,
        "project_stable_key": PROJECT_KEY,
        "evidence_records": len(document["evidence"]),
        "lifecycle_observations": len(document["lifecycle"]),
        "operating_model_observations": len(document["operating_models"]),
        "workload_observations": len(document["workloads"]),
        "capacity_estimates": len(document["capacities"]),
        "coordinates_present": 0,
        "geometry_present": 0,
        "disposition": "prepublication_existing_identity_current_build_successor",
        "published": False,
        "seeded": False,
    }


def _artifact_documents(
    recorded_at: str, document: Mapping[str, Any]
) -> dict[str, bytes]:
    witness = _collision_witness()
    assessment = _candidate_assessment(recorded_at)
    source_record = _source_record(document)
    readme = f"""# CEE NXDATA-3 current-build gap - prepublication only

This governed candidate was built at {recorded_at} and was not published. It reuses the exact NXDATA-3 / NX-3 / BUH3 campus and project stable keys from the existing identity-and-design-only source, while adding a dated June 2, 2026 first-party physical-progress observation. The official post text, not the Q4 2026 opening forecast or its image, supports `under_construction`.

Exactly three design metrics are retained: 5 MW `gross_facility_mw`, 3 MW `critical_it_mw`, and approximate 1.3 `pue`. None is current demand, consumption, annual energy, grid connection, generation, or measured performance. Carrier-neutral colocation is retained as the operating model. No workload, coordinate, geometry, map, geocoder, satellite, aerial, or computer-vision-derived fact is emitted. The downloaded official photo has only a non-claim visual description.

PORR's February 2025 statement leaves its eighth project anonymous. PORR separately identifies WAW 11.1 as a Vantage facility built between March 2021 and April 2022, so WAW 11.1 cannot be that February 2025 current build. Data4 identifies its distinct second Jawczyce / WAW01 facility as inaugurated on April 9, 2026. No source bridges the anonymous PORR project to Data4; even if later evidence did, the Data4 facility is now operational. All three leads remain review-only and create no source record.

The builder has no publication or promotion function. Candidate source and artifact bytes remain private mode-0600 files in mode-0700 hidden staging directories. No final source path, source-artifact path, open-seed successor, release, construction product, identity product, map, federation, or coverage artifact is created or changed.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "regional_completeness_claimed": False,
        "source_records": [source_record],
        "totals": {
            "candidate_assessments": 4,
            "source_records": 1,
            "governed_prepublication_candidates": 1,
            "review_only_candidates": 3,
            "distinct_campuses_in_source_records": 1,
            "projects": 1,
            "distinct_entity_snapshots": 2,
            "new_entities_against_v95": 0,
            "reused_predecessor_stable_keys": 2,
            "evidence_records": 4,
            "lifecycle_observations": 1,
            "operating_model_observations": 1,
            "workload_observations": 0,
            "capacity_estimates": 3,
            "design_capacity_estimates": 3,
            "coordinate_observations": 0,
            "geometry_observations": 0,
            "satellite_observations": 0,
            "computer_vision_normalized_claims": 0,
            "energy_consumption_observations": 0,
        },
        "v95_and_predecessor_collision_witness": witness,
        "integration": {
            "published": False,
            "final_source_path_created": False,
            "final_artifact_path_created": False,
            "open_seed_successor_created": False,
            "v95_mutated": False,
            "release_integration": "none",
            "construction_integration": "none",
            "identity_integration": "none",
            "federation_integration": "none",
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
            "raw_capture_retained_private": True,
        },
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-disposition-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "source_rights": (
            "Captured NXDATA, LinkedIn, PORR, and Data4 response bodies and media "
            "are treated as all-rights-reserved; no redistribution license was "
            "relied on."
        ),
        "artifact_is_hash_and_factual_extract_only": True,
        "raw_capture_redistributed": False,
        "raw_response_bodies_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "publisher_pdfs_retained_in_artifact": False,
        "publisher_media_retained_in_artifact": False,
        "request_credentials_supplied": False,
        "private_capture_directory": str(CAPTURE_ORIGIN),
        "private_capture_directory_retained": True,
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


def _offline_import(path: Path, recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="cee-nxdata-prepublication-import-", dir="/private/tmp"
    ) as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        adapter.import_file(connection, path, recorded_at=recorded_at)
        adapter.import_file(connection, path, recorded_at=recorded_at)
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
            "entities": 2,
            "entity_snapshots": 2,
            "evidence": 4,
            "lifecycle_observations": 1,
            "operating_model_observations": 1,
            "workload_observations": 0,
            "capacity_estimates": 3,
        }
        if counts != expected:
            raise RuntimeError(f"offline import counts differ: {counts!r}")
        return counts


def _assert_no_publication() -> None:
    collisions = [
        str(path)
        for path in (PROSPECTIVE_ARTIFACT, PROSPECTIVE_SOURCE)
        if path.exists() or path.is_symlink()
    ]
    if collisions:
        raise RuntimeError(f"prospective final-path collision: {collisions!r}")


def _write_source(directory: Path, document: Mapping[str, Any]) -> Path:
    path = directory / SOURCE_FILENAME
    path.write_bytes(_canonical(document))
    path.chmod(0o600)
    return path


def _write_artifact(
    directory: Path, recorded_at: str, document: Mapping[str, Any]
) -> None:
    payloads = _artifact_documents(recorded_at, document)
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
        "candidate_assessments": 4,
        "curated_source_candidates": 1,
        "review_only_candidates": 3,
        "raw_capture_redistributed": False,
        "published": False,
        "publisher_function_present": False,
        "regional_completeness_claimed": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
    }
    manifest_path = directory / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    manifest_path.chmod(0o600)
    sidecar = directory / "manifest.sha256"
    sidecar.write_text(f"{_sha256(manifest_path)}  manifest.json\n", encoding="utf-8")
    sidecar.chmod(0o600)


def validate_candidate(artifact_stage: Path, source_stage: Path) -> dict[str, Any]:
    _assert_no_publication()
    _validate_capture_directory()
    if (
        artifact_stage.is_symlink()
        or source_stage.is_symlink()
        or not artifact_stage.is_dir()
        or not source_stage.is_dir()
    ):
        raise RuntimeError("candidate stage is missing or unsafe")
    if stat.S_IMODE(artifact_stage.stat().st_mode) != 0o700:
        raise RuntimeError("candidate artifact directory mode differs")
    if stat.S_IMODE(source_stage.stat().st_mode) != 0o700:
        raise RuntimeError("candidate source directory mode differs")

    source_entries = {path.name: path for path in source_stage.iterdir()}
    if set(source_entries) != {SOURCE_FILENAME}:
        raise RuntimeError("candidate source closed file set differs")
    source_path = source_entries[SOURCE_FILENAME]
    if source_path.is_symlink() or not source_path.is_file():
        raise RuntimeError("candidate source is missing or unsafe")
    if stat.S_IMODE(source_path.stat().st_mode) != 0o600:
        raise RuntimeError("candidate source mode differs")
    document = expected_source_document()
    if source_path.read_bytes() != _canonical(document):
        raise RuntimeError("staged source differs")
    first = _offline_import(source_path, "2026-07-22T04:40:00Z")
    second = _offline_import(source_path, "2026-07-22T04:40:00Z")
    if first != second:
        raise RuntimeError("CEE NXDATA offline replay differs")

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
        raise RuntimeError("candidate manifest file inventory differs")
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
        raise RuntimeError("candidate manifest checksum differs")
    expected_payloads = _artifact_documents(manifest["recorded_at"], document)
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected_payloads[name]:
            raise RuntimeError(f"candidate artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != [_source_record(document)]:
        raise RuntimeError("candidate source record pin differs")
    return manifest


@dataclass(frozen=True)
class PreparedCandidate:
    source_stage: Path
    artifact_stage: Path
    recorded_at: str


def prepare_candidate(*, recorded_at: str | None = None) -> PreparedCandidate:
    """Create validated private stages; intentionally never promote them."""

    _assert_no_publication()
    _validate_capture_directory()
    _collision_witness()
    document = expected_source_document()
    instant = recorded_at or datetime.now(UTC).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")
    source_stage = Path(
        tempfile.mkdtemp(
            prefix=".official-cee-nxdata-gap-prepublication-sources.",
            dir=SOURCES_ROOT,
        )
    )
    artifact_stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT)
    )
    try:
        _write_source(source_stage, document)
        _write_artifact(artifact_stage, instant, document)
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
    source_path = prepared.source_stage / SOURCE_FILENAME
    return {
        "status": "PREPUBLICATION_CANDIDATE_BUILT_NOT_PUBLISHED",
        "recorded_at": prepared.recorded_at,
        "artifact_stage": str(prepared.artifact_stage),
        "artifact_manifest_sha256": _sha256(
            prepared.artifact_stage / "manifest.json"
        ),
        "artifact_tree_sha256": tree_digest(prepared.artifact_stage),
        "source_stage": str(prepared.source_stage),
        "source_pin": {
            "path": str(source_path),
            "bytes": source_path.stat().st_size,
            "sha256": _sha256(source_path),
        },
        "candidate_assessments": manifest["candidate_assessments"],
        "curated_source_candidates": manifest["curated_source_candidates"],
        "review_only_candidates": manifest["review_only_candidates"],
        "published": False,
        "prospective_final_artifact_exists": PROSPECTIVE_ARTIFACT.exists(),
        "prospective_final_source_exists": PROSPECTIVE_SOURCE.exists(),
    }


def main() -> int:
    prepared = prepare_candidate()
    print(json.dumps(candidate_result(prepared), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
