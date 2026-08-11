"""Freeze the governed review of four unresolved official-build candidates.

This artifact is deliberately separate from open-seed publication.  Fresh,
credential-free captures are retained only as a hash-pinned all-rights-reserved
directory in Trash.  The published artifact contains compact transport facts,
hashes, and explicit review dispositions; it emits no curated source record and
no normalized or seeded row.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping

from .external_captures import resolve_external_capture
from . import global_official_builds_next_tranche_20260721 as publication
from .open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "global-official-builds-unresolved-four-2026-07-21-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".global-official-builds-unresolved-four-20260721.lock"

CAPTURE_ORIGIN = Path("/private/tmp/dc-unresolved-four-20260721.VMKPdG")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-unresolved-four-20260721.VMKPdG")
CAPTURE_TREE_SHA256 = (
    "f577bc084d5fc27c5f99eea6d8f3d144a338a965187361f5cd321920e52eeb21"
)
CAPTURE_FILE_COUNT = 95
CAPTURE_TOTAL_BYTES = 2_104_407
CAPTURE_DIRECTORY_MODE = 0o700
CAPTURE_FILE_MODE = 0o644

V84_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v84.json"
V84_RELEASE = ROOT / "releases/2026-07-21-open-seed-v84"
V84_MANIFEST = V84_RELEASE / "manifest.json"
V84_ENTITIES = V84_RELEASE / "entities.csv"
V84_PINS = {
    V84_DEFINITION: (
        100_280,
        "910b2f0d830106b274d8ec22849e2d637463ea5fc57c3481aca2d468218bf8ef",
    ),
    V84_MANIFEST: (
        15_118,
        "0c4b7b3979c5c3bcdfb3a9bef38b5b32f4da5df31633a0c38920ef937914e301",
    ),
    V84_ENTITIES: (
        967_751,
        "89413800f6fa000b6efe1c37335a3ce6bf2ab307497d5604372cc8eed07dc213",
    ),
}
V84_RECORDED_AT = "2026-07-21T19:10:20Z"
V84_TREE_SHA256 = "3ec1197343778c51609221aedbac6f4bf8942cb6620c80fc857b7b1f3124e52b"
V84_INPUT_COUNT = 447

HANNAM_UNIVERSITY_MOU_URL = (
    "https://www.hannam.ac.kr/kor/community/community_01_2.html?"
    "pPageNo=1&pPostNo=197577&pRowCount=12"
)
HANNAM_MAGAZINE_URL = (
    "https://www.hannam.ac.kr/kor/community/community_01_11.html?"
    "isGongjiPostList=N&pPostNo=200585"
)
DAEJEON_MOU_URL = (
    "https://www.daejeon.go.kr/drh/depart/board/boardNormalView.do?"
    "boardId=normal_0189&menuSeq=1632&ntatcSeq=1504086780&pageIndex=4"
)
HANNAM_MROD_URL = "https://mrod.kr/news/?bmode=view&idx=170977271"
EGAI_ROOT_URL = "https://egai.us/"
EGAI_ABOUT_URL = "https://egai.us/about/"
EGAI_DATA_CENTER_URL = "https://egai.us/data-center/"
EGAI_RICE_PRESENTATION_URL = (
    "https://ricetx.gov/images/images_mi/"
    "mi_81_EG_AI_Corp_Rice_TX_Community_1352902479_8919.pdf"
)
QTS_FAST41_URL = (
    "https://www.permits.performance.gov/permitting-project/"
    "fast-41-covered-projects/"
    "qts-richmond-technology-park-data-center-5-ric5"
)
QTS_AGENCY_POSTING_URL = (
    "https://www.permits.performance.gov/"
    "fast-41-covered-projects-postings-agencies-"
    "qts-richmond-technology-park-data-center-5-ric5"
)
QTS_PERMITTING_PRESS_URL = (
    "https://www.permitting.gov/newsroom/press-releases/"
    "first-data-center-project-gains-permitting-councils-fast-41-coverage"
)
QTS_USACE_URL = (
    "https://www.nao.usace.army.mil/Media/Public-Notices/Article/4510991/"
    "nao-2021-02695-qts-ric-5-henrico-virginia/"
)
SEGRO_UPDATE_URL = (
    "https://www.segro.com/media/news/2026/"
    "160326-segro-plc-segro-data-centre-update"
)
SEGRO_TRADING_UPDATE_URL = (
    "https://www.segro.com/en/investors/financial-results-centre/trading-update"
)

REQUEST_SPECS: dict[str, dict[str, Any]] = {
    "daejeon_mou": {
        "candidate_id": "hannam-ax-cluster-ai-gpu-hub-daejeon",
        "classification": "first_party_city_mou_program_page",
        "requested_url": DAEJEON_MOU_URL,
        "expected_http_status": 200,
    },
    "egai_about": {
        "candidate_id": "eg-ai-corp-dallas-immersion-gpu-facility",
        "classification": "first_party_operator_current_state_and_roadmap_page",
        "requested_url": EGAI_ABOUT_URL,
        "expected_http_status": 200,
    },
    "egai_data_center": {
        "candidate_id": "eg-ai-corp-dallas-immersion-gpu-facility",
        "classification": "first_party_operator_planned_facility_page",
        "requested_url": EGAI_DATA_CENTER_URL,
        "expected_http_status": 200,
    },
    "egai_rice_presentation": {
        "candidate_id": "eg-ai-corp-dallas-immersion-gpu-facility",
        "classification": "municipal_hosted_operator_community_presentation",
        "requested_url": EGAI_RICE_PRESENTATION_URL,
        "expected_http_status": 200,
    },
    "egai_root": {
        "candidate_id": "eg-ai-corp-dallas-immersion-gpu-facility",
        "classification": "first_party_operator_marketing_homepage",
        "requested_url": EGAI_ROOT_URL,
        "expected_http_status": 200,
    },
    "hannam_march_magazine": {
        "candidate_id": "hannam-ax-cluster-ai-gpu-hub-daejeon",
        "classification": "first_party_university_program_page",
        "requested_url": HANNAM_MAGAZINE_URL,
        "expected_http_status": 200,
    },
    "hannam_mou": {
        "candidate_id": "hannam-ax-cluster-ai-gpu-hub-daejeon",
        "classification": "first_party_university_mou_page",
        "requested_url": HANNAM_UNIVERSITY_MOU_URL,
        "expected_http_status": 200,
    },
    "hannam_mrod_groundbreaking": {
        "candidate_id": "hannam-ax-cluster-ai-gpu-hub-daejeon",
        "classification": "named_participant_hosted_ceremony_article",
        "requested_url": HANNAM_MROD_URL,
        "expected_http_status": 200,
    },
    "qts_agency_posting": {
        "candidate_id": "qts-richmond-technology-park-dc5-ric5",
        "classification": "required_fast41_agency_posting_default_curl",
        "requested_url": QTS_AGENCY_POSTING_URL,
        "expected_http_status": 403,
    },
    "qts_agency_posting_browser": {
        "candidate_id": "qts-richmond-technology-park-dc5-ric5",
        "classification": "required_fast41_agency_posting_browser_headers",
        "requested_url": QTS_AGENCY_POSTING_URL,
        "expected_http_status": 403,
    },
    "qts_fast41": {
        "candidate_id": "qts-richmond-technology-park-dc5-ric5",
        "classification": "required_fast41_project_page_default_curl",
        "requested_url": QTS_FAST41_URL,
        "expected_http_status": 403,
    },
    "qts_fast41_apex": {
        "candidate_id": "qts-richmond-technology-park-dc5-ric5",
        "classification": "required_fast41_project_page_apex_host_retry",
        "requested_url": QTS_FAST41_URL.replace("www.", ""),
        "expected_http_status": 403,
    },
    "qts_fast41_browser": {
        "candidate_id": "qts-richmond-technology-park-dc5-ric5",
        "classification": "required_fast41_project_page_browser_headers",
        "requested_url": QTS_FAST41_URL,
        "expected_http_status": 403,
    },
    "qts_fast41_http1": {
        "candidate_id": "qts-richmond-technology-park-dc5-ric5",
        "classification": "required_fast41_project_page_http1_ipv4_retry",
        "requested_url": QTS_FAST41_URL,
        "expected_http_status": 403,
    },
    "qts_fast41_query": {
        "candidate_id": "qts-richmond-technology-park-dc5-ric5",
        "classification": "required_fast41_project_page_query_retry",
        "requested_url": f"{QTS_FAST41_URL}?source=direct",
        "expected_http_status": 403,
    },
    "qts_permitting_press": {
        "candidate_id": "qts-richmond-technology-park-dc5-ric5",
        "classification": "first_party_permitting_council_press_release",
        "requested_url": QTS_PERMITTING_PRESS_URL,
        "expected_http_status": 200,
    },
    "qts_usace_public_notice": {
        "candidate_id": "qts-richmond-technology-park-dc5-ric5",
        "classification": "first_party_usace_public_notice_default_curl",
        "requested_url": QTS_USACE_URL,
        "expected_http_status": 403,
    },
    "segro_trading_update": {
        "candidate_id": "segro-slough-powered-shell-prelet-2026",
        "classification": "first_party_developer_trading_update",
        "requested_url": SEGRO_TRADING_UPDATE_URL,
        "expected_http_status": 200,
    },
    "segro_update": {
        "candidate_id": "segro-slough-powered-shell-prelet-2026",
        "classification": "first_party_developer_prelet_announcement",
        "requested_url": SEGRO_UPDATE_URL,
        "expected_http_status": 200,
    },
}
REQUEST_IDS = tuple(REQUEST_SPECS)
CAPTURE_SUFFIXES = ("body", "headers", "retrieved_at", "stderr", "writeout")

BODY_PINS = {
    "hannam_mou": (
        89_073,
        "f88c3e5477ff334ac028c6721453d8bf6eb5dc1133a0694bf2884ed92306a0c0",
    ),
    "hannam_march_magazine": (
        89_502,
        "64527e464582238d50d33ad05ba21e851efb99d76770743261508a34b6bc6da7",
    ),
    "daejeon_mou": (
        160_089,
        "81dbf51d02af2fe956b473eb4ebce6a6f4a6b2e9833d2fb14a45d13648ccc0a1",
    ),
    "hannam_mrod_groundbreaking": (
        334_479,
        "05fa9cf64a6b306ffdd20c8e1a8a030bf905be6793cc669524563990588404b7",
    ),
    "egai_root": (
        23_714,
        "1ed2acda765248d06139228f44d4126bb55b7babd2bb1c72db87abf973e07367",
    ),
    "egai_about": (
        27_638,
        "fd7d1ac3b60d4e1175bcd57ff9de8095835f9b9bc63ddf7bd5e2a37040958466",
    ),
    "egai_data_center": (
        20_442,
        "5913e8fb690ee0ee02091ca124e05b3f4e1c2cedeabbf9c2ac29853c8468801a",
    ),
    "egai_rice_presentation": (
        795_036,
        "c462e44a32172cccc297f74fcec8d77979bcbca484ccbf00237be836ad7250d2",
    ),
    "qts_permitting_press": (
        43_930,
        "786fd68b180c1e7a396d211d86e9a7dd3bff343a067039eea5d0ad7807f35651",
    ),
    "segro_update": (
        112_873,
        "d1e5208631dbc8fb9013f4ef3335e62e1c588fc343a19a968d1d31f82bef54e2",
    ),
    "segro_trading_update": (
        111_942,
        "8f7a424155d278ae4dd5793049da18c04c2736752b0d76c765f4946eb6cafd57",
    ),
}

BODY_MARKERS = {
    "hannam_mou": ("업무협약", "2026년부터 2028년까지"),
    "hannam_mrod_groundbreaking": ("기공식", "기술 협력"),
    "egai_root": ("Planned compute capacity", "2.5MW planned capacity"),
    "egai_about": (
        "3 warehouse sites in Dallas shortlisted for conversion",
        "Complete engineering design and begin construction",
    ),
    "qts_permitting_press": (
        "Once permitted",
        "construction to begin by January 2028",
    ),
    "segro_update": (
        "signed an agreement to develop a powered shell data centre",
        "50MVA of power when fully operational",
    ),
    "segro_trading_update": (
        "30,000 sq m powered shell data centre pre-let",
        "ongoing infrastructure works ahead of a major power upgrade in Slough",
    ),
}

SOURCE_FILENAMES: tuple[str, ...] = ()
CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

COLLISION_TOKENS = (
    "hannam ax cluster",
    "한남대 ax 클러스터",
    "eg ai corp",
    "qts richmond technology park data center 5",
    "qts-richmond-technology-park-dc5-ric5",
    "segro-slough-powered-shell-prelet-2026",
    HANNAM_UNIVERSITY_MOU_URL,
    EGAI_ROOT_URL,
    QTS_FAST41_URL,
    SEGRO_UPDATE_URL,
)


class UnresolvedFourArtifactError(RuntimeError):
    """Raised when evidence, lineage, or publication differs from the contract."""


_canonical = publication._canonical
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
_file_tree = publication._file_tree


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _capture_root() -> Path:
    origin_exists = CAPTURE_ORIGIN.exists()
    if origin_exists and CAPTURE_TRASH.exists():
        raise UnresolvedFourArtifactError(
            "capture origin and Trash destination both exist"
        )
    if origin_exists:
        return CAPTURE_ORIGIN
    return resolve_external_capture(CAPTURE_TRASH)


def _ordinary_file_pin(path: Path) -> tuple[int, str]:
    if path.is_symlink() or not path.is_file():
        raise UnresolvedFourArtifactError(f"capture member is not ordinary: {path}")
    return path.stat().st_size, _sha256(path)


def _validate_capture_directory(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise UnresolvedFourArtifactError("capture root must be an ordinary directory")
    if stat.S_IMODE(root.stat().st_mode) != CAPTURE_DIRECTORY_MODE:
        raise UnresolvedFourArtifactError("capture root mode differs")
    entries = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise UnresolvedFourArtifactError("capture tree contains a non-ordinary member")
    if any(stat.S_IMODE(entry.stat().st_mode) != CAPTURE_FILE_MODE for entry in entries):
        raise UnresolvedFourArtifactError("capture file mode differs")
    if len(entries) != CAPTURE_FILE_COUNT:
        raise UnresolvedFourArtifactError("capture file count differs")
    if sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES:
        raise UnresolvedFourArtifactError("capture byte count differs")
    expected_names = {
        f"{request_id}.{suffix}"
        for request_id in REQUEST_IDS
        for suffix in CAPTURE_SUFFIXES
    }
    if {entry.name for entry in entries} != expected_names:
        raise UnresolvedFourArtifactError("capture closed file set differs")
    if tree_digest(root) != CAPTURE_TREE_SHA256:
        raise UnresolvedFourArtifactError("capture physical tree differs")

    for request_id, spec in REQUEST_SPECS.items():
        metadata = json.loads((root / f"{request_id}.writeout").read_text())
        if (
            metadata.get("url") != spec["requested_url"]
            or metadata.get("http_code") != spec["expected_http_status"]
            or metadata.get("exitcode") != 0
        ):
            raise UnresolvedFourArtifactError(
                f"capture transport differs: {request_id}"
            )
        _instant((root / f"{request_id}.retrieved_at").read_text().strip())

    for request_id, expected in BODY_PINS.items():
        if _ordinary_file_pin(root / f"{request_id}.body") != expected:
            raise UnresolvedFourArtifactError(f"claim body differs: {request_id}")
    for request_id, markers in BODY_MARKERS.items():
        body_text = (root / f"{request_id}.body").read_text(
            encoding="utf-8", errors="strict"
        )
        if any(marker not in body_text for marker in markers):
            raise UnresolvedFourArtifactError(
                f"claim boundary marker absent: {request_id}"
            )


def _request_row(root: Path, request_id: str) -> dict[str, Any]:
    spec = REQUEST_SPECS[request_id]
    metadata = json.loads((root / f"{request_id}.writeout").read_text())
    body = root / f"{request_id}.body"
    headers = root / f"{request_id}.headers"
    stderr = root / f"{request_id}.stderr"
    retrieved_at = (root / f"{request_id}.retrieved_at").read_text().strip()
    http_200 = metadata.get("http_code") == 200
    return {
        "request_id": request_id,
        "candidate_id": spec["candidate_id"],
        "classification": spec["classification"],
        "requested_url": spec["requested_url"],
        "effective_url": metadata.get("url_effective"),
        "retrieved_at": retrieved_at,
        "curl_exit_code": metadata.get("exitcode"),
        "http_status": metadata.get("http_code"),
        "http_version": metadata.get("http_version"),
        "content_type": metadata.get("content_type"),
        "content_encoding_as_received": metadata.get("content_encoding"),
        "wire_download_bytes": metadata.get("size_download"),
        "decoded_body_bytes": body.stat().st_size,
        "decoded_body_sha256": _sha256(body),
        "headers_bytes": headers.stat().st_size,
        "headers_sha256": _sha256(headers),
        "stderr_bytes": stderr.stat().st_size,
        "stderr_sha256": _sha256(stderr),
        "redirect_count": metadata.get("num_redirects"),
        "time_connect_seconds": metadata.get("time_connect"),
        "time_total_seconds": metadata.get("time_total"),
        "credentials_supplied": False,
        "network_timeout_contract": "connect_timeout_10s_wall_clock_timeout_45s",
        "identity_bound_http_200_body": http_200,
        "eligible_for_candidate_review": http_200,
        "direct_physical_work_observation": False,
        "eligible_for_normalized_claims": False,
        "used_for_normalized_claims": False,
        "source_record_created": False,
        "raw_redistributed": False,
    }


def _retrieval_inventory(recorded_at: str) -> dict[str, Any]:
    root = _capture_root()
    rows = [_request_row(root, request_id) for request_id in REQUEST_IDS]
    return {
        "format": "datacenter-atlas-unresolved-four-retrieval-inventory-v1",
        "recorded_at": recorded_at,
        "retrieval_attempt_count": len(rows),
        "successful_http_200_decoded_body_count": sum(
            row["http_status"] == 200 for row in rows
        ),
        "failed_http_403_body_count": sum(row["http_status"] == 403 for row in rows),
        "direct_physical_work_body_count": 0,
        "claim_eligible_capture_count": 0,
        "request_credentials_supplied": False,
        "network_timeout_contract": "connect_timeout_10s_wall_clock_timeout_45s",
        "search_snippets_used_for_claims": False,
        "transformed_web_text_used_for_claims": False,
        "publisher_media_used_for_claims": False,
        "requests": rows,
        "qts_required_page_boundary": {
            "required_url": QTS_FAST41_URL,
            "default_http_status": 403,
            "bounded_variants_attempted": 7,
            "identity_bound_http_200_body_captured": False,
            "separate_first_party_press_request_id": "qts_permitting_press",
            "press_body_http_status": 200,
            "press_body_boundary": (
                "The Permitting Council body says construction is anticipated only "
                "after permitting, by January 2028; it does not prove physical work."
            ),
        },
        "raw_capture": {
            "origin": str(CAPTURE_ORIGIN),
            "trash_destination": str(CAPTURE_TRASH),
            "file_count": CAPTURE_FILE_COUNT,
            "total_bytes": CAPTURE_TOTAL_BYTES,
            "physical_tree_sha256": CAPTURE_TREE_SHA256,
            "retained_in_artifact": False,
            "moved_intact_to_trash": True,
        },
    }


def _empty_normalized_contract() -> dict[str, Any]:
    return {
        "source_record_created": False,
        "seed_eligible": False,
        "seeded": False,
        "entity_rows": 0,
        "evidence_rows": 0,
        "lifecycle_rows": 0,
        "operating_model_rows": 0,
        "workload_rows": 0,
        "capacity_rows": 0,
        "coordinates_present": False,
        "geometry_present": False,
        "confirmed_current_status": False,
        "current_status": "unknown",
    }


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    empty = _empty_normalized_contract()
    candidates = [
        {
            "candidate_id": "hannam-ax-cluster-ai-gpu-hub-daejeon",
            "candidate_name": (
                "Hannam University AX Cluster / high-performance AI GPU hub center"
            ),
            "country": "South Korea",
            "locality_candidate": "Daejeon",
            "decision": (
                "review_only_ceremonial_groundbreaking_without_physical_work_observation"
            ),
            "first_party_request_ids": [
                "hannam_mou",
                "hannam_march_magazine",
                "daejeon_mou",
                "hannam_mrod_groundbreaking",
            ],
            "source_native_process_facts": {
                "university_and_city_pages": "MOU and planned 2026-2028 program",
                "named_participant_page": (
                    "MROD-hosted article says it attended an April 16 ceremony and "
                    "will pursue technical cooperation"
                ),
                "ceremony_is_physical_work_observation": False,
            },
            "direct_physical_work_body_available": False,
            "withheld_claims": [
                "under_construction or any other physical lifecycle status",
                "320,000 GPU count or GPU model",
                "GPU count converted to MW or any power metric",
                "project cost, financing, or current energy consumption",
                "EMP protection, certification, operator, tenant, or workload enum",
                "coordinates or geometry",
            ],
            "normalized": dict(empty),
        },
        {
            "candidate_id": "eg-ai-corp-dallas-immersion-gpu-facility",
            "candidate_name": "EG AI Corp planned immersion-cooled GPU facility",
            "country": "United States",
            "locality_candidate": "Dallas / Rice, Texas",
            "decision": "review_only_operator_future_intent_without_physical_start",
            "first_party_request_ids": [
                "egai_root",
                "egai_about",
                "egai_data_center",
                "egai_rice_presentation",
            ],
            "source_native_process_facts": {
                "operator_current_state_text": (
                    "3 warehouse sites in Dallas shortlisted for conversion"
                ),
                "operator_roadmap_text": (
                    "complete engineering design and begin construction"
                ),
                "municipal_hosted_presentation_locality": "Rice, Texas",
            },
            "planned_power_candidate_metadata": {
                "source_native_text": "2.5 MW planned compute capacity",
                "value": 2.5,
                "unit": "MW",
                "metric_type": "unspecified",
                "is_it_load": None,
                "is_facility_power": None,
                "is_current_load": False,
                "normalized_capacity_row_created": False,
            },
            "direct_physical_work_body_available": False,
            "withheld_claims": [
                "under_construction, groundbreaking, or any physical lifecycle status",
                "2.5 MW as IT load, facility power, utility capacity, or consumption",
                "current energy use, PUE, cooling savings, or GPU count",
                "single-tenant operating model or workload enum",
                "exact site identity, address, coordinates, or geometry",
                "completion, operator readiness, customer, or tenant",
            ],
            "normalized": dict(empty),
        },
        {
            "candidate_id": "qts-richmond-technology-park-dc5-ric5",
            "candidate_name": "QTS Richmond Technology Park Data Center 5 (RIC5)",
            "country": "United States",
            "locality_candidate": "Henrico County / Richmond, Virginia",
            "decision": "review_only_permitting_in_progress_before_future_construction",
            "required_request_ids": [
                "qts_fast41",
                "qts_fast41_browser",
                "qts_fast41_http1",
                "qts_fast41_query",
                "qts_fast41_apex",
                "qts_agency_posting",
                "qts_agency_posting_browser",
            ],
            "required_page_http_status": 403,
            "separate_first_party_request_id": "qts_permitting_press",
            "source_native_process_facts": {
                "process": "FAST-41 environmental review and permitting",
                "construction_timing_text": (
                    "Once permitted, the sponsor anticipates construction to begin "
                    "by January 2028"
                ),
            },
            "coordinate_candidate_metadata": {
                "latitude": 37.505653,
                "longitude": -77.265146,
                "scope": "required FAST-41 project-page candidate metadata",
                "required_body_captured": False,
                "verified_in_captured_body": False,
                "seeded": False,
                "geometry_created": False,
            },
            "direct_physical_work_body_available": False,
            "withheld_claims": [
                "under_construction or any physical lifecycle status",
                "coordinate normalization or geometry",
                "capacity, current load, energy consumption, PUE, or cooling",
                "tenant, operator, workload enum, or completion",
            ],
            "normalized": dict(empty),
        },
        {
            "candidate_id": "segro-slough-powered-shell-prelet-2026",
            "candidate_name": "SEGRO Slough Trading Estate powered-shell pre-let",
            "country": "United Kingdom",
            "locality_candidate": "Slough",
            "decision": "review_only_prelet_without_project_specific_physical_work",
            "first_party_request_ids": ["segro_update", "segro_trading_update"],
            "source_native_process_facts": {
                "agreement": "agreement to develop a powered shell data centre",
                "building_area_when_complete": "30,000 sq m",
                "power_when_fully_operational": "50MVA",
                "separate_project_excluded": (
                    "SEGRO Pure Premier Park planning approval in West London"
                ),
                "slough_power_upgrade_scope": (
                    "estate-level infrastructure works, not a physical observation "
                    "for this powered-shell project"
                ),
            },
            "power_candidate_metadata": {
                "source_native_text": "50MVA of power when fully operational",
                "value": 50,
                "unit": "MVA",
                "converted_to_mw": False,
                "is_it_load": None,
                "is_current_load": False,
                "normalized_capacity_row_created": False,
            },
            "direct_physical_work_body_available": False,
            "withheld_claims": [
                "under_construction or any physical lifecycle status",
                "50 MVA converted to MW or IT load",
                "current energy consumption, PUE, cooling, or workload enum",
                "tenant identity, coordinates, geometry, or completion",
            ],
            "normalized": dict(empty),
        },
    ]
    return {
        "format": "datacenter-atlas-unresolved-four-candidate-assessment-v1",
        "recorded_at": recorded_at,
        "candidate_count": len(candidates),
        "curated_source_record_count": 0,
        "seed_eligible_count": 0,
        "review_only_count": len(candidates),
        "current_status_unknown_count": len(candidates),
        "capacity_row_count": 0,
        "coordinate_row_count": 0,
        "source_records": [],
        "candidates": candidates,
        "global_completeness_claimed": False,
        "unique_physical_site_count": None,
        "semi_analysis_parity_claimed": False,
    }


def _rights_and_disposition(recorded_at: str) -> dict[str, Any]:
    return {
        "format": "datacenter-atlas-arr-capture-disposition-v1",
        "recorded_at": recorded_at,
        "rights_assumption": "all-rights-reserved_no_open_reuse_grant",
        "published_material": "compact factual request metadata and hashes only",
        "raw_bodies_published": False,
        "raw_headers_published": False,
        "raw_stderr_published": False,
        "publisher_images_published": False,
        "raw_capture_directory": {
            "origin": str(CAPTURE_ORIGIN),
            "trash_destination": str(CAPTURE_TRASH),
            "file_count": CAPTURE_FILE_COUNT,
            "total_bytes": CAPTURE_TOTAL_BYTES,
            "physical_tree_sha256": CAPTURE_TREE_SHA256,
            "moved_intact_to_trash": True,
        },
        "search_snippets_substituted_for_bodies": False,
        "transformed_proxy_text_used": False,
        "satellite_or_cv_used": False,
    }


def _validate_v84_nonmutation() -> dict[str, Any]:
    for path, expected in V84_PINS.items():
        _pin(path, expected)
        if stat.S_IMODE(path.stat().st_mode) != 0o444:
            raise UnresolvedFourArtifactError(f"v84 file mode differs: {path}")
    if V84_RELEASE.is_symlink() or not V84_RELEASE.is_dir():
        raise UnresolvedFourArtifactError("v84 release directory is absent")
    if stat.S_IMODE(V84_RELEASE.stat().st_mode) != 0o555:
        raise UnresolvedFourArtifactError("v84 release mode differs")
    if tree_digest(V84_RELEASE) != V84_TREE_SHA256:
        raise UnresolvedFourArtifactError("v84 release tree differs")
    manifest = json.loads(V84_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("recorded_at") != V84_RECORDED_AT:
        raise UnresolvedFourArtifactError("v84 recorded_at differs")
    definition = json.loads(V84_DEFINITION.read_text(encoding="utf-8"))
    selected = definition.get("curated_inputs")
    if not isinstance(selected, list) or len(selected) != V84_INPUT_COUNT:
        raise UnresolvedFourArtifactError("v84 selected input count differs")

    tokens = tuple(token.casefold() for token in COLLISION_TOKENS)
    selected_paths: list[str] = []
    for row in selected:
        relative = row.get("path")
        if not isinstance(relative, str):
            raise UnresolvedFourArtifactError("v84 selected input path differs")
        selected_paths.append(relative)
        source = ROOT / relative
        if source.is_symlink() or not source.is_file():
            raise UnresolvedFourArtifactError(f"v84 selected source absent: {relative}")
        searchable = f"{relative}\n{source.read_text(encoding='utf-8')}".casefold()
        if any(token in searchable for token in tokens):
            raise UnresolvedFourArtifactError(
                f"planned candidate collides with v84 source: {relative}"
            )
    release_searchable = V84_ENTITIES.read_text(encoding="utf-8").casefold()
    if any(token in release_searchable for token in tokens):
        raise UnresolvedFourArtifactError("planned candidate collides with v84 release")
    return {
        "definition_bytes": V84_PINS[V84_DEFINITION][0],
        "definition_sha256": V84_PINS[V84_DEFINITION][1],
        "manifest_bytes": V84_PINS[V84_MANIFEST][0],
        "manifest_sha256": V84_PINS[V84_MANIFEST][1],
        "entities_bytes": V84_PINS[V84_ENTITIES][0],
        "entities_sha256": V84_PINS[V84_ENTITIES][1],
        "release_tree_sha256": V84_TREE_SHA256,
        "recorded_at": V84_RECORDED_AT,
        "selected_input_count": len(selected_paths),
        "candidate_alias_collision_count": 0,
        "candidate_url_collision_count": 0,
    }


def _source_snapshot(recorded_at: str) -> dict[str, Any]:
    return {
        "format": "datacenter-atlas-unresolved-four-source-snapshot-v1",
        "recorded_at": recorded_at,
        "source_records": [],
        "planned_source_filenames": [],
        "normalized_counts": {
            "entities": 0,
            "evidence": 0,
            "lifecycle": 0,
            "operating_models": 0,
            "workloads": 0,
            "capacities": 0,
            "coordinates": 0,
            "geometry": 0,
        },
        "v84": _validate_v84_nonmutation(),
        "integration": {
            "open_seed_successor_created": False,
            "v84_mutated": False,
            "v85_mutated": False,
            "release_integration": "none",
            "downstream_product_integration": "none",
            "reason": "all four candidates remain governed review-only",
        },
        "unique_physical_site_count": None,
        "semi_analysis_parity_claimed": False,
    }


def _readme(recorded_at: str) -> bytes:
    return (
        "# Four-candidate unresolved official-build audit\n\n"
        f"Recorded at `{recorded_at}`.\n\n"
        "Fresh first-party and official-host bodies were captured for Hannam, EG AI, "
        "QTS, and SEGRO. None proves project-specific physical work. Hannam's named "
        "participant page records a ceremonial groundbreaking and future cooperation, "
        "not an observable physical milestone. EG AI's current-state page says three "
        "warehouse sites are shortlisted and its construction language remains roadmap "
        "text. QTS is in permitting and the Permitting Council says construction is "
        "anticipated only after permitting. SEGRO reports a powered-shell pre-let and "
        "separate Slough power-upgrade works, not physical work on the pre-let project.\n\n"
        "All four candidates are review-only. The source-native 2.5 MW planned-compute "
        "label remains an untyped candidate fact; 50 MVA is not converted to MW or IT "
        "load; GPU counts are not converted to power. No source JSON, entity, evidence, "
        "lifecycle, role, model, workload, capacity, coordinate, geometry, energy, PUE, "
        "tenant, or current-status row is emitted.\n\n"
        "Raw all-rights-reserved captures are not redistributed. Their single closed "
        "directory was moved intact to Trash and is pinned by file count, byte count, "
        "and a mode/path/content tree digest. Open seed v84 is hash-pinned and unchanged; "
        "v85 is not mutated or integrated. This artifact makes no completeness, "
        "unique-site, or SemiAnalysis parity claim.\n"
    ).encode("utf-8")


def _artifact_documents(recorded_at: str) -> dict[str, bytes]:
    return {
        "README.md": _readme(recorded_at),
        "candidate-assessment.json": _canonical(_candidate_assessment(recorded_at)),
        "retrieval-inventory.json": _canonical(_retrieval_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(
            _rights_and_disposition(recorded_at)
        ),
        "source-snapshot.json": _canonical(_source_snapshot(recorded_at)),
    }


def _write_artifact_stage(stage: Path, recorded_at: str) -> None:
    payloads = _artifact_documents(recorded_at)
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
        "candidate_assessments": 4,
        "curated_source_records": 0,
        "seed_eligible_source_records": 0,
        "review_only_candidates": 4,
        "successful_http_200_decoded_bodies": 11,
        "direct_physical_work_bodies": 0,
        "claim_eligible_capture_count": 0,
        "raw_capture_redistributed": False,
        "raw_capture_directory_moved_intact_to_trash": True,
        "search_snippets_used_for_claims": False,
        "open_seed_successor_created": False,
        "v84_mutated": False,
        "v85_mutated": False,
        "release_integration": "none",
        "downstream_product_integration": "none",
        "unique_physical_site_count": None,
        "semi_analysis_parity_claimed": False,
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


def _all_stage_paths(stage: Path) -> tuple[Path, ...]:
    return (stage, *tuple(stage.iterdir()))


def _max_capture_timestamp() -> datetime:
    root = _capture_root()
    timestamps = [
        _instant(member.read_text(encoding="utf-8").strip())
        for member in root.glob("*.retrieved_at")
    ]
    if len(timestamps) != len(REQUEST_IDS):
        raise UnresolvedFourArtifactError("capture timestamps are incomplete")
    return max(timestamps)


def validate_artifact(
    path: Path = ARTIFACT,
    *,
    require_live: bool = True,
    wall_clock: datetime | None = None,
) -> dict[str, Any]:
    _validate_v84_nonmutation()
    _validate_capture_directory(_capture_root())
    if path.is_symlink() or not path.is_dir():
        raise UnresolvedFourArtifactError("artifact must be an ordinary directory")
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise UnresolvedFourArtifactError("artifact closed file set differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries.values()):
        raise UnresolvedFourArtifactError("artifact contains a non-ordinary file")
    if stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise UnresolvedFourArtifactError("artifact directory mode differs")
    if any(stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries.values()):
        raise UnresolvedFourArtifactError("artifact file mode differs")

    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest):
        raise UnresolvedFourArtifactError("manifest JSON is not canonical")
    if (
        manifest.get("artifact_id") != ARTIFACT_ID
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or manifest.get("candidate_assessments") != 4
        or manifest.get("curated_source_records") != 0
        or manifest.get("seed_eligible_source_records") != 0
        or manifest.get("review_only_candidates") != 4
        or manifest.get("successful_http_200_decoded_bodies") != 11
        or manifest.get("direct_physical_work_bodies") != 0
        or manifest.get("claim_eligible_capture_count") != 0
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("v84_mutated") is not False
        or manifest.get("v85_mutated") is not False
        or manifest.get("release_integration") != "none"
        or manifest.get("downstream_product_integration") != "none"
        or manifest.get("semi_analysis_parity_claimed") is not False
        or manifest.get("unique_physical_site_count") is not None
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise UnresolvedFourArtifactError("manifest contract differs")
    if [row["path"] for row in manifest["files"]] != list(CONTENT_FILES):
        raise UnresolvedFourArtifactError("manifest file order differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (row["bytes"], row["sha256"]):
            raise UnresolvedFourArtifactError(
                f"manifest file pin differs: {row['path']}"
            )
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise UnresolvedFourArtifactError("manifest checksum differs")
    expected = _artifact_documents(manifest["recorded_at"])
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected[name]:
            raise UnresolvedFourArtifactError(f"artifact content differs: {name}")

    target = _instant(manifest["recorded_at"])
    if target <= _instant(V84_RECORDED_AT):
        raise UnresolvedFourArtifactError("artifact does not post-date v84")
    if target < _max_capture_timestamp():
        raise UnresolvedFourArtifactError("artifact predates capture completion")
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise UnresolvedFourArtifactError("validation wall clock lacks timezone")
    if require_live:
        if now.astimezone(UTC) < target:
            raise UnresolvedFourArtifactError("artifact recorded_at is not live")
        if CAPTURE_ORIGIN.exists():
            raise UnresolvedFourArtifactError("raw capture was not moved to Trash")
        resolve_external_capture(CAPTURE_TRASH)
        _assert_final_ctimes((path,), target)
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
        raise UnresolvedFourArtifactError("publication lock already exists") from error
    os.close(descriptor)
    try:
        yield
    finally:
        try:
            PUBLICATION_LOCK.unlink()
        except FileNotFoundError:
            pass


@dataclass(frozen=True)
class _PreparedPublication:
    recorded_at: str
    target: datetime
    stage: Path
    stage_identity: tuple[int, int]
    member_identities: Mapping[str, tuple[int, int]]


def _prepare_publication(recorded_at: str) -> _PreparedPublication:
    target = _instant(recorded_at)
    if target <= _instant(V84_RECORDED_AT):
        raise UnresolvedFourArtifactError("recorded_at must post-date v84")
    if target < _max_capture_timestamp():
        raise UnresolvedFourArtifactError("recorded_at predates capture completion")
    stage = Path(
        tempfile.mkdtemp(
            dir=ARTIFACT_ROOT,
            prefix=f".{ARTIFACT_ID}.stage-",
        )
    )
    stage.chmod(0o700)
    stage_identity = _identity(stage, directory=True)
    try:
        _write_artifact_stage(stage, recorded_at)
        validate_artifact(
            stage,
            require_live=False,
            wall_clock=datetime.now(UTC),
        )
        _require_finals_absent((ARTIFACT,), "staging")
        _assert_stage_precedes_target(_all_stage_paths(stage), target)
        if datetime.now(UTC) >= target:
            raise UnresolvedFourArtifactError(
                "private staging did not finish before recorded_at"
            )
        return _PreparedPublication(
            recorded_at=recorded_at,
            target=target,
            stage=stage,
            stage_identity=stage_identity,
            member_identities={
                name: _identity(stage / name, directory=False) for name in CLOSED_FILES
            },
        )
    except BaseException as primary_error:
        try:
            if stage.exists():
                members = {
                    entry.name: _identity(entry, directory=False)
                    for entry in stage.iterdir()
                }
                _discard_owned_directory(stage, stage_identity, members)
        except Exception as cleanup_error:
            primary_error.add_note(f"private-stage cleanup failed: {cleanup_error}")
        raise


def _cleanup_prepared(prepared: _PreparedPublication) -> None:
    if prepared.stage.exists():
        _discard_owned_directory(
            prepared.stage,
            prepared.stage_identity,
            prepared.member_identities,
        )


def _move_capture_to_trash() -> None:
    if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
        raise UnresolvedFourArtifactError(
            "capture origin and Trash destination both exist"
        )
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH))


def _publish(prepared: _PreparedPublication) -> None:
    _require_finals_absent((ARTIFACT,), "pre-wait")
    _wait_until(prepared.target.timestamp())
    _require_finals_absent((ARTIFACT,), "publication")
    _assert_stage_precedes_target(_all_stage_paths(prepared.stage), prepared.target)
    promoted: list[tuple[Path, Path, tuple[int, int], bool]] = []
    try:
        _promote_noreplace(prepared.stage, ARTIFACT)
        promoted.append((prepared.stage, ARTIFACT, prepared.stage_identity, True))
        if not _has_identity(ARTIFACT, prepared.stage_identity, directory=True):
            raise UnresolvedFourArtifactError("artifact identity changed on promotion")
        _assert_final_ctimes((ARTIFACT,), prepared.target)
    except BaseException as primary_error:
        try:
            _rollback_promotions(promoted)
        except Exception as rollback_error:
            primary_error.add_note(f"identity-safe rollback failed: {rollback_error}")
        raise


def _default_recorded_at() -> str:
    target = math.ceil(time.time() + 25.0)
    return datetime.fromtimestamp(target, UTC).isoformat().replace("+00:00", "Z")


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    """Publish the closed four-candidate review artifact exactly once."""

    target_text = recorded_at or _default_recorded_at()
    _require_finals_absent((ARTIFACT,), "initial")
    _validate_v84_nonmutation()
    _validate_capture_directory(_capture_root())
    with _publication_lock():
        _require_finals_absent((ARTIFACT,), "locked initial")
        prepared = _prepare_publication(target_text)
        published = False
        try:
            _move_capture_to_trash()
            _publish(prepared)
            published = True
        finally:
            if not published:
                _cleanup_prepared(prepared)
    _validate_capture_directory(resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH))
    _validate_v84_nonmutation()
    manifest = validate_artifact(ARTIFACT)
    return {
        "artifact_id": ARTIFACT_ID,
        "recorded_at": manifest["recorded_at"],
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "logical_tree_sha256": manifest["tree_sha256"],
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "source_records": [],
        "counts": {
            "candidates": 4,
            "source_records": 0,
            "seed_eligible": 0,
            "review_only": 4,
            "entities": 0,
            "evidence": 0,
            "lifecycle": 0,
            "operating_models": 0,
            "workloads": 0,
            "capacities": 0,
            "coordinates": 0,
            "geometry": 0,
        },
        "capture_directory": str(CAPTURE_TRASH),
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "v84_tree_sha256": V84_TREE_SHA256,
        "open_seed_successor_created": False,
        "release_integration": "none",
    }


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
