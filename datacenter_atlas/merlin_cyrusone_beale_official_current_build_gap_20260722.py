"""Publish a hash-bound MERLIN, CyrusOne, and Beale official-source tranche.

Six schema-1.1 source records cover five campus candidates and six projects.
Raw all-rights-reserved captures are represented only by exact pins, retrieval
facts, and compact factual extracts.
"""

from __future__ import annotations

from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence

from .external_captures import resolve_external_capture
from . import global_official_current_build_gap_20260721 as prior
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "merlin-cyrusone-beale-official-current-build-gap-2026-07-22-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".merlin-cyrusone-beale-current-build-gap.lock"

CAPTURE_ORIGIN = Path("/private/tmp/dc-official-current-gap-20260722.jce4gD")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-official-current-gap-20260722.jce4gD")
CAPTURE_FILE_COUNT = 30
CAPTURE_TOTAL_BYTES = 13_100_740
CAPTURE_TREE_SHA256 = (
    "bcde54589be1934223b1b30e69f9e8c3c1b306275c19df897ab5dd146f57f3aa"
)

V92_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v92.json"
V92_RELEASE = ROOT / "releases/2026-07-21-open-seed-v92"
V92_MANIFEST = V92_RELEASE / "manifest.json"
V92_ENTITIES = V92_RELEASE / "entities.csv"
V92_SOURCE_INPUTS = V92_RELEASE / "source_inputs.json"
V92_PINS = {
    V92_DEFINITION: (
        109_851,
        "2dab6d4a4bdac34f248268f9f2973ccac88b7fe25deb78b10cf5e44c11990516",
    ),
    V92_MANIFEST: (
        16_558,
        "3ac9a48eeb121e6ac8a462fb2d99de1a7f2267c6cf9f6b7bd4b74d2b74a25fd7",
    ),
    V92_ENTITIES: (
        1_025_359,
        "3e1bf82358ee1e037a7e8ce1a175eee3958dfb4f4d3f5dc6fbd7b92704fd7290",
    ),
    V92_SOURCE_INPUTS: (
        410_016,
        "f46dcc40074e9daef10c7ce59fa37b2be8ca9c081fe5d067645332b1e4d514e9",
    ),
}
V92_TREE_SHA256 = "52bdbd5ea299dbd845adfe8e05f739894bff914107ae8fec341551bdb800034b"
V92_INPUT_COUNT = 485
V92_ENTITY_COUNT = 988

_canonical = prior._canonical
_sha256 = prior._sha256
_sha256_bytes = prior._sha256_bytes
_instant = prior._instant
_pin = prior._pin
_fsync_regular = prior._fsync_regular
_fsync_directory = prior._fsync_directory
_promote_noreplace = prior._promote_noreplace


CAPTURE_FILE_PINS: dict[str, tuple[int, str]] = {
    "beale_leadership_pdf.body": (
        61_505,
        "8c9ac293f959dc619b8be445491ce9d533985bc870509f3bd5d9530270ca57ce",
    ),
    "beale_leadership_pdf.headers": (
        1_721,
        "e7a286815fbc4242084b122d6d02eec150c751ebf57a245b3f54be06d49f9845",
    ),
    "beale_locations.body": (
        73_891,
        "cc9e696243d7d70d332609892c7f10d7a7214958a16ff55e76ba58b66281e6fa",
    ),
    "beale_locations.headers": (
        1_004,
        "0785eff7ff1b715be4c4ae0112bbab297594b29294fb6ab238520f45ca140ee1",
    ),
    "beale_pima_location.body": (
        87_354,
        "ecf0db7eec3e14d42ac1c47454b0efb93999981a3bd5cfad0a76f29300ea53ef",
    ),
    "beale_pima_location.headers": (
        1_014,
        "bbc7a3429e902b2104ac61a589b28ca23989199ff82590a02579b4c6b65c9894",
    ),
    "beale_tulsa_announcement.body": (
        60_662,
        "ad0ea00dbe3defbc80051126eced9000265306a5f8cf1c7fce9fc8deff232e55",
    ),
    "beale_tulsa_announcement.headers": (
        1_006,
        "c3353ca397871a96ea3bceae117a659edcee65f6966af15f33d1eab023431268",
    ),
    "beale_tulsa_location.body": (
        93_952,
        "30cee538f69beb8b610fe494d94ea291f7c59b712479b1ae04e29e076055a256",
    ),
    "beale_tulsa_location.headers": (
        1_009,
        "1d862f68970e7380e85dc838c8f9afdfe6768d11232375d79d879a691396ee05",
    ),
    "cyrus_fra5_social.body": (
        35_572,
        "a83f18ec293de19bbbc8df9a41ef3dc2b3cc6178fe9be7402355825ef64b748f",
    ),
    "cyrus_fra5_social.headers": (
        3_870,
        "8dd7e2b1b9dfaea07fdf707d2a2362990bdbf59bbee5025ec4067361e49196b8",
    ),
    "cyrus_wooddale_press.body": (
        87_984,
        "d7e9bcf0d1e6ff2a06869bb4daafdd2d2a184111b1e70f38617d9da251cb91c8",
    ),
    "cyrus_wooddale_press.headers": (
        2_971,
        "31edc5edc34916d1da6008652ba37d745376ca488926d944d7e4e8a733ffbd86",
    ),
    "cyrus_wooddale_social.body": (
        25_351,
        "8e278948ba2841ccafb3129d100875a1d2422ab10fd3b717fdd5ddeea6156198",
    ),
    "cyrus_wooddale_social.headers": (
        3_870,
        "532020656f925623dabbc456d8ca5adb4cbfcb6281ba4d041f289812b483a930",
    ),
    "merlin_asset.body": (
        104_317,
        "e63d0ac075448c4284076d67ada3e287f51d47cb7d8a66c95316d3e3b76691e8",
    ),
    "merlin_asset.headers": (
        559,
        "466c1cfd294a7c7c4cf0142dc81b0101d09e7200dd552a3dda7051009c1bbf2d",
    ),
    "merlin_progress.body": (
        99_729,
        "356a5c57e9404421d11720abb10913b6d3fd960032db08e34f1fadc1e7294d6e",
    ),
    "merlin_progress.headers": (
        617,
        "a7eae0e4af5f2940cfccad2e7d88239075053e956d44f71e607fa1073c90a2d8",
    ),
    "pima_project_blue_faq.body": (
        1_133_012,
        "0b9e63794c6b3ba52ff4874ab76a06d2cb409476a384a1e7d12eea8e7f2ec163",
    ),
    "pima_project_blue_faq.headers": (
        2_469,
        "735086af8ab046b45234c4e8c0b4936a6aa421010803bb2b356ab3414c402f84",
    ),
    "pima_project_blue_news.body": (
        1_156_738,
        "f08ee195d5dcb2fbc21e52ab9a0ff6d11b1266d4e3a6a8783103596a169cfd9b",
    ),
    "pima_project_blue_news.headers": (
        2_469,
        "b78136bca3217549551c92f6432203d533d4b1629698be640cf3703781a26d83",
    ),
    "pima_project_blue_nov.body": (
        4_331_983,
        "7d9bde798539f5a325793a98d673fb75afb57c917a705aa90a60ab6770aa78d3",
    ),
    "pima_project_blue_nov.headers": (
        552,
        "392019632142857f395078b90d985c99efd2c017e12e249addd72cdc2b885d8f",
    ),
    "pima_project_blue_progress_pdf.body": (
        380_704,
        "b4d73dbddc831d71f026543daac692e4605743ee1efcafd8c99f6a59bad0782d",
    ),
    "pima_project_blue_progress_pdf.headers": (
        548,
        "25e3d0f5228dc8a2800d96471549f95d24e4a4bd8c145b2220083c551cfc3dde",
    ),
    "pima_project_blue_response.body": (
        5_343_631,
        "abdb311c26cf507cfa564072c55f37608a3cb4dff905abb2f39fc407a5fbb90a",
    ),
    "pima_project_blue_response.headers": (
        676,
        "7914c0518bed290def85e649be5b181e436576c4ff1c1f3674e15378b3068eb8",
    ),
}


@dataclass(frozen=True)
class Capture:
    capture_id: str
    stem: str
    url: str
    retrieved_at: str
    published_at: str | None
    content_type: str
    claim_use: str


CAPTURES = (
    Capture(
        "merlin_asset",
        "merlin_asset",
        "https://www.merlinproperties.com/en/assets/data-center-bilbao-arasur/",
        "2026-07-22T02:17:58Z",
        None,
        "text/html; charset=UTF-8",
        "identity_and_marketing_context",
    ),
    Capture(
        "merlin_progress",
        "merlin_progress",
        "https://www.merlinproperties.com/en/dia-a-dia/we-keep-moving-forward-at-our-merlin-edged-bilbao-arasur-campus-in-spain/",
        "2026-07-22T02:17:57Z",
        "2026-04-10",
        "text/html; charset=UTF-8",
        "normalized_physical_status",
    ),
    Capture(
        "cyrus_fra5_social",
        "cyrus_fra5_social",
        "https://www.linkedin.com/feed/update/urn:li:activity:7366165991585665024",
        "2026-07-22T02:17:56Z",
        "2025-08-26",
        "text/html; charset=utf-8",
        "normalized_physical_status_and_typed_capacity",
    ),
    Capture(
        "cyrus_wooddale_press",
        "cyrus_wooddale_press",
        "https://www.cyrusone.com/resources/press-releases/cyrusone-celebrates-wood-dale-topping-out-ceremony",
        "2026-07-22T02:17:57Z",
        "2025-05-13",
        "text/html; charset=UTF-8",
        "normalized_shell_status_and_typed_capacity",
    ),
    Capture(
        "cyrus_wooddale_social",
        "cyrus_wooddale_social",
        "https://www.linkedin.com/feed/update/urn:li:activity:7361067298977165313",
        "2026-07-22T02:17:56Z",
        "2025-08-12",
        "text/html; charset=utf-8",
        "normalized_physical_status",
    ),
    Capture(
        "beale_tulsa_announcement",
        "beale_tulsa_announcement",
        "https://bealeinfra.com/beale-infrastructure-announces-new-data-center-campus-in-tulsa-county/",
        "2026-07-22T02:17:56Z",
        "2025-10-31",
        "text/html; charset=UTF-8",
        "normalized_construction_start",
    ),
    Capture(
        "beale_leadership_pdf",
        "beale_leadership_pdf",
        "https://bealeinfra.com/beale-infrastructure-expands-leadership-team-and-accelerates-buildout-of-north-american-digital-infrastructure-platform/",
        "2026-07-22T02:17:57Z",
        "2025-11-24",
        "text/html; charset=UTF-8",
        "normalized_physical_status",
    ),
    Capture(
        "beale_locations",
        "beale_locations",
        "https://bealeinfra.com/locations/",
        "2026-07-22T02:18:36Z",
        None,
        "text/html; charset=UTF-8",
        "retrieval_only",
    ),
    Capture(
        "beale_tulsa_location",
        "beale_tulsa_location",
        "https://bealeinfra.com/location/tulsa-county/",
        "2026-07-22T02:17:57Z",
        None,
        "text/html; charset=UTF-8",
        "retrieval_only",
    ),
    Capture(
        "beale_pima_location",
        "beale_pima_location",
        "https://bealeinfra.com/location/pima-county/",
        "2026-07-22T02:21:00Z",
        None,
        "text/html; charset=UTF-8",
        "identity_context",
    ),
    Capture(
        "pima_project_blue_faq",
        "pima_project_blue_faq",
        "https://www.pima.gov/3552/Project-Blue-FAQ",
        "2026-07-22T02:21:00Z",
        None,
        "text/html; charset=utf-8",
        "retrieval_only",
    ),
    Capture(
        "pima_project_blue_news",
        "pima_project_blue_news",
        "https://www.pima.gov/2720/Newsroom",
        "2026-07-22T02:20:59Z",
        None,
        "text/html; charset=utf-8",
        "excluded_civicplus_shell_non_evidence",
    ),
    Capture(
        "pima_project_blue_progress_pdf",
        "pima_project_blue_progress_pdf",
        "https://content.civicplus.com/api/assets/32428b1b-4a81-444a-92a4-72b1fa039655",
        "2026-07-22T02:21:00Z",
        "2026-04-23",
        "application/pdf",
        "identity_and_permit_context_only",
    ),
    Capture(
        "pima_project_blue_nov",
        "pima_project_blue_nov",
        "https://content.civicplus.com/api/assets/640632e2-0b76-4257-bb62-8b751f22aa64",
        "2026-07-22T02:21:28Z",
        "2026-05-12",
        "application/pdf",
        "normalized_physical_site_preparation",
    ),
    Capture(
        "pima_project_blue_response",
        "pima_project_blue_response",
        "https://content.civicplus.com/api/assets/6063ed1f-cc11-4876-bbc8-d64025507660",
        "2026-07-22T02:21:28Z",
        "2026-05-22",
        "application/pdf",
        "pause_context_without_status_override",
    ),
)
CAPTURE_BY_ID = {capture.capture_id: capture for capture in CAPTURES}


@dataclass(frozen=True)
class EvidenceSpec:
    key: str
    capture_id: str
    title: str
    publisher: str
    source_family: str
    kind: str
    excerpt: str
    facts: Mapping[str, Any]


EVIDENCE = (
    EvidenceSpec(
        "merlin-bilbao-arasur-campus-page-captured-2026-07-22",
        "merlin_asset",
        "Bilbao Arasur Data Center Campus",
        "MERLIN Properties",
        "merlin_properties_official_site",
        "company_disclosure",
        "MERLIN identifies its Bilbao-Arasur data-center campus in Spain.",
        {
            "identity_scope": "Campus identity and broad locality only.",
            "marketing_context_not_normalized": (
                "Hyperscale, colocation, sustainability, cooling, connectivity, "
                "PUE, WUE, and power figures are marketing or design context only."
            ),
        },
    ),
    EvidenceSpec(
        "merlin-bilbao-arasur-b2-b3-progress-2026-04-10",
        "merlin_progress",
        "MERLIN Edged Bilbao-Arasur campus progress",
        "MERLIN Properties",
        "merlin_properties_official_news",
        "company_disclosure",
        (
            "MERLIN reports Building 2 construction well under way and Building 3 "
            "construction begun in early 2026."
        ),
        {
            "physical_status_as_reported": (
                "Building 2 construction well under way; Building 3 began "
                "construction in early 2026."
            ),
            "marketing_context_not_normalized": (
                "+162 MW planned capacity, PUE 1.15, and WUE 0 are untyped, "
                "campus-level, forecast, or design marketing metadata only."
            ),
            "current_status_scope": (
                "Two dated last-observed construction facts; no present-day status "
                "is inferred after 2026-04-10."
            ),
        },
    ),
    EvidenceSpec(
        "cyrusone-fra5-hanau-progress-2025-08-26",
        "cyrus_fra5_social",
        "CyrusOne FRA5 construction update",
        "CyrusOne",
        "cyrusone_official_linkedin",
        "company_disclosure",
        (
            "CyrusOne reports that FRA5 in Hanau comprises two buildings, is "
            "progressing toward completion, and will deliver 54 MW of IT capacity."
        ),
        {
            "physical_status_as_reported": "FRA5 construction powers ahead.",
            "critical_it_as_reported": "54 MW of IT capacity across FRA5.",
            "scope": (
                "The normalized project aggregates the two current halls/buildings; "
                "54 MW is normalized once on the campus as planned critical IT."
            ),
        },
    ),
    EvidenceSpec(
        "cyrusone-wood-dale-phase-1-topping-out-2025-05-13",
        "cyrus_wooddale_press",
        "CyrusOne celebrates Wood Dale topping out ceremony",
        "CyrusOne",
        "cyrusone_official_press_release",
        "company_disclosure",
        (
            "CyrusOne reports the final structural beam placed at Wood Dale and an "
            "initial IT capacity of 18 MW."
        ),
        {
            "physical_status_as_reported": (
                "Final steel beam raised; structural framework complete."
            ),
            "critical_it_as_reported": "Initial IT capacity of 18 MW.",
            "capacity_scope": (
                "18 MW is normalized once on Phase 1 as planned critical IT, not "
                "current load, gross facility demand, or grid draw."
            ),
        },
    ),
    EvidenceSpec(
        "cyrusone-wood-dale-phase-1-progress-2025-08-12",
        "cyrus_wooddale_social",
        "CyrusOne Wood Dale first-phase update",
        "CyrusOne",
        "cyrusone_official_linkedin",
        "company_disclosure",
        "CyrusOne provides a construction-progress update for Wood Dale Phase 1.",
        {
            "physical_status_as_reported": "Wood Dale first phase taking shape.",
            "forecast_not_normalized": (
                "Phase 2 mid-2027 timing is forecast context only and creates no "
                "entity, status, or capacity record."
            ),
        },
    ),
    EvidenceSpec(
        "beale-tulsa-clydesdale-groundbreaking-2025-10-31",
        "beale_tulsa_announcement",
        "Beale announces Tulsa County data-center campus",
        "Beale Infrastructure",
        "beale_infrastructure_official_news",
        "company_disclosure",
        (
            "Beale announces the groundbreaking of Project Clydesdale, a new "
            "data-center campus in Tulsa County."
        ),
        {
            "physical_status_as_reported": "Groundbreaking held.",
            "investment_context_not_normalized": (
                "The planned $1 billion initial investment is financial context."
            ),
        },
    ),
    EvidenceSpec(
        "beale-tulsa-clydesdale-progress-2025-11-24",
        "beale_leadership_pdf",
        "Beale leadership and North American platform update",
        "Beale Infrastructure",
        "beale_infrastructure_official_news",
        "company_disclosure",
        (
            "Beale says its initial Tulsa County investment phase is under way "
            "following the company's first groundbreaking."
        ),
        {
            "physical_status_as_reported": "Initial Tulsa phase under way.",
            "forecast_not_normalized": (
                "Expected completion in early 2027 is forecast context only."
            ),
            "capacity_guardrail": (
                "No normalized capacity, energy, PUE, WUE, or generation claim."
            ),
        },
    ),
    EvidenceSpec(
        "beale-pima-project-bobcat-location-captured-2026-07-22",
        "beale_pima_location",
        "Beale Pima County location",
        "Beale Infrastructure",
        "beale_infrastructure_official_location",
        "company_disclosure",
        (
            "Beale identifies its planned multi-building Pima County campus and "
            "uses the Project Bobcat name."
        ),
        {
            "identity_scope": (
                "Project Bobcat is retained as Beale's name for the Pima County "
                "campus; Pima County records use Project Blue."
            ),
            "power_context_not_normalized": (
                "Any 500 MW or other power figure is untyped context only."
            ),
            "design_context_not_normalized": (
                "Air cooling, water, phased campus design, and economic-benefit "
                "language create no normalized type, workload, PUE, WUE, or role."
            ),
        },
    ),
    EvidenceSpec(
        "pima-project-blue-progress-memo-2026-04-23",
        "pima_project_blue_progress_pdf",
        "Progress update on Project Blue development",
        "Pima County",
        "pima_county_official_memorandum",
        "government_record",
        (
            "Pima County identifies Project Blue as a data-center campus and reports "
            "land and permitting context."
        ),
        {
            "identity_scope": (
                "Identity, broad locality, land-transfer, and permit context only."
            ),
            "status_guardrail": (
                "Permitting progress alone is not normalized as physical status."
            ),
        },
    ),
    EvidenceSpec(
        "pima-project-blue-site-work-inspection-2026-05-11",
        "pima_project_blue_nov",
        "Pima County notice of violation PC2605-064",
        "Pima County Department of Environmental Quality",
        "pima_county_official_environmental_record",
        "government_record",
        (
            "Pima County records ongoing work at the Project Blue site during "
            "May 8 and May 11 inspections."
        ),
        {
            "physical_status_as_reported": (
                "Ongoing dust-generating site work observed on May 8 and May 11."
            ),
            "address_as_reported": (
                "11295 S Harrison Road, Tucson, Arizona 85747."
            ),
            "status_scope": (
                "Latest inspection date, 2026-05-11, supports site preparation; "
                "no building construction or current status is inferred."
            ),
        },
    ),
    EvidenceSpec(
        "pima-project-blue-pause-response-2026-05-22",
        "pima_project_blue_response",
        "Response regarding Project Blue fugitive-dust notice",
        "Pima County",
        "pima_county_official_memorandum",
        "government_record",
        (
            "Pima County reports that loss of a water source halted major earthwork "
            "while native-plant harvesting continued."
        ),
        {
            "pause_context": (
                "Major earthwork halted after loss of the water source; native-plant "
                "harvesting continued, followed by temporary activity controls."
            ),
            "normalization_decision": (
                "This mixed pause-and-continuing-work report does not override the "
                "2026-05-11 site-preparation observation. Current status is unknown."
            ),
        },
    ),
)
EVIDENCE_BY_KEY = {evidence.key: evidence for evidence in EVIDENCE}


@dataclass(frozen=True)
class Site:
    candidate: str
    filename: str
    country: str
    address: str
    campus_key: str
    project_key: str
    campus_name: str
    project_name: str
    evidence_keys: tuple[str, ...]
    campus_evidence: str
    project_evidence: str
    campus_as_of: str
    project_as_of: str
    lifecycle: tuple[tuple[str, str, str, str], ...]
    capacity: tuple[str, float, str, str] | None = None


MERLIN_CAMPUS = "curated:merlin-edged-bilbao-arasur-campus"
SITES = (
    Site(
        "merlin-bilbao-arasur",
        "curated-official-2026-07-22-merlin-bilbao-arasur-building-2-current-build.json",
        "Spain",
        "Arasur Industrial and Logistics Park, Alava, Spain",
        MERLIN_CAMPUS,
        f"{MERLIN_CAMPUS}:building-2-current-build",
        "MERLIN Edged Bilbao-Arasur Campus",
        "MERLIN Edged Bilbao-Arasur Building 2 Current Build",
        (
            "merlin-bilbao-arasur-campus-page-captured-2026-07-22",
            "merlin-bilbao-arasur-b2-b3-progress-2026-04-10",
        ),
        "merlin-bilbao-arasur-b2-b3-progress-2026-04-10",
        "merlin-bilbao-arasur-b2-b3-progress-2026-04-10",
        "2026-04-10",
        "2026-04-10",
        (
            (
                "under_construction",
                "2026-04-10",
                "authoritative_physical_status_update",
                "merlin-bilbao-arasur-b2-b3-progress-2026-04-10",
            ),
        ),
    ),
    Site(
        "merlin-bilbao-arasur",
        "curated-official-2026-07-22-merlin-bilbao-arasur-building-3-current-build.json",
        "Spain",
        "Arasur Industrial and Logistics Park, Alava, Spain",
        MERLIN_CAMPUS,
        f"{MERLIN_CAMPUS}:building-3-current-build",
        "MERLIN Edged Bilbao-Arasur Campus",
        "MERLIN Edged Bilbao-Arasur Building 3 Current Build",
        (
            "merlin-bilbao-arasur-campus-page-captured-2026-07-22",
            "merlin-bilbao-arasur-b2-b3-progress-2026-04-10",
        ),
        "merlin-bilbao-arasur-b2-b3-progress-2026-04-10",
        "merlin-bilbao-arasur-b2-b3-progress-2026-04-10",
        "2026-04-10",
        "2026-04-10",
        (
            (
                "under_construction",
                "2026-04-10",
                "authoritative_physical_status_update",
                "merlin-bilbao-arasur-b2-b3-progress-2026-04-10",
            ),
        ),
    ),
    Site(
        "cyrusone-fra5-hanau",
        "curated-official-2026-07-22-cyrusone-fra5-hanau-halls-2-3-current-build.json",
        "Germany",
        "Hanau, Hesse, Germany",
        "curated:cyrusone-fra5-hanau-campus",
        "curated:cyrusone-fra5-hanau-campus:halls-2-3-current-build",
        "CyrusOne FRA5 Hanau Campus",
        "CyrusOne FRA5 Halls 2 and 3 Current Build",
        ("cyrusone-fra5-hanau-progress-2025-08-26",),
        "cyrusone-fra5-hanau-progress-2025-08-26",
        "cyrusone-fra5-hanau-progress-2025-08-26",
        "2025-08-26",
        "2025-08-26",
        (
            (
                "under_construction",
                "2025-08-26",
                "authoritative_physical_status_update",
                "cyrusone-fra5-hanau-progress-2025-08-26",
            ),
        ),
        ("campus", 54.0, "2025-08-26", "cyrusone-fra5-hanau-progress-2025-08-26"),
    ),
    Site(
        "cyrusone-wood-dale",
        "curated-official-2026-07-22-cyrusone-wood-dale-phase-1-current-build.json",
        "United States",
        "Wood Dale, Illinois, United States",
        "curated:cyrusone-wood-dale-campus",
        "curated:cyrusone-wood-dale-campus:phase-1-current-build",
        "CyrusOne Wood Dale Campus",
        "CyrusOne Wood Dale Phase 1 Current Build",
        (
            "cyrusone-wood-dale-phase-1-topping-out-2025-05-13",
            "cyrusone-wood-dale-phase-1-progress-2025-08-12",
        ),
        "cyrusone-wood-dale-phase-1-topping-out-2025-05-13",
        "cyrusone-wood-dale-phase-1-progress-2025-08-12",
        "2025-05-13",
        "2025-08-12",
        (
            (
                "shell",
                "2025-05-13",
                "authoritative_physical_status_update",
                "cyrusone-wood-dale-phase-1-topping-out-2025-05-13",
            ),
            (
                "under_construction",
                "2025-08-12",
                "authoritative_physical_status_update",
                "cyrusone-wood-dale-phase-1-progress-2025-08-12",
            ),
        ),
        (
            "project",
            18.0,
            "2025-05-13",
            "cyrusone-wood-dale-phase-1-topping-out-2025-05-13",
        ),
    ),
    Site(
        "beale-tulsa-clydesdale",
        "curated-official-2026-07-22-beale-tulsa-project-clydesdale-initial-phase-current-build.json",
        "United States",
        "Tulsa County, Oklahoma, United States",
        "curated:beale-tulsa-county-project-clydesdale-campus",
        "curated:beale-tulsa-county-project-clydesdale-campus:initial-phase-current-build",
        "Beale Tulsa County Project Clydesdale Campus",
        "Beale Tulsa Project Clydesdale Initial Phase Current Build",
        (
            "beale-tulsa-clydesdale-groundbreaking-2025-10-31",
            "beale-tulsa-clydesdale-progress-2025-11-24",
        ),
        "beale-tulsa-clydesdale-groundbreaking-2025-10-31",
        "beale-tulsa-clydesdale-progress-2025-11-24",
        "2025-10-31",
        "2025-11-24",
        (
            (
                "under_construction",
                "2025-10-31",
                "authoritative_construction_start",
                "beale-tulsa-clydesdale-groundbreaking-2025-10-31",
            ),
            (
                "under_construction",
                "2025-11-24",
                "authoritative_physical_status_update",
                "beale-tulsa-clydesdale-progress-2025-11-24",
            ),
        ),
    ),
    Site(
        "beale-pima-project-blue-bobcat",
        "curated-official-2026-07-22-beale-pima-project-blue-bobcat-site-preparation.json",
        "United States",
        "11295 S Harrison Road, Tucson, Arizona 85747, United States",
        "curated:beale-pima-county-project-blue-bobcat-campus",
        "curated:beale-pima-county-project-blue-bobcat-campus:current-site-preparation",
        "Beale Pima County Project Blue (Project Bobcat) Campus",
        "Beale Pima Project Blue (Project Bobcat) Current Site Preparation",
        (
            "beale-pima-project-bobcat-location-captured-2026-07-22",
            "pima-project-blue-progress-memo-2026-04-23",
            "pima-project-blue-site-work-inspection-2026-05-11",
            "pima-project-blue-pause-response-2026-05-22",
        ),
        "beale-pima-project-bobcat-location-captured-2026-07-22",
        "pima-project-blue-site-work-inspection-2026-05-11",
        "2026-07-22",
        "2026-05-11",
        (
            (
                "site_preparation",
                "2026-05-11",
                "authoritative_physical_status_update",
                "pima-project-blue-site-work-inspection-2026-05-11",
            ),
        ),
    ),
)
SOURCE_FILENAMES = tuple(site.filename for site in SITES)
SITE_BY_FILENAME = {site.filename: site for site in SITES}
CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))


def _evidence(spec: EvidenceSpec) -> dict[str, Any]:
    capture = CAPTURE_BY_ID[spec.capture_id]
    body_name = f"{capture.stem}.body"
    header_name = f"{capture.stem}.headers"
    body_size, body_sha = CAPTURE_FILE_PINS[body_name]
    header_size, header_sha = CAPTURE_FILE_PINS[header_name]
    return {
        "key": spec.key,
        "kind": spec.kind,
        "title": spec.title,
        "source_url": capture.url,
        "publisher": spec.publisher,
        "source_family": spec.source_family,
        "published_at": capture.published_at,
        "retrieved_at": capture.retrieved_at,
        "license": "all-rights-reserved",
        "attribution": spec.publisher,
        "excerpt": spec.excerpt,
        "content_hash": body_sha,
        "metadata": {
            "capture_artifact_id": ARTIFACT_ID,
            "capture_request_id": capture.capture_id,
            "capture_method": "credential_free_curl_location_compressed",
            "requested_url": capture.url,
            "effective_url": capture.url,
            "request_credentials_supplied": False,
            "http_status": 200,
            "content_type": capture.content_type,
            "content_hash_scope": (
                f"SHA-256 of the exact {body_size}-byte content-decoded public "
                "response body"
            ),
            "content_hash_verification": "fetched_bytes_sha256",
            "capture_headers_scope": (
                f"SHA-256 of the exact {header_size}-byte raw HTTP response-header capture"
            ),
            "capture_headers_sha256": header_sha,
            "status_semantics": "dated_last_observed_current_status_unknown",
            "rights_scope": (
                "Compact factual extraction from all-rights-reserved official bytes; "
                "raw bodies, headers, telemetry, and publisher media are not redistributed."
            ),
            "normalization_guardrail": (
                "No energy, PUE, WUE, facility type, operating model, workload, "
                "standardized role, coordinate, geometry, satellite, aerial, map-click, "
                "or computer-vision claim is normalized."
            ),
            **spec.facts,
        },
    }


def _entity(site: Site, *, project: bool) -> dict[str, Any]:
    return {
        "stable_key": site.project_key if project else site.campus_key,
        "name": site.project_name if project else site.campus_name,
        "country": site.country,
        "address": site.address,
        "roles": {},
        "coordinates": None,
        "geometry": None,
        "evidence_key": site.project_evidence if project else site.campus_evidence,
        "as_of_date": site.project_as_of if project else site.campus_as_of,
        "method": "authoritative_locality",
        "confidence": 0.99,
    }


def _source(site: Site) -> dict[str, Any]:
    capacities: list[dict[str, Any]] = []
    if site.capacity:
        entity, value, as_of_date, evidence_key = site.capacity
        capacities.append(
            {
                "entity": entity,
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
                "notes": (
                    "Publisher-typed planned IT capacity at the exact entity scope; "
                    "not current load, gross facility demand, grid draw, generation, "
                    "annual energy, or measured consumption."
                ),
            }
        )
    return {
        "schema_version": "1.1",
        "evidence": [_evidence(EVIDENCE_BY_KEY[key]) for key in site.evidence_keys],
        "campus": _entity(site, project=False),
        "project": _entity(site, project=True),
        "lifecycle": [
            {
                "entity": "project",
                "value": value,
                "evidence_key": evidence_key,
                "as_of_date": as_of_date,
                "method": method,
                "confidence": 0.99,
            }
            for value, as_of_date, method, evidence_key in site.lifecycle
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": capacities,
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    return {site.filename: _source(site) for site in SITES}


def _source_records(
    documents: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
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
                "candidate_id": SITE_BY_FILENAME[name].candidate,
                "country": document["campus"]["country"],
                "campus_stable_key": document["campus"]["stable_key"],
                "project_stable_key": document["project"]["stable_key"],
                "evidence_records": len(document["evidence"]),
                "lifecycle_observations": len(document["lifecycle"]),
                "capacity_estimates": len(document["capacities"]),
                "operating_model_observations": 0,
                "workload_observations": 0,
                "coordinates_present": 0,
                "geometry_present": 0,
                "disposition": "seed_eligible_direct_authoritative_physical_update",
                "seed_eligible": True,
                "seeded": False,
            }
        )
    return records


def _planned_keys(
    documents: Mapping[str, Mapping[str, Any]],
) -> tuple[set[str], set[str]]:
    stable = {
        document[entity]["stable_key"]
        for document in documents.values()
        for entity in ("campus", "project")
    }
    evidence = {
        row["key"]
        for document in documents.values()
        for row in document["evidence"]
    }
    return stable, evidence


def _collision_witness(
    documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    for path, pin in V92_PINS.items():
        _pin(path, pin)
    if tree_digest(V92_RELEASE) != V92_TREE_SHA256:
        raise RuntimeError("v92 release tree differs")
    definition = json.loads(V92_DEFINITION.read_text(encoding="utf-8"))
    selected = definition.get("curated_inputs")
    if not isinstance(selected, list) or len(selected) != V92_INPUT_COUNT:
        raise RuntimeError("v92 selected input inventory differs")
    with V92_ENTITIES.open(encoding="utf-8", newline="") as stream:
        entity_rows = list(csv.DictReader(stream))
    if len(entity_rows) != V92_ENTITY_COUNT:
        raise RuntimeError("v92 entity inventory differs")
    planned_stable, planned_evidence = _planned_keys(documents)
    base_stable = {row["stable_key"] for row in entity_rows}
    if planned_stable & base_stable:
        raise RuntimeError("planned stable key collides with v92")
    source_inputs = json.loads(V92_SOURCE_INPUTS.read_text(encoding="utf-8"))
    base_evidence = {
        value
        for row in source_inputs.get("sources", [])
        if isinstance(row, dict)
        for value in [row.get("provenance", {}).get("curated_record_key")]
        if isinstance(value, str)
    }
    if planned_evidence & base_evidence:
        raise RuntimeError("planned evidence key collides with v92")
    return {
        "v92_selected_input_count": len(selected),
        "v92_entity_count": len(entity_rows),
        "planned_distinct_stable_keys": len(planned_stable),
        "planned_distinct_evidence_keys": len(planned_evidence),
        "exact_v92_stable_key_collisions": [],
        "exact_v92_evidence_key_collisions": [],
        "merlin_shared_campus_resolution": (
            "Building 2 and Building 3 use separate schema-1.1 source records and "
            "the same campus stable key; adapter import is idempotent."
        ),
        "geometry_boundary": (
            "No coordinate or geometry is copied or inferred from addresses, PDFs, "
            "publisher images, satellite imagery, aerial imagery, or map clicks."
        ),
    }


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    documents = expected_source_documents()
    candidates = []
    for candidate in dict.fromkeys(site.candidate for site in SITES):
        members = [site for site in SITES if site.candidate == candidate]
        candidates.append(
            {
                "candidate_id": candidate,
                "decision": "seed_eligible_direct_authoritative_physical_update",
                "source_paths": [f"sources/{site.filename}" for site in members],
                "campus_stable_key": members[0].campus_key,
                "project_stable_keys": [site.project_key for site in members],
                "lifecycle": [
                    row
                    for site in members
                    for row in documents[site.filename]["lifecycle"]
                ],
                "withheld": [
                    "current-status extrapolation",
                    "untyped, design, marketing, or forecast capacity",
                    "energy, PUE, or WUE",
                    "facility type, operating model, or workload",
                    "standardized roles",
                    "coordinates or geometry",
                    "satellite, aerial, map-click, or computer-vision claims",
                ],
            }
        )
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-current-build-assessment-v1",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "candidate_count": 5,
        "seed_eligible_candidate_count": 5,
        "seed_eligible_source_record_count": 6,
        "review_only_count": 0,
        "regional_completeness_claimed": False,
        "candidates": candidates,
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "request_credentials_supplied": False,
        "successful_http_200_body_captures": 15,
        "failed_http_body_captures": 0,
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
                "capture_id": capture.capture_id,
                "requested_url": capture.url,
                "effective_url": capture.url,
                "retrieved_at": capture.retrieved_at,
                "body": {
                    "path": f"{capture.stem}.body",
                    "bytes": CAPTURE_FILE_PINS[f"{capture.stem}.body"][0],
                    "sha256": CAPTURE_FILE_PINS[f"{capture.stem}.body"][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "headers": {
                    "path": f"{capture.stem}.headers",
                    "bytes": CAPTURE_FILE_PINS[f"{capture.stem}.headers"][0],
                    "sha256": CAPTURE_FILE_PINS[f"{capture.stem}.headers"][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "http_status": 200,
                "content_type": capture.content_type,
                "request_credentials_supplied": False,
                "claim_use": capture.claim_use,
            }
            for capture in CAPTURES
        ],
        "complete_private_file_inventory": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in sorted(CAPTURE_FILE_PINS.items())
        ],
    }


def _file_tree(rows: Sequence[Mapping[str, Any]]) -> str:
    payload = (json.dumps(rows, indent=2, sort_keys=True) + "\n").encode()
    return _sha256_bytes(payload)


def _artifact_documents(
    recorded_at: str, source_documents: Mapping[str, Mapping[str, Any]]
) -> dict[str, bytes]:
    collision = _collision_witness(source_documents)
    source_records = _source_records(source_documents)
    totals = {
        "candidate_assessments": 5,
        "source_records": 6,
        "seed_eligible_candidates": 5,
        "seed_eligible_source_records": 6,
        "review_only_candidates": 0,
        "distinct_campuses_in_source_records": 5,
        "projects": 6,
        "distinct_entities_in_source_records": 11,
        "new_entities_against_v92": 11,
        "source_document_entity_snapshots": 12,
        "unique_imported_entity_snapshots": 11,
        "source_document_evidence_references": 13,
        "unique_evidence_records": 11,
        "lifecycle_observations": 8,
        "operating_model_observations": 0,
        "workload_observations": 0,
        "capacity_estimates": 2,
        "coordinates_present": 0,
        "geometry_present": 0,
    }
    readme = f"""# MERLIN, CyrusOne, and Beale official current-build gap tranche

This immutable artifact publishes six schema-1.1 records for five official-source candidates: MERLIN Bilbao-Arasur Buildings 2 and 3; CyrusOne FRA5 Halls 2 and 3; CyrusOne Wood Dale Phase 1; Beale Tulsa Project Clydesdale's initial phase; and Beale/Pima Project Blue (Project Bobcat) site preparation. The two MERLIN records share one campus key and import idempotently, yielding exactly eleven unique entities.

The source set preserves eight dated physical observations. Wood Dale retains both the 2025-05-13 shell topping-out observation and the later 2025-08-12 under-construction update. Tulsa retains the 2025-10-31 groundbreaking and 2025-11-24 progress update. Project Blue retains the latest inspected physical-work date, 2026-05-11, as site preparation. The May 22 response says major earthwork halted while native-plant harvesting continued; it is retained as context and does not establish a later categorical status. Every normalized status is dated last-observed evidence; current status is unknown.

Only two typed planned critical-IT capacities are normalized: 54 MW on the FRA5 campus and 18 MW on Wood Dale Phase 1. MERLIN's +162 MW, PUE 1.15, and WUE 0 remain design or marketing metadata; Beale's 500 MW remains untyped metadata. No energy, PUE, WUE, facility type, operating model, workload, standardized role, coordinate, geometry, satellite, aerial, map-click, or computer-vision claim is added. The CivicPlus newsroom response is a shell and is non-evidence. Pima permit and schedule material is identity/context only.

All source and artifact members received their frozen mode at or after {recorded_at}, and final paths were promoted without replacement only after that instant. Raw all-rights-reserved captures are represented only by exact hashes and compact factual extracts. The intact {CAPTURE_FILE_COUNT}-file capture directory was moved to recoverable Trash only after successful publication and validation. No open-seed, release, construction-master, map, federation, coverage, or review integration is performed.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "regional_completeness_claimed": False,
        "source_records": source_records,
        "totals": totals,
        "frozen_v92_non_mutation_witness": {
            "definition": {
                "path": "sources/open-seed-2026-07-21-v92.json",
                "bytes": V92_PINS[V92_DEFINITION][0],
                "sha256": V92_PINS[V92_DEFINITION][1],
            },
            "release_manifest": {
                "path": "releases/2026-07-21-open-seed-v92/manifest.json",
                "bytes": V92_PINS[V92_MANIFEST][0],
                "sha256": V92_PINS[V92_MANIFEST][1],
            },
            "release_entities": {
                "path": "releases/2026-07-21-open-seed-v92/entities.csv",
                "bytes": V92_PINS[V92_ENTITIES][0],
                "sha256": V92_PINS[V92_ENTITIES][1],
            },
            "release_tree_sha256": V92_TREE_SHA256,
            **collision,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v92_mutated": False,
            "release_integration": "none",
            "construction_master_integration": "none",
            "map_integration": "none",
            "federation_integration": "none",
            "coverage_integration": "none",
            "review_integration": "none",
        },
        "publication_contract": {
            "version": 2,
            "all_final_member_ctimes_at_or_after_recorded_at": True,
            "final_paths_absent_before_recorded_at": True,
            "publication_waited_until_recorded_at": True,
            "no_replace_promotion": True,
            "identity_checked_rollback_on_late_collision": True,
            "raw_capture_moved_to_trash_after_successful_validation": True,
            "source_file_mode": "0444",
            "artifact_directory_mode": "0555",
            "artifact_file_mode": "0444",
        },
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-disposition-v3",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "source_rights": (
            "All captured official response bodies are treated as all-rights-reserved; "
            "no redistribution license was relied on."
        ),
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
    }
    return {
        "README.md": readme.encode(),
        "candidate-assessment.json": _canonical(_candidate_assessment(recorded_at)),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _validate_sources(
    paths: Mapping[str, Path], *, require_frozen: bool
) -> list[dict[str, Any]]:
    expected = expected_source_documents()
    if set(paths) != set(SOURCE_FILENAMES):
        raise RuntimeError("source path inventory differs")
    for name in SOURCE_FILENAMES:
        path = paths[name]
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"curated source is unsafe: {name}")
        if path.read_bytes() != _canonical(expected[name]):
            raise RuntimeError(f"curated source differs: {name}")
        mode = stat.S_IMODE(path.stat().st_mode)
        if require_frozen and mode != 0o444:
            raise RuntimeError(f"curated source is not frozen: {name}")
        if not require_frozen and mode != 0o600:
            raise RuntimeError(f"curated source stage mode differs: {name}")
    documents = list(expected.values())
    if any(
        document[entity][field] is not None
        for document in documents
        for entity in ("campus", "project")
        for field in ("coordinates", "geometry")
    ):
        raise RuntimeError("source invented coordinates or geometry")
    if any(
        document[entity]["roles"]
        for document in documents
        for entity in ("campus", "project")
    ):
        raise RuntimeError("source invented roles")
    if any(
        document[collection]
        for document in documents
        for collection in ("operating_models", "workloads")
    ):
        raise RuntimeError("source invented normalized classification claims")
    lifecycle = {
        (
            document["project"]["stable_key"],
            row["value"],
            row["as_of_date"],
            row["method"],
        )
        for document in documents
        for row in document["lifecycle"]
    }
    expected_lifecycle = {
        (site.project_key, value, as_of_date, method)
        for site in SITES
        for value, as_of_date, method, _ in site.lifecycle
    }
    if lifecycle != expected_lifecycle or len(lifecycle) != 8:
        raise RuntimeError("lifecycle contract differs")
    capacities = [
        row for document in documents for row in document["capacities"]
    ]
    if sorted((row["entity"], row["base"]) for row in capacities) != [
        ("campus", 54.0),
        ("project", 18.0),
    ]:
        raise RuntimeError("capacity contract differs")
    if any(
        row["metric"] != "critical_it_mw" or row["stage"] != "planned"
        for row in capacities
    ):
        raise RuntimeError("capacity metric contract differs")
    return _source_records(expected)


def _validate_source_collisions() -> None:
    planned = expected_source_documents()
    _collision_witness(planned)
    planned_stable, planned_evidence = _planned_keys(planned)
    source_names = set(SOURCE_FILENAMES)
    collisions: dict[str, Any] = {}
    for path in SOURCES_ROOT.glob("*.json"):
        if path.name in source_names:
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        stable = {
            row.get("stable_key")
            for key in ("campus", "facility", "building", "project")
            if isinstance((row := document.get(key)), dict)
        }
        evidence = {
            row.get("key")
            for row in document.get("evidence", [])
            if isinstance(row, dict)
        }
        if planned_stable & stable or planned_evidence & evidence:
            collisions[str(path.relative_to(ROOT))] = {
                "stable_keys": sorted(planned_stable & stable),
                "evidence_keys": sorted(planned_evidence & evidence),
            }
    if collisions:
        raise RuntimeError(f"source collision detected: {collisions!r}")


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("capture directory absent or unsafe")
    entries = list(directory.iterdir())
    if (
        len(entries) != CAPTURE_FILE_COUNT
        or set(CAPTURE_FILE_PINS) != {entry.name for entry in entries}
        or any(entry.is_symlink() or not entry.is_file() for entry in entries)
    ):
        raise RuntimeError("capture directory closed set differs")
    if (
        sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES
        or tree_digest(directory) != CAPTURE_TREE_SHA256
    ):
        raise RuntimeError("capture directory aggregate differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(directory / name, pin)


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="merlin-cyrusone-beale-import-", dir="/private/tmp"
    ) as temporary:
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
            "entities": 11,
            "entity_snapshots": 11,
            "evidence": 11,
            "lifecycle_observations": 8,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 2,
        }
        if counts != expected:
            raise RuntimeError(f"offline import counts differ: {counts!r}")
        return counts


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def _assert_chronology(paths: Sequence[Path], recorded_at: str) -> None:
    threshold = _instant(recorded_at).timestamp()
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        if metadata.st_ctime + 0.000_001 < threshold:
            raise RuntimeError(f"member ctime predates recorded_at: {path}")


def validate_artifact(
    path: Path = ARTIFACT,
    *,
    source_paths: Mapping[str, Path] | None = None,
    require_live: bool = True,
    require_frozen: bool = True,
    wall_clock: datetime | None = None,
) -> dict[str, Any]:
    paths = source_paths or _source_paths(SOURCES_ROOT)
    source_records = _validate_sources(paths, require_frozen=require_frozen)
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError("artifact must be an ordinary directory")
    root_mode = stat.S_IMODE(path.stat().st_mode)
    if root_mode != (0o555 if require_frozen else 0o700):
        raise RuntimeError("artifact root mode differs")
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise RuntimeError("artifact closed set differs")
    expected_mode = 0o444 if require_frozen else 0o600
    if any(
        entry.is_symlink()
        or not entry.is_file()
        or stat.S_IMODE(entry.stat().st_mode) != expected_mode
        for entry in entries.values()
    ):
        raise RuntimeError("artifact frozen/staged member contract differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if (
        manifest_raw != _canonical(manifest)
        or manifest.get("artifact_id") != ARTIFACT_ID
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or manifest.get("candidate_assessments") != 5
        or manifest.get("curated_source_records") != 6
        or manifest.get("seed_eligible_candidates") != 5
        or manifest.get("review_only_candidates") != 0
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise RuntimeError("manifest contract differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (
            row["bytes"],
            row["sha256"],
        ):
            raise RuntimeError(f"manifest file pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise RuntimeError("manifest checksum differs")
    expected = _artifact_documents(manifest["recorded_at"], expected_source_documents())
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected[name]:
            raise RuntimeError(f"artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records:
        raise RuntimeError("artifact source pins differ")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise RuntimeError("wall clock must be timezone aware")
    if require_live and now.astimezone(UTC) < target:
        raise RuntimeError("artifact recorded_at is not live")
    if any(_instant(capture.retrieved_at) > target for capture in CAPTURES):
        raise RuntimeError("capture retrieval post-dates recorded_at")
    replay = [_offline_import(paths, manifest["recorded_at"]) for _ in range(2)]
    if replay[0] != replay[1]:
        raise RuntimeError("offline replay differs")
    if require_frozen:
        _assert_chronology([*paths.values(), path, *entries.values()], manifest["recorded_at"])
    return manifest


def _write_source_stage(
    stage: Path, documents: Mapping[str, Mapping[str, Any]]
) -> None:
    for name in SOURCE_FILENAMES:
        target = stage / name
        target.write_bytes(_canonical(documents[name]))
        target.chmod(0o600)
        _fsync_regular(target)
    _fsync_directory(stage)


def _write_artifact_stage(
    stage: Path, recorded_at: str, documents: Mapping[str, Mapping[str, Any]]
) -> None:
    payloads = _artifact_documents(recorded_at, documents)
    for name in CONTENT_FILES:
        target = stage / name
        target.write_bytes(payloads[name])
        target.chmod(0o600)
        _fsync_regular(target)
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
        "curated_source_records": 6,
        "seed_eligible_candidates": 5,
        "seed_eligible_source_records": 6,
        "review_only_candidates": 0,
        "successful_http_200_body_captures": 15,
        "raw_capture_redistributed": False,
        "raw_capture_directory_moved_intact_to_trash": True,
        "raw_capture_moved_after_successful_validation": True,
        "all_final_member_ctimes_at_or_after_recorded_at": True,
        "regional_completeness_claimed": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
    }
    manifest_path = stage / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    manifest_path.chmod(0o600)
    _fsync_regular(manifest_path)
    sidecar = stage / "manifest.sha256"
    sidecar.write_text(
        f"{_sha256(manifest_path)}  manifest.json\n", encoding="utf-8"
    )
    sidecar.chmod(0o600)
    _fsync_regular(sidecar)
    stage.chmod(0o700)
    _fsync_directory(stage)


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise RuntimeError("active official-source publication lock exists") from error
    os.write(descriptor, f"pid={os.getpid()}\n".encode())
    os.fsync(descriptor)
    status = os.fstat(descriptor)
    identity = (status.st_dev, status.st_ino)
    try:
        yield
    finally:
        os.close(descriptor)
        if PUBLICATION_LOCK.exists():
            current = PUBLICATION_LOCK.stat(follow_symlinks=False)
            if (current.st_dev, current.st_ino) != identity:
                raise RuntimeError("refusing substituted lock cleanup")
            PUBLICATION_LOCK.unlink()


@dataclass(frozen=True)
class _Prepared:
    source_stage: Path
    artifact_stage: Path
    recorded_at: str


def _prepare(recorded_at: str) -> _Prepared:
    if (
        any(
            (SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
        or ARTIFACT.exists()
        or ARTIFACT.is_symlink()
    ):
        raise RuntimeError("official-source final-path collision")
    _validate_source_collisions()
    capture = resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(capture)
    documents = expected_source_documents()
    source_stage = Path(
        tempfile.mkdtemp(prefix=".merlin-cyrusone-beale-sources.", dir=SOURCES_ROOT)
    )
    artifact_stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT)
    )
    try:
        _write_source_stage(source_stage, documents)
        _write_artifact_stage(artifact_stage, recorded_at, documents)
        validate_artifact(
            artifact_stage,
            source_paths=_source_paths(source_stage),
            require_live=False,
            require_frozen=False,
            wall_clock=_instant(recorded_at),
        )
        return _Prepared(source_stage, artifact_stage, recorded_at)
    except Exception:
        if source_stage.exists():
            shutil.rmtree(source_stage)
        if artifact_stage.exists():
            shutil.rmtree(artifact_stage)
        raise


def _freeze_after_barrier(prepared: _Prepared) -> None:
    target = _instant(prepared.recorded_at)
    while datetime.now(UTC) < target:
        time.sleep(min(0.25, (target - datetime.now(UTC)).total_seconds()))
    for name in SOURCE_FILENAMES:
        path = prepared.source_stage / name
        path.chmod(0o444)
        _fsync_regular(path)
    for path in prepared.artifact_stage.iterdir():
        path.chmod(0o444)
        _fsync_regular(path)
    prepared.artifact_stage.chmod(0o555)
    _fsync_directory(prepared.source_stage)
    _fsync_directory(prepared.artifact_stage)
    _assert_chronology(
        [
            *_source_paths(prepared.source_stage).values(),
            prepared.artifact_stage,
            *prepared.artifact_stage.iterdir(),
        ],
        prepared.recorded_at,
    )


def _publish(prepared: _Prepared) -> None:
    _freeze_after_barrier(prepared)
    if (
        any(
            (SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
        or ARTIFACT.exists()
        or ARTIFACT.is_symlink()
    ):
        raise RuntimeError("late official-source final-path collision")
    promoted: list[tuple[Path, Path]] = []
    try:
        for name in SOURCE_FILENAMES:
            staged = prepared.source_stage / name
            final = SOURCES_ROOT / name
            _promote_noreplace(staged, final)
            promoted.append((final, staged))
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        promoted.append((ARTIFACT, prepared.artifact_stage))
    except BaseException as error:
        for final, staged in reversed(promoted):
            try:
                _promote_noreplace(final, staged)
            except Exception as rollback_error:
                error.add_note(f"rollback failed for {final}: {rollback_error}")
        raise


def _move_capture_to_trash() -> None:
    if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
        raise RuntimeError("both raw capture origin and Trash destination exist")
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH))


def _result(manifest: Mapping[str, Any], status_value: str) -> dict[str, Any]:
    return {
        "artifact": str(ARTIFACT),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "capture_trash": str(CAPTURE_TRASH),
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "recorded_at": manifest["recorded_at"],
        "source_records": 6,
        "unique_entities": 11,
        "lifecycle_observations": 8,
        "capacity_estimates": 2,
        "status": status_value,
    }


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    if ARTIFACT.exists() and all(
        (SOURCES_ROOT / name).exists() for name in SOURCE_FILENAMES
    ):
        manifest = validate_artifact()
        _move_capture_to_trash()
        return _result(manifest, "existing-identical")
    if (
        ARTIFACT.exists()
        or ARTIFACT.is_symlink()
        or any(
            (SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
    ):
        raise RuntimeError("partial official-source final-path collision")
    target = (
        _instant(recorded_at)
        if recorded_at
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise RuntimeError("recorded_at must be future before staging")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    with _publication_lock():
        prepared = _prepare(timestamp)
        _publish(prepared)
        manifest = validate_artifact()
        _move_capture_to_trash()
        manifest = validate_artifact()
        if any(prepared.source_stage.iterdir()):
            raise RuntimeError("source stage not empty after publication")
        prepared.source_stage.rmdir()
    return _result(manifest, "published")


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
