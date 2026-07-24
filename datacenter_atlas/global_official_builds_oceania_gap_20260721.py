"""Publish the bounded Oceania official-build gap.

Seven Australian physical builds and one recently operational Guam closure
carry only direct-source observations. Ambiguous capacity labels, planned work,
and capability language remain narrative or review-only. Publication is
collision-failing and immutable.
"""

from __future__ import annotations

from contextlib import contextmanager
import csv
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

from . import global_official_builds_next_tranche_20260721 as publication
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "global-official-builds-oceania-gap-2026-07-21-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".global-official-builds-oceania-gap-20260721.lock"
CAPTURE_ORIGIN = Path("/private/tmp/dc-official-oceania-20260721.xLyZD6")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-official-oceania-20260721.xLyZD6")
CAPTURE_TREE_SHA256 = "4729444343350e9c3ec0ba388f90207e1012078656135005cb35cbc200d63148"
CAPTURE_FILE_COUNT = 40
CAPTURE_TOTAL_BYTES = 2_824_074

V81_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v81.json"
V81_RELEASE = ROOT / "releases/2026-07-21-open-seed-v81"
V81_MANIFEST = V81_RELEASE / "manifest.json"
V81_ENTITIES = V81_RELEASE / "entities.csv"
V81_PINS_ACCEPTED = True
V81_PINS = {
    V81_DEFINITION: (
        95_875,
        "f71ed7a189b6ba54d10bbed3353fb0baf680061bb3838771bbfd21fe4e6f066e",
    ),
    V81_MANIFEST: (
        14_362,
        "015c1758d9d6a44faf921fc4402dd5653c02dd96bb6a46ab3164aa83d183938d",
    ),
    V81_ENTITIES: (
        936_051,
        "d36809beb711f4a3f739cb596e5c66995f692666df7136b89190ae7d7b786d25",
    ),
}
V81_TREE_SHA256 = "50d98a2696119d722facbe3e0d017195b3251a147f0349f8ce96563c2fa84685"
V81_INPUT_COUNT = 428

SOURCE_FILENAMES = (
    "curated-official-2026-07-21-airtrunk-syd3-current-build.json",
    "curated-official-2026-07-21-cdc-eastern-creek-ec5-current-build.json",
    "curated-official-2026-07-21-cdc-eastern-creek-ec6-current-build.json",
    "curated-official-2026-07-21-cdc-marsden-park-current-build.json",
    "curated-official-2026-07-21-cdc-laverton-current-build.json",
    "curated-official-2026-07-21-cdc-brooklyn-remaining-facilities-current-build.json",
    "curated-official-2026-07-21-cdc-maddington-current-build.json",
    "curated-official-2026-07-21-gta-gu3-alupang-operational-closure.json",
)
CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

OfficialOceaniaGapError = publication.OfficialTrancheError
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
    "airtrunk_announcement.body": (91_167, "6cab9bfe6a05dafb57eb724762dc0746e702526dd0ce834134ef81fcd723c8e1"),
    "airtrunk_announcement.headers": (749, "230c570b63298ce8f63db7632f0ec3d04657293300e8f93d0ce0c1d66ce8c1a3"),
    "airtrunk_current.body": (90_199, "382b57ea6bb59428314dbbd9eacb6fd547a6bd0e4c8716483f14033838d9a276"),
    "airtrunk_current.headers": (707, "ac384017201382b33fcc500c1c678f4bb17c2e21bb141d49505440da70c21cba"),
    "airtrunk_status.body": (31_275, "cc7c9a0da80f086e4ba1e106cae388d796f91051a0bfaaa445cab41ec99d473a"),
    "airtrunk_status.headers": (3_870, "5b55b537081060ed1ffeea8cd7f346a23dec5ab24366c11e90a59c1ecb5fa37a"),
    "cdc_melbourne.body": (107_289, "a0d4bd0f390ef6c046c90e5fe4e1b0fc448b09a936ab30a9a3aabf3045304769"),
    "cdc_melbourne.headers": (3_412, "08dff1bf7de315cad178a9de066126a185f9736108a7b13fd9cca283974a2d01"),
    "cdc_perth.body": (108_868, "9628085823f3434144b66048b965c5b4babac113a5041c8191ca954706356c5c"),
    "cdc_perth.headers": (3_408, "86e9cfcf0c28f2afd378f1bbae7bc59a536a3bd0709c0ee76e2044c97699e92a"),
    "cdc_sydney.body": (107_676, "66d6de9440d4496482af80159cbe361afdb8e36bdebd5edf81ac1c65f1337620"),
    "cdc_sydney.headers": (3_408, "b96589f3975c8030a93289d25608267342badc6e0f1bcfe1a25a352267fa850b"),
    "cica_maddington.body": (26_978, "1e64874eeff27052f0a69dd2e7976a6e4f47a8b35043a1309a41db70fb61ba4a"),
    "cica_maddington.headers": (3_870, "4a39d76ef5be7db38c8d35b70974fa06f468e4c631c45c86d36e0d0a2112bd6a"),
    "datagrid_makarewa.body": (148_316, "c94407511dec2ca864850ca039857047a29373482c95f6098227165d5878d316"),
    "datagrid_makarewa.headers": (531, "a2ff4d0b8321e6e7c1c52f244998b7899e2c5b4a90e211e9fadeb7aee76dcfd1"),
    "dci_auckland.body": (66_527, "99b591aebbc5278f2465360f18cf75ed10dabbfbed2df489369c6eadef648487"),
    "dci_auckland.headers": (813, "10a52a7f0a7fe7a868abc7c55378fe182a6c877399c93d09262e234058a1ee9a"),
    "dci_locations.body": (91_673, "1d7c92594571e2af3d9823a1d2c685800e453dc686fa7d62d11892c3a483cb17"),
    "dci_locations.headers": (805, "5622e07195cf85c32e886593f67ab3861e67620474f1bfaaa296285465b86ad4"),
    "gta_groundbreak.body": (91_337, "fede036a2b5d72c7a33b1361edde09078eebc6f8b0aa0e8edd99751885f59f06"),
    "gta_groundbreak.headers": (1_979, "b33ce7162ab810687ed04583b1dd8e922a4935376c52567db504d9ddd7429e44"),
    "gta_gu3_opening.body": (27_457, "49e8be0a92a2c0362a2cdf6da6bd77d66433f189455ddd5b16dffa8e038d0e31"),
    "gta_gu3_opening.headers": (3_870, "18254706733f37122d6cbc7055d487c64a4f994b0b358b0039b88117cf1419b1"),
    "guam_jic.body": (115_693, "735f7d1f03e1f8a2da748fcbcfcb19b3fec1dfb88d1a0d5735c53a9e6050ad42"),
    "guam_jic.headers": (273, "03826799c7eacc44a64f5d739d0b23dc0b3e8ec75b7a4e9fd72fba8c9cc300a6"),
    "nextdc_ak1.body": (274_445, "dad062b0e92ad40f1e4ef9b40bf09b574fb18ffde79eba322003c40d6f3e3b77"),
    "nextdc_ak1.headers": (3_120, "6862ef63f35f38560dfbd9faa75f3a7b6e0fc66e3a4cf55239d2fb932330fb27"),
    "nzx_cdc.body": (39_019, "d7c1cae067f4a259aa1e86ef36516150831aad7d06b28b59608884ea87d6baf9"),
    "nzx_cdc.headers": (457, "c3fb21a92aee4e6917f695c8e839cc60c5f5f0f2694a28b1a0aaf253790eee13"),
    "pacific_commissioning.body": (873_516, "57638f55bcd36d5de6a0fbacf188c44a43bbbe034869a06c83c8436a4fc4b9a0"),
    "pacific_commissioning.headers": (1_596, "c97e03277b1cfc88e28bfc1b94d677ac6829f685c2b07accd9d9efdfd7ce5094"),
    "rdt_akl02.body": (79_996, "281fec0df071cec80c74e60e646e7309422ef08ebc3d8f607e816157e569ff07"),
    "rdt_akl02.headers": (289, "3f10bf49ceb1afb318c3fcd66b900282dbd406cd0755433e186de43521d857dd"),
    "tdf_papeete.body": (217_325, "74e67a08d405074e05c270ca3ff08b19b1f2b96c5677484f24082ee6f52903b3"),
    "tdf_papeete.headers": (509, "fed9551aa252990a4931bc28e4ce283b12e153e709711e51e96af7973e5064d3"),
    "vanuatu_pmo.body": (75_402, "908702319b71787214ecdd627eb5294c4b10cd99ff123bf04c46dbd22e20f75b"),
    "vanuatu_pmo.headers": (500, "4453edffd06904fb38e1ddccc378877347234e6b7d367f63a6e83c6612eda5f3"),
    "wauniversal_maddington.body": (125_405, "063ed1b84d31542ab4152f52138e196f9b3fea15fe136aef5c30d92af6906ee6"),
    "wauniversal_maddington.headers": (345, "bd48bb78bec73f8d698a51cfda1093d7a2e3526653ff475dd2bea3b1908f4a3b"),
}


def _capture(
    filename: str,
    url: str,
    *,
    published_at: str | None = None,
    content_type: str = "text/html",
    normalized_claims: bool = True,
) -> dict[str, Any]:
    size, digest = CAPTURE_FILE_PINS[f"{filename}.body"]
    return {
        "filename": f"{filename}.body",
        "url": url,
        "published_at": published_at,
        "retrieved_at": "2026-07-21T17:12:46Z",
        "http_status": 200,
        "bytes": size,
        "sha256": digest,
        "content_type": content_type,
        "used_for_normalized_claims": normalized_claims,
    }


CAPTURES = {
    "airtrunk_status": _capture("airtrunk_status", "https://www.linkedin.com/embed/feed/update/urn:li:activity:7442789273000603648", published_at="2026-03-26"),
    "airtrunk_current": _capture("airtrunk_current", "https://airtrunk.com/location/syd3-sydney-west/"),
    "airtrunk_announcement": _capture("airtrunk_announcement", "https://airtrunk.com/airtrunk-expands-western-sydney-region-with-new-syd3-hyperscale-data-centre-asia-pacifics-largest/", published_at="2021-11-04"),
    "cdc_sydney": _capture("cdc_sydney", "https://cdc.com.au/locations/sydney/"),
    "nzx_cdc": _capture("nzx_cdc", "https://www.nzx.com/announcements/469924", published_at="2026-03-26"),
    "cdc_melbourne": _capture("cdc_melbourne", "https://www.cdc.com.au/locations/melbourne/"),
    "wauniversal_maddington": _capture("wauniversal_maddington", "https://wauniversal.com.au/project/cdcs-maddington-data-centre/"),
    "cica_maddington": _capture("cica_maddington", "https://www.linkedin.com/embed/feed/update/urn:li:activity:7475736271517286400", published_at="2026-06-25"),
    "cdc_perth": _capture("cdc_perth", "https://cdc.com.au/locations/perth/"),
    "gta_gu3_opening": _capture("gta_gu3_opening", "https://www.linkedin.com/embed/feed/update/urn:li:activity:7445276952699039744", published_at="2026-04-02"),
    "guam_jic": _capture("guam_jic", "https://ghs.guam.gov/sites/default/files/jic_release_no._33_-_marine_corps_drive_open_precautionary_boil_water_notice_in_effect_for_parts_of_guam_telecommunications_update.pdf", published_at="2026-04-16", content_type="application/pdf"),
    "gta_groundbreak": _capture("gta_groundbreak", "https://news.gta.net/218940-gta-breaks-ground-on-alupang-data-center/", published_at="2022-10-06"),
    "datagrid_makarewa": _capture("datagrid_makarewa", "https://www.datagrid.nz/pr1-rc/resourceconsent", published_at="2026-03-11", normalized_claims=False),
    "dci_locations": _capture("dci_locations", "https://dcidatacenters.com/locations/", normalized_claims=False),
    "dci_auckland": _capture("dci_auckland", "https://dcidatacenters.com/auckland/", normalized_claims=False),
    "rdt_akl02": _capture("rdt_akl02", "https://www.rdtpacific.co.nz/project/dci-data-centers-akl02/", normalized_claims=False),
    "pacific_commissioning": _capture("pacific_commissioning", "https://www.commissioning.co.nz/datacentres", normalized_claims=False),
    "nextdc_ak1": _capture("nextdc_ak1", "https://www.nextdc.com/data-centres/new-zealand-data-centres/ak1-auckland", normalized_claims=False),
    "tdf_papeete": _capture("tdf_papeete", "https://www.tdf.fr/en/tdf-inaugure-son-premier-data-center-a-papeete-en-polynesie-francaise/", published_at="2025-09-18", normalized_claims=False),
    "vanuatu_pmo": _capture("vanuatu_pmo", "https://pmo.gov.vu/fr/1145-council-of-ministers-approves-key-recommendation-on-the-tamtam-submarine-cable%2C-data-centre-and-government-broadband-network.html", published_at="2025-12-05", normalized_claims=False),
}


PLANNED_ALIASES = frozenset(
    {
        "AirTrunk SYD3",
        "SYD3 Sydney West",
        "CDC Eastern Creek EC5",
        "CDC Eastern Creek EC6",
        "CDC Marsden Park",
        "CDC Laverton",
        "CDC Brooklyn",
        "CDC Maddington",
        "GTA GU3",
        "GTA Alupang Data Center",
    }
)
PLANNED_URLS = frozenset(capture["url"] for capture in CAPTURES.values())


def _evidence(
    capture_id: str,
    *,
    key: str,
    kind: str,
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
        "network_timeout_contract": "connect_timeout_10s_wall_clock_timeout_45s",
        "http_status": capture["http_status"],
        "content_type": capture["content_type"],
        "request_credentials_supplied": False,
        "rights_scope": (
            "Compact factual extraction from all-rights-reserved official bytes; "
            "raw bytes, headers, telemetry, and publisher media are not redistributed."
        ),
        "imagery_guardrail": (
            "No publisher image, satellite image, aerial image, computer vision, or "
            "analyst geolocation contributes to a normalized claim."
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


def _lifecycle(
    evidence_key: str,
    as_of_date: str,
    *,
    value: str = "under_construction",
    method: str = "authoritative_physical_status_update",
) -> dict[str, Any]:
    return {
        "entity": "project",
        "value": value,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": method,
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
    entity_evidence_key: str,
    status_evidence_key: str,
    as_of_date: str,
    campus_as_of_date: str | None = None,
    evidence: list[dict[str, Any]],
    lifecycle_value: str = "under_construction",
    lifecycle_method: str = "authoritative_physical_status_update",
    operating_models: list[dict[str, Any]] | None = None,
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
            evidence_key=entity_evidence_key,
            as_of_date=campus_as_of_date or as_of_date,
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
            _lifecycle(
                status_evidence_key,
                as_of_date,
                value=lifecycle_value,
                method=lifecycle_method,
            )
        ],
        "operating_models": operating_models or [],
        "workloads": [],
        "capacities": capacities or [],
    }


def _airtrunk_source() -> dict[str, Any]:
    status_key = "airtrunk-syd3-cooling-delivery-captured-2026-07-21"
    current_key = "airtrunk-syd3-current-facility-page-captured-2026-07-21"
    announcement_key = "airtrunk-syd3-original-design-announcement-captured-2026-07-21"
    evidence = [
        _evidence(
            "airtrunk_status",
            key=status_key,
            kind="company_disclosure",
            title="AirTrunk SYD3 cooling-infrastructure delivery",
            publisher="AirTrunk",
            source_family="airtrunk_official_updates",
            excerpt="AirTrunk reports delivery of a 700-tonne, 3,000-square-metre shipment of large-scale cooling infrastructure to its SYD3 campus.",
            metadata={
                "linkedin_activity_id": "7442789273000603648",
                "physical_status_scope": "Current site-specific equipment delivery supports generic under_construction only.",
                "status_semantics": "last_observed_current_status_unknown",
            },
        ),
        _evidence(
            "airtrunk_current",
            key=current_key,
            kind="company_disclosure",
            title="AirTrunk SYD3 Sydney West current facility page",
            publisher="AirTrunk",
            source_family="airtrunk_current_location_pages",
            excerpt="The current page identifies SYD3 in Sydney West and reports 400+ MW total capacity, 70,000 square metres of technical data halls, and 42 halls.",
            metadata={
                "capacity_label_as_reported": "400+MW total capacity",
                "capacity_guardrail": "The current generic label conflicts with the original 320+ MW IT-load design; no capacity row is normalized.",
                "operating_type_as_reported": "hyperscale campus",
            },
        ),
        _evidence(
            "airtrunk_announcement",
            key=announcement_key,
            kind="company_disclosure",
            title="AirTrunk SYD3 original design announcement",
            publisher="AirTrunk",
            source_family="airtrunk_company_news",
            excerpt="The original announcement describes nine phases and 320+ MW of IT load at SYD3.",
            metadata={
                "capacity_label_as_reported": "320+ MW of IT load",
                "capacity_guardrail": "The older IT-load label conflicts with the current 400+ MW generic total-capacity label; neither is normalized.",
            },
        ),
    ]
    return _document(
        campus_key="curated:airtrunk-syd3-western-sydney-campus",
        campus_name="AirTrunk SYD3 Western Sydney Campus",
        project_suffix="current-build",
        project_name="AirTrunk SYD3 Current Build",
        country="Australia",
        address="Sydney West, New South Wales, Australia",
        roles={"developer": ["AirTrunk"], "operator": ["AirTrunk"]},
        entity_evidence_key=current_key,
        status_evidence_key=status_key,
        as_of_date="2026-03-26",
        evidence=evidence,
    )


def _cdc_eastern_creek_source(facility: str) -> dict[str, Any]:
    token = facility.casefold()
    status_key = f"cdc-eastern-creek-{token}-current-status-captured-2026-07-21"
    corroboration_key = f"cdc-eastern-creek-{token}-nearing-operational-captured-2026-07-21"
    evidence = [
        _evidence(
            "cdc_sydney",
            key=status_key,
            kind="company_disclosure",
            title=f"CDC Eastern Creek {facility} current status",
            publisher="CDC Data Centres",
            source_family="cdc_current_location_pages",
            excerpt=f"CDC identifies {facility} as one of two separate Eastern Creek data centres under construction.",
            metadata={
                "campus_capacity_label_as_reported": "over 200 MW",
                "capacity_guardrail": "The campus-wide generic label is not allocated to the individual facility and creates no capacity row.",
                "status_semantics": "last_observed_current_status_unknown",
            },
        ),
        _evidence(
            "nzx_cdc",
            key=corroboration_key,
            kind="company_disclosure",
            title=f"CDC Eastern Creek additional-facility progress corroboration for {facility}",
            publisher="NZX Limited",
            source_family="infratil_market_announcements",
            excerpt="A dated Infratil announcement says two additional Eastern Creek data centres were nearing operational status.",
            metadata={
                "identity_guardrail": f"Used only with CDC's direct EC5/EC6 enumeration; the aggregate statement is not independent facility completion proof for {facility}.",
                "lifecycle_guardrail": "Nearing operational is retained as under_construction and never promoted to commissioning or operational.",
            },
        ),
    ]
    campus_key = "curated:cdc-eastern-creek-campus"
    return _document(
        campus_key=campus_key,
        campus_name="CDC Eastern Creek Campus",
        project_suffix=f"{token}-current-build",
        project_name=f"CDC Eastern Creek {facility} Current Build",
        country="Australia",
        address="Eastern Creek, Sydney, New South Wales, Australia",
        roles={"developer": ["CDC Data Centres"], "operator": ["CDC Data Centres"]},
        entity_evidence_key=(
            corroboration_key if facility == "EC6" else status_key
        ),
        status_evidence_key=status_key,
        as_of_date="2026-07-21",
        campus_as_of_date="2026-03-26" if facility == "EC6" else None,
        evidence=evidence,
    )


def _cdc_single_page_source(
    *,
    capture_id: str,
    key_token: str,
    campus_key: str,
    campus_name: str,
    project_suffix: str,
    project_name: str,
    address: str,
    excerpt: str,
    capacity_label: str,
    status_scope: str,
) -> dict[str, Any]:
    status_key = f"cdc-{key_token}-current-status-captured-2026-07-21"
    evidence = [
        _evidence(
            capture_id,
            key=status_key,
            kind="company_disclosure",
            title=f"{campus_name} current status",
            publisher="CDC Data Centres",
            source_family="cdc_current_location_pages",
            excerpt=excerpt,
            metadata={
                "capacity_label_as_reported": capacity_label,
                "capacity_guardrail": "The campus or regional generic label is not allocated to the selected project and creates no capacity row.",
                "physical_status_scope": status_scope,
                "status_semantics": "last_observed_current_status_unknown",
            },
        )
    ]
    return _document(
        campus_key=campus_key,
        campus_name=campus_name,
        project_suffix=project_suffix,
        project_name=project_name,
        country="Australia",
        address=address,
        roles={"developer": ["CDC Data Centres"], "operator": ["CDC Data Centres"]},
        entity_evidence_key=status_key,
        status_evidence_key=status_key,
        as_of_date="2026-07-21",
        evidence=evidence,
    )


def _cdc_marsden_source() -> dict[str, Any]:
    return _cdc_single_page_source(
        capture_id="cdc_sydney",
        key_token="marsden-park",
        campus_key="curated:cdc-marsden-park-campus",
        campus_name="CDC Marsden Park Campus",
        project_suffix="early-construction",
        project_name="CDC Marsden Park Early Construction",
        address="Marsden Park, Sydney, New South Wales, Australia",
        excerpt="CDC says its Marsden Park campus is in the early stages of construction.",
        capacity_label="over 504 MW planned; scalable to 1 GW",
        status_scope="Direct operator wording supports generic under_construction only.",
    )


def _cdc_laverton_source() -> dict[str, Any]:
    return _cdc_single_page_source(
        capture_id="cdc_melbourne",
        key_token="laverton",
        campus_key="curated:cdc-laverton-melbourne-campus",
        campus_name="CDC Laverton Melbourne Campus",
        project_suffix="current-build",
        project_name="CDC Laverton Current Build",
        address="Laverton, Melbourne, Victoria, Australia",
        excerpt="CDC says the entirety of its Laverton campus is currently under construction.",
        capacity_label="over 400 MW additional capacity when complete",
        status_scope="Direct operator wording supports one campus-level current-build aggregate; no building count is invented.",
    )


def _cdc_brooklyn_source() -> dict[str, Any]:
    return _cdc_single_page_source(
        capture_id="cdc_melbourne",
        key_token="brooklyn-remaining-facilities",
        campus_key="curated:cdc-brooklyn-melbourne-campus",
        campus_name="CDC Brooklyn Melbourne Campus",
        project_suffix="remaining-facilities-current-build",
        project_name="CDC Brooklyn Remaining Facilities Current Build",
        address="Brooklyn, Melbourne, Victoria, Australia",
        excerpt="CDC says BK1 is operational while the remaining Brooklyn campus facilities are currently under construction.",
        capacity_label="over 350 MW campus capacity",
        status_scope="The unresolved remainder is one aggregate project; no facility count, name, or individual allocation is invented.",
    )


def _cdc_maddington_source() -> dict[str, Any]:
    status_key = "cdc-maddington-structural-shell-captured-2026-07-21"
    corroboration_key = "cdc-maddington-heavy-precast-installation-captured-2026-07-21"
    identity_key = "cdc-maddington-current-campus-page-captured-2026-07-21"
    evidence = [
        _evidence(
            "cica_maddington",
            key=status_key,
            kind="company_disclosure",
            title="CDC Maddington structural-shell works",
            publisher="Crane Industry Council of Australia",
            source_family="cica_official_updates",
            excerpt="CICA reports two erected tower cranes and installation of 26 large structural steel trusses at the CDC Maddington development.",
            metadata={
                "linkedin_activity_id": "7475736271517286400",
                "project_value_and_capacity_as_reported": "$415 million, 200MW development",
                "capacity_guardrail": "The 200 MW label is untyped and creates no normalized capacity.",
                "workload_guardrail": "AI and cloud design language describes capability, not an observed active workload.",
                "status_semantics": "last_observed_current_status_unknown",
            },
        ),
        _evidence(
            "wauniversal_maddington",
            key=corroboration_key,
            kind="company_disclosure",
            title="CDC Maddington ongoing heavy-precast installation",
            publisher="WA Universal",
            source_family="wa_universal_project_portfolio",
            excerpt="WA Universal reports ongoing installation of heavy precast units and structure works supported by two CML800 tower cranes.",
            metadata={"physical_status_scope": "Direct project-participant corroboration for structural-shell work."},
        ),
        _evidence(
            "cdc_perth",
            key=identity_key,
            kind="company_disclosure",
            title="CDC Maddington current campus page",
            publisher="CDC Data Centres",
            source_family="cdc_current_location_pages",
            excerpt="CDC identifies its Maddington campus and reports 200 MW+ total capacity upon completion.",
            metadata={
                "capacity_label_as_reported": "200 MW+ total capacity upon completion",
                "capacity_guardrail": "The generic campus label remains narrative and is not treated as IT load, gross demand, current draw, energy, or PUE.",
                "workload_guardrail": "AI-ready is a capability, not an active workload observation.",
            },
        ),
    ]
    return _document(
        campus_key="curated:cdc-maddington-perth-campus",
        campus_name="CDC Maddington Perth Campus",
        project_suffix="current-build",
        project_name="CDC Maddington Current Build",
        country="Australia",
        address="Maddington, Perth, Western Australia, Australia",
        roles={"developer": ["CDC Data Centres"], "operator": ["CDC Data Centres"], "contractor": ["BUILT"]},
        entity_evidence_key=identity_key,
        status_evidence_key=status_key,
        as_of_date="2026-06-25",
        evidence=evidence,
        lifecycle_value="shell",
        lifecycle_method="authoritative_physical_status_update",
    )


def _gta_gu3_source() -> dict[str, Any]:
    opening_key = "gta-gu3-april-opening-announcement-captured-2026-07-21"
    current_identity_key = "gta-gu3-current-about-identity-captured-2026-07-21"
    operational_key = "gta-gu3-alupang-running-on-genset-captured-2026-07-21"
    design_key = "gta-alupang-facility-design-captured-2026-07-21"
    evidence = [
        _evidence(
            "gta_gu3_opening",
            key=opening_key,
            kind="company_disclosure",
            title="GTA GU3 April opening announcement",
            publisher="GTA",
            source_family="gta_official_updates",
            excerpt="GTA identifies GU3 as its third data center and says it is opening in April 2026.",
            metadata={
                "linkedin_activity_id": "7445276952699039744",
                "lifecycle_guardrail": "Opening intent alone is not used as operational proof.",
            },
        ),
        _evidence(
            "gta_groundbreak",
            key=current_identity_key,
            kind="company_disclosure",
            title="GTA current About section naming GU3 Alupang",
            publisher="GTA",
            source_family="gta_current_newsroom_about_sections",
            excerpt="The retrieval-date current About section says GTA operates three data centers and names GU3 in Alupang as its newest facility.",
            metadata={
                "current_body_observed_at": "2026-07-21T17:12:46Z",
                "publication_version_guardrail": "This dynamic current-body text is retrieval-date corroboration and is not represented as text from the page's 2022 article version.",
            },
        ),
        _evidence(
            "guam_jic",
            key=operational_key,
            kind="government_record",
            title="Guam JIC telecommunications update naming GU3 Alupang",
            publisher="Guam Homeland Security and Office of Civil Defense",
            source_family="guam_joint_information_center_releases",
            excerpt="The April 16 JIC release attributes a GTA update stating that GU3 Alupang CLS was running on generator power.",
            metadata={
                "identity_linkage": "The government release names GTA and GU3 Alupang; GTA's own announcement identifies GU3 as its third data center.",
                "operational_scope": "Running during an emergency is direct site-operation proof as of 2026-04-16.",
                "status_semantics": "last_observed_current_status_unknown",
                "historical_guardrail": "No under_construction observation is created in this tranche.",
            },
        ),
        _evidence(
            "gta_groundbreak",
            key=design_key,
            kind="company_disclosure",
            title="GTA Alupang Data Center facility design",
            publisher="GTA",
            source_family="gta_company_news",
            excerpt="GTA directly labels the two-story Alupang facility as 31,000 square feet with 4.0 MW of power capacity and best-in-class colocation.",
            metadata={
                "power_capacity_mw_as_reported": 4.0,
                "capacity_scope": "Exactly one design-stage gross_facility_mw row; not installed or current load, generation, annual energy, consumption, or PUE.",
                "workload_guardrail": "Edge-computing-led describes capability and creates no workload observation.",
            },
        ),
    ]
    campus_key = "curated:gta-gu3-alupang-data-center"
    as_of_date = "2026-04-16"
    return _document(
        campus_key=campus_key,
        campus_name="GTA GU3 Alupang Data Center",
        project_suffix="initial-build",
        project_name="GTA GU3 Alupang Initial Build",
        country="Guam",
        address="Alupang, Tamuning, Guam",
        roles={"developer": ["GTA"], "operator": ["GTA"]},
        entity_evidence_key=current_identity_key,
        status_evidence_key=operational_key,
        as_of_date=as_of_date,
        evidence=evidence,
        lifecycle_value="operational",
        lifecycle_method="government_record",
        operating_models=[
            {
                "entity": "campus",
                "value": "colocation",
                "evidence_key": design_key,
                "as_of_date": as_of_date,
                "method": "company_disclosure",
                "confidence": 0.99,
            }
        ],
        capacities=[
            {
                "entity": "project",
                "metric": "gross_facility_mw",
                "stage": "design",
                "unit": "MW",
                "low": 4.0,
                "base": 4.0,
                "high": 4.0,
                "method": "reported",
                "confidence": 0.99,
                "evidence_key": design_key,
                "as_of_date": as_of_date,
                "target_date": None,
                "notes": "Direct facility power-capacity design label only; no installed, current-draw, energy, generation, consumption, or PUE claim.",
            }
        ],
    )


def expected_source_documents() -> dict[str, dict[str, Any]]:
    """Return the exact eight schema-1.1 source documents in requested order."""

    builders = (
        _airtrunk_source,
        lambda: _cdc_eastern_creek_source("EC5"),
        lambda: _cdc_eastern_creek_source("EC6"),
        _cdc_marsden_source,
        _cdc_laverton_source,
        _cdc_brooklyn_source,
        _cdc_maddington_source,
        _gta_gu3_source,
    )
    return {
        name: builder()
        for name, builder in zip(SOURCE_FILENAMES, builders, strict=True)
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
                "disposition": (
                    "seed_eligible_recent_operational_closure"
                    if document["project"]["country"] == "Guam"
                    else "seed_eligible_official_current_physical_update"
                ),
                "seed_eligible": True,
                "seeded": False,
            }
        )
    return records


def _review_candidates() -> list[dict[str, Any]]:
    rows = [
        ("datagrid-makarewa-ai-factory", "New Zealand", "review_only_permitted_no_physical_start", "Full resource consent paves the way for construction to commence but does not prove that physical work started; the reported 280 MW remains narrative."),
        ("dci-akl02-auckland", "New Zealand", "review_only_status_conflict", "DCI says construction is underway while direct project participants say the first stage is complete; no single current project status is normalized."),
        ("nextdc-ak1-auckland", "New Zealand", "review_only_in_development", "NEXTDC labels AK1 In Development; the 15 MW design does not establish physical construction."),
        ("tdf-papeete-expansion", "French Polynesia", "review_only_planned_expansion", "TDF says a 2026 extension is planned but provides no physical-start evidence."),
        ("vanuatu-government-data-centre", "Vanuatu", "review_only_identity_ambiguous", "A government direction to complete implementation does not resolve whether this is a new facility, the existing Port Vila site, or another project."),
        ("airtrunk-mel2", "Australia", "review_only_development_only", "The bounded current-source sweep found development language but no recent physical-build observation."),
        ("dci-syd02", "Australia", "review_only_development_only", "DCI's current portfolio lists the candidate in development without eligible physical evidence."),
        ("dci-syd03", "Australia", "review_only_development_only", "DCI's current portfolio lists the candidate in development without eligible physical evidence."),
        ("dci-cbr01", "Australia", "review_only_development_only", "DCI's current portfolio lists the candidate in development without eligible physical evidence."),
        ("dci-adl03", "Australia", "review_only_development_only", "DCI's current portfolio lists the candidate in development without eligible physical evidence."),
        ("bounded-official-sweep-fiji", "Fiji", "bounded_negative_no_eligible_current_build", "The bounded official-source sweep produced no site-specific eligible current physical-build record."),
        ("bounded-official-sweep-papua-new-guinea", "Papua New Guinea", "bounded_negative_no_eligible_current_build", "The bounded official-source sweep produced no site-specific eligible current physical-build record."),
        ("bounded-official-sweep-samoa", "Samoa", "bounded_negative_no_eligible_current_build", "The bounded official-source sweep produced no site-specific eligible current physical-build record."),
        ("bounded-official-sweep-tonga", "Tonga", "bounded_negative_no_eligible_current_build", "The bounded official-source sweep produced no site-specific eligible current physical-build record."),
        ("bounded-official-sweep-palau", "Palau", "bounded_negative_no_eligible_current_build", "The bounded official-source sweep produced no site-specific eligible current physical-build record."),
        ("bounded-official-sweep-new-caledonia", "New Caledonia", "bounded_negative_no_eligible_current_build", "The bounded official-source sweep produced no site-specific eligible current physical-build record."),
        ("bounded-official-sweep-french-polynesia", "French Polynesia", "bounded_negative_no_additional_eligible_current_build", "Apart from the separately reviewed planned TDF expansion, no eligible current physical-build record was found."),
    ]
    return [
        {
            "candidate_id": candidate_id,
            "country": country,
            "decision": decision,
            "source_record_created": False,
            "seed_eligible": False,
            "normalized_claims_created": 0,
            "basis": basis,
        }
        for candidate_id, country, decision, basis in rows
    ]


def _candidate_assessments(recorded_at: str) -> dict[str, Any]:
    seed_rows = []
    for name, document in expected_source_documents().items():
        seed_rows.append(
            {
                "candidate_id": document["project"]["stable_key"],
                "country": document["project"]["country"],
                "decision": (
                    "seed_eligible_recent_operational_closure"
                    if document["project"]["country"] == "Guam"
                    else "seed_eligible_direct_current_physical_update"
                ),
                "source_record_created": True,
                "source_path": f"sources/{name}",
                "seed_eligible": True,
                "lifecycle_observations": 1,
                "capacity_estimates": len(document["capacities"]),
                "operating_model_observations": len(document["operating_models"]),
                "workload_observations": 0,
                "coordinates_created": 0,
            }
        )
    review_rows = _review_candidates()
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-oceania-official-gap-assessment-v1",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "candidate_count": len(seed_rows) + len(review_rows),
        "seed_eligible_count": len(seed_rows),
        "review_only_count": len(review_rows),
        "regional_completeness_claimed": False,
        "candidates": [*seed_rows, *review_rows],
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "capture_protocol": "Credential-free curl GETs with explicit 10-second connect and 45-second wall-clock timeouts.",
        "successful_http_200_body_captures": len(CAPTURES),
        "failed_or_partial_captures": 0,
        "failed_or_partial_capture_claims": 0,
        "request_credentials_supplied": False,
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
                "effective_url": capture["url"],
                "retrieved_at": capture["retrieved_at"],
                "http_status": 200,
                "content_type": capture["content_type"],
                "body": {"bytes": capture["bytes"], "sha256": capture["sha256"], "retained_in_artifact": False, "moved_to_trash": True},
                "capture_method": "credential_free_curl_location_compressed",
                "network_timeout_contract": "connect_timeout_10s_wall_clock_timeout_45s",
                "request_credentials_supplied": False,
                "used_for_normalized_claims": capture["used_for_normalized_claims"],
            }
            for capture_id, capture in sorted(CAPTURES.items())
        ],
        "complete_private_file_inventory": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in sorted(CAPTURE_FILE_PINS.items())
        ],
        "technical_incidents": [],
    }


def _artifact_documents(recorded_at: str, source_documents: Mapping[str, Mapping[str, Any]]) -> dict[str, bytes]:
    source_records = _source_records(source_documents)
    assessment_count = 8 + len(_review_candidates())
    readme = f"""# Oceania official-build gap assessment

This immutable artifact records {assessment_count} bounded candidate dispositions researched on 2026-07-21: seven seed-eligible Australian physical builds, one recently operational Guam closure, and {len(_review_candidates())} review-only candidates. It makes no regional-completeness claim.

The Australian records are AirTrunk SYD3; CDC Eastern Creek EC5 and EC6 as separate projects on one campus; CDC Marsden Park; CDC Laverton; one aggregate for CDC Brooklyn's remaining unnamed facilities; and CDC Maddington. Maddington is a structural-shell observation. The other six Australian rows are under-construction observations. Every lifecycle value is last-observed; present status after its evidence date remains unknown.

GTA's GU3/Alupang closure is operational as of 2026-04-16 because a Guam Joint Information Center release attributes a GTA status update that names GU3 Alupang CLS as running on generator power. GTA's April-opening announcement and the retrieval-date current About section resolve GU3 identity; the dynamic About text is not represented as part of the 2022 article version. No under-construction row is created for GU3.

Only GTA's directly labeled 4.0 MW facility power capacity becomes a capacity row: gross_facility_mw at design stage. Its directly advertised colocation model creates one operating-model row. The 320+ MW IT-load versus 400+ MW generic-total conflict at SYD3, all CDC campus or untyped capacity labels, and Maddington's untyped 200 MW remain narrative. No figure becomes installed or current load, energy use, generation, annual consumption, or PUE.

Hyperscale, AI-ready, cloud, sovereign, and edge-computing-led language describes type or capability, never an observed active workload. No workload row is created. Locality and address wording creates no coordinate or geometry.

Datagrid Makarewa remains permitted without start; DCI AKL02 remains unresolved because operator and project-participant status pages conflict; NEXTDC AK1 is development-only; TDF Papeete's expansion is planned; and the Vanuatu government project has unresolved facility identity. Named development-only Australian candidates and bounded Pacific-country negatives create no source record.

All planned names, source URLs, stable keys, and evidence keys were checked for exact normalized absence from independently accepted v81. Accepted v81 and downstream products remain unchanged. Raw all-rights-reserved captures are not redistributed; the complete {CAPTURE_FILE_COUNT}-file capture directory was moved intact to the recoverable Trash path in the rights inventory.

All source and artifact bytes were complete in private staging before `{recorded_at}`. Final paths remained absent until the declared instant and were promoted without replacement with identity-checked rollback. Source and artifact files are frozen mode 0444; the artifact directory is mode 0555.
"""
    duplicate_witness = _v81_duplicate_witness(source_documents)
    totals = {
        "candidate_assessments": assessment_count,
        "source_records": 8,
        "seed_eligible_source_records": 8,
        "review_only_candidates": len(_review_candidates()),
        "distinct_campuses": 7,
        "projects": 8,
        "entity_snapshots": 16,
        "unique_evidence_records": 17,
        "lifecycle_observations": 8,
        "operating_model_observations": 1,
        "workload_observations": 0,
        "capacity_estimates": 1,
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
        "frozen_v81_non_mutation_witness": {
            "definition": {"path": "sources/open-seed-2026-07-21-v81.json", "bytes": V81_PINS[V81_DEFINITION][0], "sha256": V81_PINS[V81_DEFINITION][1]},
            "release_manifest": {"path": "releases/2026-07-21-open-seed-v81/manifest.json", "bytes": V81_PINS[V81_MANIFEST][0], "sha256": V81_PINS[V81_MANIFEST][1]},
            "release_tree_sha256": V81_TREE_SHA256,
            "v81_selected_input_count": V81_INPUT_COUNT,
            "new_source_paths_selected_by_v81": False,
            **duplicate_witness,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v81_mutated": False,
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
        "candidate_dispositions": {"seed_eligible": 8, "review_only": len(_review_candidates())},
    }
    return {
        "README.md": readme.encode(),
        "candidate-assessment.json": _canonical(_candidate_assessments(recorded_at)),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _file_tree(rows: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_bytes((json.dumps(rows, indent=2, sort_keys=True) + "\n").encode())


def _write_source_stage(stage: Path, documents: Mapping[str, Mapping[str, Any]]) -> None:
    for name in SOURCE_FILENAMES:
        output = stage / name
        output.write_bytes(_canonical(documents[name]))
        output.chmod(0o444)
        _fsync_regular(output)
    _fsync_directory(stage)


def _write_artifact_stage(stage: Path, recorded_at: str, documents: Mapping[str, Mapping[str, Any]]) -> None:
    payloads = _artifact_documents(recorded_at, documents)
    for name in CONTENT_FILES:
        output = stage / name
        output.write_bytes(payloads[name])
        output.chmod(0o444)
        _fsync_regular(output)
    rows = [{"bytes": (stage / name).stat().st_size, "path": name, "sha256": _sha256(stage / name)} for name in CONTENT_FILES]
    manifest = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-artifact-manifest-v3",
        "recorded_at": recorded_at,
        "files": rows,
        "tree_sha256": _file_tree(rows),
        "closed_file_set": sorted(CLOSED_FILES),
        "candidate_assessments": 8 + len(_review_candidates()),
        "curated_source_records": 8,
        "seed_eligible_source_records": 8,
        "review_only_candidates": len(_review_candidates()),
        "successful_http_200_body_captures": len(CAPTURES),
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
        raise OfficialOceaniaGapError("source path inventory differs")
    for name in SOURCE_FILENAMES:
        source = paths[name]
        if source.is_symlink() or not source.is_file():
            raise OfficialOceaniaGapError(f"curated source is absent: {source}")
        if source.read_bytes() != _canonical(expected[name]):
            raise OfficialOceaniaGapError(f"curated source differs: {name}")
        if stat.S_IMODE(source.stat().st_mode) != 0o444:
            raise OfficialOceaniaGapError(f"curated source mode differs: {name}")
    documents = list(expected.values())
    if any(document[entity]["coordinates"] is not None or document[entity]["geometry"] is not None for document in documents for entity in ("campus", "project")):
        raise OfficialOceaniaGapError("source invented coordinates or geometry")
    if sum(len(document["capacities"]) for document in documents) != 1:
        raise OfficialOceaniaGapError("capacity boundary differs")
    gta_capacity = documents[-1]["capacities"][0]
    if (
        gta_capacity["metric"],
        gta_capacity["stage"],
        gta_capacity["base"],
    ) != ("gross_facility_mw", "design", 4.0):
        raise OfficialOceaniaGapError("GTA GU3 capacity boundary differs")
    if any(document["workloads"] for document in documents):
        raise OfficialOceaniaGapError("capability became workload")
    if sum(len(document["operating_models"]) for document in documents) != 1:
        raise OfficialOceaniaGapError("operating-model boundary differs")
    return _source_records(expected)


def _validate_source_collisions() -> None:
    planned = expected_source_documents()
    stable_keys = {document[entity]["stable_key"] for document in planned.values() for entity in ("campus", "project")}
    evidence_keys = {evidence["key"] for document in planned.values() for evidence in document["evidence"]}
    if len(stable_keys) != 15 or len(evidence_keys) != 17:
        raise OfficialOceaniaGapError("planned source keys are not unique")
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
        other_stable = {record.get("stable_key") for key in ("campus", "project") if isinstance((record := document.get(key)), dict)}
        other_evidence = {row.get("key") for row in document.get("evidence", []) if isinstance(row, dict)}
        stable_overlap = sorted(stable_keys & other_stable)
        evidence_overlap = sorted(evidence_keys & other_evidence)
        if stable_overlap or evidence_overlap:
            collisions[source.name] = {"stable_keys": stable_overlap, "evidence_keys": evidence_overlap}
    if collisions:
        raise OfficialOceaniaGapError(f"curated source collision: {collisions!r}")


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split()).rstrip("/")


def _selected_v81_documents() -> list[Mapping[str, Any]]:
    definition = json.loads(V81_DEFINITION.read_text(encoding="utf-8"))
    documents: list[Mapping[str, Any]] = []
    for row in definition["curated_inputs"]:
        source = ROOT / row["path"]
        document = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(document, dict):
            documents.append(document)
    return documents


def _nested_strings(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, Mapping):
        return {
            text
            for nested in value.values()
            for text in _nested_strings(nested)
        }
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return {text for nested in value for text in _nested_strings(nested)}
    return set()


def _strings_for_key(value: Any, token: str) -> set[str]:
    if isinstance(value, Mapping):
        found: set[str] = set()
        for key, nested in value.items():
            if token in str(key).casefold():
                found.update(_nested_strings(nested))
            found.update(_strings_for_key(nested, token))
        return found
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return {
            text
            for nested in value
            for text in _strings_for_key(nested, token)
        }
    return set()


def _v81_duplicate_witness(planned: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    documents = list((planned or expected_source_documents()).values())
    planned_stable = {document[entity]["stable_key"] for document in documents for entity in ("campus", "project")}
    planned_evidence = {row["key"] for document in documents for row in document["evidence"]}
    existing_stable: set[str] = set()
    existing_evidence: set[str] = set()
    existing_names: set[str] = set()
    existing_urls: set[str] = set()
    for document in _selected_v81_documents():
        existing_names.update(
            _normalize_text(text) for text in _strings_for_key(document, "alias")
        )
        existing_urls.update(
            _normalize_text(text) for text in _strings_for_key(document, "url")
        )
        for entity in ("campus", "project"):
            record = document.get(entity)
            if isinstance(record, dict):
                if isinstance(record.get("stable_key"), str):
                    existing_stable.add(record["stable_key"])
                if isinstance(record.get("name"), str):
                    existing_names.add(_normalize_text(record["name"]))
        for row in document.get("evidence", []):
            if not isinstance(row, dict):
                continue
            if isinstance(row.get("key"), str):
                existing_evidence.add(row["key"])
            if isinstance(row.get("source_url"), str):
                existing_urls.add(_normalize_text(row["source_url"]))
    with V81_ENTITIES.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("name"):
                existing_names.add(_normalize_text(row["name"]))
            if row.get("source_url"):
                existing_urls.add(_normalize_text(row["source_url"]))
    alias_overlap = sorted(alias for alias in PLANNED_ALIASES if _normalize_text(alias) in existing_names)
    url_overlap = sorted(url for url in PLANNED_URLS if _normalize_text(url) in existing_urls)
    stable_overlap = sorted(planned_stable & existing_stable)
    evidence_overlap = sorted(planned_evidence & existing_evidence)
    if alias_overlap or url_overlap or stable_overlap or evidence_overlap:
        raise OfficialOceaniaGapError(
            f"planned candidate duplicates accepted v81: aliases={alias_overlap!r}, urls={url_overlap!r}, stable={stable_overlap!r}, evidence={evidence_overlap!r}"
        )
    return {
        "planned_identity_aliases_checked": len(PLANNED_ALIASES),
        "planned_source_urls_checked": len(PLANNED_URLS),
        "planned_stable_keys_checked": len(planned_stable),
        "planned_evidence_keys_checked": len(planned_evidence),
        "v81_name_or_alias_exact_normalized_collisions": 0,
        "v81_source_url_exact_normalized_collisions": 0,
        "v81_stable_key_collisions": 0,
        "v81_evidence_key_collisions": 0,
    }


def _validate_v81_nonmutation() -> None:
    if not V81_PINS_ACCEPTED:
        raise OfficialOceaniaGapError("accepted v81 pins have not been supplied")
    for source, pin in V81_PINS.items():
        _pin(source, pin)
    if tree_digest(V81_RELEASE) != V81_TREE_SHA256:
        raise OfficialOceaniaGapError("accepted v81 release tree differs")
    definition = json.loads(V81_DEFINITION.read_text(encoding="utf-8"))
    if len(definition.get("curated_inputs", [])) != V81_INPUT_COUNT:
        raise OfficialOceaniaGapError("accepted v81 input count differs")
    selected = {row["path"] for row in definition["curated_inputs"]}
    planned_paths = {f"sources/{name}" for name in SOURCE_FILENAMES}
    if selected & planned_paths:
        raise OfficialOceaniaGapError("v81 unexpectedly selects a new source path")
    _v81_duplicate_witness()


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise OfficialOceaniaGapError(f"capture directory is absent or unsafe: {directory}")
    entries = list(directory.iterdir())
    if len(entries) != CAPTURE_FILE_COUNT:
        raise OfficialOceaniaGapError("capture directory file count differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise OfficialOceaniaGapError("capture directory contains a non-file")
    if sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES:
        raise OfficialOceaniaGapError("capture directory total bytes differs")
    if tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise OfficialOceaniaGapError("capture directory tree differs")
    if set(CAPTURE_FILE_PINS) != {entry.name for entry in entries}:
        raise OfficialOceaniaGapError("capture directory closed set differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(directory / name, pin)


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory() as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for name in SOURCE_FILENAMES:
            adapter.import_file(connection, paths[name], recorded_at=recorded_at)
        validate_database(connection)
        tables = ("entities", "entity_snapshots", "evidence", "lifecycle_observations", "operating_model_observations", "workload_observations", "capacity_estimates")
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
        expected = {"entities": 15, "entity_snapshots": 16, "evidence": 17, "lifecycle_observations": 8, "operating_model_observations": 1, "workload_observations": 0, "capacity_estimates": 1}
        if counts != expected:
            raise OfficialOceaniaGapError(f"offline import counts differ: {counts!r}")
        capacity = tuple(connection.execute("SELECT e.stable_key, c.metric, c.stage, c.unit, c.base FROM capacity_estimates AS c JOIN entities AS e ON e.id=c.entity_id").fetchone())
        if capacity != ("curated:gta-gu3-alupang-data-center:initial-build", "gross_facility_mw", "design", "MW", 4.0):
            raise OfficialOceaniaGapError(f"offline capacity row differs: {capacity!r}")
        return counts


def validate_artifact(path: Path = ARTIFACT, *, source_paths: Mapping[str, Path] | None = None, require_live: bool = True, wall_clock: datetime | None = None) -> dict[str, Any]:
    paths = source_paths or _source_paths(SOURCES_ROOT)
    source_records = _validate_sources(paths)
    if path.is_symlink() or not path.is_dir():
        raise OfficialOceaniaGapError("artifact must be an ordinary directory")
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise OfficialOceaniaGapError("artifact closed file set differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries.values()):
        raise OfficialOceaniaGapError("artifact contains a non-ordinary file")
    if stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise OfficialOceaniaGapError("artifact directory mode differs")
    if any(stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries.values()):
        raise OfficialOceaniaGapError("artifact file mode differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest):
        raise OfficialOceaniaGapError("manifest JSON is not canonical")
    if manifest.get("artifact_id") != ARTIFACT_ID or set(manifest.get("closed_file_set", [])) != CLOSED_FILES or manifest.get("candidate_assessments") != 25 or manifest.get("curated_source_records") != 8 or manifest.get("seed_eligible_source_records") != 8 or manifest.get("review_only_candidates") != 17 or manifest.get("regional_completeness_claimed") is not False or manifest.get("open_seed_successor_created") is not False or manifest.get("release_integration") != "none" or _file_tree(manifest["files"]) != manifest.get("tree_sha256"):
        raise OfficialOceaniaGapError("manifest contract differs")
    if [row["path"] for row in manifest["files"]] != list(CONTENT_FILES):
        raise OfficialOceaniaGapError("manifest file order differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (row["bytes"], row["sha256"]):
            raise OfficialOceaniaGapError(f"manifest file pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != f"{_sha256_bytes(manifest_raw)}  manifest.json\n":
        raise OfficialOceaniaGapError("manifest checksum differs")
    expected = _artifact_documents(manifest["recorded_at"], expected_source_documents())
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected[name]:
            raise OfficialOceaniaGapError(f"artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records:
        raise OfficialOceaniaGapError("artifact source pins differ")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise OfficialOceaniaGapError("validation wall clock lacks timezone")
    if require_live:
        if now.astimezone(UTC) < target:
            raise OfficialOceaniaGapError("artifact recorded_at is not live")
        _assert_final_ctimes((*paths.values(), path), target)
    for capture in CAPTURES.values():
        if _instant(capture["retrieved_at"]) > target:
            raise OfficialOceaniaGapError("capture retrieval post-dates recorded_at")
    return manifest


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise OfficialOceaniaGapError(f"active publication lock exists: {PUBLICATION_LOCK}") from error
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
    return (source_stage, *sorted(source_stage.iterdir(), key=lambda item: item.name), artifact_stage, *sorted(artifact_stage.iterdir(), key=lambda item: item.name))


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
        raise OfficialOceaniaGapError("recorded_at must be future before staging")
    source_stage = Path(tempfile.mkdtemp(prefix=".official-builds-oceania-gap.", dir=SOURCES_ROOT))
    artifact_stage = Path(tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT))
    source_stage_identity = _identity(source_stage, directory=True)
    artifact_identity = _identity(artifact_stage, directory=True)
    try:
        documents = expected_source_documents()
        _write_source_stage(source_stage, documents)
        _write_artifact_stage(artifact_stage, recorded_at, documents)
        source_paths = _source_paths(source_stage)
        _validate_sources(source_paths)
        _offline_import(source_paths, recorded_at)
        validate_artifact(artifact_stage, source_paths=source_paths, require_live=False, wall_clock=datetime.now(UTC))
        finals = tuple(SOURCES_ROOT / name for name in SOURCE_FILENAMES) + (ARTIFACT,)
        _require_finals_absent(finals, "staging")
        _assert_stage_precedes_target(_all_stage_paths(source_stage, artifact_stage), target)
        if datetime.now(UTC) >= target:
            raise OfficialOceaniaGapError("private staging did not finish before recorded_at")
        return _PreparedPublication(
            recorded_at=recorded_at,
            target=target,
            source_stage=source_stage,
            source_stage_identity=source_stage_identity,
            source_identities={name: _identity(source_stage / name, directory=False) for name in SOURCE_FILENAMES},
            artifact_stage=artifact_stage,
            artifact_identity=artifact_identity,
            artifact_member_identities={name: _identity(artifact_stage / name, directory=False) for name in CLOSED_FILES},
        )
    except BaseException as primary_error:
        try:
            if artifact_stage.exists():
                members = {entry.name: _identity(entry, directory=False) for entry in artifact_stage.iterdir()}
                _discard_owned_directory(artifact_stage, artifact_identity, members)
            if source_stage.exists():
                members = {entry.name: _identity(entry, directory=False) for entry in source_stage.iterdir()}
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
    _assert_stage_precedes_target(_all_stage_paths(prepared.source_stage, prepared.artifact_stage), prepared.target)
    promoted: list[tuple[Path, Path, tuple[int, int], bool]] = []
    try:
        for name in SOURCE_FILENAMES:
            stage = prepared.source_stage / name
            final = final_sources[name]
            identity = prepared.source_identities[name]
            _promote_noreplace(stage, final)
            promoted.append((stage, final, identity, False))
            if not _has_identity(final, identity, directory=False):
                raise OfficialOceaniaGapError(f"source identity changed on promotion: {name}")
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        promoted.append((prepared.artifact_stage, ARTIFACT, prepared.artifact_identity, True))
        if not _has_identity(ARTIFACT, prepared.artifact_identity, directory=True):
            raise OfficialOceaniaGapError("artifact identity changed on promotion")
        _assert_final_ctimes(finals, prepared.target)
    except BaseException as primary_error:
        try:
            _rollback_promotions(promoted)
        except Exception as rollback_error:
            primary_error.add_note(f"identity-safe rollback failed: {rollback_error}")
        raise


def _cleanup_prepared(prepared: _PreparedPublication) -> None:
    if prepared.artifact_stage.exists():
        _discard_owned_directory(prepared.artifact_stage, prepared.artifact_identity, prepared.artifact_member_identities)
    if prepared.source_stage.exists():
        _discard_owned_directory(prepared.source_stage, prepared.source_stage_identity, prepared.source_identities)


def _move_capture_to_trash() -> None:
    if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
        raise OfficialOceaniaGapError("both capture origin and Trash destination exist")
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(CAPTURE_TRASH)


def _default_recorded_at() -> str:
    target = math.ceil(time.time() + 25.0)
    return datetime.fromtimestamp(target, UTC).isoformat().replace("+00:00", "Z")


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    """Publish eight source records and the full bounded candidate assessment."""

    target_text = recorded_at or _default_recorded_at()
    finals = tuple(SOURCES_ROOT / name for name in SOURCE_FILENAMES) + (ARTIFACT,)
    _require_finals_absent(finals, "initial")
    _validate_source_collisions()
    _validate_v81_nonmutation()
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
            _discard_owned_directory(prepared.source_stage, prepared.source_stage_identity, prepared.source_identities)
    _validate_capture_directory(CAPTURE_TRASH)
    _validate_v81_nonmutation()
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
            "candidates": 25,
            "source_records": 8,
            "seed_eligible": 8,
            "review_only": 17,
            "evidence": 17,
            "entities": 15,
            "lifecycle": 8,
            "operating_models": 1,
            "workloads": 0,
            "capacities": 1,
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
