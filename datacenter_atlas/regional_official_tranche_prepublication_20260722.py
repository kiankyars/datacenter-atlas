"""Build, but never publish, three governed regional official-source candidates.

The tranche contains Viettel's An Khanh Data Center in Vietnam, the Oran data
center and AI computing center in Algeria, and Noor Data Center in Egypt.  The
only normalized construction claims are the official An Khanh groundbreaking,
the Oran cornerstone observation, and Square Engineering's retrieval-date
``Ongoing`` classification for Noor.  Bolivia remains review-only because its
official server returned no response bytes during either controlled attempt.

This module deliberately has no publisher or promotion function.  It emits no
coordinate, geometry, facility-type, operating-model, workload, capacity,
energy-consumption, or efficiency observation.  Viettel's 60 MW is retained
only as untyped design metadata; Noor's area and planned completion are also
metadata only.  The immutable private capture bundle is pinned in place and
raw publisher bytes are never redistributed.
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
from typing import Any, Mapping, Sequence

from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "regional-official-an-khanh-oran-noor-prepublication-2026-07-22-v1"
PROSPECTIVE_ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID

AN_KHANH_SOURCE_FILENAME = (
    "curated-official-2026-07-22-viettel-an-khanh-current-build.json"
)
ORAN_SOURCE_FILENAME = (
    "curated-official-2026-07-22-oran-ai-data-center-current-build.json"
)
NOOR_SOURCE_FILENAME = (
    "curated-official-2026-07-22-noor-capital-gardens-current-build.json"
)
SOURCE_FILENAMES = (
    AN_KHANH_SOURCE_FILENAME,
    ORAN_SOURCE_FILENAME,
    NOOR_SOURCE_FILENAME,
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

CAPTURE_ORIGIN = Path("/Users/kian/.Trash/dc-regional-gap.Q63EWa")
CAPTURE_FILE_COUNT = 9
CAPTURE_TOTAL_BYTES = 638_042
CAPTURE_TREE_SHA256 = "ddbc99ff381e3cfec2e7a660933df7c64516f634d68e5c6879b7fec7d72ebcc6"
CAPTURE_FILE_PINS: Mapping[str, tuple[int, str]] = {
    "ankhanh.body": (
        343_794,
        "e17e5999c45a2341f0aa7986b94a57ab0d05a82615b64e55e353273ccbda63a0",
    ),
    "ankhanh.headers": (
        2_379,
        "e0787eb6bde85e4cde8448fae8661dbd599143bc0fb77c84155d7bee4c75efb5",
    ),
    "bolivia.headers": (
        0,
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    ),
    "noor.body": (
        35_951,
        "809b7b91729c0535105611ce9206678188ffe9bd3281210b04bdc02d7b9be920",
    ),
    "noor.headers": (
        444,
        "30c44e549751c08d551f2a90df5186eb46d8c62298238d25bc8a4556cb79fca5",
    ),
    "oran_mpt.body": (
        177_426,
        "fc754b5bd44cd345b52f09bdbfb0a8716b947e0c5247a0dec46b1453add64c21",
    ),
    "oran_mpt.headers": (
        1_346,
        "340b92ccca146ba3e837d0d55025f9a24af207be45c6ff5761dd3b5255c87e16",
    ),
    "oran_radio.body": (
        76_195,
        "6c543908dfe5ab8517178cee4a8745581bbff916aaa5733f4c58c072d4bda204",
    ),
    "oran_radio.headers": (
        507,
        "655a13b638019a7fd92bc09ee2da370a4bfee07710dd94ff5f2d22ce79a59999",
    ),
}

BOLIVIA_URL = (
    "https://www.fiscalia.gob.bo/comunicacion/noticias/"
    "fiscal-general-da-inicio-a-la-construccion-de-una-moderna-"
    "infraestructura-del-data-center-de-clase-mundial-que-transformara-"
    "la-justicia-boliviana"
)

CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))


@dataclass(frozen=True)
class Capture:
    capture_id: str
    stem: str
    requested_url: str
    effective_url: str
    publisher: str
    evidence_kind: str
    published_at: str | None
    retrieved_at: str
    response_date_header: str
    content_type: str
    claim_use: str


CAPTURES = (
    Capture(
        "ankhanh",
        "ankhanh",
        "https://baochinhphu.vn/viettel-dau-tu-1-ty-usd-khoi-cong-2-"
        "cong-trinh-trong-diem-quoc-gia-102250819102551656.htm",
        "https://baochinhphu.vn/viettel-dau-tu-1-ty-usd-khoi-cong-2-"
        "cong-trinh-trong-diem-quoc-gia-102250819102551656.htm",
        "Government Portal of Vietnam",
        "government_record",
        "2025-08-19",
        "2026-07-22T04:21:05Z",
        "2026-07-22T04:21:05Z",
        "text/html; charset=utf-8",
        "normalized_identity_locality_and_construction_start",
    ),
    Capture(
        "oran_mpt",
        "oran_mpt",
        "https://www.mpt.gov.dz/working-visit-to-oran-reinforcing-digital-"
        "infrastructures-and-supporting-digital-economy/",
        "https://www.mpt.gov.dz/working-visit-to-oran-reinforcing-digital-"
        "infrastructures-and-supporting-digital-economy/",
        "Algeria Ministry of Post and Telecommunications",
        "government_record",
        "2025-03-17",
        "2026-07-22T04:21:06Z",
        "2026-07-22T04:21:05Z",
        "text/html; charset=UTF-8",
        "identity_and_same_event_corroboration_only",
    ),
    Capture(
        "oran_radio",
        "oran_radio",
        "https://news.radioalgerie.dz/ar/node/61572",
        "https://news.radioalgerie.dz/ar/node/61572",
        "Algerian Radio",
        "government_record",
        "2025-03-16",
        "2026-07-22T04:21:06Z",
        "2026-07-22T04:13:59Z",
        "text/html; charset=UTF-8",
        "normalized_locality_and_cornerstone_observation",
    ),
    Capture(
        "noor",
        "noor",
        "https://www.square.com.eg/all-projects/noor-data-center",
        "https://www.square.com.eg/all-projects/noor-data-center",
        "Square Engineering",
        "company_disclosure",
        None,
        "2026-07-22T04:21:05Z",
        "2026-07-22T04:21:05Z",
        "text/html; charset=utf-8",
        "retrieval_date_contractor_status_and_roles",
    ),
)
CAPTURE_BY_ID = {capture.capture_id: capture for capture in CAPTURES}

AN_KHANH_CAMPUS_KEY = "curated:viettel-an-khanh-data-center-campus"
AN_KHANH_PROJECT_KEY = f"{AN_KHANH_CAMPUS_KEY}:current-build"
ORAN_CAMPUS_KEY = "curated:oran-ai-data-center-campus"
ORAN_PROJECT_KEY = f"{ORAN_CAMPUS_KEY}:current-build"
NOOR_CAMPUS_KEY = "curated:noor-capital-gardens-data-center"
NOOR_PROJECT_KEY = f"{NOOR_CAMPUS_KEY}:current-build"

AN_KHANH_EVIDENCE_KEY = (
    "vietnam-government-portal-viettel-an-khanh-groundbreaking-"
    "2025-08-19-captured-2026-07-22"
)
ORAN_MPT_EVIDENCE_KEY = (
    "algeria-mpt-oran-ai-data-center-cornerstone-2025-03-17-captured-2026-07-22"
)
ORAN_RADIO_EVIDENCE_KEY = (
    "algerian-radio-oran-ai-data-center-cornerstone-2025-03-16-captured-2026-07-22"
)
NOOR_EVIDENCE_KEY = "square-engineering-noor-data-center-ongoing-captured-2026-07-22"


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
    headers = CAPTURE_FILE_PINS[f"{capture.stem}.headers"]
    return {
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture.capture_id,
        "capture_method": (
            "credential_free_curl_http1_1_location_compressed_fail_with_body_"
            "max_time_50_retry_1_desktop_user_agent"
        ),
        "requested_url": capture.requested_url,
        "effective_url": capture.effective_url,
        "request_credentials_supplied": False,
        "http_status": 200,
        "response_date_header": capture.response_date_header,
        "content_type": capture.content_type,
        "content_hash_scope": (
            f"SHA-256 of the exact {body[0]}-byte content-decoded public response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_headers_bytes": headers[0],
        "capture_headers_sha256": headers[1],
        "raw_capture_redistributed": False,
        "rights_scope": (
            "Compact factual extraction from all-rights-reserved official bytes; "
            "raw bodies, headers, scripts, and publisher media are not redistributed."
        ),
        "spatial_guardrail": (
            "No publisher image, satellite image, aerial image, computer vision, "
            "map widget, geocoder, address point, analyst coordinate, parcel, roof, "
            "footprint, or inferred centroid contributes."
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
        "retrieved_at": capture.retrieved_at,
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
    country: str,
    address: str,
    roles: Mapping[str, Sequence[str]],
    evidence_key: str,
    as_of_date: str,
    confidence: float,
) -> dict[str, Any]:
    return {
        "stable_key": stable_key,
        "name": name,
        "country": country,
        "address": address,
        "roles": {key: list(values) for key, values in roles.items()},
        "coordinates": None,
        "geometry": None,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": "authoritative_locality",
        "confidence": confidence,
    }


def _an_khanh_document() -> dict[str, Any]:
    evidence = _evidence(
        key=AN_KHANH_EVIDENCE_KEY,
        capture_id="ankhanh",
        title=(
            "Viettel breaks ground on An Khanh Data Center and a national "
            "research and development center"
        ),
        excerpt=(
            "The Government Portal of Vietnam reports Viettel's groundbreaking "
            "for the An Khanh Data Center in An Khanh Commune, Hanoi."
        ),
        source_family="vietnam_government_portal_news",
        metadata={
            "identity_and_locality_as_reported": (
                "An Khanh Data Center, An Khanh Commune, Hanoi"
            ),
            "physical_status_as_reported": "Viettel officially broke ground.",
            "normalized_lifecycle": "under_construction",
            "developer_as_reported": "Viettel",
            "site_area_metadata_only": {
                "value": 1.9,
                "unit": "hectares",
                "normalized_spatial_row_created": False,
            },
            "design_power_not_normalized": {
                "value": 60,
                "unit": "MW",
                "source_wording": "design capacity",
                "typing": "untyped_design_metadata_only",
                "capacity_row_created": False,
                "not_asserted_as": [
                    "it_power",
                    "grid_power",
                    "utility_power",
                    "current_power",
                    "operational_power",
                    "energy_consumption",
                ],
            },
            "schedule_metadata_only": {
                "phase_1_expected_operation": "Q2 2026",
                "hyperscale_upgrade_target": "2030",
                "completion_or_operation_claim_created": False,
            },
            "classification_metadata_only": {
                "design_standard_as_reported": "Uptime Tier III",
                "future_uses_as_reported": (
                    "government, Ministry of Defense, large-enterprise, and AI uses"
                ),
                "facility_type_row_created": False,
                "workload_row_created": False,
                "customer_or_user_role_created": False,
            },
            "energy_guardrail": (
                "The source supplies no measured or forecast annual energy, grid "
                "draw, PUE, renewable share, or other normalized energy metric."
            ),
        },
    )
    roles = {"developer": ["Viettel"]}
    return {
        "schema_version": "1.1",
        "evidence": [evidence],
        "campus": _entity(
            stable_key=AN_KHANH_CAMPUS_KEY,
            name="Viettel An Khanh Data Center Campus",
            country="Vietnam",
            address="An Khanh Commune, Hanoi, Vietnam",
            roles=roles,
            evidence_key=AN_KHANH_EVIDENCE_KEY,
            as_of_date="2025-08-19",
            confidence=0.99,
        ),
        "project": _entity(
            stable_key=AN_KHANH_PROJECT_KEY,
            name="Viettel An Khanh Data Center Current Build",
            country="Vietnam",
            address="An Khanh Commune, Hanoi, Vietnam",
            roles=roles,
            evidence_key=AN_KHANH_EVIDENCE_KEY,
            as_of_date="2025-08-19",
            confidence=0.99,
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": AN_KHANH_EVIDENCE_KEY,
                "as_of_date": "2025-08-19",
                "method": "authoritative_construction_start",
                "confidence": 0.99,
            }
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _oran_document() -> dict[str, Any]:
    ministry = _evidence(
        key=ORAN_MPT_EVIDENCE_KEY,
        capture_id="oran_mpt",
        title=(
            "Working visit to Oran: reinforcing digital infrastructures and "
            "supporting the digital economy"
        ),
        excerpt=(
            "Algeria's Ministry reports that ministers laid the cornerstone for "
            "an advanced data center and AI computing center in Oran."
        ),
        source_family="algeria_mpt_official_news",
        metadata={
            "event_date_as_reported": "2025-03-16",
            "identity_as_reported": (
                "advanced data center and artificial-intelligence computing center"
            ),
            "same_event_corroboration_only": True,
            "classification_guardrail": (
                "Cloud and AI solution language is descriptive context only; no "
                "facility-type, operating-model, workload, tenant, user, or active-"
                "compute observation is normalized."
            ),
            "energy_guardrail": (
                "Rational energy use and sustainable-technology language is design "
                "context, not consumption, annual energy, grid draw, PUE, renewable "
                "share, or a measured efficiency observation."
            ),
            "role_guardrail": (
                "The visiting ministries and ministers are not normalized as owner, "
                "operator, developer, investor, or user roles."
            ),
        },
    )
    radio = _evidence(
        key=ORAN_RADIO_EVIDENCE_KEY,
        capture_id="oran_radio",
        title="Construction begins on an artificial-intelligence data center in Oran",
        excerpt=(
            "Algerian Radio reports the cornerstone event for the data center in "
            "Akid Lotfi district, Oran."
        ),
        source_family="algerian_radio_official_news",
        metadata={
            "identity_and_locality_as_reported": (
                "data center designated for artificial intelligence, Akid Lotfi "
                "district, Oran"
            ),
            "physical_status_as_reported": "The cornerstone was laid.",
            "normalized_lifecycle": "under_construction",
            "stage_guardrail": (
                "The cornerstone event supports only generic under_construction. "
                "It does not establish site preparation, civil works, foundations, "
                "shell, MEP, commissioning, energization, or operation."
            ),
            "capacity_guardrail": (
                "No rack count, MW value, PUE, energy-consumption value, or capacity "
                "metric is normalized."
            ),
            "coordinate_guardrail": (
                "Akid Lotfi district is retained only as official locality text."
            ),
        },
    )
    return {
        "schema_version": "1.1",
        "evidence": [ministry, radio],
        "campus": _entity(
            stable_key=ORAN_CAMPUS_KEY,
            name="Oran Data Center and AI Computing Center Campus",
            country="Algeria",
            address="Akid Lotfi District, Oran, Algeria",
            roles={},
            evidence_key=ORAN_RADIO_EVIDENCE_KEY,
            as_of_date="2025-03-16",
            confidence=0.99,
        ),
        "project": _entity(
            stable_key=ORAN_PROJECT_KEY,
            name="Oran Data Center and AI Computing Center Current Build",
            country="Algeria",
            address="Akid Lotfi District, Oran, Algeria",
            roles={},
            evidence_key=ORAN_RADIO_EVIDENCE_KEY,
            as_of_date="2025-03-16",
            confidence=0.99,
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": ORAN_RADIO_EVIDENCE_KEY,
                "as_of_date": "2025-03-16",
                "method": "authoritative_construction_start",
                "confidence": 0.99,
            }
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _noor_document() -> dict[str, Any]:
    evidence = _evidence(
        key=NOOR_EVIDENCE_KEY,
        capture_id="noor",
        title="Noor Data Center",
        excerpt=(
            "Square Engineering's current project page lists Noor Data Center at "
            "Noor - Capital Gardens with project status Ongoing."
        ),
        source_family="square_engineering_project_pages",
        metadata={
            "retrieval_date_status_classification": {
                "publisher_field": "PROJECT STATUS",
                "publisher_value": "Ongoing",
                "retrieved_at": "2026-07-22T04:21:05Z",
                "normalized_lifecycle": "under_construction",
                "scope": "contractor_current_page_classification_only",
            },
            "roles_as_reported": {
                "owner": "Arabian Company for Projects & Urban Development",
                "contractor": "Square Engineering",
                "consultant_metadata_only": "SHAKER Consultancy Group",
            },
            "scope_as_reported": "Full Construction & Fit Out",
            "physical_stage_guardrail": (
                "The scope and Ongoing label do not establish site preparation, "
                "civil works, foundations, shell, fit-out progress, MEP, "
                "commissioning, energization, or operation."
            ),
            "area_metadata_only": {
                "value": 44_220,
                "unit": "square_metres",
                "footprint_or_geometry_claim_created": False,
            },
            "schedule_metadata_only": {
                "planned_completion_year": 2026,
                "completion_or_operation_claim_created": False,
            },
            "metric_and_classification_guardrail": (
                "The page supplies no MW, rack, energy, PUE, facility-type, "
                "operating-model, workload, tenant, user, or active-compute row."
            ),
        },
    )
    owner = "Arabian Company for Projects & Urban Development"
    return {
        "schema_version": "1.1",
        "evidence": [evidence],
        "campus": _entity(
            stable_key=NOOR_CAMPUS_KEY,
            name="Noor Data Center Campus",
            country="Egypt",
            address="Noor - Capital Gardens, Egypt",
            roles={"owner": [owner]},
            evidence_key=NOOR_EVIDENCE_KEY,
            as_of_date="2026-07-22",
            confidence=0.95,
        ),
        "project": _entity(
            stable_key=NOOR_PROJECT_KEY,
            name="Noor Data Center Current Build",
            country="Egypt",
            address="Noor - Capital Gardens, Egypt",
            roles={"owner": [owner], "contractor": ["Square Engineering"]},
            evidence_key=NOOR_EVIDENCE_KEY,
            as_of_date="2026-07-22",
            confidence=0.95,
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": NOOR_EVIDENCE_KEY,
                "as_of_date": "2026-07-22",
                "method": "authoritative_physical_status_update",
                "confidence": 0.90,
            }
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _validate_document_contract(
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    if tuple(documents) != SOURCE_FILENAMES:
        raise RuntimeError("regional source document inventory differs")
    if sum(len(document["evidence"]) for document in documents.values()) != 4:
        raise RuntimeError("regional evidence count differs")
    if sum(len(document["lifecycle"]) for document in documents.values()) != 3:
        raise RuntimeError("regional lifecycle count differs")
    for document in documents.values():
        if (
            document["schema_version"] != "1.1"
            or document["operating_models"]
            or document["workloads"]
            or document["capacities"]
        ):
            raise RuntimeError(
                "regional normalized classification/metric boundary differs"
            )
        for entity in ("campus", "project"):
            if (
                document[entity]["coordinates"] is not None
                or document[entity]["geometry"] is not None
            ):
                raise RuntimeError("regional spatial boundary differs")

    an_khanh = documents[AN_KHANH_SOURCE_FILENAME]
    design = an_khanh["evidence"][0]["metadata"]["design_power_not_normalized"]
    if (
        design
        != {
            "value": 60,
            "unit": "MW",
            "source_wording": "design capacity",
            "typing": "untyped_design_metadata_only",
            "capacity_row_created": False,
            "not_asserted_as": [
                "it_power",
                "grid_power",
                "utility_power",
                "current_power",
                "operational_power",
                "energy_consumption",
            ],
        }
        or an_khanh["lifecycle"][0]["method"] != "authoritative_construction_start"
    ):
        raise RuntimeError("An Khanh design-power or construction boundary differs")

    oran = documents[ORAN_SOURCE_FILENAME]
    if (
        oran["campus"]["roles"]
        or oran["project"]["roles"]
        or oran["lifecycle"][0]["value"] != "under_construction"
        or oran["lifecycle"][0]["evidence_key"] != ORAN_RADIO_EVIDENCE_KEY
    ):
        raise RuntimeError("Oran cornerstone/role boundary differs")

    noor = documents[NOOR_SOURCE_FILENAME]
    status = noor["evidence"][0]["metadata"]["retrieval_date_status_classification"]
    if (
        status["publisher_value"] != "Ongoing"
        or status["scope"] != "contractor_current_page_classification_only"
        or noor["lifecycle"][0]["as_of_date"] != "2026-07-22"
        or noor["lifecycle"][0]["method"] != "authoritative_physical_status_update"
    ):
        raise RuntimeError("Noor retrieval-date status boundary differs")


def expected_source_documents() -> dict[str, dict[str, Any]]:
    documents = {
        AN_KHANH_SOURCE_FILENAME: _an_khanh_document(),
        ORAN_SOURCE_FILENAME: _oran_document(),
        NOOR_SOURCE_FILENAME: _noor_document(),
    }
    _validate_document_contract(documents)
    return documents


def _validate_capture_directory(directory: Path = CAPTURE_ORIGIN) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("private regional capture directory is missing or unsafe")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555:
        raise RuntimeError("private regional capture directory is not frozen")
    entries = {path.name: path for path in directory.iterdir()}
    if set(entries) != set(CAPTURE_FILE_PINS):
        raise RuntimeError("private regional capture inventory differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(entries[name], pin)
        if stat.S_IMODE(entries[name].stat().st_mode) != 0o444:
            raise RuntimeError(f"private regional capture is not frozen: {name}")
    if sum(pin[0] for pin in CAPTURE_FILE_PINS.values()) != CAPTURE_TOTAL_BYTES:
        raise RuntimeError("private regional capture byte total differs")
    if tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise RuntimeError("private regional capture tree differs")


def _v95_witness() -> dict[str, Any]:
    _pin(V95_DEFINITION, V95_DEFINITION_PIN)
    _pin(V95_ENTITIES, V95_ENTITIES_PIN)
    _pin(V95_EVIDENCE, V95_EVIDENCE_PIN)
    _pin(V95_MANIFEST, V95_MANIFEST_PIN)

    definition = json.loads(V95_DEFINITION.read_text(encoding="utf-8"))
    selected = definition.get("curated_inputs")
    if (
        definition.get("release_id") != "2026-07-22-open-seed-v95"
        or not isinstance(selected, list)
        or len(selected) != 507
        or definition.get("expected_summary", {}).get("entities_total") != 1_029
        or definition.get("expected_release", {}).get("evidence_records") != 678
        or definition.get("expected_release", {}).get("recorded_at")
        != "2026-07-22T04:21:58Z"
    ):
        raise RuntimeError("v95 definition contract differs")

    selected_paths: set[str] = set()
    existing_evidence_keys: set[str] = set()
    for row in selected:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise RuntimeError("v95 selected input row differs")
        relative = row["path"]
        if relative in selected_paths:
            raise RuntimeError(f"v95 selected input path duplicated: {relative}")
        selected_paths.add(relative)
        path = ROOT / relative
        if path.is_symlink() or not path.is_file() or _sha256(path) != row["sha256"]:
            raise RuntimeError(f"v95 selected input pin differs: {relative}")
        document = json.loads(path.read_text(encoding="utf-8"))
        evidence = document.get("evidence")
        if not isinstance(evidence, list):
            raise RuntimeError(f"v95 selected evidence inventory differs: {relative}")
        for item in evidence:
            key = item.get("key") if isinstance(item, dict) else None
            if not isinstance(key, str) or not key:
                raise RuntimeError(f"v95 selected evidence key differs: {relative}")
            existing_evidence_keys.add(key)

    with V95_ENTITIES.open(encoding="utf-8", newline="") as stream:
        entity_rows = list(csv.DictReader(stream))
    with V95_EVIDENCE.open(encoding="utf-8", newline="") as stream:
        evidence_rows = list(csv.DictReader(stream))
    manifest = json.loads(V95_MANIFEST.read_text(encoding="utf-8"))
    if (
        len(entity_rows) != 1_029
        or len(evidence_rows) != 678
        or manifest.get("entities") != 1_029
        or manifest.get("evidence_records") != 678
        or manifest.get("recorded_at") != "2026-07-22T04:21:58Z"
    ):
        raise RuntimeError("v95 release row contract differs")

    existing_stable_keys = {row["stable_key"] for row in entity_rows}
    planned_stable_keys = {
        AN_KHANH_CAMPUS_KEY,
        AN_KHANH_PROJECT_KEY,
        ORAN_CAMPUS_KEY,
        ORAN_PROJECT_KEY,
        NOOR_CAMPUS_KEY,
        NOOR_PROJECT_KEY,
    }
    planned_evidence_keys = {
        AN_KHANH_EVIDENCE_KEY,
        ORAN_MPT_EVIDENCE_KEY,
        ORAN_RADIO_EVIDENCE_KEY,
        NOOR_EVIDENCE_KEY,
    }
    planned_paths = {f"sources/{name}" for name in SOURCE_FILENAMES}
    stable_collisions = sorted(planned_stable_keys & existing_stable_keys)
    evidence_collisions = sorted(planned_evidence_keys & existing_evidence_keys)
    selected_path_collisions = sorted(planned_paths & selected_paths)
    if stable_collisions or evidence_collisions or selected_path_collisions:
        raise RuntimeError(
            "regional v95 collision witness differs: "
            f"{stable_collisions!r}, {evidence_collisions!r}, "
            f"{selected_path_collisions!r}"
        )
    return {
        "v95_release_id": "2026-07-22-open-seed-v95",
        "v95_recorded_at": "2026-07-22T04:21:58Z",
        "v95_selected_input_count": len(selected),
        "v95_entity_count": len(entity_rows),
        "v95_public_evidence_count": len(evidence_rows),
        "v95_pins": {
            "definition": {
                "path": "sources/open-seed-2026-07-22-v95.json",
                "bytes": V95_DEFINITION_PIN[0],
                "sha256": V95_DEFINITION_PIN[1],
            },
            "entities": {
                "path": "releases/2026-07-22-open-seed-v95/entities.csv",
                "bytes": V95_ENTITIES_PIN[0],
                "sha256": V95_ENTITIES_PIN[1],
            },
            "evidence": {
                "path": "releases/2026-07-22-open-seed-v95/evidence.csv",
                "bytes": V95_EVIDENCE_PIN[0],
                "sha256": V95_EVIDENCE_PIN[1],
            },
            "manifest": {
                "path": "releases/2026-07-22-open-seed-v95/manifest.json",
                "bytes": V95_MANIFEST_PIN[0],
                "sha256": V95_MANIFEST_PIN[1],
            },
        },
        "planned_stable_keys": sorted(planned_stable_keys),
        "planned_evidence_keys": sorted(planned_evidence_keys),
        "planned_final_source_paths": sorted(planned_paths),
        "planned_stable_key_collisions": stable_collisions,
        "planned_evidence_key_collisions": evidence_collisions,
        "planned_selected_source_path_collisions": selected_path_collisions,
    }


def _source_records(
    documents: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    dispositions = {
        AN_KHANH_SOURCE_FILENAME: "prepublication_official_groundbreaking",
        ORAN_SOURCE_FILENAME: "prepublication_official_cornerstone",
        NOOR_SOURCE_FILENAME: (
            "prepublication_retrieval_date_contractor_status_classification"
        ),
    }
    countries = {
        AN_KHANH_SOURCE_FILENAME: "Vietnam",
        ORAN_SOURCE_FILENAME: "Algeria",
        NOOR_SOURCE_FILENAME: "Egypt",
    }
    rows = []
    for name in SOURCE_FILENAMES:
        document = documents[name]
        payload = _canonical(document)
        rows.append(
            {
                "path": f"prospective-sources/{name}",
                "bytes": len(payload),
                "sha256": _sha256_bytes(payload),
                "schema_version": "1.1",
                "country": countries[name],
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
                "disposition": dispositions[name],
                "published": False,
                "seeded": False,
            }
        )
    return rows


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-prepublication-assessment-v1",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "candidate_count": 4,
        "governed_source_candidate_count": 3,
        "review_only_count": 1,
        "regional_completeness_claimed": False,
        "candidates": [
            {
                "candidate_id": "viettel-an-khanh-data-center-current-build",
                "decision": "governed_prepublication_official_groundbreaking",
                "source_paths": [f"prospective-sources/{AN_KHANH_SOURCE_FILENAME}"],
                "campus_stable_key": AN_KHANH_CAMPUS_KEY,
                "project_stable_key": AN_KHANH_PROJECT_KEY,
                "lifecycle": "under_construction",
                "as_of_date": "2025-08-19",
                "design_60_mw_normalized": False,
                "facility_type_claim_created": False,
                "workload_claim_created": False,
                "energy_claim_created": False,
                "coordinate_claim_created": False,
                "geometry_claim_created": False,
            },
            {
                "candidate_id": "oran-data-center-ai-computing-center-current-build",
                "decision": "governed_prepublication_cornerstone_observation",
                "source_paths": [f"prospective-sources/{ORAN_SOURCE_FILENAME}"],
                "campus_stable_key": ORAN_CAMPUS_KEY,
                "project_stable_key": ORAN_PROJECT_KEY,
                "lifecycle": "under_construction",
                "as_of_date": "2025-03-16",
                "specific_physical_stage_created": False,
                "facility_type_claim_created": False,
                "workload_claim_created": False,
                "capacity_claim_created": False,
                "energy_claim_created": False,
                "coordinate_claim_created": False,
                "geometry_claim_created": False,
            },
            {
                "candidate_id": "noor-capital-gardens-data-center-current-build",
                "decision": (
                    "governed_prepublication_retrieval_date_contractor_status"
                ),
                "source_paths": [f"prospective-sources/{NOOR_SOURCE_FILENAME}"],
                "campus_stable_key": NOOR_CAMPUS_KEY,
                "project_stable_key": NOOR_PROJECT_KEY,
                "lifecycle": "under_construction",
                "as_of_date": "2026-07-22",
                "status_basis": "contractor_current_page_ongoing_as_retrieved",
                "specific_physical_stage_created": False,
                "planned_completion_claim_created": False,
                "facility_type_claim_created": False,
                "workload_claim_created": False,
                "capacity_claim_created": False,
                "coordinate_claim_created": False,
                "geometry_claim_created": False,
            },
            {
                "candidate_id": "bolivia-fiscalia-data-center",
                "decision": "review_only_unhashable_official_server_timeout",
                "requested_url": BOLIVIA_URL,
                "source_paths": [],
                "stable_key_created": False,
                "lifecycle_claim_created": False,
                "evidence_record_created": False,
                "capacity_claim_created": False,
                "facility_type_claim_created": False,
                "coordinate_claim_created": False,
                "timeout_capture": {
                    "capture_method": (
                        "credential_free_curl_http1_1_location_compressed_"
                        "fail_with_body_max_time_50_retry_1_desktop_user_agent"
                    ),
                    "configured_attempts": 2,
                    "completed_timeout_attempts": 2,
                    "max_time_seconds_per_attempt": 50,
                    "http_status": None,
                    "response_header_bytes": 0,
                    "response_body_bytes": 0,
                    "headers_path": "bolivia.headers",
                    "headers_sha256": CAPTURE_FILE_PINS["bolivia.headers"][1],
                    "body_path": None,
                    "content_hash": None,
                    "outcome": "no_http_response_before_timeout_on_either_attempt",
                },
                "reason": (
                    "The controlled request and its configured retry both timed "
                    "out before any HTTP response headers or body. No hash-bound "
                    "official source exists, so no normalized record is emitted."
                ),
            },
        ],
    }


def _retrieval_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "controlled_request_target_count": 5,
        "successful_http_200_body_captures": len(CAPTURES),
        "official_server_timeout_targets": 1,
        "normalized_claim_capture_count": len(CAPTURES),
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
                "retrieved_at": capture.retrieved_at,
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
        "failed_capture": {
            "capture_id": "bolivia_fiscalia",
            "requested_url": BOLIVIA_URL,
            "configured_attempts": 2,
            "completed_timeout_attempts": 2,
            "max_time_seconds_per_attempt": 50,
            "http_status": None,
            "body": None,
            "headers": {
                "path": "bolivia.headers",
                "bytes": CAPTURE_FILE_PINS["bolivia.headers"][0],
                "sha256": CAPTURE_FILE_PINS["bolivia.headers"][1],
            },
            "normalized_claim_use": False,
            "decision": "review_only_unhashable_official_server_timeout",
        },
        "complete_private_file_inventory": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in sorted(CAPTURE_FILE_PINS.items())
        ],
    }


def _artifact_documents(
    recorded_at: str,
    documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    source_records = _source_records(documents)
    assessment = _candidate_assessment(recorded_at)
    witness = _v95_witness()
    readme = f"""# Regional official-source tranche — prepublication only

This governed candidate artifact was built at {recorded_at} and was not published. It contains private staged source candidates for Viettel An Khanh Data Center in Vietnam, the Oran data center and AI computing center in Algeria, and Noor Data Center in Egypt.

The normalized output is six entity snapshots, four evidence records, three generic `under_construction` lifecycle observations, and zero operating-model, workload, facility-type, capacity, energy-consumption, efficiency, coordinate, or geometry rows. An Khanh's 60 MW is source-described design capacity and remains untyped evidence metadata only. Oran's cornerstone supports only generic construction status, not a more specific physical stage. Noor's status is only Square Engineering's current-page `Ongoing` classification as retrieved on 2026-07-22; its 44,220-square-metre area, full-construction-and-fit-out scope, and planned 2026 completion are metadata and do not establish physical stage, completion, commissioning, energization, or operation.

The Bolivia Fiscalía candidate remains review-only and unhashable. A credential-free controlled request with one configured retry produced two timeouts before any response headers or body. The frozen bundle therefore contains only a zero-byte header file for that target; no evidence record, stable key, lifecycle observation, or source candidate is created.

No map, image, satellite, aerial, computer-vision, geocoder, address-point, parcel, roof, footprint, or centroid inference contributes. The builder exposes no publication or promotion function. Source and artifact outputs remain mode-0600 members of mode-0700 private staging directories. The frozen capture bundle remains pinned in Trash with mode-0444 files and a mode-0555 directory. No final source path, source-artifact path, open-seed successor, release, federation, identity, timeline, construction-master, map, coverage, or v96 file is created or changed.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "regional_completeness_claimed": False,
        "source_records": source_records,
        "totals": {
            "candidate_assessments": 4,
            "source_records": 3,
            "governed_prepublication_candidates": 3,
            "review_only_candidates": 1,
            "distinct_campuses_in_source_records": 3,
            "projects": 3,
            "distinct_entity_snapshots": 6,
            "new_entities_against_v95": 6,
            "reused_existing_entities": 0,
            "evidence_records": 4,
            "lifecycle_observations": 3,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
            "energy_consumption_observations": 0,
            "facility_type_observations": 0,
            "coordinate_observations": 0,
            "geometry_observations": 0,
            "satellite_observations": 0,
        },
        "v95_collision_witness": witness,
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
            "v96_files_touched": [],
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
            "Captured official response bodies are treated as all-rights-reserved; "
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
        prefix="regional-prepublication-import-", dir="/private/tmp"
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
            "entities": 6,
            "entity_snapshots": 6,
            "evidence": 4,
            "lifecycle_observations": 3,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
        }
        if counts != expected:
            raise RuntimeError(f"offline import counts differ: {counts!r}")
        return counts


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def _validate_sources(paths: Mapping[str, Path]) -> list[dict[str, Any]]:
    expected = expected_source_documents()
    if set(paths) != set(SOURCE_FILENAMES):
        raise RuntimeError("regional staged source inventory differs")
    for name in SOURCE_FILENAMES:
        path = paths[name]
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"missing or unsafe staged source: {name}")
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise RuntimeError(f"staged source mode differs: {name}")
        if path.read_bytes() != _canonical(expected[name]):
            raise RuntimeError(f"staged source differs: {name}")
    first = _offline_import(paths, "2026-07-22T04:30:00Z")
    second = _offline_import(paths, "2026-07-22T04:30:00Z")
    if first != second:
        raise RuntimeError("regional offline replay differs")
    return _source_records(expected)


def _write_sources(directory: Path, documents: Mapping[str, Mapping[str, Any]]) -> None:
    for name in SOURCE_FILENAMES:
        path = directory / name
        path.write_bytes(_canonical(documents[name]))
        path.chmod(0o600)


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
        "candidate_assessments": 4,
        "curated_source_candidates": 3,
        "review_only_candidates": 1,
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


def _assert_no_publication() -> None:
    final_sources = [SOURCES_ROOT / name for name in SOURCE_FILENAMES]
    collisions = [
        str(path)
        for path in (PROSPECTIVE_ARTIFACT, *final_sources)
        if path.exists() or path.is_symlink()
    ]
    if collisions:
        raise RuntimeError(f"prospective final-path collision: {collisions!r}")


def validate_candidate(
    artifact_stage: Path,
    source_stage: Path,
) -> dict[str, Any]:
    _assert_no_publication()
    _validate_capture_directory()
    witness = _v95_witness()
    if (
        witness["planned_stable_key_collisions"]
        or witness["planned_evidence_key_collisions"]
        or witness["planned_selected_source_path_collisions"]
    ):
        raise RuntimeError("v95 collision gate differs")
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

    documents = expected_source_documents()
    expected_payloads = _artifact_documents(manifest["recorded_at"], documents)
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected_payloads[name]:
            raise RuntimeError(f"candidate artifact content differs: {name}")
    records = _validate_sources(_source_paths(source_stage))
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != records:
        raise RuntimeError("candidate source record pins differ")
    assessment = json.loads(
        entries["candidate-assessment.json"].read_text(encoding="utf-8")
    )
    bolivia = next(
        row
        for row in assessment["candidates"]
        if row["candidate_id"] == "bolivia-fiscalia-data-center"
    )
    if (
        bolivia["source_paths"]
        or bolivia["stable_key_created"]
        or bolivia["lifecycle_claim_created"]
        or bolivia["evidence_record_created"]
        or bolivia["timeout_capture"]["content_hash"] is not None
    ):
        raise RuntimeError("Bolivia review-only boundary differs")
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
    _v95_witness()
    documents = expected_source_documents()
    instant = recorded_at or datetime.now(UTC).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")
    source_stage = Path(
        tempfile.mkdtemp(
            prefix=".regional-official-prepublication-sources.", dir=SOURCES_ROOT
        )
    )
    artifact_stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT)
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
    source_pins = [
        {
            "path": str(prepared.source_stage / name),
            "bytes": (prepared.source_stage / name).stat().st_size,
            "sha256": _sha256(prepared.source_stage / name),
        }
        for name in SOURCE_FILENAMES
    ]
    return {
        "status": "PREPUBLICATION_CANDIDATE_BUILT_NOT_PUBLISHED",
        "recorded_at": prepared.recorded_at,
        "artifact_stage": str(prepared.artifact_stage),
        "artifact_manifest_sha256": _sha256(prepared.artifact_stage / "manifest.json"),
        "artifact_tree_sha256": tree_digest(prepared.artifact_stage),
        "source_stage": str(prepared.source_stage),
        "source_pins": source_pins,
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
