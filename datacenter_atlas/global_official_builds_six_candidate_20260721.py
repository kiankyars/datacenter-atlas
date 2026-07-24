"""Publish a six-candidate official-build assessment and five source records.

The carrier is deliberately independent of open-seed publication.  It stages every
source and artifact byte before the declared recording instant, waits for that
instant, and then performs identity-checked, no-replace promotion with rollback.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import ctypes
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
from typing import Any, Callable, Iterator, Mapping, Sequence

from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "global-official-builds-six-candidate-2026-07-21-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".global-official-builds-six-candidate-20260721.lock"
CAPTURE_ORIGIN = Path("/private/tmp/dc-official-builds-20260721.t7lZRV")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-official-builds-20260721.t7lZRV")

V71_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v71.json"
V71_RELEASE = ROOT / "releases/2026-07-21-open-seed-v71"
V71_MANIFEST = V71_RELEASE / "manifest.json"
V71_ENTITIES = V71_RELEASE / "entities.csv"
V71_PINS = {
    V71_DEFINITION: (
        86_839,
        "f5115fa57f32c8d9451609a662f6b524a15283b8e4fa1d9b65af59430d9e3b38",
    ),
    V71_MANIFEST: (
        12_577,
        "0f8acbce360f763707cb4c51276a0873ee60ec96d9258b1915fa8c76fcf9fa22",
    ),
    V71_ENTITIES: (
        879_464,
        "a8ec778ce2abf5a89a7a9c6a006fa7bef9b8378d820cffcb794a10b195fd82f9",
    ),
}
V71_TREE_SHA256 = "7636964f1d640268ed8627d5f18d800a43a35a4d7dbc1f62b8386e60bd1fa720"

SOURCE_FILENAMES = (
    "curated-official-2026-07-21-lvrtc-pozitrons-kurzeme-current-build.json",
    "curated-official-2026-07-21-akashi-astana-phase-1-current-build.json",
    "curated-official-2026-07-21-bichuten-chovar-current-build.json",
    "curated-official-2026-07-21-icatec-ica-current-build.json",
    "curated-official-2026-07-21-cmc-creative-space-hanoi-phase-2-historical.json",
)

CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))


class OfficialBuildsError(RuntimeError):
    """Raised when evidence or publication invariants fail closed."""


CAPTURE_SPECS: dict[str, dict[str, Any]] = {
    "lvrtc_progress": {
        "requested_url": "https://www.lvrtc.lv/projekti/datu-centrs-pozitrons/projekta-aktualitate/",
        "retrieved_at": "2026-07-21T12:22:03Z",
        "response_http_date": "2026-07-21T12:22:00Z",
        "http_status": 200,
        "http_version": "1.1",
        "content_type": "text/html; charset=UTF-8",
        "content_encoding_as_received": None,
        "wire_download_bytes": 92_280,
        "header_count": 19,
        "body": (
            92_280,
            "4d00948cfc2a582004e38bcee3425c4ea5da5ce8dc31d3da326e6ba0a8b9d9e1",
        ),
        "headers": (
            1_054,
            "58e6619c9598b904d0d189d1a787d4b3dbbb57d2b0032206010831207c32f60a",
        ),
        "writeout": (
            11_387,
            "d1c224b359baf8aa4dc86f7a2425e6354171666ec0329fa671b2a859afb8167e",
        ),
        "evidence_keys": [
            "latvia-lvrtc-pozitrons-progress-through-2026-06-30-captured-2026-07-21"
        ],
    },
    "lvrtc_project": {
        "requested_url": "https://www.lvrtc.lv/projekti/datu-centrs-pozitrons/",
        "retrieved_at": "2026-07-21T12:22:06Z",
        "response_http_date": "2026-07-21T12:22:03Z",
        "http_status": 200,
        "http_version": "1.1",
        "content_type": "text/html; charset=UTF-8",
        "content_encoding_as_received": None,
        "wire_download_bytes": 139_225,
        "header_count": 19,
        "body": (
            139_225,
            "3f565f850e22560367c4b49384ed730ec8654d1cc2cf122c5bb2a1c40dc76578",
        ),
        "headers": (
            1_054,
            "f6bad45ec5fd8d6ae6e9d3965d7db7729e993fd1e9d5a3a336effe0e721da21c",
        ),
        "writeout": (
            11_303,
            "2438ddcb87ee9c2c36120ea0ee27bcd2514eb502e5056e89df6c8a9b3e960b26",
        ),
        "evidence_keys": [
            "latvia-lvrtc-pozitrons-project-page-captured-2026-07-21"
        ],
    },
    "akashi_progress": {
        "requested_url": "https://akashi.cloud/construction-progress/",
        "retrieved_at": "2026-07-21T12:22:07Z",
        "response_http_date": "2026-07-21T12:22:06Z",
        "http_status": 200,
        "http_version": "2",
        "content_type": "text/html; charset=utf-8",
        "content_encoding_as_received": "gzip",
        "wire_download_bytes": 16_502,
        "header_count": 8,
        "body": (
            65_761,
            "a2f3f281a66151c90b6a6ea0a089e9cab9361b586f60cde06febb1d49fee6b9f",
        ),
        "headers": (
            263,
            "7bebae05b438c08d055a9f5a384accabfed678ee56a4b51bf1324f05b48fa9ad",
        ),
        "writeout": (
            17_047,
            "6644e30061492af354b5f04bb8310686a4764b5345dc191a522cc6aec3c8b3b6",
        ),
        "evidence_keys": [
            "kazakhstan-akashi-astana-current-progress-captured-2026-07-21"
        ],
    },
    "akashi_about": {
        "requested_url": "https://akashi.cloud/about/",
        "retrieved_at": "2026-07-21T12:22:07Z",
        "response_http_date": "2026-07-21T12:22:07Z",
        "http_status": 200,
        "http_version": "2",
        "content_type": "text/html; charset=utf-8",
        "content_encoding_as_received": "gzip",
        "wire_download_bytes": 17_470,
        "header_count": 8,
        "body": (
            72_118,
            "01e105af2a09a3e96987bccde8d7c7cc68cf6add95ab48c6d9286e4dca5ce774",
        ),
        "headers": (
            263,
            "467e3224fa15b6962bc1545f8dd75b1b11e129ed344b82c2e10b36bbaf823d08",
        ),
        "writeout": (
            16_980,
            "7f952f223f3b395865a5b299aeef7b6dfb9b61161e8f985cb61a64db5d06aa27",
        ),
        "evidence_keys": [
            "kazakhstan-akashi-astana-about-page-captured-2026-07-21"
        ],
    },
    "bichuten_care": {
        "requested_url": "https://www.careratingsnepal.com/upload/CompanyFiles/PR/202604100446_Bichuten_Data_Vault_Private_Limited_-_Bank_Facilities_Ratings_Assigned.pdf",
        "retrieved_at": "2026-07-21T12:22:09Z",
        "response_http_date": "2026-07-21T12:22:02Z",
        "http_status": 200,
        "http_version": "1.1",
        "content_type": "application/pdf",
        "content_encoding_as_received": "gzip",
        "wire_download_bytes": 131_858,
        "header_count": 10,
        "body": (
            141_835,
            "45e601838c265494e5816f4b41d5adb943b565f075ca6246d9b77baf85d50b73",
        ),
        "headers": (
            511,
            "d4dc4c241f29bc27fcd1bc2349eecc3a21bc74ae54ae7068e277c0ee8263215b",
        ),
        "writeout": (
            24_682,
            "f8af0d91ce11583a5d8b8b18d4b4e73379afc363a47683592239f4fb554ae941",
        ),
        "evidence_keys": [
            "nepal-bichuten-chovar-care-rating-april-2026-captured-2026-07-21"
        ],
    },
    "icatec_february": {
        "requested_url": "https://www.gob.pe/institucion/regionica/noticias/1369876-megaproyecto-icatec-registra-progresos-en-su-etapa-estructural",
        "retrieved_at": "2026-07-21T12:22:10Z",
        "response_http_date": "2026-07-21T12:22:10Z",
        "http_status": 200,
        "http_version": "1.1",
        "content_type": "text/html; charset=utf-8",
        "content_encoding_as_received": "gzip",
        "wire_download_bytes": 9_381,
        "header_count": 23,
        "body": (
            33_113,
            "00979a2a34878605fd682a2cde8f925f654bf6cbf18dcb6597df0723d176a0fb",
        ),
        "headers": (
            1_238,
            "d31579ca02354f747591ff27a6db83fbc0a1e49cd6e935efd0347d672c5a95bf",
        ),
        "writeout": (
            14_825,
            "e986f787c1b4122bac698c81148b50ce5605bb3780add08b7f31ac1c8931300a",
        ),
        "evidence_keys": [
            "peru-icatec-structural-progress-2026-02-12-captured-2026-07-21"
        ],
    },
    "icatec_april": {
        "requested_url": "https://www.gob.pe/institucion/regionica/noticias/1411013-nota-de-prensa-n-044-2026-avanza-el-proyecto-icatec-el-futuro-digital-de-ica-ya-esta-en-construccion",
        "retrieved_at": "2026-07-21T12:22:11Z",
        "response_http_date": "2026-07-21T12:22:11Z",
        "http_status": 200,
        "http_version": "1.1",
        "content_type": "text/html; charset=utf-8",
        "content_encoding_as_received": "gzip",
        "wire_download_bytes": 9_614,
        "header_count": 23,
        "body": (
            34_179,
            "5d21ed8ba6961f819538a0c2dfdef63d6a2a601c97d259c96c4734455952ea9f",
        ),
        "headers": (
            1_238,
            "99d7b7ae02324a8e177b29ce541a6355746e77dd4422647763bfdaeb11622a81",
        ),
        "writeout": (
            14_974,
            "3e59b16fa92360a6646cac0afac35b1779316bdc81cb860e1fd17773acf29f74",
        ),
        "evidence_keys": [
            "peru-icatec-construction-progress-2026-04-07-captured-2026-07-21"
        ],
    },
    "cmc_annual_report": {
        "requested_url": "https://cdn.cmc.com.vn/img/posts/files/20250718%20-%20CMG%20-%20Annual%20report%202024%20-%20signed.pdf",
        "retrieved_at": "2026-07-21T12:22:14Z",
        "response_http_date": "2026-07-21T12:22:12Z",
        "http_status": 200,
        "http_version": "1.1",
        "content_type": "application/pdf",
        "content_encoding_as_received": None,
        "wire_download_bytes": 5_259_042,
        "header_count": 11,
        "body": (
            5_259_042,
            "97f94110030f0b5289740324c3625b0480d754c672d364045b5271c42bed3c64",
        ),
        "headers": (
            421,
            "4d88decfa42908d8899b4d3dad3d6a22496110b126681e2d6fbfd58605b986b3",
        ),
        "writeout": (
            16_811,
            "1d6c29e8369db1c9d3b983a31d89a3265f383453998527e07a26cf04d1686ca7",
        ),
        "evidence_keys": [
            "vietnam-cmc-creative-space-hanoi-annual-report-captured-2026-07-21"
        ],
    },
    "bolivia_start": {
        "requested_url": "https://www.fiscalia.gob.bo/comunicacion/noticias/fiscal-general-da-inicio-a-la-construccion-de-una-moderna-infraestructura-del-data-center-de-clase-mundial-que-transformara-la-justicia-boliviana",
        "completed_at": "2026-07-21T12:22:29Z",
        "http_status": 0,
        "http_version": "0",
        "content_type": None,
        "wire_download_bytes": 0,
        "header_count": 0,
        "headers": (
            0,
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        ),
        "writeout": (
            2_147,
            "52fe60961962e5674cbcfade5ff62e26dba2df5e4eb054ce9d0d8ec2a63fd5a4",
        ),
        "exit_code": 28,
        "error": "Failed to connect to www.fiscalia.gob.bo port 443 after 15008 ms: Timeout was reached",
        "evidence_keys": [],
    },
    "bolivia_progress_index": {
        "requested_url": "https://www.fiscalia.gob.bo/comunicacion/fotos",
        "completed_at": "2026-07-21T12:22:44Z",
        "http_status": 0,
        "http_version": "0",
        "content_type": None,
        "wire_download_bytes": 0,
        "header_count": 0,
        "headers": (
            0,
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        ),
        "writeout": (
            1_560,
            "5892d1d00512347628cf963c9238ddb6880b6929f8cdd5696ce2ae5abca12237",
        ),
        "exit_code": 28,
        "error": "Failed to connect to www.fiscalia.gob.bo port 443 after 15006 ms: Timeout was reached",
        "evidence_keys": [],
    },
}


def _canonical(document: object) -> bytes:
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _instant(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise OfficialBuildsError(f"timestamp lacks timezone: {value}")
    return result.astimezone(UTC)


def _pin(path: Path, expected: tuple[int, str]) -> None:
    if path.is_symlink() or not path.is_file():
        raise OfficialBuildsError(f"pinned ordinary file is absent: {path}")
    actual = (path.stat().st_size, _sha256(path))
    if actual != expected:
        raise OfficialBuildsError(f"pinned file differs: {path}: {actual!r}")


def _capture_metadata(request_id: str) -> dict[str, Any]:
    spec = CAPTURE_SPECS[request_id]
    return {
        "content_hash_scope": (
            f"SHA-256 of the exact {spec['body'][0]}-byte content-decoded "
            "official response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": request_id,
        "capture_headers_bytes": spec["headers"][0],
        "capture_headers_sha256": spec["headers"][1],
        "capture_curl_writeout_bytes": spec["writeout"][0],
        "capture_curl_writeout_sha256": spec["writeout"][1],
        "retrieval_timestamp_basis": (
            "UTC whole-second mtime of the completed curl writeout, sampled after "
            "curl returned"
        ),
        "http_status": spec["http_status"],
        "http_version": spec["http_version"],
        "content_type": spec["content_type"],
        "content_encoding_as_received": spec["content_encoding_as_received"],
        "wire_download_bytes": spec["wire_download_bytes"],
        "response_http_date": spec["response_http_date"],
        "rights_scope": (
            "Compact factual extraction from all-rights-reserved official bytes; "
            "captured bytes and publisher media are not redistributed."
        ),
        "imagery_guardrail": (
            "No publisher image, satellite image, aerial image, computer vision, or "
            "analyst geolocation contributes to this record."
        ),
    }


def _evidence(
    request_id: str,
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
    spec = CAPTURE_SPECS[request_id]
    common = _capture_metadata(request_id)
    common.update(metadata)
    return {
        "key": key,
        "kind": kind,
        "title": title,
        "source_url": spec["requested_url"],
        "publisher": publisher,
        "source_family": source_family,
        "published_at": published_at,
        "retrieved_at": spec["retrieved_at"],
        "license": "all-rights-reserved",
        "attribution": publisher,
        "excerpt": excerpt,
        "content_hash": spec["body"][1],
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
    value: str, evidence_key: str, as_of_date: str, *, confidence: float = 0.99
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
    evidence_key: str, as_of_date: str, *, confidence: float
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


def _lvrtc_source() -> dict[str, Any]:
    progress_key = CAPTURE_SPECS["lvrtc_progress"]["evidence_keys"][0]
    project_key = CAPTURE_SPECS["lvrtc_project"]["evidence_keys"][0]
    legal_name = (
        "Valsts akciju sabiedrība “Latvijas Valsts radio un televīzijas centrs”"
    )
    evidence = [
        _evidence(
            "lvrtc_progress",
            key=progress_key,
            kind="company_disclosure",
            title="Projekta aktualitātes",
            publisher=legal_name,
            source_family="lvrtc_pozitrons_project_pages",
            published_at="2026-02-12",
            excerpt=(
                "LVRTC reports that Pozitrons construction-plan execution exceeded "
                "one quarter through June 30, 2026, with opening planned for Q2 2027."
            ),
            metadata={
                "official_page_modified_at": "2026-07-03T09:13:28Z",
                "location_as_reported": "Kurzeme",
                "status_wording_as_reported": (
                    "Through 2026-06-30 construction-plan execution exceeded one "
                    "quarter; construction works had started in December 2025."
                ),
                "physical_status_scope": (
                    "One generic under_construction observation is retained as of "
                    "2026-06-30. A percentage-plan statement is not converted to an "
                    "exact physical-completion percentage or a finer construction stage."
                ),
                "currentness_scope": (
                    "This is the last observed physical status through 2026-06-30, not "
                    "an automatically current status after that date."
                ),
            },
        ),
        _evidence(
            "lvrtc_project",
            key=project_key,
            kind="company_disclosure",
            title="Datu centrs POZITRONS",
            publisher=legal_name,
            source_family="lvrtc_pozitrons_project_pages",
            published_at="2026-01-09",
            excerpt=(
                "LVRTC's project page describes Pozitrons as a data-processing and "
                "storage facility in its service portfolio and reports a PUE of 1.4."
            ),
            metadata={
                "official_page_modified_at": "2026-07-02T10:30:18Z",
                "pue_as_reported": 1.4,
                "classification_scope": (
                    "Data storage, remote hands, interconnection, and colocation service "
                    "language supports an intended colocation classification. It does not "
                    "assert that the project is operating."
                ),
                "capacity_scope": (
                    "The reported PUE is retained at design stage. No MW, current load, "
                    "consumption, annual energy, generation, or renewable share is emitted."
                ),
                "role_scope": (
                    "LVRTC says it is building data-centre infrastructure and that "
                    "Pozitrons will join its service portfolio, supporting developer and "
                    "intended-operator roles only."
                ),
            },
        ),
    ]
    campus_key = "curated:lvrtc-pozitrons-kurzeme-data-center"
    project_stable_key = f"{campus_key}:phase-1-current-build"
    roles = {"developer": [legal_name], "operator": [legal_name]}
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="LVRTC Pozitrons Kurzeme Data Center",
            country="Latvia",
            address="Kurzeme, Latvia",
            roles=roles,
            evidence_key=progress_key,
            as_of_date="2026-06-30",
            confidence=0.97,
        ),
        "project": _entity(
            stable_key=project_stable_key,
            name="Pozitrons Phase 1 Current Build",
            country="Latvia",
            address="Kurzeme, Latvia",
            roles=roles,
            evidence_key=progress_key,
            as_of_date="2026-06-30",
            confidence=0.97,
        ),
        "lifecycle": [_lifecycle("under_construction", progress_key, "2026-06-30")],
        "operating_models": [
            _operating_model(project_key, "2026-07-02", confidence=0.95)
        ],
        "workloads": [],
        "capacities": [
            _capacity(
                metric="pue",
                stage="design",
                unit="ratio",
                value=1.4,
                evidence_key=project_key,
                as_of_date="2026-07-02",
                confidence=0.98,
                notes=(
                    "Reported project PUE retained as a design value; it is not measured, "
                    "commissioned, accepted, or operating performance."
                ),
            )
        ],
    }


def _akashi_source() -> dict[str, Any]:
    progress_key = CAPTURE_SPECS["akashi_progress"]["evidence_keys"][0]
    about_key = CAPTURE_SPECS["akashi_about"]["evidence_keys"][0]
    publisher = "Akashi Data Center"
    evidence = [
        _evidence(
            "akashi_progress",
            key=progress_key,
            kind="company_disclosure",
            title="Construction progress",
            publisher=publisher,
            source_family="akashi_data_center_project_pages",
            published_at=None,
            excerpt=(
                "Akashi's live Astana campus page says the foundation is complete, the "
                "first buildings are rising, and phase 1 has 5.28 MW of IT load."
            ),
            metadata={
                "status_wording_as_reported": (
                    "Live status; foundation complete; first buildings rising; 11 "
                    "hectares of purpose-built infrastructure under construction."
                ),
                "critical_it_capacity_mw_planned_as_reported": 5.28,
                "first_phase_launch_as_reported": "May 2027",
                "physical_status_scope": (
                    "The current first-party page supports generic under_construction as "
                    "observed at retrieval. It does not prove completion, commissioning, "
                    "operation, or any Uptime certification."
                ),
                "capacity_scope": (
                    "Only the source-typed 5.28 MW phase-1 IT load is normalized, at "
                    "planned stage. The JavaScript site-power ticker is dynamic and "
                    "excluded."
                ),
                "certification_guardrail": (
                    "Tier IV audit and certification references are targets or scheduled "
                    "processes, not a completed facility certification."
                ),
                "currentness_scope": (
                    "Status is tied to the current official page observed on 2026-07-21; "
                    "it is not projected beyond the retrieval date."
                ),
            },
        ),
        _evidence(
            "akashi_about",
            key=about_key,
            kind="company_disclosure",
            title="About Akashi",
            publisher=publisher,
            source_family="akashi_data_center_project_pages",
            published_at=None,
            excerpt=(
                "Akashi says its Astana campus is being built and markets turnkey "
                "enterprise colocation across four planned data-center buildings."
            ),
            metadata={
                "dedicated_power_mw_as_reported": 100,
                "dedicated_power_dimension": "not sufficiently typed",
                "power_guardrail": (
                    "The advertised 100 MW dedicated-power and 2027+ expansion figures "
                    "are not explicitly typed as critical IT, gross facility, grid "
                    "connection, or generation, so no normalized capacity row is emitted."
                ),
                "classification_scope": (
                    "Turnkey enterprise colocation, cages, and cabinet-rental services "
                    "support intended colocation classification only."
                ),
                "role_scope": (
                    "Akashi says it is being built in Astana and identifies its team as "
                    "building and operating the campus, supporting developer and intended "
                    "operator roles without asserting operation."
                ),
            },
        ),
    ]
    campus_key = "curated:akashi-astana-data-center-campus"
    project_key = f"{campus_key}:phase-1-current-build"
    roles = {"developer": [publisher], "operator": [publisher]}
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="Akashi Astana Data Center Campus",
            country="Kazakhstan",
            address="Astana, Kazakhstan",
            roles=roles,
            evidence_key=progress_key,
            as_of_date="2026-07-21",
            confidence=0.99,
        ),
        "project": _entity(
            stable_key=project_key,
            name="Akashi Astana Phase 1 Current Build",
            country="Kazakhstan",
            address="Astana, Kazakhstan",
            roles=roles,
            evidence_key=progress_key,
            as_of_date="2026-07-21",
            confidence=0.99,
        ),
        "lifecycle": [_lifecycle("under_construction", progress_key, "2026-07-21")],
        "operating_models": [
            _operating_model(about_key, "2026-07-21", confidence=0.98)
        ],
        "workloads": [],
        "capacities": [
            _capacity(
                metric="critical_it_mw",
                stage="planned",
                unit="MW",
                value=5.28,
                evidence_key=progress_key,
                as_of_date="2026-07-21",
                confidence=0.99,
                notes=(
                    "Reported phase-1 IT load retained at planned stage. It is not "
                    "installed, energized, operational, current demand, grid capacity, "
                    "generation, consumption, or annual energy."
                ),
            )
        ],
    }


def _bichuten_source() -> dict[str, Any]:
    evidence_key = CAPTURE_SPECS["bichuten_care"]["evidence_keys"][0]
    publisher = "CARE Ratings Nepal Limited"
    company = "Bichuten Data Vault Private Limited"
    evidence = [
        _evidence(
            "bichuten_care",
            key=evidence_key,
            kind="company_disclosure",
            title="Bichuten Data Vault Private Limited",
            publisher=publisher,
            source_family="care_ratings_nepal_releases",
            published_at=None,
            excerpt=(
                "CARE Ratings Nepal says Bichuten's Chovar-06 plant was in a nascent "
                "stage of construction through March 2026 and describes planned "
                "colocation services."
            ),
            metadata={
                "report_date_as_displayed": "April 2026",
                "publication_date_verification": (
                    "The PDF exposes only April 2026, not a reliable exact day; "
                    "published_at remains null."
                ),
                "status_wording_as_reported": (
                    "The plant is in nascent stage of construction; through March end "
                    "2026 the required land area had been leased."
                ),
                "physical_status_scope": (
                    "One generic under_construction observation is retained as of "
                    "2026-03-31. No foundations, shell, MEP, commissioning, completion, "
                    "operation, or exact physical percentage is inferred."
                ),
                "reported_capacity_text": "120 kW across Chovar-06 and Birgunj",
                "capacity_guardrail": (
                    "The 120 kW wording does not allocate capacity between the two sites, "
                    "so no Chovar capacity is normalized."
                ),
                "certification_guardrail": (
                    "Tier IV-certified wording describes the planned project and is not "
                    "a current certification claim."
                ),
                "classification_scope": (
                    "The report says Bichuten's major services will include colocation; "
                    "classification is intended and does not assert operation."
                ),
                "role_scope": (
                    "The report says Bichuten is developing the facility and will provide "
                    "its services, supporting developer and intended-operator roles."
                ),
            },
        )
    ]
    campus_key = "curated:bichuten-chovar-data-center"
    project_key = f"{campus_key}:initial-container-build"
    roles = {"developer": [company], "operator": [company]}
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="Bichuten Chovar Data Center",
            country="Nepal",
            address="Chovar-06, Kirtipur Municipality, Bagmati Province, Nepal",
            roles=roles,
            evidence_key=evidence_key,
            as_of_date="2026-03-31",
            confidence=0.99,
        ),
        "project": _entity(
            stable_key=project_key,
            name="Bichuten Chovar Initial Container Build",
            country="Nepal",
            address="Chovar-06, Kirtipur Municipality, Bagmati Province, Nepal",
            roles=roles,
            evidence_key=evidence_key,
            as_of_date="2026-03-31",
            confidence=0.99,
        ),
        "lifecycle": [_lifecycle("under_construction", evidence_key, "2026-03-31")],
        "operating_models": [
            _operating_model(evidence_key, "2026-03-31", confidence=0.95)
        ],
        "workloads": [],
        "capacities": [],
    }


def _icatec_source() -> dict[str, Any]:
    february_key = CAPTURE_SPECS["icatec_february"]["evidence_keys"][0]
    april_key = CAPTURE_SPECS["icatec_april"]["evidence_keys"][0]
    publisher = "Gobierno Regional de Ica"
    evidence = [
        _evidence(
            "icatec_february",
            key=february_key,
            kind="government_record",
            title=(
                "Nota de Prensa N° 019-2026: Megaproyecto ICATEC registra progresos "
                "en su etapa estructural"
            ),
            publisher=publisher,
            source_family="peru_gob_pe_region_ica_news",
            published_at="2026-02-12",
            excerpt=(
                "The Ica regional government reports foundation excavation, steel "
                "placement, and concrete work for ICATEC's four-storey structure."
            ),
            metadata={
                "status_wording_as_reported": (
                    "Site leveling, foundation excavations, steel preparation and "
                    "placement, and concrete placement were underway for four floors."
                ),
                "physical_status_scope": (
                    "The explicit foundation works support foundations as of 2026-02-12. "
                    "No physical percentage, shell, MEP, commissioning, completion, or "
                    "operation is inferred."
                ),
                "project_scope": (
                    "ICATEC is a broader government technology project; the record "
                    "represents its source-identified facility that will contain data "
                    "processing infrastructure, not a standalone hyperscale campus."
                ),
            },
        ),
        _evidence(
            "icatec_april",
            key=april_key,
            kind="government_record",
            title=(
                "Nota de Prensa N° 044-2026: Avanza el proyecto ICATEC: el futuro "
                "digital de Ica ya está en construcción"
            ),
            publisher=publisher,
            source_family="peru_gob_pe_region_ica_news",
            published_at="2026-04-07",
            excerpt=(
                "An official supervision visit verified construction progress on the "
                "ICATEC facility that will house Ica's data-processing center and a data "
                "center on more than 2,500 square metres."
            ),
            metadata={
                "area_more_than_square_metres_as_reported": 2_500,
                "status_wording_as_reported": (
                    "A supervision visit verified construction progress on the "
                    "infrastructure that will house the new Digital Transformation and "
                    "Data Processing Center."
                ),
                "physical_status_scope": (
                    "The dated government inspection supports generic under_construction "
                    "as of 2026-04-07. It does not provide a reliable finer stage."
                ),
                "capacity_guardrail": (
                    "Floor area is not power or energy. No load, grid, generation, annual "
                    "energy, PUE, utilization, or capacity observation is emitted."
                ),
                "classification_guardrail": (
                    "The mixed government technology and data-processing scope is retained "
                    "as metadata; no supported operating-model or workload row is emitted."
                ),
                "role_scope": (
                    "The Ica regional government says it continues executing the project, "
                    "supporting a developer role only."
                ),
            },
        ),
    ]
    campus_key = "curated:icatec-ica-digital-transformation-data-center"
    project_key = f"{campus_key}:four-storey-technology-center-build"
    roles = {"developer": [publisher]}
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="ICATEC Ica Digital Transformation and Data Processing Center",
            country="Peru",
            address="Ica Region, Peru",
            roles=roles,
            evidence_key=april_key,
            as_of_date="2026-04-07",
            confidence=0.98,
        ),
        "project": _entity(
            stable_key=project_key,
            name="ICATEC Four-Storey Technology Center Build",
            country="Peru",
            address="Ica Region, Peru",
            roles=roles,
            evidence_key=april_key,
            as_of_date="2026-04-07",
            confidence=0.98,
        ),
        "lifecycle": [
            _lifecycle("foundations", february_key, "2026-02-12"),
            _lifecycle("under_construction", april_key, "2026-04-07"),
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _cmc_source() -> dict[str, Any]:
    evidence_key = CAPTURE_SPECS["cmc_annual_report"]["evidence_keys"][0]
    publisher = "CMC Corporation"
    evidence = [
        _evidence(
            "cmc_annual_report",
            key=evidence_key,
            kind="company_disclosure",
            title="CMC Annual Report 2024",
            publisher=publisher,
            source_family="cmc_corporation_annual_reports",
            published_at=None,
            excerpt=(
                "CMC's annual report says Creative Space Hanoi Phase 2 includes a "
                "five-storey data-center tower and a 23-storey office tower and officially "
                "broke ground on June 1, 2025."
            ),
            metadata={
                "selected_pdf_page": 50,
                "publication_date_verification": (
                    "The captured annual report does not expose a reliable exact "
                    "publication day; published_at remains null."
                ),
                "land_area_square_metres_as_reported": 11_341,
                "construction_area_square_metres_as_reported": 90_095,
                "data_center_storeys_as_reported": 5,
                "office_tower_storeys_as_reported": 23,
                "status_wording_as_reported": (
                    "Phase 2 includes construction of the Data Center tower and Office "
                    "tower; the project officially broke ground on 2025-06-01."
                ),
                "physical_status_scope": (
                    "One historical under_construction observation is retained at the "
                    "official groundbreaking date. The report does not establish current "
                    "2026 physical status, completion, commissioning, or operation."
                ),
                "historical_only_guardrail": (
                    "This record is source-valid but not seed-eligible in the fresh-build "
                    "tranche because its last physical evidence is the 2025-06-01 start."
                ),
                "schedule_guardrail": (
                    "Expected Q1 2027 completion is a forecast, not a verified outcome."
                ),
                "capacity_guardrail": (
                    "Building and land areas are not power or energy. No load, grid, "
                    "generation, annual energy, PUE, or utilization value is emitted."
                ),
                "role_scope": (
                    "CMC says it commenced construction, supporting a developer role only."
                ),
            },
        )
    ]
    campus_key = "curated:cmc-creative-space-hanoi"
    project_key = f"{campus_key}:phase-2-data-center-and-office-tower-build"
    roles = {"developer": [publisher]}
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="CMC Creative Space Hanoi",
            country="Vietnam",
            address="Hanoi, Vietnam",
            roles=roles,
            evidence_key=evidence_key,
            as_of_date="2025-06-01",
            confidence=0.98,
        ),
        "project": _entity(
            stable_key=project_key,
            name="CMC Creative Space Hanoi Phase 2 Data Center and Office Tower Build",
            country="Vietnam",
            address="Hanoi, Vietnam",
            roles=roles,
            evidence_key=evidence_key,
            as_of_date="2025-06-01",
            confidence=0.98,
        ),
        "lifecycle": [
            {
                **_lifecycle("under_construction", evidence_key, "2025-06-01"),
                "method": "authoritative_construction_start",
            }
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    """Return the five exact schema-1.1 source documents."""

    builders = (
        _lvrtc_source,
        _akashi_source,
        _bichuten_source,
        _icatec_source,
        _cmc_source,
    )
    return {
        name: builder() for name, builder in zip(SOURCE_FILENAMES, builders, strict=True)
    }


SOURCE_DISPOSITIONS = {
    SOURCE_FILENAMES[0]: "seed_eligible_fresh_official_physical_update",
    SOURCE_FILENAMES[1]: "seed_eligible_fresh_official_physical_update",
    SOURCE_FILENAMES[2]: "seed_eligible_fresh_official_physical_update",
    SOURCE_FILENAMES[3]: "seed_eligible_fresh_official_physical_update",
    SOURCE_FILENAMES[4]: "historical_only_current_status_unknown",
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
                "seed_eligible": name != SOURCE_FILENAMES[4],
                "seeded": False,
            }
        )
    return records


def _candidate_assessments(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-six-candidate-official-build-assessment-v1",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "candidate_count": 6,
        "seed_eligible_count": 4,
        "historical_only_count": 1,
        "review_only_count": 1,
        "candidates": [
            {
                "candidate_id": "lvrtc-pozitrons-kurzeme",
                "country": "Latvia",
                "decision": "seed_eligible_fresh_official_physical_update",
                "source_record_created": True,
                "seed_eligible": True,
                "basis": (
                    "Direct LVRTC bytes report construction progress through 2026-06-30."
                ),
            },
            {
                "candidate_id": "akashi-astana-phase-1",
                "country": "Kazakhstan",
                "decision": "seed_eligible_fresh_official_physical_update",
                "source_record_created": True,
                "seed_eligible": True,
                "basis": (
                    "Direct Akashi bytes present a current construction snapshot on the "
                    "2026-07-21 retrieval date."
                ),
            },
            {
                "candidate_id": "bichuten-chovar",
                "country": "Nepal",
                "decision": "seed_eligible_fresh_official_physical_update",
                "source_record_created": True,
                "seed_eligible": True,
                "basis": (
                    "The directly captured CARE Ratings Nepal release says the Chovar "
                    "plant was in a nascent construction stage through March 2026."
                ),
            },
            {
                "candidate_id": "icatec-ica",
                "country": "Peru",
                "decision": "seed_eligible_fresh_official_physical_update",
                "source_record_created": True,
                "seed_eligible": True,
                "basis": (
                    "Two directly captured Ica government releases document foundations "
                    "and later inspected construction progress in February and April 2026."
                ),
            },
            {
                "candidate_id": "cmc-creative-space-hanoi-phase-2",
                "country": "Vietnam",
                "decision": "historical_only_current_status_unknown",
                "source_record_created": True,
                "seed_eligible": False,
                "basis": (
                    "The direct annual-report bytes prove the 2025-06-01 groundbreaking "
                    "but not fresh 2026 physical status."
                ),
            },
            {
                "candidate_id": "bolivia-fiscalia-sucre-data-center",
                "country": "Bolivia",
                "decision": "review_only_no_direct_capture",
                "source_record_created": False,
                "seed_eligible": False,
                "basis": (
                    "Both direct official requests timed out without response headers or "
                    "body bytes. Browser-visible index context is not substituted for a "
                    "captured source body."
                ),
                "browser_context_not_evidence": {
                    "index_title_observed": (
                        "MINISTERIO PÚBLICO AVANZA EN LA CONSTRUCCIÓN DE SU NUEVO "
                        "EDIFICIO PARA EL DATA CENTER DE CLASE MUNDIAL EN SUCRE"
                    ),
                    "index_timestamp_observed": "2026-05-15T14:10:45-04:00",
                    "used_for_normalized_claims": False,
                },
            },
        ],
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    requests = []
    for request_id, spec in CAPTURE_SPECS.items():
        succeeded = "body" in spec
        row = {
            "request_id": request_id,
            "requested_url": spec["requested_url"],
            "effective_url": spec["requested_url"],
            "completed_at": spec.get("retrieved_at", spec.get("completed_at")),
            "completion_timestamp_basis": (
                "UTC whole-second mtime of the completed curl writeout, sampled after "
                "curl returned"
            ),
            "curl_exit_code": 0 if succeeded else spec["exit_code"],
            "http_status": spec["http_status"],
            "http_version": spec["http_version"],
            "content_type": spec["content_type"],
            "wire_download_bytes": spec["wire_download_bytes"],
            "curl_header_bytes": spec["headers"][0],
            "curl_num_headers": spec["header_count"],
            "redirect_count": 0,
            "contributes_evidence": succeeded,
            "evidence_keys": spec["evidence_keys"],
            "headers": {
                "bytes": spec["headers"][0],
                "sha256": spec["headers"][1],
                "retained_in_artifact": False,
                "moved_to_trash": True,
            },
            "curl_writeout": {
                "bytes": spec["writeout"][0],
                "sha256": spec["writeout"][1],
                "retained_in_artifact": False,
                "moved_to_trash": True,
            },
        }
        if succeeded:
            row.update(
                {
                    "retrieved_at": spec["retrieved_at"],
                    "content_encoding_as_received": spec[
                        "content_encoding_as_received"
                    ],
                    "response_http_date": spec["response_http_date"],
                    "response_http_date_used_as_retrieved_at": False,
                    "body": {
                        "bytes": spec["body"][0],
                        "sha256": spec["body"][1],
                        "retained_in_artifact": False,
                        "moved_to_trash": True,
                    },
                }
            )
        else:
            row.update(
                {
                    "body_created": False,
                    "curl_error": spec["error"],
                    "evidence_created": False,
                }
            )
        requests.append(row)
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v2",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "capture_protocol": (
            "Credential-free public curl GETs with redirects, content decoding, a "
            "transparent research User-Agent, separate response bodies and header "
            "streams, and newline-terminated curl JSON writeouts."
        ),
        "direct_request_attempts": 10,
        "successful_http_requests": 8,
        "failed_transport_requests": 2,
        "evidence_supporting_captures": 8,
        "captured_file_count": 28,
        "request_credentials_supplied": False,
        "browser_session_used_for_evidence": False,
        "raw_capture_redistributed": False,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "controlled_http_requests": requests,
    }


def _artifact_documents(
    recorded_at: str, source_documents: Mapping[str, Mapping[str, Any]]
) -> dict[str, bytes]:
    source_records = _source_records(source_documents)
    readme = f"""# Global official-build six-candidate assessment

This immutable artifact records a frozen 2026-07-21 assessment of six global data-center construction candidates. Four pass the fresh direct-official-byte boundary: LVRTC Pozitrons, Akashi Astana phase 1, Bichuten Chovar, and ICATEC Ica. CMC Creative Space Hanoi is preserved as historical-only because the captured annual report proves a June 1, 2025 groundbreaking but no fresh 2026 physical status. Bolivia remains review-only because both controlled direct requests timed out without a response body.

Only source-typed dimensions are normalized. Akashi contributes 5.28 MW of planned phase-1 IT load; its dynamic site-power ticker and untyped 100 MW dedicated-power claim are excluded. LVRTC contributes design PUE 1.4. Bichuten's 120 kW is not allocated between Chovar and Birgunj and is excluded. Generation, grid connection, current load, consumption, annual energy, floor area, building count, and forecast completion are never substituted for each other.

No source has coordinates or geometry. No publisher imagery, satellite imagery, aerial imagery, computer vision, or analyst geolocation contributes to identity or status. Lifecycle values are last observations at their stated dates, not automatic current-state claims.

All source and artifact bytes were completed in private staging before `{recorded_at}`. Final paths remained absent until that instant, after which all six outputs were promoted without replacement as one rollback-protected publication set. Source files are 0644; the artifact is frozen 0555/0444. This tranche does not create an open-seed successor because the coordinate v72 lane has priority, and it does not mutate accepted open seed v71 or any downstream product.

The complete 28-file capture directory was moved intact to the unique recoverable Trash path recorded in the rights inventory. Raw all-rights-reserved response bodies, headers, cookies, and curl writeouts are not redistributed.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v2",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "source_records": source_records,
        "totals": {
            "candidate_assessments": 6,
            "source_records": 5,
            "seed_eligible_source_records": 4,
            "historical_only_source_records": 1,
            "review_only_candidates": 1,
            "distinct_campuses": 5,
            "projects": 5,
            "entity_snapshots": 10,
            "unique_evidence_records": 8,
            "lifecycle_observations": 6,
            "operating_model_observations": 3,
            "workload_observations": 0,
            "capacity_estimates": 2,
            "coordinates_present": 0,
            "geometry_present": 0,
        },
        "frozen_v71_non_mutation_witness": {
            "definition": {
                "path": "sources/open-seed-2026-07-21-v71.json",
                "bytes": V71_PINS[V71_DEFINITION][0],
                "sha256": V71_PINS[V71_DEFINITION][1],
            },
            "release_manifest": {
                "path": "releases/2026-07-21-open-seed-v71/manifest.json",
                "bytes": V71_PINS[V71_MANIFEST][0],
                "sha256": V71_PINS[V71_MANIFEST][1],
            },
            "release_tree_sha256": V71_TREE_SHA256,
            "v71_selected_input_count": 393,
            "new_source_paths_selected_by_v71": False,
            "new_stable_key_collisions": 0,
            "new_evidence_key_collisions": 0,
        },
        "integration": {
            "open_seed_successor_created": False,
            "reason": "coordinate_v72_lane_has_priority",
            "open_seed_v71_mutated": False,
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
        "format": "datacenter-atlas-source-rights-disposition-v2",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "source_rights": (
            "All captured publisher response bodies are treated as all-rights-reserved; "
            "no redistribution license was relied on."
        ),
        "artifact_is_hash_only": True,
        "raw_capture_redistributed": False,
        "raw_response_bodies_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "curl_writeouts_retained_in_artifact": False,
        "publisher_media_retained_in_artifact": False,
        "response_cookies_retained_in_artifact": False,
        "request_credentials_supplied": False,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "temporary_capture_move_scope": (
            "The entire 28-file directory was moved intact: eight bodies, ten raw "
            "header streams, and ten curl JSON writeouts, including both failed Bolivia "
            "attempts."
        ),
        "deletion_performed": False,
        "candidate_dispositions": {
            "seed_eligible": 4,
            "historical_only": 1,
            "review_only_no_direct_capture": 1,
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
    stage: Path, documents: Mapping[str, Mapping[str, Any]]
) -> None:
    for name in SOURCE_FILENAMES:
        path = stage / name
        path.write_bytes(_canonical(documents[name]))
        path.chmod(0o644)
        _fsync_regular(path)
    _fsync_directory(stage)


def _write_artifact_stage(
    stage: Path, recorded_at: str, documents: Mapping[str, Mapping[str, Any]]
) -> None:
    payloads = _artifact_documents(recorded_at, documents)
    for name in CONTENT_FILES:
        path = stage / name
        path.write_bytes(payloads[name])
        path.chmod(0o444)
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
        "format": "datacenter-atlas-official-source-artifact-manifest-v2",
        "recorded_at": recorded_at,
        "files": rows,
        "tree_sha256": _file_tree(rows),
        "closed_file_set": sorted(CLOSED_FILES),
        "candidate_assessments": 6,
        "curated_source_records": 5,
        "seed_eligible_source_records": 4,
        "historical_only_source_records": 1,
        "review_only_candidates": 1,
        "successful_raw_captures": 8,
        "failed_transport_captures": 2,
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
        raise OfficialBuildsError("source path inventory differs")
    for name in SOURCE_FILENAMES:
        path = paths[name]
        if path.is_symlink() or not path.is_file():
            raise OfficialBuildsError(f"curated source is absent: {path}")
        raw = path.read_bytes()
        if raw != _canonical(expected[name]):
            raise OfficialBuildsError(f"curated source differs: {name}")
        if stat.S_IMODE(path.stat().st_mode) != 0o644:
            raise OfficialBuildsError(f"curated source mode differs: {name}")
        document = json.loads(raw)
        if document["campus"]["coordinates"] is not None:
            raise OfficialBuildsError(f"curated source invented coordinates: {name}")
        if document["project"]["coordinates"] is not None:
            raise OfficialBuildsError(f"curated source invented coordinates: {name}")
        if document["campus"]["geometry"] is not None:
            raise OfficialBuildsError(f"curated source invented geometry: {name}")
        if document["project"]["geometry"] is not None:
            raise OfficialBuildsError(f"curated source invented geometry: {name}")
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
    if len(stable_keys) != 10 or len(evidence_keys) != 8:
        raise OfficialBuildsError("planned source keys are not unique")
    collisions: dict[str, dict[str, list[str]]] = {}
    for path in SOURCES_ROOT.glob("*.json"):
        if path.name in SOURCE_FILENAMES:
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
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
            collisions[path.name] = {
                "stable_keys": stable_overlap,
                "evidence_keys": evidence_overlap,
            }
    if collisions:
        raise OfficialBuildsError(f"curated source collision: {collisions!r}")


def _validate_v71_nonmutation() -> None:
    for path, pin in V71_PINS.items():
        _pin(path, pin)
    if tree_digest(V71_RELEASE) != V71_TREE_SHA256:
        raise OfficialBuildsError("accepted v71 release tree differs")
    definition = json.loads(V71_DEFINITION.read_text(encoding="utf-8"))
    if len(definition.get("curated_inputs", [])) != 393:
        raise OfficialBuildsError("accepted v71 input count differs")
    selected = {row["path"] for row in definition["curated_inputs"]}
    planned_paths = {f"sources/{name}" for name in SOURCE_FILENAMES}
    if selected & planned_paths:
        raise OfficialBuildsError("v71 unexpectedly selects a new source path")
    entities_text = V71_ENTITIES.read_text(encoding="utf-8")
    for document in expected_source_documents().values():
        for entity in ("campus", "project"):
            if document[entity]["stable_key"] in entities_text:
                raise OfficialBuildsError("new source stable key collides with v71")


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise OfficialBuildsError(f"capture directory is absent or unsafe: {directory}")
    expected_names = {
        f"{request_id}.{suffix}"
        for request_id, spec in CAPTURE_SPECS.items()
        for suffix in (("body", "headers", "writeout") if "body" in spec else ("headers", "writeout"))
    }
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != expected_names:
        raise OfficialBuildsError("capture directory file closure differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise OfficialBuildsError("capture directory contains a non-ordinary file")
    for request_id, spec in CAPTURE_SPECS.items():
        suffixes = ("body", "headers", "writeout") if "body" in spec else (
            "headers",
            "writeout",
        )
        for suffix in suffixes:
            _pin(directory / f"{request_id}.{suffix}", spec[suffix])
        writeout = json.loads(
            (directory / f"{request_id}.writeout").read_text(encoding="utf-8")
        )
        expected = (
            spec["requested_url"],
            spec["http_status"],
            spec["http_version"],
            spec["content_type"],
            spec["wire_download_bytes"],
            spec["headers"][0],
            spec["header_count"],
            0,
            0 if "body" in spec else spec["exit_code"],
            None if "body" in spec else spec["error"],
        )
        actual = (
            writeout["url_effective"],
            writeout["response_code"],
            writeout["http_version"],
            writeout["content_type"],
            writeout["size_download"],
            writeout["size_header"],
            writeout["num_headers"],
            writeout["num_redirects"],
            writeout["exitcode"],
            writeout["errormsg"],
        )
        if actual != expected:
            raise OfficialBuildsError(f"capture writeout differs: {request_id}")
        completion = datetime.fromtimestamp(
            (directory / f"{request_id}.writeout").stat().st_mtime, UTC
        ).replace(microsecond=0)
        expected_completion = _instant(
            spec.get("retrieved_at", spec.get("completed_at"))
        )
        if completion != expected_completion:
            raise OfficialBuildsError(
                f"capture completion timestamp differs: {request_id}"
            )


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory() as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for name in SOURCE_FILENAMES:
            adapter.import_file(connection, paths[name], recorded_at=recorded_at)
        validate_database(connection)
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "entities",
                "entity_snapshots",
                "evidence",
                "lifecycle_observations",
                "operating_model_observations",
                "workload_observations",
                "capacity_estimates",
            )
        }
        expected = {
            "entities": 10,
            "entity_snapshots": 10,
            "evidence": 8,
            "lifecycle_observations": 6,
            "operating_model_observations": 3,
            "workload_observations": 0,
            "capacity_estimates": 2,
        }
        if counts != expected:
            raise OfficialBuildsError(f"offline import counts differ: {counts!r}")
        capacities = [
            tuple(row)
            for row in connection.execute(
                "SELECT metric, stage, unit, base FROM capacity_estimates "
                "ORDER BY metric, stage"
            )
        ]
        if capacities != [
            ("critical_it_mw", "planned", "MW", 5.28),
            ("pue", "design", "ratio", 1.4),
        ]:
            raise OfficialBuildsError(f"offline capacity rows differ: {capacities!r}")
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
        raise OfficialBuildsError("artifact must be an ordinary directory")
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise OfficialBuildsError("artifact closed file set differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries.values()):
        raise OfficialBuildsError("artifact contains a non-ordinary file")
    if stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise OfficialBuildsError("artifact directory mode differs")
    if any(stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries.values()):
        raise OfficialBuildsError("artifact file mode differs")
    for name in CONTENT_FILES[1:]:
        raw = entries[name].read_bytes()
        if raw != _canonical(json.loads(raw)):
            raise OfficialBuildsError(f"artifact JSON is not canonical: {name}")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest):
        raise OfficialBuildsError("manifest JSON is not canonical")
    if (
        manifest.get("artifact_id") != ARTIFACT_ID
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or manifest.get("candidate_assessments") != 6
        or manifest.get("curated_source_records") != 5
        or manifest.get("seed_eligible_source_records") != 4
        or manifest.get("historical_only_source_records") != 1
        or manifest.get("review_only_candidates") != 1
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise OfficialBuildsError("manifest contract differs")
    if [row["path"] for row in manifest["files"]] != list(CONTENT_FILES):
        raise OfficialBuildsError("manifest file order differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (
            row["bytes"],
            row["sha256"],
        ):
            raise OfficialBuildsError(f"manifest file pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise OfficialBuildsError("manifest checksum differs")
    expected_documents = _artifact_documents(manifest["recorded_at"], expected_source_documents())
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected_documents[name]:
            raise OfficialBuildsError(f"artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records:
        raise OfficialBuildsError("artifact source pins differ")
    assessment = json.loads(
        entries["candidate-assessment.json"].read_text(encoding="utf-8")
    )
    bolivia = next(
        row
        for row in assessment["candidates"]
        if row["candidate_id"] == "bolivia-fiscalia-sucre-data-center"
    )
    if bolivia["source_record_created"] or bolivia["seed_eligible"]:
        raise OfficialBuildsError("Bolivia disposition differs")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise OfficialBuildsError("validation wall clock lacks timezone")
    if require_live:
        if now.astimezone(UTC) < target:
            raise OfficialBuildsError("artifact recorded_at is not live")
        _assert_final_ctimes((*paths.values(), path), target)
    for document in expected_source_documents().values():
        for evidence in document["evidence"]:
            if _instant(evidence["retrieved_at"]) > target:
                raise OfficialBuildsError("evidence retrieval post-dates recorded_at")
    return manifest


def _fsync_regular(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _identity(path: Path, *, directory: bool) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    correct_type = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(
        metadata.st_mode
    )
    if not correct_type:
        raise OfficialBuildsError(f"staged path type differs: {path}")
    return metadata.st_dev, metadata.st_ino


def _has_identity(path: Path, identity: tuple[int, int], *, directory: bool) -> bool:
    try:
        metadata = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return False
    correct_type = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(
        metadata.st_mode
    )
    return correct_type and (metadata.st_dev, metadata.st_ino) == identity


def _promote_noreplace(source: Path, destination: Path) -> None:
    """Atomically rename one same-filesystem path without replacing a late arrival."""

    library = ctypes.CDLL(None, use_errno=True)
    source_raw = os.fsencode(source)
    destination_raw = os.fsencode(destination)
    if sys.platform == "darwin":
        function = getattr(library, "renamex_np", None)
        if function is None:  # pragma: no cover
            raise OfficialBuildsError("atomic no-replace publication is unavailable")
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(source_raw, destination_raw, 0x00000004)
    elif sys.platform.startswith("linux"):
        function = getattr(library, "renameat2", None)
        if function is None:  # pragma: no cover
            raise OfficialBuildsError("atomic no-replace publication is unavailable")
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(-100, source_raw, -100, destination_raw, 0x00000001)
    else:  # pragma: no cover
        raise OfficialBuildsError("atomic no-replace publication is unavailable")
    if result == 0:
        _fsync_directory(destination.parent)
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise OfficialBuildsError(
            f"late output collision; refusing replacement: {destination}"
        )
    raise OfficialBuildsError(
        f"atomic no-replace publication failed: {os.strerror(error_number)}"
    )


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise OfficialBuildsError(
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
    source_members = sorted(source_stage.iterdir(), key=lambda path: path.name)
    artifact_members = sorted(artifact_stage.iterdir(), key=lambda path: path.name)
    return (source_stage, *source_members, artifact_stage, *artifact_members)


def _assert_stage_precedes_target(paths: Sequence[Path], target: datetime) -> None:
    target_epoch = target.timestamp()
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        if not hasattr(metadata, "st_birthtime"):
            raise OfficialBuildsError("filesystem birth time is unavailable")
        if max(metadata.st_birthtime, metadata.st_mtime) > target_epoch + 0.000_001:
            raise OfficialBuildsError(f"private stage post-dates recorded_at: {path}")


def _assert_final_ctimes(paths: Sequence[Path], target: datetime) -> None:
    target_epoch = target.timestamp()
    for path in paths:
        if path.is_symlink() or not path.exists():
            raise OfficialBuildsError(f"published root is absent: {path}")
        if path.stat(follow_symlinks=False).st_ctime + 0.000_001 < target_epoch:
            raise OfficialBuildsError(
                f"published root rename predates recorded_at: {path}"
            )


def _require_finals_absent(finals: Sequence[Path], label: str) -> None:
    occupied = [path for path in finals if path.exists() or path.is_symlink()]
    if occupied:
        raise OfficialBuildsError(f"{label} final path occupied: {occupied!r}")


def _discard_owned_directory(
    path: Path,
    identity: tuple[int, int],
    member_identities: Mapping[str, tuple[int, int]],
) -> None:
    try:
        metadata = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(metadata.st_mode) or (
        metadata.st_dev,
        metadata.st_ino,
    ) != identity:
        raise OfficialBuildsError(f"refusing substituted staging directory: {path}")
    entries = list(path.iterdir())
    actual = {
        entry.name: _identity(entry, directory=False)
        for entry in entries
        if not entry.is_symlink() and entry.is_file()
    }
    if len(actual) != len(entries) or actual != {
        name: member_identities[name]
        for name in actual
        if name in member_identities
    }:
        raise OfficialBuildsError(f"refusing contaminated staging cleanup: {path}")
    path.chmod(0o700)
    for entry in entries:
        entry.chmod(0o600)
        entry.unlink()
    path.rmdir()


def _wait_until(
    target: float,
    *,
    clock: Callable[[], float] = time.time,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    while True:
        remaining = target - clock()
        if remaining <= 0:
            return
        sleeper(min(remaining, 0.25))


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
        raise OfficialBuildsError("recorded_at must be future before staging")
    source_stage = Path(
        tempfile.mkdtemp(prefix=".official-builds-six.", dir=SOURCES_ROOT)
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
        final_paths = tuple(SOURCES_ROOT / name for name in SOURCE_FILENAMES) + (
            ARTIFACT,
        )
        _require_finals_absent(final_paths, "staging")
        _assert_stage_precedes_target(
            _all_stage_paths(source_stage, artifact_stage), target
        )
        if datetime.now(UTC) >= target:
            raise OfficialBuildsError("private staging did not finish before recorded_at")
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
                artifact_members = {
                    entry.name: _identity(entry, directory=False)
                    for entry in artifact_stage.iterdir()
                }
                _discard_owned_directory(
                    artifact_stage, artifact_identity, artifact_members
                )
            if source_stage.exists():
                source_members = {
                    entry.name: _identity(entry, directory=False)
                    for entry in source_stage.iterdir()
                }
                _discard_owned_directory(
                    source_stage, source_stage_identity, source_members
                )
        except Exception as cleanup_error:
            primary_error.add_note(f"private-stage cleanup failed: {cleanup_error}")
        raise


def _rollback_promotions(
    promoted: Sequence[tuple[Path, Path, tuple[int, int], bool]],
) -> None:
    for stage, final, identity, directory in reversed(promoted):
        if not _has_identity(final, identity, directory=directory):
            raise OfficialBuildsError(
                f"refusing rollback of substituted published path: {final}"
            )
        if stage.exists() or stage.is_symlink():
            raise OfficialBuildsError(
                f"refusing rollback over occupied private stage: {stage}"
            )
        _promote_noreplace(final, stage)
        if not _has_identity(stage, identity, directory=directory):
            raise OfficialBuildsError(f"rollback failed to restore private inode: {stage}")


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
                raise OfficialBuildsError(f"source identity changed on promotion: {name}")
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
            raise OfficialBuildsError("artifact identity changed on promotion")
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
        raise OfficialBuildsError("both capture origin and Trash destination exist")
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(CAPTURE_TRASH)


def _default_recorded_at() -> str:
    target = math.ceil(time.time() + 20.0)
    return datetime.fromtimestamp(target, UTC).isoformat().replace("+00:00", "Z")


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    """Publish the five sources and assessment under the temporal contract."""

    target_text = recorded_at or _default_recorded_at()
    final_paths = tuple(SOURCES_ROOT / name for name in SOURCE_FILENAMES) + (ARTIFACT,)
    _require_finals_absent(final_paths, "initial")
    _validate_source_collisions()
    _validate_v71_nonmutation()
    capture_directory = CAPTURE_ORIGIN if CAPTURE_ORIGIN.exists() else CAPTURE_TRASH
    _validate_capture_directory(capture_directory)
    with _publication_lock():
        _require_finals_absent(final_paths, "locked initial")
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
    _validate_v71_nonmutation()
    manifest = validate_artifact(ARTIFACT)
    source_records = _validate_sources(_source_paths(SOURCES_ROOT))
    return {
        "artifact_id": ARTIFACT_ID,
        "recorded_at": manifest["recorded_at"],
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "source_records": source_records,
        "counts": {
            "candidates": 6,
            "source_records": 5,
            "seed_eligible": 4,
            "historical_only": 1,
            "review_only": 1,
            "evidence": 8,
            "entities": 10,
            "lifecycle": 6,
            "operating_models": 3,
            "workloads": 0,
            "capacities": 2,
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
