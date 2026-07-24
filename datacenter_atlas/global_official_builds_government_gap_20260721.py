"""Freeze the fail-closed Changle, Sucre, and Fuzhou government audit.

The two claim-bearing publisher pages could not be captured as identity-bound
HTTP 200 bodies under the bounded retrieval contract.  Therefore this artifact
creates no curated source record and no open-seed input.  It retains only
compact request metadata and hashes; all raw all-rights-reserved bytes remain
outside the repository in one hash-pinned Trash directory.
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

from . import global_official_builds_next_tranche_20260721 as publication
from .open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "global-official-builds-government-gap-2026-07-21-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".global-official-builds-government-gap-20260721.lock"

CAPTURE_ORIGIN = Path("/private/tmp/dc-gov-builds-20260721.xwySIb")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-gov-builds-20260721.xwySIb")
CAPTURE_TREE_SHA256 = (
    "602f7568815dba74bcd2f2b04f598dd90a59cbd45cdb9ea7adcbdbcbe6677c6c"
)
CAPTURE_FILE_COUNT = 120
CAPTURE_TOTAL_BYTES = 96_466
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

CHANGLE_REQUIRED_URL = (
    "https://www.fzcl.gov.cn/xjwz/zwgk/zfxxgkzdgz/zdjsxm/jsqk/"
    "202601/t20260119_5273462.htm"
)
CHANGLE_CONTINUITY_URL = (
    "https://www.fzcl.gov.cn/xjwz/zwgk/ghjh/fzgh/202602/"
    "t20260211_5284428.htm"
)
CHANGLE_SUPPLEMENTAL_URL = (
    "https://swt.fujian.gov.cn/xxgk/jgzn/jgcs/zsxdc/tzdt/202601/"
    "t20260122_7084250.htm"
)
BOLIVIA_PROGRESS_URL = (
    "https://www.fiscalia.gob.bo/comunicacion/monitoreo-institucional/"
    "monitoreo-15052026"
)
BOLIVIA_START_URL = (
    "https://www.fiscalia.gob.bo/comunicacion/noticias/"
    "fiscal-general-da-inicio-a-la-construccion-de-una-moderna-infraestructura-"
    "del-data-center-de-clase-mundial-que-transformara-la-justicia-boliviana"
)
FUZHOU_PHASE23_URL = (
    "https://fzxq.fuzhou.gov.cn/xxgk/xqyw/tpxw/202503/"
    "t20250330_4996804.htm"
)

REQUEST_IDS = (
    "bolivia_progress",
    "bolivia_progress_http_root",
    "bolivia_progress_http_www",
    "bolivia_progress_index",
    "bolivia_progress_index_http",
    "bolivia_progress_query",
    "bolivia_start",
    "changle_continuity",
    "changle_http_112_54_42_147",
    "changle_http_121_204_110_23",
    "changle_http_218_106_155_204",
    "changle_https_112_54_42_147",
    "changle_https_121_204_110_23",
    "changle_https_218_106_155_204",
    "changle_progress",
    "changle_progress_http",
    "changle_progress_http_v2",
    "changle_swt_mirror",
    "fiscalia_api_root",
    "fuzhou_phase23",
)
REQUIRED_REQUEST_IDS = frozenset({"changle_progress", "bolivia_progress"})
SUPPLEMENTAL_HTTP_200_ID = "changle_swt_mirror"
CHANGLE_A_RECORDS = ("112.54.42.147", "121.204.110.23", "218.106.155.204")

MIRROR_BODY_PIN = (
    45_346,
    "46903d276adac0ba20c1d9bed6c7f2ddd191ef6bd3613a090c20dd83d2307d26",
)
REJECTED_PROXY_BODY_PIN = (
    371,
    "f18f91c88e088cfb556cd773a3912ec4ce62a7f803ffde5e20015a4406cd2719",
)

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
    "curated:changle-airport-comprehensive-bonded-zone-ai-computing-center",
    "curated:ministerio-publico-sucre-data-center",
    "curated:fuzhou-new-area-compute-center-phase-3",
    "changle airport comprehensive bonded zone ai computing center",
    "长乐机场综保区人工智能智算中心",
    CHANGLE_REQUIRED_URL,
    BOLIVIA_PROGRESS_URL,
)


class GovernmentGapArtifactError(RuntimeError):
    """Raised when capture, lineage, or publication differs from the contract."""


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
    trash_exists = CAPTURE_TRASH.exists()
    if origin_exists and trash_exists:
        raise GovernmentGapArtifactError(
            "capture origin and Trash destination both exist"
        )
    if origin_exists:
        return CAPTURE_ORIGIN
    if trash_exists:
        return CAPTURE_TRASH
    raise GovernmentGapArtifactError("raw capture directory is absent")


def _ordinary_file_pin(path: Path) -> tuple[int, str]:
    if path.is_symlink() or not path.is_file():
        raise GovernmentGapArtifactError(f"capture member is not ordinary: {path}")
    return path.stat().st_size, _sha256(path)


def _validate_capture_directory(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise GovernmentGapArtifactError("capture root must be an ordinary directory")
    if stat.S_IMODE(root.stat().st_mode) != CAPTURE_DIRECTORY_MODE:
        raise GovernmentGapArtifactError("capture root mode differs")
    entries = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise GovernmentGapArtifactError("capture tree contains a non-ordinary member")
    if any(stat.S_IMODE(entry.stat().st_mode) != CAPTURE_FILE_MODE for entry in entries):
        raise GovernmentGapArtifactError("capture file mode differs")
    if len(entries) != CAPTURE_FILE_COUNT:
        raise GovernmentGapArtifactError("capture file count differs")
    if sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES:
        raise GovernmentGapArtifactError("capture byte count differs")
    if tree_digest(root) != CAPTURE_TREE_SHA256:
        raise GovernmentGapArtifactError("capture physical tree differs")
    if _ordinary_file_pin(root / "changle_swt_mirror.body") != MIRROR_BODY_PIN:
        raise GovernmentGapArtifactError("supplemental mirror body differs")
    if _ordinary_file_pin(root / "fiscalia_jina_discovery.body") != (
        REJECTED_PROXY_BODY_PIN
    ):
        raise GovernmentGapArtifactError("rejected proxy body differs")

    for request_id in REQUEST_IDS:
        writeout = root / f"{request_id}.writeout"
        if writeout.is_symlink() or not writeout.is_file():
            raise GovernmentGapArtifactError(f"request writeout absent: {request_id}")
        try:
            metadata = json.loads(writeout.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GovernmentGapArtifactError(
                f"request writeout invalid: {request_id}"
            ) from error
        if not isinstance(metadata, dict):
            raise GovernmentGapArtifactError(f"request writeout shape differs: {request_id}")
        for suffix in ("headers", "stderr"):
            member = root / f"{request_id}.{suffix}"
            if member.is_symlink() or not member.is_file():
                raise GovernmentGapArtifactError(
                    f"request telemetry absent: {request_id}.{suffix}"
                )

    mirror = json.loads((root / "changle_swt_mirror.writeout").read_text())
    if (
        mirror.get("http_code") != 200
        or mirror.get("url_effective") != CHANGLE_SUPPLEMENTAL_URL
        or mirror.get("content_type") != "text/html"
        or mirror.get("size_download") != 12_207
        or mirror.get("num_redirects") != 0
    ):
        raise GovernmentGapArtifactError("supplemental mirror transport differs")
    for request_id in REQUIRED_REQUEST_IDS:
        metadata = json.loads((root / f"{request_id}.writeout").read_text())
        if metadata.get("http_code") != 0 or (root / f"{request_id}.body").exists():
            raise GovernmentGapArtifactError(
                f"required failed-closed request differs: {request_id}"
            )


def _request_classification(request_id: str) -> str:
    if request_id in REQUIRED_REQUEST_IDS:
        return "required_claim_bearing_page"
    if request_id == SUPPLEMENTAL_HTTP_200_ID:
        return "supplemental_date_mismatched_official_mirror"
    if request_id == "fuzhou_phase23":
        return "review_only_phase_2_phase_3_candidate_page"
    if request_id == "changle_continuity":
        return "supplemental_later_continuity_page"
    if request_id.startswith("changle_http_") or request_id.startswith(
        "changle_https_"
    ):
        return "required_page_explicit_a_record_retry"
    if request_id.startswith("changle_progress_http"):
        return "required_page_http_retry"
    if request_id.startswith("bolivia_progress"):
        return "required_page_or_index_retry"
    if request_id == "bolivia_start":
        return "supplemental_earlier_start_page"
    if request_id == "fiscalia_api_root":
        return "non_claim_bearing_first_party_api_discovery"
    raise GovernmentGapArtifactError(f"request classification absent: {request_id}")


def _request_row(root: Path, request_id: str) -> dict[str, Any]:
    metadata = json.loads((root / f"{request_id}.writeout").read_text())
    body = root / f"{request_id}.body"
    headers = root / f"{request_id}.headers"
    stderr = root / f"{request_id}.stderr"
    exit_file = root / f"{request_id}.exit_code"
    started_file = root / f"{request_id}.started_at"
    completed_file = root / f"{request_id}.completed_at"
    classification = _request_classification(request_id)
    forced_resolve_ip = None
    for address in CHANGLE_A_RECORDS:
        if request_id.endswith(address.replace(".", "_")):
            forced_resolve_ip = address
            break
    return {
        "request_id": request_id,
        "classification": classification,
        "requested_url": metadata.get("url"),
        "effective_url": metadata.get("url_effective"),
        "started_at": (
            started_file.read_text(encoding="utf-8").strip()
            if started_file.exists()
            else None
        ),
        "completed_at": (
            completed_file.read_text(encoding="utf-8").strip()
            if completed_file.exists()
            else None
        ),
        "curl_exit_code": (
            int(exit_file.read_text(encoding="utf-8").strip())
            if exit_file.exists()
            else None
        ),
        "http_status": metadata.get("http_code"),
        "http_version": metadata.get("http_version"),
        "content_type": metadata.get("content_type"),
        "wire_download_bytes": metadata.get("size_download"),
        "decoded_body_created": body.exists(),
        "decoded_body_bytes": body.stat().st_size if body.exists() else 0,
        "decoded_body_sha256": _sha256(body) if body.exists() else None,
        "headers_bytes": headers.stat().st_size,
        "headers_sha256": _sha256(headers),
        "stderr_bytes": stderr.stat().st_size,
        "stderr_sha256": _sha256(stderr),
        "redirect_count": metadata.get("num_redirects"),
        "remote_ip": metadata.get("remote_ip") or None,
        "forced_resolve_ip": forced_resolve_ip,
        "time_connect_seconds": metadata.get("time_connect"),
        "time_total_seconds": metadata.get("time_total"),
        "credentials_supplied": False,
        "network_timeout_contract": "connect_timeout_10s_wall_clock_timeout_45s",
        "identity_bound_http_200_body": request_id == SUPPLEMENTAL_HTTP_200_ID,
        "eligible_for_normalized_claims": False,
        "used_for_normalized_claims": False,
        "source_record_created": False,
        "raw_redistributed": False,
    }


def _retrieval_inventory(recorded_at: str) -> dict[str, Any]:
    root = _capture_root()
    rows = [_request_row(root, request_id) for request_id in REQUEST_IDS]
    return {
        "format": "datacenter-atlas-bounded-government-retrieval-inventory-v1",
        "recorded_at": recorded_at,
        "retrieval_attempt_count": len(rows),
        "successful_http_200_decoded_body_count": sum(
            row["http_status"] == 200 and row["decoded_body_created"] for row in rows
        ),
        "required_claim_bearing_http_200_body_count": 0,
        "identity_bound_http_200_body_count": sum(
            row["identity_bound_http_200_body"] for row in rows
        ),
        "claim_eligible_capture_count": 0,
        "technical_incident_group_count": 3,
        "request_credentials_supplied": False,
        "network_timeout_contract": "connect_timeout_10s_wall_clock_timeout_45s",
        "search_snippets_used_for_claims": False,
        "transformed_web_text_used_for_claims": False,
        "publisher_media_used_for_claims": False,
        "requests": rows,
        "changle_current_a_records_attempted": list(CHANGLE_A_RECORDS),
        "supplemental_mirror_boundary": {
            "request_id": SUPPLEMENTAL_HTTP_200_ID,
            "http_status": 200,
            "effective_url": CHANGLE_SUPPLEMENTAL_URL,
            "content_type": "text/html",
            "decoded_body_bytes": MIRROR_BODY_PIN[0],
            "decoded_body_sha256": MIRROR_BODY_PIN[1],
            "page_publication_metadata": "2026-01-22 16:48",
            "claim_eligibility": "none",
            "reason": (
                "A January 22 mirror cannot authenticate the required January 19 "
                "physical observation and is retained only as supplemental retrieval metadata."
            ),
        },
        "rejected_nonpublisher_probe": {
            "filename": "fiscalia_jina_discovery.body",
            "bytes": REJECTED_PROXY_BODY_PIN[0],
            "sha256": REJECTED_PROXY_BODY_PIN[1],
            "http_status": 401,
            "used_for_discovery": False,
            "used_for_claims": False,
            "reason": "third-party proxy response is not a first-party publisher body",
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
            "candidate_id": "changle-airport-comprehensive-bonded-zone-ai-computing-center",
            "candidate_name": "Changle Airport Comprehensive Bonded Zone AI Computing Center",
            "country": "China",
            "decision": "review_only_required_january_19_publisher_body_unavailable",
            "required_source_url": CHANGLE_REQUIRED_URL,
            "required_as_of_date": "2026-01-19",
            "required_request_id": "changle_progress",
            "required_http_status": 0,
            "direct_claim_body_available": False,
            "supplemental_request_id": SUPPLEMENTAL_HTTP_200_ID,
            "supplemental_body_pin": {
                "bytes": MIRROR_BODY_PIN[0],
                "sha256": MIRROR_BODY_PIN[1],
            },
            "supplemental_claim_eligible": False,
            "supplemental_reason": (
                "The accessible January 22 provincial mirror is later than the required "
                "January 19 observation and cannot be substituted for it."
            ),
            "withheld_claims": [
                "foundations lifecycle observation",
                "developer identity",
                "AI-specialized design or workload enum",
                "road-bounded locality",
                "15,000P or 10,000P FP16 as any capacity or power metric",
            ],
            "compute_figures_are_not_capacity_rows": True,
            "normalized": dict(empty),
        },
        {
            "candidate_id": "bolivia-ministerio-publico-data-center-sucre",
            "candidate_name": "Ministerio Público Data Center, Sucre",
            "country": "Bolivia",
            "decision": "review_only_required_progress_publisher_body_unavailable",
            "required_source_url": BOLIVIA_PROGRESS_URL,
            "required_as_of_date": "2026-05-15",
            "required_request_id": "bolivia_progress",
            "required_http_status": 0,
            "direct_claim_body_available": False,
            "parallel_interim_address": "Calle Destacamento 317",
            "parallel_interim_address_normalized": False,
            "withheld_claims": [
                "under_construction lifecycle observation",
                "owner or user role for Ministerio Público",
                "enterprise IT operating model or workload enum",
                "street address",
                "operator, tenant, certification, power, PUE, or energy",
            ],
            "normalized": dict(empty),
        },
        {
            "candidate_id": "fuzhou-phase-2-phase-3-program-candidate",
            "candidate_name": "Additional Fuzhou phase-2/phase-3 candidate",
            "country": "China",
            "decision": "review_only_no_direct_publisher_body",
            "requested_source_url": FUZHOU_PHASE23_URL,
            "request_id": "fuzhou_phase23",
            "http_status": 0,
            "program_or_project_identity_bound": False,
            "withheld_claims": [
                "specific project identity",
                "physical construction status",
                "operator, owner, developer, tenant, or user",
                "capacity, power, PUE, energy, or coordinates",
            ],
            "normalized": dict(empty),
        },
    ]
    return {
        "format": "datacenter-atlas-government-candidate-assessment-v1",
        "recorded_at": recorded_at,
        "candidate_count": len(candidates),
        "curated_source_record_count": 0,
        "seed_eligible_count": 0,
        "review_only_count": len(candidates),
        "current_status_unknown_count": len(candidates),
        "capacity_row_count": 0,
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
        "third_party_mirror_substituted_for_bodies": False,
        "transformed_proxy_text_used": False,
        "satellite_or_cv_used": False,
    }


def _validate_v84_nonmutation() -> dict[str, Any]:
    for path, expected in V84_PINS.items():
        _pin(path, expected)
        if stat.S_IMODE(path.stat().st_mode) != 0o444:
            raise GovernmentGapArtifactError(f"v84 file mode differs: {path}")
    if V84_RELEASE.is_symlink() or not V84_RELEASE.is_dir():
        raise GovernmentGapArtifactError("v84 release directory is absent")
    if stat.S_IMODE(V84_RELEASE.stat().st_mode) != 0o555:
        raise GovernmentGapArtifactError("v84 release mode differs")
    if tree_digest(V84_RELEASE) != V84_TREE_SHA256:
        raise GovernmentGapArtifactError("v84 release tree differs")
    manifest = json.loads(V84_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("recorded_at") != V84_RECORDED_AT:
        raise GovernmentGapArtifactError("v84 recorded_at differs")
    definition = json.loads(V84_DEFINITION.read_text(encoding="utf-8"))
    selected = definition.get("curated_inputs")
    if not isinstance(selected, list) or len(selected) != V84_INPUT_COUNT:
        raise GovernmentGapArtifactError("v84 selected input count differs")

    tokens = tuple(token.casefold() for token in COLLISION_TOKENS)
    selected_paths: list[str] = []
    for row in selected:
        relative = row.get("path")
        if not isinstance(relative, str):
            raise GovernmentGapArtifactError("v84 selected input path differs")
        selected_paths.append(relative)
        source = ROOT / relative
        if source.is_symlink() or not source.is_file():
            raise GovernmentGapArtifactError(f"v84 selected source absent: {relative}")
        searchable = f"{relative}\n{source.read_text(encoding='utf-8')}".casefold()
        if any(token in searchable for token in tokens):
            raise GovernmentGapArtifactError(
                f"planned candidate collides with v84 source: {relative}"
            )
    release_searchable = V84_ENTITIES.read_text(encoding="utf-8").casefold()
    if any(token in release_searchable for token in tokens):
        raise GovernmentGapArtifactError("planned candidate collides with v84 release")
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
        "format": "datacenter-atlas-government-gap-source-snapshot-v1",
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
            "release_integration": "none",
            "downstream_product_integration": "none",
            "reason": "all candidates fail closed as review-only",
        },
        "unique_physical_site_count": None,
        "semi_analysis_parity_claimed": False,
    }


def _readme(recorded_at: str) -> bytes:
    return (
        "# Government-source construction gap audit\n\n"
        f"Recorded at `{recorded_at}`.\n\n"
        "The required Changle January 19 and Sucre May 15 publisher pages did "
        "not return identity-bound HTTP 200 bodies under the 10-second connect / "
        "45-second wall-clock retrieval contract. The additional Fuzhou phase-2/"
        "phase-3 candidate page also returned no body. All three candidates are "
        "therefore review-only.\n\n"
        "One January 22 Fujian provincial mirror returned an HTTP 200 decoded body, "
        "but its later date cannot authenticate the required January 19 observation; "
        "it is retained only as supplemental request metadata. No source JSON, entity, "
        "lifecycle, role, model, workload, capacity, address, coordinate, energy, PUE, "
        "certification, operator, tenant, or current-status claim is emitted.\n\n"
        "Raw all-rights-reserved captures are not redistributed. Their single closed "
        "directory was moved intact to Trash and is pinned by file count, byte count, "
        "and a mode/path/content tree digest. Open seed v84 is hash-pinned and unchanged. "
        "This artifact makes no completeness, unique-site, or SemiAnalysis parity claim.\n"
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
        "candidate_assessments": 3,
        "curated_source_records": 0,
        "seed_eligible_source_records": 0,
        "review_only_candidates": 3,
        "required_claim_bearing_http_200_bodies": 0,
        "supplemental_identity_bound_http_200_bodies": 1,
        "claim_eligible_capture_count": 0,
        "raw_capture_redistributed": False,
        "raw_capture_directory_moved_intact_to_trash": True,
        "search_snippets_used_for_claims": False,
        "open_seed_successor_created": False,
        "v84_mutated": False,
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
    timestamps: list[datetime] = []
    for suffix in ("started_at", "completed_at"):
        for member in root.glob(f"*.{suffix}"):
            timestamps.append(_instant(member.read_text(encoding="utf-8").strip()))
    if not timestamps:
        raise GovernmentGapArtifactError("capture timestamps are absent")
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
        raise GovernmentGapArtifactError("artifact must be an ordinary directory")
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise GovernmentGapArtifactError("artifact closed file set differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries.values()):
        raise GovernmentGapArtifactError("artifact contains a non-ordinary file")
    if stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise GovernmentGapArtifactError("artifact directory mode differs")
    if any(stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries.values()):
        raise GovernmentGapArtifactError("artifact file mode differs")

    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest):
        raise GovernmentGapArtifactError("manifest JSON is not canonical")
    if (
        manifest.get("artifact_id") != ARTIFACT_ID
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or manifest.get("candidate_assessments") != 3
        or manifest.get("curated_source_records") != 0
        or manifest.get("seed_eligible_source_records") != 0
        or manifest.get("review_only_candidates") != 3
        or manifest.get("required_claim_bearing_http_200_bodies") != 0
        or manifest.get("supplemental_identity_bound_http_200_bodies") != 1
        or manifest.get("claim_eligible_capture_count") != 0
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("v84_mutated") is not False
        or manifest.get("release_integration") != "none"
        or manifest.get("downstream_product_integration") != "none"
        or manifest.get("semi_analysis_parity_claimed") is not False
        or manifest.get("unique_physical_site_count") is not None
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise GovernmentGapArtifactError("manifest contract differs")
    if [row["path"] for row in manifest["files"]] != list(CONTENT_FILES):
        raise GovernmentGapArtifactError("manifest file order differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (row["bytes"], row["sha256"]):
            raise GovernmentGapArtifactError(
                f"manifest file pin differs: {row['path']}"
            )
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise GovernmentGapArtifactError("manifest checksum differs")
    expected = _artifact_documents(manifest["recorded_at"])
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected[name]:
            raise GovernmentGapArtifactError(f"artifact content differs: {name}")

    target = _instant(manifest["recorded_at"])
    if target <= _instant(V84_RECORDED_AT):
        raise GovernmentGapArtifactError("artifact does not post-date v84")
    if target < _max_capture_timestamp():
        raise GovernmentGapArtifactError("artifact predates capture completion")
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise GovernmentGapArtifactError("validation wall clock lacks timezone")
    if require_live:
        if now.astimezone(UTC) < target:
            raise GovernmentGapArtifactError("artifact recorded_at is not live")
        if CAPTURE_ORIGIN.exists() or not CAPTURE_TRASH.exists():
            raise GovernmentGapArtifactError("raw capture was not moved to Trash")
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
        raise GovernmentGapArtifactError("publication lock already exists") from error
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
        raise GovernmentGapArtifactError("recorded_at must post-date v84")
    if target < _max_capture_timestamp():
        raise GovernmentGapArtifactError("recorded_at predates capture completion")
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
            raise GovernmentGapArtifactError(
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
        raise GovernmentGapArtifactError(
            "capture origin and Trash destination both exist"
        )
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(CAPTURE_TRASH)


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
            raise GovernmentGapArtifactError("artifact identity changed on promotion")
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
    """Publish the closed fail-closed review artifact exactly once."""

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
    _validate_capture_directory(CAPTURE_TRASH)
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
            "candidates": 3,
            "source_records": 0,
            "seed_eligible": 0,
            "review_only": 3,
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

