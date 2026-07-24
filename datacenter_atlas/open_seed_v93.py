"""Build open seed v93 as the strict three-source append successor to v92."""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import csv
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
from typing import Any, Iterator, Mapping

from . import (
    google_official_haskell_maize_pyramid_current_build_gap_v2_20260722 as google_v2,
)
from . import open_seed_v69 as v69
from . import open_seed_v70 as v70
from . import open_seed_v85 as v85
from . import open_seed_v92 as v92
from .publication_release import build_release_documents
from .service import _current_rows


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v92.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v92"
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v93.json"
RELEASE_ID = "2026-07-21-open-seed-v93"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v93.lock"
AS_OF = "2026-07-22"

BASE_RECORDED_AT = "2026-07-22T02:00:23Z"
BASE_DEFINITION_PIN = (
    109_851,
    "2dab6d4a4bdac34f248268f9f2973ccac88b7fe25deb78b10cf5e44c11990516",
)
BASE_MANIFEST_PIN = (
    16_558,
    "3ac9a48eeb121e6ac8a462fb2d99de1a7f2267c6cf9f6b7bd4b74d2b74a25fd7",
)
BASE_TREE_SHA256 = "52bdbd5ea299dbd845adfe8e05f739894bff914107ae8fec341551bdb800034b"
BASE_ENTITIES_PIN = (
    1_025_359,
    "3e1bf82358ee1e037a7e8ce1a175eee3958dfb4f4d3f5dc6fbd7b92704fd7290",
)

V2_MEMBER_PINS: Mapping[str, tuple[int, str, int]] = {
    "README.md": (
        2_313,
        "03f52419aa228b04758dd1f252f0dcb52dcdc2f4f74109757171cae18366f250",
        1_784_687_700_007_570_166,
    ),
    "candidate-assessment.json": (
        9_216,
        "734dc0010c35a3f4a7e2b53254f5597afa80dbebc31f02c8005c3c64bedcb40c",
        1_784_687_700_007_641_667,
    ),
    "manifest.json": (
        7_745,
        "75b0abee276eecb7bfa0d32caf5341db6769d34ea71d6497ffd45225d5740f47",
        1_784_687_700_007_699_751,
    ),
    "manifest.sha256": (
        80,
        "51affc739f25e23250498a7afddbe7a979a1b197a6e7bd4e9469b526894ca7e9",
        1_784_687_700_007_755_334,
    ),
    "retrieval-inventory.json": (
        20_603,
        "c869758d04c7167276cd4dcdb2a0fc4d09f98b42b4f1742da32cf686b87861a7",
        1_784_687_700_007_812_668,
    ),
    "rights-and-disposition.json": (
        4_108,
        "59862d649e17a5d0eff064fb9e942616293791897ca8ed1d54bf0d69f108d6f3",
        1_784_687_700_007_872_752,
    ),
    "source-snapshot.json": (
        8_980,
        "b548f14ab3c72e7aebeded5deb032fcc52b4f52faf0e2e3a1532e42c9ae7d72a",
        1_784_687_700_007_943_253,
    ),
}
V2_ROOT_CTIME_NS = 1_784_687_700_061_638_494

REJECTED_V1_MEMBER_PINS: Mapping[str, tuple[int, str, int]] = {
    "README.md": (
        1_931,
        "9d1ecbbd0c9303a9fb3089c1d17c9a6e46a8bd6c4fec87f29dafb9f94fe91258",
        1_784_685_647_966_924_238,
    ),
    "candidate-assessment.json": (
        6_264,
        "beace8901d54f7d0fa5710874bb35a3f1f35875369fdd27b4a5f5837025314d3",
        1_784_685_647_967_037_864,
    ),
    "manifest.json": (
        1_837,
        "b05989194bc280d050eb5011ae9951b4dfad94427fd5771924db7b118c554820",
        1_784_685_647_967_591_662,
    ),
    "manifest.sha256": (
        80,
        "744d85b5aa526428d78907717db230989fecb15457e7b41ca2c29dec16157aca",
        1_784_685_647_967_709_497,
    ),
    "retrieval-inventory.json": (
        17_651,
        "aa8d23101829feb666587f9707a99b5d53099e969ca68cbd0a4b7fd8e171f54e",
        1_784_685_647_967_137_574,
    ),
    "rights-and-disposition.json": (
        1_156,
        "94cf2c9345d51edbee2a0719b446ffaf1cf73f7036778f2c9924d92179a89994",
        1_784_685_647_967_232_825,
    ),
    "source-snapshot.json": (
        6_028,
        "c39e37c396303474f41debe4141322a0fbf1201b597548cd148d9005ed049a44",
        1_784_685_647_967_333_034,
    ),
}
REJECTED_V1_ID = "google-official-haskell-maize-pyramid-current-build-gap-2026-07-22-v1"
REJECTED_V1_RECORDED_AT = "2026-07-22T02:01:32Z"
REJECTED_V1_LOGICAL_TREE_SHA256 = (
    "db1e1411deb788191fb658f9fa135ef79aaf8c6d6798db517689838f60180588"
)
REJECTED_V1_PHYSICAL_TREE_SHA256 = (
    "3613881b11187faae76682dc09e1fc2d1185c0c60a2d053ff9328fc4d0220d87"
)
REJECTED_V1_ROOT_CTIME_NS = 1_784_685_692_010_618_369
REJECTED_V1_INCIDENT = {
    "accepted_as_base": False,
    "artifact_id": REJECTED_V1_ID,
    "artifact_path": f"source_artifacts/{REJECTED_V1_ID}",
    "declared_recorded_at": REJECTED_V1_RECORDED_AT,
    "failed_members": {
        name: {
            "bytes": size,
            "ctime_ns": ctime_ns,
            "path": f"source_artifacts/{REJECTED_V1_ID}/{name}",
            "sha256": digest,
        }
        for name, (size, digest, ctime_ns) in sorted(REJECTED_V1_MEMBER_PINS.items())
    },
    "logical_tree_sha256": REJECTED_V1_LOGICAL_TREE_SHA256,
    "physical_tree_sha256": REJECTED_V1_PHYSICAL_TREE_SHA256,
    "reason": (
        "All seven final artifact child files retained private-stage ctimes "
        "that predated the declared recorded_at."
    ),
    "root_ctime_ns": REJECTED_V1_ROOT_CTIME_NS,
    "status": "rejected_publication_incident",
}

OFFICIAL_SPECS = {
    "google_haskell_maize_pyramid_v2": {
        "module": google_v2,
        "recorded_at": "2026-07-22T02:35:00Z",
        "manifest_pin": (
            7_745,
            "75b0abee276eecb7bfa0d32caf5341db6769d34ea71d6497ffd45225d5740f47",
        ),
        "logical_tree": "79b9ce0ca96969a597eaf9507b11a20a8918e73eecf36f476cae1657bd07e690",
        "physical_tree": "59308cdc266dc6da1a0b6919b07c09e7568e0cb4b8a56210be4b24ec1ad1b885",
        "source_count": 3,
        "member_pins": V2_MEMBER_PINS,
        "root_ctime_ns": V2_ROOT_CTIME_NS,
    },
}

ADDITION_ORDER = (
    "sources/curated-official-2026-07-22-google-haskell-quantum-linked-current-build.json",
    "sources/curated-official-2026-07-22-google-michigan-city-project-maize-site-works.json",
    "sources/curated-official-2026-07-22-google-west-memphis-project-pyramid-current-build.json",
)
ADDITION_PINS = {
    ADDITION_ORDER[0]: (
        8_973,
        "72fe2080d815d6c42f518804119d622b6673aabdd874cbb077978bc5f1fa3a22",
    ),
    ADDITION_ORDER[1]: (
        8_734,
        "8a4badebd8271e0360e5e1977f4abd88e1cc4c4bda4ebe9497b5944cad80c24f",
    ),
    ADDITION_ORDER[2]: (
        6_985,
        "55db0349fd90cc348f512f1409e92671892f06e288cd82a8dce2e4cf5530f692",
    ),
}
SOURCE_CTIME_NS = {
    ADDITION_ORDER[0]: 1_784_685_692_010_133_613,
    ADDITION_ORDER[1]: 1_784_685_692_010_325_282,
    ADDITION_ORDER[2]: 1_784_685_692_010_455_283,
}

SOURCE_MODULES = dict.fromkeys(ADDITION_ORDER, google_v2.v1)

ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:google-haskell-county-quantum-linked-data-center-campus",
        "curated:google-haskell-county-quantum-linked-data-center-campus:current-development",
        "curated:google-michigan-city-project-maize-data-center",
        "curated:google-michigan-city-project-maize-data-center:2025-site-works",
        "curated:google-west-memphis-project-pyramid-data-center-campus",
        "curated:google-west-memphis-project-pyramid-data-center-campus:current-development",
    }
)
ADDED_PROJECT_KEYS = frozenset(
    key for key in ADDED_ENTITY_KEYS if ":" in key.removeprefix("curated:")
)
ADDED_EVIDENCE_KEYS = frozenset(
    {
        "google-haskell-county-construction-start-2025-11",
        "google-texas-one-haskell-energy-colocation-2025-11-14",
        "intersect-quantum-google-colocation-observed-2026-07-22",
        "google-michigan-city-project-maize-identity-observed-2026-07-22",
        "edcmc-google-project-maize-acquisition-2026-04-16",
        "idem-project-maize-site-works-inspection-2025-09-24",
        "arkansas-google-west-memphis-construction-2025-10-02",
        "serc-project-pyramid-google-west-memphis-identity-2026-06-24",
    }
)
ADDED_EXPORTED_EVIDENCE_KEYS = frozenset(
    {
        "google-haskell-county-construction-start-2025-11",
        "intersect-quantum-google-colocation-observed-2026-07-22",
        "edcmc-google-project-maize-acquisition-2026-04-16",
        "idem-project-maize-site-works-inspection-2025-09-24",
        "arkansas-google-west-memphis-construction-2025-10-02",
        "serc-project-pyramid-google-west-memphis-identity-2026-06-24",
    }
)
ADDED_SIGNAL_EVIDENCE_KEYS = frozenset(
    {
        "google-haskell-county-construction-start-2025-11",
        "idem-project-maize-site-works-inspection-2025-09-24",
        "arkansas-google-west-memphis-construction-2025-10-02",
    }
)
LIFECYCLE_CONTRACT = frozenset(
    {
        (
            "curated:google-haskell-county-quantum-linked-data-center-campus:current-development",
            "under_construction",
            "2025-11-30",
            "authoritative_physical_status_update",
        ),
        (
            "curated:google-michigan-city-project-maize-data-center:2025-site-works",
            "site_preparation",
            "2025-09-24",
            "authoritative_physical_status_update",
        ),
        (
            "curated:google-west-memphis-project-pyramid-data-center-campus:current-development",
            "under_construction",
            "2025-10-02",
            "authoritative_physical_status_update",
        ),
    }
)
CAPACITY_CONTRACT: frozenset[tuple[Any, ...]] = frozenset()

FRESHNESS_README = """
Open seed v93 is the exact append-only accepted-v92 successor with only three
unchanged curated records appended at input indices 485 through 487: Google's
Haskell County, Michigan City Project Maize, and West Memphis Project Pyramid
current-build records. The accepted v2 source artifact, its logical and
physical trees, all seven frozen members and chronology, and the immutable
rejected-v1 incident lineage are pinned by the v93 builder. Rejected v1 is
incident evidence only and is never an accepted integration input.

The append creates six v92-new entities: three campuses and three projects.
Public contract-v4 rows preserve the accepted v92 projection byte-for-byte
where their stable IDs or keys are unchanged; the six new rows carry no
coordinate or geometry. Derived v92 freshness rows likewise remain frozen,
while three new project freshness rows are computed at the v93 as-of date.

The curated database delta is eight evidence records and three lifecycle
observations. Public projection is intentionally smaller: `evidence.csv`
adds the six evidence records referenced by exported current fields;
`lifecycle_freshness.csv`, `construction_pipeline.csv`, and
`construction_source_signals.csv` each add exactly three records. This
projection is not evidence loss.

No capacity, energy, voltage, PUE, WUE, operating model, workload, facility
type, standardized role, coordinate, geometry, permit, forecast, persistence,
satellite, aerial, map-click, or computer-vision assertion is added. There is
no cross-source identity resolution or unique-site claim. Every appended
status is a dated last-observed fact; `current_status_classification` is
`unknown` and `current_construction_claim` is `false`.
""".strip()


class OpenSeedV93Error(RuntimeError):
    """Raised when a v93 lineage, claim, or publication guard fails closed."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any, *, sort_keys: bool = False) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=sort_keys, ensure_ascii=False) + "\n"
    ).encode()


def _read_json(
    path: Path, *, mode: int | None = None, sort_keys: bool = False
) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise OpenSeedV93Error(f"expected ordinary JSON file: {path}")
    if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
        raise OpenSeedV93Error(f"file mode differs: {path}")
    raw = path.read_bytes()
    document = json.loads(raw)
    if raw != _canonical(document, sort_keys=sort_keys):
        raise OpenSeedV93Error(f"JSON is not canonical: {path}")
    return raw, document


def _validate_pinned_tree(
    root: Path,
    *,
    member_pins: Mapping[str, tuple[int, str, int]],
    root_ctime_ns: int,
    recorded_at: str,
    label: str,
    accepted_chronology: bool = True,
) -> None:
    if (
        root.is_symlink()
        or not root.is_dir()
        or stat.S_IMODE(root.stat().st_mode) != 0o555
        or root.stat().st_ctime_ns != root_ctime_ns
    ):
        raise OpenSeedV93Error(f"{label} root chronology or mode differs")
    members = {path.name: path for path in root.iterdir()}
    if set(members) != set(member_pins):
        raise OpenSeedV93Error(f"{label} closed member inventory differs")
    target = v70.parse_utc(recorded_at, label=f"{label} recorded_at").timestamp()
    for name, (size, digest, ctime_ns) in member_pins.items():
        path = members[name]
        metadata = path.stat(follow_symlinks=False)
        if (
            path.is_symlink()
            or not path.is_file()
            or stat.S_IMODE(metadata.st_mode) != 0o444
            or (metadata.st_size, _sha256(path.read_bytes()), metadata.st_ctime_ns)
            != (size, digest, ctime_ns)
            or max(metadata.st_birthtime, metadata.st_mtime) > target + 1e-6
            or (accepted_chronology and metadata.st_ctime + 1e-6 < target)
            or (not accepted_chronology and metadata.st_ctime >= target)
        ):
            raise OpenSeedV93Error(f"{label} member pin or chronology differs: {name}")


def _validate_rejected_v1_incident() -> None:
    root = ROOT / "source_artifacts" / REJECTED_V1_ID
    _validate_pinned_tree(
        root,
        member_pins=REJECTED_V1_MEMBER_PINS,
        root_ctime_ns=REJECTED_V1_ROOT_CTIME_NS,
        recorded_at=REJECTED_V1_RECORDED_AT,
        label="rejected Google v1 incident",
        accepted_chronology=False,
    )
    if (
        v69.tree_digest(root) != REJECTED_V1_PHYSICAL_TREE_SHA256
        or google_v2.REJECTED_V1_ID != REJECTED_V1_ID
        or google_v2.REJECTED_V1_RECORDED_AT != REJECTED_V1_RECORDED_AT
        or google_v2.REJECTED_V1_LOGICAL_TREE_SHA256 != REJECTED_V1_LOGICAL_TREE_SHA256
        or google_v2.REJECTED_V1_PHYSICAL_TREE_SHA256
        != REJECTED_V1_PHYSICAL_TREE_SHA256
        or google_v2.REJECTED_V1_ROOT_CTIME_NS != REJECTED_V1_ROOT_CTIME_NS
        or dict(google_v2.REJECTED_V1_MEMBER_PINS) != REJECTED_V1_MEMBER_PINS
        or google_v2.INCIDENT_LINEAGE != REJECTED_V1_INCIDENT
    ):
        raise OpenSeedV93Error("rejected Google v1 incident lineage differs")


def _validate_official_artifact() -> dict[str, dict[str, Any]]:
    records_by_path: dict[str, dict[str, Any]] = {}
    _validate_rejected_v1_incident()
    if {
        f"sources/{name}": pin for name, pin in google_v2.SOURCE_PINS.items()
    } != ADDITION_PINS or {
        f"sources/{name}": ctime_ns
        for name, ctime_ns in google_v2.SOURCE_CTIME_NS.items()
    } != SOURCE_CTIME_NS:
        raise OpenSeedV93Error("Google v2 source pin constants differ")
    for label, spec in OFFICIAL_SPECS.items():
        module = spec["module"]
        artifact = ROOT / "source_artifacts" / module.ARTIFACT_ID
        try:
            manifest = module.validate_artifact(artifact)
        except RuntimeError as error:
            raise OpenSeedV93Error(
                f"{label} official artifact invalid: {error}"
            ) from error
        _validate_pinned_tree(
            artifact,
            member_pins=spec["member_pins"],
            root_ctime_ns=spec["root_ctime_ns"],
            recorded_at=spec["recorded_at"],
            label=label,
        )
        manifest_raw = (artifact / "manifest.json").read_bytes()
        if (
            (len(manifest_raw), _sha256(manifest_raw)) != spec["manifest_pin"]
            or manifest.get("recorded_at") != spec["recorded_at"]
            or manifest.get("tree_sha256") != spec["logical_tree"]
            or v69.tree_digest(artifact) != spec["physical_tree"]
            or manifest.get("curated_source_records") != spec["source_count"]
            or manifest.get("seed_eligible_source_records") != spec["source_count"]
            or manifest.get("open_seed_successor_created") is not False
            or manifest.get("release_integration") != "none"
            or manifest.get("incident_lineage") != REJECTED_V1_INCIDENT
        ):
            raise OpenSeedV93Error(f"{label} official artifact pin differs")
        snapshot = json.loads(
            (artifact / "source-snapshot.json").read_text(encoding="utf-8")
        )
        for record in snapshot.get("source_records", []):
            path = record.get("path")
            if not isinstance(path, str) or path in records_by_path:
                raise OpenSeedV93Error("official artifact source inventory overlaps")
            records_by_path[path] = record

    if tuple(records_by_path) != ADDITION_ORDER:
        raise OpenSeedV93Error("official artifact source order differs")
    documents: dict[str, dict[str, Any]] = {}
    for relative in ADDITION_ORDER:
        path = ROOT / relative
        raw, document = _read_json(path, mode=0o444)
        record = records_by_path[relative]
        pin = ADDITION_PINS[relative]
        module = SOURCE_MODULES[relative]
        expected = module.expected_source_documents()[path.name]
        metadata = path.stat(follow_symlinks=False)
        expected_ctime_ns = SOURCE_CTIME_NS[relative]
        if (
            (len(raw), _sha256(raw)) != pin
            or (record.get("bytes"), record.get("sha256")) != pin
            or raw != module._canonical(expected)
            or metadata.st_ctime_ns != expected_ctime_ns
            or max(metadata.st_birthtime, metadata.st_mtime)
            > v70.parse_utc(
                OFFICIAL_SPECS["google_haskell_maize_pyramid_v2"]["recorded_at"],
                label="Google v2 recorded_at",
            ).timestamp()
            + 1e-6
        ):
            raise OpenSeedV93Error(f"v93 source pin differs: {relative}")
        documents[relative] = document

    stable_keys = {
        document[entity]["stable_key"]
        for document in documents.values()
        for entity in ("campus", "project")
    }
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
    evidence_keys = {
        row["key"] for document in documents.values() for row in document["evidence"]
    }
    if (
        stable_keys != ADDED_ENTITY_KEYS
        or lifecycle != LIFECYCLE_CONTRACT
        or capacities != CAPACITY_CONTRACT
        or evidence_keys != ADDED_EVIDENCE_KEYS
        or any(document["operating_models"] for document in documents.values())
        or any(document["workloads"] for document in documents.values())
        or any(
            document[entity]["roles"]
            for document in documents.values()
            for entity in ("campus", "project")
        )
        or any(
            document[entity][field] is not None
            for document in documents.values()
            for entity in ("campus", "project")
            for field in ("coordinates", "geometry")
        )
    ):
        raise OpenSeedV93Error(
            "official current-build normalized claim contract differs"
        )
    if any(
        row["metric"] in {"annual_energy_mwh", "pue", "wue"}
        for document in documents.values()
        for row in document["capacities"]
    ):
        raise OpenSeedV93Error("v93 source adds energy or efficiency capacity")
    return documents


def _base_paths(base: Mapping[str, Any]) -> list[Path]:
    paths = []
    for row in base["curated_inputs"]:
        path = ROOT / row["path"]
        if path.is_symlink() or not path.is_file() or v69.sha256(path) != row["sha256"]:
            raise OpenSeedV93Error(f"accepted v92 input pin differs: {row['path']}")
        paths.append(path)
    return paths


def selected_inputs(
    base: Mapping[str, Any],
    *,
    recorded_at: str,
    validation_wall_clock: datetime | None = None,
) -> tuple[list[dict[str, str]], list[Path]]:
    if base.get("release_id") != v92.RELEASE_ID:
        raise OpenSeedV93Error("v93 base must be exactly accepted v92")
    rows = base.get("curated_inputs")
    if (
        not isinstance(rows, list)
        or len(rows) != 485
        or any(
            not isinstance(row, dict) or set(row) != {"path", "sha256"} for row in rows
        )
    ):
        raise OpenSeedV93Error("accepted v92 curated inventory differs")
    documents = _validate_official_artifact()
    target = v70.parse_utc(recorded_at, label="v93 recorded_at")
    wall = validation_wall_clock or datetime.now(UTC)
    if (
        wall.tzinfo is None
        or target > wall.astimezone(UTC)
        or any(
            v70.parse_utc(spec["recorded_at"], label=f"{label} recorded_at") > target
            for label, spec in OFFICIAL_SPECS.items()
        )
    ):
        raise OpenSeedV93Error("v93 publication time precedes an input")

    paths = _base_paths(base)
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
    if base_evidence & ADDED_EVIDENCE_KEYS:
        raise OpenSeedV93Error("v93 evidence append collides with accepted v92")
    base_stable = {
        row["stable_key"] for row in _csv_rows(BASE_RELEASE / "entities.csv")
    }
    if base_stable & ADDED_ENTITY_KEYS:
        raise OpenSeedV93Error("v93 stable-key append collides with accepted v92")

    selected = [dict(row) for row in rows]
    for relative in ADDITION_ORDER:
        selected.append({"path": relative, "sha256": ADDITION_PINS[relative][1]})
        paths.append(ROOT / relative)
    if (
        selected[:485] != rows
        or [row["path"] for row in selected[485:]] != list(ADDITION_ORDER)
        or tuple(documents) != ADDITION_ORDER
        or len(selected) != 488
        or len({row["path"] for row in selected}) != 488
    ):
        raise OpenSeedV93Error("v93 did not append exactly three ordered inputs")
    for relative, document in documents.items():
        for index, evidence in enumerate(document["evidence"]):
            retrieved = v70.parse_utc(
                evidence["retrieved_at"],
                label=f"{relative} evidence[{index}].retrieved_at",
            )
            if retrieved > target or retrieved > wall.astimezone(UTC):
                raise OpenSeedV93Error("v93 selected evidence is future-dated")
    return selected, paths


def _guard_state() -> dict[str, Any]:
    _validate_official_artifact()
    return {
        "base_definition": (
            BASE_DEFINITION.stat().st_size,
            v69.sha256(BASE_DEFINITION),
        ),
        "base_manifest": (
            (BASE_RELEASE / "manifest.json").stat().st_size,
            v69.sha256(BASE_RELEASE / "manifest.json"),
        ),
        "base_tree": v69.tree_digest(BASE_RELEASE),
        "base_entities": (
            (BASE_RELEASE / "entities.csv").stat().st_size,
            v69.sha256(BASE_RELEASE / "entities.csv"),
        ),
        "official_manifests": {
            label: (
                (
                    ROOT
                    / "source_artifacts"
                    / spec["module"].ARTIFACT_ID
                    / "manifest.json"
                )
                .stat()
                .st_size,
                v69.sha256(
                    ROOT
                    / "source_artifacts"
                    / spec["module"].ARTIFACT_ID
                    / "manifest.json"
                ),
            )
            for label, spec in OFFICIAL_SPECS.items()
        },
        "official_trees": {
            label: v69.tree_digest(
                ROOT / "source_artifacts" / spec["module"].ARTIFACT_ID
            )
            for label, spec in OFFICIAL_SPECS.items()
        },
        "additions": {
            relative: ((ROOT / relative).stat().st_size, v69.sha256(ROOT / relative))
            for relative in ADDITION_ORDER
        },
    }


def _table_state(connection: sqlite3.Connection, table: str) -> set[tuple[Any, ...]]:
    return {tuple(row) for row in connection.execute(f"SELECT * FROM {table}")}


def _validate_database_contract(
    connection: sqlite3.Connection,
    base: Mapping[str, Any],
    *,
    recorded_at: str,
) -> None:
    expected_counts = {
        "entities": 994,
        "entity_snapshots": 1_017,
        "evidence": 825,
        "lifecycle_observations": 574,
        "capacity_estimates": 559,
        "operating_model_observations": 73,
        "workload_observations": 135,
    }
    actual_counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in expected_counts
    }
    if actual_counts != expected_counts:
        raise OpenSeedV93Error(f"v93 database counts differ: {actual_counts}")
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v93-base-", dir="/private/tmp"
    ) as temporary:
        prior = v69._populate_database(
            base,
            _base_paths(base),
            Path(temporary) / "v92.sqlite",
            recorded_at=recorded_at,
        )
        try:
            for table in (
                "entities",
                "evidence",
                "campuses",
                "facilities",
                "buildings",
                "projects",
                "administrative_assignments",
                "entity_snapshots",
                "lifecycle_observations",
                "operating_model_observations",
                "workload_observations",
                "capacity_estimates",
            ):
                if not _table_state(prior, table) <= _table_state(connection, table):
                    raise OpenSeedV93Error(f"v93 changed a v92 database row: {table}")
            before_entities = {
                row[0] for row in prior.execute("SELECT stable_key FROM entities")
            }
            after_entities = {
                row[0] for row in connection.execute("SELECT stable_key FROM entities")
            }
            if (
                after_entities - before_entities != ADDED_ENTITY_KEYS
                or before_entities - after_entities
            ):
                raise OpenSeedV93Error("v93 database identity delta differs")
            before_evidence = set(v70._evidence_by_key(prior))
            after_evidence = set(v70._evidence_by_key(connection))
            if (
                after_evidence - before_evidence != ADDED_EVIDENCE_KEYS
                or before_evidence - after_evidence
            ):
                raise OpenSeedV93Error("v93 database evidence delta differs")
        finally:
            prior.close()

    project_targets = {
        row["project_key"]: row["campus_key"]
        for row in connection.execute(
            """
            SELECT project.stable_key AS project_key,
                   target.stable_key AS campus_key
            FROM projects
            JOIN entities project ON project.id=projects.entity_id
            JOIN entities target ON target.id=projects.target_entity_id
            """
        )
        if row["project_key"] in ADDED_PROJECT_KEYS
    }
    expected_targets = {
        document["project"]["stable_key"]: document["campus"]["stable_key"]
        for document in _validate_official_artifact().values()
    }
    if project_targets != expected_targets:
        raise OpenSeedV93Error("v93 project/campus boundaries differ")

    project_keys = tuple(sorted(ADDED_PROJECT_KEYS))
    project_placeholders = ",".join("?" for _ in project_keys)
    lifecycle = {
        tuple(row)
        for row in connection.execute(
            f"""
            SELECT entities.stable_key, status, as_of_date,
                   lifecycle_observations.method
            FROM lifecycle_observations
            JOIN entities ON entities.id=entity_id
            WHERE entities.stable_key IN ({project_placeholders})
            """,
            project_keys,
        )
    }
    capacity_keys = tuple(sorted(ADDED_ENTITY_KEYS))
    capacity_placeholders = ",".join("?" for _ in capacity_keys)
    evidence_keys = tuple(sorted(ADDED_EVIDENCE_KEYS))
    evidence_placeholders = ",".join("?" for _ in evidence_keys)
    capacities = {
        tuple(row)
        for row in connection.execute(
            f"""
            SELECT entities.stable_key, metric, stage, unit, base, as_of_date,
                   capacity_estimates.method
            FROM capacity_estimates
            JOIN entities ON entities.id=entity_id
            JOIN evidence ON evidence.id=capacity_estimates.evidence_id
            WHERE entities.stable_key IN ({capacity_placeholders})
              AND json_extract(evidence.metadata_json,
                  '$.curated_record_key') IN ({evidence_placeholders})
            """,
            (*capacity_keys, *evidence_keys),
        )
    }
    models = connection.execute(
        f"""
        SELECT COUNT(*) FROM operating_model_observations
        JOIN entities ON entities.id=entity_id
        WHERE entities.stable_key IN ({project_placeholders})
        """,
        project_keys,
    ).fetchone()[0]
    workloads = connection.execute(
        f"""
        SELECT COUNT(*) FROM workload_observations
        JOIN entities ON entities.id=entity_id
        WHERE entities.stable_key IN ({project_placeholders})
        """,
        project_keys,
    ).fetchone()[0]
    snapshots = list(
        connection.execute(
            f"""
            SELECT entities.stable_key, latitude, longitude, geometry_json
            FROM entity_snapshots
            JOIN entities ON entities.id=entity_id
            WHERE entities.stable_key IN ({",".join("?" for _ in ADDED_ENTITY_KEYS)})
            """,
            tuple(sorted(ADDED_ENTITY_KEYS)),
        )
    )
    if (
        lifecycle != LIFECYCLE_CONTRACT
        or capacities != CAPACITY_CONTRACT
        or models
        or workloads
        or len(snapshots) != 6
        or any(
            row[1] is not None or row[2] is not None or row[3] not in {None, "null"}
            for row in snapshots
        )
    ):
        raise OpenSeedV93Error("v93 imported claim contract differs")

    evidence_rows = {
        json.loads(row["metadata_json"] or "{}").get("curated_record_key"): row
        for row in connection.execute(
            "SELECT kind, source_family, metadata_json FROM evidence"
        )
        if json.loads(row["metadata_json"] or "{}").get("curated_record_key")
        in ADDED_EVIDENCE_KEYS
    }
    if set(evidence_rows) != ADDED_EVIDENCE_KEYS or not {
        row["kind"] for row in evidence_rows.values()
    } <= {"company_disclosure", "government_record", "utility_record"}:
        raise OpenSeedV93Error("v93 imported evidence classification differs")

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
        len(located) != 213
        or sum(kinds[row["entity_id"]] == "campus" for row in located) != 141
    ):
        raise OpenSeedV93Error("v93 internal as-of coordinate coverage differs")


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


def _csv_text(template: str, rows: list[dict[str, str]]) -> str:
    reader = csv.DictReader(io.StringIO(template))
    fields = reader.fieldnames
    if fields is None:
        raise OpenSeedV93Error("CSV template lacks a header")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _append_only_csv(
    output: dict[str, str],
    filename: str,
    *,
    key: str,
    expected_base: int,
    expected_added: int,
) -> None:
    base_rows = _csv_rows(BASE_RELEASE / filename)
    current_rows = list(csv.DictReader(io.StringIO(output[filename])))
    if len(base_rows) != expected_base:
        raise OpenSeedV93Error(f"v92 {filename} baseline count differs")
    base_keys = {row[key] for row in base_rows}
    if len(base_keys) != len(base_rows) or not base_keys <= {
        row[key] for row in current_rows
    }:
        raise OpenSeedV93Error(f"v93 {filename} baseline identity differs")
    added = [row for row in current_rows if row[key] not in base_keys]
    if len(added) != expected_added or len({row[key] for row in added}) != len(added):
        raise OpenSeedV93Error(f"v93 {filename} append count differs")
    output[filename] = _csv_text(output[filename], [*base_rows, *added])


def _append_only_projection(output: dict[str, str]) -> None:
    _append_only_csv(
        output,
        "entities.csv",
        key="stable_key",
        expected_base=988,
        expected_added=6,
    )
    _append_only_csv(
        output,
        "evidence.csv",
        key="evidence_id",
        expected_base=645,
        expected_added=6,
    )
    _append_only_csv(
        output,
        "construction_pipeline.csv",
        key="stable_key",
        expected_base=501,
        expected_added=3,
    )
    _append_only_csv(
        output,
        "construction_source_signals.csv",
        key="source_observation_evidence_id",
        expected_base=400,
        expected_added=3,
    )
    _append_only_csv(
        output,
        "lifecycle_freshness.csv",
        key="stable_key",
        expected_base=550,
        expected_added=3,
    )

    entity_rows = list(csv.DictReader(io.StringIO(output["entities.csv"])))
    new_entity_ids = {
        row["entity_id"]
        for row in entity_rows
        if row["stable_key"] in ADDED_ENTITY_KEYS
    }
    base_capacity = _csv_rows(BASE_RELEASE / "capacity_estimates.csv")
    raw_capacity = list(csv.DictReader(io.StringIO(output["capacity_estimates.csv"])))
    added_capacity = [row for row in raw_capacity if row["entity_id"] in new_entity_ids]
    if len(base_capacity) != 558 or added_capacity:
        raise OpenSeedV93Error("v93 capacity append count differs")
    output["capacity_estimates.csv"] = (
        BASE_RELEASE / "capacity_estimates.csv"
    ).read_text(encoding="utf-8")

    base_geojson = json.loads((BASE_RELEASE / "atlas.geojson").read_text())
    current_geojson = json.loads(output["atlas.geojson"])
    new_features = [
        feature
        for feature in current_geojson["features"]
        if feature["properties"]["stable_key"] in ADDED_ENTITY_KEYS
    ]
    if (
        len(base_geojson["features"]) != 988
        or len(new_features) != 6
        or any(
            feature.get("geometry") is not None
            or feature["properties"].get("latitude") is not None
            or feature["properties"].get("longitude") is not None
            for feature in new_features
        )
    ):
        raise OpenSeedV93Error("v93 GeoJSON append boundary differs")
    current_geojson["features"] = [*base_geojson["features"], *new_features]
    output["atlas.geojson"] = (
        json.dumps(current_geojson, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )

    base_sources = json.loads(
        (BASE_RELEASE / "source_inputs.json").read_text(encoding="utf-8")
    )["sources"]
    current_sources = json.loads(output["source_inputs.json"])["sources"]
    base_canonical = {
        json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        for row in base_sources
    }
    added_sources = [
        row
        for row in current_sources
        if json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        not in base_canonical
    ]
    if len(base_sources) != 572 or len(added_sources) != 6:
        raise OpenSeedV93Error("v93 source-input projection differs")
    output["source_inputs.json"] = (
        json.dumps(
            {"sources": [*base_sources, *added_sources]},
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )

    summary = json.loads(output["summary.json"])
    summary["entities_with_coordinates"] = 213
    summary["campuses_with_coordinates"] = 141
    summary["append_projection"] = {
        "base_release_id": v92.RELEASE_ID,
        "base_rows_frozen": True,
        "curated_source_input_delta": 3,
        "internal_database_delta": {
            "entities": 6,
            "evidence": 8,
            "lifecycle_observations": 3,
            "capacity_estimates": 0,
        },
        "public_release_delta": {
            "entities": 6,
            "evidence": 6,
            "lifecycle_freshness": 3,
            "capacity_estimates": 0,
            "construction_pipeline": 3,
            "construction_source_signals": 3,
        },
        "projection_explanation": "Public claim evidence includes only the six evidence records referenced by exported current identity and dated last-observed lifecycle fields; all eight evidence records remain in the internal database.",
        "public_source_input_rows_delta": 6,
        "unrelated_future_effective_base_coordinates_published": False,
    }
    output["summary.json"] = _canonical(summary, sort_keys=True).decode()


def _augment_release(documents: Mapping[str, str]) -> dict[str, str]:
    previous_as_of = v85.AS_OF
    try:
        v85.AS_OF = AS_OF
        output = v92.v91._augment_release(documents)
    finally:
        v85.AS_OF = previous_as_of
    _append_only_projection(output)
    output["README.md"] = (
        output["README.md"].rstrip() + "\n\n" + FRESHNESS_README + "\n"
    )
    manifest = json.loads(output["manifest.json"])
    manifest.update(
        {
            "as_of": AS_OF,
            "entities": 994,
            "entities_by_kind": {"campus": 516, "project": 478},
            "capacity_estimates": 558,
            "construction_pipeline_records": 504,
            "construction_source_signals": 403,
            "evidence_records": 651,
            "lifecycle_freshness_records": 553,
            "append_only_base_release": v92.RELEASE_ID,
            "base_rows_frozen": True,
            "curated_source_input_delta": 3,
            "internal_database_delta": {
                "entities": 6,
                "evidence": 8,
                "lifecycle_observations": 3,
                "capacity_estimates": 0,
            },
            "public_release_delta": {
                "entities": 6,
                "evidence": 6,
                "lifecycle_freshness": 3,
                "capacity_estimates": 0,
                "construction_pipeline": 3,
                "construction_source_signals": 3,
            },
            "public_source_input_rows_delta": 6,
        }
    )
    for filename, text in output.items():
        if filename == "manifest.json":
            continue
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
            raise OpenSeedV93Error("precreated v93 release stage must be empty")
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


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _entity_csv_record(path: Path, stable_key: str) -> bytes:
    marker = f",{stable_key},".encode()
    matches = [
        line for line in path.read_bytes().splitlines(keepends=True) if marker in line
    ]
    if len(matches) != 1:
        raise OpenSeedV93Error(f"entity CSV record lookup differs: {stable_key}")
    return matches[0]


PUBLIC_CSV_DELTA = {
    "entities.csv": (988, 6),
    "evidence.csv": (645, 6),
    "capacity_estimates.csv": (558, 0),
    "construction_pipeline.csv": (501, 3),
    "construction_source_signals.csv": (400, 3),
    "lifecycle_freshness.csv": (550, 3),
}


def _validate_public_delta(stage: Path) -> None:
    for filename, (base_count, added_count) in PUBLIC_CSV_DELTA.items():
        base_lines = Counter(
            (BASE_RELEASE / filename).read_bytes().splitlines(keepends=True)[1:]
        )
        stage_lines = Counter(
            (stage / filename).read_bytes().splitlines(keepends=True)[1:]
        )
        if (
            sum(base_lines.values()) != base_count
            or not base_lines <= stage_lines
            or sum((stage_lines - base_lines).values()) != added_count
            or sum((base_lines - stage_lines).values()) != 0
        ):
            raise OpenSeedV93Error(f"v93 append-only CSV delta differs: {filename}")

    for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
        if (stage / filename).read_bytes() != (BASE_RELEASE / filename).read_bytes():
            raise OpenSeedV93Error(
                f"v93 unrelated resolution output changed: {filename}"
            )

    base_features = json.loads((BASE_RELEASE / "atlas.geojson").read_text())["features"]
    current_features = json.loads((stage / "atlas.geojson").read_text())["features"]
    if current_features[: len(base_features)] != base_features:
        raise OpenSeedV93Error("v93 changed a v92 GeoJSON feature")

    montgomery = "epoch-ai:data-center:dec73855-d62c-5f35-bd1a-3b1f00b20bec"
    if _entity_csv_record(stage / "entities.csv", montgomery) != _entity_csv_record(
        BASE_RELEASE / "entities.csv", montgomery
    ):
        raise OpenSeedV93Error("v93 altered the v92 Montgomery campus CSV record")


def _validate_release_facts(stage: Path, *, recorded_at: str) -> None:
    if stage.is_symlink() or not stage.is_dir():
        raise OpenSeedV93Error("v93 release is not an ordinary directory")
    entries = {path.name: path for path in stage.iterdir()}
    if len(entries) != 14 or any(
        path.is_symlink() or not path.is_file() for path in entries.values()
    ):
        raise OpenSeedV93Error("v93 release file inventory differs")
    _raw, manifest = _read_json(stage / "manifest.json", sort_keys=True)
    if (
        manifest.get("as_of") != AS_OF
        or manifest.get("recorded_at") != recorded_at
        or manifest.get("publication_contract_version") != 4
        or manifest.get("entities") != 994
        or manifest.get("entities_by_kind") != {"campus": 516, "project": 478}
        or manifest.get("evidence_records") != 651
        or manifest.get("lifecycle_freshness_records") != 553
        or manifest.get("capacity_estimates") != 558
        or manifest.get("construction_pipeline_records") != 504
        or manifest.get("construction_source_signals") != 403
        or manifest.get("append_only_base_release") != v92.RELEASE_ID
        or manifest.get("base_rows_frozen") is not True
        or manifest.get("curated_source_input_delta") != 3
        or manifest.get("public_source_input_rows_delta") != 6
        or set(entries) != set(manifest["files"]) | {"manifest.json"}
    ):
        raise OpenSeedV93Error("v93 manifest release facts differ")
    for filename, pin in manifest["files"].items():
        raw = entries[filename].read_bytes()
        if (len(raw), _sha256(raw)) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV93Error(f"v93 release pin differs: {filename}")
    _validate_public_delta(stage)

    source_inputs = json.loads((stage / "source_inputs.json").read_text())
    sources = source_inputs.get("sources")
    base_sources = json.loads((BASE_RELEASE / "source_inputs.json").read_text())[
        "sources"
    ]
    added_source_inputs = {
        row.get("provenance", {}).get("curated_record_key"): row
        for row in sources or []
        if row.get("provenance", {}).get("curated_record_key")
        in ADDED_EXPORTED_EVIDENCE_KEYS
    }
    if (
        not isinstance(sources, list)
        or len(sources) != 578
        or sources[: len(base_sources)] != base_sources
        or len(sources) - len(base_sources) != 6
        or set(added_source_inputs) != ADDED_EXPORTED_EVIDENCE_KEYS
        or any(
            row.get("license") != "all-rights-reserved"
            for row in added_source_inputs.values()
        )
    ):
        raise OpenSeedV93Error("v93 source-input inventory differs")

    relevant_keys = ADDED_ENTITY_KEYS
    entities = {
        row["stable_key"]: row
        for row in _csv_rows(stage / "entities.csv")
        if row["stable_key"] in relevant_keys
    }
    if set(entities) != relevant_keys:
        raise OpenSeedV93Error("v93 relevant entity export differs")
    expected_country = dict.fromkeys(ADDED_ENTITY_KEYS, "United States")
    for key in ADDED_ENTITY_KEYS:
        row = entities[key]
        if (
            row["latitude"]
            or row["longitude"]
            or row["geometry_json"] not in {"", "null"}
            or row["country"] != expected_country[key]
            or any(
                row[field]
                for field in ("owner", "operator", "users", "tenants", "customers")
            )
            or row["operating_model"]
            or json.loads(row["workloads_json"]) != []
        ):
            raise OpenSeedV93Error(f"v93 added entity scope differs: {key}")

    for key, row in entities.items():
        capacities = json.loads(row["capacity_estimates_json"])
        if capacities:
            raise OpenSeedV93Error(f"v93 unexpected added capacity: {key}")

    expected_status = {
        key: ("", "") for key in ADDED_ENTITY_KEYS - ADDED_PROJECT_KEYS
    } | {
        "curated:google-haskell-county-quantum-linked-data-center-campus:current-development": (
            "under_construction",
            "2025-11-30",
        ),
        "curated:google-michigan-city-project-maize-data-center:2025-site-works": (
            "site_preparation",
            "2025-09-24",
        ),
        "curated:google-west-memphis-project-pyramid-data-center-campus:current-development": (
            "under_construction",
            "2025-10-02",
        ),
    }
    if {
        key: (entities[key]["status"], entities[key]["status_as_of"])
        for key in ADDED_ENTITY_KEYS
    } != expected_status:
        raise OpenSeedV93Error("v93 exported lifecycle facts differ")

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
        raise OpenSeedV93Error("v93 freshness boundary differs")
    pipeline = {
        row["stable_key"]
        for row in _csv_rows(stage / "construction_pipeline.csv")
        if row["stable_key"] in ADDED_PROJECT_KEYS
    }
    if pipeline != ADDED_PROJECT_KEYS:
        raise OpenSeedV93Error("v93 construction-pipeline delta differs")
    added_signals = [
        row
        for row in _csv_rows(stage / "construction_source_signals.csv")
        if row["representative_stable_key"] in ADDED_PROJECT_KEYS
    ]
    if (
        len(added_signals) != 3
        or {row["representative_stable_key"] for row in added_signals}
        != ADDED_PROJECT_KEYS
        or any(
            row["representative_latitude"] or row["representative_longitude"]
            for row in added_signals
        )
    ):
        raise OpenSeedV93Error("v93 construction-source-signal delta differs")

    summary = json.loads((stage / "summary.json").read_text(encoding="utf-8"))
    projection = summary.get("append_projection")
    if (
        summary.get("entities_total") != 994
        or summary.get("campuses_total") != 516
        or summary.get("projects_total") != 478
        or summary.get("evidence_total") != 825
        or summary.get("lifecycle_observations_current") != 553
        or summary.get("capacity_estimates_current") != 558
        or summary.get("construction_pipeline_records") != 504
        or summary.get("construction_source_signals") != 403
        or summary.get("entities_with_coordinates") != 213
        or summary.get("campuses_with_coordinates") != 141
        or not isinstance(projection, dict)
        or projection.get("curated_source_input_delta") != 3
        or projection.get("public_source_input_rows_delta") != 6
        or projection.get("internal_database_delta")
        != {
            "entities": 6,
            "evidence": 8,
            "lifecycle_observations": 3,
            "capacity_estimates": 0,
        }
        or projection.get("public_release_delta")
        != {
            "entities": 6,
            "evidence": 6,
            "lifecycle_freshness": 3,
            "capacity_estimates": 0,
            "construction_pipeline": 3,
            "construction_source_signals": 3,
        }
    ):
        raise OpenSeedV93Error("v93 summary projection contract differs")

    new_features = [
        feature
        for feature in json.loads((stage / "atlas.geojson").read_text())["features"]
        if feature["properties"]["stable_key"] in ADDED_ENTITY_KEYS
    ]
    if len(new_features) != 6 or any(
        feature.get("geometry") is not None for feature in new_features
    ):
        raise OpenSeedV93Error("v93 public geometry append differs")
    readme = (stage / "README.md").read_text(encoding="utf-8")
    for marker in (
        "Open seed v93 is the exact append-only accepted-v92 successor",
        "The curated database delta is eight evidence records and three lifecycle",
        "Public projection is intentionally smaller",
        "Rejected v1 is",
        "No capacity, energy, voltage",
        "no cross-source identity resolution or unique-site claim",
        "current_status_classification` is `unknown`",
        "current_construction_claim` is `false`",
    ):
        if marker not in readme:
            raise OpenSeedV93Error(f"v93 README guardrail differs: {marker}")


def _validate_definition(
    document: Mapping[str, Any],
    base: Mapping[str, Any],
    *,
    validation_wall_clock: datetime,
) -> str:
    if set(document) != set(base) or document.get("release_id") != RELEASE_ID:
        raise OpenSeedV93Error("v93 definition identity or schema differs")
    build = document.get("build")
    if not isinstance(build, dict) or set(build) != {"as_of", "recorded_at"}:
        raise OpenSeedV93Error("v93 definition build carrier differs")
    if build["as_of"] != AS_OF:
        raise OpenSeedV93Error("v93 as_of differs")
    expected_summary = document.get("expected_summary")
    if not isinstance(expected_summary, dict) or set(expected_summary) != set(
        base["expected_summary"]
    ):
        raise OpenSeedV93Error("v93 expected-summary key contract differs")
    recorded = v70.parse_utc(build["recorded_at"], label="v93 recorded_at")
    if (
        validation_wall_clock.tzinfo is None
        or recorded > validation_wall_clock.astimezone(UTC)
    ):
        raise OpenSeedV93Error("v93 recorded_at is later than validation wall clock")
    for key in (
        "epoch_capture",
        "expected_epoch_result",
        "freshness_contract",
        "publication_contract_version",
        "schema_version",
        "scope",
    ):
        if document.get(key) != base.get(key):
            raise OpenSeedV93Error(f"v93 inherited definition field differs: {key}")
    return build["recorded_at"]


def _validate_publication_times(
    definition: Path,
    release: Path,
    *,
    recorded_at: str,
    require_live: bool,
) -> None:
    target = v70.parse_utc(recorded_at, label="v93 recorded_at")
    for path in (definition, release, *release.iterdir()):
        metadata = path.stat(follow_symlinks=False)
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV93Error(
                f"v93 staged inode post-dates recorded_at: {path.name}"
            )
    if require_live:
        if datetime.now(UTC) < target:
            raise OpenSeedV93Error("v93 recorded_at is not live")
        for path in (definition, release, *release.iterdir()):
            if path.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
                raise OpenSeedV93Error(
                    f"v93 final inode ctime predates recorded_at: {path.name}"
                )


def _validate_guard(guard: Mapping[str, Any]) -> None:
    base_files = list(BASE_RELEASE.iterdir()) if BASE_RELEASE.is_dir() else []
    if (
        v92.DEFINITION != BASE_DEFINITION
        or v92.RELEASE != BASE_RELEASE
        or BASE_DEFINITION.is_symlink()
        or not BASE_DEFINITION.is_file()
        or stat.S_IMODE(BASE_DEFINITION.stat().st_mode) != 0o444
        or BASE_RELEASE.is_symlink()
        or not BASE_RELEASE.is_dir()
        or stat.S_IMODE(BASE_RELEASE.stat().st_mode) != 0o555
        or not base_files
        or any(
            path.is_symlink()
            or not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != 0o444
            for path in base_files
        )
        or guard["base_definition"] != BASE_DEFINITION_PIN
        or guard["base_manifest"] != BASE_MANIFEST_PIN
        or guard["base_tree"] != BASE_TREE_SHA256
        or guard["base_entities"] != BASE_ENTITIES_PIN
    ):
        raise OpenSeedV93Error("accepted v92 base pin differs")
    expected_manifests = {
        label: spec["manifest_pin"] for label, spec in OFFICIAL_SPECS.items()
    }
    expected_trees = {
        label: spec["physical_tree"] for label, spec in OFFICIAL_SPECS.items()
    }
    if (
        guard["official_manifests"] != expected_manifests
        or guard["official_trees"] != expected_trees
        or guard["additions"] != ADDITION_PINS
    ):
        raise OpenSeedV93Error("v93 official-source pin differs")


def validate_open_seed_v93(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
    require_live: bool = True,
) -> dict[str, Any]:
    if replay_count != 2:
        raise OpenSeedV93Error("v93 requires exactly two offline replays")
    wall = validation_wall_clock or datetime.now(UTC)
    guard = _guard_state()
    _validate_guard(guard)
    base = json.loads(BASE_DEFINITION.read_text())
    _definition_raw, definition = _read_json(
        definition_path, mode=0o444, sort_keys=True
    )
    recorded_at = _validate_definition(definition, base, validation_wall_clock=wall)
    selected, paths = selected_inputs(
        base, recorded_at=recorded_at, validation_wall_clock=wall
    )
    if definition.get("curated_inputs") != selected:
        raise OpenSeedV93Error("v93 selected input inventory differs")
    if release_path.is_symlink() or not release_path.is_dir():
        raise OpenSeedV93Error("v93 release must be an ordinary directory")
    if require_frozen and stat.S_IMODE(release_path.stat().st_mode) != 0o555:
        raise OpenSeedV93Error("v93 release root is not frozen")
    release_files = {path.name: path for path in release_path.iterdir()}
    if any(path.is_symlink() or not path.is_file() for path in release_files.values()):
        raise OpenSeedV93Error("v93 release contains a non-file")
    if require_frozen and any(
        stat.S_IMODE(path.stat().st_mode) != 0o444 for path in release_files.values()
    ):
        raise OpenSeedV93Error("v93 release file is not frozen")
    manifest_raw, manifest = _read_json(
        release_path / "manifest.json", mode=0o444, sort_keys=True
    )
    if _sha256(manifest_raw) != definition["expected_release"].get("manifest_sha256"):
        raise OpenSeedV93Error("v93 manifest hash differs")
    expected_release = {
        key: value
        for key, value in definition["expected_release"].items()
        if key != "manifest_sha256"
    }
    if {
        key: value for key, value in manifest.items() if key != "files"
    } != expected_release:
        raise OpenSeedV93Error("v93 expected release facts differ")
    if set(release_files) != set(manifest["files"]) | {"manifest.json"}:
        raise OpenSeedV93Error("v93 release file inventory differs")
    for filename, pin in manifest["files"].items():
        raw = (release_path / filename).read_bytes()
        if (len(raw), _sha256(raw)) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV93Error(f"v93 release pin differs: {filename}")
    _validate_publication_times(
        definition_path,
        release_path,
        recorded_at=recorded_at,
        require_live=require_live,
    )
    _validate_release_facts(release_path, recorded_at=recorded_at)
    summary = json.loads((release_path / "summary.json").read_text())
    if {key: summary[key] for key in definition["expected_summary"]} != definition[
        "expected_summary"
    ]:
        raise OpenSeedV93Error("v93 expected summary differs")

    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v93-replay-{replay + 1}-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            connection = _build_database(
                base, paths, root / "atlas.sqlite", recorded_at=recorded_at
            )
            try:
                replay_release = root / "release"
                _write_release(connection, replay_release, recorded_at=recorded_at)
            finally:
                connection.close()
            _validate_release_facts(replay_release, recorded_at=recorded_at)
            if {path.name for path in replay_release.iterdir()} != set(release_files):
                raise OpenSeedV93Error("v93 replay file inventory differs")
            for filename, frozen in release_files.items():
                if (replay_release / filename).read_bytes() != frozen.read_bytes():
                    raise OpenSeedV93Error(f"v93 offline replay differs: {filename}")
    if _guard_state() != guard:
        raise OpenSeedV93Error("v93 validation mutated accepted inputs")
    return manifest


def _path_identity(path: Path, *, directory: bool) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    expected = (
        stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    )
    if not expected:
        raise OpenSeedV93Error(f"v93 stage type differs: {path}")
    return metadata.st_dev, metadata.st_ino


def _release_identities(root: Path) -> dict[str, tuple[int, int]]:
    return {path.name: _path_identity(path, directory=False) for path in root.iterdir()}


def _assert_release_identities(
    root: Path,
    root_identity: tuple[int, int],
    members: Mapping[str, tuple[int, int]],
) -> None:
    if _path_identity(root, directory=True) != root_identity:
        raise OpenSeedV93Error("v93 release stage root identity changed")
    if _release_identities(root) != dict(members):
        raise OpenSeedV93Error("v93 release stage member identity changed")


def _discard_release_stage(
    root: Path,
    root_identity: tuple[int, int],
    members: Mapping[str, tuple[int, int]],
) -> None:
    if not root.exists() and not root.is_symlink():
        return
    _assert_release_identities(root, root_identity, members)
    root.chmod(0o700)
    for path in root.iterdir():
        path.chmod(0o600)
        path.unlink()
    root.rmdir()


def _discard_file_stage(path: Path, identity: tuple[int, int]) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if _path_identity(path, directory=False) != identity:
        raise OpenSeedV93Error("refusing substituted v93 definition cleanup")
    path.chmod(0o600)
    path.unlink()


def _fsync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise OpenSeedV93Error("active v93 publication lock exists") from error
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
                or (
                    current.st_dev,
                    current.st_ino,
                )
                != identity
            ):
                raise OpenSeedV93Error("refusing substituted v93 lock cleanup")
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
    release.chmod(0o500)
    for path in release.iterdir():
        path.chmod(0o400)
        path.chmod(0o444)
        _fsync(path)
    release.chmod(0o555)
    _fsync(release)


def _require_absent(label: str) -> None:
    if DEFINITION.exists() or DEFINITION.is_symlink():
        raise OpenSeedV93Error(f"{label} v93 definition collision")
    if RELEASE.exists() or RELEASE.is_symlink():
        raise OpenSeedV93Error(f"{label} v93 release collision")


def _rollback_release(release_identity: tuple[int, int], release_stage: Path) -> None:
    if _path_identity(RELEASE, directory=True) != release_identity:
        raise OpenSeedV93Error("refusing rollback of substituted v93 release")
    if release_stage.exists() or release_stage.is_symlink():
        raise OpenSeedV93Error("v93 release rollback stage is occupied")
    v69.promote_noreplace(RELEASE, release_stage)


def _rollback_definition(
    definition_identity: tuple[int, int], definition_stage: Path
) -> None:
    if _path_identity(DEFINITION, directory=False) != definition_identity:
        raise OpenSeedV93Error("refusing rollback of substituted v93 definition")
    if definition_stage.exists() or definition_stage.is_symlink():
        raise OpenSeedV93Error("v93 definition rollback stage is occupied")
    v69.promote_noreplace(DEFINITION, definition_stage)


def build_open_seed_v93(recorded_at: str | None = None) -> dict[str, Any]:
    """Build and atomically publish the three-source v92 successor."""

    if (DEFINITION.exists() or DEFINITION.is_symlink()) and (
        RELEASE.exists() or RELEASE.is_symlink()
    ):
        manifest = validate_open_seed_v93()
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
        raise OpenSeedV93Error("partial v93 final-path collision")

    guard = _guard_state()
    _validate_guard(guard)
    target = (
        v70.parse_utc(recorded_at, label="v93 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=90)
    )
    if datetime.now(UTC) >= target:
        raise OpenSeedV93Error("v93 recorded_at must be future before staging")
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
        release_identity = _path_identity(release_stage, directory=True)
        release_members: dict[str, tuple[int, int]] = {}
        published_release = False
        published_definition = False
        try:
            os.close(descriptor)
            base = json.loads(BASE_DEFINITION.read_text())
            input_rows, paths = selected_inputs(
                base, recorded_at=recorded_at, validation_wall_clock=target
            )
            with tempfile.TemporaryDirectory(
                prefix="open-seed-v93-db-", dir="/private/tmp"
            ) as temporary_database:
                connection = _build_database(
                    base,
                    paths,
                    Path(temporary_database) / "atlas.sqlite",
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
            summary = json.loads(
                (release_stage / "summary.json").read_text(encoding="utf-8")
            )
            manifest_raw = (release_stage / "manifest.json").read_bytes()
            manifest = json.loads(manifest_raw)
            expected_release = {
                key: value for key, value in manifest.items() if key != "files"
            }
            expected_release["manifest_sha256"] = _sha256(manifest_raw)
            definition = dict(base)
            definition["build"] = {"as_of": AS_OF, "recorded_at": recorded_at}
            definition["curated_inputs"] = input_rows
            definition["expected_release"] = expected_release
            definition["expected_summary"] = {
                key: summary[key] for key in base["expected_summary"]
            }
            definition["release_id"] = RELEASE_ID
            with definition_stage.open("r+b") as stream:
                stream.write(_canonical(definition, sort_keys=True))
                stream.truncate()
                stream.flush()
                os.fsync(stream.fileno())
            definition_stage.chmod(0o444)
            _fsync(definition_stage)
            for path in release_stage.iterdir():
                path.chmod(0o444)
                _fsync(path)
            release_stage.chmod(0o555)
            _fsync(release_stage)
            release_members = _release_identities(release_stage)
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
                raise OpenSeedV93Error("v93 definition stage identity changed")
            _assert_release_identities(release_stage, release_identity, release_members)
            if (
                definition_stage.read_bytes() != frozen_definition
                or v69.tree_digest(release_stage) != frozen_tree
            ):
                raise OpenSeedV93Error("v93 private stage changed while waiting")
            _refresh_publication_ctimes(definition_stage, release_stage)
            _assert_release_identities(release_stage, release_identity, release_members)
            if (
                definition_stage.read_bytes() != frozen_definition
                or v69.tree_digest(release_stage) != frozen_tree
            ):
                raise OpenSeedV93Error("v93 private bytes changed at publication")
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
                    _rollback_release(release_identity, release_stage)
                    published_release = False
                except Exception as rollback_error:
                    error.add_note(f"v93 release rollback failed: {rollback_error}")
                raise
            try:
                manifest = validate_open_seed_v93(DEFINITION, RELEASE)
            except BaseException as error:
                rollback_errors = []
                try:
                    _rollback_definition(definition_identity, definition_stage)
                    published_definition = False
                except Exception as rollback_error:
                    rollback_errors.append(
                        f"v93 definition rollback failed: {rollback_error}"
                    )
                try:
                    _rollback_release(release_identity, release_stage)
                    published_release = False
                except Exception as rollback_error:
                    rollback_errors.append(
                        f"v93 release rollback failed: {rollback_error}"
                    )
                for note in rollback_errors:
                    error.add_note(note)
                raise
        finally:
            if not published_release and release_stage.exists():
                if release_members:
                    _discard_release_stage(
                        release_stage, release_identity, release_members
                    )
                else:
                    shutil.rmtree(release_stage)
            if not published_definition and definition_stage.exists():
                _discard_file_stage(definition_stage, definition_identity)
    if _guard_state() != guard:
        raise OpenSeedV93Error("v93 build mutated accepted inputs")
    return {
        "definition": str(DEFINITION),
        "definition_sha256": v69.sha256(DEFINITION),
        "manifest_sha256": v69.sha256(RELEASE / "manifest.json"),
        "recorded_at": manifest["recorded_at"],
        "release": str(RELEASE),
        "release_tree_sha256": v69.tree_digest(RELEASE),
        "status": "published",
    }


def main() -> int:
    print(json.dumps(build_open_seed_v93(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
