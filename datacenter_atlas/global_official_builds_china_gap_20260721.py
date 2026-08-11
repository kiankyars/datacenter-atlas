"""Publish a bounded official-source China and Hong Kong build-gap artifact.

The carrier is independent of open-seed and downstream publication. It stages
every source and artifact byte before the declared recording instant, waits for
that instant, and performs no-replace promotion with identity-safe rollback.
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

from .external_captures import resolve_external_capture
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from . import global_official_builds_six_candidate_20260721 as publication
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "global-official-builds-china-gap-2026-07-21-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".global-official-builds-china-gap-20260721.lock"
CAPTURE_ORIGIN = Path("/private/tmp/dc-official-china-gap-20260721.BUEbM9")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-official-china-gap-20260721.BUEbM9")
CAPTURE_TREE_SHA256 = (
    "a4cc9c9ed763131bd03e32b851550045240b1fea978b2a66e75d1b81da1cdb83"
)
CAPTURE_FILE_COUNT = 39
CAPTURE_BYTES = 510_600

V73_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v73.json"
V73_RELEASE = ROOT / "releases/2026-07-21-open-seed-v73"
V73_MANIFEST = V73_RELEASE / "manifest.json"
V73_ENTITIES = V73_RELEASE / "entities.csv"
V73_PINS = {
    V73_DEFINITION: (
        88_004,
        "cf8a4cfb8861ab732cdb9e72a01cbdd01d0e435102c47fd6d92bc30ebf11f97d",
    ),
    V73_MANIFEST: (
        12_814,
        "229c572759ab493448b788946a0c8a61ff6995d0ab505bea2af08860a19e204d",
    ),
    V73_ENTITIES: (
        887_459,
        "8c50475f1a58a7f7623a4eef2706be3f63bca0175a5fe4fffecdd548442944e7",
    ),
}
V73_TREE_SHA256 = (
    "692583b86324b746fd6edf0ec2dc5101efa86ce0f08e04831e0d471e767a6394"
)
V73_INPUT_COUNT = 397

SOURCE_FILENAMES = (
    "curated-official-2026-07-21-runze-chongqing-phase-2-p6-current-build.json",
    "curated-official-2026-07-21-china-telecom-guizhou-b5-b6-current-build.json",
    "curated-official-2026-07-21-baoji-digital-building-mobile-dc-current-build.json",
    "curated-official-2026-07-21-digital-qinghai-telecom-phase-2-current-build.json",
    "curated-official-2026-07-21-mobile-plateau-haidong-phase-2-current-build.json",
    "curated-official-2026-07-21-zhipu-iflytek-haidong-ai-base-current-build.json",
    "curated-official-2026-07-21-haidong-training-inference-ai-current-build.json",
    "curated-official-2026-07-21-wuhu-longteng-ai-park-current-build.json",
    "curated-official-2026-07-21-china-telecom-tongling-dated-build.json",
    "curated-official-2026-07-21-runze-hong-kong-sandy-ridge-current-build.json",
)

CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

ChinaGapError = publication.OfficialBuildsError
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


CAPTURE_BODIES: dict[str, dict[str, Any]] = {
    "runze_chongqing": {
        "filename": "runze_chongqing.body",
        "url": "https://cqjlp.gov.cn/zwxx/qxdt/202604/t20260413_15606753_wap.html",
        "retrieved_at": "2026-07-21T15:55:01Z",
        "bytes": 26_900,
        "sha256": "289d2df4ef216068ef151b34d7a681ad59d79f6d56cf47baebcf8dbab6a01fca",
        "content_type": "text/html; charset=utf-8",
    },
    "guizhou_cscec": {
        "filename": "guizhou_cscec.body",
        "url": "https://www.cscec.com/xwzx_new/zqydt_new/202604/3939955.html",
        "retrieved_at": "2026-07-21T15:55:05Z",
        "bytes": 78_633,
        "sha256": "7af9d18c3c131ddfc9aea6f59b27d1944de7d15332112200fbeb811d4f69802a",
        "content_type": "text/html; charset=utf-8",
    },
    "baoji": {
        "filename": "baoji.body",
        "url": "https://jt.baojidj.gov.cn/info/1125/14700.htm",
        "retrieved_at": "2026-07-21T15:55:08Z",
        "bytes": 40_185,
        "sha256": "37fac1029875d250e2733b6294b8048a3b2b8edfa90d11a86b2466bd53936edd",
        "content_type": "text/html; charset=utf-8",
    },
    "haidong": {
        "filename": "haidong.body",
        "url": "https://www.huzhu.gov.cn/info/1007/85926.htm",
        "retrieved_at": "2026-07-21T15:55:09Z",
        "bytes": 22_725,
        "sha256": "0c6f983f91c9f2804287c2cbd8420c6006af2f500cb2b265aebb1d1a4bb2c9ba",
        "content_type": "text/html; charset=utf-8",
    },
    "wuhu": {
        "filename": "wuhu.body",
        "url": "https://tzcjzx.wuhu.gov.cn/zsdt/gzdt/8910580.html",
        "retrieved_at": "2026-07-21T15:55:10Z",
        "bytes": 15_837,
        "sha256": "9bd43453fbba92c7ef81aeb58c8018b0b61e6e8138aa19685df635b81d4fe49c",
        "content_type": "text/html; charset=utf-8",
    },
    "tongling": {
        "filename": "tongling.body",
        "url": "https://zfcxjsj.tl.gov.cn/tlszfhcxjsj/c00126/pc/content/content_2061658207261876224.html",
        "retrieved_at": "2026-07-21T15:55:11Z",
        "bytes": 76_531,
        "sha256": "574a2499d1cd3080d31b69ea27498410dcefc9a89b2b18949fcccedd88b7c766",
        "content_type": "text/html; charset=utf-8",
    },
    "hongkong_gov": {
        "filename": "hongkong_gov.body",
        "url": "https://www.news.gov.hk/chi/2026/03/20260328/20260328_120409_346.html",
        "retrieved_at": "2026-07-21T15:55:11Z",
        "bytes": 34_904,
        "sha256": "b7666c6efd09543e7054107eb827719f1a9f83747ec6983badbbc98c6245dfc1",
        "content_type": "text/html; charset=utf-8",
    },
    "xinhua_hongkong": {
        "filename": "xinhua_hongkong.body",
        "url": "https://www.news.cn/gangao/20260522/fbc83ad0f3cb4574867bba5cf6bb20e6/c.html",
        "retrieved_at": "2026-07-21T15:55:12Z",
        "bytes": 20_410,
        "sha256": "35d1d57e3b0247ba0ce535fe3b99bc8d4e6905e7b138ae063b0f91d7e37a21b2",
        "content_type": "text/html; charset=utf-8",
    },
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
    capture = CAPTURE_BODIES[capture_id]
    common = {
        "content_hash_scope": (
            f"SHA-256 of the exact {capture['bytes']}-byte content-decoded "
            "official response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture_id,
        "capture_method": "curl_location_compressed",
        "http_status": 200,
        "content_type": capture["content_type"],
        "request_credentials_supplied": False,
        "rights_scope": (
            "Compact factual extraction from all-rights-reserved official bytes; "
            "the response body and publisher media are not redistributed."
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
    value: str,
    evidence_key: str,
    as_of_date: str,
    *,
    method: str = "authoritative_physical_status_update",
    confidence: float = 0.99,
) -> dict[str, Any]:
    return {
        "entity": "project",
        "value": value,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": method,
        "confidence": confidence,
    }


def _document(
    *,
    evidence: list[dict[str, Any]],
    campus_key: str,
    campus_name: str,
    project_key: str,
    project_name: str,
    country: str,
    address: str,
    roles: Mapping[str, list[str]],
    evidence_key: str,
    as_of_date: str,
    lifecycle: list[dict[str, Any]],
    confidence: float = 0.98,
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
            evidence_key=evidence_key,
            as_of_date=as_of_date,
            confidence=confidence,
        ),
        "project": _entity(
            stable_key=project_key,
            name=project_name,
            country=country,
            address=address,
            roles=roles,
            evidence_key=evidence_key,
            as_of_date=as_of_date,
            confidence=confidence,
        ),
        "lifecycle": lifecycle,
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _runze_chongqing_source() -> dict[str, Any]:
    evidence_key = "china-runze-chongqing-phase2-p6-shell-2026-04-01"
    publisher = "Chongqing Jiulongpo District People's Government"
    evidence = _evidence(
        "runze_chongqing",
        key=evidence_key,
        kind="government_record",
        title="Runze computing-center power heart topped out",
        publisher=publisher,
        source_family="chongqing_jiulongpo_government_updates",
        published_at="2026-04-13",
        excerpt=(
            "A district-government site visit records the P-6 power center in "
            "Runze Southwest International Information Port phase 2 as topped out "
            "on 2026-04-01."
        ),
        metadata={
            "status_wording_as_reported": (
                "Phase 2 began in August 2025; the P-6 power center topped out on "
                "2026-04-01."
            ),
            "physical_status_scope": (
                "Shell is retained only for the P-6 power-center build. A5 and A6 "
                "are described as subsequent data-center construction and are not "
                "asserted to have started."
            ),
            "month_only_start_scope": (
                "The August 2025 start has no exact day and is metadata only."
            ),
            "capacity_guardrail": (
                "The reported 32,000-rack campus plan and 8,000-rack phase-1 figure "
                "are not phase-2/P-6 capacities. Building area is not power or energy."
            ),
            "currentness_scope": (
                "This is a dated 2026-04-01 physical observation; current status "
                "after that date is unknown."
            ),
        },
    )
    campus_key = "curated:runze-southwest-international-information-port-chongqing"
    roles = {"developer": ["Chongqing Runze Zhihui Big Data Co., Ltd."]}
    return _document(
        evidence=[evidence],
        campus_key=campus_key,
        campus_name="Runze Southwest International Information Port",
        project_key=f"{campus_key}:phase-2-p6-power-center-build",
        project_name="Runze Southwest Information Port Phase 2 P-6 Power Center Build",
        country="China",
        address="Xipeng Industrial Park, Jiulongpo District, Chongqing, China",
        roles=roles,
        evidence_key=evidence_key,
        as_of_date="2026-04-01",
        lifecycle=[_lifecycle("shell", evidence_key, "2026-04-01")],
    )


def _guizhou_source() -> dict[str, Any]:
    evidence_key = "china-telecom-guizhou-park-b5-b6-shell-by-2026-04-22"
    publisher = "China State Construction Engineering Corporation"
    evidence = _evidence(
        "guizhou_cscec",
        key=evidence_key,
        kind="company_disclosure",
        title=(
            "China Telecom Cloud Computing Guizhou Information Park 2.1 phase "
            "second package topped out"
        ),
        publisher=publisher,
        source_family="cscec_project_updates",
        published_at="2026-04-22",
        excerpt=(
            "CSCEC reports that the main structures of the B5 and B6 data-center "
            "buildings were fully topped out by its 2026-04-22 publication."
        ),
        metadata={
            "status_wording_as_reported": (
                "B5 and B6, the 2.1-phase second-package data centers, had their "
                "main structures fully topped out."
            ),
            "date_scope": (
                "The page says recently and gives no event day; 2026-04-22 is "
                "retained as the latest-by publication date, not an invented event date."
            ),
            "capacity_guardrail": (
                "No campus compute, electricity, PUE, rack, grid, generation, load, "
                "or energy value is assigned to B5 or B6."
            ),
            "china_telecom_capture_scope": (
                "A separate China Telecom URL returned HTTP 412 and contributes no "
                "claim. This record is governed solely by the direct CSCEC body."
            ),
            "currentness_scope": (
                "This is a latest-by 2026-04-22 shell observation; current status "
                "after that date is unknown."
            ),
        },
    )
    campus_key = "curated:china-telecom-cloud-computing-guizhou-information-park"
    roles = {
        "owner": ["China Telecom Corporation Limited"],
        "contractor": ["China Construction Fifth Engineering Division Corp., Ltd."],
    }
    return _document(
        evidence=[evidence],
        campus_key=campus_key,
        campus_name="China Telecom Cloud Computing Guizhou Information Park",
        project_key=f"{campus_key}:phase-2-1-b5-b6-data-center-build",
        project_name="Guizhou Information Park 2.1 Phase B5 and B6 Build",
        country="China",
        address="Gui'an New Area, Guizhou, China",
        roles=roles,
        evidence_key=evidence_key,
        as_of_date="2026-04-22",
        lifecycle=[_lifecycle("shell", evidence_key, "2026-04-22")],
    )


def _baoji_source() -> dict[str, Any]:
    evidence_key = "china-baoji-digital-building-mobile-dc-build-2026-07-15"
    publisher = "Jintai District Committee, Baoji"
    evidence = _evidence(
        "baoji",
        key=evidence_key,
        kind="government_record",
        title="Wolongsiguan subdistrict first-half project update",
        publisher=publisher,
        source_family="baoji_jintai_district_updates",
        published_at="2026-07-15",
        excerpt=(
            "The official district update records main-structure work accelerating "
            "at the Baoji Digital Building and China Mobile Data Center project."
        ),
        metadata={
            "status_wording_as_reported": "Main-structure construction is accelerating.",
            "physical_status_scope": (
                "Only generic under_construction is retained; no exact completion "
                "percentage or finer building stage is inferred."
            ),
            "cost_guardrail": (
                "The reported CNY 1.5 billion investment is project cost, not power, "
                "load, generation, consumption, or annual energy."
            ),
            "currentness_scope": (
                "This is a 2026-07-15 physical observation, not a timeless current claim."
            ),
        },
    )
    campus_key = "curated:baoji-digital-building-china-mobile-data-center"
    return _document(
        evidence=[evidence],
        campus_key=campus_key,
        campus_name="Baoji Digital Building and China Mobile Data Center",
        project_key=f"{campus_key}:main-structure-build",
        project_name="Baoji Digital Building and China Mobile Data Center Build",
        country="China",
        address="Wolongsiguan Subdistrict, Jintai District, Baoji, Shaanxi, China",
        roles={},
        evidence_key=evidence_key,
        as_of_date="2026-07-15",
        lifecycle=[_lifecycle("under_construction", evidence_key, "2026-07-15")],
    )


def _haidong_source(
    *,
    evidence_key: str,
    exact_chinese_name: str,
    campus_key: str,
    campus_name: str,
    project_suffix: str,
    project_name: str,
) -> dict[str, Any]:
    publisher = "Huzhu County People's Government"
    evidence = _evidence(
        "haidong",
        key=evidence_key,
        kind="government_record",
        title="Haidong mayor visits computing-industry construction sites",
        publisher=publisher,
        source_family="haidong_government_project_updates",
        published_at="2026-06-24",
        excerpt=(
            f"The official bulletin names {exact_chinese_name} among the project "
            "construction sites visited in Haidong Industrial Park on 2026-06-23."
        ),
        metadata={
            "exact_project_name_as_reported": exact_chinese_name,
            "status_wording_as_reported": (
                "The mayor visited the named project construction site on 2026-06-23 "
                "to review project construction, safety, and factor support."
            ),
            "physical_status_scope": (
                "The explicit construction-site visit supports only generic "
                "under_construction. No finer stage or completion percentage is inferred."
            ),
            "shared_bulletin_scope": (
                "One direct official bulletin separately names four data/AI-center "
                "projects. This evidence key and source record are scoped only to the "
                "project named above."
            ),
            "capacity_guardrail": (
                "No capacity, power, load, generation, PUE, energy, rack, or compute "
                "claim is emitted. The source-grid-load-storage phrase is a project-name "
                "component, not a conversion or measured-energy claim."
            ),
            "currentness_scope": (
                "This is a 2026-06-23 physical observation; current status after that "
                "date is unknown."
            ),
        },
    )
    address = "Haidong Industrial Park Computing Industry Park, Qinghai, China"
    return _document(
        evidence=[evidence],
        campus_key=campus_key,
        campus_name=campus_name,
        project_key=f"{campus_key}:{project_suffix}",
        project_name=project_name,
        country="China",
        address=address,
        roles={},
        evidence_key=evidence_key,
        as_of_date="2026-06-23",
        lifecycle=[_lifecycle("under_construction", evidence_key, "2026-06-23")],
    )


def _digital_qinghai_source() -> dict[str, Any]:
    return _haidong_source(
        evidence_key="china-telecom-digital-qinghai-phase2-build-2026-06-23",
        exact_chinese_name="中国电信数字青海绿色大数据中心二期",
        campus_key="curated:china-telecom-digital-qinghai-green-big-data-center",
        campus_name="China Telecom Digital Qinghai Green Big Data Center",
        project_suffix="phase-2-build",
        project_name="Digital Qinghai Green Big Data Center Phase 2 Build",
    )


def _mobile_plateau_source() -> dict[str, Any]:
    return _haidong_source(
        evidence_key="china-mobile-plateau-haidong-phase2-build-2026-06-23",
        exact_chinese_name="中国移动高原大数据中心二期",
        campus_key="curated:china-mobile-plateau-big-data-center-haidong",
        campus_name="China Mobile Plateau Big Data Center Haidong",
        project_suffix="phase-2-build",
        project_name="China Mobile Plateau Big Data Center Phase 2 Build",
    )


def _zhipu_iflytek_source() -> dict[str, Any]:
    return _haidong_source(
        evidence_key="china-zhipu-iflytek-haidong-ai-base-build-2026-06-23",
        exact_chinese_name="智谱讯飞海东智算基地暨源网荷储算电协同一体化",
        campus_key="curated:zhipu-iflytek-haidong-ai-computing-base",
        campus_name="Zhipu iFlytek Haidong AI Computing Base",
        project_suffix="source-grid-load-storage-integrated-build",
        project_name=(
            "Zhipu iFlytek Haidong AI Base and Source-Grid-Load-Storage "
            "Integrated Build"
        ),
    )


def _haidong_training_inference_source() -> dict[str, Any]:
    return _haidong_source(
        evidence_key="china-haidong-training-inference-ai-center-build-2026-06-23",
        exact_chinese_name="青海海东训推一体化智算中心",
        campus_key="curated:qinghai-haidong-training-inference-integrated-ai-center",
        campus_name="Qinghai Haidong Training and Inference Integrated AI Center",
        project_suffix="current-build",
        project_name="Haidong Training and Inference Integrated AI Center Build",
    )


def _wuhu_source() -> dict[str, Any]:
    evidence_key = "china-wuhu-longteng-ai-internet-park-build-2026-02-26"
    publisher = "Wuhu Investment Promotion Center"
    evidence = _evidence(
        "wuhu",
        key=evidence_key,
        kind="government_record",
        title="AI-computing city construction continued through Spring Festival",
        publisher=publisher,
        source_family="wuhu_government_project_updates",
        published_at="2026-02-26",
        excerpt=(
            "The official Wuhu update records equipment assembly and adjustment at "
            "the 珑腾 AI Computing Internet Industrial Park construction site."
        ),
        metadata={
            "exact_project_name_as_reported": "芜湖珑腾智算互联网产业园",
            "transliteration_scope": (
                "Longteng is a cautious descriptive transliteration of 珑腾; it is "
                "not asserted as a separate registered English legal name."
            ),
            "status_wording_as_reported": (
                "Equipment was being assembled and adjusted ahead of a key hoisting "
                "stage, with construction continuing through the holiday."
            ),
            "physical_status_scope": (
                "Generic under_construction is retained. Equipment activity is not "
                "converted into MEP completion, facility commissioning, or operation."
            ),
            "capacity_guardrail": (
                "No capacity, load, generation, consumption, annual energy, PUE, rack, "
                "or compute value is emitted."
            ),
            "currentness_scope": (
                "This is a 2026-02-26 physical observation; current status after that "
                "date is unknown."
            ),
        },
    )
    campus_key = "curated:wuhu-longteng-ai-computing-internet-industrial-park"
    roles = {"contractor": ["China Construction Second Engineering Bureau Anhui"]}
    return _document(
        evidence=[evidence],
        campus_key=campus_key,
        campus_name="Wuhu 珑腾 (Longteng) AI Computing Internet Industrial Park",
        project_key=f"{campus_key}:current-build",
        project_name="Wuhu 珑腾 AI Computing Internet Industrial Park Build",
        country="China",
        address="Wuhu, Anhui, China",
        roles=roles,
        evidence_key=evidence_key,
        as_of_date="2026-02-26",
        lifecycle=[_lifecycle("under_construction", evidence_key, "2026-02-26")],
    )


def _tongling_source() -> dict[str, Any]:
    evidence_key = "china-telecom-tongling-rainwater-site-build-2026-02-07"
    publisher = "Tongling Municipal Housing and Urban-Rural Development Bureau"
    evidence = _evidence(
        "tongling",
        key=evidence_key,
        kind="government_record",
        title="Municipal administrative record concerning a Tongling project work site",
        publisher=publisher,
        source_family="tongling_housing_authority_records",
        published_at="2026-06-02",
        excerpt=(
            "The municipal record establishes that external rainwater-network work "
            "was taking place at the China Telecom Tongling AI Computing Center project "
            "site on 2026-02-07."
        ),
        metadata={
            "source_context": (
                "The publisher record is an administrative safety notice. Only the "
                "dated physical construction fact is extracted; human impact is not "
                "summarized or used as project characterization."
            ),
            "status_wording_as_reported": (
                "External rainwater-network construction at the project site on "
                "2026-02-07."
            ),
            "physical_status_scope": (
                "Generic under_construction is retained. External civil works do not "
                "establish the data-center building's finer stage, completion, "
                "commissioning, or operation."
            ),
            "capacity_guardrail": (
                "No capacity, load, generation, consumption, annual energy, PUE, rack, "
                "or compute value is emitted."
            ),
            "currentness_scope": (
                "This is a 2026-02-07 physical observation; current status after that "
                "date is unknown."
            ),
        },
    )
    campus_key = "curated:china-telecom-tongling-ai-computing-center"
    roles = {"contractor": ["Anzhi Construction Group Co., Ltd."]}
    return _document(
        evidence=[evidence],
        campus_key=campus_key,
        campus_name="China Telecom Tongling AI Computing Center",
        project_key=f"{campus_key}:data-center-and-site-infrastructure-build",
        project_name="Tongling AI Computing Center and Site Infrastructure Build",
        country="China",
        address="Tongling Economic Development Zone, Anhui, China",
        roles=roles,
        evidence_key=evidence_key,
        as_of_date="2026-02-07",
        lifecycle=[_lifecycle("under_construction", evidence_key, "2026-02-07")],
    )


def _hong_kong_source() -> dict[str, Any]:
    government_key = "hong-kong-runze-sandy-ridge-build-start-2026-03-28"
    xinhua_key = "hong-kong-runze-sandy-ridge-physical-build-2026-05-20"
    government = _evidence(
        "hongkong_gov",
        key=government_key,
        kind="government_record",
        title="Sandy Ridge data park project commences",
        publisher="Government of the Hong Kong Special Administrative Region",
        source_family="hong_kong_government_news",
        published_at="2026-03-28",
        excerpt=(
            "The Hong Kong government records that Runze (Hong Kong) Sandy Ridge Data "
            "Park held its commencement ceremony after the project entered the site."
        ),
        metadata={
            "physical_status_scope": (
                "A dated authoritative construction-start observation is retained. "
                "The ceremony alone does not establish a finer physical stage."
            ),
            "area_and_cost_guardrail": (
                "The reported 250,000 square metres and HKD 23.8 billion are area and "
                "cost, not capacity, load, generation, consumption, or energy."
            ),
            "compute_guardrail": (
                "The 2032 floating-point-compute target is compute, not MW or MWh, and "
                "is not normalized."
            ),
        },
    )
    xinhua = _evidence(
        "xinhua_hongkong",
        key=xinhua_key,
        kind="government_record",
        title="Sandy Ridge data park runs at Hong Kong new speed",
        publisher="Xinhua News Agency",
        source_family="xinhua_hong_kong_reports",
        published_at="2026-05-22",
        excerpt=(
            "Xinhua's report and 2026-05-20 site caption describe piling machinery, "
            "earthmoving equipment, cranes, and workers at the Sandy Ridge build."
        ),
        metadata={
            "physical_observation_date": "2026-05-20",
            "physical_status_scope": (
                "The explicit machinery and piling observation supports generic "
                "under_construction only; no completion percentage or finer stage is "
                "inferred."
            ),
            "site_area_square_metres_as_reported": 110_000,
            "area_guardrail": (
                "The approximate 110,000-square-metre site is area, not power or energy."
            ),
            "currentness_scope": (
                "This is a 2026-05-20 physical observation; current status after that "
                "date is unknown."
            ),
        },
    )
    campus_key = "curated:runze-hong-kong-sandy-ridge-data-facility-cluster"
    roles = {"developer": ["Runze Intelligent Computing Technology Group Co., Ltd."]}
    return _document(
        evidence=[government, xinhua],
        campus_key=campus_key,
        campus_name="Runze Hong Kong Sandy Ridge Data Facility Cluster",
        project_key=f"{campus_key}:initial-build",
        project_name="Runze Hong Kong Sandy Ridge Initial Build",
        country="Hong Kong",
        address="Sandy Ridge, North Metropolis, Hong Kong",
        roles=roles,
        evidence_key=xinhua_key,
        as_of_date="2026-05-20",
        lifecycle=[
            _lifecycle(
                "under_construction",
                government_key,
                "2026-03-28",
                method="authoritative_construction_start",
            ),
            _lifecycle(
                "under_construction",
                xinhua_key,
                "2026-05-20",
                method="physical_observation",
            ),
        ],
    )


def expected_source_documents() -> dict[str, dict[str, Any]]:
    """Return the ten exact schema-1.1 source documents."""

    builders = (
        _runze_chongqing_source,
        _guizhou_source,
        _baoji_source,
        _digital_qinghai_source,
        _mobile_plateau_source,
        _zhipu_iflytek_source,
        _haidong_training_inference_source,
        _wuhu_source,
        _tongling_source,
        _hong_kong_source,
    )
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
                "operating_model_observations": 0,
                "workload_observations": 0,
                "capacity_estimates": 0,
                "coordinates_present": 0,
                "geometry_present": 0,
                "disposition": "seed_eligible_fresh_official_physical_update",
                "seed_eligible": True,
                "seeded": False,
            }
        )
    return records


def _candidate_assessments(recorded_at: str) -> dict[str, Any]:
    candidate_specs = (
        (
            "runze-chongqing-phase-2-p6",
            SOURCE_FILENAMES[0],
            "2026-04-01",
            [
                "A5 and A6 are subsequent/future and are not asserted started",
                "32,000 campus racks and 8,000 phase-1 racks are not phase-2 capacity",
            ],
        ),
        (
            "china-telecom-guizhou-b5-b6",
            SOURCE_FILENAMES[1],
            "2026-04-22",
            [
                "China Telecom HTTP-412 response contributes no claim",
                "campus compute, electricity, PUE, and rack values are not assigned",
            ],
        ),
        (
            "baoji-digital-building-china-mobile-data-center",
            SOURCE_FILENAMES[2],
            "2026-07-15",
            ["CNY 1.5 billion is project cost, not capacity"],
        ),
        (
            "china-telecom-digital-qinghai-phase-2",
            SOURCE_FILENAMES[3],
            "2026-06-23",
            ["no capacity or energy claim"],
        ),
        (
            "china-mobile-plateau-data-center-phase-2",
            SOURCE_FILENAMES[4],
            "2026-06-23",
            ["no capacity or energy claim"],
        ),
        (
            "zhipu-iflytek-haidong-ai-base",
            SOURCE_FILENAMES[5],
            "2026-06-23",
            [
                "source-grid-load-storage is a project-name component, not a power conversion"
            ],
        ),
        (
            "qinghai-haidong-training-inference-ai-center",
            SOURCE_FILENAMES[6],
            "2026-06-23",
            ["no capacity or workload classification inferred"],
        ),
        (
            "wuhu-longteng-ai-computing-internet-park",
            SOURCE_FILENAMES[7],
            "2026-02-26",
            ["equipment activity is not commissioning or operation"],
        ),
        (
            "china-telecom-tongling-ai-computing-center",
            SOURCE_FILENAMES[8],
            "2026-02-07",
            [
                "external rainwater work does not establish a finer building stage",
                "the safety record's human impact is not used as project characterization",
            ],
        ),
        (
            "runze-hong-kong-sandy-ridge-data-facility-cluster",
            SOURCE_FILENAMES[9],
            "2026-05-20",
            [
                "110,000 and 250,000 square metres are area only",
                "HKD 23.8 billion is cost only",
                "180,000 PFLOPS is compute only",
            ],
        ),
    )
    source_rows = [
        {
            "candidate_id": candidate_id,
            "decision": "seed_eligible_fresh_official_physical_update",
            "source_record_created": True,
            "source_path": f"sources/{source_name}",
            "seed_eligible": True,
            "seeded": False,
            "last_observed_physical_date": observed_date,
            "confirmed_current_status": False,
            "current_status_after_last_observation": "unknown",
            "coordinates_present": False,
            "geometry_present": False,
            "capacity_rows": 0,
            "excluded_claims": excluded_claims,
        }
        for candidate_id, source_name, observed_date, excluded_claims in candidate_specs
    ]
    changle = {
        "candidate_id": "changle-airport-free-trade-zone-ai-computing-center",
        "decision": "review_only_no_direct_publisher_capture",
        "source_record_created": False,
        "source_path": None,
        "seed_eligible": False,
        "seeded": False,
        "last_observed_physical_date": None,
        "confirmed_current_status": False,
        "current_status_after_last_observation": "unknown",
        "coordinates_present": False,
        "geometry_present": False,
        "capacity_rows": 0,
        "requested_publisher_url": (
            "https://www.fzcl.gov.cn/xjwz/zwgk/zfxxgkzdgz/zdjsxm/jsqk/"
            "202601/t20260119_5273462.htm"
        ),
        "technical_incident": {
            "direct_hostname_attempt": (
                "Three curl attempts returned no publisher bytes and timed out."
            ),
            "resolved_a_records": [
                "112.54.42.147",
                "121.204.110.23",
                "218.106.155.204",
            ],
            "explicit_a_record_attempts": (
                "Each explicit TLS attempt returned no publisher bytes and timed out."
            ),
            "browser_fallback": (
                "Chrome fallback did not yield a loaded publisher response or savable bytes."
            ),
            "alternate_pdf_attempt": (
                "A city-newspaper PDF candidate returned HTTP 404 and was not used."
            ),
        },
        "browser_context_not_evidence": {
            "transformed_page_text_seen": True,
            "search_snippets_seen": True,
            "used_for_normalized_claims": False,
            "retained_in_artifact": False,
        },
        "excluded_claims": [
            "no lifecycle, identity, role, type, capacity, or geometry is normalized",
            "15,000P is compute, not MW",
            "phase-2 server manufacturing is distinct from the data-center build",
        ],
    }
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-build-candidate-assessment-v3",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "candidate_count": 11,
        "source_record_count": 10,
        "seed_eligible_count": 10,
        "review_only_count": 1,
        "technical_incident_group_count": 2,
        "candidates": [changle, *source_rows],
    }


def _capture_directory() -> Path:
    if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
        raise ChinaGapError("both capture origin and Trash destination exist")
    if CAPTURE_ORIGIN.exists():
        return CAPTURE_ORIGIN
    if CAPTURE_TRASH.exists():
        return CAPTURE_TRASH
    return resolve_external_capture(CAPTURE_TRASH)


def _capture_file_rows() -> list[dict[str, Any]]:
    directory = _capture_directory()
    return [
        {
            "path": entry.name,
            "bytes": entry.stat().st_size,
            "sha256": _sha256(entry),
        }
        for entry in sorted(directory.iterdir(), key=lambda item: item.name)
    ]


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    evidence_uses = {
        "runze_chongqing": ["china-runze-chongqing-phase2-p6-shell-2026-04-01"],
        "guizhou_cscec": [
            "china-telecom-guizhou-park-b5-b6-shell-by-2026-04-22"
        ],
        "baoji": ["china-baoji-digital-building-mobile-dc-build-2026-07-15"],
        "haidong": [
            "china-telecom-digital-qinghai-phase2-build-2026-06-23",
            "china-mobile-plateau-haidong-phase2-build-2026-06-23",
            "china-zhipu-iflytek-haidong-ai-base-build-2026-06-23",
            "china-haidong-training-inference-ai-center-build-2026-06-23",
        ],
        "wuhu": ["china-wuhu-longteng-ai-internet-park-build-2026-02-26"],
        "tongling": ["china-telecom-tongling-rainwater-site-build-2026-02-07"],
        "hongkong_gov": ["hong-kong-runze-sandy-ridge-build-start-2026-03-28"],
        "xinhua_hongkong": [
            "hong-kong-runze-sandy-ridge-physical-build-2026-05-20"
        ],
    }
    successful = [
        {
            "request_id": request_id,
            "requested_url": spec["url"],
            "retrieved_at": spec["retrieved_at"],
            "http_status": 200,
            "content_type": spec["content_type"],
            "body_file": spec["filename"],
            "body_bytes": spec["bytes"],
            "body_sha256": spec["sha256"],
            "content_encoding_as_stored": "decoded_by_curl",
            "evidence_keys": evidence_uses[request_id],
            "rights": "all-rights-reserved",
            "raw_redistributed": False,
        }
        for request_id, spec in CAPTURE_BODIES.items()
    ]
    incidents = [
        {
            "incident_id": "changle-direct-publisher-timeouts",
            "requested_url": (
                "https://www.fzcl.gov.cn/xjwz/zwgk/zfxxgkzdgz/zdjsxm/jsqk/"
                "202601/t20260119_5273462.htm"
            ),
            "result": "no_direct_publisher_body",
            "hostname_attempts": 3,
            "explicit_a_record_attempts": {
                "112.54.42.147": "connect_timeout_no_bytes",
                "121.204.110.23": "connect_timeout_no_bytes",
                "218.106.155.204": "connect_timeout_no_bytes",
            },
            "browser_fallback": "no_loaded_or_savable_publisher_bytes",
            "alternate_pdf_attempt": "http_404_no_body",
            "capture_files": [
                "changle.headers",
                "changle.writeout",
                "changle_112_54_42_147.headers",
                "changle_112_54_42_147.writeout",
                "changle_121_204_110_23.headers",
                "changle_121_204_110_23.writeout",
                "changle_218_106_155_204.headers",
                "changle_218_106_155_204.writeout",
                "changle_fuzhou_evening_news.headers",
                "changle_fuzhou_evening_news.writeout",
            ],
            "evidence_use": False,
            "source_record_created": False,
        },
        {
            "incident_id": "china-telecom-http-412",
            "requested_url": (
                "https://www.chinatelecom.com.cn/ct/news/gdxw/166580.html"
            ),
            "result": "http_412_antibot_response",
            "capture_files": [
                "guizhou_telecom.headers",
                "guizhou_telecom.writeout",
                "guizhou_telecom_retry.body",
                "guizhou_telecom_retry.headers",
                "guizhou_telecom_retry.writeout",
            ],
            "evidence_use": False,
            "claims_copied": False,
            "governing_alternative": "guizhou_cscec",
        },
    ]
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "capture_directory_file_count": CAPTURE_FILE_COUNT,
        "capture_directory_bytes": CAPTURE_BYTES,
        "capture_directory_tree_sha256": CAPTURE_TREE_SHA256,
        "successful_direct_publisher_bodies": successful,
        "successful_direct_publisher_body_count": len(successful),
        "technical_incidents": incidents,
        "technical_incident_group_count": len(incidents),
        "capture_files": _capture_file_rows(),
        "raw_capture_redistributed": False,
    }


def _artifact_documents(
    recorded_at: str,
    source_documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    source_records = _source_records(source_documents)
    readme = f"""# China and Hong Kong official physical-build gap assessment

This immutable artifact assesses eleven project identities absent from open seed v73. Ten direct-source identities have dated physical-build observations and exact schema-1.1 source records. They are seed-eligible but are not integrated here. Every lifecycle row is a dated last observation; no source record asserts confirmed-current status after its observation date.

The Changle Airport Free Trade Zone AI Computing Center remains review-only. Direct hostname attempts and explicit attempts against all three observed A records timed out without publisher bytes, and the Chrome fallback yielded no loaded or savable publisher response. Transformed web text and search snippets were not used. Changle therefore has no source record, lifecycle, identity, role, type, capacity, or geometry claim in this artifact.

China Telecom's Guizhou page returned HTTP 412 and contributes no claim. The B5/B6 source record is governed solely by the direct official CSCEC contractor body. P-6 is scoped to the topped-out phase-2 power center; A5/A6 are not asserted started. The Haidong government bulletin supports four separately keyed construction-site records. Tongling is treated sensitively: only the dated external rainwater-network construction fact is extracted from the administrative safety record.

No source contains normalized capacity. Compute, rack, area, cost, investment, source-grid-load-storage wording, campus electricity, PUE, generation, load, consumption, and annual energy are not converted or reassigned. No source has coordinates or geometry. No publisher imagery, satellite imagery, aerial imagery, computer vision, or analyst geolocation contributes to identity, status, capacity, type, roles, or location.

All source and artifact bytes were completed in private staging before `{recorded_at}`. Final paths remained absent until that instant and were promoted without replacement as one rollback-protected set. The accepted v73 seed and every downstream artifact remain unchanged. Raw all-rights-reserved captures are not redistributed; the complete 39-file capture directory was moved intact to the recoverable Trash path in the rights inventory.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "source_records": source_records,
        "totals": {
            "candidate_assessments": 11,
            "source_records": 10,
            "seed_eligible_source_records": 10,
            "review_only_candidates": 1,
            "distinct_campuses": 10,
            "projects": 10,
            "entity_snapshots": 20,
            "unique_evidence_records": 11,
            "lifecycle_observations": 11,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
            "coordinates_present": 0,
            "geometry_present": 0,
        },
        "frozen_v73_non_mutation_witness": {
            "definition": {
                "path": "sources/open-seed-2026-07-21-v73.json",
                "bytes": V73_PINS[V73_DEFINITION][0],
                "sha256": V73_PINS[V73_DEFINITION][1],
            },
            "release_manifest": {
                "path": "releases/2026-07-21-open-seed-v73/manifest.json",
                "bytes": V73_PINS[V73_MANIFEST][0],
                "sha256": V73_PINS[V73_MANIFEST][1],
            },
            "release_tree_sha256": V73_TREE_SHA256,
            "v73_selected_input_count": V73_INPUT_COUNT,
            "new_source_paths_selected_by_v73": False,
            "new_stable_key_collisions": 0,
            "new_evidence_key_collisions": 0,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v73_mutated": False,
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
        "format": "datacenter-atlas-source-rights-disposition-v3",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "source_rights": (
            "Captured publisher response bodies are treated as all-rights-reserved; "
            "no redistribution license was relied on."
        ),
        "artifact_is_hash_only": True,
        "compact_factual_extractions_retained": True,
        "raw_capture_redistributed": False,
        "raw_response_bodies_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "publisher_media_retained_in_artifact": False,
        "request_credentials_supplied": False,
        "transformed_web_text_used_for_claims": False,
        "search_snippets_used_for_claims": False,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "temporary_capture_file_count": CAPTURE_FILE_COUNT,
        "temporary_capture_bytes": CAPTURE_BYTES,
        "temporary_capture_tree_sha256": CAPTURE_TREE_SHA256,
        "deletion_performed": False,
        "candidate_dispositions": {
            "seed_eligible": 10,
            "review_only_no_direct_publisher_capture": 1,
        },
        "technical_incident_groups": 2,
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
        "candidate_assessments": 11,
        "curated_source_records": 10,
        "seed_eligible_source_records": 10,
        "review_only_candidates": 1,
        "technical_incident_groups": 2,
        "successful_raw_captures": len(CAPTURE_BODIES),
        "raw_capture_redistributed": False,
        "raw_capture_directory_moved_intact_to_trash": True,
        "transformed_web_text_used_for_claims": False,
        "search_snippets_used_for_claims": False,
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
        raise ChinaGapError("source path inventory differs")
    for name in SOURCE_FILENAMES:
        source = paths[name]
        if source.is_symlink() or not source.is_file():
            raise ChinaGapError(f"curated source is absent: {source}")
        raw = source.read_bytes()
        if raw != _canonical(expected[name]):
            raise ChinaGapError(f"curated source differs: {name}")
        if stat.S_IMODE(source.stat().st_mode) != 0o644:
            raise ChinaGapError(f"curated source mode differs: {name}")
        document = json.loads(raw)
        for entity in ("campus", "project"):
            if document[entity]["coordinates"] is not None:
                raise ChinaGapError(f"source invented coordinates: {name}")
            if document[entity]["geometry"] is not None:
                raise ChinaGapError(f"source invented geometry: {name}")
        if (
            document["operating_models"]
            or document["workloads"]
            or document["capacities"]
        ):
            raise ChinaGapError(f"source exceeded zero-classification boundary: {name}")
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
    if len(stable_keys) != 20 or len(evidence_keys) != 11:
        raise ChinaGapError("planned source keys are not unique")
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
        raise ChinaGapError(f"curated source collision: {collisions!r}")


def _validate_v73_nonmutation() -> None:
    for source, pin in V73_PINS.items():
        _pin(source, pin)
    if tree_digest(V73_RELEASE) != V73_TREE_SHA256:
        raise ChinaGapError("accepted v73 release tree differs")
    definition = json.loads(V73_DEFINITION.read_text(encoding="utf-8"))
    if len(definition.get("curated_inputs", [])) != V73_INPUT_COUNT:
        raise ChinaGapError("accepted v73 input count differs")
    selected = {row["path"] for row in definition["curated_inputs"]}
    planned_paths = {f"sources/{name}" for name in SOURCE_FILENAMES}
    if selected & planned_paths:
        raise ChinaGapError("v73 unexpectedly selects a new source path")
    entities_text = V73_ENTITIES.read_text(encoding="utf-8")
    for document in expected_source_documents().values():
        for entity in ("campus", "project"):
            if document[entity]["stable_key"] in entities_text:
                raise ChinaGapError("new source stable key collides with v73")


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise ChinaGapError(f"capture directory is absent or unsafe: {directory}")
    entries = list(directory.iterdir())
    if len(entries) != CAPTURE_FILE_COUNT:
        raise ChinaGapError("capture directory file count differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise ChinaGapError("capture directory contains a non-ordinary file")
    if sum(entry.stat().st_size for entry in entries) != CAPTURE_BYTES:
        raise ChinaGapError("capture directory byte count differs")
    if tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise ChinaGapError("capture directory tree differs")
    for spec in CAPTURE_BODIES.values():
        _pin(directory / spec["filename"], (spec["bytes"], spec["sha256"]))


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
            "entities": 20,
            "entity_snapshots": 20,
            "evidence": 11,
            "lifecycle_observations": 11,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
        }
        if counts != expected:
            raise ChinaGapError(f"offline import counts differ: {counts!r}")
        statuses = [
            tuple(row)
            for row in connection.execute(
                "SELECT status, as_of_date, method FROM lifecycle_observations "
                "ORDER BY as_of_date, status, method"
            )
        ]
        if len(statuses) != 11:
            raise ChinaGapError("offline lifecycle count differs")
        if any(status[0] not in {"shell", "under_construction"} for status in statuses):
            raise ChinaGapError(f"offline lifecycle boundary differs: {statuses!r}")
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
        raise ChinaGapError("artifact must be an ordinary directory")
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise ChinaGapError("artifact closed file set differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries.values()):
        raise ChinaGapError("artifact contains a non-ordinary file")
    if stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise ChinaGapError("artifact directory mode differs")
    if any(stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries.values()):
        raise ChinaGapError("artifact file mode differs")
    for name in CONTENT_FILES[1:]:
        raw = entries[name].read_bytes()
        if raw != _canonical(json.loads(raw)):
            raise ChinaGapError(f"artifact JSON is not canonical: {name}")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest):
        raise ChinaGapError("manifest JSON is not canonical")
    if (
        manifest.get("artifact_id") != ARTIFACT_ID
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or manifest.get("candidate_assessments") != 11
        or manifest.get("curated_source_records") != 10
        or manifest.get("seed_eligible_source_records") != 10
        or manifest.get("review_only_candidates") != 1
        or manifest.get("technical_incident_groups") != 2
        or manifest.get("successful_raw_captures") != 8
        or manifest.get("transformed_web_text_used_for_claims") is not False
        or manifest.get("search_snippets_used_for_claims") is not False
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or manifest.get("downstream_product_integration") != "none"
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise ChinaGapError("manifest contract differs")
    if [row["path"] for row in manifest["files"]] != list(CONTENT_FILES):
        raise ChinaGapError("manifest file order differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (row["bytes"], row["sha256"]):
            raise ChinaGapError(f"manifest file pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise ChinaGapError("manifest checksum differs")
    expected = _artifact_documents(manifest["recorded_at"], expected_source_documents())
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected[name]:
            raise ChinaGapError(f"artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records:
        raise ChinaGapError("artifact source pins differ")
    assessment = json.loads(
        entries["candidate-assessment.json"].read_text(encoding="utf-8")
    )
    rows = {row["candidate_id"]: row for row in assessment["candidates"]}
    if len(rows) != 11:
        raise ChinaGapError("candidate identity count differs")
    changle = rows["changle-airport-free-trade-zone-ai-computing-center"]
    if (
        changle["decision"] != "review_only_no_direct_publisher_capture"
        or changle["source_record_created"]
        or changle["seed_eligible"]
        or changle["last_observed_physical_date"] is not None
        or changle["browser_context_not_evidence"]["used_for_normalized_claims"]
    ):
        raise ChinaGapError("Changle no-capture boundary differs")
    if sum(row["source_record_created"] for row in rows.values()) != 10:
        raise ChinaGapError("source candidate count differs")
    if sum(row["seed_eligible"] for row in rows.values()) != 10:
        raise ChinaGapError("seed-eligible candidate count differs")
    guizhou = expected_source_documents()[SOURCE_FILENAMES[1]]
    if (
        len(guizhou["evidence"]) != 1
        or guizhou["evidence"][0]["source_url"] != CAPTURE_BODIES["guizhou_cscec"]["url"]
        or "chinatelecom.com.cn" in json.dumps(guizhou, ensure_ascii=False)
    ):
        raise ChinaGapError("Guizhou CSCEC-only evidence boundary differs")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ChinaGapError("validation wall clock lacks timezone")
    if require_live:
        if now.astimezone(UTC) < target:
            raise ChinaGapError("artifact recorded_at is not live")
        _assert_final_ctimes((*paths.values(), path), target)
    for document in expected_source_documents().values():
        for evidence in document["evidence"]:
            if _instant(evidence["retrieved_at"]) > target:
                raise ChinaGapError("evidence retrieval post-dates recorded_at")
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
        raise ChinaGapError(
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
        raise ChinaGapError("recorded_at must be future before staging")
    source_stage = Path(
        tempfile.mkdtemp(prefix=".official-builds-china-gap.", dir=SOURCES_ROOT)
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
            _all_stage_paths(source_stage, artifact_stage),
            target,
        )
        if datetime.now(UTC) >= target:
            raise ChinaGapError("private staging did not finish before recorded_at")
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
                raise ChinaGapError(f"source identity changed on promotion: {name}")
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
            raise ChinaGapError("artifact identity changed on promotion")
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
        raise ChinaGapError("both capture origin and Trash destination exist")
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH))


def _default_recorded_at() -> str:
    target = math.ceil(time.time() + 25.0)
    return datetime.fromtimestamp(target, UTC).isoformat().replace("+00:00", "Z")


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    """Publish ten source records and the eleven-candidate assessment."""

    target_text = recorded_at or _default_recorded_at()
    finals = tuple(SOURCES_ROOT / name for name in SOURCE_FILENAMES) + (ARTIFACT,)
    _require_finals_absent(finals, "initial")
    _validate_source_collisions()
    _validate_v73_nonmutation()
    _validate_capture_directory(_capture_directory())
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
    _validate_capture_directory(resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH))
    _validate_v73_nonmutation()
    manifest = validate_artifact(ARTIFACT)
    source_records = _validate_sources(_source_paths(SOURCES_ROOT))
    return {
        "artifact_id": ARTIFACT_ID,
        "recorded_at": manifest["recorded_at"],
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "source_records": source_records,
        "counts": {
            "candidates": 11,
            "source_records": 10,
            "seed_eligible": 10,
            "review_only": 1,
            "technical_incident_groups": 2,
            "successful_direct_bodies": 8,
            "evidence": 11,
            "entities": 20,
            "lifecycle": 11,
            "operating_models": 0,
            "workloads": 0,
            "capacities": 0,
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
