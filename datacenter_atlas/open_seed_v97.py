"""Governed open-seed v97 successor over the immutable live v96 release.

V97 appends exactly the accepted CtrlS Chandanvelly, CtrlS Pharmacity, and
EdgeConneX/Lambda Chicago source files.  It performs no replacement.  Every
v96 public row is projected byte-for-byte and only the deterministic new rows
are appended.  The normal entry point is a private prepublication run.  Live
publication requires an explicit authorization flag and crosses a release-
first, definition-second, atomic no-replace barrier only after two identical
offline replays.
"""

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
import sys
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence

from . import ctrls_chandanvelly_pharmacity_current_build_tranche_20260722 as ctrls
from . import edgeconnex_lambda_chicago_official_current_build_20260722 as edge
from . import open_seed_v69 as v69
from . import open_seed_v95 as v95
from . import open_seed_v96 as v96
from .publication_release import build_release_documents


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
BASE_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-22-v96.json"
BASE_RELEASE = ROOT / "releases/2026-07-22-open-seed-v96"
DEFINITION = SOURCES_ROOT / "open-seed-2026-07-22-v97.json"
RELEASE_ID = "2026-07-22-open-seed-v97"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v97.lock"
AS_OF = "2026-07-22"

BASE_RECORDED_AT = "2026-07-22T05:29:06Z"
BASE_INPUT_COUNT = 516
EXPECTED_INPUT_COUNT = 519
BASE_DEFINITION_PIN = (
    121_029,
    "d49c9de9aaded6af7c103375b71d07f0904fe6cc7a24785a678e82bfe5e6d6c0",
)
BASE_MANIFEST_PIN = (
    21_007,
    "8407f11a8e414810cd7d56ee5fd6f7e95015771c72d3106e4ab96d1ddb41422e",
)
BASE_ENTITIES_PIN = (
    1_071_703,
    "fd33c2df011b63f57ca1dc3388b5d0925b5cc1a43017c94e1ceb849a49c47c68",
)
BASE_SOURCE_INPUTS_PIN = (
    440_619,
    "51a8a0b974e24b39364eeba9d1728a99d4db2ae4434482489657d4103ae8856f",
)
BASE_TREE_SHA256 = "8fdd260892474febf2ac3dc7a368b68ecda419d53f97357b54142b1c40bca558"

CTRL_ARTIFACT_RECORDED_AT = "2026-07-22T05:41:33Z"
CTRL_ARTIFACT_MANIFEST_PIN = (
    2_072,
    "084a7d80f3a0436e8489c297835aca074a6742cb451a9047f0b4a895b41f2270",
)
CTRL_ARTIFACT_LOGICAL_TREE_SHA256 = (
    "481e3afd109f820b5b18d377e79c1170c5b2992ea19b8684f90e90c41c587ebe"
)
CTRL_ARTIFACT_PHYSICAL_TREE_SHA256 = (
    "6a2df9c3069ac1ed726ed302400e22083fe18d4e9c80f5ebc839d5d7eec9126b"
)

EDGE_ARTIFACT_RECORDED_AT = "2026-07-22T05:30:49Z"
EDGE_ARTIFACT_MANIFEST_PIN = (
    1_723,
    "106a768c6a451da3ed335a6515a2e4e2458eaa8ac2c5c326ad4c6b97ef0e39d0",
)
EDGE_ARTIFACT_LOGICAL_TREE_SHA256 = (
    "e896f56c8364037287b7827e32f53f4f6c780b4a30bad6046ce499ab488a4147"
)
EDGE_ARTIFACT_PHYSICAL_TREE_SHA256 = (
    "9b9214c972e96dd51a679d29a55b449d0db4fc3e45f5b9b81c290771125a0d6d"
)

APPEND_ORDER = (
    f"sources/{ctrls.CHANDANVELLY_SOURCE_FILENAME}",
    f"sources/{ctrls.PHARMACITY_SOURCE_FILENAME}",
    f"sources/{edge.SOURCE_FILENAME}",
)
SOURCE_PINS: Mapping[str, tuple[int, str]] = {
    APPEND_ORDER[0]: (
        7_825,
        "af57d566fde98ad81d52b89df6709bece2d6fa46a0f0e5302ae9df5e0ad40c37",
    ),
    APPEND_ORDER[1]: (
        4_932,
        "fc9175408fff782eaedce12d5da04b5125caa103dfe194f6032b26d1ff6b737b",
    ),
    APPEND_ORDER[2]: (
        12_217,
        "d43bcec02e9459d307ecaadadf0c9cbc59100f9008d835567db9f1db47c8748f",
    ),
}
SOURCE_BIRTH_MTIME_PINS: Mapping[str, tuple[float, int]] = {
    APPEND_ORDER[0]: (1_784_698_849.0706782, 1_784_698_849_070_678_287),
    APPEND_ORDER[1]: (1_784_698_849.0708606, 1_784_698_849_070_860_575),
    APPEND_ORDER[2]: (1_784_698_204.049011, 1_784_698_204_049_010_959),
}
HISTORICAL_SOURCE_CTIME_NS: Mapping[str, int] = {
    APPEND_ORDER[0]: 1_784_698_893_030_743_791,
    APPEND_ORDER[1]: 1_784_698_893_030_859_372,
    APPEND_ORDER[2]: 1_784_698_249_038_004_879,
}

ADDED_ENTITY_KEYS = frozenset(
    {
        ctrls.CHANDANVELLY_CAMPUS_KEY,
        ctrls.CHANDANVELLY_PROJECT_KEY,
        ctrls.PHARMACITY_CAMPUS_KEY,
        ctrls.PHARMACITY_PROJECT_KEY,
        edge.CAMPUS_KEY,
        edge.PROJECT_KEY,
    }
)
ADDED_PROJECT_KEYS = frozenset(
    {
        ctrls.CHANDANVELLY_PROJECT_KEY,
        ctrls.PHARMACITY_PROJECT_KEY,
        edge.PROJECT_KEY,
    }
)
EXPECTED_EVIDENCE_KEYS = frozenset(
    {
        "ctrls-chandanvelly-building-page-modified-2026-07-21-captured-2026-07-22",
        "ctrls-chandanvelly-announcement-2025-01-20-captured-2026-07-22",
        "ctrls-pharmacity-building-page-modified-2026-07-21-captured-2026-07-22",
        "edgeconnex-lambda-chicago-build-2025-08-21",
        "edgeconnex-construction-safety-week-2025-05-18",
        "edgeconnex-chicago-location-page-captured-2026-07-22",
    }
)
PUBLIC_EVIDENCE_IDS = frozenset(
    {
        "c96c59a0-8bfb-5b34-a380-21d5d519f3b4",
        "9456693a-13b4-5bbc-bc2d-0cdde1cf6512",
        "ba4efcbb-a21b-50f2-9be9-b324ce23adea",
    }
)
EXPECTED_LIFECYCLE = frozenset(
    {
        (
            ctrls.CHANDANVELLY_PROJECT_KEY,
            "under_construction",
            "2026-07-21",
            "authoritative_physical_status_update",
        ),
        (
            ctrls.PHARMACITY_PROJECT_KEY,
            "under_construction",
            "2026-07-21",
            "authoritative_physical_status_update",
        ),
        (
            edge.PROJECT_KEY,
            "under_construction",
            "2025-08-21",
            "authoritative_physical_status_update",
        ),
    }
)
EXPECTED_WORKLOADS = frozenset(
    {
        (edge.PROJECT_KEY, "hpc", "2025-08-21", "company_disclosure"),
        (edge.PROJECT_KEY, "ai_training", "2025-08-21", "company_disclosure"),
        (edge.PROJECT_KEY, "ai_inference", "2025-08-21", "company_disclosure"),
    }
)
EXPECTED_DATABASE_COUNTS = {
    "entities": 1_053,
    "evidence": 889,
    "campuses": 545,
    "projects": 508,
    "entity_snapshots": 1_078,
    "lifecycle_observations": 606,
    "operating_model_observations": 77,
    "workload_observations": 139,
    "capacity_estimates": 571,
}
INTERNAL_DELTA = {
    "entities": 6,
    "evidence": 6,
    "campuses": 3,
    "projects": 3,
    "entity_snapshots": 6,
    "lifecycle_observations": 3,
    "operating_model_observations": 0,
    "workload_observations": 3,
    "capacity_estimates": 0,
}
PUBLIC_DELTA = {
    "entities": 6,
    "evidence": 3,
    "lifecycle_freshness": 3,
    "construction_pipeline": 3,
    "construction_source_signals": 3,
    "capacity_estimates": 0,
    "source_input_rows": 3,
}
STALE_POLICY = dict(v96.STALE_POLICY)
COORDINATE_BOUNDARY = {
    **v96.COORDINATE_BOUNDARY,
    "v97_coordinates_added": [],
}
CLAIM_BOUNDARY = {
    "ctrls_normalized_operating_models": [],
    "ctrls_normalized_workloads": [],
    "ctrls_normalized_capacity_or_efficiency": [],
    "edge_normalized_operating_models": [],
    "edge_normalized_workloads": ["hpc", "ai_training", "ai_inference"],
    "edge_reported_23mw_treatment": "untyped_source_metadata_only",
    "annual_energy_added": False,
    "wue_added": False,
    "coordinates_or_geometry_added": False,
}
ATTRIBUTION_ADDITIONS = frozenset({"CtrlS Datacenters Ltd"})

V97_README = """## Governed v97 append-only successor boundary

Open seed v97 is the exact append-only successor to immutable live v96. It
appends only the accepted CtrlS Chandanvelly, CtrlS Pharmacity, and
EdgeConneX/Lambda Chicago source records. Every v96 public row is retained
byte-for-byte and the three new campus/project pairs are appended.

The two CtrlS records add only generic under-construction lifecycle evidence.
They add no normalized data-center type, operating model, workload, capacity,
energy, PUE, WUE, coordinate, footprint, or geometry. The Chicago record adds
the three explicitly disclosed workloads: HPC, AI training, and AI inference.
Its reported 23 MW remains untyped source metadata and creates no capacity,
load, consumption, generation, or energy observation.

Jakarta, Hanoi, and Oran keep the v96 stale-status policy unchanged: their
history and source signals remain, their public current status stays unknown,
and they remain outside the construction pipeline.
"""

PROMOTION_CONTRACT = {
    "atomic_no_replace_required": True,
    "definition_and_release_same_filesystem_as_final_parent": True,
    "identity_checked_before_and_after_promotion": True,
    "rollback_uses_atomic_no_replace": True,
    "rollback_refuses_identity_mismatch": True,
    "replay_count": 2,
    "publication_implemented": True,
    "stage_adoption_allowed": False,
}


class OpenSeedV97Error(RuntimeError):
    """Raised when a v97 lineage, semantic, or publication fuse fails."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pin(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), _sha256(raw)


def _source_metadata(path: Path) -> dict[str, int | float | None]:
    metadata = path.stat(follow_symlinks=False)
    return {
        "birthtime": getattr(metadata, "st_birthtime", None),
        "mtime_ns": metadata.st_mtime_ns,
        "ctime_ns": metadata.st_ctime_ns,
        "nlink": metadata.st_nlink,
    }


def _accepted_source_inode_observations() -> dict[str, dict[str, int]]:
    observations: dict[str, dict[str, int]] = {}
    for relative in APPEND_ORDER:
        metadata = _source_metadata(ROOT / relative)
        observations[relative] = {
            "historical_accepted_ctime_ns": HISTORICAL_SOURCE_CTIME_NS[relative],
            "current_ctime_ns": int(metadata["ctime_ns"]),
            "current_nlink": int(metadata["nlink"]),
        }
    return observations


def _canonical(value: Any, *, sort_keys: bool = False) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=sort_keys, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _read_json(
    path: Path, *, mode: int | None = None, sort_keys: bool = False
) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise OpenSeedV97Error(f"ordinary JSON file is absent: {path}")
    if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
        raise OpenSeedV97Error(f"JSON mode differs: {path}")
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict) or raw != _canonical(value, sort_keys=sort_keys):
        raise OpenSeedV97Error(f"JSON is not canonical: {path}")
    return value


def _release_descendants(root: Path) -> list[Path]:
    return sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix())


def _validate_chronology(root: Path, recorded_at: str, *, frozen: bool) -> None:
    target = v95.v70.parse_utc(recorded_at, label="accepted recorded_at")
    paths = [root, *_release_descendants(root)] if root.is_dir() else [root]
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        birth = getattr(metadata, "st_birthtime", metadata.st_mtime)
        if max(birth, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV97Error(f"accepted inode post-dates recorded_at: {path}")
        if frozen and metadata.st_ctime + 1e-6 < target.timestamp():
            raise OpenSeedV97Error(f"accepted ctime predates recorded_at: {path}")


def _validate_base() -> dict[str, Any]:
    if (
        BASE_DEFINITION != v96.DEFINITION
        or BASE_RELEASE != v96.RELEASE
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
        raise OpenSeedV97Error("immutable live v96 base pin differs")
    definition = _read_json(BASE_DEFINITION, mode=0o444, sort_keys=True)
    manifest = _read_json(BASE_RELEASE / "manifest.json", mode=0o444, sort_keys=True)
    if (
        definition.get("release_id") != v96.RELEASE_ID
        or definition.get("build", {}).get("recorded_at") != BASE_RECORDED_AT
        or len(definition.get("curated_inputs", [])) != BASE_INPUT_COUNT
        or manifest.get("recorded_at") != BASE_RECORDED_AT
        or manifest.get("entities") != 1_047
        or set(manifest.get("files", {}))
        != {
            path.name for path in BASE_RELEASE.iterdir() if path.name != "manifest.json"
        }
    ):
        raise OpenSeedV97Error("immutable live v96 base semantics differ")
    for path in _release_descendants(BASE_RELEASE):
        if (
            path.is_symlink()
            or not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != 0o444
        ):
            raise OpenSeedV97Error(f"immutable live v96 member differs: {path.name}")
    for filename, row in manifest["files"].items():
        if _pin(BASE_RELEASE / filename) != (row["bytes"], row["sha256"]):
            raise OpenSeedV97Error(f"immutable live v96 member pin differs: {filename}")
    expected_release = definition.get("expected_release", {})
    if expected_release.get("manifest_sha256") != BASE_MANIFEST_PIN[1]:
        raise OpenSeedV97Error("immutable live v96 definition manifest pin differs")
    _validate_chronology(BASE_DEFINITION, BASE_RECORDED_AT, frozen=True)
    _validate_chronology(BASE_RELEASE, BASE_RECORDED_AT, frozen=True)
    return definition


def _validate_accepted_inputs() -> dict[str, dict[str, Any]]:
    try:
        ctrls_result = ctrls._existing_identical(None)
        edge_result = edge.validate_published()
    except (ctrls.CtrlSPublicationError, edge.EdgeConneXPublicationError) as error:
        raise OpenSeedV97Error(f"accepted v97 input invalid: {error}") from error
    ctrl_manifest = _read_json(ctrls.ARTIFACT / "manifest.json", mode=0o444)
    edge_manifest = _read_json(edge.ARTIFACT / "manifest.json", mode=0o444)
    if (
        ctrls_result.get("recorded_at") != CTRL_ARTIFACT_RECORDED_AT
        or _pin(ctrls.ARTIFACT / "manifest.json") != CTRL_ARTIFACT_MANIFEST_PIN
        or ctrl_manifest.get("tree_sha256") != CTRL_ARTIFACT_LOGICAL_TREE_SHA256
        or v69.tree_digest(ctrls.ARTIFACT) != CTRL_ARTIFACT_PHYSICAL_TREE_SHA256
        or edge_result.get("recorded_at") != EDGE_ARTIFACT_RECORDED_AT
        or _pin(edge.ARTIFACT / "manifest.json") != EDGE_ARTIFACT_MANIFEST_PIN
        or edge_manifest.get("tree_sha256") != EDGE_ARTIFACT_LOGICAL_TREE_SHA256
        or v69.tree_digest(edge.ARTIFACT) != EDGE_ARTIFACT_PHYSICAL_TREE_SHA256
    ):
        raise OpenSeedV97Error("accepted v97 artifact pin differs")
    ctrl_documents = ctrls.expected_source_documents()
    edge_documents = edge.expected_source_documents()
    documents: dict[str, dict[str, Any]] = {
        f"sources/{name}": document for name, document in ctrl_documents.items()
    }
    documents.update(
        {f"sources/{name}": document for name, document in edge_documents.items()}
    )
    if tuple(documents) != APPEND_ORDER:
        raise OpenSeedV97Error("accepted v97 source order differs")
    for relative, document in documents.items():
        path = ROOT / relative
        metadata = path.stat(follow_symlinks=False)
        source_metadata = _source_metadata(path)
        if (
            path.is_symlink()
            or not path.is_file()
            or stat.S_IMODE(metadata.st_mode) != 0o444
            or _pin(path) != SOURCE_PINS[relative]
            or (source_metadata["birthtime"], source_metadata["mtime_ns"])
            != SOURCE_BIRTH_MTIME_PINS[relative]
            or path.read_bytes() != _canonical(document)
        ):
            raise OpenSeedV97Error(f"accepted v97 source pin differs: {relative}")
    _assert_no_later_collisions(documents)
    _validate_source_claims(documents)
    return documents


def _assert_no_later_collisions(
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    stable_keys = {
        document[name]["stable_key"]
        for document in documents.values()
        for name in ("campus", "project")
    }
    evidence_keys = {
        row["key"] for document in documents.values() for row in document["evidence"]
    }
    selected_names = {Path(relative).name for relative in documents}
    collisions: list[str] = []
    for path in sorted(SOURCES_ROOT.glob("curated-*.json")):
        if path.name in selected_names:
            continue
        if path.is_symlink() or not path.is_file():
            collisions.append(f"unsafe:{path.name}")
            continue
        try:
            candidate = json.loads(path.read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            collisions.append(f"unreadable:{path.name}")
            continue
        for name in ("campus", "project"):
            entity = candidate.get(name)
            if isinstance(entity, dict) and entity.get("stable_key") in stable_keys:
                collisions.append(f"stable-key:{path.name}:{name}")
        for row in candidate.get("evidence", []):
            if isinstance(row, dict) and row.get("key") in evidence_keys:
                collisions.append(f"evidence:{path.name}")
    if collisions:
        raise OpenSeedV97Error(
            f"accepted v97 source has later collision: {collisions!r}"
        )


def _validate_source_claims(
    documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if tuple(documents) != APPEND_ORDER:
        raise OpenSeedV97Error("v97 source document order differs")
    stable_keys = {
        document[name]["stable_key"]
        for document in documents.values()
        for name in ("campus", "project")
    }
    evidence_keys = {
        row["key"] for document in documents.values() for row in document["evidence"]
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
    workloads = {
        (
            document[row["entity"]]["stable_key"],
            row["value"],
            row["as_of_date"],
            row["method"],
        )
        for document in documents.values()
        for row in document["workloads"]
    }
    if (
        stable_keys != ADDED_ENTITY_KEYS
        or evidence_keys != EXPECTED_EVIDENCE_KEYS
        or lifecycle != EXPECTED_LIFECYCLE
        or workloads != EXPECTED_WORKLOADS
        or any(document["capacities"] for document in documents.values())
        or any(document["operating_models"] for document in documents.values())
    ):
        raise OpenSeedV97Error("v97 accepted source claim contract differs")
    for relative, document in documents.items():
        for name in ("campus", "project"):
            entity = document[name]
            if entity["coordinates"] is not None or entity["geometry"] is not None:
                raise OpenSeedV97Error(f"v97 unexpected coordinate: {relative}")
        for row in (*document["capacities"], *document["workloads"]):
            if row.get("metric") in {"annual_energy_mwh", "wue"}:
                raise OpenSeedV97Error("v97 normalized energy or WUE")
    ctrl_paths = APPEND_ORDER[:2]
    if any(
        documents[path][field]
        for path in ctrl_paths
        for field in ("capacities", "operating_models", "workloads")
    ):
        raise OpenSeedV97Error("CtrlS acquired an unsupported normalized type")
    return {
        "stable_keys": stable_keys,
        "evidence_keys": evidence_keys,
        "lifecycle": lifecycle,
        "workloads": workloads,
    }


def planned_selection(
    base: Mapping[str, Any], documents: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, str]]:
    rows = base.get("curated_inputs")
    if (
        base.get("release_id") != v96.RELEASE_ID
        or not isinstance(rows, list)
        or len(rows) != BASE_INPUT_COUNT
        or any(set(row) != {"path", "sha256"} for row in rows)
        or tuple(documents) != APPEND_ORDER
    ):
        raise OpenSeedV97Error("immutable v96 curated inventory differs")
    existing = {row["path"] for row in rows}
    if existing & set(APPEND_ORDER):
        raise OpenSeedV97Error("v97 append path already selected")
    selected = [*map(dict, rows)]
    selected.extend(
        {"path": relative, "sha256": SOURCE_PINS[relative][1]}
        for relative in APPEND_ORDER
    )
    if (
        selected[:BASE_INPUT_COUNT] != rows
        or [row["path"] for row in selected[BASE_INPUT_COUNT:]] != list(APPEND_ORDER)
        or len(selected) != EXPECTED_INPUT_COUNT
        or len({row["path"] for row in selected}) != EXPECTED_INPUT_COUNT
    ):
        raise OpenSeedV97Error("v97 append-only inventory differs")
    base_stable = {
        row["stable_key"] for row in _csv_rows(BASE_RELEASE / "entities.csv")
    }
    base_evidence = {
        item["key"]
        for row in rows
        for item in json.loads((ROOT / row["path"]).read_text()).get("evidence", [])
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }
    contract = _validate_source_claims(documents)
    if (
        base_stable & contract["stable_keys"]
        or base_evidence & contract["evidence_keys"]
    ):
        raise OpenSeedV97Error("v97 stable/evidence key collides with v96")
    return selected


def readiness_report() -> dict[str, Any]:
    base = _validate_base()
    documents = _validate_accepted_inputs()
    selected = planned_selection(base, documents)
    return {
        "status": "ready",
        "base_release_id": v96.RELEASE_ID,
        "base_definition_sha256": BASE_DEFINITION_PIN[1],
        "base_tree_sha256": BASE_TREE_SHA256,
        "base_input_count": BASE_INPUT_COUNT,
        "planned_input_count": len(selected),
        "append_order": list(APPEND_ORDER),
        "accepted_artifacts_validated": ["ctrls", "edgeconnex_lambda"],
        "accepted_source_inode_observations": _accepted_source_inode_observations(),
        "accepted_source_observational_not_identity_signals": ["ctime_ns", "nlink"],
        "stale_status_suppression_unchanged": sorted(v96.EXPECTED_STALE_PROJECT_KEYS),
        "promotion_contract": dict(PROMOTION_CONTRACT),
        "final_definition_absent": not DEFINITION.exists(),
        "final_release_absent": not RELEASE.exists(),
        "publication_lock_absent": not PUBLICATION_LOCK.exists(),
    }


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _csv_text(template: str, rows: Sequence[Mapping[str, str]]) -> str:
    reader = csv.DictReader(io.StringIO(template))
    if reader.fieldnames is None:
        raise OpenSeedV97Error("CSV template lacks a header")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=reader.fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def selected_inputs(
    base: Mapping[str, Any],
    *,
    recorded_at: str,
    validation_wall_clock: datetime | None = None,
) -> tuple[list[dict[str, str]], list[Path]]:
    documents = _validate_accepted_inputs()
    selected = planned_selection(base, documents)
    target = v95.v70.parse_utc(recorded_at, label="v97 recorded_at")
    wall = validation_wall_clock or datetime.now(UTC)
    if wall.tzinfo is None or target > wall.astimezone(UTC):
        raise OpenSeedV97Error("v97 recorded_at exceeds validation wall clock")
    if any(
        v95.v70.parse_utc(value, label="accepted artifact recorded_at") > target
        for value in (CTRL_ARTIFACT_RECORDED_AT, EDGE_ARTIFACT_RECORDED_AT)
    ):
        raise OpenSeedV97Error("v97 publication time precedes an accepted input")
    for relative, document in documents.items():
        for index, evidence in enumerate(document["evidence"]):
            retrieved = v95.v70.parse_utc(
                evidence["retrieved_at"], label=f"{relative} evidence[{index}]"
            )
            if retrieved > target or retrieved > wall.astimezone(UTC):
                raise OpenSeedV97Error("v97 accepted evidence is future-dated")
    paths: list[Path] = []
    for row in selected:
        path = ROOT / row["path"]
        if path.is_symlink() or not path.is_file() or v69.sha256(path) != row["sha256"]:
            raise OpenSeedV97Error(f"v97 selected input pin differs: {row['path']}")
        paths.append(path)
    return selected, paths


def _base_paths(base: Mapping[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for row in base["curated_inputs"]:
        path = ROOT / row["path"]
        if path.is_symlink() or not path.is_file() or v69.sha256(path) != row["sha256"]:
            raise OpenSeedV97Error(f"immutable v96 input pin differs: {row['path']}")
        paths.append(path)
    return paths


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
        raise OpenSeedV97Error(f"v97 database counts differ: {counts}")

    with tempfile.TemporaryDirectory(
        prefix="open-seed-v97-base-", dir="/private/tmp"
    ) as temporary:
        prior = v69._populate_database(
            base,
            _base_paths(base),
            Path(temporary) / "v96.sqlite",
            recorded_at=recorded_at,
        )
        try:
            expected_additions = {
                "entities": 6,
                "evidence": 6,
                "campuses": 3,
                "projects": 3,
                "entity_snapshots": 6,
                "lifecycle_observations": 3,
                "operating_model_observations": 0,
                "workload_observations": 3,
                "capacity_estimates": 0,
            }
            for table, expected_added in expected_additions.items():
                before = _table_state(prior, table)
                after = _table_state(connection, table)
                if before - after or len(after - before) != expected_added:
                    raise OpenSeedV97Error(f"v97 database delta differs: {table}")
            added_entities = _table_state(connection, "entities") - _table_state(
                prior, "entities"
            )
            entity_columns = [
                row[1] for row in connection.execute("PRAGMA table_info(entities)")
            ]
            stable_index = entity_columns.index("stable_key")
            if {row[stable_index] for row in added_entities} != ADDED_ENTITY_KEYS:
                raise OpenSeedV97Error("v97 entity key delta differs")
            added_snapshots = _table_state(
                connection, "entity_snapshots"
            ) - _table_state(prior, "entity_snapshots")
            if (
                _entity_keys_for_rows(connection, added_snapshots, id_index=1)
                != ADDED_ENTITY_KEYS
            ):
                raise OpenSeedV97Error("v97 snapshot key delta differs")
            added_lifecycle = _table_state(
                connection, "lifecycle_observations"
            ) - _table_state(prior, "lifecycle_observations")
            if (
                _entity_keys_for_rows(connection, added_lifecycle, id_index=1)
                != ADDED_PROJECT_KEYS
            ):
                raise OpenSeedV97Error("v97 lifecycle key delta differs")
            added_workloads = _table_state(
                connection, "workload_observations"
            ) - _table_state(prior, "workload_observations")
            if _entity_keys_for_rows(connection, added_workloads, id_index=1) != {
                edge.PROJECT_KEY
            }:
                raise OpenSeedV97Error("v97 workload key delta differs")
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
    workloads = {
        tuple(row)
        for row in connection.execute(
            """
            SELECT entities.stable_key, workload, as_of_date,
                   workload_observations.method
            FROM workload_observations
            JOIN entities ON entities.id=entity_id
            """
        )
        if row[0] in ADDED_ENTITY_KEYS
    }
    operating_models = [
        tuple(row)
        for row in connection.execute(
            """
            SELECT entities.stable_key, operating_model
            FROM operating_model_observations
            JOIN entities ON entities.id=entity_id
            """
        )
        if row[0] in ADDED_ENTITY_KEYS
    ]
    capacities = [
        tuple(row)
        for row in connection.execute(
            """
            SELECT entities.stable_key, metric, stage, unit, base
            FROM capacity_estimates
            JOIN entities ON entities.id=entity_id
            """
        )
        if row[0] in ADDED_ENTITY_KEYS
    ]
    if (
        lifecycle != EXPECTED_LIFECYCLE
        or workloads != EXPECTED_WORKLOADS
        or operating_models
        or capacities
    ):
        raise OpenSeedV97Error("v97 imported claim contract differs")
    placeholders = ",".join("?" for _ in ADDED_ENTITY_KEYS)
    snapshots = connection.execute(
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
        for _key, latitude, longitude, geometry_json in snapshots
    ):
        raise OpenSeedV97Error("v97 imported an unaccepted coordinate")


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
        raise OpenSeedV97Error(f"duplicate public key: {key}")
    return rows, by_key


def _project_keyed_csv(
    output: dict[str, str],
    filename: str,
    *,
    key: str,
    raw_additions: frozenset[str],
    raw_changes: frozenset[str] = frozenset(),
    selected_additions: frozenset[str] | None = None,
    allow_base_recomputation: bool = False,
) -> None:
    base_rows = _csv_rows(BASE_RELEASE / filename)
    current_rows, current_by_key = _keyed_rows(output[filename], key)
    base_by_key = {row[key]: row for row in base_rows}
    base_keys = set(base_by_key)
    current_keys = set(current_by_key)
    changed = {
        row_key
        for row_key in base_keys & current_keys
        if base_by_key[row_key] != current_by_key[row_key]
    }
    if (
        base_keys - current_keys
        or current_keys - base_keys != set(raw_additions)
        or (not allow_base_recomputation and changed != set(raw_changes))
    ):
        raise OpenSeedV97Error(f"v97 raw public row boundary differs: {filename}")
    additions = selected_additions if selected_additions is not None else raw_additions
    projected = [*base_rows]
    projected.extend(row for row in current_rows if row[key] in additions)
    output[filename] = _csv_text(output[filename], projected)


def _project_public_rows(output: dict[str, str]) -> None:
    _project_keyed_csv(
        output,
        "entities.csv",
        key="stable_key",
        raw_additions=ADDED_ENTITY_KEYS,
        raw_changes=v96.EXPECTED_STALE_PROJECT_KEYS,
    )
    _project_keyed_csv(
        output,
        "evidence.csv",
        key="evidence_id",
        raw_additions=PUBLIC_EVIDENCE_IDS,
    )
    _project_keyed_csv(
        output,
        "lifecycle_freshness.csv",
        key="stable_key",
        raw_additions=ADDED_PROJECT_KEYS,
        allow_base_recomputation=True,
    )
    _project_keyed_csv(
        output,
        "construction_pipeline.csv",
        key="stable_key",
        raw_additions=ADDED_PROJECT_KEYS | v96.EXPECTED_STALE_PROJECT_KEYS,
        selected_additions=ADDED_PROJECT_KEYS,
    )
    _project_keyed_csv(
        output,
        "construction_source_signals.csv",
        key="source_observation_evidence_id",
        raw_additions=PUBLIC_EVIDENCE_IDS,
    )

    base_capacity = (BASE_RELEASE / "capacity_estimates.csv").read_bytes()
    if output["capacity_estimates.csv"].encode() != base_capacity:
        base_rows = _csv_rows(BASE_RELEASE / "capacity_estimates.csv")
        current_rows = list(
            csv.DictReader(io.StringIO(output["capacity_estimates.csv"]))
        )
        canonical = lambda row: json.dumps(  # noqa: E731
            row, sort_keys=True, separators=(",", ":")
        )
        if Counter(map(canonical, base_rows)) != Counter(map(canonical, current_rows)):
            raise OpenSeedV97Error("v97 public capacity rows changed")
        output["capacity_estimates.csv"] = _csv_text(
            output["capacity_estimates.csv"], base_rows
        )

    base_geojson = json.loads((BASE_RELEASE / "atlas.geojson").read_text())
    current_geojson = json.loads(output["atlas.geojson"])
    base_by_key = {
        row["properties"]["stable_key"]: row for row in base_geojson["features"]
    }
    current_by_key = {
        row["properties"]["stable_key"]: row for row in current_geojson["features"]
    }
    changed = {
        key
        for key in set(base_by_key) & set(current_by_key)
        if base_by_key[key] != current_by_key[key]
    }
    if (
        set(base_by_key) - set(current_by_key)
        or set(current_by_key) - set(base_by_key) != ADDED_ENTITY_KEYS
        or changed != v96.EXPECTED_STALE_PROJECT_KEYS
    ):
        raise OpenSeedV97Error("v97 raw GeoJSON boundary differs")
    current_geojson["features"] = [
        *base_geojson["features"],
        *(
            row
            for row in current_geojson["features"]
            if row["properties"]["stable_key"] in ADDED_ENTITY_KEYS
        ),
    ]
    output["atlas.geojson"] = _canonical(current_geojson, sort_keys=True).decode()

    base_sources = json.loads((BASE_RELEASE / "source_inputs.json").read_text())[
        "sources"
    ]
    current_sources = json.loads(output["source_inputs.json"])["sources"]
    canonical_source = lambda row: json.dumps(  # noqa: E731
        row, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    base_keys = {canonical_source(row) for row in base_sources}
    current_keys = {canonical_source(row) for row in current_sources}
    added_sources = [
        row for row in current_sources if canonical_source(row) not in base_keys
    ]
    if (
        base_keys - current_keys
        or len(current_sources) != 620
        or len(added_sources) != 3
        or {
            row.get("provenance", {}).get("curated_record_key") for row in added_sources
        }
        != {
            "ctrls-chandanvelly-building-page-modified-2026-07-21-captured-2026-07-22",
            "ctrls-pharmacity-building-page-modified-2026-07-21-captured-2026-07-22",
            "edgeconnex-lambda-chicago-build-2025-08-21",
        }
    ):
        raise OpenSeedV97Error("v97 public source-input boundary differs")
    output["source_inputs.json"] = _canonical(
        {"sources": [*base_sources, *added_sources]}, sort_keys=True
    ).decode()

    for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
        if output[filename].encode() != (BASE_RELEASE / filename).read_bytes():
            raise OpenSeedV97Error(f"v97 changed unrelated output: {filename}")


def _augment_release(documents: Mapping[str, str]) -> dict[str, str]:
    previous_as_of = v95.v85.AS_OF
    try:
        v95.v85.AS_OF = AS_OF
        output = v95.v94.v93.v92.v91._augment_release(dict(documents))
    finally:
        v95.v85.AS_OF = previous_as_of
    _project_public_rows(output)

    base_attribution = set((BASE_RELEASE / "ATTRIBUTION.txt").read_text().splitlines())
    current_attribution = set(output["ATTRIBUTION.txt"].splitlines())
    if (
        base_attribution - current_attribution
        or current_attribution - base_attribution != ATTRIBUTION_ADDITIONS
    ):
        raise OpenSeedV97Error("v97 attribution delta differs")
    output["README.md"] = (
        (BASE_RELEASE / "README.md").read_text().rstrip() + "\n\n" + V97_README
    )

    summary = json.loads(output["summary.json"])
    summary.update(
        {
            "entities_total": 1_053,
            "campuses_total": 545,
            "projects_total": 508,
            "evidence_total": 889,
            "lifecycle_observations_current": 583,
            "capacity_estimates_current": 570,
            "construction_pipeline_records": 531,
            "construction_source_signals": 432,
            "entities_with_coordinates": 215,
            "campuses_with_coordinates": 142,
        }
    )
    summary["entities_by_status"]["under_construction"] = 408
    summary["capacity_estimates_by_stage"]["design"] = 36
    summary["successor_projection"] = {
        "base_release_id": v96.RELEASE_ID,
        "base_rows_frozen": True,
        "governed_base_row_replacements": {},
        "curated_source_input_delta": 3,
        "curated_source_input_appends": 3,
        "curated_source_input_replacements": 0,
        "internal_database_delta": INTERNAL_DELTA,
        "public_release_delta": PUBLIC_DELTA,
        "stale_status_suppression": STALE_POLICY,
        "coordinate_boundary": COORDINATE_BOUNDARY,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    output["summary.json"] = _canonical(summary, sort_keys=True).decode()

    manifest = json.loads(output["manifest.json"])
    manifest.update(
        {
            "as_of": AS_OF,
            "entities": 1_053,
            "entities_by_kind": {"campus": 545, "project": 508},
            "evidence_records": 693,
            "lifecycle_freshness_records": 583,
            "capacity_estimates": 570,
            "construction_pipeline_records": 531,
            "construction_source_signals": 432,
            "append_only_base_release": v96.RELEASE_ID,
            "governed_successor_base_release": v96.RELEASE_ID,
            "base_rows_frozen": True,
            "unaffected_base_rows_frozen": True,
            "governed_base_row_replacements": {},
            "curated_source_input_delta": 3,
            "curated_source_input_appends": 3,
            "curated_source_input_replacements": 0,
            "internal_database_delta": INTERNAL_DELTA,
            "public_release_delta": PUBLIC_DELTA,
            "public_source_input_rows_delta": 3,
            "stale_status_suppression": STALE_POLICY,
            "coordinate_boundary": COORDINATE_BOUNDARY,
            "claim_boundary": CLAIM_BOUNDARY,
        }
    )
    for filename, text_value in output.items():
        if filename != "manifest.json":
            raw = text_value.encode()
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
            raise OpenSeedV97Error("precreated v97 release stage must be empty")
    else:
        output.mkdir(parents=True, exist_ok=False)
    if identity_tracker is not None:
        observed_root = ("directory", *_identity(output, directory=True))
        captured_root = identity_tracker.get(".")
        if captured_root is None:
            raise OpenSeedV97Error("v97 release root descriptor identity is missing")
        if observed_root != captured_root:
            raise OpenSeedV97Error("v97 release root identity changed before writing")
    documents = build_release_documents(
        connection,
        as_of=AS_OF,
        recorded_at=recorded_at,
        publication_contract_version=4,
    )
    for filename, text_value in _augment_release(documents).items():
        path = output / filename
        descriptor = os.open(
            path,
            os.O_CREAT
            | os.O_EXCL
            | os.O_WRONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        try:
            metadata = _fstat_identity_with_retry(
                descriptor,
                expected_kind="file",
                expected_mode=0o600,
                label=f"v97 release member {filename}",
            )
        except BaseException:
            os.close(descriptor)
            raise
        if identity_tracker is not None:
            identity_tracker[filename] = ("file", metadata[0], metadata[1])
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(text_value.encode())
            stream.flush()
            os.fsync(stream.fileno())


def _guard_state() -> dict[str, Any]:
    _validate_base()
    _validate_accepted_inputs()
    return {
        "base_definition": _pin(BASE_DEFINITION),
        "base_manifest": _pin(BASE_RELEASE / "manifest.json"),
        "base_entities": _pin(BASE_RELEASE / "entities.csv"),
        "base_source_inputs": _pin(BASE_RELEASE / "source_inputs.json"),
        "base_tree": v69.tree_digest(BASE_RELEASE),
        "artifact_manifests": {
            "ctrls": _pin(ctrls.ARTIFACT / "manifest.json"),
            "edgeconnex_lambda": _pin(edge.ARTIFACT / "manifest.json"),
        },
        "artifact_trees": {
            "ctrls": v69.tree_digest(ctrls.ARTIFACT),
            "edgeconnex_lambda": v69.tree_digest(edge.ARTIFACT),
        },
        "selected_sources": {
            relative: _pin(ROOT / relative) for relative in APPEND_ORDER
        },
        "selected_source_birth_mtimes": {
            relative: (
                _source_metadata(ROOT / relative)["birthtime"],
                _source_metadata(ROOT / relative)["mtime_ns"],
            )
            for relative in APPEND_ORDER
        },
    }


def _validate_guard(guard: Mapping[str, Any]) -> None:
    if (
        guard["base_definition"] != BASE_DEFINITION_PIN
        or guard["base_manifest"] != BASE_MANIFEST_PIN
        or guard["base_entities"] != BASE_ENTITIES_PIN
        or guard["base_source_inputs"] != BASE_SOURCE_INPUTS_PIN
        or guard["base_tree"] != BASE_TREE_SHA256
        or guard["artifact_manifests"]
        != {
            "ctrls": CTRL_ARTIFACT_MANIFEST_PIN,
            "edgeconnex_lambda": EDGE_ARTIFACT_MANIFEST_PIN,
        }
        or guard["artifact_trees"]
        != {
            "ctrls": CTRL_ARTIFACT_PHYSICAL_TREE_SHA256,
            "edgeconnex_lambda": EDGE_ARTIFACT_PHYSICAL_TREE_SHA256,
        }
        or guard["selected_sources"] != dict(SOURCE_PINS)
        or guard["selected_source_birth_mtimes"] != dict(SOURCE_BIRTH_MTIME_PINS)
    ):
        raise OpenSeedV97Error("v97 immutable-input guard differs")


def _public_key_delta(
    stage: Path, filename: str, *, key: str
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
    expectations = (
        ("entities.csv", "stable_key", ADDED_ENTITY_KEYS),
        ("evidence.csv", "evidence_id", PUBLIC_EVIDENCE_IDS),
        ("lifecycle_freshness.csv", "stable_key", ADDED_PROJECT_KEYS),
        ("construction_pipeline.csv", "stable_key", ADDED_PROJECT_KEYS),
        (
            "construction_source_signals.csv",
            "source_observation_evidence_id",
            PUBLIC_EVIDENCE_IDS,
        ),
    )
    for filename, key, expected_added in expectations:
        changed, removed, added = _public_key_delta(stage, filename, key=key)
        if changed or removed or added != set(expected_added):
            raise OpenSeedV97Error(f"v97 public delta differs: {filename}")
    if (stage / "capacity_estimates.csv").read_bytes() != (
        BASE_RELEASE / "capacity_estimates.csv"
    ).read_bytes():
        raise OpenSeedV97Error("v97 public capacity file changed")
    for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
        if (stage / filename).read_bytes() != (BASE_RELEASE / filename).read_bytes():
            raise OpenSeedV97Error(f"v97 unrelated output changed: {filename}")
    base_geojson = json.loads((BASE_RELEASE / "atlas.geojson").read_text())
    current_geojson = json.loads((stage / "atlas.geojson").read_text())
    base_by_key = {
        row["properties"]["stable_key"]: row for row in base_geojson["features"]
    }
    current_by_key = {
        row["properties"]["stable_key"]: row for row in current_geojson["features"]
    }
    if (
        set(base_by_key) - set(current_by_key)
        or set(current_by_key) - set(base_by_key) != ADDED_ENTITY_KEYS
        or any(current_by_key[key] != row for key, row in base_by_key.items())
    ):
        raise OpenSeedV97Error("v97 public GeoJSON delta differs")
    base_sources = json.loads((BASE_RELEASE / "source_inputs.json").read_text())[
        "sources"
    ]
    current_sources = json.loads((stage / "source_inputs.json").read_text())["sources"]
    if (
        current_sources[: len(base_sources)] != base_sources
        or len(current_sources) != 620
    ):
        raise OpenSeedV97Error("v97 public source-input rows differ")


def _validate_release_facts(stage: Path, *, recorded_at: str) -> dict[str, Any]:
    if stage.is_symlink() or not stage.is_dir():
        raise OpenSeedV97Error("v97 release stage is not an ordinary directory")
    entries = {path.name: path for path in stage.iterdir()}
    if len(entries) != 14 or any(
        path.is_symlink() or not path.is_file() for path in entries.values()
    ):
        raise OpenSeedV97Error("v97 release inventory differs")
    manifest = _read_json(stage / "manifest.json", sort_keys=True)
    if (
        manifest.get("as_of") != AS_OF
        or manifest.get("recorded_at") != recorded_at
        or manifest.get("publication_contract_version") != 4
        or manifest.get("entities") != 1_053
        or manifest.get("entities_by_kind") != {"campus": 545, "project": 508}
        or manifest.get("evidence_records") != 693
        or manifest.get("lifecycle_freshness_records") != 583
        or manifest.get("capacity_estimates") != 570
        or manifest.get("construction_pipeline_records") != 531
        or manifest.get("construction_source_signals") != 432
        or manifest.get("append_only_base_release") != v96.RELEASE_ID
        or manifest.get("governed_successor_base_release") != v96.RELEASE_ID
        or manifest.get("base_rows_frozen") is not True
        or manifest.get("unaffected_base_rows_frozen") is not True
        or manifest.get("governed_base_row_replacements") != {}
        or manifest.get("curated_source_input_delta") != 3
        or manifest.get("curated_source_input_appends") != 3
        or manifest.get("curated_source_input_replacements") != 0
        or manifest.get("internal_database_delta") != INTERNAL_DELTA
        or manifest.get("public_release_delta") != PUBLIC_DELTA
        or manifest.get("public_source_input_rows_delta") != 3
        or manifest.get("stale_status_suppression") != STALE_POLICY
        or manifest.get("coordinate_boundary") != COORDINATE_BOUNDARY
        or manifest.get("claim_boundary") != CLAIM_BOUNDARY
        or set(entries) != set(manifest.get("files", {})) | {"manifest.json"}
    ):
        raise OpenSeedV97Error("v97 manifest facts differ")
    for filename, row in manifest["files"].items():
        if _pin(entries[filename]) != (row["bytes"], row["sha256"]):
            raise OpenSeedV97Error(f"v97 release pin differs: {filename}")
    _validate_public_delta(stage)

    entities = {row["stable_key"]: row for row in _csv_rows(stage / "entities.csv")}
    for key in v96.EXPECTED_STALE_PROJECT_KEYS:
        if any(entities[key][field] for field in v95.STATUS_FIELDS):
            raise OpenSeedV97Error(f"v97 stale status persisted: {key}")
    for key in ADDED_ENTITY_KEYS:
        row = entities[key]
        if row["latitude"] or row["longitude"] or row["geometry_json"] != "null":
            raise OpenSeedV97Error(f"v97 unexpected public coordinate: {key}")
        if key in {
            ctrls.CHANDANVELLY_PROJECT_KEY,
            ctrls.PHARMACITY_PROJECT_KEY,
        } and (
            row["operating_model"]
            or row["workloads_json"] != "[]"
            or row["capacity_estimates_json"] != "[]"
        ):
            raise OpenSeedV97Error("CtrlS acquired an unsupported public type")
    edge_row = entities[edge.PROJECT_KEY]
    edge_workloads = json.loads(edge_row["workloads_json"])
    if (
        edge_row["operating_model"]
        or [row.get("workload") for row in edge_workloads]
        != ["ai_inference", "ai_training", "hpc"]
        or any(
            row.get("as_of_date") != "2025-08-21"
            or row.get("method") != "company_disclosure"
            or row.get("evidence_id") != "ba4efcbb-a21b-50f2-9be9-b324ce23adea"
            for row in edge_workloads
        )
        or edge_row["capacity_estimates_json"] != "[]"
    ):
        raise OpenSeedV97Error("EdgeConneX/Lambda public claim boundary differs")
    pipeline = {
        row["stable_key"] for row in _csv_rows(stage / "construction_pipeline.csv")
    }
    if pipeline & v96.EXPECTED_STALE_PROJECT_KEYS or not ADDED_PROJECT_KEYS <= pipeline:
        raise OpenSeedV97Error("v97 pipeline stale/new boundary differs")

    summary = _read_json(stage / "summary.json", sort_keys=True)
    projection = summary.get("successor_projection")
    if (
        summary.get("entities_total") != 1_053
        or summary.get("campuses_total") != 545
        or summary.get("projects_total") != 508
        or summary.get("evidence_total") != 889
        or summary.get("lifecycle_observations_current") != 583
        or summary.get("capacity_estimates_current") != 570
        or summary.get("construction_pipeline_records") != 531
        or summary.get("construction_source_signals") != 432
        or summary.get("entities_with_coordinates") != 215
        or summary.get("campuses_with_coordinates") != 142
        or summary.get("entities_by_status", {}).get("under_construction") != 408
        or summary.get("capacity_estimates_by_stage", {}).get("design") != 36
        or not isinstance(projection, dict)
        or projection.get("base_release_id") != v96.RELEASE_ID
        or projection.get("base_rows_frozen") is not True
        or projection.get("internal_database_delta") != INTERNAL_DELTA
        or projection.get("public_release_delta") != PUBLIC_DELTA
        or projection.get("stale_status_suppression") != STALE_POLICY
        or projection.get("coordinate_boundary") != COORDINATE_BOUNDARY
        or projection.get("claim_boundary") != CLAIM_BOUNDARY
    ):
        raise OpenSeedV97Error("v97 summary contract differs")
    readme = (stage / "README.md").read_text(encoding="utf-8")
    for marker in (
        "Open seed v97 is the exact append-only successor",
        "Every v96 public row is retained",
        "no normalized data-center type",
        "reported 23 MW remains untyped source metadata",
        "Jakarta, Hanoi, and Oran",
    ):
        if marker not in readme:
            raise OpenSeedV97Error(f"v97 README guardrail differs: {marker}")
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
    document["freshness_contract"] = dict(base["freshness_contract"])
    document["release_id"] = RELEASE_ID
    return document


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
    target = v95.v70.parse_utc(recorded_at, label="v97 recorded_at")
    paths = [definition, release, *_release_descendants(release)]
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        birth = getattr(metadata, "st_birthtime", metadata.st_mtime)
        if max(birth, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV97Error(
                f"v97 inode birth/mtime post-dates recorded_at: {path}"
            )
    if require_live:
        if datetime.now(UTC) < target:
            raise OpenSeedV97Error("v97 recorded_at is not live")
        for path in paths:
            if path.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
                raise OpenSeedV97Error(
                    f"v97 recursive ctime predates recorded_at: {path}"
                )


def validate_open_seed_v97(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
    require_live: bool = True,
) -> dict[str, Any]:
    if replay_count != 2:
        raise OpenSeedV97Error("v97 requires exactly two offline replays")
    guard = _guard_state()
    _validate_guard(guard)
    base = _validate_base()
    definition = _read_json(
        definition_path,
        mode=0o444 if require_frozen else None,
        sort_keys=True,
    )
    if set(definition) != set(base) or definition.get("release_id") != RELEASE_ID:
        raise OpenSeedV97Error("v97 definition identity differs")
    build = definition.get("build")
    if (
        not isinstance(build, dict)
        or set(build) != {"as_of", "recorded_at"}
        or build.get("as_of") != AS_OF
    ):
        raise OpenSeedV97Error("v97 definition build carrier differs")
    wall = validation_wall_clock or datetime.now(UTC)
    selected, paths = selected_inputs(
        base, recorded_at=build["recorded_at"], validation_wall_clock=wall
    )
    if definition.get("curated_inputs") != selected:
        raise OpenSeedV97Error("v97 definition selected inputs differ")
    if definition.get("freshness_contract") != base.get("freshness_contract"):
        raise OpenSeedV97Error("v97 changed the v96 freshness contract")

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
        raise OpenSeedV97Error("v97 staged release is not frozen")
    manifest = _validate_release_facts(release_path, recorded_at=build["recorded_at"])
    manifest_raw = (release_path / "manifest.json").read_bytes()
    if _sha256(manifest_raw) != definition["expected_release"]["manifest_sha256"]:
        raise OpenSeedV97Error("v97 expected manifest hash differs")
    if {key: value for key, value in manifest.items() if key != "files"} != {
        key: value
        for key, value in definition["expected_release"].items()
        if key != "manifest_sha256"
    }:
        raise OpenSeedV97Error("v97 expected release facts differ")
    summary = json.loads((release_path / "summary.json").read_text())
    if {key: summary[key] for key in definition["expected_summary"]} != definition[
        "expected_summary"
    ]:
        raise OpenSeedV97Error("v97 expected summary differs")
    _validate_publication_times(
        definition_path,
        release_path,
        recorded_at=build["recorded_at"],
        require_live=require_live,
    )

    replay_digests: list[str] = []
    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v97-replay-{replay + 1}-", dir="/private/tmp"
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
            _validate_release_facts(replay_release, recorded_at=build["recorded_at"])
            for filename in set(manifest["files"]) | {"manifest.json"}:
                if (replay_release / filename).read_bytes() != (
                    release_path / filename
                ).read_bytes():
                    raise OpenSeedV97Error(f"v97 offline replay differs: {filename}")
            replay_digests.append(
                _sha256((replay_release / "manifest.json").read_bytes())
            )
    replay_digest = _two_replay_gate(replay_digests)
    if replay_digest != _sha256((release_path / "manifest.json").read_bytes()):
        raise OpenSeedV97Error("v97 staged manifest differs from replays")
    if _guard_state() != guard:
        raise OpenSeedV97Error("v97 validation mutated accepted inputs")
    return {**manifest, "two_replay_manifest_sha256": replay_digest}


def validate_staged_open_seed_v97(
    definition_path: Path,
    release_path: Path,
    *,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
) -> dict[str, Any]:
    return validate_open_seed_v97(
        definition_path,
        release_path,
        require_frozen=True,
        replay_count=replay_count,
        validation_wall_clock=validation_wall_clock,
        require_live=False,
    )


def _identity(path: Path, *, directory: bool) -> tuple[int, int]:
    if path.is_symlink():
        raise OpenSeedV97Error(f"symlinked promotion member: {path}")
    metadata = path.stat(follow_symlinks=False)
    if directory and not stat.S_ISDIR(metadata.st_mode):
        raise OpenSeedV97Error(f"promotion member is not a directory: {path}")
    if not directory and not stat.S_ISREG(metadata.st_mode):
        raise OpenSeedV97Error(f"promotion member is not a file: {path}")
    return metadata.st_dev, metadata.st_ino


def _fstat_identity_with_retry(
    descriptor: int,
    *,
    expected_kind: str,
    label: str,
    expected_mode: int | None = None,
    attempts: int = 2,
) -> tuple[int, int, str]:
    if attempts < 1:
        raise ValueError("identity attempts must be positive")
    last_error: OSError | None = None
    for _attempt in range(attempts):
        try:
            metadata = os.fstat(descriptor)
        except OSError as error:
            last_error = error
            continue
        actual_kind = (
            "directory"
            if stat.S_ISDIR(metadata.st_mode)
            else "file"
            if stat.S_ISREG(metadata.st_mode)
            else "other"
        )
        if actual_kind != expected_kind:
            raise OpenSeedV97Error(
                f"{label} is not an owned {expected_kind}; retained fail-closed"
            )
        if (
            expected_mode is not None
            and stat.S_IMODE(metadata.st_mode) != expected_mode
        ):
            raise OpenSeedV97Error(f"{label} mode differs; retained fail-closed")
        return metadata.st_dev, metadata.st_ino, actual_kind
    raise OpenSeedV97Error(
        f"{label} identity unavailable after {attempts} attempts; retained fail-closed"
    ) from last_error


def _has_identity(path: Path, identity: tuple[int, int], *, directory: bool) -> bool:
    try:
        return _identity(path, directory=directory) == identity
    except (FileNotFoundError, OpenSeedV97Error):
        return False


def _promote_noreplace(
    stage: Path, destination: Path, *, directory: bool
) -> tuple[int, int]:
    identity = _identity(stage, directory=directory)
    if stage.stat().st_dev != destination.parent.stat().st_dev:
        raise OpenSeedV97Error("v97 promotion crosses filesystems")
    try:
        v69.promote_noreplace(stage, destination)
    except SystemExit as error:
        raise OpenSeedV97Error(str(error)) from error
    if not _has_identity(destination, identity, directory=directory):
        raise OpenSeedV97Error("v97 promoted identity differs")
    return identity


def _rollback_noreplace(
    destination: Path,
    stage: Path,
    identity: tuple[int, int],
    *,
    directory: bool,
) -> None:
    if not _has_identity(destination, identity, directory=directory):
        raise OpenSeedV97Error("v97 refuses identity-mismatched rollback")
    _promote_noreplace(destination, stage, directory=directory)
    if not _has_identity(stage, identity, directory=directory):
        raise OpenSeedV97Error("v97 rollback identity differs")


def _tree_identities(root: Path) -> dict[str, tuple[str, int, int]]:
    identities: dict[str, tuple[str, int, int]] = {}
    for path in [root, *_release_descendants(root)]:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise OpenSeedV97Error(f"v97 tree contains symlink: {relative}")
        metadata = path.stat(follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            kind = "directory"
        elif stat.S_ISREG(metadata.st_mode):
            kind = "file"
        else:
            raise OpenSeedV97Error(f"v97 tree contains special member: {relative}")
        identities[relative] = (kind, metadata.st_dev, metadata.st_ino)
    return identities


def _assert_tree_identities(
    root: Path, expected: Mapping[str, tuple[str, int, int]]
) -> None:
    if _tree_identities(root) != dict(expected):
        raise OpenSeedV97Error("v97 recursive tree identity changed")


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
        raise OpenSeedV97Error("refusing substituted v97 definition cleanup")
    path.chmod(0o600)
    path.unlink()


def _create_owned_release_stage() -> tuple[Path, dict[str, tuple[str, int, int]]]:
    """Create a same-parent stage and capture its root only through an open fd.

    If descriptor identity cannot be captured after the required retry, the
    unknown path is deliberately retained.  It is never rediscovered or
    adopted for cleanup.
    """

    stage = Path(tempfile.mkdtemp(prefix=f".{RELEASE.name}.", dir=RELEASE.parent))
    descriptor: int | None = None
    identity: tuple[int, int] | None = None
    try:
        descriptor = os.open(
            stage,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        metadata = _fstat_identity_with_retry(
            descriptor,
            expected_kind="directory",
            expected_mode=0o700,
            label="v97 release stage root",
        )
        identity = metadata[:2]
        if not _has_identity(stage, identity, directory=True):
            raise OpenSeedV97Error(
                "v97 release stage path differs from creation descriptor; retained fail-closed"
            )
        return stage, {".": ("directory", *identity)}
    except BaseException as error:
        if identity is not None and _has_identity(stage, identity, directory=True):
            try:
                _discard_release_stage(stage, {".": ("directory", *identity)})
            except Exception as cleanup_error:
                error.add_note(f"v97 owned root cleanup failed: {cleanup_error}")
        else:
            error.add_note(f"v97 unknown release stage retained fail-closed: {stage}")
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK,
            os.O_CREAT
            | os.O_EXCL
            | os.O_WRONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
    except FileExistsError as error:
        raise OpenSeedV97Error("active v97 publication lock exists") from error
    identity: tuple[int, int] | None = None
    try:
        identity = _fstat_identity_with_retry(
            descriptor,
            expected_kind="file",
            expected_mode=0o600,
            label="v97 publication lock",
        )[:2]
        payload = f"pid={os.getpid()}\n".encode("ascii")
        if os.write(descriptor, payload) != len(payload):
            raise OpenSeedV97Error("short v97 publication-lock write")
        os.fsync(descriptor)
        yield
    finally:
        try:
            os.close(descriptor)
        finally:
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
                        raise OpenSeedV97Error(
                            "refusing substituted v97 publication-lock cleanup"
                        )
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
        raise OpenSeedV97Error(f"{label} v97 definition collision")
    if RELEASE.exists() or RELEASE.is_symlink():
        raise OpenSeedV97Error(f"{label} v97 release collision")


def _rollback_release(
    release_identity: tuple[int, int],
    release_identities: Mapping[str, tuple[str, int, int]],
    stage: Path,
) -> None:
    if _identity(RELEASE, directory=True) != release_identity:
        raise OpenSeedV97Error("refusing rollback of substituted v97 release")
    _assert_tree_identities(RELEASE, release_identities)
    if stage.exists() or stage.is_symlink():
        raise OpenSeedV97Error("v97 release rollback stage is occupied")
    _promote_noreplace(RELEASE, stage, directory=True)
    _assert_tree_identities(stage, release_identities)


def _rollback_definition(definition_identity: tuple[int, int], stage: Path) -> None:
    if _identity(DEFINITION, directory=False) != definition_identity:
        raise OpenSeedV97Error("refusing rollback of substituted v97 definition")
    if stage.exists() or stage.is_symlink():
        raise OpenSeedV97Error("v97 definition rollback stage is occupied")
    _promote_noreplace(DEFINITION, stage, directory=False)


def _private_promotion_roundtrip(definition: Path, release: Path, root: Path) -> None:
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
            raise OpenSeedV97Error("v97 private definition identity changed")
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
                promoted_release, release, release_identity, directory=True
            )
            _assert_tree_identities(release, release_identities)
        except Exception as error:
            rollback_errors.append(error)
    if operation_error is not None:
        for error in rollback_errors:
            operation_error.add_note(f"v97 private rollback failed: {error}")
        raise operation_error
    if rollback_errors:
        primary = rollback_errors[0]
        for error in rollback_errors[1:]:
            primary.add_note(f"additional v97 private rollback failure: {error}")
        raise primary
    if promoted_definition.exists() or promoted_release.exists():
        raise OpenSeedV97Error("v97 private promotion roundtrip left residue")


def _two_replay_gate(digests: Sequence[str]) -> str:
    if len(digests) != 2 or not all(
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
        for value in digests
    ):
        raise OpenSeedV97Error("v97 requires exactly two replay digests")
    if digests[0] != digests[1]:
        raise OpenSeedV97Error("v97 replay digests differ")
    return digests[0]


def _assert_final_absent() -> None:
    present = [
        str(path)
        for path in (DEFINITION, RELEASE, PUBLICATION_LOCK)
        if path.exists() or path.is_symlink()
    ]
    if present:
        raise OpenSeedV97Error(f"v97 final path collision: {present!r}")


def prepare_open_seed_v97(
    recorded_at: str | None = None, *, replay_count: int = 2
) -> dict[str, Any]:
    """Build, freeze, replay, validate, roundtrip, and discard a private stage."""

    _assert_final_absent()
    if replay_count != 2:
        raise OpenSeedV97Error("v97 requires exactly two offline replays")
    report = readiness_report()
    target = (
        v95.v70.parse_utc(recorded_at, label="v97 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=90)
    )
    if target <= datetime.now(UTC):
        raise OpenSeedV97Error("v97 prepublication recorded_at must be future")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    guard = _guard_state()
    _validate_guard(guard)
    base = _validate_base()
    selected, paths = selected_inputs(
        base, recorded_at=timestamp, validation_wall_clock=target
    )
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v97-prepublication-", dir="/private/tmp"
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
            manifest = validate_staged_open_seed_v97(
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
                raise OpenSeedV97Error("v97 private bytes changed during roundtrip")
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
                "internal_evidence_records": EXPECTED_DATABASE_COUNTS["evidence"],
                "lifecycle_freshness_records": manifest["lifecycle_freshness_records"],
                "capacity_estimates": manifest["capacity_estimates"],
                "construction_pipeline_records": manifest[
                    "construction_pipeline_records"
                ],
                "construction_source_signals": manifest["construction_source_signals"],
                "source_input_rows": 620,
                "private_no_replace_roundtrip_validated": True,
                "final_definition_absent": not DEFINITION.exists(),
                "final_release_absent": not RELEASE.exists(),
                "publication_lock_absent": not PUBLICATION_LOCK.exists(),
                "readiness": report["status"],
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
        raise OpenSeedV97Error("v97 prepublication left residue or mutated inputs")
    return result


def _existing_identical(recorded_at: str | None) -> dict[str, Any]:
    definition = _read_json(DEFINITION, mode=0o444, sort_keys=True)
    existing_recorded_at = definition.get("build", {}).get("recorded_at")
    if not isinstance(existing_recorded_at, str):
        raise OpenSeedV97Error("existing v97 recorded_at is missing")
    if recorded_at is not None and recorded_at != existing_recorded_at:
        raise OpenSeedV97Error("existing v97 recorded_at differs")
    manifest = validate_open_seed_v97(DEFINITION, RELEASE)
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


def build_open_seed_v97(
    recorded_at: str | None = None, *, publication_authorized: bool = False
) -> dict[str, Any]:
    """Publish only after explicit authorization and every governed gate."""

    if not publication_authorized:
        raise OpenSeedV97Error("v97 publication requires explicit authorization")
    definition_present = DEFINITION.exists() or DEFINITION.is_symlink()
    release_present = RELEASE.exists() or RELEASE.is_symlink()
    if definition_present and release_present:
        return _existing_identical(recorded_at)
    if definition_present or release_present:
        raise OpenSeedV97Error("partial v97 final-path collision")
    target = (
        v95.v70.parse_utc(recorded_at, label="v97 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=90)
    )
    if datetime.now(UTC) >= target:
        raise OpenSeedV97Error("v97 recorded_at must be future before staging")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    guard = _guard_state()
    _validate_guard(guard)

    with _publication_lock():
        _require_final_absent("initial")
        release_stage, release_identities = _create_owned_release_stage()
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
            metadata = _fstat_identity_with_retry(
                descriptor,
                expected_kind="file",
                expected_mode=0o600,
                label="v97 definition stage",
            )
            definition_identity = metadata[:2]
            if _identity(definition_stage, directory=False) != definition_identity:
                raise OpenSeedV97Error("v97 definition stage identity differs")
            os.close(descriptor)
            descriptor_open = False
            base = _validate_base()
            selected, paths = selected_inputs(
                base, recorded_at=timestamp, validation_wall_clock=target
            )
            with tempfile.TemporaryDirectory(
                prefix="open-seed-v97-db-", dir="/private/tmp"
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
                raise OpenSeedV97Error("v97 release stage identities differ")
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
            validate_staged_open_seed_v97(
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
                raise OpenSeedV97Error("v97 definition stage identity changed")
            _assert_tree_identities(release_stage, release_identities)
            if (
                definition_stage.read_bytes() != frozen_definition
                or v69.tree_digest(release_stage) != frozen_tree
            ):
                raise OpenSeedV97Error("v97 private stage changed while waiting")
            _refresh_publication_ctimes(definition_stage, release_stage)
            if _identity(definition_stage, directory=False) != definition_identity:
                raise OpenSeedV97Error("v97 refreshed definition identity changed")
            _assert_tree_identities(release_stage, release_identities)
            if (
                definition_stage.read_bytes() != frozen_definition
                or v69.tree_digest(release_stage) != frozen_tree
            ):
                raise OpenSeedV97Error("v97 private bytes changed at publication")
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
                    raise OpenSeedV97Error("v97 definition promotion identity differs")
            except BaseException as error:
                if DEFINITION.exists() or DEFINITION.is_symlink():
                    try:
                        _rollback_definition(definition_identity, definition_stage)
                        published_definition = False
                    except Exception as rollback_error:
                        error.add_note(
                            f"v97 definition rollback failed: {rollback_error}"
                        )
                try:
                    _rollback_release(
                        release_identity, release_identities, release_stage
                    )
                    published_release = False
                except Exception as rollback_error:
                    error.add_note(f"v97 release rollback failed: {rollback_error}")
                raise
            try:
                manifest = validate_open_seed_v97(DEFINITION, RELEASE)
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
                    error.add_note(f"v97 rollback failed: {rollback_error}")
                raise
        finally:
            active_error = sys.exception()
            cleanup_errors: list[Exception] = []
            if descriptor_open:
                try:
                    os.close(descriptor)
                except Exception as error:
                    cleanup_errors.append(error)
            if not published_release and (
                release_stage.exists() or release_stage.is_symlink()
            ):
                try:
                    _discard_release_stage(release_stage, release_identities)
                except Exception as error:
                    cleanup_errors.append(error)
            if (
                not published_definition
                and (definition_stage.exists() or definition_stage.is_symlink())
                and definition_identity is not None
            ):
                try:
                    _discard_file_stage(definition_stage, definition_identity)
                except Exception as error:
                    cleanup_errors.append(error)
            if cleanup_errors:
                if active_error is not None:
                    for error in cleanup_errors:
                        active_error.add_note(f"v97 cleanup failed: {error}")
                else:
                    primary = cleanup_errors[0]
                    for error in cleanup_errors[1:]:
                        primary.add_note(f"additional v97 cleanup failed: {error}")
                    raise primary
    if _guard_state() != guard:
        raise OpenSeedV97Error("v97 publication mutated accepted inputs")
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
        build_open_seed_v97(publication_authorized=True)
        if publication_authorized
        else prepare_open_seed_v97()
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
