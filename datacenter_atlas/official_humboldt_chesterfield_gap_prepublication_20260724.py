"""Build, but never publish, the Humboldt and Chesterfield gap tranche.

Four governed source candidates are prepared:

* an unnamed 15 MW cryptocurrency-mining data center under construction near
  Humboldt, Tennessee;
* an in-place enrichment of the existing Google Bermuda Hundred stable keys;
* Chirisa Digital Drive as one grouped two-building construction project; and
* CTP-02/CTP-03 as one grouped construction project.

The county's CTP-02/03/04 row is not used to assign status to an individual
building.  Chirisa's current page directly groups CTP-02 and CTP-03 as in
construction and separately reserves CTP-04/05/06 for future use.  The
existing Epoch ``CoreWeave Chester VA`` row at 1401 Meadowville is preserved
as an unresolved external record and is not merged with the county's 1381
Meadowville group.

HCLTech Bhubaneswar and Hut 8 Beacon Point Phase 2 remain review-only.  The
HCLTech disclosure is a proposal and MoU.  Hut 8's statement that site
preparation is underway does not identify a Phase 2 component, so it creates
no Phase 2 construction status.

This module has no publisher or promotion function.  It writes only private
mode-0600 files inside mode-0700 staging directories.  Raw response bodies and
headers remain in a frozen private Trash bundle and are represented only by
hashes and compact factual extracts.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import shutil
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database

ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"

ARTIFACT_ID = (
    "official-humboldt-chesterfield-gap-prepublication-2026-07-24-v1"
)
PROSPECTIVE_ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID

HUMBOLDT_SOURCE_FILENAME = (
    "curated-official-2026-07-24-humboldt-tennessee-15mw-"
    "crypto-current-build.json"
)
GOOGLE_SOURCE_FILENAME = (
    "curated-official-2026-07-24-google-bermuda-hundred-"
    "chesterfield-enrichment-v2.json"
)
DIGITAL_DRIVE_SOURCE_FILENAME = (
    "curated-official-2026-07-24-chirisa-digital-drive-"
    "grouped-current-build.json"
)
CTP_SOURCE_FILENAME = (
    "curated-official-2026-07-24-chirisa-ctp02-ctp03-"
    "grouped-current-build.json"
)
SOURCE_FILENAMES = (
    HUMBOLDT_SOURCE_FILENAME,
    GOOGLE_SOURCE_FILENAME,
    DIGITAL_DRIVE_SOURCE_FILENAME,
    CTP_SOURCE_FILENAME,
)

V97_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-22-v97.json"
V97_RELEASE = ROOT / "releases/2026-07-22-open-seed-v97"
V97_ENTITIES = V97_RELEASE / "entities.csv"
V97_EVIDENCE = V97_RELEASE / "evidence.csv"
V97_MANIFEST = V97_RELEASE / "manifest.json"
V97_DEFINITION_PIN = (
    120_979,
    "32f22ccc74ec6ec33dc9bc7377a83bfee83f88dff3555555fc89cb43a27d673f",
)
V97_ENTITIES_PIN = (
    1_076_359,
    "7950a4e871d4afd0fd877e6e4f3ba9f9cbc1ffd664a611bc036896fbdba46fa1",
)
V97_EVIDENCE_PIN = (
    271_797,
    "c73263c3b27f984c8bebf76f9db31b63a22059a3774dbec9ed944ceee344f2d1",
)
V97_MANIFEST_PIN = (
    20_402,
    "0a6f41f4239944df27f2ce70e81a089b91cec401f154bbae28412b27a4d00fdd",
)
V97_RELEASE_TREE_SHA256 = (
    "5136ad66f56b7474053ff3b8cbbffca1f3df3479d8a30745a1502917fa0e7954"
)

GOOGLE_V1_SOURCE = (
    SOURCES_ROOT
    / "curated-official-2026-07-20-google-bermuda-hundred-chesterfield.json"
)
GOOGLE_V1_SOURCE_PIN = (
    16_995,
    "cf283bdd697427ea54cc282b37078af2ca4e0ba85aee08352b38427bcc8f4724",
)
GOOGLE_V1_SELECTED_PATH = (
    "sources/curated-official-2026-07-20-google-"
    "bermuda-hundred-chesterfield.json"
)

CAPTURE_ORIGIN = Path(
    "/Users/kian/.Trash/dc-official-gap-20260724.fcDR2r"
)
CAPTURE_RETRIEVED_AT = "2026-07-24T21:10:24Z"
CAPTURE_FILE_COUNT = 20
CAPTURE_TOTAL_BYTES = 3_916_471
CAPTURE_TREE_SHA256 = (
    "1616b5606827e928f9e1400e0484b465d1ff2d526bf9ae0557d8c178d849d137"
)
CAPTURE_FILE_PINS: Mapping[str, tuple[int, str]] = {
    "chesterfield_map.body": (
        2_815_406,
        "1b10fac9beaa042dd12673f7c85a94f5976047e72b71f5a6e0fdced0ceead259",
    ),
    "chesterfield_map.headers": (
        971,
        "ca1f671a23a1cd2332c7df37c26f0894bab016d7a34412a2b6690145faa0e2e4",
    ),
    "chesterfield_status.body": (
        161_337,
        "e4fb99aadfe56f33d7373e2f0b5900fcc4721eead2b6bb41f11088c4eb2c0b22",
    ),
    "chesterfield_status.headers": (
        949,
        "09a8fbd2c39dc55237b37801b1e6560ede94bc99c3466f25984da3f07ac24fa9",
    ),
    "chirisa_current.body": (
        164_315,
        "33dc758ae1735481c2d3ee73e1516330f379351c3bfc6c21107645b4f79cef11",
    ),
    "chirisa_current.headers": (
        413,
        "d07a4630c4dc45ebbb4dac17ed999e20d73b448fef1d5516a8f393ce640ff9fa",
    ),
    "hcl_bhubaneswar.body": (
        144_549,
        "13bd206e5d5722b74a1dcf39099a067287126c7147d5a19264f2d66ff51a6466",
    ),
    "hcl_bhubaneswar.headers": (
        7_285,
        "f5321e183a4d852faab92befec6ef189a220a0973b7e54fbc2d515f6c780af2f",
    ),
    "humboldt.body": (
        204_139,
        "0206d5750bc88a48ec5012a79cfb4ffbadcdf232240602e9325f696203ea1950",
    ),
    "humboldt.headers": (
        1_130,
        "e86293e02d8fe4270727d9998eb1aeefc869c7d8b7b609b699cbc38ddc3bb012",
    ),
    "hut8_beacon_point.body": (
        215_640,
        "740ffcd5969c985c3ddf610b47113926f621d422a164d1447df4bd0728228053",
    ),
    "hut8_beacon_point.headers": (
        340,
        "d611db815f69e28006589701d33888807ff964805ad6433e02717b8d04a912a6",
    ),
    "hut8_phase2.body": (
        145_388,
        "f8de731fe9fc806b50a2ca37c5563d209b6bf11d63aa3306e56705e6feba843d",
    ),
    "hut8_phase2.headers": (
        336,
        "a9977008094eef5f4a116cc85eb387cdae34b5fe464b28e2f56058f218704a4f",
    ),
    "powerhouse_ctp23.body": (
        25_444,
        "2729550c3930354f6ce2a8986f2037897d5dfc7d372773c7a6e3aa3d83cf506d",
    ),
    "powerhouse_ctp23.headers": (
        1_189,
        "30dceeda3b604a5547362ea297c237196d45b36e3593e63596cb3f34bb0de640",
    ),
    "powerhouse_digital_drive.body": (
        906,
        "90c032f35272ba1a7aa93027ab635e6610d4f24cf9e53c0624d00f065d7c7e7d",
    ),
    "powerhouse_digital_drive.headers": (
        848,
        "48c09d1d705a3c8eccc9eec86a4cb0f74e9d14bf960c3a74253f5fdd114ac804",
    ),
    "powerhouse_digital_drive_current.body": (
        24_698,
        "49793a7c46b5824e2fc08cebd887d3397d5e0adef7508d0b3d8e1de48c93044e",
    ),
    "powerhouse_digital_drive_current.headers": (
        1_188,
        "866279df11778a3fb89b66cf7ff49076a5dd341cb8fa2dd45ee480cb9e6588ed",
    ),
}

CONTENT_FILES = (
    "README.md",
    "review-ledger.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

HUMBOLDT_CAMPUS_KEY = (
    "curated:humboldt-tennessee-unnamed-15mw-crypto-data-center"
)
HUMBOLDT_PROJECT_KEY = f"{HUMBOLDT_CAMPUS_KEY}:current-build"
GOOGLE_CAMPUS_KEY = "curated:google-bermuda-hundred-chesterfield-campus"
GOOGLE_PROJECT_KEY = f"{GOOGLE_CAMPUS_KEY}:current-development"
DIGITAL_DRIVE_CAMPUS_KEY = (
    "curated:chirisa-digital-drive-chesterfield-campus"
)
DIGITAL_DRIVE_PROJECT_KEY = (
    f"{DIGITAL_DRIVE_CAMPUS_KEY}:two-building-current-build"
)
CTP_CAMPUS_KEY = "curated:chirisa-ctp-richmond-campus-1381-meadowville"
CTP_PROJECT_KEY = f"{CTP_CAMPUS_KEY}:ctp02-ctp03-grouped-current-build"

HUMBOLDT_EVIDENCE_KEY = (
    "humboldt-joint-local-data-center-release-2026-07-23-"
    "captured-2026-07-24"
)
COUNTY_EVIDENCE_KEY = (
    "chesterfield-county-data-center-status-july-2026-"
    "captured-2026-07-24"
)
CHIRISA_EVIDENCE_KEY = (
    "chirisa-current-location-inventory-captured-2026-07-24"
)
POWERHOUSE_CTP_EVIDENCE_KEY = (
    "powerhouse-ctp02-ctp03-current-page-captured-2026-07-24"
)
POWERHOUSE_DIGITAL_EVIDENCE_KEY = (
    "powerhouse-digital-drive-current-page-captured-2026-07-24"
)

EPOCH_CHESTER_STABLE_KEY = (
    "epoch-ai:data-center:6bfa628e-452f-5e99-a5dc-0e00bee67e8c"
)
EPOCH_CHESTER_ADDRESS = "1401 Meadowville Technology Parkway, Chester, VA"


@dataclass(frozen=True)
class Capture:
    capture_id: str
    stem: str
    requested_url: str
    effective_url: str
    publisher: str
    evidence_kind: str
    published_at: str | None
    response_date_header: str
    content_type: str
    claim_use: str


CAPTURES = (
    Capture(
        "humboldt",
        "humboldt",
        "https://humboldtchamber.com/"
        "local-officials-release-details-on-humboldt-data-center/",
        "https://humboldtchamber.com/"
        "local-officials-release-details-on-humboldt-data-center/",
        "City of Humboldt, Humboldt Utilities, Humboldt Chamber of Commerce",
        "government_record",
        "2026-07-23",
        "2026-07-24T21:09:58Z",
        "text/html; charset=UTF-8",
        "normalized_identity_status_workload_and_planned_facility_load",
    ),
    Capture(
        "chesterfield_status",
        "chesterfield_status",
        "https://www.chesterfield.gov/5989/Data-Centers",
        "https://www.chesterfield.gov/5989/Data-Centers",
        "Chesterfield County, Virginia",
        "government_record",
        None,
        "2026-07-24T21:09:59Z",
        "text/html; charset=utf-8",
        "normalized_address_grouped_status_and_maximum_water_metadata",
    ),
    Capture(
        "chesterfield_map",
        "chesterfield_map",
        "https://www.chesterfield.gov/DocumentCenter/View/48245/"
        "Data-Center-Map-July-2026-PDF",
        "https://www.chesterfield.gov/DocumentCenter/View/48245/"
        "Data-Center-Map-July-2026-PDF",
        "Chesterfield County, Virginia",
        "government_record",
        "2026-07",
        "2026-07-24T21:10:00Z",
        "application/pdf",
        "private_hash_bound_map_capture_no_spatial_or_identity_claim",
    ),
    Capture(
        "chirisa_current",
        "chirisa_current",
        "https://chirisatechnologyparks.com/",
        "https://chirisatechnologyparks.com/",
        "Chirisa Technology Parks",
        "company_disclosure",
        None,
        "2026-07-24T21:10:01Z",
        "text/html; charset=UTF-8",
        "normalized_ctp02_ctp03_group_status_and_phase_boundary",
    ),
    Capture(
        "powerhouse_ctp23",
        "powerhouse_ctp23",
        "https://www.powerhousedata.com/data-center/ctp-2",
        "https://www.powerhousedata.com/data-center/ctp-2",
        "PowerHouse Data Centers",
        "company_disclosure",
        None,
        "2026-07-24T21:10:01Z",
        "text/html; charset=utf-8",
        "group_identity_and_timeline_corroboration_only",
    ),
    Capture(
        "powerhouse_digital_drive_current",
        "powerhouse_digital_drive_current",
        "https://www.powerhousedata.com/data-center/digital-drive",
        "https://www.powerhousedata.com/data-center/digital-drive",
        "PowerHouse Data Centers",
        "company_disclosure",
        None,
        "2026-07-24T21:10:23Z",
        "text/html; charset=utf-8",
        "review_only_address_and_scope_discrepancy",
    ),
    Capture(
        "hcl_bhubaneswar",
        "hcl_bhubaneswar",
        "https://www.hcltech.com/press-releases/"
        "hcltech-announces-ai-data-center-bhubaneswar-"
        "partnership-sarvam-and-government",
        "https://www.hcltech.com/press-releases/"
        "hcltech-announces-ai-data-center-bhubaneswar-"
        "partnership-sarvam-and-government",
        "HCLTech",
        "company_disclosure",
        "2026-07-24",
        "2026-07-24T21:10:24Z",
        "text/html; charset=UTF-8",
        "review_only_proposal_and_mou",
    ),
    Capture(
        "hut8_phase2",
        "hut8_phase2",
        "https://www.hut8.com/news-insights/press-releases/"
        "hut-8-fully-commercializes-1-gw-beacon-point-ai-data-center-"
        "campus-with-second-352-mw-it-lease",
        "https://www.hut8.com/news-insights/press-releases/"
        "hut-8-fully-commercializes-1-gw-beacon-point-ai-data-center-"
        "campus-with-second-352-mw-it-lease",
        "Hut 8 Corp.",
        "company_disclosure",
        "2026-07-20",
        "2026-07-24T21:04:27Z",
        "text/html;charset=utf-8",
        "review_only_phase2_lease_and_phase_ambiguous_site_preparation",
    ),
    Capture(
        "hut8_beacon_point",
        "hut8_beacon_point",
        "https://www.hut8.com/data-centers/beacon-point",
        "https://www.hut8.com/data-centers/beacon-point",
        "Hut 8 Corp.",
        "company_disclosure",
        None,
        "2026-07-24T20:48:18Z",
        "text/html;charset=utf-8",
        "review_only_campus_context",
    ),
)
CAPTURE_BY_ID = {capture.capture_id: capture for capture in CAPTURES}

FAILED_CAPTURE = {
    "capture_id": "powerhouse_digital_drive_wrong_route",
    "requested_url": (
        "https://www.powerhousedata.com/data-center/1600-digital-drive"
    ),
    "http_status": 404,
    "response_date_header": "2026-07-24T21:10:03Z",
    "body_path": "powerhouse_digital_drive.body",
    "headers_path": "powerhouse_digital_drive.headers",
    "decision": "retained_rejected_wrong_route_capture",
    "normalized_claim_use": False,
}


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _pin(path: Path, expected: tuple[int, str]) -> None:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"pinned file is missing or unsafe: {path}")
    actual = (path.stat().st_size, _sha256(path))
    if actual != expected:
        raise RuntimeError(
            f"pinned file differs: {path}; expected={expected!r}, actual={actual!r}"
        )


def _capture_metadata(capture_id: str) -> dict[str, Any]:
    capture = CAPTURE_BY_ID[capture_id]
    body_pin = CAPTURE_FILE_PINS[f"{capture.stem}.body"]
    headers_pin = CAPTURE_FILE_PINS[f"{capture.stem}.headers"]
    return {
        "content_hash_scope": (
            f"SHA-256 of the exact {body_pin[0]}-byte content-decoded "
            "credential-free response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_headers_scope": (
            f"SHA-256 of the exact {headers_pin[0]}-byte raw HTTP header capture"
        ),
        "capture_headers_sha256": headers_pin[1],
        "requested_url": capture.requested_url,
        "effective_url": capture.effective_url,
        "response_http_date": capture.response_date_header,
        "content_type": capture.content_type,
        "http_status": 200,
        "retrieval_method": (
            "credential-free curl GET with redirects and compression enabled, "
            "retries disabled, and bounded connection and total timeouts"
        ),
        "request_credentials_supplied": False,
        "private_capture": {
            "directory": str(CAPTURE_ORIGIN),
            "body_path": f"{capture.stem}.body",
            "headers_path": f"{capture.stem}.headers",
            "retained_private": True,
            "redistributed": False,
        },
        "rights_scope": (
            "Compact factual extraction only; raw response bytes and publisher "
            "media are not redistributed."
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
        "kind": capture.evidence_kind,
        "title": title,
        "source_url": capture.effective_url,
        "publisher": capture.publisher,
        "source_family": source_family,
        "published_at": capture.published_at,
        "retrieved_at": CAPTURE_RETRIEVED_AT,
        "license": "all-rights-reserved",
        "attribution": capture.publisher,
        "excerpt": excerpt,
        "content_hash": CAPTURE_FILE_PINS[f"{capture.stem}.body"][1],
        "metadata": {
            **_capture_metadata(capture_id),
            **dict(metadata),
        },
    }


def _entity(
    *,
    stable_key: str,
    name: str,
    address: str,
    roles: Mapping[str, list[str]],
    evidence_key: str,
    confidence: float,
) -> dict[str, Any]:
    return {
        "stable_key": stable_key,
        "name": name,
        "country": "United States",
        "address": address,
        "roles": dict(roles),
        "coordinates": None,
        "geometry": None,
        "evidence_key": evidence_key,
        "as_of_date": "2026-07-24",
        "method": "authoritative_locality",
        "confidence": confidence,
    }


def _humboldt_evidence() -> dict[str, Any]:
    return _evidence(
        key=HUMBOLDT_EVIDENCE_KEY,
        capture_id="humboldt",
        title="Local Officials Release Details on Humboldt Data Center",
        excerpt=(
            "Local officials jointly report an unnamed data center currently "
            "under construction near the Gibson County Industrial Park that "
            "will operate as a 15 MW cryptocurrency-mining facility."
        ),
        source_family="humboldt_joint_local_official_release",
        metadata={
            "reported_identity": "new data center",
            "reported_locality": (
                "near the Gibson County Industrial Park, Humboldt, Tennessee"
            ),
            "reported_site_area_acres_approximate": 2,
            "reported_status_wording": "currently under construction",
            "reported_application": "cryptocurrency mining",
            "reported_customer_facility_load_mw": 15,
            "reported_annual_water_use_gallons_up_to_approximate": 2_000_000,
            "reported_dedicated_electrical_infrastructure": True,
            "developer": None,
            "operator": None,
            "owner": None,
            "identity_guardrail": (
                "No unnamed owner, operator, developer, customer, utility "
                "affiliate, parcel owner, or contractor is inferred."
            ),
            "locality_guardrail": (
                "The broad locality is retained without a street address, "
                "parcel, point, footprint, geometry, or inferred unique-site "
                "coordinate."
            ),
            "capacity_scope": (
                "The 15 MW is normalized once as planned reported gross "
                "facility/customer load because the release describes the "
                "whole facility as a new 15 MW electric customer. It is not "
                "critical IT, current draw, metered consumption, annual "
                "energy, generation, grid-connection capacity, or PUE."
            ),
            "water_guardrail": (
                "The approximate annual maximum remains source metadata only. "
                "It is not current or measured water use, WUE, energy, power, "
                "cooling capacity, or a conversion to daily consumption."
            ),
            "currentness_scope": (
                "Under construction is a last-observed status as of the "
                "2026-07-23 release, not proof of the facility's status after "
                "that date."
            ),
            "imagery_guardrail": (
                "No publisher image, satellite image, aerial image, computer "
                "vision, geocoder, or analyst geolocation contributes."
            ),
        },
    )


def _county_evidence() -> dict[str, Any]:
    return _evidence(
        key=COUNTY_EVIDENCE_KEY,
        capture_id="chesterfield_status",
        title="Chesterfield County Data Center Project Status as of July 2026",
        excerpt=(
            "The county reports Peanut LLC at 2100 Bermuda Hundred Road under "
            "construction as three buildings, Chirisa Digital Drive at 1551 "
            "Digital Drive under construction as two buildings, and a grouped "
            "CTP-02/03/04 row at 1381 Meadowville Tech Parkway."
        ),
        source_family="chesterfield_county_data_center_status",
        metadata={
            "status_period_as_reported": "July 2026",
            "status_observed_at": CAPTURE_RETRIEVED_AT,
            "google_bermuda_hundred": {
                "county_project_label": "Peanut LLC",
                "address": "2100 Bermuda Hundred Road",
                "status": "Under construction; three buildings",
                "maximum_water_usage_mgd": 6.0,
            },
            "chirisa_digital_drive": {
                "address": "1551 Digital Drive",
                "status": "Under construction; two buildings",
                "maximum_water_usage": "None anticipated; closed system",
            },
            "chirisa_ctp_group": {
                "county_project_label": "Chirisa CTP-02, 03 and 04",
                "address": "1381 Meadowville Tech Parkway",
                "status": (
                    "Two existing buildings and one building under construction"
                ),
                "maximum_water_usage_mgd": 0.840,
            },
            "water_guardrail": (
                "Every water value is a county-reported maximum or design "
                "expectation, not current use, measured use, WUE, energy, "
                "power, or capacity."
            ),
            "building_guardrail": (
                "Building counts remain grouped metadata. No building entity, "
                "building-specific lifecycle, phase assignment, capacity "
                "allocation, or unique physical-site arithmetic is created."
            ),
            "status_date_guardrail": (
                "The county gives month precision. The normalized observation "
                "date is the credential-free retrieval date and means status "
                "observed on the county's current July 2026 page, not a claimed "
                "day-specific construction event."
            ),
            "map_pdf_private_capture": {
                "url": CAPTURE_BY_ID["chesterfield_map"].effective_url,
                "bytes": CAPTURE_FILE_PINS["chesterfield_map.body"][0],
                "sha256": CAPTURE_FILE_PINS["chesterfield_map.body"][1],
                "headers_sha256": CAPTURE_FILE_PINS[
                    "chesterfield_map.headers"
                ][1],
                "normalized_claim_use": False,
                "coordinate_or_geometry_claim_created": False,
            },
        },
    )


def _chirisa_evidence() -> dict[str, Any]:
    return _evidence(
        key=CHIRISA_EVIDENCE_KEY,
        capture_id="chirisa_current",
        title="Chirisa Technology Parks current data center locations",
        excerpt=(
            "Chirisa's current location inventory groups CTP-02 and CTP-03 as "
            "in construction and separately reserves CTP-04/05/06 for future "
            "use; it describes the DDC campus as buildings under development."
        ),
        source_family="chirisa_technology_parks_locations_20260724",
        metadata={
            "ctp02_ctp03": {
                "status_wording": "CTP-02 & CTP-03 – in construction",
                "reported_group_area_sqft": 284_000,
                "reported_utility_power_mw": 120,
                "reservation_status": "Reserved",
            },
            "ctp04_ctp05_ctp06": {
                "status_wording": "reserved for future use",
                "reported_planned_area_sqft": 450_000,
                "reported_utility_power_mw": 200,
                "forecast": "Reserved for 2027/2028 delivery",
            },
            "ddc_campus": {
                "reported_site_area_acres": 104,
                "reported_scope": "3 x 200,000 sq. ft. buildings under development",
                "forecast": "Reserved for 2027/2028 delivery",
            },
            "capacity_guardrail": (
                "Utility-power displays, forecast availability, acreage, and "
                "floor area remain metadata. They create no critical IT, gross "
                "facility, grid connection, generation, current load, annual "
                "energy, or PUE row."
            ),
            "phase_guardrail": (
                "CTP-02 and CTP-03 remain one grouped project; CTP-04, CTP-05, "
                "and CTP-06 create no entity or lifecycle observation."
            ),
            "ddc_guardrail": (
                "The DDC inventory does not allocate current construction to an "
                "individual building or reconcile its three-building scope with "
                "the county's two-building current row."
            ),
        },
    )


def _powerhouse_ctp_evidence() -> dict[str, Any]:
    return _evidence(
        key=POWERHOUSE_CTP_EVIDENCE_KEY,
        capture_id="powerhouse_ctp23",
        title="PowerHouse CTP-02 and CTP-03",
        excerpt=(
            "PowerHouse groups CTP-02 and CTP-03 as two buildings and displays "
            "a construction/delivery timeline from Q3 2024 to Q1 2027."
        ),
        source_family="powerhouse_data_centers_current_projects",
        metadata={
            "reported_group": "CTP-02 and CTP-03",
            "reported_buildings": 2,
            "reported_max_utility_power_mw": 120,
            "reported_delivery": "Q1 2027",
            "reported_construction_delivery_timeline": "Q3 2024 - Q1 2027",
            "capacity_guardrail": (
                "The displayed maximum utility power is not normalized as "
                "critical IT, gross facility load, contracted grid capacity, "
                "generation, current draw, consumption, annual energy, or PUE."
            ),
            "schedule_guardrail": (
                "The forecast creates no completion, energization, "
                "commissioning, occupancy, operation, or currentness claim."
            ),
        },
    )


def _powerhouse_digital_evidence() -> dict[str, Any]:
    return _evidence(
        key=POWERHOUSE_DIGITAL_EVIDENCE_KEY,
        capture_id="powerhouse_digital_drive_current",
        title="PowerHouse 1600 Digital Drive",
        excerpt=(
            "PowerHouse's current project page identifies 1600 Digital Drive "
            "and a planned multi-building campus but does not provide a current "
            "physical construction statement."
        ),
        source_family="powerhouse_data_centers_current_projects",
        metadata={
            "reported_page_title": "1600 Digital Drive",
            "reported_site_area_acres": 100,
            "reported_developable_sqft": 695_000,
            "reported_buildings_up_to": 5,
            "reported_max_utility_power_mw": 300,
            "reported_delivery": "Q3 2027",
            "address_reconciliation_guardrail": (
                "The PowerHouse page's 1600 label differs from the county's "
                "1551 Digital Drive current-build address. It is retained only "
                "as a review signal and creates no address alias, parcel merge, "
                "building identity, lifecycle observation, or capacity row."
            ),
            "status_guardrail": (
                "A future delivery timeline is not component-specific physical "
                "construction evidence."
            ),
        },
    )


def _humboldt_document() -> dict[str, Any]:
    address = (
        "Near Gibson County Industrial Park, Humboldt, Tennessee, United States"
    )
    return {
        "schema_version": "1.1",
        "evidence": [_humboldt_evidence()],
        "campus": _entity(
            stable_key=HUMBOLDT_CAMPUS_KEY,
            name="Unnamed Humboldt 15 MW Cryptocurrency Data Center",
            address=address,
            roles={},
            evidence_key=HUMBOLDT_EVIDENCE_KEY,
            confidence=0.97,
        ),
        "project": _entity(
            stable_key=HUMBOLDT_PROJECT_KEY,
            name="Unnamed Humboldt 15 MW Current Build",
            address=address,
            roles={},
            evidence_key=HUMBOLDT_EVIDENCE_KEY,
            confidence=0.97,
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": HUMBOLDT_EVIDENCE_KEY,
                "as_of_date": "2026-07-23",
                "method": "authoritative_physical_status_update",
                "confidence": 0.99,
            }
        ],
        "operating_models": [],
        "workloads": [
            {
                "entity": "project",
                "value": "crypto_mining",
                "evidence_key": HUMBOLDT_EVIDENCE_KEY,
                "as_of_date": "2026-07-23",
                "method": "government_record",
                "confidence": 0.99,
            }
        ],
        "capacities": [
            {
                "entity": "project",
                "metric": "gross_facility_mw",
                "stage": "planned",
                "unit": "MW",
                "low": 15,
                "base": 15,
                "high": 15,
                "method": "reported",
                "confidence": 0.98,
                "evidence_key": HUMBOLDT_EVIDENCE_KEY,
                "as_of_date": "2026-07-23",
                "target_date": None,
                "notes": (
                    "Reported whole-facility/customer planned load. This is not "
                    "critical IT, current draw, metered consumption, annual "
                    "energy, grid connection, generation, or PUE."
                ),
            }
        ],
    }


def _google_document() -> dict[str, Any]:
    _pin(GOOGLE_V1_SOURCE, GOOGLE_V1_SOURCE_PIN)
    original = json.loads(GOOGLE_V1_SOURCE.read_text(encoding="utf-8"))
    document = copy.deepcopy(original)
    document["schema_version"] = "1.1"
    document["evidence"].append(_county_evidence())
    address = (
        "2100 Bermuda Hundred Road, Chesterfield County, Virginia, United States"
    )
    for entity_name in ("campus", "project"):
        entity = document[entity_name]
        entity["address"] = address
        entity["evidence_key"] = COUNTY_EVIDENCE_KEY
        entity["as_of_date"] = "2026-07-24"
        entity["method"] = "authoritative_locality"
        entity["confidence"] = 0.99
    document["lifecycle"].append(
        {
            "entity": "project",
            "value": "under_construction",
            "evidence_key": COUNTY_EVIDENCE_KEY,
            "as_of_date": "2026-07-24",
            "method": "authoritative_physical_status_update",
            "confidence": 0.99,
        }
    )
    return document


def _digital_drive_document() -> dict[str, Any]:
    address = (
        "1551 Digital Drive, Chesterfield County, Virginia, United States"
    )
    roles = {"developer": ["Chirisa Technology Parks"]}
    return {
        "schema_version": "1.1",
        "evidence": [
            _county_evidence(),
            _chirisa_evidence(),
            _powerhouse_digital_evidence(),
        ],
        "campus": _entity(
            stable_key=DIGITAL_DRIVE_CAMPUS_KEY,
            name="Chirisa Digital Drive Campus",
            address=address,
            roles=roles,
            evidence_key=COUNTY_EVIDENCE_KEY,
            confidence=0.99,
        ),
        "project": _entity(
            stable_key=DIGITAL_DRIVE_PROJECT_KEY,
            name="Chirisa Digital Drive Two-Building Current Build",
            address=address,
            roles=roles,
            evidence_key=COUNTY_EVIDENCE_KEY,
            confidence=0.99,
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": COUNTY_EVIDENCE_KEY,
                "as_of_date": "2026-07-24",
                "method": "authoritative_physical_status_update",
                "confidence": 0.99,
            }
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _ctp_document() -> dict[str, Any]:
    address = (
        "1381 Meadowville Tech Parkway, Chesterfield County, Virginia, "
        "United States"
    )
    roles = {"developer": ["Chirisa Technology Parks"]}
    return {
        "schema_version": "1.1",
        "evidence": [
            _county_evidence(),
            _chirisa_evidence(),
            _powerhouse_ctp_evidence(),
        ],
        "campus": _entity(
            stable_key=CTP_CAMPUS_KEY,
            name="Chirisa CTP Richmond Campus at 1381 Meadowville",
            address=address,
            roles=roles,
            evidence_key=COUNTY_EVIDENCE_KEY,
            confidence=0.98,
        ),
        "project": _entity(
            stable_key=CTP_PROJECT_KEY,
            name="Chirisa CTP-02 and CTP-03 Grouped Current Build",
            address=address,
            roles=roles,
            evidence_key=COUNTY_EVIDENCE_KEY,
            confidence=0.98,
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": CHIRISA_EVIDENCE_KEY,
                "as_of_date": "2026-07-24",
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
        HUMBOLDT_SOURCE_FILENAME: _humboldt_document(),
        GOOGLE_SOURCE_FILENAME: _google_document(),
        DIGITAL_DRIVE_SOURCE_FILENAME: _digital_drive_document(),
        CTP_SOURCE_FILENAME: _ctp_document(),
    }
    if tuple(documents) != SOURCE_FILENAMES:
        raise RuntimeError("source document order differs")
    for name, document in documents.items():
        if (
            document["schema_version"] != "1.1"
            or document["operating_models"]
        ):
            raise RuntimeError(f"source boundary differs: {name}")
        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            if entity["coordinates"] is not None or entity["geometry"] is not None:
                raise RuntimeError(f"spatial boundary differs: {name}")
    return documents


def _validate_capture_directory(directory: Path = CAPTURE_ORIGIN) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("private capture directory is unsafe")
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


def _planned_stable_keys() -> set[str]:
    return {
        HUMBOLDT_CAMPUS_KEY,
        HUMBOLDT_PROJECT_KEY,
        GOOGLE_CAMPUS_KEY,
        GOOGLE_PROJECT_KEY,
        DIGITAL_DRIVE_CAMPUS_KEY,
        DIGITAL_DRIVE_PROJECT_KEY,
        CTP_CAMPUS_KEY,
        CTP_PROJECT_KEY,
    }


def _planned_evidence_keys() -> set[str]:
    documents = expected_source_documents()
    return {
        evidence["key"]
        for document in documents.values()
        for evidence in document["evidence"]
    }


def _v97_witness() -> dict[str, Any]:
    _pin(V97_DEFINITION, V97_DEFINITION_PIN)
    _pin(V97_ENTITIES, V97_ENTITIES_PIN)
    _pin(V97_EVIDENCE, V97_EVIDENCE_PIN)
    _pin(V97_MANIFEST, V97_MANIFEST_PIN)
    if tree_digest(V97_RELEASE) != V97_RELEASE_TREE_SHA256:
        raise RuntimeError("v97 release tree differs")

    definition = json.loads(V97_DEFINITION.read_text(encoding="utf-8"))
    manifest = json.loads(V97_MANIFEST.read_text(encoding="utf-8"))
    with V97_ENTITIES.open(encoding="utf-8", newline="") as handle:
        entities = list(csv.DictReader(handle))
    with V97_EVIDENCE.open(encoding="utf-8", newline="") as handle:
        evidence = list(csv.DictReader(handle))

    by_stable = {row["stable_key"]: row for row in entities}
    existing_stable = set(by_stable)
    existing_evidence = {row["title"]: row for row in evidence}
    existing_evidence_ids = {row["evidence_id"] for row in evidence}
    del existing_evidence_ids
    selected = {row["path"]: row["sha256"] for row in definition["curated_inputs"]}

    google = {
        key: {
            "entity_kind": by_stable[key]["entity_kind"],
            "name": by_stable[key]["name"],
            "address": by_stable[key]["address"],
        }
        for key in (GOOGLE_CAMPUS_KEY, GOOGLE_PROJECT_KEY)
    }
    epoch = by_stable.get(EPOCH_CHESTER_STABLE_KEY)
    if epoch is None:
        raise RuntimeError("v97 Epoch Chester witness is missing")
    if (
        epoch["name"] != "CoreWeave Chester VA"
        or epoch["address"] != EPOCH_CHESTER_ADDRESS
    ):
        raise RuntimeError("v97 Epoch Chester witness differs")

    old_google = json.loads(GOOGLE_V1_SOURCE.read_text(encoding="utf-8"))
    old_google_primary_title = next(
        row["title"]
        for row in old_google["evidence"]
        if row["key"] == old_google["campus"]["evidence_key"]
    )
    if old_google_primary_title not in existing_evidence:
        raise RuntimeError("v97 Google evidence witness differs")

    collisions = sorted(_planned_stable_keys() & existing_stable)
    expected_collisions = sorted({GOOGLE_CAMPUS_KEY, GOOGLE_PROJECT_KEY})
    if collisions != expected_collisions:
        raise RuntimeError("v97 stable-key collision boundary differs")

    return {
        "release_id": definition["release_id"],
        "recorded_at": manifest["recorded_at"],
        "curated_input_count": len(definition["curated_inputs"]),
        "entity_count": len(entities),
        "evidence_count": len(evidence),
        "release_tree_sha256": V97_RELEASE_TREE_SHA256,
        "planned_stable_key_collisions": collisions,
        "expected_in_place_google_replacement_collisions": expected_collisions,
        "planned_new_stable_keys": sorted(
            _planned_stable_keys() - existing_stable
        ),
        "google_existing_entities": google,
        "google_v1_selected": selected.get(GOOGLE_V1_SELECTED_PATH)
        == GOOGLE_V1_SOURCE_PIN[1],
        "prospective_google_integration_mode": (
            "replace_v1_source_never_co_select"
        ),
        "existing_epoch_chester_record": {
            "stable_key": epoch["stable_key"],
            "name": epoch["name"],
            "address": epoch["address"],
            "latitude": epoch["latitude"],
            "longitude": epoch["longitude"],
            "merge_with_ctp_or_digital_drive_asserted": False,
        },
    }


def _review_ledger(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-gap-review-ledger-v1",
        "research_date": "2026-07-24",
        "recorded_at": recorded_at,
        "candidate_count": 7,
        "governed_source_candidate_count": 4,
        "review_only_count": 3,
        "published": False,
        "candidates": [
            {
                "candidate_id": "humboldt-unnamed-15mw-crypto-current-build",
                "decision": "governed_prepublication_current_physical_build",
                "source_paths": [
                    f"prospective-sources/{HUMBOLDT_SOURCE_FILENAME}"
                ],
                "campus_stable_key": HUMBOLDT_CAMPUS_KEY,
                "project_stable_key": HUMBOLDT_PROJECT_KEY,
                "new_entity_snapshots": 2,
                "lifecycle": "under_construction",
                "workload": "crypto_mining",
                "planned_gross_facility_mw": 15,
                "current_load_claim_created": False,
                "annual_energy_claim_created": False,
                "generation_claim_created": False,
                "water_observation_created": False,
            },
            {
                "candidate_id": "google-bermuda-hundred-v2-enrichment",
                "decision": "governed_prepublication_in_place_enrichment",
                "source_paths": [
                    f"prospective-sources/{GOOGLE_SOURCE_FILENAME}"
                ],
                "campus_stable_key": GOOGLE_CAMPUS_KEY,
                "project_stable_key": GOOGLE_PROJECT_KEY,
                "new_entity_snapshots": 0,
                "reused_entity_snapshots": 2,
                "integration_mode": "replace_v1_source_never_co_select",
                "address": "2100 Bermuda Hundred Road",
                "grouped_buildings_under_construction": 3,
                "maximum_water_usage_mgd_metadata_only": 6.0,
                "duplicate_entity_created": False,
            },
            {
                "candidate_id": "chirisa-digital-drive-grouped-current-build",
                "decision": "governed_prepublication_grouped_current_build",
                "source_paths": [
                    f"prospective-sources/{DIGITAL_DRIVE_SOURCE_FILENAME}"
                ],
                "campus_stable_key": DIGITAL_DRIVE_CAMPUS_KEY,
                "project_stable_key": DIGITAL_DRIVE_PROJECT_KEY,
                "address": "1551 Digital Drive",
                "grouped_buildings_under_construction": 2,
                "per_building_entities_created": 0,
                "powerhouse_1600_address_alias_asserted": False,
            },
            {
                "candidate_id": "chirisa-ctp02-ctp03-grouped-current-build",
                "decision": "governed_prepublication_phase_unresolved_group",
                "source_paths": [
                    f"prospective-sources/{CTP_SOURCE_FILENAME}"
                ],
                "campus_stable_key": CTP_CAMPUS_KEY,
                "project_stable_key": CTP_PROJECT_KEY,
                "address": "1381 Meadowville Tech Parkway",
                "group_members": ["CTP-02", "CTP-03"],
                "per_building_status_assignment_created": False,
                "county_ctp02_ctp03_ctp04_building_assignment_used": False,
                "epoch_coreweave_chester_merge_asserted": False,
            },
            {
                "candidate_id": "chirisa-ctp04",
                "decision": "review_only_future_use_and_county_phase_conflict",
                "source_paths": [],
                "stable_key_created": False,
                "lifecycle_claim_created": False,
                "reason": (
                    "Chirisa reserves CTP-04/05/06 for future use, while the "
                    "county groups CTP-02/03/04 without assigning its two "
                    "existing and one under-construction buildings."
                ),
            },
            {
                "candidate_id": "hcltech-bhubaneswar-ai-data-center",
                "decision": "review_only_proposal_and_mou",
                "source_paths": [],
                "stable_key_created": False,
                "lifecycle_claim_created": False,
                "reported_wording": "plans to set-up",
                "reported_mou": True,
                "reported_planned_capital_outlay_inr_crore": 14_257,
                "reason": (
                    "The official disclosure is a plan and MoU and contains no "
                    "component-specific physical construction evidence."
                ),
            },
            {
                "candidate_id": "hut8-beacon-point-phase2",
                "decision": (
                    "review_only_phase_ambiguous_site_preparation_enrichment"
                ),
                "source_paths": [],
                "stable_key_created": False,
                "lifecycle_claim_created": False,
                "existing_campus_stable_key": (
                    "curated:hut8-beacon-point-ai-data-center-campus"
                ),
                "reported_second_lease_critical_it_mw": 352,
                "reported_initial_phase2_data_hall_delivery": "Q2 2028",
                "site_preparation_wording": "Site preparation is underway",
                "site_preparation_assigned_to_phase2": False,
                "reason": (
                    "The physical wording says site, not a named Phase 2 data "
                    "hall or component. It cannot promote Phase 2 to a physical "
                    "construction lifecycle."
                ),
            },
        ],
        "cross_record_reconciliation": {
            "epoch_coreweave_chester": {
                "stable_key": EPOCH_CHESTER_STABLE_KEY,
                "address": EPOCH_CHESTER_ADDRESS,
                "merged_with_1381_meadowville_group": False,
                "merged_with_1551_digital_drive_group": False,
                "reason": (
                    "No exact official identity bridge establishes that the "
                    "Epoch record is either grouped source candidate."
                ),
            },
            "digital_drive_address_discrepancy": {
                "county_current_build_address": "1551 Digital Drive",
                "powerhouse_page_label": "1600 Digital Drive",
                "alias_or_parcel_equivalence_asserted": False,
            },
        },
    }


def _retrieval_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-24",
        "recorded_at": recorded_at,
        "controlled_request_target_count": 10,
        "successful_http_200_body_captures": 9,
        "retained_rejected_http_captures": 1,
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
                "requested_url": capture.requested_url,
                "effective_url": capture.effective_url,
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
        "retained_rejected_capture": {
            **FAILED_CAPTURE,
            "body": {
                "path": FAILED_CAPTURE["body_path"],
                "bytes": CAPTURE_FILE_PINS[FAILED_CAPTURE["body_path"]][0],
                "sha256": CAPTURE_FILE_PINS[FAILED_CAPTURE["body_path"]][1],
            },
            "headers": {
                "path": FAILED_CAPTURE["headers_path"],
                "bytes": CAPTURE_FILE_PINS[FAILED_CAPTURE["headers_path"]][0],
                "sha256": CAPTURE_FILE_PINS[FAILED_CAPTURE["headers_path"]][1],
            },
        },
        "complete_private_file_inventory": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in sorted(CAPTURE_FILE_PINS.items())
        ],
    }


def _source_records(
    documents: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "path": f"prospective-sources/{name}",
            "sha256": _sha256_bytes(_canonical(document)),
            "bytes": len(_canonical(document)),
            "campus_stable_key": document["campus"]["stable_key"],
            "project_stable_key": document["project"]["stable_key"],
            "evidence_records": len(document["evidence"]),
            "lifecycle_observations": len(document["lifecycle"]),
            "workload_observations": len(document["workloads"]),
            "capacity_estimates": len(document["capacities"]),
            "coordinates_present": False,
            "geometry_present": False,
            "published": False,
            "seeded": False,
        }
        for name, document in documents.items()
    ]


def _artifact_documents(
    recorded_at: str,
    documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    ledger = _review_ledger(recorded_at)
    witness = _v97_witness()
    readme = f"""# Humboldt and Chesterfield official gap — prepublication only

Built at {recorded_at}; not published.

The four private source candidates contain eight entity snapshots: six new
snapshots and an in-place two-entity enrichment of the existing Google Bermuda
Hundred stable keys. They contain seven distinct evidence records, five
lifecycle observations, one `crypto_mining` workload observation, and one
planned reported 15 MW `gross_facility_mw` row. No current load, critical IT,
annual energy, generation, PUE, measured water, coordinate, geometry, parcel,
building entity, or satellite-derived claim is created.

Humboldt's developer, operator, and owner remain unknown. Google keeps its
existing stable keys and must replace, never coexist with, the v1 selected
source. Digital Drive is a grouped two-building project at the county's 1551
Digital Drive address. CTP-02 and CTP-03 are one phase-unresolved grouped
project; CTP-04/05/06 remain future/review-only. The Epoch CoreWeave Chester
record at 1401 Meadowville is not merged.

HCLTech Bhubaneswar is proposal/MoU-only. Hut 8 Beacon Point Phase 2 remains
review-only because the statement that site preparation is underway does not
identify a Phase 2 component.

The frozen private capture bundle contains nine successful first-party
responses and one retained rejected 404 wrong-route response. Raw bodies,
headers, PDFs, and media are not redistributed. This builder exposes no
publisher or promotion function and creates no final source, final artifact,
open-seed successor, release, federation, identity, timeline, master, map, or
coverage output.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "research_date": "2026-07-24",
        "recorded_at": recorded_at,
        "global_completeness_claimed": False,
        "source_records": _source_records(documents),
        "totals": {
            "candidate_assessments": 7,
            "source_records": 4,
            "governed_prepublication_candidates": 4,
            "review_only_candidates": 3,
            "distinct_entity_snapshots": 8,
            "new_entities_against_v97": 6,
            "reused_existing_entities": 2,
            "distinct_evidence_records": 7,
            "source_document_evidence_appearances": 10,
            "lifecycle_observations": 5,
            "operating_model_observations": 0,
            "workload_observations": 1,
            "capacity_estimates": 1,
            "current_load_observations": 0,
            "annual_energy_observations": 0,
            "generation_observations": 0,
            "water_observations": 0,
            "coordinate_observations": 0,
            "geometry_observations": 0,
            "satellite_observations": 0,
        },
        "v97_witness": witness,
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
        "research_date": "2026-07-24",
        "recorded_at": recorded_at,
        "source_rights": (
            "Captured official responses are treated as all-rights-reserved; "
            "no redistribution license was relied on."
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
        "publication_performed": False,
    }
    return {
        "README.md": readme.encode(),
        "review-ledger.json": _canonical(ledger),
        "retrieval-inventory.json": _canonical(
            _retrieval_inventory(recorded_at)
        ),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def _write_sources(
    directory: Path,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    for name in SOURCE_FILENAMES:
        path = directory / name
        path.write_bytes(_canonical(documents[name]))
        path.chmod(0o600)


def _offline_import(
    paths: Mapping[str, Path],
    recorded_at: str,
) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="humboldt-chesterfield-prepublication-import-",
        dir="/private/tmp",
    ) as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            for name in SOURCE_FILENAMES:
                adapter.import_file(
                    connection,
                    paths[name],
                    recorded_at=recorded_at,
                )
        errors = validate_database(connection)
        if errors:
            raise RuntimeError(
                f"offline database validation failed: {errors!r}"
            )
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
            table: connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            for table in tables
        }
        expected = {
            "entities": 8,
            "entity_snapshots": 8,
            "evidence": 7,
            "lifecycle_observations": 5,
            "operating_model_observations": 0,
            "workload_observations": 1,
            "capacity_estimates": 1,
        }
        if counts != expected:
            raise RuntimeError(f"offline import counts differ: {counts!r}")
        return counts


def _validate_sources(paths: Mapping[str, Path]) -> dict[str, int]:
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
    first = _offline_import(paths, "2026-07-24T21:20:00Z")
    second = _offline_import(paths, "2026-07-24T21:20:00Z")
    if first != second:
        raise RuntimeError("offline import replay differs")
    return first


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
        "candidate_assessments": 7,
        "curated_source_candidates": 4,
        "review_only_candidates": 3,
        "raw_capture_redistributed": False,
        "published": False,
        "publisher_function_present": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
    }
    manifest_path = directory / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    manifest_path.chmod(0o600)
    sidecar = directory / "manifest.sha256"
    sidecar.write_text(
        f"{_sha256(manifest_path)}  manifest.json\n",
        encoding="utf-8",
    )
    sidecar.chmod(0o600)


def _assert_no_publication() -> None:
    final_sources = [SOURCES_ROOT / name for name in SOURCE_FILENAMES]
    collisions = [
        str(path)
        for path in (PROSPECTIVE_ARTIFACT, *final_sources)
        if path.exists() or path.is_symlink()
    ]
    if collisions:
        raise RuntimeError(
            f"prospective final-path collision: {collisions!r}"
        )


def validate_candidate(
    artifact_stage: Path,
    source_stage: Path,
) -> dict[str, Any]:
    _assert_no_publication()
    _validate_capture_directory()
    witness = _v97_witness()
    if witness["planned_stable_key_collisions"] != sorted(
        {GOOGLE_CAMPUS_KEY, GOOGLE_PROJECT_KEY}
    ):
        raise RuntimeError("expected Google replacement collision differs")
    if (
        artifact_stage.is_symlink()
        or source_stage.is_symlink()
        or not artifact_stage.is_dir()
        or not source_stage.is_dir()
    ):
        raise RuntimeError("candidate stage is missing or unsafe")
    if stat.S_IMODE(artifact_stage.stat().st_mode) != 0o700:
        raise RuntimeError("artifact stage mode differs")
    if stat.S_IMODE(source_stage.stat().st_mode) != 0o700:
        raise RuntimeError("source stage mode differs")

    source_counts = _validate_sources(_source_paths(source_stage))
    artifact_entries = {
        path.name: path for path in artifact_stage.iterdir()
    }
    if set(artifact_entries) != CLOSED_FILES:
        raise RuntimeError("candidate artifact closed file set differs")
    for name, path in artifact_entries.items():
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"unsafe artifact member: {name}")
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise RuntimeError(f"artifact member mode differs: {name}")

    manifest_path = artifact_entries["manifest.json"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest["published"] is not False
        or manifest["publisher_function_present"] is not False
        or manifest["curated_source_candidates"] != 4
        or manifest["review_only_candidates"] != 3
    ):
        raise RuntimeError("prepublication manifest boundary differs")
    sidecar = artifact_entries["manifest.sha256"].read_text(encoding="utf-8")
    if sidecar != f"{_sha256(manifest_path)}  manifest.json\n":
        raise RuntimeError("manifest sidecar differs")
    listed = {row["path"]: row for row in manifest["files"]}
    if set(listed) != set(CONTENT_FILES):
        raise RuntimeError("manifest file inventory differs")
    for name, row in listed.items():
        path = artifact_entries[name]
        if row["bytes"] != path.stat().st_size or row["sha256"] != _sha256(
            path
        ):
            raise RuntimeError(f"manifest member pin differs: {name}")

    ledger = json.loads(
        artifact_entries["review-ledger.json"].read_text(encoding="utf-8")
    )
    if (
        ledger["candidate_count"] != 7
        or ledger["governed_source_candidate_count"] != 4
        or ledger["review_only_count"] != 3
        or ledger["published"] is not False
    ):
        raise RuntimeError("review-ledger counts differ")
    _assert_no_publication()
    return {
        **manifest,
        "offline_import_counts": source_counts,
        "v97_witness": witness,
    }


@dataclass(frozen=True)
class PreparedCandidate:
    source_stage: Path
    artifact_stage: Path
    recorded_at: str


def prepare_candidate(*, recorded_at: str | None = None) -> PreparedCandidate:
    _assert_no_publication()
    _validate_capture_directory()
    timestamp = recorded_at or datetime.now(UTC).isoformat().replace(
        "+00:00",
        "Z",
    )
    source_stage = Path(
        tempfile.mkdtemp(
            prefix=".humboldt-chesterfield-prepublication-sources.",
            dir=SOURCES_ROOT,
        )
    )
    artifact_stage = Path(
        tempfile.mkdtemp(
            prefix=".humboldt-chesterfield-prepublication-artifact.",
            dir=ARTIFACT_ROOT,
        )
    )
    source_stage.chmod(0o700)
    artifact_stage.chmod(0o700)
    try:
        documents = expected_source_documents()
        _write_sources(source_stage, documents)
        _write_artifact(artifact_stage, timestamp, documents)
        validate_candidate(artifact_stage, source_stage)
    except BaseException:
        shutil.rmtree(source_stage, ignore_errors=True)
        shutil.rmtree(artifact_stage, ignore_errors=True)
        raise
    return PreparedCandidate(source_stage, artifact_stage, timestamp)


def candidate_result(prepared: PreparedCandidate) -> dict[str, Any]:
    manifest = validate_candidate(
        prepared.artifact_stage,
        prepared.source_stage,
    )
    return {
        "status": "PREPUBLICATION_CANDIDATE_BUILT_NOT_PUBLISHED",
        "artifact_id": ARTIFACT_ID,
        "recorded_at": prepared.recorded_at,
        "source_stage": str(prepared.source_stage),
        "artifact_stage": str(prepared.artifact_stage),
        "source_stage_tree_sha256": tree_digest(prepared.source_stage),
        "artifact_stage_tree_sha256": tree_digest(prepared.artifact_stage),
        "candidate_assessments": manifest["candidate_assessments"],
        "curated_source_candidates": manifest["curated_source_candidates"],
        "review_only_candidates": manifest["review_only_candidates"],
        "offline_import_counts": manifest["offline_import_counts"],
        "published": False,
        "prospective_final_artifact_exists": PROSPECTIVE_ARTIFACT.exists(),
        "prospective_final_sources_exist": {
            name: (SOURCES_ROOT / name).exists() for name in SOURCE_FILENAMES
        },
        "open_seed_successor_created": False,
        "release_integration": "none",
        "federation_integration": "none",
        "identity_integration": "none",
        "construction_master_integration": "none",
        "map_integration": "none",
    }


def main() -> int:
    prepared = prepare_candidate()
    print(json.dumps(candidate_result(prepared), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
