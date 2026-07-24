"""Build and freeze official open seed v67 as the exact v66 successor.

V67 is the 2026-07-21 release-day view. It preserves the frozen 2026-07-20
Epoch capture and adds exactly fourteen schema-1.1 curated sources whose source
and capture lineage remains 2026-07-20. Lifecycle values remain dated,
last-observed facts and never become current-status claims.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import csv
from dataclasses import asdict
from datetime import date
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
from typing import Any, Iterator, Mapping

from .curated import CuratedOfficialSourceAdapter
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .epoch import EpochAIAdapter
from .open_seed_release_v10 import (
    OUT_OF_SCOPE_EXCLUSIONS,
    PENDING_NEXT_DAY_EXCLUSIONS,
    STALE_EXCLUSIONS,
    freshness_contract as base_freshness_contract,
)
from .open_seed_v56 import (
    canonical_json,
    discard_release_stage,
    promote_noreplace,
    sha256,
    tree_digest,
)
from .open_seed_v61 import FRESHNESS_FIELDS, FRESHNESS_FILENAME, build_freshness_csv
from .publication_release import build_release_documents
from .service import summarize, validate_database


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v66.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v66"
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v67.json"
RELEASE_ID = "2026-07-21-open-seed-v67"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v67.lock"

AS_OF = "2026-07-21"
RECORDED_AT = "2026-07-21T07:30:00Z"
V11_RECORDED_AT = RECORDED_AT
EPOCH_AS_OF = "2026-07-20"
SOURCE_LINEAGE_DATE = "2026-07-20"
STT_JOHOR_SOURCE = (
    "sources/curated-official-2026-07-20-stt-johor-1-current-build.json"
)

BASE_DEFINITION_SHA256 = (
    "c75d74fa6e1362c0a4fa2cb650c7a57a210c45caa578e51d84d77c36ed86e50d"
)
BASE_MANIFEST_SHA256 = (
    "b8df0f535df3d65efd675d3419b59c78638b21d67084a763550305a8d9005ea7"
)
BASE_TREE_SHA256 = "2ee1853cb92118ffc8422151173aa6c0bb7c768a870d890169f05a162d11969a"

FRESHNESS_README = (
    "`lifecycle_freshness.csv` treats every published lifecycle value as a "
    "last-observed historical fact, reports its age on the 2026-07-21 release "
    "date, and makes no current-construction inference. Its 0–90, 91–365, and "
    "over-365-day bands are review queues, not evidence that a status "
    "persisted. `current_status_classification` remains `unknown` and "
    "`current_construction_claim` remains `false` for every row, including the "
    "fourteen newly published project observations. Workload rows describe "
    "intended facility type only; they do not assert a current tenant, runtime, "
    "hardware, utilization, load, training, or inference workload. The frozen "
    "Epoch capture and all added source/capture identifiers retain their "
    "2026-07-20 lineage. Only Microsoft SYD06 contributes new coordinates."
)

ADDITION_PINS: dict[str, tuple[int, str]] = {
    "sources/curated-official-2026-07-20-sk-ai-data-center-ulsan.json": (
        8_727,
        "28c3e84fae1d949768da053f16209439bb694295c7629634d18e09e605a58bc9",
    ),
    "sources/curated-official-2026-07-20-dci-koramco-ansan-sel02.json": (
        10_874,
        "98ee45a625ee6366ff89676fa48b058a711dfd168efb83369cef618a784d5ae3",
    ),
    "sources/curated-official-2026-07-20-sify-bengaluru-02-current-build.json": (
        4_775,
        "ee6b6472e9a757239e19438f78c5b302d9761acc51dbe323e6b0bc4cb65e5203",
    ),
    "sources/curated-official-2026-07-20-datavolt-tashkent-green-data-center.json": (
        10_389,
        "ebe6f8e5456f51cc64f66e03a9e3db5d4b6c9cd07ce9596a8e027054f911cec3",
    ),
    "sources/curated-official-2026-07-20-datavolt-riyadh-first-phase.json": (
        5_184,
        "247f6daacd22f81c13aa5248d769165c416c5d35672c2c33a332a24158ceaac5",
    ),
    "sources/curated-official-2026-07-20-datavolt-yanbu-first-phase.json": (
        5_133,
        "893eb78ff834f507cb9cc05b9ca5ae1379f16ce4c3a2a35df96e19277b1e31d4",
    ),
    "sources/curated-official-2026-07-20-capitaland-navi-mumbai-tower-2.json": (
        8_319,
        "787c41abd758cecd9d91d08cbf975fd136a917ab39910537bcb11d3a4a757ac6",
    ),
    "sources/curated-official-2026-07-20-capitaland-chennai-ambattur.json": (
        8_353,
        "702e8eb7624998684e9afaeed4de4234ab5349c3b214cd52c141f022a854abad",
    ),
    "sources/curated-official-2026-07-20-stt-johor-1-current-build.json": (
        9_468,
        "785959fb2fb9962e1acefbd954ebb40b7d91305d180391c6311fc128c8899e7e",
    ),
    "sources/curated-official-2026-07-20-digital-edge-sel3-bupyeong.json": (
        12_604,
        "b8f6ff6a9cebe6630bf9757eb78c56af1cd63cd0b949c9f72615bb0ae44ff67b",
    ),
    "sources/curated-official-2026-07-20-smplus-smx01-jakarta-cbd.json": (
        19_150,
        "fce7c2103f43a97dd296874c602443829d747b836658e00d4b74eaa6a6ecdf9f",
    ),
    "sources/curated-official-2026-07-20-microsoft-kemps-creek-syd06-building-two.json": (
        15_323,
        "9268190e7851dc5b613baf11d4aee199a63487b1c19b2709863560f1b0f43818",
    ),
    "sources/curated-official-2026-07-20-aurora-core-mikkeli-phase-1.json": (
        13_241,
        "c9fdc17a73bd225cd31eaa19134375b5f6f0399993fd89bab1cecad11787ce6d",
    ),
    "sources/curated-official-2026-07-20-alps-duqm-under-construction.json": (
        10_312,
        "a7f6ef7e6474971b2f69663e0735814a38e26c866e708e966a364b853bfd9be8",
    ),
}

ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:alps-middle-east-duqm-data-center",
        "curated:alps-middle-east-duqm-data-center:initial-80mw-build",
        "curated:aurora-core-mikkeli-pellosniemi-ai-data-centre",
        "curated:aurora-core-mikkeli-pellosniemi-ai-data-centre:phase-1",
        "curated:capitaland-dc-chennai-ambattur",
        "curated:capitaland-dc-chennai-ambattur:current-facility-build",
        "curated:capitaland-dc-navi-mumbai-campus",
        "curated:capitaland-dc-navi-mumbai-campus:tower-2",
        "curated:datavolt-riyadh-16mw-liquid-cooled-facility",
        "curated:datavolt-riyadh-16mw-liquid-cooled-facility:first-phase",
        "curated:datavolt-tashkent-green-data-center",
        "curated:datavolt-tashkent-green-data-center:current-facility-build",
        "curated:datavolt-yanbu-4mw-facility",
        "curated:datavolt-yanbu-4mw-facility:first-phase",
        "curated:dci-koramco-ansan-sihwa-sel02-data-center",
        "curated:dci-koramco-ansan-sihwa-sel02-data-center:current-facility-build",
        "curated:digital-edge-seoul-bupyeong-campus",
        "curated:digital-edge-seoul-bupyeong-campus:sel3-phase-2",
        "curated:microsoft-kemps-creek-data-centre",
        "curated:microsoft-kemps-creek-data-centre:syd06-building-two",
        "curated:sify-bengaluru-02-data-center-campus",
        "curated:sify-bengaluru-02-data-center-campus:two-tower-current-build",
        "curated:sk-ai-data-center-ulsan-campus",
        "curated:sk-ai-data-center-ulsan-campus:current-facility-build",
        "curated:smplus-smx01-jakarta-cbd",
        "curated:smplus-smx01-jakarta-cbd:initial-18mw-build",
        "curated:stt-johor-data-centre-campus",
        "curated:stt-johor-data-centre-campus:stt-johor-1",
    }
)
ADDED_PROJECT_KEYS = frozenset(
    key for key in ADDED_ENTITY_KEYS if key.count(":") == 2
)

LIFECYCLE_WINNERS = {
    "curated:sk-ai-data-center-ulsan-campus:current-facility-build": (
        "under_construction",
        "2026-07-05",
    ),
    "curated:dci-koramco-ansan-sihwa-sel02-data-center:current-facility-build": (
        "under_construction",
        "2026-06-09",
    ),
    "curated:sify-bengaluru-02-data-center-campus:two-tower-current-build": (
        "under_construction",
        "2025-05-14",
    ),
    "curated:datavolt-tashkent-green-data-center:current-facility-build": (
        "under_construction",
        "2025-12-31",
    ),
    "curated:datavolt-riyadh-16mw-liquid-cooled-facility:first-phase": (
        "under_construction",
        "2025-12-31",
    ),
    "curated:datavolt-yanbu-4mw-facility:first-phase": (
        "under_construction",
        "2025-12-31",
    ),
    "curated:capitaland-dc-navi-mumbai-campus:tower-2": (
        "under_construction",
        "2025-12-31",
    ),
    "curated:capitaland-dc-chennai-ambattur:current-facility-build": (
        "under_construction",
        "2025-12-31",
    ),
    "curated:stt-johor-data-centre-campus:stt-johor-1": (
        "under_construction",
        "2025-02-24",
    ),
    "curated:digital-edge-seoul-bupyeong-campus:sel3-phase-2": (
        "under_construction",
        "2026-07-09",
    ),
    "curated:smplus-smx01-jakarta-cbd:initial-18mw-build": (
        "shell",
        "2026-05-08",
    ),
    "curated:microsoft-kemps-creek-data-centre:syd06-building-two": (
        "under_construction",
        "2026-05-01",
    ),
    "curated:aurora-core-mikkeli-pellosniemi-ai-data-centre:phase-1": (
        "civil_works",
        "2026-04-06",
    ),
    "curated:alps-middle-east-duqm-data-center:initial-80mw-build": (
        "under_construction",
        "2026-07-21",
    ),
}

CAPACITY_CONTRACT = {
    (
        "curated:capitaland-dc-chennai-ambattur:current-facility-build",
        "critical_it_mw",
        "planned",
        34.0,
        "2025-12-31",
    ),
    (
        "curated:capitaland-dc-chennai-ambattur:current-facility-build",
        "gross_facility_mw",
        "planned",
        53.0,
        "2025-12-31",
    ),
    (
        "curated:capitaland-dc-navi-mumbai-campus:tower-2",
        "critical_it_mw",
        "planned",
        37.0,
        "2025-12-31",
    ),
    (
        "curated:capitaland-dc-navi-mumbai-campus:tower-2",
        "gross_facility_mw",
        "planned",
        55.0,
        "2025-12-31",
    ),
    (
        "curated:stt-johor-data-centre-campus",
        "critical_it_mw",
        "planned",
        120.0,
        "2025-12-01",
    ),
    (
        "curated:stt-johor-data-centre-campus:stt-johor-1",
        "critical_it_mw",
        "planned",
        16.0,
        "2025-12-01",
    ),
    (
        "curated:digital-edge-seoul-bupyeong-campus:sel3-phase-2",
        "critical_it_mw",
        "planned",
        60.0,
        "2026-07-09",
    ),
    (
        "curated:smplus-smx01-jakarta-cbd:initial-18mw-build",
        "critical_it_mw",
        "planned",
        18.0,
        "2026-06-02",
    ),
    (
        "curated:alps-middle-east-duqm-data-center:initial-80mw-build",
        "gross_facility_mw",
        "planned",
        80.0,
        "2026-07-21",
    ),
}

WORKLOAD_CONTRACT = {
    (
        "curated:sk-ai-data-center-ulsan-campus:current-facility-build",
        "ai_specialized_unspecified",
        "2026-07-05",
        "company_disclosure",
    ),
    (
        "curated:dci-koramco-ansan-sihwa-sel02-data-center:current-facility-build",
        "ai_specialized_unspecified",
        "2026-06-11",
        "company_disclosure",
    ),
    (
        "curated:dci-koramco-ansan-sihwa-sel02-data-center:current-facility-build",
        "general_cloud",
        "2026-06-11",
        "company_disclosure",
    ),
}

SYD06_COORDINATE_KEYS = frozenset(
    {
        "curated:microsoft-kemps-creek-data-centre",
        "curated:microsoft-kemps-creek-data-centre:syd06-building-two",
    }
)

SHARED_EVIDENCE_COUNTS = {
    "datavolt-2025-milestones-linkedin-2025-12-31-captured-2026-07-20": 3,
    "capitaland-clint-fy2025-results-filing-captured-2026-07-20": 2,
    "capitaland-india-dc-fund-three-centres-2025-12-31-captured-2026-07-20": 2,
}

FRESHNESS_CLASS_TRANSITION = {
    "curated:bell-ai-fabric-sherwood-campus:saskatchewan-facility": (
        "recent_0_90_days",
        "aging_91_365_days",
    )
}

# Common, added, added hash, removed, removed hash against frozen v66.
CSV_DELTA_CONTRACT = {
    "entities.csv": (
        755,
        28,
        "7553339b2f987a4d33ff4a566be0e1ba6ed4b127dbfd8ef8d268782d22d82026",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "evidence.csv": (
        471,
        23,
        "237df2a3649a64fc786d9e00d2af6fbea5d9538128823b5ffccd0bdb241f8f14",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "capacity_estimates.csv": (
        512,
        9,
        "15e232f87f71b89ef5d1bcd7e6a167cb4372d8cda166b779ee05528bf1457af8",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_pipeline.csv": (
        387,
        14,
        "0e0fbb6eb31c0f1d6a18816024f4e32363482b17fb70efee041b8a0f46dfb22a",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_source_signals.csv": (
        292,
        11,
        "22dbb6277f931208ce3fbc8962327f7edc677973a7845756731cacb0e84cc7ce",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "resolution_candidates.csv": (
        6,
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "lifecycle_freshness.csv": (
        0,
        443,
        "e2f218ef7199f361adddf77ab3dbe43c1ff90c90b82cf5e920f12ced8a4ac089",
        429,
        "786a4e0891e96f44ccf0beb91ae0b8a72960f1b00af0d7254567195627e8e839",
    ),
}

NEW_SOURCE_FAMILIES = {
    "alps_middle_east_live_site_pages",
    "capitaland_india_trust_financial_results",
    "capitaland_newsroom",
    "datavolt_linkedin_public_post",
    "dci_data_centers_linkedin_public_post",
    "dssa_press_releases",
    "hsbc_cib_linkedin_public_post",
    "koramco_media_news_listing",
    "lg_sinar_mas_newsroom",
    "nsw_planning_portal_vpa",
    "sec_edgar_issuer_filings",
    "sify_technologies_events",
    "sk_ecoplant_newsroom",
    "sk_telecom_newsroom",
    "smplus_newsroom",
    "stt_gdc_company_news",
    "stt_gdc_data_center_factsheets",
    "stt_gdc_data_center_pages",
    "three_e_network_investor_relations",
    "uzbekistan_ministry_digital_news",
}


def freshness_contract() -> dict[str, Any]:
    """Move only STT Johor from stale-excluded to historical-only."""

    contract = base_freshness_contract()
    historical = set(contract["historical_inputs_included_as_last_observed"])
    historical.add(STT_JOHOR_SOURCE)
    contract["historical_inputs_included_as_last_observed"] = sorted(historical)
    contract["stale_inputs_excluded"] = sorted(STALE_EXCLUSIONS - {STT_JOHOR_SOURCE})
    return contract


@contextmanager
def publication_lock() -> Iterator[None]:
    """Hold an exclusive v67 publication lock without replacing any file."""

    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise SystemExit(
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


def _load_addition(relative: str, size: int, digest: str) -> dict[str, Any]:
    source = ROOT / relative
    if not source.is_file() or source.is_symlink():
        raise SystemExit(f"addition must be an ordinary file: {relative}")
    if stat.S_IMODE(source.stat().st_mode) != 0o644:
        raise SystemExit(f"addition mode must be 0644: {relative}")
    raw = source.read_bytes()
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
        raise SystemExit(f"addition byte pin differs: {relative}")
    document = json.loads(raw)
    if raw.decode("utf-8") != json.dumps(
        document, indent=2, ensure_ascii=False
    ) + "\n":
        raise SystemExit(f"addition JSON is not canonical: {relative}")
    return document


def _validate_additions() -> None:
    if len(ADDITION_PINS) != 14:
        raise SystemExit("v67 must contain exactly fourteen additions")
    documents = {
        relative: _load_addition(relative, size, digest)
        for relative, (size, digest) in ADDITION_PINS.items()
    }
    entity_keys: set[str] = set()
    evidence_by_key: dict[str, list[dict[str, Any]]] = {}
    lifecycle_rows: list[tuple[str, str, str]] = []
    capacity_rows: set[tuple[str, str, str, float, str]] = set()
    workload_rows: set[tuple[str, str, str, str]] = set()
    coordinate_keys: set[str] = set()
    operating_model_count = 0
    for relative, document in documents.items():
        if document.get("schema_version") != "1.1":
            raise SystemExit(f"v67 addition schema differs: {relative}")
        if "2026-07-20" not in relative or "2026-07-21" in relative:
            raise SystemExit(f"v67 addition path loses Jul20 lineage: {relative}")
        for evidence in document["evidence"]:
            evidence_by_key.setdefault(evidence["key"], []).append(evidence)
            if "captured-2026-07-21" in evidence["key"]:
                raise SystemExit(f"v67 evidence key loses Jul20 lineage: {relative}")
            if evidence["retrieved_at"] > RECORDED_AT:
                raise SystemExit(f"v67 evidence is newer than publication: {relative}")
        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            if entity["stable_key"] in entity_keys:
                raise SystemExit(f"duplicate v67 entity key: {entity['stable_key']}")
            entity_keys.add(entity["stable_key"])
            if date.fromisoformat(entity["as_of_date"]) > date.fromisoformat(AS_OF):
                raise SystemExit(f"v67 entity crosses release day: {relative}")
            has_coordinates = entity["coordinates"] is not None
            if has_coordinates:
                coordinate_keys.add(entity["stable_key"])
            if entity["geometry"] is not None:
                raise SystemExit(f"v67 addition gained unsupported geometry: {relative}")
        for row in document["lifecycle"]:
            stable_key = document[row["entity"]]["stable_key"]
            lifecycle_rows.append((stable_key, row["value"], row["as_of_date"]))
            if date.fromisoformat(row["as_of_date"]) > date.fromisoformat(AS_OF):
                raise SystemExit(f"v67 lifecycle crosses release day: {relative}")
        for row in document["capacities"]:
            stable_key = document[row["entity"]]["stable_key"]
            capacity_rows.add(
                (
                    stable_key,
                    row["metric"],
                    row["stage"],
                    float(row["base"]),
                    row["as_of_date"],
                )
            )
            if row["stage"] != "planned" or row["metric"] not in {
                "critical_it_mw",
                "gross_facility_mw",
            }:
                raise SystemExit(f"v67 promoted a conflicting or untyped metric: {relative}")
        for row in document["workloads"]:
            stable_key = document[row["entity"]]["stable_key"]
            workload_rows.add(
                (stable_key, row["value"], row["as_of_date"], row["method"])
            )
        operating_model_count += len(document["operating_models"])

    if entity_keys != ADDED_ENTITY_KEYS:
        raise SystemExit("v67 added entity identity set differs")
    if coordinate_keys != SYD06_COORDINATE_KEYS:
        raise SystemExit("only Microsoft SYD06 may add coordinates")
    if len(lifecycle_rows) != 15:
        raise SystemExit("v67 lifecycle observation count differs")
    winners: dict[str, tuple[str, str]] = {}
    for stable_key, status, observed in sorted(
        lifecycle_rows, key=lambda row: (row[0], row[2])
    ):
        winners[stable_key] = (status, observed)
    if winners != LIFECYCLE_WINNERS:
        raise SystemExit(f"v67 lifecycle winners differ: {winners}")
    if capacity_rows != CAPACITY_CONTRACT:
        raise SystemExit(f"v67 capacity contract differs: {capacity_rows}")
    if workload_rows != WORKLOAD_CONTRACT:
        raise SystemExit(f"v67 workload contract differs: {workload_rows}")
    if operating_model_count:
        raise SystemExit("v67 additions gained an operating-model claim")

    occurrences = sum(len(rows) for rows in evidence_by_key.values())
    shared_counts = {
        key: len(rows) for key, rows in evidence_by_key.items() if len(rows) > 1
    }
    if occurrences != 36 or len(evidence_by_key) != 32:
        raise SystemExit("v67 evidence occurrence/dedup arithmetic differs")
    if shared_counts != SHARED_EVIDENCE_COUNTS:
        raise SystemExit(f"v67 intended shared evidence keys differ: {shared_counts}")
    for key, rows in evidence_by_key.items():
        if any(row != rows[0] for row in rows[1:]):
            raise SystemExit(f"v67 shared evidence payload conflicts: {key}")


def selected_inputs(base: Mapping[str, Any]) -> tuple[list[dict[str, str]], list[Path]]:
    """Return the exact fourteen-addition, 378-input v66 successor."""

    if base.get("release_id") != "2026-07-20-open-seed-v66":
        raise SystemExit("v67 base must be exactly frozen v66")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 364:
        raise SystemExit("frozen v66 curated inventory differs")
    pins: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise SystemExit("frozen v66 curated row is invalid")
        source_path, digest = row["path"], row["sha256"]
        if (
            not isinstance(source_path, str)
            or not isinstance(digest, str)
            or source_path in pins
        ):
            raise SystemExit("frozen v66 curated inventory is invalid")
        pins[source_path] = digest

    _validate_additions()
    for source_path, (_, digest) in ADDITION_PINS.items():
        if source_path in pins:
            raise SystemExit(f"v67 addition already occurs in v66: {source_path}")
        pins[source_path] = digest
    excluded = (
        STALE_EXCLUSIONS | PENDING_NEXT_DAY_EXCLUSIONS | OUT_OF_SCOPE_EXCLUSIONS
    ) - set(ADDITION_PINS)
    if excluded & set(pins):
        raise SystemExit("an unaccepted excluded source was selected")
    if len(pins) != 378:
        raise SystemExit(f"expected 378 unique v67 inputs, found {len(pins)}")

    rows_out = [
        {"path": source_path, "sha256": pins[source_path]}
        for source_path in sorted(pins)
    ]
    paths: list[Path] = []
    for row in rows_out:
        source = ROOT / row["path"]
        if not source.is_file() or source.is_symlink():
            raise SystemExit(f"input must be an ordinary file: {row['path']}")
        if stat.S_IMODE(source.stat().st_mode) != 0o644:
            raise SystemExit(f"input mode must be 0644: {row['path']}")
        if sha256(source) != row["sha256"]:
            raise SystemExit(f"input hash differs: {row['path']}")
        paths.append(source)
    return rows_out, paths


def _base_paths(base: Mapping[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for row in base["curated_inputs"]:
        source = ROOT / row["path"]
        if sha256(source) != row["sha256"]:
            raise SystemExit(f"frozen v66 source hash differs: {row['path']}")
        paths.append(source)
    return paths


def _import_curated(connection: sqlite3.Connection, source: Path) -> object:
    document = json.loads(source.read_text(encoding="utf-8"))
    timestamps = {item["retrieved_at"] for item in document["evidence"]}
    if document["schema_version"] == "1.0":
        if len(timestamps) != 1:
            raise SystemExit(f"schema 1.0 source has multiple timestamps: {source.name}")
        return CuratedOfficialSourceAdapter().import_file(
            connection, source, retrieved_at=next(iter(timestamps))
        )
    if document["schema_version"] == "1.1":
        return CuratedOfficialSourceAdapterV11().import_file(
            connection, source, recorded_at=V11_RECORDED_AT
        )
    raise SystemExit(f"unsupported curated schema: {source.name}")


def _populate_database(
    base: Mapping[str, Any], paths: list[Path], sqlite_path: Path
) -> sqlite3.Connection:
    connection, _ = initialize(sqlite_path)
    epoch = base["epoch_capture"]
    result = EpochAIAdapter().import_file(
        connection,
        ROOT / epoch["archive"],
        map_html=ROOT / epoch["map"],
        retrieved_at=epoch["retrieved_at"],
        as_of_date=EPOCH_AS_OF,
    )
    if json.loads(json.dumps(asdict(result))) != base["expected_epoch_result"]:
        connection.close()
        raise SystemExit("frozen Epoch import result differs from v66")
    try:
        for source in paths:
            imported = _import_curated(connection, source)
            if getattr(imported, "warnings"):
                raise SystemExit(f"curated import warnings for {source.name}")
        errors = validate_database(connection)
        if errors:
            raise SystemExit("fresh database validation failed: " + "; ".join(errors))
        return connection
    except Exception:
        connection.close()
        raise


def _semantic_state(
    connection: sqlite3.Connection, stable_keys: tuple[str, ...]
) -> dict[str, tuple[tuple[Any, ...], ...]]:
    placeholders = ",".join("?" for _ in stable_keys)
    queries = {
        "entities": f"""
            SELECT stable_key, kind, created_from_evidence_id
            FROM entities WHERE stable_key IN ({placeholders})
        """,
        "snapshots": f"""
            SELECT entities.stable_key, name, latitude, longitude, geometry_json,
                   tags_json, evidence_id, as_of_date, valid_to_date, method, confidence
            FROM entity_snapshots JOIN entities ON entities.id = entity_id
            WHERE entities.stable_key IN ({placeholders})
        """,
        "lifecycle": f"""
            SELECT entities.stable_key, status, evidence_id, as_of_date,
                   valid_to_date, method, confidence, notes
            FROM lifecycle_observations JOIN entities ON entities.id = entity_id
            WHERE entities.stable_key IN ({placeholders})
        """,
        "capacity": f"""
            SELECT entities.stable_key, metric, stage, unit, low, base, high,
                   method, confidence, evidence_id, as_of_date, target_date,
                   valid_to_date, notes
            FROM capacity_estimates JOIN entities ON entities.id = entity_id
            WHERE entities.stable_key IN ({placeholders})
        """,
        "models": f"""
            SELECT entities.stable_key, operating_model, evidence_id, as_of_date,
                   valid_to_date, method, confidence, notes
            FROM operating_model_observations JOIN entities ON entities.id = entity_id
            WHERE entities.stable_key IN ({placeholders})
        """,
        "workloads": f"""
            SELECT entities.stable_key, workload, evidence_id, as_of_date,
                   valid_to_date, method, confidence, notes
            FROM workload_observations JOIN entities ON entities.id = entity_id
            WHERE entities.stable_key IN ({placeholders})
        """,
        "projects": f"""
            SELECT project_entity.stable_key, target_entity.stable_key
            FROM projects
            JOIN entities AS project_entity ON project_entity.id = projects.entity_id
            JOIN entities AS target_entity ON target_entity.id = projects.target_entity_id
            WHERE project_entity.stable_key IN ({placeholders})
        """,
    }
    return {
        name: tuple(sorted((tuple(row) for row in connection.execute(query, stable_keys)), key=repr))
        for name, query in queries.items()
    }


def _validate_prior_semantics(
    connection: sqlite3.Connection, base: Mapping[str, Any]
) -> None:
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v67-base-compare-", dir="/private/tmp"
    ) as temporary:
        base_connection = _populate_database(
            base, _base_paths(base), Path(temporary) / "v66.sqlite"
        )
        try:
            base_keys = tuple(
                row[0]
                for row in base_connection.execute(
                    "SELECT stable_key FROM entities ORDER BY stable_key"
                )
            )
            if len(base_keys) != 755:
                raise SystemExit("frozen v66 identity count differs")
            if _semantic_state(connection, base_keys) != _semantic_state(
                base_connection, base_keys
            ):
                raise SystemExit("v67 changed a prior semantic entity row")
            base_evidence = {
                row[0]: tuple(row[1:])
                for row in base_connection.execute("SELECT * FROM evidence")
            }
            current_evidence = {
                row[0]: tuple(row[1:]) for row in connection.execute("SELECT * FROM evidence")
            }
            if any(current_evidence.get(key) != value for key, value in base_evidence.items()):
                raise SystemExit("v67 changed a prior evidence row")
        finally:
            base_connection.close()


def _validate_database_contract(connection: sqlite3.Connection) -> None:
    expected = {
        "entities": 783,
        "evidence": 615,
        "lifecycle_observations": 459,
        "capacity_estimates": 522,
        "entity_snapshots": 803,
        "operating_model_observations": 56,
        "workload_observations": 128,
    }
    counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in expected
    }
    if counts != expected:
        raise SystemExit(f"fresh v67 database projection differs: {counts}")

    keys = tuple(sorted(ADDED_ENTITY_KEYS))
    placeholders = ",".join("?" for _ in keys)
    entity_rows = connection.execute(
        f"SELECT stable_key, kind FROM entities WHERE stable_key IN ({placeholders})",
        keys,
    ).fetchall()
    if {row[0] for row in entity_rows} != ADDED_ENTITY_KEYS:
        raise SystemExit("v67 added identity set differs")
    if {row[0] for row in entity_rows if row[1] == "project"} != ADDED_PROJECT_KEYS:
        raise SystemExit("v67 added project set differs")

    lifecycle = connection.execute(
        f"""
        SELECT entities.stable_key, status, as_of_date
        FROM lifecycle_observations JOIN entities ON entities.id = entity_id
        WHERE entities.stable_key IN ({placeholders})
        ORDER BY entities.stable_key, as_of_date
        """,
        keys,
    ).fetchall()
    if len(lifecycle) != 15:
        raise SystemExit("v67 lifecycle database delta differs")
    capacity = connection.execute(
        f"""
        SELECT entities.stable_key, metric, stage, base, as_of_date
        FROM capacity_estimates JOIN entities ON entities.id = entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        keys,
    ).fetchall()
    if {tuple(row) for row in capacity} != CAPACITY_CONTRACT:
        raise SystemExit("v67 capacity database delta differs")
    workloads = connection.execute(
        f"""
        SELECT entities.stable_key, workload, as_of_date, method
        FROM workload_observations JOIN entities ON entities.id = entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        keys,
    ).fetchall()
    if {tuple(row) for row in workloads} != WORKLOAD_CONTRACT:
        raise SystemExit("v67 workload database delta differs")
    models = connection.execute(
        f"""
        SELECT COUNT(*) FROM operating_model_observations
        JOIN entities ON entities.id = entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        keys,
    ).fetchone()[0]
    if models:
        raise SystemExit("v67 additions gained an operating-model row")

    snapshots = connection.execute(
        f"""
        SELECT entities.stable_key, latitude, longitude, geometry_json, method
        FROM entity_snapshots JOIN entities ON entities.id = entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        keys,
    ).fetchall()
    coordinate_rows = {
        row[0]: (row[1], row[2], row[3], row[4])
        for row in snapshots
        if row[1] is not None or row[2] is not None or row[3] is not None
    }
    if set(coordinate_rows) != SYD06_COORDINATE_KEYS or any(
        value
        != (
            -33.83614,
            150.78015,
            '{"coordinates":[150.78015,-33.83614],"type":"Point"}',
            "authoritative_site_plan",
        )
        for value in coordinate_rows.values()
    ):
        raise SystemExit(f"v67 SYD06 coordinate boundary differs: {coordinate_rows}")


def _build_database(base: Mapping[str, Any], paths: list[Path], sqlite_path: Path):
    connection = _populate_database(base, paths, sqlite_path)
    try:
        _validate_database_contract(connection)
        _validate_prior_semantics(connection, base)
        return connection
    except Exception:
        connection.close()
        raise


def augment_release_documents(
    documents: Mapping[str, str], *, as_of: str
) -> dict[str, str]:
    """Add the release-day last-observed carrier and bind it into the manifest."""

    output = dict(documents)
    if FRESHNESS_FILENAME in output:
        raise RuntimeError("freshness filename already exists")
    freshness = build_freshness_csv(output["entities.csv"], as_of=as_of)
    output[FRESHNESS_FILENAME] = freshness
    readme = output["README.md"].rstrip() + "\n\n" + FRESHNESS_README + "\n"
    output["README.md"] = readme
    manifest = json.loads(output["manifest.json"])
    manifest["files"]["README.md"] = {
        "bytes": len(readme.encode("utf-8")),
        "sha256": hashlib.sha256(readme.encode("utf-8")).hexdigest(),
    }
    manifest["files"][FRESHNESS_FILENAME] = {
        "bytes": len(freshness.encode("utf-8")),
        "sha256": hashlib.sha256(freshness.encode("utf-8")).hexdigest(),
    }
    freshness_rows = list(csv.DictReader(io.StringIO(freshness)))
    manifest["current_status_inferred"] = False
    manifest["lifecycle_freshness_records"] = len(freshness_rows)
    manifest["lifecycle_status_semantics"] = "last_observed"
    output["manifest.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    return output


def _write_augmented_release(connection: sqlite3.Connection, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    documents = build_release_documents(
        connection,
        as_of=AS_OF,
        recorded_at=RECORDED_AT,
        publication_contract_version=4,
    )
    for filename, text in augment_release_documents(documents, as_of=AS_OF).items():
        (output / filename).write_text(text, encoding="utf-8")


def _csv_counter(path: Path) -> Counter[tuple[tuple[str, str], ...]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return Counter(tuple(row.items()) for row in csv.DictReader(stream))


def _counter_hash(counter: Counter[tuple[tuple[str, str], ...]]) -> str:
    rows = [dict(packed) for packed in counter.elements()]
    rows.sort(
        key=lambda row: json.dumps(
            row, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    )
    raw = (
        json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _rows_by_key(path: Path, key: str) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return {row[key]: row for row in csv.DictReader(stream)}


def _validate_release_delta(stage: Path) -> None:
    for filename, expected in CSV_DELTA_CONTRACT.items():
        before = _csv_counter(BASE_RELEASE / filename)
        after = _csv_counter(stage / filename)
        common = before & after
        added = after - common
        removed = before - common
        actual = (
            sum(common.values()),
            sum(added.values()),
            _counter_hash(added),
            sum(removed.values()),
            _counter_hash(removed),
        )
        if actual != expected:
            raise SystemExit(f"fresh v67 CSV delta differs: {filename}: {actual}")

    before_entities = _rows_by_key(BASE_RELEASE / "entities.csv", "stable_key")
    after_entities = _rows_by_key(stage / "entities.csv", "stable_key")
    if set(after_entities) - set(before_entities) != ADDED_ENTITY_KEYS:
        raise SystemExit("v67 public added entity set differs")
    if set(before_entities) - set(after_entities):
        raise SystemExit("v67 removed a prior entity")
    if any(before_entities[key] != after_entities[key] for key in before_entities):
        raise SystemExit("v67 changed a prior entity/claim/snapshot row")

    if (stage / "resolution_candidates.csv").read_bytes() != (
        BASE_RELEASE / "resolution_candidates.csv"
    ).read_bytes() or (stage / "resolution_candidates.json").read_bytes() != (
        BASE_RELEASE / "resolution_candidates.json"
    ).read_bytes():
        raise SystemExit("v67 changed a resolution advisory")


def _validate_freshness(stage: Path) -> None:
    before = _rows_by_key(BASE_RELEASE / FRESHNESS_FILENAME, "stable_key")
    after = _rows_by_key(stage / FRESHNESS_FILENAME, "stable_key")
    if len(after) != 443 or tuple(next(iter(after.values()))) != FRESHNESS_FIELDS:
        raise SystemExit(f"fresh v67 freshness shape differs: {len(after)}")
    if set(after) - set(before) != set(LIFECYCLE_WINNERS):
        raise SystemExit("v67 added freshness identity set differs")
    if set(before) - set(after):
        raise SystemExit("v67 removed a prior freshness row")
    class_transitions: dict[str, tuple[str, str]] = {}
    for stable_key, old in before.items():
        new = after[stable_key]
        for field in old:
            if field in {"observation_age_days", "freshness_class"}:
                continue
            if old[field] != new[field]:
                raise SystemExit(f"v67 changed prior freshness semantics: {stable_key}")
        if int(new["observation_age_days"]) != int(old["observation_age_days"]) + 1:
            raise SystemExit(f"v67 prior freshness age did not advance once: {stable_key}")
        if new["freshness_class"] != old["freshness_class"]:
            class_transitions[stable_key] = (
                old["freshness_class"],
                new["freshness_class"],
            )
    if class_transitions != FRESHNESS_CLASS_TRANSITION:
        raise SystemExit(
            f"v67 inherited freshness-class transition differs: {class_transitions}"
        )
    for stable_key, (status, observed) in LIFECYCLE_WINNERS.items():
        row = after[stable_key]
        if (
            row["last_observed_status"] != status
            or row["last_observed_status_as_of"] != observed
        ):
            raise SystemExit(f"v67 last-observed winner differs: {stable_key}")
    if any(
        row["status_semantics"] != "last_observed"
        or row["current_status_classification"] != "unknown"
        or row["current_construction_claim"] != "false"
        for row in after.values()
    ):
        raise SystemExit("v67 freshness rows infer current construction")
    classes = Counter(row["freshness_class"] for row in after.values())
    if classes != {
        "recent_0_90_days": 224,
        "aging_91_365_days": 190,
        "stale_over_365_days": 29,
    }:
        raise SystemExit(f"v67 freshness distribution differs: {classes}")


def _validate_release_facts(stage: Path) -> None:
    summary = json.loads((stage / "summary.json").read_text(encoding="utf-8"))
    expected = {
        "campuses_total": 415,
        "campuses_with_coordinates": 128,
        "capacity_estimates_current": 521,
        "construction_pipeline_records": 401,
        "construction_source_signals": 303,
        "entities_total": 783,
        "entities_with_coordinates": 183,
        "evidence_total": 615,
        "lifecycle_observations_current": 443,
        "projects_total": 368,
        "recorded_at": RECORDED_AT,
    }
    actual = {key: summary.get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"fresh v67 summary facts differ: {actual}")
    if summary["entities_by_status"] != {
        "announced": 6,
        "civil_works": 3,
        "commissioning": 2,
        "expansion": 29,
        "foundations": 2,
        "mep_electrical": 19,
        "operational": 42,
        "permitted": 3,
        "proposed": 2,
        "shell": 28,
        "site_control": 1,
        "site_preparation": 12,
        "under_construction": 294,
    }:
        raise SystemExit("fresh v67 status summary differs")
    if summary["capacity_estimates_by_metric"].get("critical_it_mw") != 257:
        raise SystemExit("fresh v67 critical-IT count differs")
    if summary["capacity_estimates_by_metric"].get("gross_facility_mw") != 132:
        raise SystemExit("fresh v67 gross-facility count differs")
    if summary["capacity_estimates_by_stage"].get("planned") != 154:
        raise SystemExit("fresh v67 planned-capacity count differs")

    manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    expected_manifest = {
        "entities": 783,
        "evidence_records": 494,
        "capacity_estimates": 521,
        "construction_pipeline_records": 401,
        "construction_source_signals": 303,
        "resolution_candidates": 6,
        "lifecycle_freshness_records": 443,
        "lifecycle_status_semantics": "last_observed",
        "current_status_inferred": False,
    }
    actual_manifest = {key: manifest.get(key) for key in expected_manifest}
    if actual_manifest != expected_manifest:
        raise SystemExit(f"fresh v67 manifest facts differ: {actual_manifest}")
    base_manifest = json.loads(
        (BASE_RELEASE / "manifest.json").read_text(encoding="utf-8")
    )
    if set(manifest["source_families"]) - set(base_manifest["source_families"]) != (
        NEW_SOURCE_FAMILIES
    ):
        raise SystemExit("fresh v67 source-family delta differs")
    if set(base_manifest["source_families"]) - set(manifest["source_families"]):
        raise SystemExit("fresh v67 removed a source family")
    if len(manifest["source_families"]) != 280:
        raise SystemExit("fresh v67 source-family count differs")
    if len(list(stage.iterdir())) != 14:
        raise SystemExit("fresh v67 release must contain exactly 14 files")
    _validate_freshness(stage)


def _ordinary_file(path: Path, label: str) -> bytes:
    if not path.is_file() or path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"{label} must be an ordinary file")
    return path.read_bytes()


def _guard_state() -> dict[str, Any]:
    additions: dict[str, tuple[int, str]] = {}
    for relative, pin in ADDITION_PINS.items():
        source = ROOT / relative
        additions[relative] = (source.stat().st_size, sha256(source))
        if additions[relative] != pin:
            raise SystemExit(f"v67 addition pin differs: {relative}")
    return {
        "base_definition": sha256(BASE_DEFINITION),
        "base_manifest": sha256(BASE_RELEASE / "manifest.json"),
        "base_tree": tree_digest(BASE_RELEASE),
        "additions": additions,
    }


def _validate_definition(document: Mapping[str, Any], base: Mapping[str, Any]) -> None:
    if set(document) != set(base):
        raise ValueError("v67 definition schema differs from v66")
    if document.get("release_id") != RELEASE_ID:
        raise ValueError("release_id must identify frozen v67")
    if document.get("build") != {"as_of": AS_OF, "recorded_at": RECORDED_AT}:
        raise ValueError("v67 build timestamp contract differs")
    if document.get("publication_contract_version") != 4:
        raise ValueError("v67 publication contract differs")
    if document.get("freshness_contract") != freshness_contract():
        raise ValueError("v67 freshness contract differs")
    for key in ("epoch_capture", "expected_epoch_result", "schema_version", "scope"):
        if document.get(key) != base.get(key):
            raise ValueError(f"v67 inherited definition field differs: {key}")


def validate_open_seed_v67(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
) -> dict[str, Any]:
    """Validate exact adjacency, frozen bytes, and deterministic offline replay."""

    if replay_count != 2:
        raise ValueError("v67 requires exactly two offline replays")
    guard = _guard_state()
    if (
        guard["base_definition"] != BASE_DEFINITION_SHA256
        or guard["base_manifest"] != BASE_MANIFEST_SHA256
        or guard["base_tree"] != BASE_TREE_SHA256
    ):
        raise ValueError("accepted v66 base pin differs")
    base = json.loads(_ordinary_file(BASE_DEFINITION, "v66 definition"))
    raw = _ordinary_file(definition_path, "v67 definition")
    document = json.loads(raw)
    if raw != canonical_json(document):
        raise ValueError("v67 definition JSON is not canonical")
    _validate_definition(document, base)
    selected_rows, paths = selected_inputs(base)
    if document.get("curated_inputs") != selected_rows:
        raise ValueError("v67 selected input inventory differs")

    if not release_path.is_dir() or release_path.is_symlink():
        raise ValueError("v67 release must be an ordinary directory")
    if require_frozen and stat.S_IMODE(release_path.stat().st_mode) != 0o555:
        raise ValueError("v67 release directory mode must be 0555")
    release_files = {path.name: path for path in release_path.iterdir()}
    if any(path.is_symlink() or not path.is_file() for path in release_files.values()):
        raise ValueError("v67 release contains a symlink or non-file entry")
    if require_frozen and any(
        stat.S_IMODE(path.stat().st_mode) != 0o444 for path in release_files.values()
    ):
        raise ValueError("v67 release file mode must be 0444")

    manifest_raw = _ordinary_file(release_path / "manifest.json", "v67 manifest")
    manifest = json.loads(manifest_raw)
    if hashlib.sha256(manifest_raw).hexdigest() != document["expected_release"].get(
        "manifest_sha256"
    ):
        raise ValueError("v67 release manifest hash differs")
    expected_release = {
        key: value
        for key, value in document["expected_release"].items()
        if key != "manifest_sha256"
    }
    actual_release = {key: value for key, value in manifest.items() if key != "files"}
    if actual_release != expected_release:
        raise ValueError("v67 expected release facts differ")
    expected_names = set(manifest["files"]) | {"manifest.json"}
    if set(release_files) != expected_names:
        raise ValueError("v67 release file inventory differs")
    for filename, pin in manifest["files"].items():
        payload = _ordinary_file(release_path / filename, filename)
        if len(payload) != pin["bytes"] or hashlib.sha256(payload).hexdigest() != pin[
            "sha256"
        ]:
            raise ValueError(f"v67 release file pin differs: {filename}")
    _validate_release_delta(release_path)
    _validate_release_facts(release_path)

    summary = json.loads((release_path / "summary.json").read_text(encoding="utf-8"))
    if {
        key: summary[key] for key in document["expected_summary"]
    } != document["expected_summary"]:
        raise ValueError("v67 expected summary differs")

    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v67-replay-{replay + 1}-", dir="/private/tmp"
        ) as temporary:
            temporary_path = Path(temporary)
            connection = _build_database(
                base, paths, temporary_path / "atlas.sqlite"
            )
            try:
                replay_release = temporary_path / "release"
                _write_augmented_release(connection, replay_release)
            finally:
                connection.close()
            _validate_release_delta(replay_release)
            _validate_release_facts(replay_release)
            if {path.name for path in replay_release.iterdir()} != set(release_files):
                raise ValueError("v67 replay file inventory differs")
            for filename, frozen in release_files.items():
                if (replay_release / filename).read_bytes() != frozen.read_bytes():
                    raise ValueError(f"v67 offline replay differs: {filename}")
    if _guard_state() != guard:
        raise ValueError("v67 validation mutated v66 or an accepted source")
    return manifest


def build_open_seed_v67() -> dict[str, object]:
    """Build and freeze v67 exactly once, refusing every publication collision."""

    guard = _guard_state()
    with publication_lock():
        if DEFINITION.exists() or DEFINITION.is_symlink():
            raise SystemExit(
                f"definition already exists; refusing overwrite: {DEFINITION}"
            )
        if RELEASE.exists() or RELEASE.is_symlink():
            raise SystemExit(f"release already exists; refusing overwrite: {RELEASE}")
        if guard["base_definition"] != BASE_DEFINITION_SHA256:
            raise SystemExit("accepted v66 definition hash differs")
        if guard["base_manifest"] != BASE_MANIFEST_SHA256:
            raise SystemExit("accepted v66 manifest hash differs")
        if guard["base_tree"] != BASE_TREE_SHA256:
            raise SystemExit("accepted v66 release tree differs")

        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        input_rows, paths = selected_inputs(base)
        staging_root = ROOT / ".staging"
        staging_root.mkdir(exist_ok=True)
        release_stage = Path(
            tempfile.mkdtemp(prefix=f".{RELEASE.name}.", dir=RELEASE.parent)
        )
        release_stage.rmdir()
        definition_stage = DEFINITION.parent / f".{DEFINITION.name}.{os.getpid()}.tmp"
        published_release = False
        try:
            with tempfile.TemporaryDirectory(
                prefix="open-seed-v67-db-", dir=staging_root
            ) as temporary:
                connection = _build_database(
                    base, paths, Path(temporary) / "atlas.sqlite"
                )
                try:
                    _write_augmented_release(connection, release_stage)
                    summary = summarize(
                        connection, as_of=AS_OF, recorded_at=RECORDED_AT
                    )
                finally:
                    connection.close()

            _validate_release_delta(release_stage)
            _validate_release_facts(release_stage)
            manifest_raw = (release_stage / "manifest.json").read_bytes()
            manifest = json.loads(manifest_raw)
            expected_release = {
                key: value for key, value in manifest.items() if key != "files"
            }
            expected_release["manifest_sha256"] = hashlib.sha256(
                manifest_raw
            ).hexdigest()
            expected_summary = {key: summary[key] for key in base["expected_summary"]}
            definition = dict(base)
            definition["build"] = {"as_of": AS_OF, "recorded_at": RECORDED_AT}
            definition["curated_inputs"] = input_rows
            definition["expected_release"] = expected_release
            definition["expected_summary"] = expected_summary
            definition["freshness_contract"] = freshness_contract()
            definition["publication_contract_version"] = 4
            definition["release_id"] = RELEASE.name
            with definition_stage.open("xb") as stream:
                stream.write(canonical_json(definition))
                stream.flush()
                os.fsync(stream.fileno())
            definition_stage.chmod(0o644)

            for output in release_stage.iterdir():
                output.chmod(0o444)
            release_stage.chmod(0o555)
            validate_open_seed_v67(definition_stage, release_stage)
            promote_noreplace(release_stage, RELEASE)
            published_release = True
            promote_noreplace(definition_stage, DEFINITION)
            validate_open_seed_v67(DEFINITION, RELEASE)
        finally:
            if not published_release:
                discard_release_stage(release_stage)
            try:
                definition_stage.unlink()
            except FileNotFoundError:
                pass
    if _guard_state() != guard:
        raise SystemExit("v67 build mutated v66 or an accepted source")

    manifest = json.loads((RELEASE / "manifest.json").read_text(encoding="utf-8"))
    return {
        "definition": str(DEFINITION),
        "definition_sha256": sha256(DEFINITION),
        "manifest_sha256": sha256(RELEASE / "manifest.json"),
        "recorded_at": RECORDED_AT,
        "release": str(RELEASE),
        "release_tree_sha256": tree_digest(RELEASE),
        **{
            key: value
            for key, value in manifest.items()
            if key not in {"files", "source_families"}
        },
        "source_families": len(manifest["source_families"]),
    }


def main() -> int:
    print(json.dumps(build_open_seed_v67(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
