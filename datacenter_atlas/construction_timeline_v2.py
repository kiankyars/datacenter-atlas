"""Frozen v62 successor carrier for the source-scoped construction timeline."""

# ruff: noqa: F821 -- accepted-v1 symbols are installed by the pinned exec below.

from __future__ import annotations

from collections import Counter as _CarrierCounter
import csv as _carrier_csv
import hashlib as _carrier_hashlib
from pathlib import Path as _CarrierPath
from typing import Any as _CarrierAny


_BASE_SOURCE_SHA256 = (
    "c75520069a8f098e6be447891954f6b9bd9c0d0c4bff5b6adb20254c18430a3b"
)
_BASE_SOURCE = _CarrierPath(__file__).with_name("construction_timeline_v1.py")


def _successor_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_timeline_v2 accepted-v1 boundary changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if _carrier_hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_timeline_v1 changed; refusing v2 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("open_seed_release_v5", "open_seed_release_v7", 4),
    ("v60", "v62", 39),
    ("2026-07-20-public-open-v1", "2026-07-20-public-open-v2", 1),
    ("2026-07-21T04:35:00Z", "2026-07-21T04:50:00Z", 1),
    (
        "4f3a81ad33c3cb73565eefe0904fcf4118d57bfc071852dc226e331e3dd32b66",
        "e992f321a463c4a4316ed617dcc1efef505f01792fb91f6e13aded94e10b6f66",
        1,
    ),
    (
        "d69ded6f7b86415b4dc8ad84cbee65835d878e310fbcb2c8954636066173f430",
        "60c7172a20a7ff43a3644902d5c186b015e06228737ea8b39c7a5082d3d94ea6",
        1,
    ),
    (
        "1d58652f691b8030717b7af6c61d2717b2b3427520f7d1b402b75b7670beb138",
        "71ec5c0a2f0af7d5557de5479f81fcb29dca0ae6342736681e3bdc12ac4ae8fb",
        1,
    ),
    ("construction-timeline-definition-v1", "construction-timeline-definition-v2", 1),
    ("construction-timeline-bundle-v1", "construction-timeline-bundle-v2", 1),
    ("construction-timeline-coverage-v1", "construction-timeline-coverage-v2", 1),
    ("source-scoped-entity-timeline-v1", "source-scoped-entity-timeline-v2", 1),
    ("SCHEMA_VERSION = 1", "SCHEMA_VERSION = 2", 1),
    ('"entities_with_lifecycle_observations": 412', '"entities_with_lifecycle_observations": 415', 1),
    ('"multi_observation_entities": 14', '"multi_observation_entities": 15', 1),
    ('"raw_lifecycle_observations": 426', '"raw_lifecycle_observations": 430', 1),
    ('"single_observation_entities": 398', '"single_observation_entities": 400', 1),
    ('"source_families": 175', '"source_families": 178', 1),
    ('"status_changing_multi_observation_entities": 10', '"status_changing_multi_observation_entities": 11', 1),
    ("!= 725", "!= 730", 1),
    ("accepted v1 ID", "accepted v2 ID", 1),
    ("construction-timeline-v1-db-", "construction-timeline-v2-db-", 1),
    ("construction milestone timeline v1", "construction milestone timeline v2", 1),
    ("v59 base definition", "v61 base definition", 2),
):
    _source = _successor_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())


_V1_DEFINITION = ROOT / "sources/construction-timeline-2026-07-20-public-open-v1.json"
_V1_BUNDLE = ROOT / "construction_timelines/2026-07-20-public-open-v1"
_V1_DEFINITION_SHA256 = (
    "b7e04ec1915c1527bcb8cd3c7c08dad561b3bde5bdfe668cb5f6defaa14c0e7d"
)
_V1_MANIFEST_SHA256 = (
    "610b4058593e2d426faf4560799b9c1335711105c35b0bd839f0bcb06539f4fd"
)
_V1_TREE_SHA256 = (
    "29f5f724089d8a2eafce69cfb6cfd193d6547dbd21efbca1e89945b4557e39b2"
)

_QAREEB_KEY = "curated:batelco-qareeb-beyon-data-oasis-edge-data-center:facility-build"
_APPLIED_PARENT_KEY = (
    "curated:applied-digital-polaris-forge-1:second-150mw-facility"
)
_APPLIED_PHASE_KEY = f"{_APPLIED_PARENT_KEY}:phase-1"
_DATABANK_IAD5_KEY = "curated:databank-culpeper-campus:iad5-current-build"
_STC_BAHRAIN_KEY = "curated:stc-bahrain-data-center:facility-build"

V62_FOCUS_CONTRACT = {
    "applied_digital_parent": {
        "critical_it_mw": 150.0,
        "capacity_stage": "contracted",
        "observed_date": "2026-04-08",
        "stable_key": _APPLIED_PARENT_KEY,
        "status": "under_construction",
    },
    "applied_digital_phase_1_child": {
        "critical_it_mw": 75.0,
        "capacity_stage": "operational",
        "observed_date": "2026-07-01",
        "stable_key": _APPLIED_PHASE_KEY,
        "status": "operational",
    },
    "databank_iad5": {
        "critical_it_mw": 72.0,
        "capacity_stage": "planned",
        "observed_date": "2026-05-14",
        "stable_key": _DATABANK_IAD5_KEY,
        "status": "under_construction",
    },
    "qareeb_timeline": {
        "stable_key": _QAREEB_KEY,
        "observations": [
            {"observed_date": "2025-02-05", "status": "under_construction"},
            {"observed_date": "2026-01-13", "status": "commissioning"},
        ],
    },
    "stc_bahrain_timeline": {
        "stable_key": _STC_BAHRAIN_KEY,
        "observations": [
            {"observed_date": "2024-12-31", "status": "under_construction"},
            {"observed_date": "2025-12-31", "status": "operational"},
        ],
    },
    "v1_observation_id_inventory_preserved": True,
}


def _v2_observation_events(
    rows: list[dict[str, _CarrierAny]], stable_key: str
) -> list[tuple[str, str]]:
    return [
        (str(row["observed_date"]), str(row["status"]))
        for row in rows
        if row["entity_stable_key"] == stable_key
    ]


def _validate_v1_history_inventory(rows: list[dict[str, _CarrierAny]]) -> None:
    if _sha256_file(_V1_DEFINITION) != _V1_DEFINITION_SHA256:
        raise ConstructionTimelineError("frozen timeline v1 definition changed")
    if _sha256_file(_V1_BUNDLE / MANIFEST_FILENAME) != _V1_MANIFEST_SHA256:
        raise ConstructionTimelineError("frozen timeline v1 manifest changed")
    if tree_digest(_V1_BUNDLE) != _V1_TREE_SHA256:
        raise ConstructionTimelineError("frozen timeline v1 tree changed")
    with (_V1_BUNDLE / OBSERVATIONS_FILENAME).open(
        encoding="utf-8", newline=""
    ) as stream:
        predecessor = list(_carrier_csv.DictReader(stream))
    predecessor_ids = _CarrierCounter(row["observation_id"] for row in predecessor)
    current_ids = _CarrierCounter(str(row["observation_id"]) for row in rows)
    if predecessor_ids - current_ids or len(predecessor) != 426:
        raise ConstructionTimelineError("v62 dropped a frozen v1 observation history")


def _validate_v62_focus_contract(
    definition: _CarrierAny, rows: list[dict[str, _CarrierAny]]
) -> None:
    _validate_v1_history_inventory(rows)
    expected_events = {
        _QAREEB_KEY: [
            ("2025-02-05", "under_construction"),
            ("2026-01-13", "commissioning"),
        ],
        _APPLIED_PARENT_KEY: [("2026-04-08", "under_construction")],
        _APPLIED_PHASE_KEY: [("2026-07-01", "operational")],
        _DATABANK_IAD5_KEY: [("2026-05-14", "under_construction")],
        _STC_BAHRAIN_KEY: [
            ("2024-12-31", "under_construction"),
            ("2025-12-31", "operational"),
        ],
    }
    actual_events = {
        stable_key: _v2_observation_events(rows, stable_key)
        for stable_key in expected_events
    }
    if actual_events != expected_events:
        raise ConstructionTimelineError(
            f"v62 focus lifecycle contract differs: {actual_events}"
        )

    with (definition.open_seed_release / "entities.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        entities = {
            row["stable_key"]: row for row in _carrier_csv.DictReader(stream)
        }
    entity_ids = {
        stable_key: entities[stable_key]["entity_id"]
        for stable_key in (
            _APPLIED_PARENT_KEY,
            _APPLIED_PHASE_KEY,
            _DATABANK_IAD5_KEY,
        )
    }
    with (definition.open_seed_release / "capacity_estimates.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        capacities = {
            row["entity_id"]: (
                row["metric"],
                row["stage"],
                row["unit"],
                row["low"],
                row["base"],
                row["high"],
            )
            for row in _carrier_csv.DictReader(stream)
            if row["entity_id"] in set(entity_ids.values())
        }
    expected_capacities = {
        entity_ids[_APPLIED_PARENT_KEY]: (
            "critical_it_mw",
            "contracted",
            "MW",
            "150.0",
            "150.0",
            "150.0",
        ),
        entity_ids[_APPLIED_PHASE_KEY]: (
            "critical_it_mw",
            "operational",
            "MW",
            "75.0",
            "75.0",
            "75.0",
        ),
        entity_ids[_DATABANK_IAD5_KEY]: (
            "critical_it_mw",
            "planned",
            "MW",
            "72.0",
            "72.0",
            "72.0",
        ),
    }
    if capacities != expected_capacities:
        raise ConstructionTimelineError(
            f"v62 focus capacity identities differ: {capacities}"
        )


_v2_base_reconstruct_observations = _reconstruct_observations


def _reconstruct_observations(
    definition: _CarrierAny,
) -> list[dict[str, _CarrierAny]]:
    rows = _v2_base_reconstruct_observations(definition)
    _validate_v62_focus_contract(definition, rows)
    return rows


_v2_base_coverage = _coverage


def _coverage(
    observations: list[dict[str, _CarrierAny]],
    timelines: list[dict[str, _CarrierAny]],
    definition: _CarrierAny,
) -> dict[str, _CarrierAny]:
    result = _v2_base_coverage(observations, timelines, definition)
    result["v62_focus_contract"] = V62_FOCUS_CONTRACT
    return result


_v2_base_readme = _readme


def _readme(coverage: dict[str, _CarrierAny]) -> bytes:
    raw = _v2_base_readme(coverage)
    marker = (
        b"Name and country are the v62 release-projected entity labels used to make the "
    )
    if raw.count(marker) != 1:
        raise ConstructionTimelineError("v2 README insertion boundary changed")
    focus = (
        b"V62 preserves the Qareeb construction-to-commissioning history and the stc "
        b"Bahrain construction-to-operational history. Applied Digital's operational "
        b"75 MW Phase 1 child remains separate from its unchanged 150 MW contracted "
        b"parent under construction; DataBank IAD5 remains a distinct under-construction "
        b"project with 72 MW planned critical IT. These typed capacity facts validate "
        b"identity boundaries and are not converted into lifecycle milestones.\n\n"
    )
    return raw.replace(marker, focus + marker)
