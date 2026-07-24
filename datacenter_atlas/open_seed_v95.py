"""Prepare, but do not publish, the governed open-seed v95 successor.

The carrier pins accepted v94, eight accepted Nordic/global records with the
corrected NorthC coordinate successor selected in place of its predecessor,
and the accepted CENTRA RNO2 record.  It can build, freeze, replay, and validate
a private release stage.  It deliberately has no final-path promotion path.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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

from . import centra_rno2_official_current_build_gap_20260722 as centra
from . import global_official_batam_jakarta_hanoi_bue1_current_build_gap_20260722 as global_gap
from . import official_coordinate_assessment_aalsmeer_bue1_20260722 as coordinate
from . import official_nordic_iren_current_build_gap_20260722 as nordic
from . import open_seed_v69 as v69
from . import open_seed_v70 as v70
from . import open_seed_v85 as v85
from . import open_seed_v94 as v94
from .publication_release import build_release_documents
from .service import _current_rows


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v94.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v94"
DEFINITION = ROOT / "sources/open-seed-2026-07-22-v95.json"
RELEASE_ID = "2026-07-22-open-seed-v95"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v95.lock"
AS_OF = "2026-07-22"

BASE_RECORDED_AT = "2026-07-22T03:35:54Z"
BASE_DEFINITION_PIN = (
    113_819,
    "c65f61b3708b4cdc1fb755eaf8d0edffab545526f206689e66056220b27cc0ff",
)
BASE_MANIFEST_PIN = (
    17_866,
    "8315811764024f026eb2fc69f9ff06b738c554dcd9717aed6ba9254f6cf3fc65",
)
BASE_ENTITIES_PIN = (
    1_044_783,
    "87d2320671a5773c8d7619be972b5434f82adb12a28f3afe383e2e1bd63605f4",
)
BASE_SOURCE_INPUTS_PIN = (
    423_750,
    "9001ec0544a5f7d86d62472fcd71c5cff584587599058c07bfa4111cf6a8ea33",
)
BASE_TREE_SHA256 = "e947ec413e1c43ea053f7766928ccab373f7e1f058be42fc5c433ea7dda49766"
BASE_INPUT_COUNT = 498


class OpenSeedV95Error(RuntimeError):
    """Raised when a v95 lineage, semantic, or prepublication fuse fails."""


@dataclass(frozen=True)
class ArtifactSpec:
    label: str
    artifact: Path
    recorded_at: str
    manifest_pin: tuple[int, str]
    logical_tree: str
    physical_tree: str
    source_count: int


@dataclass(frozen=True)
class SourceSpec:
    relative: str
    pin: tuple[int, str]
    ctime_ns: int
    artifact_label: str


ARTIFACT_SPECS = (
    ArtifactSpec(
        "nordic",
        nordic.ARTIFACT,
        "2026-07-22T03:51:00Z",
        (1_731, "0731687c2b2d69a9bf5300d9bbed7be5d6795e0495819d3087a25bbbcb9abe11"),
        "c803dc2195607a4fa674cef118c57c8c033681567027cb6cf3ed200cb6cdc185",
        "061dc5ef83fcaa4a4d4cfd75eb206904ab7eeaf798ae297ed4c33213727bf470",
        4,
    ),
    ArtifactSpec(
        "global",
        global_gap.ARTIFACT,
        "2026-07-22T03:56:03Z",
        (2_091, "eb8713267c4c94a473107cd9459abfba5c2aad19284c3c74c9206fba33acb13c"),
        "6304447459783043e3afb4f1d488451074bb65833d6a403f1458440e241d4192",
        "e3bfd0d237e044acebe9b8d7dcaf5f5863329fb71f9e5314287a0b89fd667214",
        4,
    ),
    ArtifactSpec(
        "coordinate_v2",
        coordinate.ARTIFACT,
        "2026-07-22T04:03:01Z",
        (1_820, "29b18e190f7347134ea90c37eafff35efc82b6c0a852eeb6ab5a96feb2565740"),
        "f1d62cacf7e879d724b9ace28da5cec0aae2176d8f5a2ccef9646c122f3328ae",
        "f9dc77b2f12ed033cd26b1eb02321959e18b5c85d9af0395cfb2986046b81b00",
        1,
    ),
    ArtifactSpec(
        "centra",
        centra.ARTIFACT,
        "2026-07-22T04:02:16Z",
        (1_730, "47bda388b9126b43e567b2072db468ed4db6355b87c974c12bbb4b5e2306f6a3"),
        "7e8f50bcac99202f9eef8142491d1db8751c47c6a0e04ed5d23f86faf33d7cf1",
        "72103a485726c8d122602cd2e142a3855280b98a3fa6ab6452d8d5b66691f9fe",
        1,
    ),
)

NORTHC_SUCCESSOR = (
    "source_artifacts/official-coordinate-assessment-aalsmeer-bue1-2026-07-22-v2/"
    "normalized-successors/curated-official-2026-07-22-northc-aalsmeer-phase-2-"
    "expansion-coordinate-v2.json"
)
REJECTED_COORDINATE_V1_SUCCESSOR = (
    "source_artifacts/official-coordinate-assessment-aalsmeer-bue1-2026-07-22-v1/"
    "normalized-successors/curated-official-2026-07-22-northc-aalsmeer-phase-2-"
    "expansion-coordinate-v1.json"
)
REJECTED_INCIDENT_PIN = (
    4_821,
    "dc7aea69f1c68c71ba500abd69baa2eabaaef686fd0a8b66308532cc811c6858",
)

SOURCE_SPECS = (
    SourceSpec(
        "sources/curated-official-2026-07-22-nscale-kvandal-narvik-current-build.json",
        (7_646, "d9502562d9be0b6d6361ee9d28256c5678d771aee70604baec11ccc48b6d9305"),
        1_784_692_260_012_123_558,
        "nordic",
    ),
    SourceSpec(
        NORTHC_SUCCESSOR,
        (12_373, "84b48f795ccf7d8a2f8f128454fd3ddc5297214c76818a489a222fcdc99ec9a4"),
        1_784_692_981_011_846_086,
        "coordinate_v2",
    ),
    SourceSpec(
        "sources/curated-official-2026-07-22-iren-childress-horizons-1-4-current-build.json",
        (11_682, "54ac0d2dfebf06b2763ce2b11801b6d22b47914f121bd0bf3a26e9008c86eef3"),
        1_784_692_260_012_904_554,
        "nordic",
    ),
    SourceSpec(
        "sources/curated-official-2026-07-22-bitzero-namsskogan-power-expansion-foundations.json",
        (7_854, "bd7167a2ebb723f26d573610cb927c4281d28e2b2ff637be3427253309580e77"),
        1_784_692_260_013_209_053,
        "nordic",
    ),
    SourceSpec(
        "sources/curated-official-2026-07-22-neutradc-nxera-batam-btm1-current-build.json",
        (11_438, "ddd06228274f34d9b545950efb47d4992f7704ff156926f7696465236a596c17"),
        1_784_692_563_013_015_771,
        "global",
    ),
    SourceSpec(
        "sources/curated-official-2026-07-22-cirion-bue1-expansion-current-build.json",
        (7_436, "71b173a1e5b3ffed5a018f7541a88fce51cc409092996c01ce2f13d368ab634b"),
        1_784_692_563_013_482_685,
        "global",
    ),
    SourceSpec(
        "sources/curated-official-2026-07-22-edgnex-second-jakarta-ai-current-build.json",
        (5_738, "412a60cde1ea4cdcd98f25738436e5378c6dd5c4261f88e1a31ead15aced330f"),
        1_784_692_563_013_905_266,
        "global",
    ),
    SourceSpec(
        "sources/curated-official-2026-07-22-cmc-creative-space-hanoi-data-center-tower-current-build.json",
        (10_867, "f9fc9210c7b76e12eaed415284d6d624292b04b3f1a636741b3fc17054ebe1a7"),
        1_784_692_563_014_210_723,
        "global",
    ),
    SourceSpec(
        "sources/curated-official-2026-07-22-centra-rno2-reno-shell-current-build.json",
        (10_407, "ba6df8d22ac19a3f9c84136bf6b0f1c41e2accc2cfb5760ad4b63657f6d21a2b"),
        1_784_692_936_008_108_513,
        "centra",
    ),
)
ADDITION_ORDER = tuple(spec.relative for spec in SOURCE_SPECS)
ADDITION_PINS = {spec.relative: spec.pin for spec in SOURCE_SPECS}

NORTHC_KEYS = frozenset({coordinate.NORTHC_CAMPUS_KEY, coordinate.NORTHC_PROJECT_KEY})
JAKARTA_PROJECT = global_gap.JAKARTA_PROJECT
HANOI_PROJECT = global_gap.CMC_PROJECT
STALE_SUPPRESSED_PROJECT_KEYS = frozenset({JAKARTA_PROJECT, HANOI_PROJECT})
STATUS_FIELDS = (
    "status",
    "status_as_of",
    "status_confidence",
    "status_method",
    "status_evidence_id",
)

ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:nscale-kvandal-narvik-ai-data-center-campus",
        "curated:nscale-kvandal-narvik-ai-data-center-campus:initial-25mw-epc-current-build",
        coordinate.NORTHC_CAMPUS_KEY,
        coordinate.NORTHC_PROJECT_KEY,
        "curated:iren-childress-ai-data-center-campus",
        "curated:iren-childress-ai-data-center-campus:horizons-1-4-current-build",
        "curated:bitzero-namsskogan-data-center-campus",
        "curated:bitzero-namsskogan-data-center-campus:2026-power-infrastructure-expansion",
        global_gap.BTM_CAMPUS,
        global_gap.BTM_PROJECT,
        global_gap.CIRION_CAMPUS,
        global_gap.CIRION_PROJECT,
        global_gap.JAKARTA_CAMPUS,
        global_gap.JAKARTA_PROJECT,
        global_gap.CMC_CAMPUS,
        global_gap.CMC_PROJECT,
        "curated:centra-rno2-reno-data-center",
        "curated:centra-rno2-reno-data-center:current-build",
    }
)
ADDED_PROJECT_KEYS = frozenset(
    {
        "curated:nscale-kvandal-narvik-ai-data-center-campus:initial-25mw-epc-current-build",
        coordinate.NORTHC_PROJECT_KEY,
        "curated:iren-childress-ai-data-center-campus:horizons-1-4-current-build",
        "curated:bitzero-namsskogan-data-center-campus:2026-power-infrastructure-expansion",
        global_gap.BTM_PROJECT,
        global_gap.CIRION_PROJECT,
        global_gap.JAKARTA_PROJECT,
        global_gap.CMC_PROJECT,
        "curated:centra-rno2-reno-data-center:current-build",
    }
)

LIFECYCLE_CONTRACT = {
    ("curated:nscale-kvandal-narvik-ai-data-center-campus:initial-25mw-epc-current-build", "under_construction", "2026-07-06", "authoritative_physical_status_update"),
    (coordinate.NORTHC_PROJECT_KEY, "expansion", "2026-04-01", "authoritative_physical_status_update"),
    ("curated:iren-childress-ai-data-center-campus:horizons-1-4-current-build", "under_construction", "2026-05-07", "authoritative_physical_status_update"),
    ("curated:bitzero-namsskogan-data-center-campus:2026-power-infrastructure-expansion", "foundations", "2026-06-15", "authoritative_physical_status_update"),
    (global_gap.BTM_PROJECT, "shell", "2025-10-30", "authoritative_physical_status_update"),
    (global_gap.CIRION_PROJECT, "expansion", "2025-08-21", "authoritative_physical_status_update"),
    (global_gap.JAKARTA_PROJECT, "under_construction", "2025-06-17", "authoritative_physical_status_update"),
    (global_gap.CMC_PROJECT, "under_construction", "2025-06-01", "authoritative_construction_start"),
    ("curated:centra-rno2-reno-data-center:current-build", "shell", "2026-04-30", "authoritative_physical_status_update"),
}
CAPACITY_CONTRACT = {
    (coordinate.NORTHC_PROJECT_KEY, "critical_it_mw", "planned", "MW", 2.4, "2026-04-01", "reported"),
    ("curated:iren-childress-ai-data-center-campus:horizons-1-4-current-build", "critical_it_mw", "contracted", "MW", 200.0, "2025-11-02", "reported"),
    (global_gap.BTM_PROJECT, "critical_it_mw", "planned", "MW", 18.0, "2025-10-30", "reported"),
}
MODEL_CONTRACT = {
    (global_gap.CIRION_CAMPUS, "colocation"),
    ("curated:centra-rno2-reno-data-center:current-build", "colocation"),
}

EXPECTED_DATABASE_COUNTS = {
    "entities": 1_029,
    "entity_snapshots": 1_054,
    "evidence": 867,
    "lifecycle_observations": 594,
    "capacity_estimates": 568,
    "operating_model_observations": 76,
    "workload_observations": 136,
}
INTERNAL_DELTA = {
    "entities": 18,
    "entity_snapshots": 18,
    "evidence": 22,
    "lifecycle_observations": 9,
    "capacity_estimates": 3,
    "operating_model_observations": 2,
    "workload_observations": 0,
}
PUBLIC_DELTA = {
    "entities": 18,
    "evidence": 13,
    "lifecycle_freshness": 9,
    "capacity_estimates": 3,
    "construction_pipeline": 7,
    "construction_source_signals": 9,
}
PUBLIC_COUNTS = {
    "entities": 1_029,
    "evidence": 678,
    "lifecycle_freshness": 571,
    "capacity_estimates": 567,
    "construction_pipeline": 520,
    "construction_source_signals": 420,
}

EXPORTED_EVIDENCE_KEYS = frozenset(
    {
        "neutradc-nxera-batam-btm1-topping-2025-10-30-captured-2026-07-22",
        "cirion-bue1-expansion-2025-08-21-captured-2026-07-22",
        "cirion-bue1-current-facility-page-captured-2026-07-22",
        "centra-rno2-topout-2026-04-30-captured-2026-07-22",
        "bitzero-namsskogan-transformer-foundations-2026-06-15",
        "iren-horizons-1-4-progress-update-2026-05-07",
        "cmc-creative-space-hanoi-groundbreaking-2025-06-01-archived-captured-2026-07-22",
        "nscale-nordscale-kvandal-construction-2026-07-06",
        "cmc-annual-report-2024-pdf-captured-2026-07-22",
        "iren-microsoft-horizons-1-4-contract-2025-11-02",
        coordinate.PDOK_EVIDENCE_KEY,
        "northc-aalsmeer-phase-2-expansion-2026-04-01",
        "damac-second-jakarta-early-construction-2025-06-17-archived-captured-2026-07-22",
    }
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pin(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), _sha256(raw)


def _canonical(value: Any, *, sort_keys: bool = False) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=sort_keys, ensure_ascii=False) + "\n"
    ).encode()


def _read_json(
    path: Path, *, mode: int | None = None, sort_keys: bool = False
) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise OpenSeedV95Error(f"ordinary JSON file is absent: {path}")
    if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
        raise OpenSeedV95Error(f"JSON mode differs: {path}")
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict) or raw != _canonical(value, sort_keys=sort_keys):
        raise OpenSeedV95Error(f"JSON is not canonical: {path}")
    return raw, value


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _csv_text(template: str, rows: Sequence[Mapping[str, str]]) -> str:
    reader = csv.DictReader(io.StringIO(template))
    if reader.fieldnames is None:
        raise OpenSeedV95Error("CSV template lacks a header")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=reader.fieldnames, lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _validate_generic_artifact(
    spec: ArtifactSpec, validator: Any
) -> dict[str, Any]:
    try:
        manifest = validator(spec.artifact)
    except RuntimeError as error:
        raise OpenSeedV95Error(f"{spec.label} artifact invalid: {error}") from error
    manifest_raw = (spec.artifact / "manifest.json").read_bytes()
    if (
        (len(manifest_raw), _sha256(manifest_raw)) != spec.manifest_pin
        or manifest.get("recorded_at") != spec.recorded_at
        or manifest.get("tree_sha256") != spec.logical_tree
        or v69.tree_digest(spec.artifact) != spec.physical_tree
        or manifest.get("curated_source_records") != spec.source_count
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
    ):
        raise OpenSeedV95Error(f"{spec.label} artifact pin differs")
    return manifest


def _validate_artifacts() -> dict[str, str]:
    specs = {spec.label: spec for spec in ARTIFACT_SPECS}
    _validate_generic_artifact(specs["nordic"], nordic.validate_artifact)
    _validate_generic_artifact(specs["global"], global_gap.validate_artifact)
    _validate_generic_artifact(specs["centra"], centra.validate_artifact)

    coordinate_spec = specs["coordinate_v2"]
    manifest = json.loads(
        (coordinate_spec.artifact / "manifest.json").read_text(encoding="utf-8")
    )
    try:
        payloads = coordinate.build_payloads(coordinate_spec.recorded_at)
        coordinate._verify_live(coordinate_spec.artifact, payloads)
    except RuntimeError as error:
        raise OpenSeedV95Error(f"coordinate v2 artifact invalid: {error}") from error
    manifest_raw = payloads["manifest.json"]
    if (
        (len(manifest_raw), _sha256(manifest_raw)) != coordinate_spec.manifest_pin
        or manifest.get("recorded_at") != coordinate_spec.recorded_at
        or manifest.get("tree_sha256") != coordinate_spec.logical_tree
        or v69.tree_digest(coordinate_spec.artifact)
        != coordinate_spec.physical_tree
        or _pin(coordinate_spec.artifact / "publication-incident.json")
        != REJECTED_INCIDENT_PIN
    ):
        raise OpenSeedV95Error("coordinate v2 or rejected-v1 incident pin differs")
    incident = json.loads(
        (coordinate_spec.artifact / "publication-incident.json").read_text()
    )
    if (
        incident.get("status") != "rejected_immutable_no_integration"
        or incident.get("disposition", {}).get("v1_must_not_be_integrated")
        is not True
        or incident.get("disposition", {}).get(
            "v1_successor_path_must_not_be_selected"
        )
        is not True
    ):
        raise OpenSeedV95Error("coordinate v1 rejection disposition differs")

    return {spec.label: spec.recorded_at for spec in ARTIFACT_SPECS}


def _validate_selected_documents() -> dict[str, dict[str, Any]]:
    artifact_times = _validate_artifacts()
    documents: dict[str, dict[str, Any]] = {}
    for spec in SOURCE_SPECS:
        path = ROOT / spec.relative
        raw, document = _read_json(path, mode=0o444)
        metadata = path.stat(follow_symlinks=False)
        recorded = v70.parse_utc(
            artifact_times[spec.artifact_label],
            label=f"{spec.artifact_label} recorded_at",
        )
        if (
            (len(raw), _sha256(raw)) != spec.pin
            or metadata.st_ctime_ns != spec.ctime_ns
            or max(metadata.st_birthtime, metadata.st_mtime)
            > recorded.timestamp() + 1e-6
        ):
            raise OpenSeedV95Error(f"selected source pin differs: {spec.relative}")
        documents[spec.relative] = document

    if (
        tuple(documents) != ADDITION_ORDER
        or len(documents) != 9
        or REJECTED_COORDINATE_V1_SUCCESSOR in documents
        or NORTHC_SUCCESSOR not in documents
        or any(
            row.endswith("northc-aalsmeer-phase-2-expansion.json")
            for row in documents
        )
    ):
        raise OpenSeedV95Error("v95 selected-source order or replacement differs")

    stable_keys = {
        document[entity]["stable_key"]
        for document in documents.values()
        for entity in ("campus", "project")
    }
    evidence_keys = [
        row["key"]
        for document in documents.values()
        for row in document["evidence"]
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
            row["as_of_date"],
            row["method"],
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
        row
        for document in documents.values()
        for row in document["workloads"]
    ]
    if (
        stable_keys != ADDED_ENTITY_KEYS
        or len(evidence_keys) != 22
        or len(set(evidence_keys)) != 22
        or lifecycle != LIFECYCLE_CONTRACT
        or capacities != CAPACITY_CONTRACT
        or models != MODEL_CONTRACT
        or workloads
    ):
        raise OpenSeedV95Error("v95 normalized source claim contract differs")
    if any(
        row["metric"] in {"annual_energy_mwh", "pue", "wue"}
        for document in documents.values()
        for row in document["capacities"]
    ):
        raise OpenSeedV95Error("v95 source normalized energy or efficiency")

    for relative, document in documents.items():
        for entity in ("campus", "project"):
            row = document[entity]
            if row["stable_key"] in NORTHC_KEYS:
                if (
                    row["coordinates"]
                    != {"latitude": 52.25979593, "longitude": 4.77335841}
                    or row["geometry"]
                    != {"type": "Point", "coordinates": [4.77335841, 52.25979593]}
                    or row["evidence_key"] != coordinate.PDOK_EVIDENCE_KEY
                    or row["method"] != "authoritative_address_geocode"
                ):
                    raise OpenSeedV95Error("NorthC coordinate successor differs")
            elif row["coordinates"] is not None or row["geometry"] is not None:
                raise OpenSeedV95Error(f"unexpected coordinate in {relative}")
    pdok = next(
        row
        for row in documents[NORTHC_SUCCESSOR]["evidence"]
        if row["key"] == coordinate.PDOK_EVIDENCE_KEY
    )
    if (
        pdok["metadata"].get("horizontal_uncertainty_m") != 50
        or "address point" not in pdok["metadata"].get("coordinate_scope", "")
        or "not as a data-centre" not in pdok["metadata"].get(
            "coordinate_scope", ""
        )
    ):
        raise OpenSeedV95Error("NorthC address-point scope differs")
    return documents


def _base_paths(base: Mapping[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for row in base["curated_inputs"]:
        path = ROOT / row["path"]
        if (
            path.is_symlink()
            or not path.is_file()
            or v69.sha256(path) != row["sha256"]
        ):
            raise OpenSeedV95Error(f"accepted v94 input pin differs: {row['path']}")
        paths.append(path)
    return paths


def selected_inputs(
    base: Mapping[str, Any],
    *,
    recorded_at: str,
    validation_wall_clock: datetime | None = None,
) -> tuple[list[dict[str, str]], list[Path]]:
    if base.get("release_id") != v94.RELEASE_ID:
        raise OpenSeedV95Error("v95 base must be exactly accepted v94")
    rows = base.get("curated_inputs")
    if (
        not isinstance(rows, list)
        or len(rows) != BASE_INPUT_COUNT
        or any(set(row) != {"path", "sha256"} for row in rows)
    ):
        raise OpenSeedV95Error("accepted v94 curated inventory differs")
    documents = _validate_selected_documents()
    target = v70.parse_utc(recorded_at, label="v95 recorded_at")
    wall = validation_wall_clock or datetime.now(UTC)
    if wall.tzinfo is None or target > wall.astimezone(UTC) or any(
        v70.parse_utc(spec.recorded_at, label=f"{spec.label} recorded_at")
        > target
        for spec in ARTIFACT_SPECS
    ):
        raise OpenSeedV95Error("v95 publication time precedes an input")

    paths = _base_paths(base)
    base_stable = {
        row["stable_key"] for row in _csv_rows(BASE_RELEASE / "entities.csv")
    }
    if base_stable & ADDED_ENTITY_KEYS:
        raise OpenSeedV95Error("v95 stable-key append collides with accepted v94")
    base_evidence: set[str] = set()
    for path in paths:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        base_evidence.update(
            row["key"]
            for row in document.get("evidence", [])
            if isinstance(row, dict) and isinstance(row.get("key"), str)
        )
    added_evidence = {
        row["key"]
        for document in documents.values()
        for row in document["evidence"]
    }
    if base_evidence & added_evidence:
        raise OpenSeedV95Error("v95 evidence append collides with accepted v94")

    selected = [dict(row) for row in rows]
    for spec in SOURCE_SPECS:
        selected.append({"path": spec.relative, "sha256": spec.pin[1]})
        paths.append(ROOT / spec.relative)
    if (
        selected[:BASE_INPUT_COUNT] != rows
        or [row["path"] for row in selected[BASE_INPUT_COUNT:]]
        != list(ADDITION_ORDER)
        or len(selected) != 507
        or len({row["path"] for row in selected}) != 507
    ):
        raise OpenSeedV95Error("v95 did not append exactly nine ordered inputs")
    for relative, document in documents.items():
        for index, evidence in enumerate(document["evidence"]):
            retrieved = v70.parse_utc(
                evidence["retrieved_at"],
                label=f"{relative} evidence[{index}].retrieved_at",
            )
            if retrieved > target or retrieved > wall.astimezone(UTC):
                raise OpenSeedV95Error("v95 selected evidence is future-dated")
    return selected, paths


def _table_state(connection: sqlite3.Connection, table: str) -> set[tuple[Any, ...]]:
    return {tuple(row) for row in connection.execute(f"SELECT * FROM {table}")}


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
        raise OpenSeedV95Error(f"v95 database counts differ: {counts}")
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v95-base-", dir="/private/tmp"
    ) as temporary:
        prior = v69._populate_database(
            base,
            _base_paths(base),
            Path(temporary) / "v94.sqlite",
            recorded_at=recorded_at,
        )
        try:
            for table in (
                "entities",
                "evidence",
                "campuses",
                "projects",
                "entity_snapshots",
                "lifecycle_observations",
                "operating_model_observations",
                "workload_observations",
                "capacity_estimates",
            ):
                if not _table_state(prior, table) <= _table_state(connection, table):
                    raise OpenSeedV95Error(f"v95 changed a v94 row: {table}")
            before = {
                row[0] for row in prior.execute("SELECT stable_key FROM entities")
            }
            after = {
                row[0] for row in connection.execute("SELECT stable_key FROM entities")
            }
            if after - before != ADDED_ENTITY_KEYS or before - after:
                raise OpenSeedV95Error("v95 database identity delta differs")
            before_evidence = set(v70._evidence_by_key(prior))
            after_evidence = set(v70._evidence_by_key(connection))
            if len(after_evidence - before_evidence) != 22 or before_evidence - after_evidence:
                raise OpenSeedV95Error("v95 database evidence delta differs")
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
        if row[0] in ADDED_PROJECT_KEYS
    }
    capacities = {
        tuple(row)
        for row in connection.execute(
            """
            SELECT entities.stable_key, metric, stage, unit, base, as_of_date,
                   capacity_estimates.method
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
        row
        for row in connection.execute(
            """
            SELECT entities.stable_key, workload
            FROM workload_observations
            JOIN entities ON entities.id=entity_id
            """
        )
        if row[0] in ADDED_ENTITY_KEYS
    ]
    if (
        lifecycle != LIFECYCLE_CONTRACT
        or capacities != CAPACITY_CONTRACT
        or models != MODEL_CONTRACT
        or workloads
    ):
        raise OpenSeedV95Error("v95 imported claim contract differs")

    stable_by_id = {
        row["id"]: row["stable_key"]
        for row in connection.execute("SELECT id, stable_key FROM entities")
    }
    snapshots = {
        stable_by_id[row["entity_id"]]: row
        for row in _current_rows(
            connection, "entity_snapshots", as_of=AS_OF, recorded_at=recorded_at
        )
        if stable_by_id[row["entity_id"]] in ADDED_ENTITY_KEYS
    }
    if set(snapshots) != ADDED_ENTITY_KEYS:
        raise OpenSeedV95Error("v95 current snapshot identity differs")
    for key, row in snapshots.items():
        if key in NORTHC_KEYS:
            if (
                float(row["latitude"]) != 52.25979593
                or float(row["longitude"]) != 4.77335841
                or json.loads(row["geometry_json"])
                != {"type": "Point", "coordinates": [4.77335841, 52.25979593]}
            ):
                raise OpenSeedV95Error("v95 NorthC database coordinate differs")
        elif (
            row["latitude"] is not None
            or row["longitude"] is not None
            or row["geometry_json"] not in {None, "null"}
        ):
            raise OpenSeedV95Error(f"v95 unexpected database coordinate: {key}")
    current = _current_rows(
        connection, "entity_snapshots", as_of=AS_OF, recorded_at=recorded_at
    )
    kinds = {
        row["id"]: row["kind"]
        for row in connection.execute("SELECT id, kind FROM entities")
    }
    located = [
        row
        for row in current
        if row["latitude"] is not None and row["longitude"] is not None
    ]
    if (
        len(located) != 215
        or sum(kinds[row["entity_id"]] == "campus" for row in located) != 142
    ):
        raise OpenSeedV95Error("v95 coordinate coverage differs")


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


def _successor_csv(
    output: dict[str, str],
    filename: str,
    *,
    key: str,
    expected_base: int,
    expected_added: int,
    allow_base_recomputation: bool = False,
) -> None:
    base_rows = _csv_rows(BASE_RELEASE / filename)
    current_rows = list(csv.DictReader(io.StringIO(output[filename])))
    base_by_key = {row[key]: row for row in base_rows}
    current_by_key = {row[key]: row for row in current_rows}
    if (
        len(base_rows) != expected_base
        or len(base_by_key) != len(base_rows)
        or len(current_by_key) != len(current_rows)
        or not set(base_by_key) <= set(current_by_key)
        or (
            not allow_base_recomputation
            and any(
                current_by_key[row_key] != row
                for row_key, row in base_by_key.items()
            )
        )
    ):
        raise OpenSeedV95Error(f"v95 {filename} altered a v94 row")
    added = [row for row in current_rows if row[key] not in base_by_key]
    if len(added) != expected_added or len({row[key] for row in added}) != len(added):
        raise OpenSeedV95Error(f"v95 {filename} append count differs")
    output[filename] = _csv_text(output[filename], [*base_rows, *added])


def _suppress_stale_public_status(output: dict[str, str]) -> None:
    entity_rows = list(csv.DictReader(io.StringIO(output["entities.csv"])))
    seen: set[str] = set()
    for row in entity_rows:
        if row["stable_key"] in STALE_SUPPRESSED_PROJECT_KEYS:
            seen.add(row["stable_key"])
            for field in STATUS_FIELDS:
                row[field] = ""
    if seen != STALE_SUPPRESSED_PROJECT_KEYS:
        raise OpenSeedV95Error("v95 stale entity suppression boundary differs")
    output["entities.csv"] = _csv_text(output["entities.csv"], entity_rows)

    pipeline = list(csv.DictReader(io.StringIO(output["construction_pipeline.csv"])))
    removed = {
        row["stable_key"]
        for row in pipeline
        if row["stable_key"] in STALE_SUPPRESSED_PROJECT_KEYS
    }
    if removed != STALE_SUPPRESSED_PROJECT_KEYS:
        raise OpenSeedV95Error("v95 stale pipeline suppression boundary differs")
    output["construction_pipeline.csv"] = _csv_text(
        output["construction_pipeline.csv"],
        [
            row
            for row in pipeline
            if row["stable_key"] not in STALE_SUPPRESSED_PROJECT_KEYS
        ],
    )

    geojson = json.loads(output["atlas.geojson"])
    seen.clear()
    for feature in geojson["features"]:
        properties = feature["properties"]
        if properties["stable_key"] in STALE_SUPPRESSED_PROJECT_KEYS:
            seen.add(properties["stable_key"])
            for field in STATUS_FIELDS:
                properties[field] = None
    if seen != STALE_SUPPRESSED_PROJECT_KEYS:
        raise OpenSeedV95Error("v95 stale GeoJSON suppression boundary differs")
    output["atlas.geojson"] = (
        json.dumps(geojson, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )


def _append_capacity(output: dict[str, str]) -> None:
    base = _csv_rows(BASE_RELEASE / "capacity_estimates.csv")
    current = list(csv.DictReader(io.StringIO(output["capacity_estimates.csv"])))
    base_counter = Counter(
        json.dumps(row, sort_keys=True, separators=(",", ":")) for row in base
    )
    current_counter = Counter(
        json.dumps(row, sort_keys=True, separators=(",", ":")) for row in current
    )
    if len(base) != 564 or base_counter - current_counter:
        raise OpenSeedV95Error("v95 capacity projection altered v94")
    added_counter = current_counter - base_counter
    added = [json.loads(raw) for raw in added_counter.elements()]
    if len(added) != 3:
        raise OpenSeedV95Error("v95 capacity append count differs")
    output["capacity_estimates.csv"] = _csv_text(
        output["capacity_estimates.csv"], [*base, *added]
    )


def _append_geojson(output: dict[str, str]) -> None:
    base = json.loads((BASE_RELEASE / "atlas.geojson").read_text())
    current = json.loads(output["atlas.geojson"])
    base_by_key = {
        feature["properties"]["stable_key"]: feature for feature in base["features"]
    }
    current_by_key = {
        feature["properties"]["stable_key"]: feature
        for feature in current["features"]
    }
    new = [
        feature
        for feature in current["features"]
        if feature["properties"]["stable_key"] not in base_by_key
    ]
    if (
        len(base["features"]) != 1_011
        or any(current_by_key.get(key) != feature for key, feature in base_by_key.items())
        or len(new) != 18
        or {feature["properties"]["stable_key"] for feature in new}
        != ADDED_ENTITY_KEYS
    ):
        raise OpenSeedV95Error("v95 GeoJSON append boundary differs")
    for feature in new:
        key = feature["properties"]["stable_key"]
        if key in NORTHC_KEYS:
            if feature["geometry"] != {
                "type": "Point",
                "coordinates": [4.77335841, 52.25979593],
            }:
                raise OpenSeedV95Error("v95 NorthC GeoJSON point differs")
        elif feature["geometry"] is not None:
            raise OpenSeedV95Error(f"v95 unexpected new geometry: {key}")
    current["features"] = [*base["features"], *new]
    output["atlas.geojson"] = (
        json.dumps(current, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )


def _append_source_inputs(output: dict[str, str]) -> None:
    base = json.loads((BASE_RELEASE / "source_inputs.json").read_text())["sources"]
    current = json.loads(output["source_inputs.json"])["sources"]
    base_rows = {
        json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        for row in base
    }
    added = [
        row
        for row in current
        if json.dumps(
            row, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        not in base_rows
    ]
    if len(base) != 592 or len(added) != 13:
        raise OpenSeedV95Error("v95 source-input projection differs")
    output["source_inputs.json"] = (
        json.dumps(
            {"sources": [*base, *added]},
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )


STALE_POLICY = {
    "policy_version": 1,
    "stable_keys": sorted(STALE_SUPPRESSED_PROJECT_KEYS),
    "entities_status_fields_blank": list(STATUS_FIELDS),
    "geojson_status_fields_null": list(STATUS_FIELDS),
    "construction_pipeline_excluded": True,
    "lifecycle_freshness_retained": True,
    "construction_source_signals_retained": True,
    "required_freshness_class": "stale_over_365_days",
    "current_status_classification": "unknown",
    "current_construction_claim": False,
    "successor_rehydration_forbidden": True,
}
COORDINATE_BOUNDARY = {
    "stable_keys": sorted(NORTHC_KEYS),
    "longitude": 4.77335841,
    "latitude": 52.25979593,
    "horizontal_uncertainty_m": 50,
    "method": "authoritative_address_geocode",
    "scope": "official BAG address point only; not site, footprint, parcel, or facility centroid",
    "bue1_coordinate_accepted": False,
}


def _append_only_projection(output: dict[str, str]) -> None:
    _suppress_stale_public_status(output)
    _successor_csv(
        output,
        "entities.csv",
        key="stable_key",
        expected_base=1_011,
        expected_added=18,
    )
    _successor_csv(
        output,
        "evidence.csv",
        key="evidence_id",
        expected_base=665,
        expected_added=13,
    )
    _successor_csv(
        output,
        "lifecycle_freshness.csv",
        key="stable_key",
        expected_base=562,
        expected_added=9,
        allow_base_recomputation=True,
    )
    _successor_csv(
        output,
        "construction_pipeline.csv",
        key="stable_key",
        expected_base=513,
        expected_added=7,
    )
    _successor_csv(
        output,
        "construction_source_signals.csv",
        key="source_observation_evidence_id",
        expected_base=411,
        expected_added=9,
    )
    _append_capacity(output)
    _append_geojson(output)
    _append_source_inputs(output)
    for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
        if output[filename].encode() != (BASE_RELEASE / filename).read_bytes():
            raise OpenSeedV95Error(f"v95 changed unrelated output: {filename}")

    summary = json.loads(output["summary.json"])
    summary.update(
        {
            "entities_total": 1_029,
            "campuses_total": 533,
            "projects_total": 496,
            "evidence_total": 867,
            "lifecycle_observations_current": 571,
            "capacity_estimates_current": 567,
            "construction_pipeline_records": 520,
            "construction_source_signals": 420,
            "entities_with_coordinates": 215,
            "campuses_with_coordinates": 142,
        }
    )
    summary["append_projection"] = {
        "base_release_id": v94.RELEASE_ID,
        "base_rows_frozen": True,
        "unaffected_base_rows_frozen": True,
        "governed_base_row_replacements": {},
        "curated_source_input_delta": 9,
        "internal_database_delta": INTERNAL_DELTA,
        "public_release_delta": PUBLIC_DELTA,
        "public_source_input_rows_delta": 13,
        "stale_status_suppression": STALE_POLICY,
        "coordinate_boundary": COORDINATE_BOUNDARY,
        "rejected_coordinate_v1_selected": False,
        "downstream_rehydration_guard": (
            "Jakarta and Hanoi remain dated historical observations; no successor "
            "may republish their suppressed values as current without newer evidence."
        ),
    }
    output["summary.json"] = _canonical(summary, sort_keys=True).decode()


FRESHNESS_README = """## Governed v95 successor boundary

Open seed v95 is the exact governed accepted-v94 successor for nine ordered
inputs. The corrected NorthC coordinate-v2 source replaces, rather than adds
to, its original Nordic predecessor; rejected coordinate v1 is incident
lineage only and is never selected. CENTRA RNO2 is the ninth input.

All 1,011 v94 entity rows and every other unaffected v94 public row remain
byte-identical. V95 adds 18 entities, 22 internal evidence records, nine dated
lifecycle observations, three typed critical-IT capacities, and exactly two
generic colocation observations. It adds no workload or energy/efficiency fact.

Jakarta and Hanoi retain their internal dated lifecycle, public stale freshness,
and source-signal history, but their public entity and GeoJSON status fields are
blank/null and they are omitted from the construction pipeline. Both remain
current-status unknown and are guarded against silent downstream rehydration.

Only the NorthC Aalsmeer campus/project receive coordinates: the exact official
BAG address-result point at 4.77335841, 52.25979593 with 50 m horizontal
uncertainty. It is an address point only, not a site, footprint, parcel, campus,
building, or facility centroid. BUE1 remains unmapped.
"""


def _augment_release(documents: Mapping[str, str]) -> dict[str, str]:
    previous_as_of = v85.AS_OF
    try:
        v85.AS_OF = AS_OF
        output = v94.v93.v92.v91._augment_release(documents)
    finally:
        v85.AS_OF = previous_as_of
    _append_only_projection(output)
    output["README.md"] = output["README.md"].rstrip() + "\n\n" + FRESHNESS_README
    manifest = json.loads(output["manifest.json"])
    manifest.update(
        {
            "as_of": AS_OF,
            "entities": 1_029,
            "entities_by_kind": {"campus": 533, "project": 496},
            "evidence_records": 678,
            "lifecycle_freshness_records": 571,
            "capacity_estimates": 567,
            "construction_pipeline_records": 520,
            "construction_source_signals": 420,
            "append_only_base_release": v94.RELEASE_ID,
            "base_rows_frozen": True,
            "unaffected_base_rows_frozen": True,
            "governed_base_row_replacements": {},
            "curated_source_input_delta": 9,
            "internal_database_delta": INTERNAL_DELTA,
            "public_release_delta": PUBLIC_DELTA,
            "public_source_input_rows_delta": 13,
            "stale_status_suppression": STALE_POLICY,
            "coordinate_boundary": COORDINATE_BOUNDARY,
            "rejected_coordinate_v1_selected": False,
        }
    )
    for filename, text in output.items():
        if filename != "manifest.json":
            manifest["files"][filename] = {
                "bytes": len(text.encode()),
                "sha256": _sha256(text.encode()),
            }
    output["manifest.json"] = _canonical(manifest, sort_keys=True).decode()
    return output


def _write_release(
    connection: sqlite3.Connection,
    output: Path,
    *,
    recorded_at: str,
    precreated: bool = False,
) -> None:
    if precreated:
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise OpenSeedV95Error("precreated v95 release stage must be empty")
    else:
        output.mkdir(parents=True, exist_ok=False)
    documents = build_release_documents(
        connection,
        as_of=AS_OF,
        recorded_at=recorded_at,
        publication_contract_version=4,
    )
    for filename, text in _augment_release(documents).items():
        path = output / filename
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(text.encode())
            stream.flush()
            os.fsync(stream.fileno())


def _validate_base() -> None:
    files = list(BASE_RELEASE.iterdir()) if BASE_RELEASE.is_dir() else []
    definition = json.loads(BASE_DEFINITION.read_text())
    manifest = json.loads((BASE_RELEASE / "manifest.json").read_text())
    if (
        v94.DEFINITION != BASE_DEFINITION
        or v94.RELEASE != BASE_RELEASE
        or BASE_DEFINITION.is_symlink()
        or not BASE_DEFINITION.is_file()
        or stat.S_IMODE(BASE_DEFINITION.stat().st_mode) != 0o444
        or BASE_RELEASE.is_symlink()
        or not BASE_RELEASE.is_dir()
        or stat.S_IMODE(BASE_RELEASE.stat().st_mode) != 0o555
        or any(
            path.is_symlink()
            or not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != 0o444
            for path in files
        )
        or _pin(BASE_DEFINITION) != BASE_DEFINITION_PIN
        or _pin(BASE_RELEASE / "manifest.json") != BASE_MANIFEST_PIN
        or _pin(BASE_RELEASE / "entities.csv") != BASE_ENTITIES_PIN
        or _pin(BASE_RELEASE / "source_inputs.json") != BASE_SOURCE_INPUTS_PIN
        or v69.tree_digest(BASE_RELEASE) != BASE_TREE_SHA256
        or definition.get("release_id") != v94.RELEASE_ID
        or definition.get("build", {}).get("recorded_at") != BASE_RECORDED_AT
        or manifest.get("recorded_at") != BASE_RECORDED_AT
    ):
        raise OpenSeedV95Error("accepted v94 base pin differs")
    for filename, pin in manifest["files"].items():
        if _pin(BASE_RELEASE / filename) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV95Error(f"accepted v94 member pin differs: {filename}")


def _guard_state() -> dict[str, Any]:
    _validate_base()
    _validate_selected_documents()
    return {
        "base_definition": _pin(BASE_DEFINITION),
        "base_manifest": _pin(BASE_RELEASE / "manifest.json"),
        "base_entities": _pin(BASE_RELEASE / "entities.csv"),
        "base_source_inputs": _pin(BASE_RELEASE / "source_inputs.json"),
        "base_tree": v69.tree_digest(BASE_RELEASE),
        "artifact_manifests": {
            spec.label: _pin(spec.artifact / "manifest.json")
            for spec in ARTIFACT_SPECS
        },
        "artifact_trees": {
            spec.label: v69.tree_digest(spec.artifact) for spec in ARTIFACT_SPECS
        },
        "selected_sources": {
            spec.relative: _pin(ROOT / spec.relative) for spec in SOURCE_SPECS
        },
        "rejected_incident": _pin(
            coordinate.ARTIFACT / "publication-incident.json"
        ),
    }


def _validate_guard(guard: Mapping[str, Any]) -> None:
    if (
        guard["base_definition"] != BASE_DEFINITION_PIN
        or guard["base_manifest"] != BASE_MANIFEST_PIN
        or guard["base_entities"] != BASE_ENTITIES_PIN
        or guard["base_source_inputs"] != BASE_SOURCE_INPUTS_PIN
        or guard["base_tree"] != BASE_TREE_SHA256
        or guard["artifact_manifests"]
        != {spec.label: spec.manifest_pin for spec in ARTIFACT_SPECS}
        or guard["artifact_trees"]
        != {spec.label: spec.physical_tree for spec in ARTIFACT_SPECS}
        or guard["selected_sources"] != ADDITION_PINS
        or guard["rejected_incident"] != REJECTED_INCIDENT_PIN
    ):
        raise OpenSeedV95Error("v95 immutable-input guard differs")


def _validate_public_delta(stage: Path) -> None:
    keyed = {
        "entities.csv": ("stable_key", 18),
        "evidence.csv": ("evidence_id", 13),
        "lifecycle_freshness.csv": ("stable_key", 9),
        "construction_pipeline.csv": ("stable_key", 7),
        "construction_source_signals.csv": (
            "source_observation_evidence_id",
            9,
        ),
    }
    for filename, (key, expected_added) in keyed.items():
        base = _csv_rows(BASE_RELEASE / filename)
        current = _csv_rows(stage / filename)
        base_by_key = {row[key]: row for row in base}
        current_by_key = {row[key]: row for row in current}
        if (
            any(current_by_key.get(row_key) != row for row_key, row in base_by_key.items())
            or len(set(current_by_key) - set(base_by_key)) != expected_added
            or set(base_by_key) - set(current_by_key)
        ):
            raise OpenSeedV95Error(f"v95 public row delta differs: {filename}")

    base_capacity = Counter(
        json.dumps(row, sort_keys=True, separators=(",", ":"))
        for row in _csv_rows(BASE_RELEASE / "capacity_estimates.csv")
    )
    current_capacity = Counter(
        json.dumps(row, sort_keys=True, separators=(",", ":"))
        for row in _csv_rows(stage / "capacity_estimates.csv")
    )
    if base_capacity - current_capacity or sum(
        (current_capacity - base_capacity).values()
    ) != 3:
        raise OpenSeedV95Error("v95 public capacity delta differs")

    base_geojson = json.loads((BASE_RELEASE / "atlas.geojson").read_text())
    current_geojson = json.loads((stage / "atlas.geojson").read_text())
    base_by_key = {
        row["properties"]["stable_key"]: row for row in base_geojson["features"]
    }
    current_by_key = {
        row["properties"]["stable_key"]: row
        for row in current_geojson["features"]
    }
    if (
        any(current_by_key.get(key) != row for key, row in base_by_key.items())
        or set(current_by_key) - set(base_by_key) != ADDED_ENTITY_KEYS
        or set(base_by_key) - set(current_by_key)
    ):
        raise OpenSeedV95Error("v95 GeoJSON delta differs")
    for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
        if (stage / filename).read_bytes() != (BASE_RELEASE / filename).read_bytes():
            raise OpenSeedV95Error(f"v95 unrelated output changed: {filename}")


def _validate_release_facts(stage: Path, *, recorded_at: str) -> None:
    if stage.is_symlink() or not stage.is_dir():
        raise OpenSeedV95Error("v95 release stage is not an ordinary directory")
    entries = {path.name: path for path in stage.iterdir()}
    if len(entries) != 14 or any(
        path.is_symlink() or not path.is_file() for path in entries.values()
    ):
        raise OpenSeedV95Error("v95 release inventory differs")
    manifest_raw, manifest = _read_json(stage / "manifest.json", sort_keys=True)
    if (
        manifest.get("as_of") != AS_OF
        or manifest.get("recorded_at") != recorded_at
        or manifest.get("publication_contract_version") != 4
        or manifest.get("entities") != 1_029
        or manifest.get("entities_by_kind") != {"campus": 533, "project": 496}
        or manifest.get("evidence_records") != 678
        or manifest.get("lifecycle_freshness_records") != 571
        or manifest.get("capacity_estimates") != 567
        or manifest.get("construction_pipeline_records") != 520
        or manifest.get("construction_source_signals") != 420
        or manifest.get("append_only_base_release") != v94.RELEASE_ID
        or manifest.get("base_rows_frozen") is not True
        or manifest.get("unaffected_base_rows_frozen") is not True
        or manifest.get("curated_source_input_delta") != 9
        or manifest.get("internal_database_delta") != INTERNAL_DELTA
        or manifest.get("public_release_delta") != PUBLIC_DELTA
        or manifest.get("stale_status_suppression") != STALE_POLICY
        or manifest.get("coordinate_boundary") != COORDINATE_BOUNDARY
        or manifest.get("rejected_coordinate_v1_selected") is not False
        or set(entries) != set(manifest["files"]) | {"manifest.json"}
    ):
        raise OpenSeedV95Error("v95 manifest facts differ")
    for filename, pin in manifest["files"].items():
        if _pin(entries[filename]) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV95Error(f"v95 release pin differs: {filename}")
    _validate_public_delta(stage)

    entities = {
        row["stable_key"]: row
        for row in _csv_rows(stage / "entities.csv")
        if row["stable_key"] in ADDED_ENTITY_KEYS
    }
    if set(entities) != ADDED_ENTITY_KEYS:
        raise OpenSeedV95Error("v95 added entity inventory differs")
    for key, row in entities.items():
        if key in STALE_SUPPRESSED_PROJECT_KEYS and any(
            row[field] for field in STATUS_FIELDS
        ):
            raise OpenSeedV95Error(f"v95 stale status persisted: {key}")
        if key in NORTHC_KEYS:
            if (
                float(row["latitude"]) != 52.25979593
                or float(row["longitude"]) != 4.77335841
                or json.loads(row["geometry_json"])
                != {"type": "Point", "coordinates": [4.77335841, 52.25979593]}
            ):
                raise OpenSeedV95Error("v95 public NorthC coordinate differs")
        elif row["latitude"] or row["longitude"] or row["geometry_json"] != "null":
            raise OpenSeedV95Error(f"v95 unexpected public coordinate: {key}")

    freshness = {
        row["stable_key"]: row
        for row in _csv_rows(stage / "lifecycle_freshness.csv")
        if row["stable_key"] in ADDED_PROJECT_KEYS
    }
    if set(freshness) != ADDED_PROJECT_KEYS or any(
        row["status_semantics"] != "last_observed"
        or row["current_status_classification"] != "unknown"
        or row["current_construction_claim"] != "false"
        for row in freshness.values()
    ):
        raise OpenSeedV95Error("v95 freshness semantics differ")
    if {
        key
        for key, row in freshness.items()
        if row["freshness_class"] == "stale_over_365_days"
    } != STALE_SUPPRESSED_PROJECT_KEYS:
        raise OpenSeedV95Error("v95 stale-freshness boundary differs")
    pipeline = {
        row["stable_key"]
        for row in _csv_rows(stage / "construction_pipeline.csv")
        if row["stable_key"] in ADDED_PROJECT_KEYS
    }
    if pipeline != ADDED_PROJECT_KEYS - STALE_SUPPRESSED_PROJECT_KEYS:
        raise OpenSeedV95Error("v95 pipeline suppression differs")
    signals = {
        row["representative_stable_key"]
        for row in _csv_rows(stage / "construction_source_signals.csv")
        if row["representative_stable_key"] in ADDED_PROJECT_KEYS
    }
    if signals != ADDED_PROJECT_KEYS:
        raise OpenSeedV95Error("v95 source-signal history differs")

    sources = json.loads((stage / "source_inputs.json").read_text())["sources"]
    base_sources = json.loads(
        (BASE_RELEASE / "source_inputs.json").read_text()
    )["sources"]
    added_sources = sources[len(base_sources) :]
    if (
        sources[: len(base_sources)] != base_sources
        or len(added_sources) != 13
        or {
            row.get("provenance", {}).get("curated_record_key")
            for row in added_sources
        }
        != EXPORTED_EVIDENCE_KEYS
    ):
        raise OpenSeedV95Error("v95 source-input evidence boundary differs")

    summary = json.loads((stage / "summary.json").read_text())
    projection = summary.get("append_projection")
    if (
        summary.get("entities_total") != 1_029
        or summary.get("campuses_total") != 533
        or summary.get("projects_total") != 496
        or summary.get("evidence_total") != 867
        or summary.get("lifecycle_observations_current") != 571
        or summary.get("capacity_estimates_current") != 567
        or summary.get("construction_pipeline_records") != 520
        or summary.get("construction_source_signals") != 420
        or summary.get("entities_with_coordinates") != 215
        or summary.get("campuses_with_coordinates") != 142
        or not isinstance(projection, dict)
        or projection.get("internal_database_delta") != INTERNAL_DELTA
        or projection.get("public_release_delta") != PUBLIC_DELTA
        or projection.get("stale_status_suppression") != STALE_POLICY
        or projection.get("coordinate_boundary") != COORDINATE_BOUNDARY
    ):
        raise OpenSeedV95Error("v95 summary contract differs")
    readme = (stage / "README.md").read_text(encoding="utf-8")
    for marker in (
        "Open seed v95 is the exact governed accepted-v94 successor",
        "rejected coordinate v1 is incident",
        "All 1,011 v94 entity rows",
        "Jakarta and Hanoi retain their internal dated lifecycle",
        "omitted from the construction pipeline",
        "address point only",
        "BUE1 remains unmapped",
    ):
        if marker not in readme:
            raise OpenSeedV95Error(f"v95 README guardrail differs: {marker}")
    if not manifest_raw:
        raise OpenSeedV95Error("v95 manifest unexpectedly empty")


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
    document["release_id"] = RELEASE_ID
    return document


def _fsync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _freeze(definition: Path, release: Path) -> None:
    definition.chmod(0o444)
    _fsync(definition)
    descendants = _release_descendants(release)
    for path in descendants:
        if path.is_file():
            path.chmod(0o444)
            _fsync(path)
    for path in sorted(
        (path for path in descendants if path.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        path.chmod(0o555)
        _fsync(path)
    release.chmod(0o555)
    _fsync(release)


def _thaw_private_stage(definition: Path, release: Path) -> None:
    """Make a verified private stage removable without changing its bytes."""

    if release.exists() and not release.is_symlink():
        release.chmod(0o700)
        for path in release.rglob("*"):
            path.chmod(0o700 if path.is_dir() else 0o600)
    if definition.exists() and not definition.is_symlink():
        definition.chmod(0o600)


def _release_descendants(root: Path) -> list[Path]:
    return sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix())


def _validate_publication_times(
    definition: Path,
    release: Path,
    *,
    recorded_at: str,
    require_live: bool,
) -> None:
    target = v70.parse_utc(recorded_at, label="v95 recorded_at")
    paths = [definition, release, *_release_descendants(release)]
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV95Error(
                f"v95 inode birth/mtime post-dates recorded_at: {path}"
            )
    if require_live:
        if datetime.now(UTC) < target:
            raise OpenSeedV95Error("v95 recorded_at is not live")
        for path in paths:
            if path.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
                raise OpenSeedV95Error(
                    f"v95 recursive ctime predates recorded_at: {path}"
                )


def validate_open_seed_v95(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
    require_live: bool = True,
) -> dict[str, Any]:
    if replay_count != 2:
        raise OpenSeedV95Error("v95 requires exactly two offline replays")
    guard = _guard_state()
    _validate_guard(guard)
    base = json.loads(BASE_DEFINITION.read_text())
    _raw, definition = _read_json(
        definition_path,
        mode=0o444 if require_frozen else None,
        sort_keys=True,
    )
    if set(definition) != set(base) or definition.get("release_id") != RELEASE_ID:
        raise OpenSeedV95Error("v95 definition identity differs")
    build = definition.get("build")
    if (
        not isinstance(build, dict)
        or build.get("as_of") != AS_OF
        or set(build) != {"as_of", "recorded_at"}
    ):
        raise OpenSeedV95Error("v95 definition build carrier differs")
    wall = validation_wall_clock or datetime.now(UTC)
    recorded = v70.parse_utc(build["recorded_at"], label="v95 recorded_at")
    if wall.tzinfo is None or recorded > wall.astimezone(UTC):
        raise OpenSeedV95Error("v95 recorded_at exceeds validation wall clock")
    selected, paths = selected_inputs(
        base, recorded_at=build["recorded_at"], validation_wall_clock=wall
    )
    if definition.get("curated_inputs") != selected:
        raise OpenSeedV95Error("v95 definition selected inputs differ")
    descendants = _release_descendants(release_path) if release_path.is_dir() else []
    if release_path.is_symlink() or not release_path.is_dir() or (
        require_frozen
        and (
            stat.S_IMODE(release_path.stat().st_mode) != 0o555
            or any(
                path.is_symlink()
                or (
                    path.is_dir()
                    and stat.S_IMODE(path.stat().st_mode) != 0o555
                )
                or (
                    path.is_file()
                    and stat.S_IMODE(path.stat().st_mode) != 0o444
                )
                or (not path.is_dir() and not path.is_file())
                for path in descendants
            )
        )
    ):
        raise OpenSeedV95Error("v95 staged release is not frozen")
    manifest_raw = (release_path / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    if _sha256(manifest_raw) != definition["expected_release"]["manifest_sha256"]:
        raise OpenSeedV95Error("v95 expected manifest hash differs")
    if {
        key: value for key, value in manifest.items() if key != "files"
    } != {
        key: value
        for key, value in definition["expected_release"].items()
        if key != "manifest_sha256"
    }:
        raise OpenSeedV95Error("v95 expected release facts differ")
    _validate_release_facts(release_path, recorded_at=build["recorded_at"])
    _validate_publication_times(
        definition_path,
        release_path,
        recorded_at=build["recorded_at"],
        require_live=require_live,
    )
    summary = json.loads((release_path / "summary.json").read_text())
    if {
        key: summary[key] for key in definition["expected_summary"]
    } != definition["expected_summary"]:
        raise OpenSeedV95Error("v95 expected summary differs")

    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v95-replay-{replay + 1}-", dir="/private/tmp"
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
                    connection, replay_release, recorded_at=build["recorded_at"]
                )
            finally:
                connection.close()
            _validate_release_facts(
                replay_release, recorded_at=build["recorded_at"]
            )
            for filename in set(manifest["files"]) | {"manifest.json"}:
                if (replay_release / filename).read_bytes() != (
                    release_path / filename
                ).read_bytes():
                    raise OpenSeedV95Error(f"v95 offline replay differs: {filename}")
    if _guard_state() != guard:
        raise OpenSeedV95Error("v95 validation mutated accepted inputs")
    return manifest


def validate_staged_open_seed_v95(
    definition_path: Path,
    release_path: Path,
    *,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
) -> dict[str, Any]:
    return validate_open_seed_v95(
        definition_path,
        release_path,
        require_frozen=True,
        replay_count=replay_count,
        validation_wall_clock=validation_wall_clock,
        require_live=False,
    )


def prepare_open_seed_v95(recorded_at: str | None = None) -> dict[str, Any]:
    """Build, freeze, replay, validate, and discard a private v95 stage."""

    if (
        DEFINITION.exists()
        or DEFINITION.is_symlink()
        or RELEASE.exists()
        or RELEASE.is_symlink()
        or PUBLICATION_LOCK.exists()
        or PUBLICATION_LOCK.is_symlink()
    ):
        raise OpenSeedV95Error("v95 final path or publication lock already exists")
    target = (
        v70.parse_utc(recorded_at, label="v95 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=90)
    )
    if target <= datetime.now(UTC):
        raise OpenSeedV95Error("v95 prepublication recorded_at must be future")
    recorded_at = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    guard = _guard_state()
    _validate_guard(guard)
    base = json.loads(BASE_DEFINITION.read_text())
    selected, paths = selected_inputs(
        base, recorded_at=recorded_at, validation_wall_clock=target
    )
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v95-prepublication-", dir="/private/tmp"
    ) as temporary:
        root = Path(temporary)
        release = root / "release"
        definition = root / DEFINITION.name
        try:
            connection = _build_database(
                base, paths, root / "atlas.sqlite", recorded_at=recorded_at
            )
            try:
                _write_release(connection, release, recorded_at=recorded_at)
            finally:
                connection.close()
            _validate_release_facts(release, recorded_at=recorded_at)
            definition.write_bytes(
                _canonical(
                    _definition_document(
                        base, selected, release, recorded_at=recorded_at
                    ),
                    sort_keys=True,
                )
            )
            _freeze(definition, release)
            manifest = validate_staged_open_seed_v95(
                definition,
                release,
                validation_wall_clock=target,
            )
            result = {
                "status": "prepublication-validated",
                "publication_authorized": False,
                "barrier": "stopped-before-no-replace-promotion",
                "recorded_at": recorded_at,
                "definition_sha256": v69.sha256(definition),
                "manifest_sha256": v69.sha256(release / "manifest.json"),
                "release_tree_sha256": v69.tree_digest(release),
                "entities": manifest["entities"],
                "final_definition_absent": not DEFINITION.exists(),
                "final_release_absent": not RELEASE.exists(),
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
        raise OpenSeedV95Error("v95 prepublication left residue or mutated inputs")
    return result


def _path_identity(path: Path, *, directory: bool) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    expected = (
        stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    )
    if not expected or path.is_symlink():
        raise OpenSeedV95Error(f"v95 stage type differs: {path}")
    return metadata.st_dev, metadata.st_ino


def _release_identities(root: Path) -> dict[str, tuple[str, int, int]]:
    identities: dict[str, tuple[str, int, int]] = {}
    for path in [root, *_release_descendants(root)]:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise OpenSeedV95Error(f"v95 stage contains symlink: {relative}")
        metadata = path.stat(follow_symlinks=False)
        kind = "directory" if stat.S_ISDIR(metadata.st_mode) else "file"
        if kind == "file" and not stat.S_ISREG(metadata.st_mode):
            raise OpenSeedV95Error(f"v95 stage contains special member: {relative}")
        identities[relative] = (kind, metadata.st_dev, metadata.st_ino)
    return identities


def _assert_release_identities(
    root: Path, expected: Mapping[str, tuple[str, int, int]]
) -> None:
    if _release_identities(root) != dict(expected):
        raise OpenSeedV95Error("v95 release stage recursive identity changed")


def _discard_release_stage(
    root: Path, expected: Mapping[str, tuple[str, int, int]]
) -> None:
    if not root.exists() and not root.is_symlink():
        return
    _assert_release_identities(root, expected)
    root.chmod(0o700)
    descendants = _release_descendants(root)
    for path in descendants:
        path.chmod(0o700 if path.is_dir() else 0o600)
    shutil.rmtree(root)


def _discard_file_stage(path: Path, identity: tuple[int, int]) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if _path_identity(path, directory=False) != identity:
        raise OpenSeedV95Error("refusing substituted v95 definition cleanup")
    path.chmod(0o600)
    path.unlink()


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise OpenSeedV95Error("active v95 publication lock exists") from error
    os.write(descriptor, f"pid={os.getpid()}\n".encode())
    os.fsync(descriptor)
    metadata = os.fstat(descriptor)
    identity = (metadata.st_dev, metadata.st_ino)
    try:
        yield
    finally:
        os.close(descriptor)
        try:
            current = PUBLICATION_LOCK.stat(follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if (
                not stat.S_ISREG(current.st_mode)
                or (current.st_dev, current.st_ino) != identity
            ):
                raise OpenSeedV95Error("refusing substituted v95 lock cleanup")
            PUBLICATION_LOCK.unlink()


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _refresh_publication_ctimes(definition: Path, release: Path) -> None:
    definition.chmod(0o400)
    definition.chmod(0o444)
    _fsync(definition)
    descendants = _release_descendants(release)
    for path in descendants:
        if path.is_file():
            path.chmod(0o400)
            path.chmod(0o444)
            _fsync(path)
    for path in sorted(
        (path for path in descendants if path.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        path.chmod(0o500)
        path.chmod(0o555)
        _fsync(path)
    release.chmod(0o500)
    release.chmod(0o555)
    _fsync(release)


def _require_absent(label: str) -> None:
    if DEFINITION.exists() or DEFINITION.is_symlink():
        raise OpenSeedV95Error(f"{label} v95 definition collision")
    if RELEASE.exists() or RELEASE.is_symlink():
        raise OpenSeedV95Error(f"{label} v95 release collision")


def _rollback_release(release_identity: tuple[int, int], stage: Path) -> None:
    if _path_identity(RELEASE, directory=True) != release_identity:
        raise OpenSeedV95Error("refusing rollback of substituted v95 release")
    if stage.exists() or stage.is_symlink():
        raise OpenSeedV95Error("v95 release rollback stage is occupied")
    v69.promote_noreplace(RELEASE, stage)


def _rollback_definition(definition_identity: tuple[int, int], stage: Path) -> None:
    if _path_identity(DEFINITION, directory=False) != definition_identity:
        raise OpenSeedV95Error("refusing rollback of substituted v95 definition")
    if stage.exists() or stage.is_symlink():
        raise OpenSeedV95Error("v95 definition rollback stage is occupied")
    v69.promote_noreplace(DEFINITION, stage)


def build_open_seed_v95(
    recorded_at: str | None = None, *, publication_authorized: bool = False
) -> dict[str, Any]:
    """Atomically publish v95 only behind the explicit authorization gate."""

    if not publication_authorized:
        raise OpenSeedV95Error(
            "v95 publication requires publication_authorized=True"
        )
    if (DEFINITION.exists() or DEFINITION.is_symlink()) and (
        RELEASE.exists() or RELEASE.is_symlink()
    ):
        manifest = validate_open_seed_v95(DEFINITION, RELEASE)
        return {
            "definition": str(DEFINITION),
            "definition_sha256": v69.sha256(DEFINITION),
            "manifest_sha256": v69.sha256(RELEASE / "manifest.json"),
            "recorded_at": manifest["recorded_at"],
            "release": str(RELEASE),
            "release_tree_sha256": v69.tree_digest(RELEASE),
            "status": "existing-identical",
        }
    if (
        DEFINITION.exists()
        or DEFINITION.is_symlink()
        or RELEASE.exists()
        or RELEASE.is_symlink()
    ):
        raise OpenSeedV95Error("partial v95 final-path collision")

    guard = _guard_state()
    _validate_guard(guard)
    target = (
        v70.parse_utc(recorded_at, label="v95 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=90)
    )
    if datetime.now(UTC) >= target:
        raise OpenSeedV95Error("v95 recorded_at must be future before staging")
    recorded_at = target.isoformat(timespec="seconds").replace("+00:00", "Z")

    with _publication_lock():
        _require_absent("initial")
        release_stage = Path(
            tempfile.mkdtemp(prefix=f".{RELEASE.name}.", dir=RELEASE.parent)
        )
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{DEFINITION.name}.", suffix=".stage", dir=DEFINITION.parent
        )
        definition_stage = Path(temporary)
        definition_identity = _path_identity(definition_stage, directory=False)
        release_root_identity = _path_identity(release_stage, directory=True)
        release_identities: dict[str, tuple[str, int, int]] = {
            ".": ("directory", *release_root_identity)
        }
        published_release = False
        published_definition = False
        try:
            os.close(descriptor)
            base = json.loads(BASE_DEFINITION.read_text())
            selected, paths = selected_inputs(
                base, recorded_at=recorded_at, validation_wall_clock=target
            )
            with tempfile.TemporaryDirectory(
                prefix="open-seed-v95-db-", dir="/private/tmp"
            ) as database_root:
                connection = _build_database(
                    base,
                    paths,
                    Path(database_root) / "atlas.sqlite",
                    recorded_at=recorded_at,
                )
                try:
                    _write_release(
                        connection,
                        release_stage,
                        recorded_at=recorded_at,
                        precreated=True,
                    )
                finally:
                    connection.close()
            _validate_release_facts(release_stage, recorded_at=recorded_at)
            definition = _definition_document(
                base, selected, release_stage, recorded_at=recorded_at
            )
            with definition_stage.open("r+b") as stream:
                stream.write(_canonical(definition, sort_keys=True))
                stream.truncate()
                stream.flush()
                os.fsync(stream.fileno())
            _freeze(definition_stage, release_stage)
            release_identities = _release_identities(release_stage)
            _validate_publication_times(
                definition_stage,
                release_stage,
                recorded_at=recorded_at,
                require_live=False,
            )
            _require_absent("pre-wait")
            frozen_definition = definition_stage.read_bytes()
            frozen_tree = v69.tree_digest(release_stage)
            _wait_until(target)
            _require_absent("late")
            if _path_identity(definition_stage, directory=False) != definition_identity:
                raise OpenSeedV95Error("v95 definition stage identity changed")
            _assert_release_identities(release_stage, release_identities)
            if (
                definition_stage.read_bytes() != frozen_definition
                or v69.tree_digest(release_stage) != frozen_tree
            ):
                raise OpenSeedV95Error("v95 private stage changed while waiting")
            _refresh_publication_ctimes(definition_stage, release_stage)
            _assert_release_identities(release_stage, release_identities)
            if (
                definition_stage.read_bytes() != frozen_definition
                or v69.tree_digest(release_stage) != frozen_tree
            ):
                raise OpenSeedV95Error("v95 private bytes changed at publication")
            _validate_publication_times(
                definition_stage,
                release_stage,
                recorded_at=recorded_at,
                require_live=True,
            )
            v69.promote_noreplace(release_stage, RELEASE)
            published_release = True
            try:
                v69.promote_noreplace(definition_stage, DEFINITION)
                published_definition = True
            except BaseException as error:
                try:
                    _rollback_release(release_root_identity, release_stage)
                    published_release = False
                except Exception as rollback_error:
                    error.add_note(f"v95 release rollback failed: {rollback_error}")
                raise
            try:
                manifest = validate_open_seed_v95(DEFINITION, RELEASE)
            except BaseException as error:
                rollback_errors = []
                try:
                    _rollback_definition(definition_identity, definition_stage)
                    published_definition = False
                except Exception as rollback_error:
                    rollback_errors.append(
                        f"v95 definition rollback failed: {rollback_error}"
                    )
                try:
                    _rollback_release(release_root_identity, release_stage)
                    published_release = False
                except Exception as rollback_error:
                    rollback_errors.append(
                        f"v95 release rollback failed: {rollback_error}"
                    )
                for note in rollback_errors:
                    error.add_note(note)
                raise
        finally:
            if not published_release and (
                release_stage.exists() or release_stage.is_symlink()
            ):
                _discard_release_stage(release_stage, release_identities)
            if not published_definition and (
                definition_stage.exists() or definition_stage.is_symlink()
            ):
                _discard_file_stage(definition_stage, definition_identity)
    if _guard_state() != guard:
        raise OpenSeedV95Error("v95 build mutated accepted inputs")
    return {
        "definition": str(DEFINITION),
        "definition_sha256": v69.sha256(DEFINITION),
        "manifest_sha256": v69.sha256(RELEASE / "manifest.json"),
        "recorded_at": manifest["recorded_at"],
        "release": str(RELEASE),
        "release_tree_sha256": v69.tree_digest(RELEASE),
        "status": "published",
    }


def main(*, publication_authorized: bool = False) -> int:
    print(
        json.dumps(
            build_open_seed_v95(publication_authorized=publication_authorized),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
