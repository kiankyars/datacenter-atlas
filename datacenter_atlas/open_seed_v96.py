"""Governed, unpublished open-seed v96 successor carrier.

V96 is rooted only in the exact accepted v95 definition and release.  Its
planned 516-input inventory replaces the selected FIN04 predecessor in place,
then appends XTX Kajaani, Skygard OSL1 phase 2, three Gulf Data Hub Dubai
records, three accepted regional records, and NXDATA-3.  NXDATA-3 is eligible
only after its final accepted source and artifact exist and a live artifact
manifest pin has been reviewed into this carrier.

The carrier binds the accepted live NXDATA final lineage.  Its default command
is a private preflight.  Live publication is a separate, explicit-
authorization path with no fallback to a prospective or private staged source.
No-replace promotion, recursive identity checks, rollback, final chronology,
and exactly-two-replay gates protect that path.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence

from . import (
    gulf_data_hub_dubai_dso456_official_current_build_gap_20260722 as gdh,
)
from . import official_nordic_current_build_tranche_20260722 as nordic
from . import official_nxdata3_current_build_20260722 as nxdata
from . import open_seed_v69 as v69
from . import open_seed_v95 as v95
from .publication_release import build_release_documents
from . import (
    regional_official_an_khanh_oran_noor_current_build_tranche_20260722 as regional,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
BASE_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-22-v95.json"
BASE_RELEASE = ROOT / "releases/2026-07-22-open-seed-v95"
DEFINITION = SOURCES_ROOT / "open-seed-2026-07-22-v96.json"
RELEASE_ID = "2026-07-22-open-seed-v96"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v96.lock"
AS_OF = "2026-07-22"

BASE_RECORDED_AT = "2026-07-22T04:21:58Z"
BASE_INPUT_COUNT = 507
EXPECTED_INPUT_COUNT = 516
BASE_DEFINITION_PIN = (
    117_088,
    "e28cc9ad10229cbf718314f1bd1a4306e02faee1166dcbfbf93c01a1c82e8e15",
)
BASE_MANIFEST_PIN = (
    19_195,
    "1181fa215be08c130bf237107c68a461a4762e020b7120041f19cd705b6b7af6",
)
BASE_ENTITIES_PIN = (
    1_058_933,
    "038bfa4ef15e4e6494ac91fa835671105d45662c0acd6b6f5c3a5e750ad3e09d",
)
BASE_SOURCE_INPUTS_PIN = (
    432_685,
    "30572edcc50ecf82c5de57abf7a7e10275a09b879189334834a512d9280860d0",
)
BASE_TREE_SHA256 = "752593650007f602f2bd13f2bd0c3ac8702cdd74c4b6103ec2bdaa348c6ef17a"

FIN04_PREDECESSOR = "sources/curated-official-2026-07-20-atnorth-fin04-kouvola.json"
FIN04_PREDECESSOR_PIN = (
    15_068,
    "28773caea4d839386074e6bd3003953c75c9f1bbd3441442a83cfc2d9ca22fe4",
)
FIN04_SUCCESSOR = (
    "sources/curated-official-2026-07-22-atnorth-fin04-kouvola-"
    "currentness-successor.json"
)

NXDATA_SOURCE = (
    "sources/curated-official-2026-07-22-nxdata3-bucharest-current-build-successor.json"
)
NXDATA_SOURCE_PIN = (
    13_866,
    "1ed2d1999113ac32def96a319d5283865ef6f2cd9e37db1a4c2d5cbda03d3ab3",
)
NXDATA_ARTIFACT = ARTIFACT_ROOT / "official-nxdata3-current-build-2026-07-22-v1"
NXDATA_PROSPECTIVE_MANIFEST_PIN = (
    1_685,
    "a988438501524d4539371082eddd41c40a5ab134be9f4ac51de4513b9e907912",
)
NXDATA_PROSPECTIVE_RECORDED_AT = "2099-01-01T00:00:00Z"
NXDATA_PROSPECTIVE_TREE_SHA256 = (
    "89abace7844497ac7381b7b66e6925d1187af0e39b313920ea44d9d9abdf27b4"
)
# A real final artifact is recorded at a live publication timestamp.  Its exact
# manifest pin must be supplied by a later reviewed change; the deterministic
# 2099 preflight pin above is provenance only and can never satisfy this gate.
NXDATA_LIVE_RECORDED_AT = "2026-07-22T04:55:42Z"
NXDATA_LIVE_MANIFEST_PIN: tuple[int, str] | None = (
    1_685,
    "c5a14d58b68658d718e059fc6df479caaca8a6b1698607323b34ca20a89fc34c",
)
NXDATA_LIVE_TREE_SHA256: str | None = (
    "e1a63ac778d9a9029e77aefdc31a107353e1364efa583f681760d89f84b8a0a3"
)


class OpenSeedV96Error(RuntimeError):
    """Raised when a v96 lineage, semantic, or prepublication fuse fails."""


class OpenSeedV96ReadinessError(OpenSeedV96Error):
    """Raised when an accepted final input required by v96 is not ready."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ArtifactSpec:
    label: str
    artifact: Path
    recorded_at: str
    manifest_pin: tuple[int, str]
    logical_tree_sha256: str
    physical_tree_sha256: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class SourceSpec:
    relative: str
    pin: tuple[int, str]
    ctime_ns: int
    artifact_label: str


NORDIC_SOURCES = (
    FIN04_SUCCESSOR,
    "sources/curated-official-2026-07-22-xtx-kajaani-second-data-center-"
    "current-build.json",
    "sources/curated-official-2026-07-22-skygard-osl1-phase-2-current-build.json",
)
GDH_SOURCES = tuple(gdh.SOURCE_PATHS)
REGIONAL_SOURCES = (
    "sources/curated-official-2026-07-22-viettel-an-khanh-current-build.json",
    "sources/curated-official-2026-07-22-oran-ai-data-center-current-build.json",
    "sources/curated-official-2026-07-22-noor-capital-gardens-current-build.json",
)

ARTIFACT_SPECS = (
    ArtifactSpec(
        "nordic",
        nordic.ARTIFACT,
        "2026-07-22T04:29:37Z",
        (
            1_644,
            "52826c4be84e4cbb19d3a572e812ffbf0ecac8de1d26f970eb533cdc39eb5bef",
        ),
        "b05cabefa306e127853b2f27b0991dc0b29b35f388b2f112d908b63bbdedda9c",
        "9682b4931c902d9a5d7db82cbf83d1de75af62731d55c4525c987ebc9b0b5157",
        NORDIC_SOURCES,
    ),
    ArtifactSpec(
        "gdh",
        gdh.ARTIFACT,
        "2026-07-22T04:44:46Z",
        (
            1_960,
            "d64ccaec5a3906775a61b0567473c3244d69c1a33d604718fb0ba0e81e00c378",
        ),
        "d43fe11ac5a4c7a9a98b1ffd8693e729f16328eaf739f61bacec546c7374792e",
        "62f161cd98996d3e76e753f8a0ee8603217e52cfa2db53af1bc121cffcd7e766",
        GDH_SOURCES,
    ),
    ArtifactSpec(
        "regional",
        regional.ARTIFACT,
        "2026-07-22T04:46:44Z",
        (
            1_715,
            "44f5929102931cd7acc2a4cb6a8eaa70d9230266b380ec388d07db6f66358076",
        ),
        "7b2ccf76395851c375fb99169e95642bbe9a0fb2535cf5b0fbe0fa38c7f344af",
        "b5e932bf440df14142487204b4a05f2854336fcda7c5accbff843ebcf447dc1c",
        REGIONAL_SOURCES,
    ),
)

SOURCE_SPECS = (
    SourceSpec(
        FIN04_SUCCESSOR,
        (
            19_173,
            "ccba18dd2b8398c775e1b435830037a29e027482518c125419607ebcdb1e470e",
        ),
        1_784_694_577_049_573_430,
        "nordic",
    ),
    SourceSpec(
        NORDIC_SOURCES[1],
        (
            7_793,
            "dfd8908152eb6b6c937ba4c0b1ced909685733d90ab50e1a826b3e23ca937976",
        ),
        1_784_694_577_049_348_805,
        "nordic",
    ),
    SourceSpec(
        NORDIC_SOURCES[2],
        (
            7_152,
            "77fc3d8b702b06eb6f5941d08f12ef542ee5d545184e33a43fb2b3ab917291ad",
        ),
        1_784_694_577_049_473_888,
        "nordic",
    ),
    SourceSpec(
        GDH_SOURCES[0],
        (
            4_560,
            "64cddc09bdec92bd4ff2b17679452d13ebb607e4f1804ac80e8ad549a5d67c97",
        ),
        1_784_695_486_161_700_381,
        "gdh",
    ),
    SourceSpec(
        GDH_SOURCES[1],
        (
            4_560,
            "5c7247bd51fa7fd7b4e338d9ff6a6c6e7c4bfa39f2bb8d9fff45d73302b8e440",
        ),
        1_784_695_486_161_822_714,
        "gdh",
    ),
    SourceSpec(
        GDH_SOURCES[2],
        (
            4_560,
            "ac517277fcc182bc1dee02f9d000e7fdfa381aa3471b3e7c6eaa01690b6ea006",
        ),
        1_784_695_486_161_919_923,
        "gdh",
    ),
    SourceSpec(
        REGIONAL_SOURCES[0],
        (
            5_538,
            "fe220d936abcef27f2099123d4486a541385b97c4ded69ea2fd4c4078177b8d1",
        ),
        1_784_695_604_035_318_912,
        "regional",
    ),
    SourceSpec(
        REGIONAL_SOURCES[1],
        (
            7_401,
            "d71be15c1fb19d3c1d90d6341dcbf809f7c2ab9c24b2afc252c09d902020b3b8",
        ),
        1_784_695_604_035_446_287,
        "regional",
    ),
    SourceSpec(
        REGIONAL_SOURCES[2],
        (
            4_951,
            "9b771b6e0817d68c010775c5f8a2f45745279a30bddef3666ea975418ac7dbbc",
        ),
        1_784_695_604_035_548_079,
        "regional",
    ),
)

APPEND_ORDER = (
    NORDIC_SOURCES[1],
    NORDIC_SOURCES[2],
    *GDH_SOURCES,
    *REGIONAL_SOURCES,
    NXDATA_SOURCE,
)
ALL_SUCCESSOR_ORDER = (FIN04_SUCCESSOR, *APPEND_ORDER)
NON_NXDATA_PINS = {spec.relative: spec.pin for spec in SOURCE_SPECS}

FIN04_KEYS = frozenset(
    {
        "curated:atnorth-fin04-kouvola-campus",
        "curated:atnorth-fin04-kouvola-campus:phase-1",
    }
)
NXDATA_KEYS = frozenset({nxdata.CAMPUS_KEY, nxdata.PROJECT_KEY})
NXDATA_PROJECT_ID = "df2b8f33-9c46-5f6a-9853-b47474606979"
NXDATA_TECHNICAL_EVIDENCE_ID = "7d5ca79b-2c93-5ac0-9cb6-7d1a30eda120"
ORAN_PROJECT_KEY = "curated:oran-ai-data-center-campus:current-build"

EXPECTED_LIFECYCLE = frozenset(
    {
        (
            "curated:atnorth-fin04-kouvola-campus:phase-1",
            "under_construction",
            "2026-07-21",
            "authoritative_physical_status_update",
        ),
        (
            "curated:xtx-markets-kajaani-data-center-campus:second-data-center",
            "under_construction",
            "2026-06-25",
            "authoritative_physical_status_update",
        ),
        (
            "curated:skygard-osl1-hovinbyen-campus:phase-2",
            "under_construction",
            "2026-06-16",
            "authoritative_construction_start",
        ),
        *(
            (
                f"curated:gulf-data-hub-dubai-dso{number}-data-center:"
                "official-under-construction-build",
                "under_construction",
                "2026-07-22",
                "authoritative_physical_status_update",
            )
            for number in (4, 5, 6)
        ),
        (
            "curated:viettel-an-khanh-data-center-campus:current-build",
            "under_construction",
            "2025-08-19",
            "authoritative_construction_start",
        ),
        (
            ORAN_PROJECT_KEY,
            "under_construction",
            "2025-03-16",
            "authoritative_construction_start",
        ),
        (
            "curated:noor-capital-gardens-data-center:current-build",
            "under_construction",
            "2026-07-22",
            "authoritative_physical_status_update",
        ),
        (
            nxdata.PROJECT_KEY,
            "under_construction",
            "2026-06-02",
            "authoritative_physical_status_update",
        ),
    }
)
EXPECTED_CAPACITIES = frozenset(
    {
        (nxdata.PROJECT_KEY, "gross_facility_mw", "design", "MW", 5.0),
        (nxdata.PROJECT_KEY, "critical_it_mw", "design", "MW", 3.0),
        (nxdata.PROJECT_KEY, "pue", "design", "ratio", 1.3),
    }
)
EXPECTED_MODELS = frozenset({(nxdata.PROJECT_KEY, "colocation")})
EXPECTED_CAPACITY_DETAILS = frozenset(
    {
        (
            nxdata.PROJECT_KEY,
            metric,
            "design",
            unit,
            value,
            value,
            value,
            "2025-07-11",
            "reported",
            "nxdata3-technical-brochure-captured-2026-07-22",
        )
        for metric, unit, value in (
            ("gross_facility_mw", "MW", 5.0),
            ("critical_it_mw", "MW", 3.0),
            ("pue", "ratio", 1.3),
        )
    }
)
EXPECTED_MODEL_DETAILS = frozenset(
    {
        (
            nxdata.PROJECT_KEY,
            "colocation",
            "2025-07-11",
            "company_disclosure",
            "nxdata3-technical-brochure-captured-2026-07-22",
        )
    }
)
EXPECTED_DB_CAPACITY_DETAILS = frozenset(
    row[:-1] + (NXDATA_TECHNICAL_EVIDENCE_ID,) for row in EXPECTED_CAPACITY_DETAILS
)
EXPECTED_DB_MODEL_DETAILS = frozenset(
    row[:-1] + (NXDATA_TECHNICAL_EVIDENCE_ID,) for row in EXPECTED_MODEL_DETAILS
)
EXPECTED_STALE_PROJECT_KEYS = frozenset(
    {*v95.STALE_SUPPRESSED_PROJECT_KEYS, ORAN_PROJECT_KEY}
)
EXPECTED_NEW_EVIDENCE_COUNT = 16
EXPECTED_NEW_ENTITY_COUNT = 18

FIN04_PROJECT_KEY = "curated:atnorth-fin04-kouvola-campus:phase-1"
FIN04_OLD_EVIDENCE_KEY = (
    "atnorth-fin04-current-construction-2026-03-26-captured-2026-07-20"
)
FIN04_NEW_EVIDENCE_KEY = (
    "yit-atnorth-fin04-immediate-construction-2026-07-21-captured-2026-07-22"
)
FIN04_OLD_EVIDENCE_ID = "97ae0303-4e21-5324-a54e-48420a0fba5e"
FIN04_NEW_EVIDENCE_ID = "a49b85ce-f91a-56b8-af06-3b663336bdf8"

ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:xtx-markets-kajaani-data-center-campus",
        "curated:xtx-markets-kajaani-data-center-campus:second-data-center",
        "curated:skygard-osl1-hovinbyen-campus",
        "curated:skygard-osl1-hovinbyen-campus:phase-2",
        "curated:gulf-data-hub-dubai-dso4-data-center",
        "curated:gulf-data-hub-dubai-dso4-data-center:official-under-construction-build",
        "curated:gulf-data-hub-dubai-dso5-data-center",
        "curated:gulf-data-hub-dubai-dso5-data-center:official-under-construction-build",
        "curated:gulf-data-hub-dubai-dso6-data-center",
        "curated:gulf-data-hub-dubai-dso6-data-center:official-under-construction-build",
        "curated:viettel-an-khanh-data-center-campus",
        "curated:viettel-an-khanh-data-center-campus:current-build",
        "curated:oran-ai-data-center-campus",
        ORAN_PROJECT_KEY,
        "curated:noor-capital-gardens-data-center",
        "curated:noor-capital-gardens-data-center:current-build",
        nxdata.CAMPUS_KEY,
        nxdata.PROJECT_KEY,
    }
)
ADDED_PROJECT_KEYS = frozenset(
    project
    for project, _status, _as_of, _method in EXPECTED_LIFECYCLE
    if project != FIN04_PROJECT_KEY
)
EXPORTED_EVIDENCE_KEYS = frozenset(
    {
        FIN04_NEW_EVIDENCE_KEY,
        "bravida-xtx-kajaani-second-work-underway-2026-06-25-captured-2026-07-22",
        "sentia-hent-osl1-phase-2-immediate-start-2026-06-16-captured-2026-07-22",
        "skygard-osl1-hovinbyen-current-page-captured-2026-07-22",
        "gulf-data-hub-dubai-dso4-official-status-page-captured-2026-07-22",
        "gulf-data-hub-dubai-dso5-official-status-page-captured-2026-07-22",
        "gulf-data-hub-dubai-dso6-official-status-page-captured-2026-07-22",
        "vietnam-government-portal-viettel-an-khanh-groundbreaking-2025-08-19-captured-2026-07-22",
        "algerian-radio-oran-ai-data-center-cornerstone-2025-03-16-captured-2026-07-22",
        "square-engineering-noor-data-center-ongoing-captured-2026-07-22",
        "nxdata3-project-page-design-captured-2026-07-22",
        "nxdata3-technical-brochure-captured-2026-07-22",
        "nxdata3-official-foundation-progress-2026-06-02-captured-2026-07-22",
    }
)

EXPECTED_DATABASE_COUNTS = {
    "entities": 1_047,
    "evidence": 883,
    "campuses": 542,
    "projects": 505,
    "entity_snapshots": 1_072,
    "lifecycle_observations": 603,
    "operating_model_observations": 77,
    "workload_observations": 136,
    "capacity_estimates": 571,
}
INTERNAL_DELTA = {
    "entities": 18,
    "entity_replacements": 2,
    "evidence": 16,
    "entity_snapshots": 18,
    "entity_snapshot_replacements": 2,
    "lifecycle_observations": 9,
    "lifecycle_replacements": 1,
    "operating_model_observations": 1,
    "workload_observations": 0,
    "capacity_estimates": 3,
}
PUBLIC_DELTA = {
    "entities": 18,
    "entity_replacements": 2,
    "evidence": 12,
    "evidence_replacements": 1,
    "lifecycle_freshness": 9,
    "lifecycle_freshness_replacements": 1,
    "construction_pipeline": 8,
    "construction_pipeline_replacements": 1,
    "construction_source_signals": 9,
    "construction_source_signal_replacements": 1,
    "capacity_estimates": 3,
    "source_input_rows": 12,
    "source_input_replacements": 1,
}
GOVERNED_REPLACEMENTS = {
    "curated_definition": {
        "index": 174,
        "removed_path": FIN04_PREDECESSOR,
        "selected_path": FIN04_SUCCESSOR,
    },
    "entity_stable_keys": sorted(FIN04_KEYS),
    "lifecycle_stable_keys": [FIN04_PROJECT_KEY],
    "removed_evidence_id": FIN04_OLD_EVIDENCE_ID,
    "selected_evidence_id": FIN04_NEW_EVIDENCE_ID,
    "removed_evidence_key": FIN04_OLD_EVIDENCE_KEY,
    "selected_evidence_key": FIN04_NEW_EVIDENCE_KEY,
}
STALE_POLICY = {
    "policy_version": 1,
    "stable_keys": sorted(EXPECTED_STALE_PROJECT_KEYS),
    "entities_status_fields_blank": list(v95.STATUS_FIELDS),
    "geojson_status_fields_null": list(v95.STATUS_FIELDS),
    "construction_pipeline_excluded": True,
    "lifecycle_freshness_retained": True,
    "construction_source_signals_retained": True,
    "required_freshness_class": "stale_over_365_days",
    "current_status_classification": "unknown",
    "current_construction_claim": False,
    "successor_rehydration_forbidden": True,
}
COORDINATE_BOUNDARY = {
    **v95.COORDINATE_BOUNDARY,
    "v96_coordinates_added": [],
}
ATTRIBUTION_ADDITIONS = frozenset(
    {
        "Algerian Radio",
        "Bravida",
        "Government Portal of Vietnam",
        "Gulf Data Hub",
        "NXDATA",
        "NXDATA SRL",
        "Sentia",
        "Skygard",
        "Square Engineering",
        "YIT",
    }
)

V96_README = """## Governed v96 successor boundary

Open seed v96 is the exact governed accepted-v95 successor. It replaces the
selected FIN04 source at curated-input index 174 with its accepted 2026-07-21
currentness successor, then appends exactly nine accepted current-build inputs.
The predecessor remains immutable lineage and is not selected.

Every unrelated v95 public row remains byte-identical. Only the two FIN04
entity/current rows and their current evidence, freshness, pipeline,
source-signal, GeoJSON, and source-input projections are replaced. V96 adds 18
entities, 16 internal evidence records, nine lifecycle observations, one
generic colocation observation, and three NXDATA design metrics. It adds no
workload, annual-energy, WUE, coordinate, footprint, or inferred geometry.

Jakarta, Hanoi, and Oran retain dated historical lifecycle and source-signal
history, but their public entity and GeoJSON status fields are blank/null and
they are omitted from the construction pipeline. Their current status remains unknown;
downstream successor projections may not silently rehydrate them.
"""

PROMOTION_CONTRACT = {
    "atomic_no_replace_required": True,
    "definition_and_release_same_filesystem_as_final_parent": True,
    "identity_checked_before_and_after_promotion": True,
    "rollback_uses_atomic_no_replace": True,
    "rollback_refuses_identity_mismatch": True,
    "replay_count": 2,
    "publication_implemented": True,
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pin(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), _sha256(raw)


def _canonical(value: Any, *, sort_keys: bool = False) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=sort_keys, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _read_json(
    path: Path, *, mode: int | None = None, sort_keys: bool = False
) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise OpenSeedV96Error(f"ordinary JSON file is absent: {path}")
    if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
        raise OpenSeedV96Error(f"JSON mode differs: {path}")
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict) or raw != _canonical(value, sort_keys=sort_keys):
        raise OpenSeedV96Error(f"JSON is not canonical: {path}")
    return value


def _validate_base() -> dict[str, Any]:
    if (
        BASE_DEFINITION != v95.DEFINITION
        or BASE_RELEASE != v95.RELEASE
        or BASE_DEFINITION.is_symlink()
        or not BASE_DEFINITION.is_file()
        or stat.S_IMODE(BASE_DEFINITION.stat().st_mode) != 0o444
        or BASE_RELEASE.is_symlink()
        or not BASE_RELEASE.is_dir()
        or stat.S_IMODE(BASE_RELEASE.stat().st_mode) != 0o555
        or _pin(BASE_DEFINITION) != BASE_DEFINITION_PIN
        or _pin(BASE_RELEASE / "manifest.json") != BASE_MANIFEST_PIN
        or _pin(BASE_RELEASE / "entities.csv") != BASE_ENTITIES_PIN
        or _pin(BASE_RELEASE / "source_inputs.json") != BASE_SOURCE_INPUTS_PIN
        or v69.tree_digest(BASE_RELEASE) != BASE_TREE_SHA256
    ):
        raise OpenSeedV96Error("accepted v95 base pin differs")
    definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
    manifest = json.loads((BASE_RELEASE / "manifest.json").read_text())
    if (
        definition.get("release_id") != v95.RELEASE_ID
        or definition.get("build", {}).get("recorded_at") != BASE_RECORDED_AT
        or len(definition.get("curated_inputs", [])) != BASE_INPUT_COUNT
        or manifest.get("recorded_at") != BASE_RECORDED_AT
        or manifest.get("entities") != 1_029
    ):
        raise OpenSeedV96Error("accepted v95 base semantics differ")
    for path in BASE_RELEASE.iterdir():
        if (
            path.is_symlink()
            or not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != 0o444
        ):
            raise OpenSeedV96Error("accepted v95 member mode differs")
    for filename, record in manifest["files"].items():
        if _pin(BASE_RELEASE / filename) != (
            record["bytes"],
            record["sha256"],
        ):
            raise OpenSeedV96Error(f"accepted v95 member pin differs: {filename}")
    return definition


def _artifact_snapshot_records(spec: ArtifactSpec) -> dict[str, dict[str, Any]]:
    snapshot = json.loads(
        (spec.artifact / "source-snapshot.json").read_text(encoding="utf-8")
    )
    records = snapshot.get("source_records")
    if not isinstance(records, list):
        raise OpenSeedV96Error(f"{spec.label} source snapshot is invalid")
    result = {row.get("path"): row for row in records if isinstance(row, dict)}
    if set(result) != set(spec.sources):
        raise OpenSeedV96Error(f"{spec.label} artifact source lineage differs")
    return result


def _validate_artifact(spec: ArtifactSpec) -> dict[str, Any]:
    if spec.label == "nordic":
        paths = {name: SOURCES_ROOT / name for name in nordic.SOURCE_FILENAMES}
        manifest = nordic._validate_artifact(
            spec.artifact,
            paths,
            frozen=True,
            require_live=True,
            require_final_chronology=True,
        )
    elif spec.label == "gdh":
        result = gdh.validate_published_gdh_dubai_dso456()
        manifest = result["manifest"]
    elif spec.label == "regional":
        paths = {name: SOURCES_ROOT / name for name in regional.SOURCE_FILENAMES}
        manifest = regional._validate_artifact(
            spec.artifact,
            paths,
            frozen=True,
            require_live=True,
            require_final_chronology=True,
        )
    else:  # pragma: no cover - closed static specification
        raise OpenSeedV96Error(f"unknown artifact label: {spec.label}")
    manifest_raw = (spec.artifact / "manifest.json").read_bytes()
    if (
        (len(manifest_raw), _sha256(manifest_raw)) != spec.manifest_pin
        or manifest.get("recorded_at") != spec.recorded_at
        or manifest.get("tree_sha256") != spec.logical_tree_sha256
        or v69.tree_digest(spec.artifact) != spec.physical_tree_sha256
        or manifest.get("accepted") is not True
        or manifest.get("published") is not True
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
    ):
        raise OpenSeedV96Error(f"{spec.label} accepted artifact pin differs")
    return manifest


def _validate_non_nxdata_inputs() -> dict[str, dict[str, Any]]:
    artifact_by_label = {spec.label: spec for spec in ARTIFACT_SPECS}
    snapshots: dict[str, dict[str, Any]] = {}
    for spec in ARTIFACT_SPECS:
        _validate_artifact(spec)
        snapshots.update(_artifact_snapshot_records(spec))
    documents: dict[str, dict[str, Any]] = {}
    for spec in SOURCE_SPECS:
        path = ROOT / spec.relative
        document = _read_json(path, mode=0o444)
        metadata = path.stat(follow_symlinks=False)
        artifact = artifact_by_label[spec.artifact_label]
        recorded = datetime.fromisoformat(artifact.recorded_at.replace("Z", "+00:00"))
        snapshot = snapshots.get(spec.relative)
        if (
            _pin(path) != spec.pin
            or metadata.st_ctime_ns != spec.ctime_ns
            or max(metadata.st_birthtime, metadata.st_mtime)
            > recorded.timestamp() + 1e-6
            or metadata.st_ctime + 1e-6 < recorded.timestamp()
            or not isinstance(snapshot, dict)
            or (snapshot.get("bytes"), snapshot.get("sha256")) != spec.pin
            or snapshot.get("accepted") is not True
            or snapshot.get("published") is not True
        ):
            raise OpenSeedV96Error(f"selected source lineage differs: {spec.relative}")
        documents[spec.relative] = document
    if tuple(documents) != tuple(spec.relative for spec in SOURCE_SPECS):
        raise OpenSeedV96Error("non-NXDATA source order differs")
    return documents


def _nxdata_final_state() -> tuple[bool, list[str]]:
    final_source = ROOT / NXDATA_SOURCE
    paths = [final_source, NXDATA_ARTIFACT]
    present = [
        str(path.relative_to(ROOT))
        for path in paths
        if path.exists() or path.is_symlink()
    ]
    return len(present) == 2, present


def _validate_nxdata_final() -> dict[str, Any]:
    complete, present = _nxdata_final_state()
    if not complete:
        raise OpenSeedV96ReadinessError(
            "nxdata_final_absent",
            f"v96 requires both accepted NXDATA final paths; present={present!r}",
        )
    if NXDATA_LIVE_MANIFEST_PIN is None or NXDATA_LIVE_TREE_SHA256 is None:
        raise OpenSeedV96ReadinessError(
            "nxdata_live_pin_unreviewed",
            "v96 requires the exact live NXDATA artifact manifest and tree pins; "
            "the 2099 preflight pin is not accepted lineage",
        )
    source = ROOT / NXDATA_SOURCE
    if _pin(source) != NXDATA_SOURCE_PIN:
        raise OpenSeedV96Error("NXDATA accepted final source pin differs")
    try:
        manifest = nxdata._validate_artifact(
            NXDATA_ARTIFACT,
            source,
            frozen=True,
            require_live=True,
            require_final_chronology=True,
        )
    except nxdata.NXDataPublicationError as error:
        raise OpenSeedV96Error(f"NXDATA accepted artifact invalid: {error}") from error
    manifest_raw = (NXDATA_ARTIFACT / "manifest.json").read_bytes()
    if (
        (len(manifest_raw), _sha256(manifest_raw)) != NXDATA_LIVE_MANIFEST_PIN
        or v69.tree_digest(NXDATA_ARTIFACT) != NXDATA_LIVE_TREE_SHA256
        or manifest.get("recorded_at") != NXDATA_LIVE_RECORDED_AT
        or manifest.get("accepted") is not True
        or manifest.get("published") is not True
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or manifest.get("recorded_at") == NXDATA_PROSPECTIVE_RECORDED_AT
        or (len(manifest_raw), _sha256(manifest_raw)) == NXDATA_PROSPECTIVE_MANIFEST_PIN
    ):
        raise OpenSeedV96Error("NXDATA live artifact pin differs")
    return _read_json(source, mode=0o444)


def _planned_documents(
    accepted: Mapping[str, Mapping[str, Any]],
    *,
    include_prospective_nxdata: bool,
) -> dict[str, dict[str, Any]]:
    documents = {relative: dict(document) for relative, document in accepted.items()}
    if include_prospective_nxdata:
        prospective = nxdata.expected_source_document()
        raw = nxdata._canonical(prospective)
        if (len(raw), _sha256(raw)) != NXDATA_SOURCE_PIN:
            raise OpenSeedV96Error("prospective NXDATA source contract drifted")
        documents[NXDATA_SOURCE] = prospective
    return documents


def _claim_contract(documents: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if tuple(documents) != ALL_SUCCESSOR_ORDER:
        raise OpenSeedV96Error("v96 successor document order differs")
    stable_keys = {
        document[entity]["stable_key"]
        for document in documents.values()
        for entity in ("campus", "project")
    }
    evidence_keys = [
        row["key"] for document in documents.values() for row in document["evidence"]
    ]
    lifecycle = {
        (
            document[row["entity"]]["stable_key"],
            row["value"],
            row["as_of_date"],
            row["method"],
        )
        for document in documents.values()
        for row in document["lifecycle"]
    }
    capacities = {
        (
            document[row["entity"]]["stable_key"],
            row["metric"],
            row["stage"],
            row["unit"],
            float(row["base"]),
        )
        for document in documents.values()
        for row in document["capacities"]
    }
    models = {
        (document[row["entity"]]["stable_key"], row["value"])
        for document in documents.values()
        for row in document["operating_models"]
    }
    workloads = [
        row for document in documents.values() for row in document["workloads"]
    ]
    capacity_details = {
        (
            document[row["entity"]]["stable_key"],
            row["metric"],
            row["stage"],
            row["unit"],
            float(row["low"]),
            float(row["base"]),
            float(row["high"]),
            row["as_of_date"],
            row["method"],
            row["evidence_key"],
        )
        for document in documents.values()
        for row in document["capacities"]
    }
    model_details = {
        (
            document[row["entity"]]["stable_key"],
            row["value"],
            row["as_of_date"],
            row["method"],
            row["evidence_key"],
        )
        for document in documents.values()
        for row in document["operating_models"]
    }
    if (
        len(stable_keys) != 20
        or len(evidence_keys) != 19
        or len(set(evidence_keys)) != 19
        or lifecycle != EXPECTED_LIFECYCLE
        or capacities != EXPECTED_CAPACITIES
        or models != EXPECTED_MODELS
        or capacity_details != EXPECTED_CAPACITY_DETAILS
        or model_details != EXPECTED_MODEL_DETAILS
        or workloads
    ):
        raise OpenSeedV96Error("v96 source claim contract differs")
    for relative, document in documents.items():
        for entity in ("campus", "project"):
            row = document[entity]
            if row["coordinates"] is not None or row["geometry"] is not None:
                raise OpenSeedV96Error(f"v96 unexpected coordinate: {relative}")
        for row in document["capacities"]:
            if row["metric"] in {"annual_energy_mwh", "wue"}:
                raise OpenSeedV96Error("v96 normalized energy or WUE")
            if row["metric"] == "pue" and (
                row["unit"] != "ratio" or row["stage"] != "design"
            ):
                raise OpenSeedV96Error("v96 PUE typing differs")
    stale = {
        project
        for project, _status, as_of, _method in lifecycle
        if (date.fromisoformat(AS_OF) - date.fromisoformat(as_of)).days > 365
    }
    if stale != {ORAN_PROJECT_KEY}:
        raise OpenSeedV96Error("v96 newly stale source boundary differs")
    return {
        "stable_keys": stable_keys,
        "evidence_keys": frozenset(evidence_keys),
        "lifecycle": lifecycle,
        "capacities": capacities,
        "models": models,
        "newly_stale": stale,
    }


def _base_evidence_keys(base: Mapping[str, Any]) -> set[str]:
    evidence: set[str] = set()
    for row in base["curated_inputs"]:
        path = ROOT / row["path"]
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        evidence.update(
            item["key"]
            for item in document.get("evidence", [])
            if isinstance(item, dict) and isinstance(item.get("key"), str)
        )
    return evidence


def planned_selection(
    base: Mapping[str, Any], documents: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, str]]:
    """Return the exact prospective 516 rows without asserting NXDATA readiness."""

    rows = base.get("curated_inputs")
    if (
        base.get("release_id") != v95.RELEASE_ID
        or not isinstance(rows, list)
        or len(rows) != BASE_INPUT_COUNT
        or any(set(row) != {"path", "sha256"} for row in rows)
    ):
        raise OpenSeedV96Error("accepted v95 curated inventory differs")
    predecessor_indices = [
        index for index, row in enumerate(rows) if row["path"] == FIN04_PREDECESSOR
    ]
    if predecessor_indices != [174] or rows[174]["sha256"] != FIN04_PREDECESSOR_PIN[1]:
        raise OpenSeedV96Error("v95 FIN04 predecessor selection differs")
    if FIN04_SUCCESSOR in {row["path"] for row in rows}:
        raise OpenSeedV96Error("FIN04 successor already exists in v95")
    if tuple(documents) != ALL_SUCCESSOR_ORDER:
        raise OpenSeedV96Error("planned successor order differs")
    pins = {**NON_NXDATA_PINS, NXDATA_SOURCE: NXDATA_SOURCE_PIN}
    selected = [dict(row) for row in rows]
    selected[174] = {"path": FIN04_SUCCESSOR, "sha256": pins[FIN04_SUCCESSOR][1]}
    selected.extend(
        {"path": relative, "sha256": pins[relative][1]} for relative in APPEND_ORDER
    )
    if (
        selected[:174] != rows[:174]
        or selected[175:BASE_INPUT_COUNT] != rows[175:]
        or len(selected) != EXPECTED_INPUT_COUNT
        or len({row["path"] for row in selected}) != EXPECTED_INPUT_COUNT
        or [row["path"] for row in selected[BASE_INPUT_COUNT:]] != list(APPEND_ORDER)
    ):
        raise OpenSeedV96Error("v96 replacement/append inventory differs")

    base_stable = {
        row["stable_key"] for row in v95._csv_rows(BASE_RELEASE / "entities.csv")
    }
    contract = _claim_contract(documents)
    added_stable = contract["stable_keys"] - FIN04_KEYS
    if (
        not FIN04_KEYS <= base_stable
        or base_stable & added_stable
        or len(added_stable) != EXPECTED_NEW_ENTITY_COUNT
    ):
        raise OpenSeedV96Error("v96 stable-key collision boundary differs")
    predecessor = _read_json(ROOT / FIN04_PREDECESSOR)
    predecessor_evidence = [row["key"] for row in predecessor["evidence"]]
    successor_evidence = [row["key"] for row in documents[FIN04_SUCCESSOR]["evidence"]]
    base_evidence = _base_evidence_keys(base)
    overlap = contract["evidence_keys"] & base_evidence
    if (
        successor_evidence[:-1] != predecessor_evidence
        or overlap != set(predecessor_evidence)
        or len(contract["evidence_keys"] - base_evidence) != EXPECTED_NEW_EVIDENCE_COUNT
    ):
        raise OpenSeedV96Error("v96 evidence collision/replacement boundary differs")
    return selected


def readiness_report() -> dict[str, Any]:
    """Validate every accepted lineage and report preflight readiness."""

    base = _validate_base()
    accepted = _validate_non_nxdata_inputs()
    planned_documents = _planned_documents(accepted, include_prospective_nxdata=True)
    selected = planned_selection(base, planned_documents)
    complete, present = _nxdata_final_state()
    barrier = None
    if not complete:
        barrier = "nxdata_final_absent"
    elif NXDATA_LIVE_MANIFEST_PIN is None or NXDATA_LIVE_TREE_SHA256 is None:
        barrier = "nxdata_live_pin_unreviewed"
    if barrier is None:
        _validate_nxdata_final()
    return {
        "status": "blocked" if barrier else "ready",
        "barrier": barrier,
        "base_release_id": v95.RELEASE_ID,
        "base_definition_sha256": BASE_DEFINITION_PIN[1],
        "base_tree_sha256": BASE_TREE_SHA256,
        "base_input_count": BASE_INPUT_COUNT,
        "planned_input_count": len(selected),
        "fin04_replacement_index": 174,
        "fin04_predecessor_removed": FIN04_PREDECESSOR
        not in {row["path"] for row in selected},
        "fin04_successor_selected_once": sum(
            row["path"] == FIN04_SUCCESSOR for row in selected
        )
        == 1,
        "append_order": list(APPEND_ORDER),
        "accepted_artifacts_validated": [
            *(spec.label for spec in ARTIFACT_SPECS),
            "nxdata",
        ],
        "accepted_non_nxdata_sources": len(accepted),
        "nxdata_final_paths_present": present,
        "nxdata_prospective_source_pin": {
            "path": NXDATA_SOURCE,
            "bytes": NXDATA_SOURCE_PIN[0],
            "sha256": NXDATA_SOURCE_PIN[1],
        },
        "nxdata_prospective_artifact_pin_not_accepted": {
            "recorded_at": NXDATA_PROSPECTIVE_RECORDED_AT,
            "manifest_bytes": NXDATA_PROSPECTIVE_MANIFEST_PIN[0],
            "manifest_sha256": NXDATA_PROSPECTIVE_MANIFEST_PIN[1],
            "tree_sha256": NXDATA_PROSPECTIVE_TREE_SHA256,
        },
        "nxdata_live_artifact_pin": {
            "recorded_at": NXDATA_LIVE_RECORDED_AT,
            "manifest_bytes": NXDATA_LIVE_MANIFEST_PIN[0]
            if NXDATA_LIVE_MANIFEST_PIN
            else None,
            "manifest_sha256": NXDATA_LIVE_MANIFEST_PIN[1]
            if NXDATA_LIVE_MANIFEST_PIN
            else None,
            "tree_sha256": NXDATA_LIVE_TREE_SHA256,
        },
        "stale_status_suppression_required": sorted(EXPECTED_STALE_PROJECT_KEYS),
        "promotion_contract": dict(PROMOTION_CONTRACT),
        "final_definition_absent": not DEFINITION.exists(),
        "final_release_absent": not RELEASE.exists(),
        "publication_lock_absent": not PUBLICATION_LOCK.exists(),
    }


def require_readiness() -> dict[str, Any]:
    report = readiness_report()
    if report["barrier"] == "nxdata_final_absent":
        _validate_nxdata_final()
    if report["barrier"] == "nxdata_live_pin_unreviewed":
        _validate_nxdata_final()
    nx_document = _validate_nxdata_final()
    accepted = _validate_non_nxdata_inputs()
    documents = {**accepted, NXDATA_SOURCE: nx_document}
    planned_selection(_validate_base(), documents)
    return report


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _csv_text(template: str, rows: Sequence[Mapping[str, str]]) -> str:
    reader = csv.DictReader(io.StringIO(template))
    if reader.fieldnames is None:
        raise OpenSeedV96Error("CSV template lacks a header")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=reader.fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _base_paths(base: Mapping[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for row in base["curated_inputs"]:
        path = ROOT / row["path"]
        if path.is_symlink() or not path.is_file() or v69.sha256(path) != row["sha256"]:
            raise OpenSeedV96Error(f"accepted v95 input pin differs: {row['path']}")
        paths.append(path)
    return paths


def selected_inputs(
    base: Mapping[str, Any],
    *,
    recorded_at: str,
    validation_wall_clock: datetime | None = None,
) -> tuple[list[dict[str, str]], list[Path]]:
    """Validate chronology and return the exact selected rows and paths."""

    accepted = _validate_non_nxdata_inputs()
    documents = {**accepted, NXDATA_SOURCE: _validate_nxdata_final()}
    selected = planned_selection(base, documents)
    target = v95.v70.parse_utc(recorded_at, label="v96 recorded_at")
    wall = validation_wall_clock or datetime.now(UTC)
    if wall.tzinfo is None or target > wall.astimezone(UTC):
        raise OpenSeedV96Error("v96 recorded_at exceeds validation wall clock")
    artifact_times = [
        *(spec.recorded_at for spec in ARTIFACT_SPECS),
        NXDATA_LIVE_RECORDED_AT,
    ]
    if any(
        v95.v70.parse_utc(value, label="accepted artifact recorded_at") > target
        for value in artifact_times
    ):
        raise OpenSeedV96Error("v96 publication time precedes an input")
    for relative, document in documents.items():
        for index, evidence in enumerate(document["evidence"]):
            retrieved = v95.v70.parse_utc(
                evidence["retrieved_at"],
                label=f"{relative} evidence[{index}].retrieved_at",
            )
            if retrieved > target or retrieved > wall.astimezone(UTC):
                raise OpenSeedV96Error("v96 selected evidence is future-dated")
    paths = []
    for row in selected:
        path = ROOT / row["path"]
        if path.is_symlink() or not path.is_file() or v69.sha256(path) != row["sha256"]:
            raise OpenSeedV96Error(f"v96 selected input pin differs: {row['path']}")
        paths.append(path)
    return selected, paths


def _table_state(connection: sqlite3.Connection, table: str) -> set[tuple[Any, ...]]:
    return {tuple(row) for row in connection.execute(f"SELECT * FROM {table}")}


def _entity_keys_for_rows(
    connection: sqlite3.Connection, rows: set[tuple[Any, ...]], *, id_index: int
) -> set[str]:
    by_id = {
        row["id"]: row["stable_key"]
        for row in connection.execute("SELECT id, stable_key FROM entities")
    }
    return {by_id[row[id_index]] for row in rows}


def _validate_database_contract(
    connection: sqlite3.Connection,
    base: Mapping[str, Any],
    *,
    recorded_at: str,
) -> None:
    counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in EXPECTED_DATABASE_COUNTS
    }
    if counts != EXPECTED_DATABASE_COUNTS:
        raise OpenSeedV96Error(f"v96 database counts differ: {counts}")

    with tempfile.TemporaryDirectory(
        prefix="open-seed-v96-base-", dir="/private/tmp"
    ) as temporary:
        prior = v69._populate_database(
            base,
            _base_paths(base),
            Path(temporary) / "v95.sqlite",
            recorded_at=recorded_at,
        )
        try:
            before_entities = {
                row["stable_key"]: tuple(row)
                for row in prior.execute("SELECT * FROM entities")
            }
            after_entities = {
                row["stable_key"]: tuple(row)
                for row in connection.execute("SELECT * FROM entities")
            }
            changed_entities = {
                key
                for key in before_entities.keys() & after_entities.keys()
                if before_entities[key] != after_entities[key]
            }
            if (
                changed_entities != FIN04_KEYS
                or set(after_entities) - set(before_entities) != ADDED_ENTITY_KEYS
                or set(before_entities) - set(after_entities)
            ):
                raise OpenSeedV96Error("v96 entity replacement delta differs")

            for table in ("evidence", "campuses", "projects"):
                before = _table_state(prior, table)
                after = _table_state(connection, table)
                expected_added = {
                    "evidence": 16,
                    "campuses": 9,
                    "projects": 9,
                }[table]
                if before - after or len(after - before) != expected_added:
                    raise OpenSeedV96Error(f"v96 database delta differs: {table}")

            before_snapshots = _table_state(prior, "entity_snapshots")
            after_snapshots = _table_state(connection, "entity_snapshots")
            if (
                _entity_keys_for_rows(
                    prior, before_snapshots - after_snapshots, id_index=1
                )
                != FIN04_KEYS
                or _entity_keys_for_rows(
                    connection, after_snapshots - before_snapshots, id_index=1
                )
                != FIN04_KEYS | ADDED_ENTITY_KEYS
                or len(before_snapshots - after_snapshots) != 2
                or len(after_snapshots - before_snapshots) != 20
            ):
                raise OpenSeedV96Error("v96 snapshot replacement delta differs")

            before_lifecycle = _table_state(prior, "lifecycle_observations")
            after_lifecycle = _table_state(connection, "lifecycle_observations")
            if (
                _entity_keys_for_rows(
                    prior, before_lifecycle - after_lifecycle, id_index=1
                )
                != {FIN04_PROJECT_KEY}
                or _entity_keys_for_rows(
                    connection, after_lifecycle - before_lifecycle, id_index=1
                )
                != {FIN04_PROJECT_KEY} | ADDED_PROJECT_KEYS
                or len(before_lifecycle - after_lifecycle) != 1
                or len(after_lifecycle - before_lifecycle) != 10
            ):
                raise OpenSeedV96Error("v96 lifecycle replacement delta differs")

            for table, expected_added in (
                ("operating_model_observations", 1),
                ("capacity_estimates", 3),
            ):
                before = _table_state(prior, table)
                after = _table_state(connection, table)
                if before - after or len(after - before) != expected_added:
                    raise OpenSeedV96Error(f"v96 database delta differs: {table}")
            if _table_state(prior, "workload_observations") != _table_state(
                connection, "workload_observations"
            ):
                raise OpenSeedV96Error("v96 changed a workload observation")
        finally:
            prior.close()

    lifecycle = {
        tuple(row)
        for row in connection.execute(
            """
            SELECT entities.stable_key, status, as_of_date,
                   lifecycle_observations.method
            FROM lifecycle_observations
            JOIN entities ON entities.id=entity_id
            """
        )
        if row[0] in ADDED_PROJECT_KEYS | {FIN04_PROJECT_KEY}
    }
    capacities = {
        tuple(row)
        for row in connection.execute(
            """
            SELECT entities.stable_key, metric, stage, unit, base
            FROM capacity_estimates
            JOIN entities ON entities.id=entity_id
            """
        )
        if row[0] in ADDED_ENTITY_KEYS
    }
    models = {
        tuple(row)
        for row in connection.execute(
            """
            SELECT entities.stable_key, operating_model
            FROM operating_model_observations
            JOIN entities ON entities.id=entity_id
            """
        )
        if row[0] in ADDED_ENTITY_KEYS
    }
    workloads = [
        tuple(row)
        for row in connection.execute(
            """
            SELECT entities.stable_key, workload
            FROM workload_observations
            JOIN entities ON entities.id=entity_id
            """
        )
        if row[0] in ADDED_ENTITY_KEYS
    ]
    capacity_details = {
        tuple(row)
        for row in connection.execute(
            """
            SELECT entities.stable_key, metric, stage, unit, low, base, high,
                   as_of_date, capacity_estimates.method, evidence_id
            FROM capacity_estimates
            JOIN entities ON entities.id=entity_id
            """
        )
        if row[0] in ADDED_ENTITY_KEYS
    }
    model_details = {
        tuple(row)
        for row in connection.execute(
            """
            SELECT entities.stable_key, operating_model, as_of_date,
                   operating_model_observations.method, evidence_id
            FROM operating_model_observations
            JOIN entities ON entities.id=entity_id
            """
        )
        if row[0] in ADDED_ENTITY_KEYS
    }
    if (
        lifecycle != EXPECTED_LIFECYCLE
        or capacities != EXPECTED_CAPACITIES
        or models != EXPECTED_MODELS
        or capacity_details != EXPECTED_DB_CAPACITY_DETAILS
        or model_details != EXPECTED_DB_MODEL_DETAILS
        or workloads
    ):
        raise OpenSeedV96Error("v96 imported claim contract differs")

    placeholders = ",".join("?" for _ in ADDED_ENTITY_KEYS)
    snapshot_rows = connection.execute(
        f"""
        SELECT entities.stable_key, latitude, longitude, geometry_json
        FROM entity_snapshots
        JOIN entities ON entities.id=entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        tuple(sorted(ADDED_ENTITY_KEYS)),
    )
    if any(
        latitude is not None
        or longitude is not None
        or geometry_json not in {None, "null"}
        for _key, latitude, longitude, geometry_json in snapshot_rows
    ):
        raise OpenSeedV96Error("v96 imported an unaccepted coordinate")


def _build_database(
    base: Mapping[str, Any],
    paths: list[Path],
    sqlite_path: Path,
    *,
    recorded_at: str,
) -> sqlite3.Connection:
    connection = v69._populate_database(
        base, paths, sqlite_path, recorded_at=recorded_at
    )
    try:
        _validate_database_contract(connection, base, recorded_at=recorded_at)
        return connection
    except Exception:
        connection.close()
        raise


def _keyed_rows(
    text: str, key: str
) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    rows = list(csv.DictReader(io.StringIO(text)))
    by_key = {row[key]: row for row in rows}
    if len(rows) != len(by_key):
        raise OpenSeedV96Error(f"duplicate public key: {key}")
    return rows, by_key


def _project_keyed_csv(
    output: dict[str, str],
    filename: str,
    *,
    key: str,
    replacements: frozenset[str] = frozenset(),
    raw_replacements: frozenset[str] | None = None,
    removals: frozenset[str] = frozenset(),
    raw_additions: frozenset[str],
    selected_additions: frozenset[str] | None = None,
    allow_base_recomputation: bool = False,
) -> None:
    base_rows = _csv_rows(BASE_RELEASE / filename)
    current_rows, current_by_key = _keyed_rows(output[filename], key)
    base_by_key = {row[key]: row for row in base_rows}
    if len(base_by_key) != len(base_rows):
        raise OpenSeedV96Error(f"duplicate accepted-v95 public key: {filename}")
    base_keys = set(base_by_key)
    current_keys = set(current_by_key)
    permitted_raw_replacements = (
        raw_replacements if raw_replacements is not None else replacements
    )
    if (
        base_keys - current_keys != set(removals)
        or current_keys - base_keys != set(raw_additions)
        or (
            not allow_base_recomputation
            and any(
                current_by_key[row_key] != row
                for row_key, row in base_by_key.items()
                if row_key not in permitted_raw_replacements | removals
            )
        )
    ):
        raise OpenSeedV96Error(f"v96 raw public row boundary differs: {filename}")
    additions = selected_additions if selected_additions is not None else raw_additions
    projected = [
        current_by_key[row[key]] if row[key] in replacements else row
        for row in base_rows
        if row[key] not in removals
    ]
    projected.extend(row for row in current_rows if row[key] in additions)
    output[filename] = _csv_text(output[filename], projected)


def _project_public_rows(output: dict[str, str]) -> None:
    _project_keyed_csv(
        output,
        "entities.csv",
        key="stable_key",
        replacements=FIN04_KEYS,
        raw_replacements=FIN04_KEYS | v95.STALE_SUPPRESSED_PROJECT_KEYS,
        raw_additions=ADDED_ENTITY_KEYS,
    )

    _evidence_rows, evidence_by_id = _keyed_rows(output["evidence.csv"], "evidence_id")
    base_evidence_ids = {
        row["evidence_id"] for row in _csv_rows(BASE_RELEASE / "evidence.csv")
    }
    new_evidence_ids = frozenset(set(evidence_by_id) - base_evidence_ids)
    if len(new_evidence_ids) != 13 or FIN04_NEW_EVIDENCE_ID not in new_evidence_ids:
        raise OpenSeedV96Error("v96 public evidence addition set differs")
    _project_keyed_csv(
        output,
        "evidence.csv",
        key="evidence_id",
        removals=frozenset({FIN04_OLD_EVIDENCE_ID}),
        raw_additions=new_evidence_ids,
    )

    _project_keyed_csv(
        output,
        "lifecycle_freshness.csv",
        key="stable_key",
        replacements=frozenset({FIN04_PROJECT_KEY}),
        raw_additions=ADDED_PROJECT_KEYS,
        allow_base_recomputation=True,
    )

    inherited_stale = v95.STALE_SUPPRESSED_PROJECT_KEYS
    _project_keyed_csv(
        output,
        "construction_pipeline.csv",
        key="stable_key",
        replacements=frozenset({FIN04_PROJECT_KEY}),
        raw_additions=ADDED_PROJECT_KEYS | inherited_stale,
        selected_additions=ADDED_PROJECT_KEYS - {ORAN_PROJECT_KEY},
    )

    signal_rows, signal_by_id = _keyed_rows(
        output["construction_source_signals.csv"],
        "source_observation_evidence_id",
    )
    base_signal_ids = {
        row["source_observation_evidence_id"]
        for row in _csv_rows(BASE_RELEASE / "construction_source_signals.csv")
    }
    new_signal_ids = frozenset(set(signal_by_id) - base_signal_ids)
    if len(new_signal_ids) != 10 or {
        row["representative_stable_key"]
        for row in signal_rows
        if row["source_observation_evidence_id"] in new_signal_ids
    } != ADDED_PROJECT_KEYS | {FIN04_PROJECT_KEY}:
        raise OpenSeedV96Error("v96 source-signal addition set differs")
    _project_keyed_csv(
        output,
        "construction_source_signals.csv",
        key="source_observation_evidence_id",
        removals=frozenset({FIN04_OLD_EVIDENCE_ID}),
        raw_additions=new_signal_ids,
    )

    base_capacity = _csv_rows(BASE_RELEASE / "capacity_estimates.csv")
    current_capacity = list(
        csv.DictReader(io.StringIO(output["capacity_estimates.csv"]))
    )
    canonical = lambda row: json.dumps(  # noqa: E731 - compact multiset key
        row, sort_keys=True, separators=(",", ":")
    )
    base_counter = Counter(canonical(row) for row in base_capacity)
    current_counter = Counter(canonical(row) for row in current_capacity)
    added_capacity = [
        json.loads(raw) for raw in (current_counter - base_counter).elements()
    ]
    if (
        base_counter - current_counter
        or {
            (
                row["metric"],
                row["stage"],
                row["unit"],
                float(row["base"]),
            )
            for row in added_capacity
        }
        != {
            ("gross_facility_mw", "design", "MW", 5.0),
            ("critical_it_mw", "design", "MW", 3.0),
            ("pue", "design", "ratio", 1.3),
        }
        or any(row["entity_id"] != NXDATA_PROJECT_ID for row in added_capacity)
    ):
        raise OpenSeedV96Error("v96 public capacity delta differs")
    output["capacity_estimates.csv"] = _csv_text(
        output["capacity_estimates.csv"], [*base_capacity, *added_capacity]
    )

    base_geojson = json.loads((BASE_RELEASE / "atlas.geojson").read_text())
    current_geojson = json.loads(output["atlas.geojson"])
    base_by_key = {
        row["properties"]["stable_key"]: row for row in base_geojson["features"]
    }
    current_by_key = {
        row["properties"]["stable_key"]: row for row in current_geojson["features"]
    }
    if (
        set(current_by_key) - set(base_by_key) != ADDED_ENTITY_KEYS
        or set(base_by_key) - set(current_by_key)
        or {key for key in base_by_key if current_by_key[key] != base_by_key[key]}
        != FIN04_KEYS | v95.STALE_SUPPRESSED_PROJECT_KEYS
    ):
        raise OpenSeedV96Error("v96 raw GeoJSON replacement boundary differs")
    new_features = [
        feature
        for feature in current_geojson["features"]
        if feature["properties"]["stable_key"] in ADDED_ENTITY_KEYS
    ]
    current_geojson["features"] = [
        *(
            current_by_key[feature["properties"]["stable_key"]]
            if feature["properties"]["stable_key"] in FIN04_KEYS
            else feature
            for feature in base_geojson["features"]
        ),
        *new_features,
    ]
    output["atlas.geojson"] = _canonical(current_geojson, sort_keys=True).decode()

    base_sources = json.loads((BASE_RELEASE / "source_inputs.json").read_text())[
        "sources"
    ]
    current_sources = json.loads(output["source_inputs.json"])["sources"]
    source_key = lambda row: json.dumps(  # noqa: E731 - canonical object key
        row, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    base_source_keys = {source_key(row) for row in base_sources}
    current_source_keys = {source_key(row) for row in current_sources}
    removed_sources = [
        row for row in base_sources if source_key(row) not in current_source_keys
    ]
    added_sources = [
        row for row in current_sources if source_key(row) not in base_source_keys
    ]
    if (
        len(removed_sources) != 1
        or removed_sources[0].get("provenance", {}).get("curated_record_key")
        != FIN04_OLD_EVIDENCE_KEY
        or len(added_sources) != 13
        or {
            row.get("provenance", {}).get("curated_record_key") for row in added_sources
        }
        != EXPORTED_EVIDENCE_KEYS
    ):
        raise OpenSeedV96Error("v96 public source-input replacement differs")
    output["source_inputs.json"] = _canonical(
        {
            "sources": [
                *(row for row in base_sources if row is not removed_sources[0]),
                *added_sources,
            ]
        },
        sort_keys=True,
    ).decode()

    for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
        if output[filename].encode() != (BASE_RELEASE / filename).read_bytes():
            raise OpenSeedV96Error(f"v96 changed unrelated output: {filename}")


def _suppress_stale_public_status(output: dict[str, str]) -> None:
    rows = list(csv.DictReader(io.StringIO(output["entities.csv"])))
    seen: set[str] = set()
    for row in rows:
        if row["stable_key"] in EXPECTED_STALE_PROJECT_KEYS:
            seen.add(row["stable_key"])
            for field in v95.STATUS_FIELDS:
                row[field] = ""
    if seen != EXPECTED_STALE_PROJECT_KEYS:
        raise OpenSeedV96Error("v96 stale entity suppression boundary differs")
    output["entities.csv"] = _csv_text(output["entities.csv"], rows)

    geojson = json.loads(output["atlas.geojson"])
    seen.clear()
    for feature in geojson["features"]:
        properties = feature["properties"]
        if properties["stable_key"] in EXPECTED_STALE_PROJECT_KEYS:
            seen.add(properties["stable_key"])
            for field in v95.STATUS_FIELDS:
                properties[field] = None
    if seen != EXPECTED_STALE_PROJECT_KEYS:
        raise OpenSeedV96Error("v96 stale GeoJSON suppression boundary differs")
    output["atlas.geojson"] = _canonical(geojson, sort_keys=True).decode()


def _augment_release(documents: Mapping[str, str]) -> dict[str, str]:
    previous_as_of = v95.v85.AS_OF
    try:
        v95.v85.AS_OF = AS_OF
        output = v95.v94.v93.v92.v91._augment_release(dict(documents))
    finally:
        v95.v85.AS_OF = previous_as_of

    _project_public_rows(output)
    _suppress_stale_public_status(output)

    base_attribution = set((BASE_RELEASE / "ATTRIBUTION.txt").read_text().splitlines())
    current_attribution = set(output["ATTRIBUTION.txt"].splitlines())
    if (
        base_attribution - current_attribution
        or current_attribution - base_attribution != ATTRIBUTION_ADDITIONS
    ):
        raise OpenSeedV96Error("v96 attribution delta differs")
    output["README.md"] = (
        (BASE_RELEASE / "README.md").read_text().rstrip() + "\n\n" + V96_README
    )

    summary = json.loads(output["summary.json"])
    summary.update(
        {
            "entities_total": 1_047,
            "campuses_total": 542,
            "projects_total": 505,
            "evidence_total": 883,
            "lifecycle_observations_current": 580,
            "capacity_estimates_current": 570,
            "construction_pipeline_records": 528,
            "construction_source_signals": 429,
            "entities_with_coordinates": 215,
            "campuses_with_coordinates": 142,
        }
    )
    summary["entities_by_status"]["under_construction"] = 405
    summary["capacity_estimates_by_stage"]["design"] = 36
    summary["successor_projection"] = {
        "base_release_id": v95.RELEASE_ID,
        "base_rows_frozen": False,
        "unaffected_base_rows_frozen": True,
        "governed_base_row_replacements": GOVERNED_REPLACEMENTS,
        "curated_source_input_delta": 9,
        "curated_source_input_appends": 9,
        "curated_source_input_replacements": 1,
        "internal_database_delta": INTERNAL_DELTA,
        "public_release_delta": PUBLIC_DELTA,
        "stale_status_suppression": STALE_POLICY,
        "coordinate_boundary": COORDINATE_BOUNDARY,
        "fin04_predecessor_selected": False,
    }
    output["summary.json"] = _canonical(summary, sort_keys=True).decode()

    manifest = json.loads(output["manifest.json"])
    manifest.pop("append_only_base_release", None)
    manifest.update(
        {
            "as_of": AS_OF,
            "entities": 1_047,
            "entities_by_kind": {"campus": 542, "project": 505},
            "evidence_records": 690,
            "lifecycle_freshness_records": 580,
            "capacity_estimates": 570,
            "construction_pipeline_records": 528,
            "construction_source_signals": 429,
            "governed_successor_base_release": v95.RELEASE_ID,
            "base_rows_frozen": False,
            "unaffected_base_rows_frozen": True,
            "governed_base_row_replacements": GOVERNED_REPLACEMENTS,
            "curated_source_input_delta": 9,
            "curated_source_input_appends": 9,
            "curated_source_input_replacements": 1,
            "internal_database_delta": INTERNAL_DELTA,
            "public_release_delta": PUBLIC_DELTA,
            "public_source_input_rows_delta": 12,
            "stale_status_suppression": STALE_POLICY,
            "coordinate_boundary": COORDINATE_BOUNDARY,
            "fin04_predecessor_selected": False,
            "nxdata_predecessor_selected": False,
        }
    )
    for filename, text in output.items():
        if filename != "manifest.json":
            raw = text.encode()
            manifest["files"][filename] = {
                "bytes": len(raw),
                "sha256": _sha256(raw),
            }
    output["manifest.json"] = _canonical(manifest, sort_keys=True).decode()
    return output


def _write_release(
    connection: sqlite3.Connection,
    output: Path,
    *,
    recorded_at: str,
    precreated: bool = False,
    identity_tracker: dict[str, tuple[str, int, int]] | None = None,
) -> None:
    if precreated:
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise OpenSeedV96Error("precreated v96 release stage must be empty")
    else:
        output.mkdir(parents=True, exist_ok=False)
    if identity_tracker is not None:
        root_identity = _identity(output, directory=True)
        identity_tracker["."] = ("directory", *root_identity)
    documents = build_release_documents(
        connection,
        as_of=AS_OF,
        recorded_at=recorded_at,
        publication_contract_version=4,
    )
    for filename, text_value in _augment_release(documents).items():
        path = output / filename
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        if identity_tracker is not None:
            metadata = os.fstat(descriptor)
            identity_tracker[filename] = (
                "file",
                metadata.st_dev,
                metadata.st_ino,
            )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(text_value.encode())
            stream.flush()
            os.fsync(stream.fileno())


def _guard_state() -> dict[str, Any]:
    _validate_base()
    _validate_non_nxdata_inputs()
    _validate_nxdata_final()
    return {
        "base_definition": _pin(BASE_DEFINITION),
        "base_manifest": _pin(BASE_RELEASE / "manifest.json"),
        "base_entities": _pin(BASE_RELEASE / "entities.csv"),
        "base_source_inputs": _pin(BASE_RELEASE / "source_inputs.json"),
        "base_tree": v69.tree_digest(BASE_RELEASE),
        "fin04_predecessor": _pin(ROOT / FIN04_PREDECESSOR),
        "artifact_manifests": {
            **{
                spec.label: _pin(spec.artifact / "manifest.json")
                for spec in ARTIFACT_SPECS
            },
            "nxdata": _pin(NXDATA_ARTIFACT / "manifest.json"),
        },
        "artifact_trees": {
            **{spec.label: v69.tree_digest(spec.artifact) for spec in ARTIFACT_SPECS},
            "nxdata": v69.tree_digest(NXDATA_ARTIFACT),
        },
        "selected_sources": {
            **{spec.relative: _pin(ROOT / spec.relative) for spec in SOURCE_SPECS},
            NXDATA_SOURCE: _pin(ROOT / NXDATA_SOURCE),
        },
    }


def _validate_guard(guard: Mapping[str, Any]) -> None:
    if (
        guard["base_definition"] != BASE_DEFINITION_PIN
        or guard["base_manifest"] != BASE_MANIFEST_PIN
        or guard["base_entities"] != BASE_ENTITIES_PIN
        or guard["base_source_inputs"] != BASE_SOURCE_INPUTS_PIN
        or guard["base_tree"] != BASE_TREE_SHA256
        or guard["fin04_predecessor"] != FIN04_PREDECESSOR_PIN
        or guard["artifact_manifests"]
        != {
            **{spec.label: spec.manifest_pin for spec in ARTIFACT_SPECS},
            "nxdata": NXDATA_LIVE_MANIFEST_PIN,
        }
        or guard["artifact_trees"]
        != {
            **{spec.label: spec.physical_tree_sha256 for spec in ARTIFACT_SPECS},
            "nxdata": NXDATA_LIVE_TREE_SHA256,
        }
        or guard["selected_sources"]
        != {**NON_NXDATA_PINS, NXDATA_SOURCE: NXDATA_SOURCE_PIN}
    ):
        raise OpenSeedV96Error("v96 immutable-input guard differs")


def _public_key_delta(
    stage: Path,
    filename: str,
    *,
    key: str,
) -> tuple[set[str], set[str], set[str]]:
    base = {row[key]: row for row in _csv_rows(BASE_RELEASE / filename)}
    current = {row[key]: row for row in _csv_rows(stage / filename)}
    changed = {
        row_key
        for row_key in base.keys() & current.keys()
        if base[row_key] != current[row_key]
    }
    return changed, set(base) - set(current), set(current) - set(base)


def _validate_public_delta(stage: Path) -> None:
    entity_changed, entity_removed, entity_added = _public_key_delta(
        stage, "entities.csv", key="stable_key"
    )
    if (
        entity_changed != FIN04_KEYS
        or entity_removed
        or entity_added != ADDED_ENTITY_KEYS
    ):
        raise OpenSeedV96Error("v96 public entity delta differs")

    evidence_changed, evidence_removed, evidence_added = _public_key_delta(
        stage, "evidence.csv", key="evidence_id"
    )
    if (
        evidence_changed
        or evidence_removed != {FIN04_OLD_EVIDENCE_ID}
        or len(evidence_added) != 13
        or FIN04_NEW_EVIDENCE_ID not in evidence_added
    ):
        raise OpenSeedV96Error("v96 public evidence delta differs")

    freshness_changed, freshness_removed, freshness_added = _public_key_delta(
        stage, "lifecycle_freshness.csv", key="stable_key"
    )
    if (
        freshness_changed != {FIN04_PROJECT_KEY}
        or freshness_removed
        or freshness_added != ADDED_PROJECT_KEYS
    ):
        raise OpenSeedV96Error("v96 public freshness delta differs")

    pipeline_changed, pipeline_removed, pipeline_added = _public_key_delta(
        stage, "construction_pipeline.csv", key="stable_key"
    )
    if (
        pipeline_changed != {FIN04_PROJECT_KEY}
        or pipeline_removed
        or pipeline_added != ADDED_PROJECT_KEYS - {ORAN_PROJECT_KEY}
    ):
        raise OpenSeedV96Error("v96 public pipeline delta differs")

    signal_changed, signal_removed, signal_added = _public_key_delta(
        stage,
        "construction_source_signals.csv",
        key="source_observation_evidence_id",
    )
    if (
        signal_changed
        or signal_removed != {FIN04_OLD_EVIDENCE_ID}
        or len(signal_added) != 10
        or FIN04_NEW_EVIDENCE_ID not in signal_added
    ):
        raise OpenSeedV96Error("v96 public source-signal delta differs")

    base_capacity = Counter(
        json.dumps(row, sort_keys=True, separators=(",", ":"))
        for row in _csv_rows(BASE_RELEASE / "capacity_estimates.csv")
    )
    current_capacity = Counter(
        json.dumps(row, sort_keys=True, separators=(",", ":"))
        for row in _csv_rows(stage / "capacity_estimates.csv")
    )
    added_capacity = [
        json.loads(raw) for raw in (current_capacity - base_capacity).elements()
    ]
    if (
        base_capacity - current_capacity
        or len(added_capacity) != 3
        or any(row["entity_id"] != NXDATA_PROJECT_ID for row in added_capacity)
    ):
        raise OpenSeedV96Error("v96 public capacity delta differs")

    base_geojson = json.loads((BASE_RELEASE / "atlas.geojson").read_text())
    current_geojson = json.loads((stage / "atlas.geojson").read_text())
    base_by_key = {
        row["properties"]["stable_key"]: row for row in base_geojson["features"]
    }
    current_by_key = {
        row["properties"]["stable_key"]: row for row in current_geojson["features"]
    }
    if (
        set(current_by_key) - set(base_by_key) != ADDED_ENTITY_KEYS
        or set(base_by_key) - set(current_by_key)
        or {key for key in base_by_key if current_by_key[key] != base_by_key[key]}
        != FIN04_KEYS
    ):
        raise OpenSeedV96Error("v96 public GeoJSON delta differs")

    base_sources = json.loads((BASE_RELEASE / "source_inputs.json").read_text())[
        "sources"
    ]
    current_sources = json.loads((stage / "source_inputs.json").read_text())["sources"]
    canonical = lambda row: json.dumps(  # noqa: E731 - canonical object key
        row, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    base_source_keys = {canonical(row) for row in base_sources}
    current_source_keys = {canonical(row) for row in current_sources}
    removed_sources = [
        row for row in base_sources if canonical(row) not in current_source_keys
    ]
    added_sources = [
        row for row in current_sources if canonical(row) not in base_source_keys
    ]
    if (
        len(current_sources) != 617
        or len(removed_sources) != 1
        or removed_sources[0].get("provenance", {}).get("curated_record_key")
        != FIN04_OLD_EVIDENCE_KEY
        or len(added_sources) != 13
        or {
            row.get("provenance", {}).get("curated_record_key") for row in added_sources
        }
        != EXPORTED_EVIDENCE_KEYS
    ):
        raise OpenSeedV96Error("v96 public source-input delta differs")

    for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
        if (stage / filename).read_bytes() != (BASE_RELEASE / filename).read_bytes():
            raise OpenSeedV96Error(f"v96 unrelated output changed: {filename}")


def _validate_release_facts(stage: Path, *, recorded_at: str) -> dict[str, Any]:
    if stage.is_symlink() or not stage.is_dir():
        raise OpenSeedV96Error("v96 release stage is not an ordinary directory")
    entries = {path.name: path for path in stage.iterdir()}
    if len(entries) != 14 or any(
        path.is_symlink() or not path.is_file() for path in entries.values()
    ):
        raise OpenSeedV96Error("v96 release inventory differs")
    manifest = _read_json(stage / "manifest.json", sort_keys=True)
    if (
        manifest.get("as_of") != AS_OF
        or manifest.get("recorded_at") != recorded_at
        or manifest.get("publication_contract_version") != 4
        or manifest.get("entities") != 1_047
        or manifest.get("entities_by_kind") != {"campus": 542, "project": 505}
        or manifest.get("evidence_records") != 690
        or manifest.get("lifecycle_freshness_records") != 580
        or manifest.get("capacity_estimates") != 570
        or manifest.get("construction_pipeline_records") != 528
        or manifest.get("construction_source_signals") != 429
        or manifest.get("governed_successor_base_release") != v95.RELEASE_ID
        or manifest.get("base_rows_frozen") is not False
        or manifest.get("unaffected_base_rows_frozen") is not True
        or manifest.get("governed_base_row_replacements") != GOVERNED_REPLACEMENTS
        or manifest.get("curated_source_input_delta") != 9
        or manifest.get("curated_source_input_appends") != 9
        or manifest.get("curated_source_input_replacements") != 1
        or manifest.get("internal_database_delta") != INTERNAL_DELTA
        or manifest.get("public_release_delta") != PUBLIC_DELTA
        or manifest.get("public_source_input_rows_delta") != 12
        or manifest.get("stale_status_suppression") != STALE_POLICY
        or manifest.get("coordinate_boundary") != COORDINATE_BOUNDARY
        or manifest.get("fin04_predecessor_selected") is not False
        or manifest.get("nxdata_predecessor_selected") is not False
        or "append_only_base_release" in manifest
        or set(entries) != set(manifest["files"]) | {"manifest.json"}
    ):
        raise OpenSeedV96Error("v96 manifest facts differ")
    for filename, pin in manifest["files"].items():
        if _pin(entries[filename]) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV96Error(f"v96 release pin differs: {filename}")
    _validate_public_delta(stage)

    entities = {row["stable_key"]: row for row in _csv_rows(stage / "entities.csv")}
    for key in EXPECTED_STALE_PROJECT_KEYS:
        if any(entities[key][field] for field in v95.STATUS_FIELDS):
            raise OpenSeedV96Error(f"v96 stale status persisted: {key}")
    for key in ADDED_ENTITY_KEYS | FIN04_KEYS:
        row = entities[key]
        if row["latitude"] or row["longitude"] or row["geometry_json"] != "null":
            raise OpenSeedV96Error(f"v96 unexpected public coordinate: {key}")

    freshness = {
        row["stable_key"]: row for row in _csv_rows(stage / "lifecycle_freshness.csv")
    }
    for key in EXPECTED_STALE_PROJECT_KEYS:
        row = freshness[key]
        if (
            row["freshness_class"] != "stale_over_365_days"
            or row["status_semantics"] != "last_observed"
            or row["current_status_classification"] != "unknown"
            or row["current_construction_claim"] != "false"
        ):
            raise OpenSeedV96Error(f"v96 stale freshness differs: {key}")
    pipeline = {
        row["stable_key"] for row in _csv_rows(stage / "construction_pipeline.csv")
    }
    if pipeline & EXPECTED_STALE_PROJECT_KEYS:
        raise OpenSeedV96Error("v96 stale project entered the public pipeline")
    signals = {
        row["representative_stable_key"]
        for row in _csv_rows(stage / "construction_source_signals.csv")
    }
    if not (ADDED_PROJECT_KEYS | {FIN04_PROJECT_KEY}) <= signals:
        raise OpenSeedV96Error("v96 source-signal history is incomplete")

    summary = _read_json(stage / "summary.json", sort_keys=True)
    projection = summary.get("successor_projection")
    if (
        summary.get("entities_total") != 1_047
        or summary.get("campuses_total") != 542
        or summary.get("projects_total") != 505
        or summary.get("evidence_total") != 883
        or summary.get("lifecycle_observations_current") != 580
        or summary.get("capacity_estimates_current") != 570
        or summary.get("construction_pipeline_records") != 528
        or summary.get("construction_source_signals") != 429
        or summary.get("entities_with_coordinates") != 215
        or summary.get("campuses_with_coordinates") != 142
        or summary.get("entities_by_status", {}).get("under_construction") != 405
        or summary.get("capacity_estimates_by_stage", {}).get("design") != 36
        or not isinstance(projection, dict)
        or projection.get("base_release_id") != v95.RELEASE_ID
        or projection.get("governed_base_row_replacements") != GOVERNED_REPLACEMENTS
        or projection.get("internal_database_delta") != INTERNAL_DELTA
        or projection.get("public_release_delta") != PUBLIC_DELTA
        or projection.get("stale_status_suppression") != STALE_POLICY
        or projection.get("coordinate_boundary") != COORDINATE_BOUNDARY
    ):
        raise OpenSeedV96Error("v96 summary contract differs")
    readme = (stage / "README.md").read_text(encoding="utf-8")
    for marker in (
        "Open seed v96 is the exact governed accepted-v95 successor",
        "curated-input index 174",
        "Every unrelated v95 public row remains byte-identical",
        "NXDATA design metrics",
        "Jakarta, Hanoi, and Oran",
        "current status remains unknown",
    ):
        if marker not in readme:
            raise OpenSeedV96Error(f"v96 README guardrail differs: {marker}")
    return manifest


def _definition_document(
    base: Mapping[str, Any],
    selected: list[dict[str, str]],
    release: Path,
    *,
    recorded_at: str,
) -> dict[str, Any]:
    manifest_raw = (release / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    summary = json.loads((release / "summary.json").read_text())
    document = dict(base)
    document["build"] = {"as_of": AS_OF, "recorded_at": recorded_at}
    document["curated_inputs"] = selected
    document["expected_release"] = {
        **{key: value for key, value in manifest.items() if key != "files"},
        "manifest_sha256": _sha256(manifest_raw),
    }
    document["expected_summary"] = {
        key: summary[key] for key in base["expected_summary"]
    }
    freshness = dict(base["freshness_contract"])
    freshness["stale_status_suppressed_project_keys"] = sorted(
        EXPECTED_STALE_PROJECT_KEYS
    )
    freshness["successor_rehydration_forbidden"] = True
    document["freshness_contract"] = freshness
    document["release_id"] = RELEASE_ID
    return document


def _release_descendants(root: Path) -> list[Path]:
    return sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix())


def _freeze(definition: Path, release: Path) -> None:
    v95._freeze(definition, release)


def _thaw_private_stage(definition: Path, release: Path) -> None:
    v95._thaw_private_stage(definition, release)


def _validate_publication_times(
    definition: Path,
    release: Path,
    *,
    recorded_at: str,
    require_live: bool,
) -> None:
    target = v95.v70.parse_utc(recorded_at, label="v96 recorded_at")
    paths = [definition, release, *_release_descendants(release)]
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV96Error(
                f"v96 inode birth/mtime post-dates recorded_at: {path}"
            )
    if require_live:
        if datetime.now(UTC) < target:
            raise OpenSeedV96Error("v96 recorded_at is not live")
        for path in paths:
            if path.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
                raise OpenSeedV96Error(
                    f"v96 recursive ctime predates recorded_at: {path}"
                )


def validate_open_seed_v96(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
    require_live: bool = True,
) -> dict[str, Any]:
    if replay_count != 2:
        raise OpenSeedV96Error("v96 requires exactly two offline replays")
    guard = _guard_state()
    _validate_guard(guard)
    base = _validate_base()
    definition = _read_json(
        definition_path,
        mode=0o444 if require_frozen else None,
        sort_keys=True,
    )
    if set(definition) != set(base) or definition.get("release_id") != RELEASE_ID:
        raise OpenSeedV96Error("v96 definition identity differs")
    build = definition.get("build")
    if (
        not isinstance(build, dict)
        or set(build) != {"as_of", "recorded_at"}
        or build.get("as_of") != AS_OF
    ):
        raise OpenSeedV96Error("v96 definition build carrier differs")
    wall = validation_wall_clock or datetime.now(UTC)
    selected, paths = selected_inputs(
        base,
        recorded_at=build["recorded_at"],
        validation_wall_clock=wall,
    )
    if definition.get("curated_inputs") != selected:
        raise OpenSeedV96Error("v96 definition selected inputs differ")
    if definition.get("freshness_contract", {}).get(
        "stale_status_suppressed_project_keys"
    ) != sorted(EXPECTED_STALE_PROJECT_KEYS):
        raise OpenSeedV96Error("v96 definition stale-status contract differs")

    descendants = _release_descendants(release_path)
    if (
        release_path.is_symlink()
        or not release_path.is_dir()
        or (
            require_frozen
            and (
                stat.S_IMODE(release_path.stat().st_mode) != 0o555
                or any(
                    path.is_symlink()
                    or (path.is_dir() and stat.S_IMODE(path.stat().st_mode) != 0o555)
                    or (path.is_file() and stat.S_IMODE(path.stat().st_mode) != 0o444)
                    or (not path.is_dir() and not path.is_file())
                    for path in descendants
                )
            )
        )
    ):
        raise OpenSeedV96Error("v96 staged release is not frozen")
    manifest = _validate_release_facts(release_path, recorded_at=build["recorded_at"])
    manifest_raw = (release_path / "manifest.json").read_bytes()
    if _sha256(manifest_raw) != definition["expected_release"]["manifest_sha256"]:
        raise OpenSeedV96Error("v96 expected manifest hash differs")
    if {key: value for key, value in manifest.items() if key != "files"} != {
        key: value
        for key, value in definition["expected_release"].items()
        if key != "manifest_sha256"
    }:
        raise OpenSeedV96Error("v96 expected release facts differ")
    summary = json.loads((release_path / "summary.json").read_text())
    if {key: summary[key] for key in definition["expected_summary"]} != definition[
        "expected_summary"
    ]:
        raise OpenSeedV96Error("v96 expected summary differs")
    _validate_publication_times(
        definition_path,
        release_path,
        recorded_at=build["recorded_at"],
        require_live=require_live,
    )

    replay_digests: list[str] = []
    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v96-replay-{replay + 1}-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            connection = _build_database(
                base,
                paths,
                root / "atlas.sqlite",
                recorded_at=build["recorded_at"],
            )
            try:
                replay_release = root / "release"
                _write_release(
                    connection,
                    replay_release,
                    recorded_at=build["recorded_at"],
                )
            finally:
                connection.close()
            _validate_release_facts(replay_release, recorded_at=build["recorded_at"])
            for filename in set(manifest["files"]) | {"manifest.json"}:
                if (replay_release / filename).read_bytes() != (
                    release_path / filename
                ).read_bytes():
                    raise OpenSeedV96Error(f"v96 offline replay differs: {filename}")
            replay_digests.append(
                _sha256((replay_release / "manifest.json").read_bytes())
            )
    replay_digest = _two_replay_gate(replay_digests)
    if replay_digest != _sha256((release_path / "manifest.json").read_bytes()):
        raise OpenSeedV96Error("v96 staged manifest differs from replays")
    if _guard_state() != guard:
        raise OpenSeedV96Error("v96 validation mutated accepted inputs")
    return {**manifest, "two_replay_manifest_sha256": replay_digest}


def validate_staged_open_seed_v96(
    definition_path: Path,
    release_path: Path,
    *,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
) -> dict[str, Any]:
    return validate_open_seed_v96(
        definition_path,
        release_path,
        require_frozen=True,
        replay_count=replay_count,
        validation_wall_clock=validation_wall_clock,
        require_live=False,
    )


def _identity(path: Path, *, directory: bool) -> tuple[int, int]:
    if path.is_symlink():
        raise OpenSeedV96Error(f"symlinked promotion member: {path}")
    metadata = path.stat(follow_symlinks=False)
    if directory and not path.is_dir():
        raise OpenSeedV96Error(f"promotion member is not a directory: {path}")
    if not directory and not path.is_file():
        raise OpenSeedV96Error(f"promotion member is not a file: {path}")
    return metadata.st_dev, metadata.st_ino


def _has_identity(path: Path, identity: tuple[int, int], *, directory: bool) -> bool:
    try:
        return _identity(path, directory=directory) == identity
    except (FileNotFoundError, OpenSeedV96Error):
        return False


def _promote_noreplace(
    stage: Path, destination: Path, *, directory: bool
) -> tuple[int, int]:
    identity = _identity(stage, directory=directory)
    if stage.stat().st_dev != destination.parent.stat().st_dev:
        raise OpenSeedV96Error("v96 promotion crosses filesystems")
    try:
        v69.promote_noreplace(stage, destination)
    except SystemExit as error:
        raise OpenSeedV96Error(str(error)) from error
    if not _has_identity(destination, identity, directory=directory):
        raise OpenSeedV96Error("v96 promoted identity differs")
    return identity


def _rollback_noreplace(
    destination: Path,
    stage: Path,
    identity: tuple[int, int],
    *,
    directory: bool,
) -> None:
    if not _has_identity(destination, identity, directory=directory):
        raise OpenSeedV96Error("v96 refuses identity-mismatched rollback")
    _promote_noreplace(destination, stage, directory=directory)
    if not _has_identity(stage, identity, directory=directory):
        raise OpenSeedV96Error("v96 rollback identity differs")


def _tree_identities(root: Path) -> dict[str, tuple[str, int, int]]:
    identities: dict[str, tuple[str, int, int]] = {}
    for path in [root, *_release_descendants(root)]:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise OpenSeedV96Error(f"v96 tree contains symlink: {relative}")
        metadata = path.stat(follow_symlinks=False)
        if path.is_dir():
            kind = "directory"
        elif path.is_file():
            kind = "file"
        else:
            raise OpenSeedV96Error(f"v96 tree contains special member: {relative}")
        identities[relative] = (kind, metadata.st_dev, metadata.st_ino)
    return identities


def _assert_tree_identities(
    root: Path, expected: Mapping[str, tuple[str, int, int]]
) -> None:
    if _tree_identities(root) != dict(expected):
        raise OpenSeedV96Error("v96 recursive tree identity changed")


def _discard_release_stage(
    root: Path, expected: Mapping[str, tuple[str, int, int]]
) -> None:
    if not root.exists() and not root.is_symlink():
        return
    _assert_tree_identities(root, expected)
    root.chmod(0o700)
    descendants = _release_descendants(root)
    for path in descendants:
        path.chmod(0o700 if path.is_dir() else 0o600)
    shutil.rmtree(root)


def _discard_file_stage(path: Path, identity: tuple[int, int]) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if _identity(path, directory=False) != identity:
        raise OpenSeedV96Error("refusing substituted v96 definition cleanup")
    path.chmod(0o600)
    path.unlink()


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise OpenSeedV96Error("active v96 publication lock exists") from error
    identity: tuple[int, int] | None = None
    try:
        metadata = os.fstat(descriptor)
        identity = (metadata.st_dev, metadata.st_ino)
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        identity_error: BaseException | None = None
        if identity is None:
            try:
                metadata = os.fstat(descriptor)
                identity = (metadata.st_dev, metadata.st_ino)
            except BaseException as error:
                identity_error = error
        os.close(descriptor)
        if identity is not None:
            try:
                current = PUBLICATION_LOCK.stat(follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                if (
                    not stat.S_ISREG(current.st_mode)
                    or (current.st_dev, current.st_ino) != identity
                ):
                    raise OpenSeedV96Error("refusing substituted v96 lock cleanup")
                PUBLICATION_LOCK.unlink()
        if identity_error is not None:
            raise OpenSeedV96Error(
                "v96 lock identity unavailable; retained lock fail-closed"
            ) from identity_error


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _refresh_publication_ctimes(definition: Path, release: Path) -> None:
    definition.chmod(0o400)
    definition.chmod(0o444)
    v95._fsync(definition)
    descendants = _release_descendants(release)
    for path in descendants:
        if path.is_file():
            path.chmod(0o400)
            path.chmod(0o444)
            v95._fsync(path)
    for path in sorted(
        (path for path in descendants if path.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        path.chmod(0o500)
        path.chmod(0o555)
        v95._fsync(path)
    release.chmod(0o500)
    release.chmod(0o555)
    v95._fsync(release)


def _require_final_absent(label: str) -> None:
    if DEFINITION.exists() or DEFINITION.is_symlink():
        raise OpenSeedV96Error(f"{label} v96 definition collision")
    if RELEASE.exists() or RELEASE.is_symlink():
        raise OpenSeedV96Error(f"{label} v96 release collision")


def _rollback_release(
    release_identity: tuple[int, int],
    release_identities: Mapping[str, tuple[str, int, int]],
    stage: Path,
) -> None:
    if _identity(RELEASE, directory=True) != release_identity:
        raise OpenSeedV96Error("refusing rollback of substituted v96 release")
    _assert_tree_identities(RELEASE, release_identities)
    if stage.exists() or stage.is_symlink():
        raise OpenSeedV96Error("v96 release rollback stage is occupied")
    _promote_noreplace(RELEASE, stage, directory=True)
    _assert_tree_identities(stage, release_identities)


def _rollback_definition(definition_identity: tuple[int, int], stage: Path) -> None:
    if _identity(DEFINITION, directory=False) != definition_identity:
        raise OpenSeedV96Error("refusing rollback of substituted v96 definition")
    if stage.exists() or stage.is_symlink():
        raise OpenSeedV96Error("v96 definition rollback stage is occupied")
    _promote_noreplace(DEFINITION, stage, directory=False)


def _private_promotion_roundtrip(definition: Path, release: Path, root: Path) -> None:
    """Exercise no-replace promotion and rollback only on private temp paths."""

    # Keep source and destination in one parent, matching final publication.
    # On macOS, moving a frozen directory into a child directory requires
    # write permission on the moved directory to update its ``..`` entry.
    promoted_definition = root / f".{definition.name}.promoted"
    promoted_release = root / ".release.promoted"
    definition_identity = _identity(definition, directory=False)
    release_identity = _identity(release, directory=True)
    release_identities = _tree_identities(release)
    release_promoted = False
    definition_promoted = False
    operation_error: BaseException | None = None
    try:
        _promote_noreplace(release, promoted_release, directory=True)
        release_promoted = True
        _assert_tree_identities(promoted_release, release_identities)
        _promote_noreplace(definition, promoted_definition, directory=False)
        definition_promoted = True
        if not _has_identity(promoted_definition, definition_identity, directory=False):
            raise OpenSeedV96Error("v96 private definition identity changed")
    except BaseException as error:
        operation_error = error
    rollback_errors: list[Exception] = []
    if definition_promoted:
        try:
            _rollback_noreplace(
                promoted_definition,
                definition,
                definition_identity,
                directory=False,
            )
        except Exception as error:
            rollback_errors.append(error)
    if release_promoted:
        try:
            _assert_tree_identities(promoted_release, release_identities)
            _rollback_noreplace(
                promoted_release,
                release,
                release_identity,
                directory=True,
            )
            _assert_tree_identities(release, release_identities)
        except Exception as error:
            rollback_errors.append(error)
    if operation_error is not None:
        for error in rollback_errors:
            operation_error.add_note(f"v96 private rollback failed: {error}")
        raise operation_error
    if rollback_errors:
        primary = rollback_errors[0]
        for error in rollback_errors[1:]:
            primary.add_note(f"additional v96 private rollback failure: {error}")
        raise primary
    if promoted_definition.exists() or promoted_release.exists():
        raise OpenSeedV96Error("v96 private promotion roundtrip left residue")


def _two_replay_gate(digests: Sequence[str]) -> str:
    if len(digests) != 2 or not all(
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
        for value in digests
    ):
        raise OpenSeedV96Error("v96 requires exactly two replay digests")
    if digests[0] != digests[1]:
        raise OpenSeedV96Error("v96 replay digests differ")
    return digests[0]


def _assert_final_absent() -> None:
    present = [
        str(path)
        for path in (DEFINITION, RELEASE, PUBLICATION_LOCK)
        if path.exists() or path.is_symlink()
    ]
    if present:
        raise OpenSeedV96Error(f"v96 final path collision: {present!r}")


def prepare_open_seed_v96(
    recorded_at: str | None = None, *, replay_count: int = 2
) -> dict[str, Any]:
    """Build, freeze, replay, validate, roundtrip, and discard a private stage."""

    _assert_final_absent()
    if replay_count != 2:
        raise OpenSeedV96Error("v96 requires exactly two offline replays")
    report = require_readiness()
    if report["barrier"]:
        raise OpenSeedV96ReadinessError(
            report["barrier"],
            "v96 preflight stopped before staging: " + report["barrier"],
        )
    target = (
        v95.v70.parse_utc(recorded_at, label="v96 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=90)
    )
    if target <= datetime.now(UTC):
        raise OpenSeedV96Error("v96 prepublication recorded_at must be future")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    guard = _guard_state()
    _validate_guard(guard)
    base = _validate_base()
    selected, paths = selected_inputs(
        base, recorded_at=timestamp, validation_wall_clock=target
    )
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v96-prepublication-", dir="/private/tmp"
    ) as temporary:
        root = Path(temporary)
        release = root / "release"
        definition = root / DEFINITION.name
        try:
            connection = _build_database(
                base, paths, root / "atlas.sqlite", recorded_at=timestamp
            )
            try:
                _write_release(connection, release, recorded_at=timestamp)
            finally:
                connection.close()
            _validate_release_facts(release, recorded_at=timestamp)
            definition.write_bytes(
                _canonical(
                    _definition_document(
                        base, selected, release, recorded_at=timestamp
                    ),
                    sort_keys=True,
                )
            )
            _freeze(definition, release)
            manifest = validate_staged_open_seed_v96(
                definition,
                release,
                replay_count=replay_count,
                validation_wall_clock=target,
            )
            frozen_definition = definition.read_bytes()
            frozen_tree = v69.tree_digest(release)
            frozen_identities = _tree_identities(release)
            _private_promotion_roundtrip(definition, release, root)
            if (
                definition.read_bytes() != frozen_definition
                or v69.tree_digest(release) != frozen_tree
            ):
                raise OpenSeedV96Error(
                    "v96 private bytes changed during promotion roundtrip"
                )
            _assert_tree_identities(release, frozen_identities)
            result = {
                "status": "prepublication-validated",
                "publication_authorized": False,
                "barrier": "stopped-before-final-no-replace-promotion",
                "recorded_at": timestamp,
                "planned_input_count": len(selected),
                "definition_sha256": _sha256(definition.read_bytes()),
                "manifest_sha256": _sha256((release / "manifest.json").read_bytes()),
                "release_tree_sha256": frozen_tree,
                "two_replay_manifest_sha256": manifest["two_replay_manifest_sha256"],
                "entities": manifest["entities"],
                "evidence_records": manifest["evidence_records"],
                "lifecycle_freshness_records": manifest["lifecycle_freshness_records"],
                "capacity_estimates": manifest["capacity_estimates"],
                "construction_pipeline_records": manifest[
                    "construction_pipeline_records"
                ],
                "construction_source_signals": manifest["construction_source_signals"],
                "private_no_replace_roundtrip_validated": True,
                "final_definition_absent": not DEFINITION.exists(),
                "final_release_absent": not RELEASE.exists(),
                "publication_lock_absent": not PUBLICATION_LOCK.exists(),
            }
        finally:
            _thaw_private_stage(definition, release)
    if (
        _guard_state() != guard
        or DEFINITION.exists()
        or DEFINITION.is_symlink()
        or RELEASE.exists()
        or RELEASE.is_symlink()
        or PUBLICATION_LOCK.exists()
        or PUBLICATION_LOCK.is_symlink()
    ):
        raise OpenSeedV96Error("v96 prepublication left residue or mutated inputs")
    return result


def _existing_identical(recorded_at: str | None) -> dict[str, Any]:
    definition = _read_json(DEFINITION, mode=0o444, sort_keys=True)
    existing_recorded_at = definition.get("build", {}).get("recorded_at")
    if not isinstance(existing_recorded_at, str):
        raise OpenSeedV96Error("existing v96 recorded_at is missing")
    if recorded_at is not None and recorded_at != existing_recorded_at:
        raise OpenSeedV96Error("existing v96 recorded_at differs")
    manifest = validate_open_seed_v96(DEFINITION, RELEASE)
    return {
        "status": "existing-identical",
        "definition": str(DEFINITION),
        "definition_sha256": _sha256(DEFINITION.read_bytes()),
        "manifest_sha256": _sha256((RELEASE / "manifest.json").read_bytes()),
        "recorded_at": existing_recorded_at,
        "release": str(RELEASE),
        "release_tree_sha256": v69.tree_digest(RELEASE),
        "two_replay_manifest_sha256": manifest["two_replay_manifest_sha256"],
    }


def build_open_seed_v96(
    recorded_at: str | None = None, *, publication_authorized: bool = False
) -> dict[str, Any]:
    """Publish only after explicit authorization and every governed gate."""

    if not publication_authorized:
        raise OpenSeedV96Error("v96 publication requires explicit authorization")
    definition_present = DEFINITION.exists() or DEFINITION.is_symlink()
    release_present = RELEASE.exists() or RELEASE.is_symlink()
    if definition_present and release_present:
        return _existing_identical(recorded_at)
    if definition_present or release_present:
        raise OpenSeedV96Error("partial v96 final-path collision")

    target = (
        v95.v70.parse_utc(recorded_at, label="v96 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=90)
    )
    if datetime.now(UTC) >= target:
        raise OpenSeedV96Error("v96 recorded_at must be future before staging")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    guard = _guard_state()
    _validate_guard(guard)

    with _publication_lock():
        _require_final_absent("initial")
        release_stage = Path(
            tempfile.mkdtemp(prefix=f".{RELEASE.name}.", dir=RELEASE.parent)
        )
        release_identities = _tree_identities(release_stage)
        try:
            descriptor, temporary = tempfile.mkstemp(
                prefix=f".{DEFINITION.name}.",
                suffix=".stage",
                dir=DEFINITION.parent,
            )
        except BaseException:
            _discard_release_stage(release_stage, release_identities)
            raise
        definition_stage = Path(temporary)
        definition_identity: tuple[int, int] | None = None
        descriptor_open = True
        published_release = False
        published_definition = False
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise OpenSeedV96Error("v96 definition stage is not a file")
            definition_identity = (metadata.st_dev, metadata.st_ino)
            if _identity(definition_stage, directory=False) != definition_identity:
                raise OpenSeedV96Error("v96 definition stage identity differs")
            os.close(descriptor)
            descriptor_open = False
            base = _validate_base()
            selected, paths = selected_inputs(
                base, recorded_at=timestamp, validation_wall_clock=target
            )
            with tempfile.TemporaryDirectory(
                prefix="open-seed-v96-db-", dir="/private/tmp"
            ) as database_root:
                connection = _build_database(
                    base,
                    paths,
                    Path(database_root) / "atlas.sqlite",
                    recorded_at=timestamp,
                )
                try:
                    _write_release(
                        connection,
                        release_stage,
                        recorded_at=timestamp,
                        precreated=True,
                        identity_tracker=release_identities,
                    )
                finally:
                    connection.close()
            if _tree_identities(release_stage) != release_identities:
                raise OpenSeedV96Error("v96 release stage identities differ")
            _validate_release_facts(release_stage, recorded_at=timestamp)
            definition = _definition_document(
                base, selected, release_stage, recorded_at=timestamp
            )
            with definition_stage.open("r+b") as stream:
                stream.write(_canonical(definition, sort_keys=True))
                stream.truncate()
                stream.flush()
                os.fsync(stream.fileno())
            _freeze(definition_stage, release_stage)
            _assert_tree_identities(release_stage, release_identities)
            validate_staged_open_seed_v96(
                definition_stage,
                release_stage,
                validation_wall_clock=target,
            )
            _validate_publication_times(
                definition_stage,
                release_stage,
                recorded_at=timestamp,
                require_live=False,
            )
            _require_final_absent("pre-wait")
            frozen_definition = definition_stage.read_bytes()
            frozen_tree = v69.tree_digest(release_stage)
            _wait_until(target)
            _require_final_absent("late")
            if _identity(definition_stage, directory=False) != definition_identity:
                raise OpenSeedV96Error("v96 definition stage identity changed")
            _assert_tree_identities(release_stage, release_identities)
            if (
                definition_stage.read_bytes() != frozen_definition
                or v69.tree_digest(release_stage) != frozen_tree
            ):
                raise OpenSeedV96Error("v96 private stage changed while waiting")
            _refresh_publication_ctimes(definition_stage, release_stage)
            if _identity(definition_stage, directory=False) != definition_identity:
                raise OpenSeedV96Error("v96 refreshed definition identity changed")
            _assert_tree_identities(release_stage, release_identities)
            if (
                definition_stage.read_bytes() != frozen_definition
                or v69.tree_digest(release_stage) != frozen_tree
            ):
                raise OpenSeedV96Error("v96 private bytes changed at publication")
            _validate_publication_times(
                definition_stage,
                release_stage,
                recorded_at=timestamp,
                require_live=True,
            )

            release_identity = _promote_noreplace(
                release_stage, RELEASE, directory=True
            )
            published_release = True
            try:
                _assert_tree_identities(RELEASE, release_identities)
                promoted_definition_identity = _promote_noreplace(
                    definition_stage, DEFINITION, directory=False
                )
                published_definition = True
                if promoted_definition_identity != definition_identity:
                    raise OpenSeedV96Error("v96 definition promotion identity differs")
            except BaseException as error:
                if DEFINITION.exists() or DEFINITION.is_symlink():
                    try:
                        _rollback_definition(definition_identity, definition_stage)
                        published_definition = False
                    except Exception as rollback_error:
                        error.add_note(
                            f"v96 definition rollback failed: {rollback_error}"
                        )
                try:
                    _rollback_release(
                        release_identity, release_identities, release_stage
                    )
                    published_release = False
                except Exception as rollback_error:
                    error.add_note(f"v96 release rollback failed: {rollback_error}")
                raise
            try:
                manifest = validate_open_seed_v96(DEFINITION, RELEASE)
            except BaseException as error:
                rollback_errors: list[Exception] = []
                try:
                    _rollback_definition(definition_identity, definition_stage)
                    published_definition = False
                except Exception as rollback_error:
                    rollback_errors.append(rollback_error)
                try:
                    _rollback_release(
                        release_identity, release_identities, release_stage
                    )
                    published_release = False
                except Exception as rollback_error:
                    rollback_errors.append(rollback_error)
                for rollback_error in rollback_errors:
                    error.add_note(f"v96 rollback failed: {rollback_error}")
                raise
        finally:
            if descriptor_open:
                os.close(descriptor)
            if not published_release and (
                release_stage.exists() or release_stage.is_symlink()
            ):
                _discard_release_stage(release_stage, release_identities)
            if not published_definition and (
                definition_stage.exists() or definition_stage.is_symlink()
            ):
                if definition_identity is None:
                    definition_identity = _identity(definition_stage, directory=False)
                _discard_file_stage(definition_stage, definition_identity)
    if _guard_state() != guard:
        raise OpenSeedV96Error("v96 publication mutated accepted inputs")
    return {
        "status": "published",
        "definition": str(DEFINITION),
        "definition_sha256": _sha256(DEFINITION.read_bytes()),
        "manifest_sha256": _sha256((RELEASE / "manifest.json").read_bytes()),
        "recorded_at": manifest["recorded_at"],
        "release": str(RELEASE),
        "release_tree_sha256": v69.tree_digest(RELEASE),
        "two_replay_manifest_sha256": manifest["two_replay_manifest_sha256"],
    }


def main(*, publication_authorized: bool = False) -> int:
    result = (
        build_open_seed_v96(publication_authorized=True)
        if publication_authorized
        else prepare_open_seed_v96()
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
