"""Authorization-gated accepted publisher for the reviewed NXDATA-3 record.

The module is deliberately offline.  It accepts one reviewed NXDATA-3 / BUH3
successor, retains PORR and Data4 only as review dispositions, and never treats
publisher imagery as construction truth.  Exact reviewed stages, the private
raw-capture tree, and the existing source predecessor are immutable inputs.

``preflight`` is the safe default: it renders the exact accepted bytes in
unique same-filesystem sibling stages, imports the source twice, freezes and
validates the stages, reports their pins, and identity-safely discards them.
Only ``build(publication_authorized=True)`` can cross the future live barrier
and attempt atomic no-replace promotion.
"""

from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping

from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .official_cee_nxdata_gap_prepublication_20260722 import (
    CAPTURE_FILE_PINS as _REVIEWED_CAPTURE_FILE_PINS,
)
from .open_seed_v56 import tree_digest
from .open_seed_v69 import promote_noreplace
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"

ARTIFACT_ID = "official-nxdata3-current-build-2026-07-22-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".official-nxdata3-current-build.lock"

SOURCE_FILENAME = (
    "curated-official-2026-07-22-nxdata3-bucharest-current-build-successor.json"
)
SOURCE_FILENAMES = (SOURCE_FILENAME,)

REVIEWED_CANDIDATE_ID = "official-cee-nxdata-gap-prepublication-2026-07-22-v1"
REVIEWED_RECORDED_AT = "2026-07-22T04:42:28Z"
REVIEWED_SOURCE_STAGE = (
    SOURCES_ROOT / ".official-cee-nxdata-gap-prepublication-sources.mbt1fsun"
)
REVIEWED_ARTIFACT_STAGE = (
    ARTIFACT_ROOT / ".official-cee-nxdata-gap-prepublication-2026-07-22-v1.0g8g_vx3"
)
RAW_CAPTURE = Path("/Users/kian/.Trash/dc-cee-nxdata-gap-accepted-20260722")

REVIEWED_SOURCE_TREE_SHA256 = (
    "38448590b830b39cd160aacfa22c0e580ecb5586c73e29dbe28f048f252f9d93"
)
REVIEWED_ARTIFACT_TREE_SHA256 = (
    "cc91c0583cc0737b1bf3db7c06a4b90a83251e30dc4c00ccd28e9a62ea51a758"
)
RAW_CAPTURE_TREE_SHA256 = (
    "8db499d1e4117920eb3109bafd0be5ce45089a90b2322045542e9392329de8d2"
)

REVIEWED_SOURCE_PINS: Mapping[str, tuple[int, str]] = {
    SOURCE_FILENAME: (
        13_898,
        "be09d4ae8050effcdc1c8c987a4deebb8010d2d1a2ba8b0d657c59e88c882fd5",
    )
}
REVIEWED_ARTIFACT_PINS: Mapping[str, tuple[int, str]] = {
    "README.md": (
        1_758,
        "88b77698c2a4ebe3802ecc0c7f028aae8d9cd61973d80883487c5e7b8cb1d9dc",
    ),
    "candidate-assessment.json": (
        3_861,
        "a368c11f92945b5a2ba8b77a349274f171797ad6ab33bd037a4d3f20cfbdd713",
    ),
    "manifest.json": (
        1_593,
        "997146d4ecc0c23c0a51a13623a0d228b5d15044086f3b8bc40936a74d4a960a",
    ),
    "manifest.sha256": (
        80,
        "b0f78e9ecc6da6451264a0bd5967309a3f479bd4ae242bc82aaacbefdf6e7f8c",
    ),
    "retrieval-inventory.json": (
        16_882,
        "3d49b7659c424d3acccaefe179f20c62191d98d832ced02079d9ae413360ea0e",
    ),
    "rights-and-disposition.json": (
        1_087,
        "6488325a3b0f821dc1e4e441065f6a2257bba27a80e815e1e45a165627d6f908",
    ),
    "source-snapshot.json": (
        4_095,
        "3cec7cd374a6ab6d4e1bf0b42c00c05319d4f2828bb30522c14b0e871e584e37",
    ),
}
RAW_CAPTURE_PINS: Mapping[str, tuple[int, str]] = dict(_REVIEWED_CAPTURE_FILE_PINS)

PREDECESSOR_FILENAME = (
    "curated-official-2026-07-21-nxdata3-bucharest-source-scoped.json"
)
PREDECESSOR = SOURCES_ROOT / PREDECESSOR_FILENAME
PREDECESSOR_PIN = (
    5_945,
    "5f99c454a53c26cb9c0f01cade1e90baabe2c7b86ddf1dcf7002360fad33b1c4",
)
PREDECESSOR_MODE = 0o644

CAMPUS_KEY = "curated:nxdata3-bucharest-ring-road-campus"
PROJECT_KEY = f"{CAMPUS_KEY}:nxdata3-buh3"

CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))


class NXDataPublicationError(RuntimeError):
    """Fail-closed NXDATA-3 publication error."""


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _content_tree_sha256(root: Path) -> str:
    rows = [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat(follow_symlinks=False).st_size,
            "sha256": _sha256(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    ]
    return _sha256_bytes(_canonical(rows))


def _instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise NXDataPublicationError("recorded_at must be ISO 8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise NXDataPublicationError("recorded_at must be timezone aware")
    return parsed.astimezone(UTC)


def _pin(path: Path, expected: tuple[int, str], *, mode: int) -> None:
    if path.is_symlink() or not path.is_file():
        raise NXDataPublicationError(f"missing or unsafe pinned input: {path}")
    metadata = path.stat(follow_symlinks=False)
    if (metadata.st_size, _sha256(path)) != expected:
        raise NXDataPublicationError(f"pinned input differs: {path}")
    if stat.S_IMODE(metadata.st_mode) != mode:
        raise NXDataPublicationError(f"pinned input mode differs: {path}")


def _fsync_regular(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _identity(path: Path, *, directory: bool | None = None) -> tuple[int, int]:
    if path.is_symlink():
        raise NXDataPublicationError(f"symlink is not allowed: {path}")
    metadata = path.stat(follow_symlinks=False)
    if directory is True and not stat.S_ISDIR(metadata.st_mode):
        raise NXDataPublicationError(f"expected directory: {path}")
    if directory is False and not stat.S_ISREG(metadata.st_mode):
        raise NXDataPublicationError(f"expected regular file: {path}")
    return metadata.st_dev, metadata.st_ino


def _has_identity(
    path: Path, expected: tuple[int, int], *, directory: bool | None = None
) -> bool:
    try:
        return _identity(path, directory=directory) == expected
    except (FileNotFoundError, NXDataPublicationError):
        return False


def _tree_identities(root: Path) -> dict[str, tuple[int, int, str]]:
    if root.is_symlink() or not root.is_dir():
        raise NXDataPublicationError(f"unsafe tree root: {root}")
    result: dict[str, tuple[int, int, str]] = {}
    for candidate in (root, *sorted(root.rglob("*"))):
        if candidate.is_symlink():
            raise NXDataPublicationError(f"symlink in governed tree: {candidate}")
        metadata = candidate.stat(follow_symlinks=False)
        kind = (
            "directory"
            if stat.S_ISDIR(metadata.st_mode)
            else "file"
            if stat.S_ISREG(metadata.st_mode)
            else "other"
        )
        if kind == "other":
            raise NXDataPublicationError(f"special file in governed tree: {candidate}")
        relative = "." if candidate == root else candidate.relative_to(root).as_posix()
        result[relative] = (metadata.st_dev, metadata.st_ino, kind)
    return result


def _assert_tree_identities(
    root: Path, expected: Mapping[str, tuple[int, int, str]]
) -> None:
    if _tree_identities(root) != dict(expected):
        raise NXDataPublicationError(f"tree identity changed: {root}")


@dataclass(frozen=True)
class ReviewedInputIdentities:
    sources: Mapping[str, tuple[int, int, str]]
    artifact: Mapping[str, tuple[int, int, str]]
    captures: Mapping[str, tuple[int, int, str]]
    predecessor: tuple[int, int]


def _validate_governed_tree(
    root: Path,
    pins: Mapping[str, tuple[int, str]],
    *,
    directory_mode: int,
    file_mode: int,
    tree_sha256: str,
    label: str,
) -> None:
    if (
        root.is_symlink()
        or not root.is_dir()
        or stat.S_IMODE(root.stat(follow_symlinks=False).st_mode) != directory_mode
    ):
        raise NXDataPublicationError(f"{label} is missing or unsafe")
    entries = {path.name: path for path in root.iterdir()}
    if set(entries) != set(pins):
        raise NXDataPublicationError(f"{label} inventory differs")
    for name, pin in pins.items():
        _pin(entries[name], pin, mode=file_mode)
    if tree_digest(root) != tree_sha256:
        raise NXDataPublicationError(f"{label} tree differs")


def _validate_reviewed_inputs() -> ReviewedInputIdentities:
    _validate_governed_tree(
        REVIEWED_SOURCE_STAGE,
        REVIEWED_SOURCE_PINS,
        directory_mode=0o700,
        file_mode=0o600,
        tree_sha256=REVIEWED_SOURCE_TREE_SHA256,
        label="reviewed source stage",
    )
    _validate_governed_tree(
        REVIEWED_ARTIFACT_STAGE,
        REVIEWED_ARTIFACT_PINS,
        directory_mode=0o700,
        file_mode=0o600,
        tree_sha256=REVIEWED_ARTIFACT_TREE_SHA256,
        label="reviewed artifact stage",
    )
    _validate_governed_tree(
        RAW_CAPTURE,
        RAW_CAPTURE_PINS,
        directory_mode=0o555,
        file_mode=0o444,
        tree_sha256=RAW_CAPTURE_TREE_SHA256,
        label="raw capture bundle",
    )
    _pin(PREDECESSOR, PREDECESSOR_PIN, mode=PREDECESSOR_MODE)

    manifest = json.loads(
        (REVIEWED_ARTIFACT_STAGE / "manifest.json").read_text(encoding="utf-8")
    )
    if (
        manifest.get("artifact_id") != REVIEWED_CANDIDATE_ID
        or manifest.get("recorded_at") != REVIEWED_RECORDED_AT
        or manifest.get("published") is not False
        or manifest.get("publisher_function_present") is not False
    ):
        raise NXDataPublicationError("reviewed candidate manifest differs")
    if (REVIEWED_ARTIFACT_STAGE / "manifest.sha256").read_text(encoding="utf-8") != (
        f"{REVIEWED_ARTIFACT_PINS['manifest.json'][1]}  manifest.json\n"
    ):
        raise NXDataPublicationError("reviewed candidate checksum differs")

    reviewed = json.loads(
        (REVIEWED_SOURCE_STAGE / SOURCE_FILENAME).read_text(encoding="utf-8")
    )
    predecessor = json.loads(PREDECESSOR.read_text(encoding="utf-8"))
    for document, label in ((reviewed, "reviewed"), (predecessor, "predecessor")):
        if (
            document.get("schema_version") != "1.1"
            or document.get("campus", {}).get("stable_key") != CAMPUS_KEY
            or document.get("project", {}).get("stable_key") != PROJECT_KEY
        ):
            raise NXDataPublicationError(f"{label} stable identity differs")

    identities = ReviewedInputIdentities(
        _tree_identities(REVIEWED_SOURCE_STAGE),
        _tree_identities(REVIEWED_ARTIFACT_STAGE),
        _tree_identities(RAW_CAPTURE),
        _identity(PREDECESSOR, directory=False),
    )
    _assert_reviewed_input_identities(identities)
    return identities


def _assert_reviewed_input_identities(identities: ReviewedInputIdentities) -> None:
    _assert_tree_identities(REVIEWED_SOURCE_STAGE, identities.sources)
    _assert_tree_identities(REVIEWED_ARTIFACT_STAGE, identities.artifact)
    _assert_tree_identities(RAW_CAPTURE, identities.captures)
    if not _has_identity(PREDECESSOR, identities.predecessor, directory=False):
        raise NXDataPublicationError("predecessor identity changed")
    _pin(PREDECESSOR, PREDECESSOR_PIN, mode=PREDECESSOR_MODE)


def _walk_strings(
    value: Any, path: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_strings(item, (*path, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_strings(item, (*path, str(index)))


def _assert_publication_clean(value: Any) -> None:
    private_path = str(RAW_CAPTURE).lower()
    for path, text in _walk_strings(value):
        lowered = text.lower()
        if "prospective-sources/" in lowered:
            raise NXDataPublicationError(f"prospective source path leaked at {path!r}")
        if "prepublication" in lowered:
            raise NXDataPublicationError(f"candidate language leaked at {path!r}")
        if private_path in lowered or "/private/tmp/" in lowered:
            raise NXDataPublicationError(f"private capture path leaked at {path!r}")


def expected_source_document() -> dict[str, Any]:
    identities = _validate_reviewed_inputs()
    reviewed = json.loads(
        (REVIEWED_SOURCE_STAGE / SOURCE_FILENAME).read_text(encoding="utf-8")
    )
    accepted = copy.deepcopy(reviewed)
    replacements = 0
    for evidence in accepted.get("evidence", []):
        metadata = evidence.get("metadata")
        if (
            isinstance(metadata, dict)
            and metadata.get("capture_artifact_id") == REVIEWED_CANDIDATE_ID
        ):
            metadata["capture_artifact_id"] = ARTIFACT_ID
            replacements += 1
    if replacements != 4:
        raise NXDataPublicationError("reviewed evidence lineage count differs")
    _assert_reviewed_input_identities(identities)
    _assert_publication_clean(accepted)
    return accepted


def expected_source_documents() -> dict[str, dict[str, Any]]:
    return {SOURCE_FILENAME: expected_source_document()}


def _source_record(document: Mapping[str, Any]) -> dict[str, Any]:
    payload = _canonical(document)
    return {
        "path": f"sources/{SOURCE_FILENAME}",
        "bytes": len(payload),
        "sha256": _sha256_bytes(payload),
        "schema_version": "1.1",
        "country": document["campus"]["country"],
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
            document[entity]["geometry"] is not None for entity in ("campus", "project")
        ),
        "disposition": "accepted_existing_identity_current_build_successor",
        "accepted": True,
        "published": True,
        "seeded": False,
        "replaces_source_path": f"sources/{PREDECESSOR_FILENAME}",
        "replacement_semantics": (
            "successor_supersedes_predecessor_for_future_source_selection"
        ),
        "predecessor_retained_immutable": True,
    }


def _accepted_assessment(recorded_at: str) -> dict[str, Any]:
    reviewed = json.loads(
        (REVIEWED_ARTIFACT_STAGE / "candidate-assessment.json").read_text(
            encoding="utf-8"
        )
    )
    rows = copy.deepcopy(reviewed["candidates"])
    for row in rows:
        accepted = row.get("candidate_id") == "nxdata3-buh3"
        row["accepted"] = accepted
        row["published"] = accepted
        row["seeded"] = False
        row["open_seed_integration"] = False
        if accepted:
            row["decision"] = (
                "accepted_official_existing_identity_current_build_successor"
            )
            row["source_paths"] = [f"sources/{SOURCE_FILENAME}"]
            row["predecessor_source_path"] = f"sources/{PREDECESSOR_FILENAME}"
            row["replacement_semantics"] = (
                "successor_supersedes_predecessor_for_future_source_selection"
            )
        else:
            row["source_paths"] = []
    result = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-current-build-assessment-v1",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "candidate_count": 4,
        "accepted_source_record_count": 1,
        "published_source_record_count": 1,
        "review_only_count": 3,
        "regional_completeness_claimed": False,
        "candidates": rows,
    }
    _assert_publication_clean(result)
    return result


def _retrieval_inventory(recorded_at: str) -> dict[str, Any]:
    reviewed = json.loads(
        (REVIEWED_ARTIFACT_STAGE / "retrieval-inventory.json").read_text(
            encoding="utf-8"
        )
    )
    reviewed["artifact_id"] = ARTIFACT_ID
    reviewed["recorded_at"] = recorded_at
    reviewed.pop("capture_directory", None)
    reviewed["capture_directory_retained_private"] = True
    reviewed["raw_capture_storage_path_redacted"] = True
    reviewed["raw_capture_redistributed"] = False
    _assert_publication_clean(reviewed)
    return reviewed


def _reviewed_lineage() -> dict[str, Any]:
    return {
        "purpose": "reviewed_candidate_input_lineage_only",
        "reviewed_recorded_at": REVIEWED_RECORDED_AT,
        "reviewed_candidate_manifest_sha256": REVIEWED_ARTIFACT_PINS["manifest.json"][
            1
        ],
        "reviewed_artifact_tree_sha256": REVIEWED_ARTIFACT_TREE_SHA256,
        "reviewed_artifact_files": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in REVIEWED_ARTIFACT_PINS.items()
        ],
        "reviewed_source_tree_sha256": REVIEWED_SOURCE_TREE_SHA256,
        "reviewed_source_files": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in REVIEWED_SOURCE_PINS.items()
        ],
        "raw_capture_file_count": len(RAW_CAPTURE_PINS),
        "raw_capture_total_bytes": sum(pin[0] for pin in RAW_CAPTURE_PINS.values()),
        "raw_capture_tree_sha256": RAW_CAPTURE_TREE_SHA256,
        "raw_capture_storage_path_redacted": True,
        "raw_capture_retained_private": True,
        "direct_promotion_of_reviewed_bytes": False,
    }


def _replacement_contract() -> dict[str, Any]:
    return {
        "predecessor_source_path": f"sources/{PREDECESSOR_FILENAME}",
        "predecessor_bytes": PREDECESSOR_PIN[0],
        "predecessor_sha256": PREDECESSOR_PIN[1],
        "predecessor_retained_immutable": True,
        "predecessor_modified": False,
        "predecessor_deleted": False,
        "successor_source_path": f"sources/{SOURCE_FILENAME}",
        "successor_reuses_exact_stable_keys": [CAMPUS_KEY, PROJECT_KEY],
        "selection_semantics": (
            "successor_supersedes_predecessor_for_future_source_selection"
        ),
        "select_predecessor_and_successor_together": False,
        "downstream_selection_changed_here": False,
    }


def _artifact_documents(
    recorded_at: str, document: Mapping[str, Any]
) -> dict[str, bytes]:
    source_record = _source_record(document)
    assessment = _accepted_assessment(recorded_at)
    readme = f"""# NXDATA-3 official current-build successor

This immutable accepted source artifact publishes one NXDATA-3 / NX-3 / BUH3 evidence successor at {recorded_at}. It reuses the exact existing campus and project stable keys, adds a dated first-party `under_construction` observation as of 2026-06-02, and retains carrier-neutral colocation.

The three technical values remain design-only: 5 MW gross facility design, 3 MW customer IT design, and approximate design PUE 1.3. They are not current draw, installed load, energy consumption, grid connection, generation, or measured operating performance. The record contains no annual-energy, workload, tenant, utilization, coordinate, geometry, parcel, satellite, aerial, map-derived, or computer-vision claim. Publisher imagery is description-only and supplies no normalized lifecycle truth.

The byte-pinned predecessor remains unchanged. Future source selection must choose this successor instead of the predecessor and must never select both together. This publication does not modify an open seed, release, federation, identity graph, timeline, construction master, map, or coverage product.

PORR's anonymous February 2025 project, PORR WAW 11.1, and Data4 Jawczyce remain review-only. No identity bridge or current-build source record is created for them. The frozen official response bundle remains private and is not redistributed; its storage location is redacted.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "regional_completeness_claimed": False,
        "source_records": [source_record],
        "totals": {
            "candidate_assessments": 4,
            "accepted_source_records": 1,
            "published_source_records": 1,
            "review_only_candidates": 3,
            "distinct_campuses": 1,
            "projects": 1,
            "distinct_entity_snapshots": 2,
            "new_entities_against_v95": 0,
            "reused_predecessor_stable_keys": 2,
            "evidence_records": 4,
            "lifecycle_observations": 1,
            "operating_model_observations": 1,
            "workload_observations": 0,
            "capacity_estimates": 3,
            "design_capacity_estimates": 3,
            "current_consumption_observations": 0,
            "annual_energy_observations": 0,
            "coordinate_observations": 0,
            "geometry_observations": 0,
            "satellite_observations": 0,
            "computer_vision_normalized_claims": 0,
        },
        "reviewed_candidate_lineage": _reviewed_lineage(),
        "predecessor_replacement": _replacement_contract(),
        "integration": {
            "published": True,
            "accepted": True,
            "open_seed_successor_created": False,
            "release_integration": "none",
            "federation_integration": "none",
            "identity_integration": "none",
            "timeline_integration": "none",
            "construction_master_integration": "none",
            "map_integration": "none",
            "coverage_integration": "none",
            "downstream_files_touched": [],
        },
        "publication_contract": {
            "version": 1,
            "authorization_required": True,
            "unique_same_filesystem_sibling_stages": True,
            "lock_required": True,
            "future_recorded_at_required": True,
            "wait_live_before_freeze": True,
            "recursive_inode_recheck_before_freeze": True,
            "reviewed_lineage_inode_recheck_before_promotion": True,
            "byte_and_tree_recheck_before_and_after_freeze": True,
            "atomic_no_replace_promotion": True,
            "identity_checked_rollback": True,
            "all_recursive_stage_birthtimes_and_mtimes_at_or_before_recorded_at": True,
            "all_recursive_final_ctimes_at_or_after_recorded_at": True,
            "source_file_mode": "0444",
            "artifact_file_mode": "0444",
            "artifact_directory_mode": "0555",
            "existing_identical_replay": True,
            "private_raw_storage_path_redacted": True,
        },
    }

    reviewed_rights = json.loads(
        (REVIEWED_ARTIFACT_STAGE / "rights-and-disposition.json").read_text(
            encoding="utf-8"
        )
    )
    rights = {
        key: value
        for key, value in reviewed_rights.items()
        if key != "private_capture_directory"
    }
    rights["artifact_id"] = ARTIFACT_ID
    rights["recorded_at"] = recorded_at
    rights["private_capture_directory_retained"] = True
    rights["raw_capture_storage_path_redacted"] = True
    rights["publication_performed"] = True
    rights["deletion_performed"] = False

    payloads = {
        "README.md": readme.encode("utf-8"),
        "candidate-assessment.json": _canonical(assessment),
        "retrieval-inventory.json": _canonical(_retrieval_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }
    for name, payload in payloads.items():
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as error:  # pragma: no cover - defensive
            raise NXDataPublicationError(
                f"accepted artifact member is not UTF-8: {name}"
            ) from error
        _assert_publication_clean(text)
    return payloads


def _offline_import(path: Path, recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="nxdata3-accepted-import-", dir="/private/tmp"
    ) as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            adapter.import_file(connection, path, recorded_at=recorded_at)
        errors = validate_database(connection)
        if errors:
            raise NXDataPublicationError(
                f"offline database validation failed: {errors!r}"
            )
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
            "entities": 2,
            "entity_snapshots": 2,
            "evidence": 4,
            "lifecycle_observations": 1,
            "operating_model_observations": 1,
            "workload_observations": 0,
            "capacity_estimates": 3,
        }
        if counts != expected:
            raise NXDataPublicationError(f"offline import counts differ: {counts!r}")
        return counts


def _write_new_file(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _write_source_stage(stage: Path, document: Mapping[str, Any]) -> None:
    _write_new_file(stage / SOURCE_FILENAME, _canonical(document))
    stage.chmod(0o700)
    _fsync_directory(stage)


def _write_artifact_stage(
    stage: Path, recorded_at: str, document: Mapping[str, Any]
) -> None:
    payloads = _artifact_documents(recorded_at, document)
    for name in CONTENT_FILES:
        _write_new_file(stage / name, payloads[name])
    rows = [
        {
            "path": name,
            "bytes": (stage / name).stat().st_size,
            "sha256": _sha256(stage / name),
        }
        for name in CONTENT_FILES
    ]
    manifest = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-artifact-manifest-v3",
        "recorded_at": recorded_at,
        "files": rows,
        "tree_sha256": _sha256_bytes(_canonical(rows)),
        "closed_file_set": sorted(CLOSED_FILES),
        "candidate_assessments": 4,
        "accepted_source_records": 1,
        "published_source_records": 1,
        "review_only_candidates": 3,
        "successful_http_200_body_captures": 13,
        "raw_capture_redistributed": False,
        "raw_capture_storage_path_redacted": True,
        "published": True,
        "accepted": True,
        "regional_completeness_claimed": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
    }
    _assert_publication_clean(manifest)
    manifest_path = stage / "manifest.json"
    _write_new_file(manifest_path, _canonical(manifest))
    _write_new_file(
        stage / "manifest.sha256",
        f"{_sha256(manifest_path)}  manifest.json\n".encode("utf-8"),
    )
    stage.chmod(0o700)
    _fsync_directory(stage)


def _assert_stage_precedes(root: Path, target: datetime) -> None:
    members = (root, *root.rglob("*")) if root.is_dir() else (root,)
    for candidate in members:
        metadata = candidate.stat(follow_symlinks=False)
        birthtime = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if max(birthtime, metadata.st_mtime) > target.timestamp() + 0.000_001:
            raise NXDataPublicationError(
                f"private stage post-dates recorded_at: {candidate}"
            )


def _assert_recursive_ctimes_at_or_after(root: Path, target: datetime) -> None:
    members = (root, *root.rglob("*")) if root.is_dir() else (root,)
    for candidate in members:
        if (
            candidate.stat(follow_symlinks=False).st_ctime + 0.000_001
            < target.timestamp()
        ):
            raise NXDataPublicationError(
                f"final member ctime predates recorded_at: {candidate}"
            )


def _freeze_stages(source_stage: Path, artifact_stage: Path) -> None:
    source = source_stage / SOURCE_FILENAME
    source.chmod(0o444)
    _fsync_regular(source)
    _fsync_directory(source_stage)
    for path in artifact_stage.iterdir():
        path.chmod(0o444)
        _fsync_regular(path)
    artifact_stage.chmod(0o555)
    _fsync_directory(artifact_stage)


def _validate_source(
    path: Path,
    document: Mapping[str, Any],
    *,
    frozen: bool,
    recorded_at: str,
) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise NXDataPublicationError("accepted source is missing or unsafe")
    expected_mode = 0o444 if frozen else 0o600
    if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) != expected_mode:
        raise NXDataPublicationError("accepted source mode differs")
    payload = path.read_bytes()
    if payload != _canonical(document):
        raise NXDataPublicationError("accepted source differs")
    _assert_publication_clean(payload.decode("utf-8"))
    _offline_import(path, recorded_at)
    return _source_record(document)


def _validate_artifact(
    artifact: Path,
    source: Path,
    *,
    frozen: bool,
    require_live: bool,
    require_final_chronology: bool,
    document: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    document = dict(document or expected_source_document())
    if artifact.is_symlink() or not artifact.is_dir():
        raise NXDataPublicationError("accepted artifact is missing or unsafe")
    expected_directory_mode = 0o555 if frozen else 0o700
    expected_file_mode = 0o444 if frozen else 0o600
    if (
        stat.S_IMODE(artifact.stat(follow_symlinks=False).st_mode)
        != expected_directory_mode
    ):
        raise NXDataPublicationError("accepted artifact directory mode differs")
    entries = {path.name: path for path in artifact.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise NXDataPublicationError("accepted artifact closed file set differs")
    for name, path in entries.items():
        if path.is_symlink() or not path.is_file():
            raise NXDataPublicationError(f"unsafe accepted artifact member: {name}")
        if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) != expected_file_mode:
            raise NXDataPublicationError(
                f"accepted artifact member mode differs: {name}"
            )

    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if (
        manifest.get("artifact_id") != ARTIFACT_ID
        or manifest.get("format")
        != "datacenter-atlas-official-source-artifact-manifest-v3"
        or manifest.get("published") is not True
        or manifest.get("accepted") is not True
        or manifest.get("accepted_source_records") != 1
        or manifest.get("review_only_candidates") != 3
        or manifest.get("raw_capture_storage_path_redacted") is not True
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
    ):
        raise NXDataPublicationError("accepted manifest contract differs")
    rows = manifest.get("files")
    if not isinstance(rows, list) or [row.get("path") for row in rows] != list(
        CONTENT_FILES
    ):
        raise NXDataPublicationError("accepted manifest inventory differs")
    for row in rows:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (
            row["bytes"],
            row["sha256"],
        ):
            raise NXDataPublicationError(
                f"accepted manifest pin differs: {row['path']}"
            )
    if manifest["tree_sha256"] != _sha256_bytes(_canonical(rows)):
        raise NXDataPublicationError("accepted logical tree differs")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise NXDataPublicationError("accepted manifest checksum differs")

    expected_payloads = _artifact_documents(manifest["recorded_at"], document)
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected_payloads[name]:
            raise NXDataPublicationError(f"accepted artifact content differs: {name}")
    source_record = _validate_source(
        source,
        document,
        frozen=frozen,
        recorded_at=manifest["recorded_at"],
    )
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot.get("source_records") != [source_record]:
        raise NXDataPublicationError("accepted source pin differs")
    if snapshot.get("predecessor_replacement") != _replacement_contract():
        raise NXDataPublicationError("predecessor replacement contract differs")
    assessment = json.loads(
        entries["candidate-assessment.json"].read_text(encoding="utf-8")
    )
    accepted_rows = [row for row in assessment["candidates"] if row["accepted"]]
    if len(accepted_rows) != 1 or accepted_rows[0]["candidate_id"] != "nxdata3-buh3":
        raise NXDataPublicationError("accepted candidate set differs")
    for name, path in entries.items():
        _assert_publication_clean(path.read_text(encoding="utf-8"))

    target = _instant(manifest["recorded_at"])
    if require_live and datetime.now(UTC) < target:
        raise NXDataPublicationError("accepted recorded_at is not live")
    if require_final_chronology:
        _assert_stage_precedes(artifact, target)
        _assert_recursive_ctimes_at_or_after(artifact, target)
        _assert_stage_precedes(source, target)
        _assert_recursive_ctimes_at_or_after(source, target)
    return manifest


@dataclass(frozen=True)
class PreparedPublication:
    source_stage: Path
    artifact_stage: Path
    recorded_at: str
    document: Mapping[str, Any]
    source_identities: Mapping[str, tuple[int, int, str]]
    artifact_identities: Mapping[str, tuple[int, int, str]]
    reviewed_input_identities: ReviewedInputIdentities
    source_tree_sha256: str
    artifact_tree_sha256: str


def _final_source() -> Path:
    return SOURCES_ROOT / SOURCE_FILENAME


def _final_source_paths() -> dict[str, Path]:
    return {SOURCE_FILENAME: _final_source()}


def _final_presence() -> tuple[bool, list[str]]:
    paths = {"artifact": ARTIFACT, SOURCE_FILENAME: _final_source()}
    present = [
        name for name, path in paths.items() if path.exists() or path.is_symlink()
    ]
    return len(present) == len(paths), present


def _assert_final_absent() -> None:
    _complete, present = _final_presence()
    if present:
        raise NXDataPublicationError(f"final-path collision: {present!r}")


def _discard_owned_tree(
    root: Path,
    *,
    expected: Mapping[str, tuple[int, int, str]] | None = None,
) -> None:
    identities = _tree_identities(root)
    if expected is not None and identities != dict(expected):
        raise NXDataPublicationError(
            f"refusing identity-mismatched stage cleanup: {root}"
        )
    directories = [
        path
        for path in (root, *root.rglob("*"))
        if path.is_dir() and not path.is_symlink()
    ]
    for directory in sorted(
        directories, key=lambda item: len(item.parts), reverse=True
    ):
        relative = "." if directory == root else directory.relative_to(root).as_posix()
        if not _has_identity(directory, identities[relative][:2], directory=True):
            raise NXDataPublicationError(
                f"refusing identity-mismatched stage cleanup: {directory}"
            )
        directory.chmod(0o700)
    files = [
        path for path in root.rglob("*") if path.is_file() and not path.is_symlink()
    ]
    for path in files:
        relative = path.relative_to(root).as_posix()
        if not _has_identity(path, identities[relative][:2], directory=False):
            raise NXDataPublicationError(
                f"refusing identity-mismatched stage cleanup: {path}"
            )
        path.unlink()
    for directory in sorted(
        directories, key=lambda item: len(item.parts), reverse=True
    ):
        relative = "." if directory == root else directory.relative_to(root).as_posix()
        if not _has_identity(directory, identities[relative][:2], directory=True):
            raise NXDataPublicationError(
                f"refusing identity-mismatched stage cleanup: {directory}"
            )
        directory.rmdir()


def _prepare(recorded_at: str) -> PreparedPublication:
    _assert_final_absent()
    target = _instant(recorded_at)
    if datetime.now(UTC) >= target:
        raise NXDataPublicationError("recorded_at must be future before staging")
    reviewed_identities = _validate_reviewed_inputs()
    document = expected_source_document()
    source_stage = Path(
        tempfile.mkdtemp(
            prefix=".official-nxdata3-current-build-source-stage-",
            dir=SOURCES_ROOT,
        )
    )
    source_root_identity = _identity(source_stage, directory=True)
    artifact_stage: Path | None = None
    artifact_root_identity: tuple[int, int] | None = None
    try:
        artifact_stage = Path(
            tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.stage-", dir=ARTIFACT_ROOT)
        )
        artifact_root_identity = _identity(artifact_stage, directory=True)
        if source_root_identity[0] != _identity(SOURCES_ROOT, directory=True)[0]:
            raise NXDataPublicationError("source stage is not on source filesystem")
        if artifact_root_identity[0] != _identity(ARTIFACT_ROOT, directory=True)[0]:
            raise NXDataPublicationError("artifact stage is not on artifact filesystem")
        _write_source_stage(source_stage, document)
        _write_artifact_stage(artifact_stage, recorded_at, document)
        _assert_stage_precedes(source_stage, target)
        _assert_stage_precedes(artifact_stage, target)
        source_identities = _tree_identities(source_stage)
        artifact_identities = _tree_identities(artifact_stage)
        source_tree = _content_tree_sha256(source_stage)
        artifact_tree = _content_tree_sha256(artifact_stage)
        _validate_artifact(
            artifact_stage,
            source_stage / SOURCE_FILENAME,
            frozen=False,
            require_live=False,
            require_final_chronology=False,
            document=document,
        )
        _assert_tree_identities(source_stage, source_identities)
        _assert_tree_identities(artifact_stage, artifact_identities)
        _assert_reviewed_input_identities(reviewed_identities)
        return PreparedPublication(
            source_stage,
            artifact_stage,
            recorded_at,
            document,
            source_identities,
            artifact_identities,
            reviewed_identities,
            source_tree,
            artifact_tree,
        )
    except BaseException:
        if _has_identity(source_stage, source_root_identity, directory=True):
            _discard_owned_tree(source_stage)
        if (
            artifact_stage is not None
            and artifact_root_identity is not None
            and _has_identity(artifact_stage, artifact_root_identity, directory=True)
        ):
            _discard_owned_tree(artifact_stage)
        raise


def _assert_prepared_exact(prepared: PreparedPublication, *, frozen: bool) -> None:
    _assert_tree_identities(prepared.source_stage, prepared.source_identities)
    _assert_tree_identities(prepared.artifact_stage, prepared.artifact_identities)
    if _content_tree_sha256(prepared.source_stage) != prepared.source_tree_sha256:
        raise NXDataPublicationError("prepared source tree differs")
    if _content_tree_sha256(prepared.artifact_stage) != prepared.artifact_tree_sha256:
        raise NXDataPublicationError("prepared artifact tree differs")
    target = _instant(prepared.recorded_at)
    _assert_stage_precedes(prepared.source_stage, target)
    _assert_stage_precedes(prepared.artifact_stage, target)
    _validate_artifact(
        prepared.artifact_stage,
        prepared.source_stage / SOURCE_FILENAME,
        frozen=frozen,
        require_live=False,
        require_final_chronology=False,
        document=prepared.document,
    )


def preflight(*, recorded_at: str | None = None) -> dict[str, Any]:
    """Render, import twice, freeze, validate, and discard exact final bytes."""

    target = (
        _instant(recorded_at)
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=30)
    )
    if datetime.now(UTC) >= target:
        raise NXDataPublicationError("preflight recorded_at must be future")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    prepared = _prepare(timestamp)
    source_stage = prepared.source_stage
    artifact_stage = prepared.artifact_stage
    try:
        _assert_prepared_exact(prepared, frozen=False)
        _freeze_stages(source_stage, artifact_stage)
        _assert_prepared_exact(prepared, frozen=True)
        source_path = source_stage / SOURCE_FILENAME
        artifact_pins = [
            {
                "path": name,
                "bytes": (artifact_stage / name).stat().st_size,
                "sha256": _sha256(artifact_stage / name),
            }
            for name in sorted(CLOSED_FILES)
        ]
        result = {
            "status": "PREFLIGHT_VALIDATED_AND_DISCARDED",
            "recorded_at": timestamp,
            "artifact_id": ARTIFACT_ID,
            "artifact_manifest_sha256": _sha256(artifact_stage / "manifest.json"),
            "artifact_tree_sha256": tree_digest(artifact_stage),
            "artifact_pins": artifact_pins,
            "source_tree_sha256": tree_digest(source_stage),
            "source_pins": [
                {
                    "path": f"sources/{SOURCE_FILENAME}",
                    "bytes": source_path.stat().st_size,
                    "sha256": _sha256(source_path),
                }
            ],
            "predecessor_pin": {
                "path": f"sources/{PREDECESSOR_FILENAME}",
                "bytes": PREDECESSOR_PIN[0],
                "sha256": PREDECESSOR_PIN[1],
            },
            "modes": {
                "source_file": "0444",
                "artifact_directory": "0555",
                "artifact_files": "0444",
                "reviewed_source_directory": "0700",
                "reviewed_source_files": "0600",
                "reviewed_artifact_directory": "0700",
                "reviewed_artifact_files": "0600",
                "raw_capture_directory": "0555",
                "raw_capture_files": "0444",
                "predecessor_file": "0644",
            },
            "rows": {
                "entities": 2,
                "entity_snapshots": 2,
                "evidence": 4,
                "lifecycle": 1,
                "operating_models": 1,
                "workloads": 0,
                "capacities": 3,
                "coordinates": 0,
                "geometry": 0,
                "current_consumption": 0,
                "annual_energy": 0,
            },
            "published": False,
        }
    finally:
        if source_stage.exists():
            _discard_owned_tree(source_stage, expected=prepared.source_identities)
        if artifact_stage.exists():
            _discard_owned_tree(artifact_stage, expected=prepared.artifact_identities)
    _assert_final_absent()
    _validate_reviewed_inputs()
    result["source_stage_discarded"] = not source_stage.exists()
    result["artifact_stage_discarded"] = not artifact_stage.exists()
    result["reviewed_source_stage_retained"] = REVIEWED_SOURCE_STAGE.exists()
    result["reviewed_artifact_stage_retained"] = REVIEWED_ARTIFACT_STAGE.exists()
    result["raw_capture_retained"] = RAW_CAPTURE.exists()
    result["raw_capture_storage_path_redacted"] = True
    result["predecessor_retained"] = PREDECESSOR.exists()
    _assert_publication_clean(result)
    return result


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _promote_noreplace(source: Path, destination: Path) -> None:
    try:
        promote_noreplace(source, destination)
    except SystemExit as error:
        raise NXDataPublicationError(str(error)) from error


def _publish_prepared(prepared: PreparedPublication) -> None:
    target = _instant(prepared.recorded_at)
    _assert_prepared_exact(prepared, frozen=False)
    _assert_reviewed_input_identities(prepared.reviewed_input_identities)
    _assert_final_absent()
    _wait_until(target)
    _assert_final_absent()
    _assert_reviewed_input_identities(prepared.reviewed_input_identities)
    _validate_reviewed_inputs()
    _assert_prepared_exact(prepared, frozen=False)
    _freeze_stages(prepared.source_stage, prepared.artifact_stage)
    _assert_prepared_exact(prepared, frozen=True)
    _assert_recursive_ctimes_at_or_after(
        prepared.source_stage / SOURCE_FILENAME, target
    )
    _assert_recursive_ctimes_at_or_after(prepared.artifact_stage, target)
    _assert_final_absent()

    promoted: list[tuple[Path, Path, tuple[int, int], bool]] = []
    try:
        staged_source = prepared.source_stage / SOURCE_FILENAME
        source_identity = _identity(staged_source, directory=False)
        _promote_noreplace(staged_source, _final_source())
        if not _has_identity(_final_source(), source_identity, directory=False):
            raise NXDataPublicationError("promoted source identity differs")
        promoted.append((_final_source(), staged_source, source_identity, False))

        artifact_identity = _identity(prepared.artifact_stage, directory=True)
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        if not _has_identity(ARTIFACT, artifact_identity, directory=True):
            raise NXDataPublicationError("promoted artifact identity differs")
        _assert_tree_identities(ARTIFACT, prepared.artifact_identities)
        promoted.append((ARTIFACT, prepared.artifact_stage, artifact_identity, True))
        _validate_artifact(
            ARTIFACT,
            _final_source(),
            frozen=True,
            require_live=True,
            require_final_chronology=True,
            document=prepared.document,
        )
        _assert_reviewed_input_identities(prepared.reviewed_input_identities)
    except BaseException as error:
        for final, staged, identity, directory in reversed(promoted):
            try:
                if not _has_identity(final, identity, directory=directory):
                    raise NXDataPublicationError(
                        f"refusing identity-mismatched rollback: {final}"
                    )
                _promote_noreplace(final, staged)
                if not _has_identity(staged, identity, directory=directory):
                    raise NXDataPublicationError(
                        f"rolled-back identity differs: {staged}"
                    )
            except Exception as rollback_error:
                error.add_note(
                    f"NXDATA-3 rollback failed for {final}: {rollback_error}"
                )
        raise


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise NXDataPublicationError(
            "active NXDATA-3 publication lock exists"
        ) from error
    os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
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
                raise NXDataPublicationError(
                    "refusing substituted NXDATA-3 publication-lock cleanup"
                )
            PUBLICATION_LOCK.unlink()


def _existing_identical(recorded_at: str | None) -> dict[str, Any]:
    manifest = json.loads((ARTIFACT / "manifest.json").read_text(encoding="utf-8"))
    existing_recorded_at = manifest.get("recorded_at")
    if not isinstance(existing_recorded_at, str):
        raise NXDataPublicationError("existing recorded_at is missing")
    if recorded_at is not None and recorded_at != existing_recorded_at:
        raise NXDataPublicationError("existing recorded_at differs")
    identities = _validate_reviewed_inputs()
    document = expected_source_document()
    _validate_artifact(
        ARTIFACT,
        _final_source(),
        frozen=True,
        require_live=True,
        require_final_chronology=True,
        document=document,
    )
    _assert_reviewed_input_identities(identities)
    return {
        "status": "existing-identical",
        "artifact": str(ARTIFACT),
        "recorded_at": existing_recorded_at,
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "published": True,
        "accepted_source_records": 1,
        "review_only_candidates": 3,
        "raw_capture_retained": RAW_CAPTURE.exists(),
        "raw_capture_storage_path_redacted": True,
        "predecessor_retained": PREDECESSOR.exists(),
    }


def build(
    *,
    recorded_at: str | None = None,
    publication_authorized: bool = False,
) -> dict[str, Any]:
    """Publish only with explicit authorization; otherwise fail closed."""

    if not publication_authorized:
        raise NXDataPublicationError(
            "NXDATA-3 publication requires publication_authorized=True"
        )
    complete, present = _final_presence()
    if complete:
        return _existing_identical(recorded_at)
    if present:
        raise NXDataPublicationError(f"partial final-path collision: {present!r}")

    target = (
        _instant(recorded_at)
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise NXDataPublicationError("recorded_at must be future before publication")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    SOURCES_ROOT.mkdir(parents=True, exist_ok=True)
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    with _publication_lock():
        prepared = _prepare(timestamp)
        try:
            _publish_prepared(prepared)
        except BaseException:
            if prepared.source_stage.exists():
                _discard_owned_tree(
                    prepared.source_stage,
                    expected=prepared.source_identities,
                )
            if prepared.artifact_stage.exists():
                _discard_owned_tree(
                    prepared.artifact_stage,
                    expected=prepared.artifact_identities,
                )
            raise
        if prepared.source_stage.exists():
            if any(prepared.source_stage.iterdir()):
                raise NXDataPublicationError("source stage not empty after publication")
            root_identity = prepared.source_identities["."][:2]
            if not _has_identity(prepared.source_stage, root_identity, directory=True):
                raise NXDataPublicationError("source stage identity differs")
            prepared.source_stage.rmdir()
        manifest = _validate_artifact(
            ARTIFACT,
            _final_source(),
            frozen=True,
            require_live=True,
            require_final_chronology=True,
            document=prepared.document,
        )
    return {
        "status": "published",
        "artifact": str(ARTIFACT),
        "recorded_at": manifest["recorded_at"],
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "published": True,
        "accepted_source_records": 1,
        "review_only_candidates": 3,
        "raw_capture_retained": RAW_CAPTURE.exists(),
        "raw_capture_storage_path_redacted": True,
        "predecessor_retained": PREDECESSOR.exists(),
    }


def main() -> int:
    print(json.dumps(preflight(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
