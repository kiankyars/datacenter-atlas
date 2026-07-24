"""Publish five governed operator/developer physical-build source records.

The source bodies are all-rights-reserved and are not redistributed.  This
module publishes only compact factual extracts, hashes, retrieval telemetry,
and five schema-1.1 records.  Publication is future-bound, no-replace, and
independent of every accepted open-seed and downstream release.
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

from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from . import global_official_builds_six_candidate_20260721 as publication
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "global-official-builds-operator-social-next-tranche-2026-07-21-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".global-official-builds-operator-social-next.lock"
CAPTURE_ORIGIN = Path("/private/tmp/dc-operator-social-next-20260721.HOCD94")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-operator-social-next-20260721.HOCD94")
CAPTURE_FILE_COUNT = 60
CAPTURE_TOTAL_BYTES = 1_200_123
CAPTURE_TREE_SHA256 = "846a384b804ed08ad3271f6b825b69017e6f7eceb863ed7568e8ad4afa3ebf85"

V84_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v84.json"
V84_RELEASE = ROOT / "releases/2026-07-21-open-seed-v84"
V84_MANIFEST = V84_RELEASE / "manifest.json"
V84_PINS = {
    V84_DEFINITION: (
        100_280,
        "910b2f0d830106b274d8ec22849e2d637463ea5fc57c3481aca2d468218bf8ef",
    ),
    V84_MANIFEST: (
        15_118,
        "0c4b7b3979c5c3bcdfb3a9bef38b5b32f4da5df31633a0c38920ef937914e301",
    ),
}
V84_TREE_SHA256 = "3ec1197343778c51609221aedbac6f4bf8942cb6620c80fc857b7b1f3124e52b"
V84_INPUT_COUNT = 447

PRIOR_REVIEW_ARTIFACT = (
    ARTIFACT_ROOT / "global-official-builds-next-tranche-2026-07-21-v1"
)
PRIOR_REVIEW_PINS = {
    PRIOR_REVIEW_ARTIFACT / "manifest.json": (
        1_791,
        "5cdf7bba0090ee2a67af2699257a6557ee1be16dcafb9d8560993127b714cce7",
    ),
    PRIOR_REVIEW_ARTIFACT / "candidate-assessment.json": (
        4_816,
        "b34960337b9a0f4822d94bbec431dfed26398324c30c925978f52da8f8fef315",
    ),
}

SOURCE_FILENAMES = (
    "curated-official-2026-07-21-stack-johor-first-120mw-current-build.json",
    "curated-official-2026-07-21-echelon-dub20-current-build.json",
    "curated-official-2026-07-21-echelon-dub40-current-build.json",
    "curated-official-2026-07-21-odata-sp04-phase2-current-build.json",
    "curated-official-2026-07-21-multidc-shoham-current-build.json",
)
CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

OfficialOperatorSocialError = publication.OfficialBuildsError
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


CAPTURE_FILE_PINS: dict[str, tuple[int, str]] = {
    "echelon_dub20_facility.body": (
        49_965,
        "2acc12da44f85023f4d25b155ba1e0be22472bf3c29e5af76a1ad30d3e0e10a4",
    ),
    "echelon_dub20_facility.finished_at": (
        21,
        "2f55496bc2b6b6ec802f1dd3cfd3db7b6445475e6f6750a3bce27a84be9ff4fe",
    ),
    "echelon_dub20_facility.headers": (
        585,
        "2e720892cda55a06d6d97f6c0532f0fb94eb1d6df23660bc5ced7433fec89851",
    ),
    "echelon_dub20_facility.started_at": (
        21,
        "c626d45a6c754442417552826af7c6945343c1327af622a60a0e00a09b8306aa",
    ),
    "echelon_dub20_facility.writeout": (
        16_201,
        "4e2d00ebd4bc558cac8cd73c6d816d157f1f0bf7b146f845f6dea3881b11fd30",
    ),
    "echelon_dub20_green_energy_park.body": (
        63_186,
        "8cf94d6e72f40d721064c2d793ebf32a8b76bd046921ce178fbd40146324ef0b",
    ),
    "echelon_dub20_green_energy_park.finished_at": (
        21,
        "6373bbc8ca4ae45ce3e0f39e6d64b85f9c91f605f429c72b5e8a055a870d76e7",
    ),
    "echelon_dub20_green_energy_park.headers": (
        316,
        "1d3bdc2a5a6bcfea4d7c9e75eb7f4424575b1a5ceb39c2cf44df497ca001352b",
    ),
    "echelon_dub20_green_energy_park.started_at": (
        21,
        "6373bbc8ca4ae45ce3e0f39e6d64b85f9c91f605f429c72b5e8a055a870d76e7",
    ),
    "echelon_dub20_green_energy_park.writeout": (
        16_386,
        "fffe8101e293d974f1d05cb5eab01996965a262c586dcc6896779ce4110feaba",
    ),
    "echelon_dub20_social.body": (
        22_459,
        "aba69a74cf49f4b1bcf799e20eee8df0fa81c43a6dd25c8ddaeff96e89e7aa22",
    ),
    "echelon_dub20_social.finished_at": (
        21,
        "2f55496bc2b6b6ec802f1dd3cfd3db7b6445475e6f6750a3bce27a84be9ff4fe",
    ),
    "echelon_dub20_social.headers": (
        3_870,
        "9b8d30db0a3ce2b14c89afd6c274f6110141f63c4d902372cdafb41e0aa66154",
    ),
    "echelon_dub20_social.started_at": (
        21,
        "2f55496bc2b6b6ec802f1dd3cfd3db7b6445475e6f6750a3bce27a84be9ff4fe",
    ),
    "echelon_dub20_social.writeout": (
        17_606,
        "e8226c18ec5f53c0fcd184526891d4d01cc7561521b5c91dcc00797fc1b51a64",
    ),
    "echelon_dub40_facility.body": (
        49_965,
        "2acc12da44f85023f4d25b155ba1e0be22472bf3c29e5af76a1ad30d3e0e10a4",
    ),
    "echelon_dub40_facility.finished_at": (
        21,
        "aaea8f04db659e78aef6be26f7c7339604ba63ac64a3c674c4eb4d54c3138e47",
    ),
    "echelon_dub40_facility.headers": (
        585,
        "6271bf5b93e524439188a15894befb60021c55c4cb85a3f8ff55ddd048770c93",
    ),
    "echelon_dub40_facility.started_at": (
        21,
        "2f55496bc2b6b6ec802f1dd3cfd3db7b6445475e6f6750a3bce27a84be9ff4fe",
    ),
    "echelon_dub40_facility.writeout": (
        16_201,
        "0f18e6e431b0e2ba44e80df12fdb8eb6da92a2257958c9179098317d2db33626",
    ),
    "echelon_dub40_social.body": (
        23_705,
        "73525224704479d3ff6baa27b4741c14d8bfad4d6ae2d9e04674a67a40336b95",
    ),
    "echelon_dub40_social.finished_at": (
        21,
        "ebd81d93678ac26366a3c8b78ca34a49f90be9bc8f22dcbd454285b8a2e27e0f",
    ),
    "echelon_dub40_social.headers": (
        4_434,
        "7e667443f48a850668ce60499cc2da8a701cbc29fce889f8ba639f946aafd30f",
    ),
    "echelon_dub40_social.started_at": (
        21,
        "aaea8f04db659e78aef6be26f7c7339604ba63ac64a3c674c4eb4d54c3138e47",
    ),
    "echelon_dub40_social.writeout": (
        17_606,
        "a8fe4529c31d24bf8e2e52834e71a7e0dff53c98c8a723f47e3c457ec4ea5ee9",
    ),
    "multidc_geva_project.body": (
        543_881,
        "287353fdf0a628918f394625098fda4a3d5c137e46888ea5b2772a5aa7181571",
    ),
    "multidc_geva_project.finished_at": (
        21,
        "cff9b2bcd07906cf1f6380f50987d53289908e6d149cfff8bddac2aceaf4809c",
    ),
    "multidc_geva_project.headers": (
        1_594,
        "0072b132297da4744aaa6d4077b22abdaddff4a4e2d5fff4beeec16934f7f10d",
    ),
    "multidc_geva_project.started_at": (
        21,
        "cff9b2bcd07906cf1f6380f50987d53289908e6d149cfff8bddac2aceaf4809c",
    ),
    "multidc_geva_project.writeout": (
        15_652,
        "460dfbaa28161093ec0737f2a5cb1b5003d232723e3a8ba6d53fc3be8266d5db",
    ),
    "multidc_social.body": (
        27_632,
        "0f3827904463c6e1e1aa9f9af284d1bda6f2c4b8bbe8de93365205fb359ea4bf",
    ),
    "multidc_social.finished_at": (
        21,
        "1758a0e91d2f9d9042958f310dfb1a1e28977484373fac6ee4504748d2c9b7c8",
    ),
    "multidc_social.headers": (
        3_870,
        "0aca7dd9ad442da2f1dfc13cd702b0a9bf0e9ec3c1669800253f71c0208198cf",
    ),
    "multidc_social.started_at": (
        21,
        "cff9b2bcd07906cf1f6380f50987d53289908e6d149cfff8bddac2aceaf4809c",
    ),
    "multidc_social.writeout": (
        17_600,
        "ce3144492f5793c2b718e78d76a7a86cf2d5b29234681d441bd1f6924ad73c5b",
    ),
    "odata_sp04_facility.body": (
        49_016,
        "c5e29b0a99da06e9ec93cb86bccc96a03b110c1179f44b1e9059213cf76ec2bc",
    ),
    "odata_sp04_facility.finished_at": (
        21,
        "ebd81d93678ac26366a3c8b78ca34a49f90be9bc8f22dcbd454285b8a2e27e0f",
    ),
    "odata_sp04_facility.headers": (
        742,
        "54482c79493664ad56de3e75337fc146bb85d2b4fe7703974c2eb7970a687899",
    ),
    "odata_sp04_facility.started_at": (
        21,
        "ebd81d93678ac26366a3c8b78ca34a49f90be9bc8f22dcbd454285b8a2e27e0f",
    ),
    "odata_sp04_facility.writeout": (
        16_559,
        "9a77939232b884d84e73ae2d698042bc418635f67375d0362f41003da5634e9f",
    ),
    "odata_sp04_phase2_social.body": (
        25_334,
        "fb73fcb98ed6b67d10bc52d27795e4d444ab10def6d00eeccf74349aaf723458",
    ),
    "odata_sp04_phase2_social.finished_at": (
        21,
        "cff9b2bcd07906cf1f6380f50987d53289908e6d149cfff8bddac2aceaf4809c",
    ),
    "odata_sp04_phase2_social.headers": (
        3_870,
        "afd46b90881e02a4abb69be91355fa5fd2418666b93a70b1223f220cd621dc20",
    ),
    "odata_sp04_phase2_social.started_at": (
        21,
        "ebd81d93678ac26366a3c8b78ca34a49f90be9bc8f22dcbd454285b8a2e27e0f",
    ),
    "odata_sp04_phase2_social.writeout": (
        17_609,
        "1be2b3189b3f21d3b077355ed48809590c6c086373febf67ee7609472782c2e3",
    ),
    "stack_release.body": (
        69_849,
        "dc578eab735029806539b648513cd806cde40e9e3f4652d8fc4bc25abc1ff476",
    ),
    "stack_release.finished_at": (
        21,
        "c626d45a6c754442417552826af7c6945343c1327af622a60a0e00a09b8306aa",
    ),
    "stack_release.headers": (
        1_407,
        "473f55c1f0a225de7b2612a1e57a643969bf1100fe99de37656a177cf981f457",
    ),
    "stack_release.started_at": (
        21,
        "48b9f9234e42c8d7906f1a0d8ba00fbf0fa257f03346ae796eae442e28a373aa",
    ),
    "stack_release.writeout": (
        12_994,
        "f4d0eea7cf1b403408800512e4053aca6feb92794ef38e90da4f1aa38160f5d1",
    ),
    "stack_social_announcement.body": (
        23_012,
        "df791dd7a7b389baf9bcc6139c9141ebdd869080ce9240aef523a0841409962d",
    ),
    "stack_social_announcement.finished_at": (
        21,
        "c626d45a6c754442417552826af7c6945343c1327af622a60a0e00a09b8306aa",
    ),
    "stack_social_announcement.headers": (
        3_869,
        "45398ba202efdb08112219a5db0c913b2a24abc9c8d1803226bff11f5e56887d",
    ),
    "stack_social_announcement.started_at": (
        21,
        "c626d45a6c754442417552826af7c6945343c1327af622a60a0e00a09b8306aa",
    ),
    "stack_social_announcement.writeout": (
        17_611,
        "534ed6be09c02fd4bec788e5b35817d95e88b087a0481e4b7acd10c425109286",
    ),
    "stack_social_physical.body": (
        22_973,
        "08e505794a13e7b4ca9c3d776fb4b78229cc8e7c65ee8446d8da3c3584ed1020",
    ),
    "stack_social_physical.finished_at": (
        21,
        "092063895c2faf6b284a690fe9da246204635102163e11fe1c14d2b7865a5c01",
    ),
    "stack_social_physical.headers": (
        3_868,
        "55ac9eae9ce89549075cd9ab2ead1d77a83cbc1f222a9118ff0a0594a43dbb03",
    ),
    "stack_social_physical.started_at": (
        21,
        "092063895c2faf6b284a690fe9da246204635102163e11fe1c14d2b7865a5c01",
    ),
    "stack_social_physical.writeout": (
        17_607,
        "dd7accf5f9b1de9f8013b3c44a06a3564de70d6def7daec71107754e8c47fb4b",
    ),
}


def _capture(
    capture_id: str,
    url: str,
    *,
    retrieved_at: str,
    http_status: int,
    content_type: str,
    published_at: str | None,
    used_for_normalized_claims: bool,
) -> dict[str, Any]:
    size, digest = CAPTURE_FILE_PINS[f"{capture_id}.body"]
    return {
        "filename": f"{capture_id}.body",
        "url": url,
        "effective_url": url,
        "retrieved_at": retrieved_at,
        "http_status": http_status,
        "content_type": content_type,
        "published_at": published_at,
        "bytes": size,
        "sha256": digest,
        "used_for_normalized_claims": used_for_normalized_claims,
    }


CAPTURES = {
    "stack_release": _capture(
        "stack_release",
        "https://www.stackinfra.com/about/news-press/press-releases/stack-infrastructure-announces-220mw-campus-in-malaysia/",
        retrieved_at="2026-07-21T19:42:26Z",
        http_status=200,
        content_type="text/html; charset=UTF-8",
        published_at="2025-01-14",
        used_for_normalized_claims=True,
    ),
    "stack_social_announcement": _capture(
        "stack_social_announcement",
        "https://www.linkedin.com/embed/feed/update/urn:li:activity:7284720903857287168",
        retrieved_at="2026-07-21T19:42:26Z",
        http_status=200,
        content_type="text/html; charset=utf-8",
        published_at="2025-01-14",
        used_for_normalized_claims=False,
    ),
    "stack_social_physical": _capture(
        "stack_social_physical",
        "https://www.linkedin.com/embed/feed/update/urn:li:activity:7421703539049267200",
        retrieved_at="2026-07-21T19:45:15Z",
        http_status=200,
        content_type="text/html; charset=utf-8",
        published_at="2026-01-27",
        used_for_normalized_claims=True,
    ),
    "echelon_dub20_facility": _capture(
        "echelon_dub20_facility",
        "https://echelon-dc.com/dub20/",
        retrieved_at="2026-07-21T19:42:28Z",
        http_status=404,
        content_type="text/html; charset=UTF-8",
        published_at=None,
        used_for_normalized_claims=False,
    ),
    "echelon_dub20_green_energy_park": _capture(
        "echelon_dub20_green_energy_park",
        "https://echelon-dc.com/echelon-launches-irelands-first-green-energy-park/",
        retrieved_at="2026-07-21T19:44:59Z",
        http_status=200,
        content_type="text/html; charset=UTF-8",
        published_at="2026-03-27",
        used_for_normalized_claims=True,
    ),
    "echelon_dub20_social": _capture(
        "echelon_dub20_social",
        "https://www.linkedin.com/embed/feed/update/urn:li:activity:7367157426850070530",
        retrieved_at="2026-07-21T19:42:28Z",
        http_status=200,
        content_type="text/html; charset=utf-8",
        published_at="2025-08-29",
        used_for_normalized_claims=True,
    ),
    "echelon_dub40_facility": _capture(
        "echelon_dub40_facility",
        "https://echelon-dc.com/dub40/",
        retrieved_at="2026-07-21T19:42:29Z",
        http_status=404,
        content_type="text/html; charset=UTF-8",
        published_at=None,
        used_for_normalized_claims=False,
    ),
    "echelon_dub40_social": _capture(
        "echelon_dub40_social",
        "https://www.linkedin.com/embed/feed/update/urn:li:activity:7417143447918317568",
        retrieved_at="2026-07-21T19:42:30Z",
        http_status=200,
        content_type="text/html; charset=utf-8",
        published_at="2026-01-14",
        used_for_normalized_claims=True,
    ),
    "odata_sp04_facility": _capture(
        "odata_sp04_facility",
        "https://odatacolocation.com/blog/data-center/dc-sp04/",
        retrieved_at="2026-07-21T19:42:30Z",
        http_status=200,
        content_type="text/html; charset=UTF-8",
        published_at="2025-04-29",
        used_for_normalized_claims=True,
    ),
    "odata_sp04_phase2_social": _capture(
        "odata_sp04_phase2_social",
        "https://www.linkedin.com/embed/feed/update/urn:li:activity:7473377620018077696",
        retrieved_at="2026-07-21T19:42:31Z",
        http_status=200,
        content_type="text/html; charset=utf-8",
        published_at="2026-06-18",
        used_for_normalized_claims=True,
    ),
    "multidc_geva_project": _capture(
        "multidc_geva_project",
        "https://www.geva.co/geva-projects/multidc-shoham",
        retrieved_at="2026-07-21T19:42:31Z",
        http_status=200,
        content_type="text/html; charset=UTF-8",
        published_at=None,
        used_for_normalized_claims=True,
    ),
    "multidc_social": _capture(
        "multidc_social",
        "https://www.linkedin.com/embed/feed/update/urn:li:activity:7467894088462249984",
        retrieved_at="2026-07-21T19:42:32Z",
        http_status=200,
        content_type="text/html; charset=utf-8",
        published_at="2026-06-03",
        used_for_normalized_claims=True,
    ),
}


def _evidence(
    capture_id: str,
    *,
    key: str,
    title: str,
    publisher: str,
    source_family: str,
    excerpt: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    capture = CAPTURES[capture_id]
    common = {
        "content_hash_scope": (
            f"SHA-256 of the exact {capture['bytes']}-byte content-decoded "
            "credential-free public response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture_id,
        "capture_method": "credential_free_curl_location_compressed",
        "http_status": capture["http_status"],
        "content_type": capture["content_type"],
        "request_credentials_supplied": False,
        "rights_scope": (
            "Compact factual extraction from all-rights-reserved official bytes; "
            "raw body, headers, telemetry, and publisher media are not redistributed."
        ),
        "status_semantics": "last_observed_current_status_unknown",
        "imagery_guardrail": (
            "No publisher image, satellite image, aerial image, computer vision, "
            "or analyst geolocation contributes to a normalized claim."
        ),
    }
    common.update(metadata)
    return {
        "key": key,
        "kind": "company_disclosure",
        "title": title,
        "source_url": capture["url"],
        "publisher": publisher,
        "source_family": source_family,
        "published_at": capture["published_at"],
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
    roles: Mapping[str, list[str]],
    evidence_key: str,
    as_of_date: str,
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
        "confidence": 0.99,
    }


def _document(
    *,
    campus_key: str,
    campus_name: str,
    project_suffix: str,
    project_name: str,
    country: str,
    address: str,
    roles: Mapping[str, list[str]],
    identity_evidence_key: str,
    status_evidence_key: str,
    as_of_date: str,
    evidence: list[dict[str, Any]],
    lifecycle_value: str = "under_construction",
    capacities: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name=campus_name,
            country=country,
            address=address,
            roles=roles,
            evidence_key=identity_evidence_key,
            as_of_date=as_of_date,
        ),
        "project": _entity(
            stable_key=f"{campus_key}:{project_suffix}",
            name=project_name,
            country=country,
            address=address,
            roles=roles,
            evidence_key=status_evidence_key,
            as_of_date=as_of_date,
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": lifecycle_value,
                "evidence_key": status_evidence_key,
                "as_of_date": as_of_date,
                "method": "authoritative_physical_status_update",
                "confidence": 0.99,
            }
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": capacities or [],
    }


def _capacity(
    *,
    entity: str,
    base: float,
    evidence_key: str,
    as_of_date: str,
    notes: str,
) -> dict[str, Any]:
    return {
        "entity": entity,
        "metric": "critical_it_mw",
        "stage": "design",
        "unit": "MW",
        "low": base,
        "base": base,
        "high": base,
        "method": "reported",
        "confidence": 0.99,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "target_date": None,
        "notes": notes,
    }


def _stack_source() -> dict[str, Any]:
    identity_key = "stack-johor-campus-design-captured-2026-07-21"
    status_key = "stack-johor-first-building-progress-captured-2026-07-21"
    return _document(
        campus_key="curated:stack-johor-iskandar-puteri-campus",
        campus_name="STACK Johor Iskandar Puteri Campus",
        project_suffix="first-building-current-build",
        project_name="STACK Johor First Building Current Build",
        country="Malaysia",
        address="Iskandar Puteri, Johor Bahru, Johor, Malaysia",
        roles={
            "developer": ["STACK Infrastructure"],
            "operator": ["STACK Infrastructure"],
        },
        identity_evidence_key=identity_key,
        status_evidence_key=status_key,
        as_of_date="2026-01-27",
        evidence=[
            _evidence(
                "stack_release",
                key=identity_key,
                title="STACK Johor Iskandar Puteri campus announcement",
                publisher="STACK Infrastructure",
                source_family="stack_infrastructure_press_releases",
                excerpt=(
                    "STACK identifies its Iskandar Puteri campus, two planned data-center "
                    "buildings, and the first building's reported 120 MW label."
                ),
                metadata={
                    "capacity_labels_as_reported": [
                        "220MW campus",
                        "120MW first building",
                        "100MW second facility",
                    ],
                    "capacity_guardrail": "All three labels are untyped and create no normalized capacity row.",
                    "capability_guardrail": "Cloud and AI/ML design language creates no workload observation.",
                },
            ),
            _evidence(
                "stack_social_physical",
                key=status_key,
                title="STACK Johor first-building construction progress",
                publisher="STACK Infrastructure",
                source_family="stack_infrastructure_linkedin_company_posts",
                excerpt=(
                    "STACK reports construction progressing on the first data-center building "
                    "in Johor Bahru."
                ),
                metadata={
                    "linkedin_activity_id": "7421703539049267200",
                    "published_date_basis": "UTC date mechanically encoded by the public LinkedIn activity identifier.",
                    "power_labels_as_reported": [
                        "120MW data center",
                        "300MW on-site substation",
                    ],
                    "capacity_guardrail": "Neither generic building MW nor substation wording is recast as IT load, gross demand, grid connection, current draw, generation, or energy.",
                    "capability_guardrail": "Cloud and AI suitability creates no tenant or workload observation.",
                },
            ),
        ],
    )


def _dub20_source() -> dict[str, Any]:
    status_key = "echelon-dub20-construction-underway-captured-2026-07-21"
    earlier_key = "echelon-dub20-site-work-captured-2026-07-21"
    return _document(
        campus_key="curated:echelon-dub20-arklow-campus",
        campus_name="Echelon DUB20 Arklow Campus",
        project_suffix="current-build",
        project_name="Echelon DUB20 Current Build",
        country="Ireland",
        address="Avoca River Business Park, Arklow, County Wicklow, Ireland",
        roles={
            "developer": ["Echelon Data Centres"],
            "operator": ["Echelon Data Centres"],
        },
        identity_evidence_key=status_key,
        status_evidence_key=status_key,
        as_of_date="2026-03-27",
        evidence=[
            _evidence(
                "echelon_dub20_green_energy_park",
                key=status_key,
                title="Echelon DUB20 construction-underway update",
                publisher="Echelon Data Centres",
                source_family="echelon_data_centres_company_news",
                excerpt=(
                    "Echelon identifies DUB20 at Avoca River Business Park in Arklow and "
                    "states that construction is underway."
                ),
                metadata={
                    "physical_status_scope": "Direct site-specific statement supports under_construction only.",
                    "energy_guardrail": "Renewable, substation, storage, and grid-support descriptions create no current draw, annual energy, generation nameplate, or PUE row.",
                },
            ),
            _evidence(
                "echelon_dub20_social",
                key=earlier_key,
                title="Echelon DUB20 earlier site-work update",
                publisher="Echelon Data Centres",
                source_family="echelon_data_centres_linkedin_company_posts",
                excerpt=(
                    "Echelon reports demolition and foundation removal in the footprints "
                    "of DUB20 data-center buildings and its energy centre."
                ),
                metadata={
                    "linkedin_activity_id": "7367157426850070530",
                    "published_date_basis": "UTC date mechanically encoded by the public LinkedIn activity identifier.",
                    "lifecycle_guardrail": "Earlier physical corroboration does not supersede the newer 2026-03-27 observation.",
                },
            ),
        ],
    )


def _dub40_source() -> dict[str, Any]:
    status_key = "echelon-dub40-structural-progress-captured-2026-07-21"
    return _document(
        campus_key="curated:echelon-dub40-dublin-campus",
        campus_name="Echelon DUB40 Dublin Campus",
        project_suffix="current-build",
        project_name="Echelon DUB40 Current Build",
        country="Ireland",
        address="Dublin, Ireland",
        roles={
            "developer": ["Echelon Data Centres"],
            "operator": ["Echelon Data Centres"],
        },
        identity_evidence_key=status_key,
        status_evidence_key=status_key,
        as_of_date="2026-01-14",
        lifecycle_value="shell",
        evidence=[
            _evidence(
                "echelon_dub40_social",
                key=status_key,
                title="Echelon DUB40 structural progress",
                publisher="Echelon Data Centres",
                source_family="echelon_data_centres_linkedin_company_posts",
                excerpt=(
                    "Echelon reports structural steel and core progressing and the DUB40 "
                    "building taking shape on site."
                ),
                metadata={
                    "linkedin_activity_id": "7417143447918317568",
                    "published_date_basis": "UTC date mechanically encoded by the public LinkedIn activity identifier.",
                    "physical_status_scope": "Direct structural work supports shell as a last-observed stage.",
                    "capacity_guardrail": "The separately requested facility URL returned HTTP 404; no cached or snippet capacity becomes a claim.",
                },
            )
        ],
    )


def _odata_source() -> dict[str, Any]:
    status_key = "odata-sp04-phase2-site-mobilization-captured-2026-07-21"
    design_key = "odata-sp04-current-facility-specification-captured-2026-07-21"
    return _document(
        campus_key="curated:odata-dc-sp04-osasco-campus",
        campus_name="ODATA DC SP04 Osasco Campus",
        project_suffix="phase-2-expansion",
        project_name="ODATA DC SP04 Phase 2 Expansion",
        country="Brazil",
        address="Osasco, Greater Sao Paulo, Sao Paulo, Brazil",
        roles={"developer": ["ODATA"], "operator": ["ODATA"]},
        identity_evidence_key=design_key,
        status_evidence_key=status_key,
        as_of_date="2026-06-18",
        evidence=[
            _evidence(
                "odata_sp04_phase2_social",
                key=status_key,
                title="ODATA DC SP04 Phase 2 site mobilization",
                publisher="ODATA - An Aligned Data Centers Company",
                source_family="odata_linkedin_company_posts",
                excerpt=(
                    "ODATA identifies DC SP04 Phase 2 in Osasco and reports site "
                    "mobilization plus receipt of chillers, generators, and other equipment."
                ),
                metadata={
                    "linkedin_activity_id": "7473377620018077696",
                    "published_date_basis": "UTC date mechanically encoded by the public LinkedIn activity identifier.",
                    "phase_power_label_as_reported": "Phase 2 environments totaling 24 MW",
                    "phase_power_guardrail": "The 24 MW phrase is not explicitly typed as IT, gross demand, grid connection, current draw, generation, or energy and creates no capacity row.",
                    "capability_guardrail": "AI, high-density, critical-workload, air-cooling, and liquid-cooling design language creates no workload, tenant, operating-model, or PUE observation.",
                },
            ),
            _evidence(
                "odata_sp04_facility",
                key=design_key,
                title="ODATA DC SP04 current facility specification",
                publisher="ODATA",
                source_family="odata_current_facility_pages",
                excerpt=(
                    "ODATA's facility page labels DC SP04 with 48 MW of IT power and says "
                    "the site is built and operated by ODATA."
                ),
                metadata={
                    "capacity_label_as_reported": "Potencia de TI 48 MW",
                    "capacity_scope": "Campus design IT-power rating only; Phase 2 remained under construction in the newer operator update.",
                    "capacity_guardrail": "Not represented as installed load, current draw, energy consumption, generation, or PUE.",
                },
            ),
        ],
        capacities=[
            _capacity(
                entity="campus",
                base=48.0,
                evidence_key=design_key,
                as_of_date="2026-06-18",
                notes="Exact campus IT-power design label; not Phase 2 allocation, installed load, current draw, energy consumption, generation, or PUE.",
            )
        ],
    )


def _multidc_source() -> dict[str, Any]:
    status_key = "multidc-shoham-construction-progress-captured-2026-07-21"
    design_key = "multidc-shoham-geva-project-scope-captured-2026-07-21"
    return _document(
        campus_key="curated:multidc-shoham-campus",
        campus_name="MultiDC Shoham Campus",
        project_suffix="current-build",
        project_name="MultiDC Shoham Current Build",
        country="Israel",
        address="Shoham Industrial Zone, Shoham, Central District, Israel",
        roles={"developer": ["Geva Real Estate"], "operator": ["MultiDC"]},
        identity_evidence_key=design_key,
        status_evidence_key=status_key,
        as_of_date="2026-06-03",
        evidence=[
            _evidence(
                "multidc_social",
                key=status_key,
                title="MultiDC Shoham construction progress",
                publisher="MultiDC - Data Center Campus",
                source_family="multidc_linkedin_company_posts",
                excerpt=(
                    "MultiDC reports construction progressing at MDC Shoham and describes "
                    "the campus as approaching completion."
                ),
                metadata={
                    "linkedin_activity_id": "7467894088462249984",
                    "published_date_basis": "UTC date mechanically encoded by the public LinkedIn activity identifier.",
                    "power_labels_as_reported": [
                        "32MVA+32MVA first phase",
                        "additional 16MVA",
                        "future expansion up to 150MVA",
                    ],
                    "capacity_guardrail": "MVA is not converted to MW or IT load; the three figures are nonadditive narrative only.",
                    "lifecycle_guardrail": "Approaching completion and moving toward delivery do not establish commissioning or operation.",
                    "capability_guardrail": "AI-ready and AI-workload design language creates no workload, tenant, or operating-model observation.",
                },
            ),
            _evidence(
                "multidc_geva_project",
                key=design_key,
                title="Geva MultiDC Shoham project scope",
                publisher="Geva Real Estate",
                source_family="geva_current_project_pages",
                excerpt=(
                    "Geva identifies MultiDC Shoham as under construction in the Shoham "
                    "Industrial Zone and labels its scope 30MWIT."
                ),
                metadata={
                    "capacity_label_as_reported": "Scope 30MWIT",
                    "capacity_scope": "Campus design IT-power scope only.",
                    "capacity_guardrail": "Not represented as installed load, current draw, energy consumption, generation, or PUE.",
                },
            ),
        ],
        capacities=[
            _capacity(
                entity="campus",
                base=30.0,
                evidence_key=design_key,
                as_of_date="2026-06-03",
                notes="Exact developer-labeled 30MWIT campus design scope; MVA statements remain separate, nonadditive narrative.",
            )
        ],
    )


def expected_source_documents() -> dict[str, dict[str, Any]]:
    """Return the five exact schema-1.1 source documents."""

    builders = (
        _stack_source,
        _dub20_source,
        _dub40_source,
        _odata_source,
        _multidc_source,
    )
    return {
        name: builder()
        for name, builder in zip(SOURCE_FILENAMES, builders, strict=True)
    }


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
                "country": document["project"]["country"],
                "campus_stable_key": document["campus"]["stable_key"],
                "project_stable_key": document["project"]["stable_key"],
                "evidence_records": len(document["evidence"]),
                "lifecycle_observations": 1,
                "operating_model_observations": 0,
                "workload_observations": 0,
                "capacity_estimates": len(document["capacities"]),
                "coordinates_present": 0,
                "geometry_present": 0,
                "disposition": "seed_eligible_direct_authoritative_physical_update",
                "seed_eligible": True,
                "seeded": False,
            }
        )
    return rows


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    documents = expected_source_documents()
    rows = []
    withheld = {
        SOURCE_FILENAMES[0]: ["120MW building", "220MW campus", "300MW substation"],
        SOURCE_FILENAMES[1]: [],
        SOURCE_FILENAMES[2]: [],
        SOURCE_FILENAMES[3]: ["Phase 2 24 MW wording"],
        SOURCE_FILENAMES[4]: ["32MVA+32MVA", "16MVA", "150MVA"],
    }
    for name in SOURCE_FILENAMES:
        document = documents[name]
        rows.append(
            {
                "candidate_id": document["project"]["stable_key"],
                "country": document["project"]["country"],
                "decision": "seed_eligible_direct_authoritative_physical_update",
                "source_record_created": True,
                "source_path": f"sources/{name}",
                "seed_eligible": True,
                "lifecycle": document["lifecycle"][0],
                "normalized_capacities": document["capacities"],
                "withheld_non_normalized_power_labels": withheld[name],
                "operating_model_observations": 0,
                "workload_observations": 0,
                "coordinates_created": 0,
                "geometry_created": 0,
            }
        )
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-operator-social-next-tranche-assessment-v1",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "candidate_count": 5,
        "seed_eligible_count": 5,
        "review_only_count": 0,
        "regional_completeness_claimed": False,
        "candidates": rows,
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "capture_protocol": "Credential-free curl GETs with redirects, content decoding, explicit connect timeout, and explicit wall-clock timeout.",
        "request_credentials_supplied": False,
        "successful_http_200_body_captures": 10,
        "http_error_body_captures": 2,
        "http_error_capture_claims": 0,
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
                    "bytes": capture["bytes"],
                    "sha256": capture["sha256"],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "capture_method": "credential_free_curl_location_compressed",
                "request_credentials_supplied": False,
                "used_for_normalized_claims": capture["used_for_normalized_claims"],
            }
            for capture_id, capture in CAPTURES.items()
        ],
        "complete_private_file_inventory": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in sorted(CAPTURE_FILE_PINS.items())
        ],
        "access_dispositions": [
            {
                "capture_id": "echelon_dub20_facility",
                "http_status": 404,
                "normalized_claims_created": 0,
                "basis": "The retired facility URL's error body contributes no cached or snippet facts.",
            },
            {
                "capture_id": "echelon_dub40_facility",
                "http_status": 404,
                "normalized_claims_created": 0,
                "basis": "The retired facility URL's error body contributes no cached or snippet facts.",
            },
        ],
    }


def _nested_strings(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value.casefold()}
    if isinstance(value, Mapping):
        result: set[str] = set()
        for key, item in value.items():
            result.add(str(key).casefold())
            result.update(_nested_strings(item))
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        result = set()
        for item in value:
            result.update(_nested_strings(item))
        return result
    return set()


def _v84_duplicate_witness(
    planned: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    documents = planned or expected_source_documents()
    definition = json.loads(V84_DEFINITION.read_text(encoding="utf-8"))
    inputs = definition.get("curated_inputs", [])
    if len(inputs) != V84_INPUT_COUNT:
        raise OfficialOperatorSocialError("v84 input count differs")
    selected_strings: set[str] = set()
    for row in inputs:
        source = ROOT / row["path"]
        if _sha256(source) != row["sha256"]:
            raise OfficialOperatorSocialError(
                f"v84 selected source pin differs: {row['path']}"
            )
        try:
            selected_strings.update(
                _nested_strings(json.loads(source.read_text(encoding="utf-8")))
            )
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    planned_strings: set[str] = set()
    for name, document in documents.items():
        planned_strings.add(f"sources/{name}".casefold())
        planned_strings.update(
            document[entity][field].casefold()
            for entity in ("campus", "project")
            for field in ("stable_key", "name")
        )
        for evidence in document["evidence"]:
            planned_strings.add(evidence["key"].casefold())
            planned_strings.add(evidence["source_url"].casefold())
    overlap = sorted(planned_strings & selected_strings)
    if overlap:
        raise OfficialOperatorSocialError(
            f"planned exact string collides with v84: {overlap!r}"
        )
    return {
        "planned_exact_string_count": len(planned_strings),
        "exact_collisions_with_v84_selected_documents": 0,
        "v84_selected_input_count": len(inputs),
    }


def _artifact_documents(
    recorded_at: str,
    source_documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    source_records = _source_records(source_documents)
    duplicate_witness = _v84_duplicate_witness(source_documents)
    readme = f"""# Operator-social next-tranche official builds

This immutable artifact resolves five audited candidates with direct, identity-bound authoritative physical-work bodies: STACK's first Johor building, Echelon DUB20, Echelon DUB40, ODATA DC SP04 Phase 2, and MultiDC Shoham. All five create seed-eligible schema-1.1 records, but no open-seed or downstream release is changed.

Lifecycle values are last-observed only. STACK was under construction on 2026-01-27; DUB20 was under construction on 2026-03-27; DUB40 had structural steel and core work at shell stage on 2026-01-14; SP04 Phase 2 was under construction with site mobilization and equipment receipt on 2026-06-18; and MultiDC Shoham was under construction on 2026-06-03. None asserts present status after its evidence date.

Exactly two capacities are normalized: ODATA's campus-level 48 MW IT design rating and Geva's 30 MW IT design scope for MultiDC Shoham. STACK's 120/220 MW and 300 MW substation labels, ODATA's Phase 2 24 MW wording, and MultiDC's MVA labels remain narrative, unconverted, and nonadditive. No PUE, installed load, current draw, annual energy, generation, coordinate, geometry, tenant, operating model, or workload is inferred.

The earlier governed tranche had kept SP04 Phase 2 review-only because its social body had not been captured. This artifact resolves that gate with a credential-free public LinkedIn embed body while preserving the earlier artifact unchanged. The two retired Echelon facility URLs returned HTTP 404; their error bodies create no fact.

All source and artifact bytes were complete in private staging before `{recorded_at}`. Final paths remained absent until that instant and were promoted without replacement with identity-checked rollback. Raw all-rights-reserved bodies, headers, timestamps, and curl telemetry are not redistributed; the intact {CAPTURE_FILE_COUNT}-file capture directory was moved to the recoverable Trash path in the rights inventory.
"""
    totals = {
        "candidate_assessments": 5,
        "source_records": 5,
        "seed_eligible_source_records": 5,
        "review_only_candidates": 0,
        "distinct_campuses": 5,
        "projects": 5,
        "entity_snapshots": 10,
        "unique_evidence_records": 9,
        "lifecycle_observations": 5,
        "operating_model_observations": 0,
        "workload_observations": 0,
        "capacity_estimates": 2,
        "coordinates_present": 0,
        "geometry_present": 0,
        "placement_observations": 0,
    }
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "regional_completeness_claimed": False,
        "source_records": source_records,
        "totals": totals,
        "frozen_v84_non_mutation_witness": {
            "definition": {
                "path": "sources/open-seed-2026-07-21-v84.json",
                "bytes": V84_PINS[V84_DEFINITION][0],
                "sha256": V84_PINS[V84_DEFINITION][1],
            },
            "release_manifest": {
                "path": "releases/2026-07-21-open-seed-v84/manifest.json",
                "bytes": V84_PINS[V84_MANIFEST][0],
                "sha256": V84_PINS[V84_MANIFEST][1],
            },
            "release_tree_sha256": V84_TREE_SHA256,
            "new_source_paths_selected_by_v84": False,
            **duplicate_witness,
        },
        "prior_review_only_resolution": {
            "artifact_id": "global-official-builds-next-tranche-2026-07-21-v1",
            "candidate_id": "odata-sp04-phase-2",
            "prior_decision": "review_only_uncaptured_official_linkedin",
            "prior_artifact_mutated": False,
            "resolution": "credential_free_public_embed_body_captured_and_hash_bound",
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v84_mutated": False,
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
        "source_rights": "Captured publisher response bodies are treated as all-rights-reserved; no redistribution license was relied on.",
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
        "candidate_dispositions": {"seed_eligible": 5, "review_only": 0},
    }
    return {
        "README.md": readme.encode(),
        "candidate-assessment.json": _canonical(_candidate_assessment(recorded_at)),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _file_tree(rows: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_bytes((json.dumps(rows, indent=2, sort_keys=True) + "\n").encode())


def _write_source_stage(
    stage: Path,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    for name in SOURCE_FILENAMES:
        output = stage / name
        output.write_bytes(_canonical(documents[name]))
        output.chmod(0o444)
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
        "candidate_assessments": 5,
        "curated_source_records": 5,
        "seed_eligible_source_records": 5,
        "review_only_candidates": 0,
        "successful_http_200_body_captures": 10,
        "http_error_body_captures": 2,
        "raw_capture_redistributed": False,
        "raw_capture_directory_moved_intact_to_trash": True,
        "regional_completeness_claimed": False,
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
        raise OfficialOperatorSocialError("source path inventory differs")
    for name in SOURCE_FILENAMES:
        source = paths[name]
        if source.is_symlink() or not source.is_file():
            raise OfficialOperatorSocialError(f"curated source is absent: {source}")
        if source.read_bytes() != _canonical(expected[name]):
            raise OfficialOperatorSocialError(f"curated source differs: {name}")
        if stat.S_IMODE(source.stat().st_mode) != 0o444:
            raise OfficialOperatorSocialError(f"curated source mode differs: {name}")
    documents = list(expected.values())
    if any(
        document[entity][field] is not None
        for document in documents
        for entity in ("campus", "project")
        for field in ("coordinates", "geometry")
    ):
        raise OfficialOperatorSocialError("source invented coordinates or geometry")
    if any(
        document["operating_models"] or document["workloads"] for document in documents
    ):
        raise OfficialOperatorSocialError(
            "capability became normalized type or workload"
        )
    capacities = [row for document in documents for row in document["capacities"]]
    contract = sorted(
        (row["entity"], row["metric"], row["stage"], row["unit"], row["base"])
        for row in capacities
    )
    if contract != [
        ("campus", "critical_it_mw", "design", "MW", 30.0),
        ("campus", "critical_it_mw", "design", "MW", 48.0),
    ]:
        raise OfficialOperatorSocialError(f"capacity contract differs: {contract!r}")
    if [document["lifecycle"][0]["value"] for document in documents] != [
        "under_construction",
        "under_construction",
        "shell",
        "under_construction",
        "under_construction",
    ]:
        raise OfficialOperatorSocialError("lifecycle contract differs")
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
    if len(stable_keys) != 10 or len(evidence_keys) != 9:
        raise OfficialOperatorSocialError("planned source keys are not unique")
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
            collisions[str(source.relative_to(ROOT))] = {
                "stable_keys": stable_overlap,
                "evidence_keys": evidence_overlap,
            }
    if collisions:
        raise OfficialOperatorSocialError(f"source collision detected: {collisions!r}")


def _validate_frozen_witnesses() -> None:
    for target, pin in V84_PINS.items():
        _pin(target, pin)
    if tree_digest(V84_RELEASE) != V84_TREE_SHA256:
        raise OfficialOperatorSocialError("v84 release tree differs")
    for target, pin in PRIOR_REVIEW_PINS.items():
        _pin(target, pin)
    prior = json.loads(
        (PRIOR_REVIEW_ARTIFACT / "candidate-assessment.json").read_text(
            encoding="utf-8"
        )
    )
    row = next(
        (
            item
            for item in prior.get("candidates", [])
            if item.get("candidate_id") == "odata-sp04-phase-2"
        ),
        None,
    )
    if (
        row is None
        or row.get("seed_eligible") is not False
        or row.get("source_record_created") is not False
    ):
        raise OfficialOperatorSocialError("prior SP04 review-only witness differs")
    _v84_duplicate_witness()


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise OfficialOperatorSocialError(
            f"capture directory is absent or unsafe: {directory}"
        )
    entries = list(directory.iterdir())
    if len(entries) != CAPTURE_FILE_COUNT:
        raise OfficialOperatorSocialError("capture directory file count differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise OfficialOperatorSocialError("capture directory contains a non-file")
    if sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES:
        raise OfficialOperatorSocialError("capture directory total bytes differs")
    if tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise OfficialOperatorSocialError("capture directory tree differs")
    if set(CAPTURE_FILE_PINS) != {entry.name for entry in entries}:
        raise OfficialOperatorSocialError("capture directory closed set differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(directory / name, pin)


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory() as temporary:
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
            "entities": 10,
            "entity_snapshots": 10,
            "evidence": 9,
            "lifecycle_observations": 5,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 2,
        }
        if counts != expected:
            raise OfficialOperatorSocialError(
                f"offline import counts differ: {counts!r}"
            )
        capacities = [
            tuple(row)
            for row in connection.execute(
                "SELECT e.stable_key, c.metric, c.stage, c.unit, c.base "
                "FROM capacity_estimates AS c JOIN entities AS e ON e.id=c.entity_id "
                "ORDER BY c.base"
            )
        ]
        expected_capacities = [
            (
                "curated:multidc-shoham-campus",
                "critical_it_mw",
                "design",
                "MW",
                30.0,
            ),
            (
                "curated:odata-dc-sp04-osasco-campus",
                "critical_it_mw",
                "design",
                "MW",
                48.0,
            ),
        ]
        if capacities != expected_capacities:
            raise OfficialOperatorSocialError(
                f"offline capacity rows differ: {capacities!r}"
            )
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
        raise OfficialOperatorSocialError("artifact must be an ordinary directory")
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise OfficialOperatorSocialError("artifact closed file set differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries.values()):
        raise OfficialOperatorSocialError("artifact contains a non-ordinary file")
    if stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise OfficialOperatorSocialError("artifact directory mode differs")
    if any(stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries.values()):
        raise OfficialOperatorSocialError("artifact file mode differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest):
        raise OfficialOperatorSocialError("manifest JSON is not canonical")
    if (
        manifest.get("artifact_id") != ARTIFACT_ID
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or manifest.get("candidate_assessments") != 5
        or manifest.get("curated_source_records") != 5
        or manifest.get("seed_eligible_source_records") != 5
        or manifest.get("review_only_candidates") != 0
        or manifest.get("successful_http_200_body_captures") != 10
        or manifest.get("http_error_body_captures") != 2
        or manifest.get("regional_completeness_claimed") is not False
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise OfficialOperatorSocialError("manifest contract differs")
    if [row["path"] for row in manifest["files"]] != list(CONTENT_FILES):
        raise OfficialOperatorSocialError("manifest file order differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (
            row["bytes"],
            row["sha256"],
        ):
            raise OfficialOperatorSocialError(
                f"manifest file pin differs: {row['path']}"
            )
    expected_sidecar = f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    if entries["manifest.sha256"].read_text(encoding="utf-8") != expected_sidecar:
        raise OfficialOperatorSocialError("manifest checksum differs")
    expected = _artifact_documents(manifest["recorded_at"], expected_source_documents())
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected[name]:
            raise OfficialOperatorSocialError(f"artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records:
        raise OfficialOperatorSocialError("artifact source pins differ")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise OfficialOperatorSocialError("validation wall clock lacks timezone")
    if require_live:
        if now.astimezone(UTC) < target:
            raise OfficialOperatorSocialError("artifact recorded_at is not live")
        _assert_final_ctimes((*paths.values(), path), target)
    for capture in CAPTURES.values():
        if _instant(capture["retrieved_at"]) > target:
            raise OfficialOperatorSocialError(
                "capture retrieval post-dates recorded_at"
            )
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
        raise OfficialOperatorSocialError(
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
    return (
        source_stage,
        *sorted(source_stage.iterdir(), key=lambda item: item.name),
        artifact_stage,
        *sorted(artifact_stage.iterdir(), key=lambda item: item.name),
    )


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
        raise OfficialOperatorSocialError("recorded_at must be future before staging")
    source_stage = Path(
        tempfile.mkdtemp(
            prefix=".official-builds-operator-social-next.",
            dir=SOURCES_ROOT,
        )
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
            raise OfficialOperatorSocialError(
                "private staging did not finish before recorded_at"
            )
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
                raise OfficialOperatorSocialError(
                    f"source identity changed on promotion: {name}"
                )
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
            raise OfficialOperatorSocialError("artifact identity changed on promotion")
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
        raise OfficialOperatorSocialError(
            "both capture origin and Trash destination exist"
        )
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(CAPTURE_TRASH)


def _default_recorded_at() -> str:
    target = math.ceil(time.time() + 35.0)
    return datetime.fromtimestamp(target, UTC).isoformat().replace("+00:00", "Z")


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    """Publish five sources and their closed governed artifact."""

    target_text = recorded_at or _default_recorded_at()
    finals = tuple(SOURCES_ROOT / name for name in SOURCE_FILENAMES) + (ARTIFACT,)
    _require_finals_absent(finals, "initial")
    _validate_source_collisions()
    _validate_frozen_witnesses()
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
    _validate_frozen_witnesses()
    manifest = validate_artifact(ARTIFACT)
    source_records = _validate_sources(_source_paths(SOURCES_ROOT))
    return {
        "artifact_id": ARTIFACT_ID,
        "recorded_at": manifest["recorded_at"],
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "logical_tree_sha256": manifest["tree_sha256"],
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "source_records": source_records,
        "counts": {
            "candidates": 5,
            "source_records": 5,
            "seed_eligible": 5,
            "review_only": 0,
            "evidence": 9,
            "entities": 10,
            "lifecycle": 5,
            "operating_models": 0,
            "workloads": 0,
            "capacities": 2,
            "coordinates": 0,
            "geometry": 0,
            "placements": 0,
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
