"""Build, but never publish, three governed Nordic official-source candidates.

The tranche contains XTX Markets' second Kajaani data center, Skygard OSL1
phase 2, and an evidence/currentness successor for the existing atNorth FIN04
phase-1 record.  It deliberately has no publisher or promotion function: all
outputs remain private staging directories until a later, separately reviewed
integration tranche.

Power, efficiency, energy, and phase boundaries are strict.  The first XTX
facility's 22.5 MW is not copied to the second facility; OSL1's whole-facility
20 MW and PUE are not allocated to phase 2; FIN04's 430 MW remains untyped
entire-campus metadata.  No coordinate, geometry, map-derived address, or
imagery claim is emitted.
"""

from __future__ import annotations

import copy
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

from .external_captures import resolve_external_capture
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "official-nordic-tranche-prepublication-2026-07-22-v1"
PROSPECTIVE_ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID

XTX_SOURCE_FILENAME = (
    "curated-official-2026-07-22-xtx-kajaani-second-data-center-current-build.json"
)
SKYGARD_SOURCE_FILENAME = (
    "curated-official-2026-07-22-skygard-osl1-phase-2-current-build.json"
)
FIN04_SOURCE_FILENAME = (
    "curated-official-2026-07-22-atnorth-fin04-kouvola-currentness-successor.json"
)
SOURCE_FILENAMES = (
    XTX_SOURCE_FILENAME,
    SKYGARD_SOURCE_FILENAME,
    FIN04_SOURCE_FILENAME,
)

FIN04_PREDECESSOR_FILENAME = "curated-official-2026-07-20-atnorth-fin04-kouvola.json"
FIN04_PREDECESSOR = SOURCES_ROOT / FIN04_PREDECESSOR_FILENAME
FIN04_PREDECESSOR_PIN = (
    15_068,
    "28773caea4d839386074e6bd3003953c75c9f1bbd3441442a83cfc2d9ca22fe4",
)

V94_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v94.json"
V94_ENTITIES = ROOT / "releases/2026-07-21-open-seed-v94/entities.csv"
V94_DEFINITION_PIN = (
    113_819,
    "c65f61b3708b4cdc1fb755eaf8d0edffab545526f206689e66056220b27cc0ff",
)
V94_ENTITIES_PIN = (
    1_044_783,
    "87d2320671a5773c8d7619be972b5434f82adb12a28f3afe383e2e1bd63605f4",
)

CAPTURE_ORIGIN = Path("/private/tmp/dc-nordic-prepublication-20260722.jN0cUf")
CAPTURE_FILE_COUNT = 12
CAPTURE_TOTAL_BYTES = 436_607
CAPTURE_TREE_SHA256 = "2021d6ee7a32bf90bc20e6a682b734498fae741df861b856fd755e693965747b"

CAPTURE_FILE_PINS: Mapping[str, tuple[int, str]] = {
    "bravida_xtx_second.body": (
        130_064,
        "329255a4ef7a244fe22b03178821a7eec5f85cda2c3feafe75ebdc975d0b8cb2",
    ),
    "bravida_xtx_second.headers": (
        624,
        "9351687ac1278d74b418fb3d862c69e77104c21fd28c44434a09402acdfe5dd0",
    ),
    "bravida_xtx_second_en.body": (
        85_270,
        "a72ca5eb8725b7434d75bb981b9bee986b1ed653d696a12d842af17d239f2a56",
    ),
    "bravida_xtx_second_en.headers": (
        626,
        "61280303d145c443ff2748186040b8d9d198059c80e20ce0b483eeb9ea6759ec",
    ),
    "sentia_osl1_phase2.body": (
        70_814,
        "7448563a29b0e39cf807f6409a1efe7d7dfd90a92daef928651dfe9dcbe34228",
    ),
    "sentia_osl1_phase2.headers": (
        889,
        "2ba20a0fafa6feebc1d2c3dba25a2f436104a016b632c8767902050972081fa4",
    ),
    "skygard_osl1.body": (
        73_223,
        "e0a4fe00766c87ed0956ee59dc12ef5c5d36003552f032d8659acbfded59d365",
    ),
    "skygard_osl1.headers": (
        1_770,
        "fc9bd70ac2d2e0ef914fbc0b2f85358ccdeaa03ade555ccaba08b124d9f612ec",
    ),
    "xtx_kajaani.body": (
        8_586,
        "926369fbc769f468b35c610eba38421fec2b5692174d1aa2fdd9cb6bf981cfb4",
    ),
    "xtx_kajaani.headers": (
        583,
        "0111650138806c03f90c7669f9379084793c058855fc3fb5fb10c3529745a49f",
    ),
    "yit_atnorth_fin04.body": (
        62_648,
        "678a6298ce048e09e42c2e8aa416217f0ec05124e0ec4d25002ec4063df4f1b6",
    ),
    "yit_atnorth_fin04.headers": (
        1_510,
        "fc6f4ea6d0c761d6ae08c3847d1e68d4df9734154f6b2dc4742af3fdf3c8ac7a",
    ),
}

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
    published_at: str | None
    retrieved_at: str
    content_type: str
    claim_use: str


CAPTURES = (
    Capture(
        "xtx_kajaani",
        "xtx_kajaani",
        "https://files.xtxmarkets.com/publications/kajaani/index.html",
        "https://files.xtxmarkets.com/publications/kajaani/index.html",
        "XTX Markets",
        "2025-01-22T00:00:00Z",
        "2026-07-22T04:13:39Z",
        "text/html",
        "identity_and_phase_lineage_only",
    ),
    Capture(
        "bravida_xtx_second_en",
        "bravida_xtx_second_en",
        "https://www.bravida.se/en/press/press-releases/2026/"
        "bravida-finland-awarded-additional-installation-contract-for-xtx-"
        "markets-data-center-complex-in-kajaani/",
        "https://www.bravida.se/en/press/press-releases/2026/"
        "bravida-finland-awarded-additional-installation-contract-for-xtx-"
        "markets-data-center-complex-in-kajaani/",
        "Bravida",
        "2026-06-25T08:00:00+02:00",
        "2026-07-22T04:15:21Z",
        "text/html; charset=utf-8",
        "normalized_second_facility_status_and_roles",
    ),
    Capture(
        "bravida_xtx_second_fi",
        "bravida_xtx_second",
        "https://www.bravida.fi/lehdisto/uutiset/2026/"
        "bravida-finlandille-lisaurakka-xtx-marketsin-"
        "datakeskuskokonaisuuteen-kajaanissa/",
        "https://www.bravida.fi/lehdisto/uutiset/2026/"
        "bravida-finlandille-lisaurakka-xtx-marketsin-"
        "datakeskuskokonaisuuteen-kajaanissa/",
        "Bravida",
        "2026-06-25T08:49:22+02:00",
        "2026-07-22T04:14:04Z",
        "text/html; charset=utf-8",
        "same_publisher_local_language_duplicate_verification_only",
    ),
    Capture(
        "sentia_osl1_phase2",
        "sentia_osl1_phase2",
        "https://www.sentiagruppen.no/press/"
        "hent-inngar-kontrakt-pa-byggetrinn-2-osl1-datasenter-pa-okern",
        "https://www.sentiagruppen.no/press/"
        "hent-inngar-kontrakt-pa-byggetrinn-2-osl1-datasenter-pa-okern",
        "Sentia",
        "2026-06-16T11:15:00+02:00",
        "2026-07-22T04:14:05Z",
        "text/html; charset=utf-8",
        "normalized_phase_2_construction_start_and_roles",
    ),
    Capture(
        "skygard_osl1",
        "skygard_osl1",
        "https://www.skygard.no/osl1-eng",
        "https://www.skygard.no/osl1-eng",
        "Skygard",
        None,
        "2026-07-22T04:14:04Z",
        "text/html; charset=utf-8",
        "first_party_identity_and_whole_facility_metric_scope_only",
    ),
    Capture(
        "yit_atnorth_fin04",
        "yit_atnorth_fin04",
        "https://www.yitgroup.com/en/news-repository/investor-news/"
        "yit-and-atnorth-agree-on-construction-of-a-data-center-in-kouvola--"
        "value-for-yit-approximately-eur-300-million",
        "https://www.yitgroup.com/en/news-repository/investor-news/"
        "yit-and-atnorth-agree-on-construction-of-a-data-center-in-kouvola--"
        "value-for-yit-approximately-eur-300-million",
        "YIT",
        "2026-07-21T12:00:00+03:00",
        "2026-07-22T04:14:04Z",
        "text/html; charset=utf-8",
        "fin04_existing_phase_currentness_successor_only",
    ),
)
CAPTURE_BY_ID = {capture.capture_id: capture for capture in CAPTURES}

XTX_CAMPUS_KEY = "curated:xtx-markets-kajaani-data-center-campus"
XTX_PROJECT_KEY = f"{XTX_CAMPUS_KEY}:second-data-center"
SKYGARD_CAMPUS_KEY = "curated:skygard-osl1-hovinbyen-campus"
SKYGARD_PROJECT_KEY = f"{SKYGARD_CAMPUS_KEY}:phase-2"
FIN04_CAMPUS_KEY = "curated:atnorth-fin04-kouvola-campus"
FIN04_PROJECT_KEY = f"{FIN04_CAMPUS_KEY}:phase-1"

XTX_IDENTITY_EVIDENCE_KEY = (
    "xtx-kajaani-campus-first-and-four-further-2025-01-22-captured-2026-07-22"
)
XTX_SECOND_EVIDENCE_KEY = (
    "bravida-xtx-kajaani-second-work-underway-2026-06-25-captured-2026-07-22"
)
SKYGARD_IDENTITY_EVIDENCE_KEY = (
    "skygard-osl1-hovinbyen-current-page-captured-2026-07-22"
)
SKYGARD_PHASE2_EVIDENCE_KEY = (
    "sentia-hent-osl1-phase-2-immediate-start-2026-06-16-captured-2026-07-22"
)
FIN04_YIT_EVIDENCE_KEY = (
    "yit-atnorth-fin04-immediate-construction-2026-07-21-captured-2026-07-22"
)


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
            "credential_free_curl_fail_location_compressed_desktop_user_agent"
        ),
        "requested_url": capture.requested_url,
        "effective_url": capture.effective_url,
        "request_credentials_supplied": False,
        "http_status": 200,
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
            "map widget, geocoder, analyst coordinate, or inferred address contributes."
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
        "confidence": 0.99,
    }


def _xtx_document() -> dict[str, Any]:
    identity = _evidence(
        key=XTX_IDENTITY_EVIDENCE_KEY,
        capture_id="xtx_kajaani",
        title=(
            "XTX Markets plans to invest over €1bn in large-scale data centre "
            "project in Finland"
        ),
        excerpt=(
            "XTX identifies its Kajaani campus, says construction had begun on "
            "the first data center, and describes four additional intended data centers."
        ),
        source_family="xtx_markets_official_kajaani_release",
        metadata={
            "identity_scope": (
                "XTX Markets, one owned site in Kajaani, first data center plus "
                "four additional intended data centers."
            ),
            "first_facility_metrics_not_inherited": {
                "floor_area_sqm": 15_000,
                "data_halls": 3,
                "it_power_mw": 22.5,
                "scope": "first_data_center_only",
                "second_facility_capacity_row_created": False,
            },
            "first_facility_workload_not_inherited": (
                "The own-compute and machine-learning statements describe the first "
                "facility in this release. They create no second-facility workload row."
            ),
            "future_facility_guardrail": (
                "Intent to seek planning permission and build four more facilities "
                "is not a permit, construction start, physical observation, or current status."
            ),
        },
    )
    second = _evidence(
        key=XTX_SECOND_EVIDENCE_KEY,
        capture_id="bravida_xtx_second_en",
        title=(
            "Bravida Finland awarded additional installation contract for XTX "
            "Markets' data center complex in Kajaani"
        ),
        excerpt=(
            "Bravida identifies the second data center on XTX Markets' Kajaani "
            "campus and says its work for that facility is already underway."
        ),
        source_family="bravida_official_press_release",
        metadata={
            "physical_status_as_reported": (
                "Bravida's work for the second data center is already underway."
            ),
            "normalized_lifecycle": "under_construction",
            "scope_as_reported": (
                "server-hall electrical installations and process electricity"
            ),
            "roles_as_reported": {
                "developer": "XTX Markets",
                "main_contractor": "YIT",
                "electrical_contractor": "Bravida Finland",
            },
            "schedule_not_status": (
                "Expected completion in 2027 is forward-looking and does not "
                "establish completion, commissioning, energization, or operation."
            ),
            "power_metric_guardrail": (
                "This second-facility release states no MW value. The first "
                "facility's 22.5 MW IT-power figure is not copied or allocated."
            ),
            "same_publisher_finnish_capture": {
                "capture_id": "bravida_xtx_second_fi",
                "body_sha256": CAPTURE_FILE_PINS["bravida_xtx_second.body"][1],
                "independent_corroboration": False,
                "normalized_as_separate_evidence": False,
            },
        },
    )
    return {
        "schema_version": "1.1",
        "evidence": [identity, second],
        "campus": _entity(
            stable_key=XTX_CAMPUS_KEY,
            name="XTX Markets Kajaani Data Center Campus",
            country="Finland",
            address="Kajaani, Finland",
            roles={"developer": ["XTX Markets"]},
            evidence_key=XTX_SECOND_EVIDENCE_KEY,
            as_of_date="2026-06-25",
        ),
        "project": _entity(
            stable_key=XTX_PROJECT_KEY,
            name="XTX Markets Kajaani Second Data Center",
            country="Finland",
            address="Kajaani, Finland",
            roles={
                "developer": ["XTX Markets"],
                "contractor": ["YIT", "Bravida Finland"],
            },
            evidence_key=XTX_SECOND_EVIDENCE_KEY,
            as_of_date="2026-06-25",
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": XTX_SECOND_EVIDENCE_KEY,
                "as_of_date": "2026-06-25",
                "method": "authoritative_physical_status_update",
                "confidence": 0.99,
            }
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _skygard_document() -> dict[str, Any]:
    identity = _evidence(
        key=SKYGARD_IDENTITY_EVIDENCE_KEY,
        capture_id="skygard_osl1",
        title="Skygard OSL1",
        excerpt=(
            "Skygard identifies OSL1 in Hovinbyen, Oslo and reports whole-OSL1 "
            "facility specifications."
        ),
        source_family="skygard_official_facility_page",
        metadata={
            "identity_scope": "OSL1, Hovinbyen, Oslo",
            "whole_facility_metrics_not_phase_allocated": {
                "capacity_mw": 20,
                "pue_as_reported": "~1.2 and <1.2 average",
                "scope": "OSL1_whole_facility_only",
                "phase_2_capacity_row_created": False,
                "phase_2_pue_row_created": False,
            },
            "energy_guardrail": (
                "Renewable-power access and heat-recovery descriptions are design "
                "or availability statements, not measured consumption or annual energy."
            ),
            "address_guardrail": (
                "Only Hovinbyen, Oslo is retained. The page's distance statements, "
                "map targets, and any geocoded street address are not used."
            ),
        },
    )
    phase_2 = _evidence(
        key=SKYGARD_PHASE2_EVIDENCE_KEY,
        capture_id="sentia_osl1_phase2",
        title="HENT enters contract for construction phase 2, OSL1 at Økern",
        excerpt=(
            "Sentia says HENT contracted with Skygard for OSL1 phase 2, the "
            "remaining development, and that construction starts immediately."
        ),
        source_family="sentia_official_press_release",
        metadata={
            "identity_and_phase_scope": (
                "OSL1 at Økern in Oslo; construction phase 2; remaining development "
                "after HENT handed over phase 1 in April 2026."
            ),
            "physical_status_as_reported": "Construction start is immediate.",
            "normalized_lifecycle": "under_construction",
            "physical_scope": (
                "building works and basic building-technical installations for "
                "approximately 12,000 square metres"
            ),
            "mep_scope_guardrail": (
                "Data-center-function MEP is explicitly excluded from HENT's "
                "contract; no MEP-electrical lifecycle status is inferred."
            ),
            "phase_1_guardrail": (
                "The April 2026 phase-1 handover is retained as context only. This "
                "tranche creates no phase-1 entity, completion, or operation row."
            ),
            "publication_timestamp_guardrail": (
                "The page visibly reports 16.06.26 at 11:15. Its HTML time element "
                "contains an inconsistent 2025-04-23 datetime, which is not used."
            ),
            "schedule_guardrail": (
                "Planned completion during 2027 is forward-looking and does not "
                "establish completion, commissioning, energization, or operation."
            ),
        },
    )
    return {
        "schema_version": "1.1",
        "evidence": [identity, phase_2],
        "campus": _entity(
            stable_key=SKYGARD_CAMPUS_KEY,
            name="Skygard OSL1 Hovinbyen Campus",
            country="Norway",
            address="Hovinbyen, Oslo, Norway",
            roles={"operator": ["Skygard"]},
            evidence_key=SKYGARD_IDENTITY_EVIDENCE_KEY,
            as_of_date="2026-07-22",
        ),
        "project": _entity(
            stable_key=SKYGARD_PROJECT_KEY,
            name="Skygard OSL1 Phase 2",
            country="Norway",
            address="Hovinbyen, Oslo, Norway",
            roles={"operator": ["Skygard"], "contractor": ["HENT"]},
            evidence_key=SKYGARD_PHASE2_EVIDENCE_KEY,
            as_of_date="2026-06-16",
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": SKYGARD_PHASE2_EVIDENCE_KEY,
                "as_of_date": "2026-06-16",
                "method": "authoritative_construction_start",
                "confidence": 0.99,
            }
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _load_fin04_predecessor() -> dict[str, Any]:
    _pin(FIN04_PREDECESSOR, FIN04_PREDECESSOR_PIN)
    document = json.loads(FIN04_PREDECESSOR.read_text(encoding="utf-8"))
    if (
        document.get("campus", {}).get("stable_key") != FIN04_CAMPUS_KEY
        or document.get("project", {}).get("stable_key") != FIN04_PROJECT_KEY
        or document.get("schema_version") != "1.0"
    ):
        raise RuntimeError("FIN04 predecessor identity/schema differs")
    return document


def _fin04_document() -> dict[str, Any]:
    predecessor = copy.deepcopy(_load_fin04_predecessor())
    yit = _evidence(
        key=FIN04_YIT_EVIDENCE_KEY,
        capture_id="yit_atnorth_fin04",
        title=("YIT and atNorth agree on construction of a data center in Kouvola"),
        excerpt=(
            "YIT says the contracted data center forms part of atNorth's FIN04 "
            "campus and that construction will begin immediately."
        ),
        source_family="yit_official_investor_news",
        metadata={
            "successor_scope": (
                "Currentness and contractor evidence for the already represented "
                "FIN04 phase-1 project only; no new phase or facility identity is created."
            ),
            "phase_guardrail": (
                "YIT calls it a new data center forming part of FIN04 but gives no "
                "phase number. The existing phase-1 stable key is retained; no "
                "additional phase is inferred."
            ),
            "physical_status_as_reported": "Construction will begin immediately.",
            "contract_scope": "design, CSA, MEP, and commissioning works",
            "role_as_reported": "YIT comprehensive design-build contractor",
            "entire_campus_capacity_not_normalized": {
                "value": 430,
                "unit": "MW",
                "source_wording": "planned total capacity of the entire campus",
                "typing": "untyped_entire_campus_planning_metadata_only",
                "project_capacity_row_created": False,
                "campus_capacity_row_created": False,
            },
            "energy_guardrail": (
                "Renewable-energy operation and excess-heat reuse capability are "
                "forward-looking design statements, not measured consumption, "
                "annual MWh, PUE, generation, grid draw, or renewable share."
            ),
            "workload_guardrail": (
                "AI and HPC appear in a demand statement, not as an installed "
                "workload, tenant, customer, user, or active compute observation."
            ),
            "schedule_guardrail": (
                "Expected completion by end-2027 does not establish completion, "
                "commissioning, energization, occupancy, or operation."
            ),
            "predecessor": {
                "path": f"sources/{FIN04_PREDECESSOR_FILENAME}",
                "bytes": FIN04_PREDECESSOR_PIN[0],
                "sha256": FIN04_PREDECESSOR_PIN[1],
            },
        },
    )
    predecessor["schema_version"] = "1.1"
    predecessor["evidence"].append(yit)
    predecessor["campus"]["evidence_key"] = FIN04_YIT_EVIDENCE_KEY
    predecessor["campus"]["as_of_date"] = "2026-07-21"
    predecessor["project"]["evidence_key"] = FIN04_YIT_EVIDENCE_KEY
    predecessor["project"]["as_of_date"] = "2026-07-21"
    predecessor["project"]["roles"] = {
        "developer": ["atNorth"],
        "contractor": ["YIT"],
    }
    predecessor["lifecycle"] = [
        {
            "entity": "project",
            "value": "under_construction",
            "evidence_key": FIN04_YIT_EVIDENCE_KEY,
            "as_of_date": "2026-07-21",
            "method": "authoritative_physical_status_update",
            "confidence": 0.99,
        }
    ]
    predecessor["operating_models"] = []
    predecessor["workloads"] = []
    predecessor["capacities"] = []
    return predecessor


def expected_source_documents() -> dict[str, dict[str, Any]]:
    return {
        XTX_SOURCE_FILENAME: _xtx_document(),
        SKYGARD_SOURCE_FILENAME: _skygard_document(),
        FIN04_SOURCE_FILENAME: _fin04_document(),
    }


def _validate_capture_directory(
    directory: Path | None = None,
) -> None:
    if directory is None:
        directory = resolve_external_capture(CAPTURE_ORIGIN)
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("private Nordic capture directory is missing or unsafe")
    entries = {path.name: path for path in directory.iterdir()}
    if set(entries) != set(CAPTURE_FILE_PINS):
        raise RuntimeError("private Nordic capture inventory differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(entries[name], pin)
        if stat.S_IMODE(entries[name].stat().st_mode) != 0o444:
            raise RuntimeError(f"private Nordic capture is not frozen: {name}")
    if sum(pin[0] for pin in CAPTURE_FILE_PINS.values()) != CAPTURE_TOTAL_BYTES:
        raise RuntimeError("private Nordic capture byte total differs")
    if tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise RuntimeError("private Nordic capture tree differs")


def _v94_witness() -> dict[str, Any]:
    _pin(V94_DEFINITION, V94_DEFINITION_PIN)
    _pin(V94_ENTITIES, V94_ENTITIES_PIN)
    _pin(FIN04_PREDECESSOR, FIN04_PREDECESSOR_PIN)
    definition = json.loads(V94_DEFINITION.read_text(encoding="utf-8"))
    selected = definition.get("curated_inputs")
    if not isinstance(selected, list) or len(selected) != 498:
        raise RuntimeError("v94 curated input inventory differs")
    predecessor_rows = [
        row
        for row in selected
        if row.get("path") == f"sources/{FIN04_PREDECESSOR_FILENAME}"
    ]
    if predecessor_rows != [
        {
            "path": f"sources/{FIN04_PREDECESSOR_FILENAME}",
            "sha256": FIN04_PREDECESSOR_PIN[1],
        }
    ]:
        raise RuntimeError("v94 FIN04 predecessor selection differs")
    with V94_ENTITIES.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    stable_keys = {row["stable_key"] for row in rows}
    new_keys = {
        XTX_CAMPUS_KEY,
        XTX_PROJECT_KEY,
        SKYGARD_CAMPUS_KEY,
        SKYGARD_PROJECT_KEY,
    }
    existing_keys = {FIN04_CAMPUS_KEY, FIN04_PROJECT_KEY}
    if new_keys & stable_keys:
        raise RuntimeError("new Nordic keys collide with v94")
    if not existing_keys <= stable_keys:
        raise RuntimeError("FIN04 successor keys are absent from v94")
    return {
        "v94_selected_input_count": len(selected),
        "v94_entity_count": len(rows),
        "fin04_predecessor_selected_once": True,
        "fin04_predecessor_pin": {
            "path": f"sources/{FIN04_PREDECESSOR_FILENAME}",
            "bytes": FIN04_PREDECESSOR_PIN[0],
            "sha256": FIN04_PREDECESSOR_PIN[1],
        },
        "new_stable_keys_absent": sorted(new_keys),
        "existing_stable_keys_reused": sorted(existing_keys),
        "new_phase_created_for_fin04": False,
    }


def _source_records(
    documents: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    dispositions = {
        XTX_SOURCE_FILENAME: "prepublication_second_facility_current_build",
        SKYGARD_SOURCE_FILENAME: "prepublication_phase_2_current_build",
        FIN04_SOURCE_FILENAME: "prepublication_existing_phase_currentness_successor",
    }
    countries = {
        XTX_SOURCE_FILENAME: "Finland",
        SKYGARD_SOURCE_FILENAME: "Norway",
        FIN04_SOURCE_FILENAME: "Finland",
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
                "candidate_id": "xtx-kajaani-second-data-center",
                "decision": "governed_prepublication_current_build_candidate",
                "source_paths": [f"prospective-sources/{XTX_SOURCE_FILENAME}"],
                "campus_stable_key": XTX_CAMPUS_KEY,
                "project_stable_key": XTX_PROJECT_KEY,
                "lifecycle": "under_construction",
                "as_of_date": "2026-06-25",
                "first_facility_22_5_mw_inherited": False,
                "capacity_claim_created": False,
                "workload_claim_created": False,
                "coordinate_claim_created": False,
                "geometry_claim_created": False,
            },
            {
                "candidate_id": "xtx-kajaani-third-data-center",
                "decision": "review_only_future_intent_no_physical_start",
                "source_paths": [],
                "stable_key_created": False,
                "lifecycle_claim_created": False,
                "capacity_claim_created": False,
                "reason": (
                    "XTX's 2025 release states intent to seek planning permission "
                    "and build four additional facilities. No official evidence in "
                    "this capture set establishes third-facility construction."
                ),
            },
            {
                "candidate_id": "skygard-osl1-phase-2",
                "decision": "governed_prepublication_current_build_candidate",
                "source_paths": [f"prospective-sources/{SKYGARD_SOURCE_FILENAME}"],
                "campus_stable_key": SKYGARD_CAMPUS_KEY,
                "project_stable_key": SKYGARD_PROJECT_KEY,
                "lifecycle": "under_construction",
                "as_of_date": "2026-06-16",
                "whole_osl1_20_mw_allocated_to_phase_2": False,
                "whole_osl1_pue_allocated_to_phase_2": False,
                "capacity_claim_created": False,
                "coordinate_claim_created": False,
                "geometry_claim_created": False,
            },
            {
                "candidate_id": "atnorth-fin04-currentness-successor",
                "decision": "governed_prepublication_existing_phase_successor",
                "source_paths": [f"prospective-sources/{FIN04_SOURCE_FILENAME}"],
                "campus_stable_key": FIN04_CAMPUS_KEY,
                "project_stable_key": FIN04_PROJECT_KEY,
                "lifecycle": "under_construction",
                "as_of_date": "2026-07-21",
                "new_phase_created": False,
                "entire_campus_430_mw_normalized": False,
                "capacity_claim_created": False,
                "energy_consumption_claim_created": False,
                "coordinate_claim_created": False,
                "geometry_claim_created": False,
                "predecessor_sha256": FIN04_PREDECESSOR_PIN[1],
            },
        ],
    }


def _retrieval_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "controlled_capture_count": len(CAPTURES),
        "successful_http_200_body_captures": len(CAPTURES),
        "normalized_claim_capture_count": 5,
        "same_publisher_duplicate_verification_capture_count": 1,
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
                "effective_url": capture.effective_url,
                "published_at": capture.published_at,
                "retrieved_at": capture.retrieved_at,
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
    witness = _v94_witness()
    readme = f"""# Nordic official-source tranche — prepublication only

This governed candidate artifact was built at {recorded_at} and was not published. It contains private staged candidates for XTX Markets' second Kajaani data center, Skygard OSL1 phase 2, and a currentness/evidence successor for the existing atNorth FIN04 phase-1 record.

The normalized output is six entity snapshots, three `under_construction` lifecycle rows, eight evidence rows, and zero operating-model, workload, capacity, coordinate, or geometry rows. XTX's 22.5 MW belongs only to its first Kajaani facility and is not copied to the second. Skygard's 20 MW and PUE statements describe OSL1 as a whole and are not allocated to phase 2. YIT's 430 MW is planned total capacity for the entire FIN04 campus and remains untyped metadata. Renewable-power, heat-reuse, AI, and HPC language creates no consumption, annual-energy, efficiency, workload, tenant, or active-compute row.

XTX's third Kajaani data center remains review-only because the first-party release states only future intent for additional facilities. FIN04 reuses the exact existing campus and phase-1 stable keys and preserves the predecessor's three evidence records; YIT adds currentness and contractor evidence without creating another phase. Skygard's official OSL1 page supplies first-party identity/locality only, while Sentia's dated phase-2 release supplies the construction-start observation. No Google Maps, street address, coordinate, imagery, satellite, aerial, or computer-vision inference contributes.

The builder exposes no publication or promotion function. The three candidate source files and this artifact remain mode-0600/mode-0700 staging paths. No final source path, source-artifact path, open-seed successor, release, federation, identity, construction-master, map, coverage, or v95 file is created or changed.
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
            "new_entities_against_v94": 4,
            "reused_existing_entities": 2,
            "evidence_records": 8,
            "lifecycle_observations": 3,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
            "coordinate_observations": 0,
            "geometry_observations": 0,
            "satellite_observations": 0,
        },
        "v94_predecessor_and_collision_witness": witness,
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
            "v95_files_touched": [],
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
        prefix="nordic-prepublication-import-", dir="/private/tmp"
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
            "evidence": 8,
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
        raise RuntimeError("Nordic staged source inventory differs")
    for name in SOURCE_FILENAMES:
        path = paths[name]
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"missing or unsafe staged source: {name}")
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise RuntimeError(f"staged source mode differs: {name}")
        if path.read_bytes() != _canonical(expected[name]):
            raise RuntimeError(f"staged source differs: {name}")
    first = _offline_import(paths, "2026-07-22T04:20:00Z")
    second = _offline_import(paths, "2026-07-22T04:20:00Z")
    if first != second:
        raise RuntimeError("Nordic offline replay differs")
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
    third = next(
        row
        for row in assessment["candidates"]
        if row["candidate_id"] == "xtx-kajaani-third-data-center"
    )
    if third["source_paths"] or third["stable_key_created"]:
        raise RuntimeError("XTX third-facility review boundary differs")
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
    _v94_witness()
    documents = expected_source_documents()
    instant = recorded_at or datetime.now(UTC).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")
    source_stage = Path(
        tempfile.mkdtemp(
            prefix=".official-nordic-prepublication-sources.", dir=SOURCES_ROOT
        )
    )
    artifact_stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT)
    )
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
