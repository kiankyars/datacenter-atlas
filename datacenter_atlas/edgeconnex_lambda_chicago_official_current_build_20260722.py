"""Authorization-gated publisher for the reviewed EdgeConneX/Lambda record.

The source payload is promoted byte-for-byte from its retained reviewed stage.
The accepted artifact is rendered from pinned reviewed inputs, contains one
accepted Chicago record and nine review-only dispositions, and exposes no
storage or staging locations. If the frozen raw-response clone is still
resolvable, it is validated exactly; after publication, its absence does not
replace or relax validation of the reviewed stages or accepted final artifact.

``preflight`` is the safe default.  It renders the exact accepted bytes in
unique same-filesystem sibling stages, imports the source exactly twice,
freezes and validates both stages, reports their pins, and identity-safely
discards them.  Only ``build(publication_authorized=True)`` may wait for the
future recorded time and attempt atomic no-replace promotion.
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
from .edgeconnex_lambda_chicago_official_gap_prepublication_20260722 import (
    CAPTURE_FILE_PINS as _REVIEWED_CAPTURE_FILE_PINS,
)
from .external_captures import ExternalCaptureError, resolve_external_capture
from .open_seed_v56 import tree_digest
from .open_seed_v69 import promote_noreplace
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"

ARTIFACT_ID = "edgeconnex-lambda-chicago-official-current-build-2026-07-22-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".edgeconnex-lambda-chicago-official-current-build.lock"

SOURCE_FILENAME = (
    "curated-official-2026-07-22-edgeconnex-lambda-chicago-23mw-current-build.json"
)
SOURCE_FILENAMES = (SOURCE_FILENAME,)

REVIEWED_ARTIFACT_ID = (
    "edgeconnex-lambda-chicago-official-gap-prepublication-2026-07-22-v1"
)
REVIEWED_RECORDED_AT = "2026-07-22T05:20:00Z"
REVIEWED_SOURCE_STAGE = (
    SOURCES_ROOT / ".edgeconnex-lambda-chicago-prepublication-sources.0yaszx96"
)
REVIEWED_ARTIFACT_STAGE = (
    ARTIFACT_ROOT
    / ".edgeconnex-lambda-chicago-official-gap-prepublication-2026-07-22-v1.we41o1kb"
)
RAW_CAPTURE = Path("/Users/kian/.Trash/dc-edgeconnex-lambda-gap-accepted-20260722")

REVIEWED_SOURCE_TREE_SHA256 = (
    "19003e56e879d045110155e6e0610e1e0a8f83c53d6595e5e939e3f638a4d07e"
)
REVIEWED_ARTIFACT_TREE_SHA256 = (
    "ce3ef7075297b6b55e34bfe522f8def6f100abbf6dd3f1873df13a733ac02cfd"
)
RAW_CAPTURE_TREE_SHA256 = (
    "2704a07148f01c3e027fe7208331cc6d6072df5a462c4d3cb6ae679ad5ba8c33"
)

REVIEWED_SOURCE_PINS: Mapping[str, tuple[int, str]] = {
    SOURCE_FILENAME: (
        12_217,
        "d43bcec02e9459d307ecaadadf0c9cbc59100f9008d835567db9f1db47c8748f",
    )
}
REVIEWED_ARTIFACT_PINS: Mapping[str, tuple[int, str]] = {
    "README.md": (
        1_329,
        "68540051f60c9ea6eeaf77d459f0fbe34cbe7d8f2ada0ee04b23c7c011dc5477",
    ),
    "candidate-assessment.json": (
        4_403,
        "887809f4eb16c8371e88e9562851780b85eb8c90511a1d99b1318ec0098ed229",
    ),
    "manifest.json": (
        1_608,
        "f165864cabf99fe5e62561bc488b36a239617aacb0520c3d96bc7fb0606b89f4",
    ),
    "manifest.sha256": (
        80,
        "69ed13f8e5b7f230d6997ff6ffed6d8d2bd41dc45ff894cd0f13950946331b46",
    ),
    "retrieval-inventory.json": (
        10_249,
        "e11c8e8f7f829337095901960b0bbebfb410381115023bcd312d750d2b8c9758",
    ),
    "rights-and-disposition.json": (
        878,
        "954cd3fa46e16c143d7d7c7030d63648a6b26edfd691941a9df72f235362c587",
    ),
    "source-snapshot.json": (
        4_769,
        "d544ec8da6057a2d3d749d4ad17658c3a41fbf06cfbee0509f0ce2a93c533dbf",
    ),
}
RAW_CAPTURE_PINS: Mapping[str, tuple[int, str]] = dict(_REVIEWED_CAPTURE_FILE_PINS)

CAMPUS_KEY = "curated:edgeconnex-lambda-chicago-23mw-site"
PROJECT_KEY = f"{CAMPUS_KEY}:2025-2026-single-tenant-build"
ACCEPTED_ASSESSMENT_ID = "edgeconnex-lambda-chicago-23mw"

CONTENT_FILES = (
    "README.md",
    "acceptance-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

FORBIDDEN_PUBLICATION_FRAGMENTS = (
    "prepublication",
    "candidate",
    "prospective",
    "private-stage",
    "private stage",
    "/users/",
    "/private/",
)


class EdgeConneXPublicationError(RuntimeError):
    """Fail-closed EdgeConneX/Lambda publication error."""


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
        raise EdgeConneXPublicationError("recorded_at must be ISO 8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EdgeConneXPublicationError("recorded_at must be timezone aware")
    return parsed.astimezone(UTC)


def _pin(path: Path, expected: tuple[int, str], *, mode: int) -> None:
    if path.is_symlink() or not path.is_file():
        raise EdgeConneXPublicationError(f"missing or unsafe pinned input: {path}")
    metadata = path.stat(follow_symlinks=False)
    if (metadata.st_size, _sha256(path)) != expected:
        raise EdgeConneXPublicationError(f"pinned input differs: {path}")
    if stat.S_IMODE(metadata.st_mode) != mode:
        raise EdgeConneXPublicationError(f"pinned input mode differs: {path}")


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
        raise EdgeConneXPublicationError(f"symlink is not allowed: {path}")
    metadata = path.stat(follow_symlinks=False)
    if directory is True and not stat.S_ISDIR(metadata.st_mode):
        raise EdgeConneXPublicationError(f"expected directory: {path}")
    if directory is False and not stat.S_ISREG(metadata.st_mode):
        raise EdgeConneXPublicationError(f"expected regular file: {path}")
    return metadata.st_dev, metadata.st_ino


def _has_identity(
    path: Path, expected: tuple[int, int], *, directory: bool | None = None
) -> bool:
    try:
        return _identity(path, directory=directory) == expected
    except (FileNotFoundError, EdgeConneXPublicationError):
        return False


def _tree_identities(root: Path) -> dict[str, tuple[int, int, str]]:
    if root.is_symlink() or not root.is_dir():
        raise EdgeConneXPublicationError(f"unsafe tree root: {root}")
    result: dict[str, tuple[int, int, str]] = {}
    for path in (root, *sorted(root.rglob("*"))):
        if path.is_symlink():
            raise EdgeConneXPublicationError(f"symlink in governed tree: {path}")
        metadata = path.stat(follow_symlinks=False)
        kind = (
            "directory"
            if stat.S_ISDIR(metadata.st_mode)
            else "file"
            if stat.S_ISREG(metadata.st_mode)
            else "other"
        )
        if kind == "other":
            raise EdgeConneXPublicationError(f"special file in governed tree: {path}")
        relative = "." if path == root else path.relative_to(root).as_posix()
        result[relative] = (metadata.st_dev, metadata.st_ino, kind)
    return result


def _assert_tree_identities(
    root: Path, expected: Mapping[str, tuple[int, int, str]]
) -> None:
    if _tree_identities(root) != dict(expected):
        raise EdgeConneXPublicationError(f"tree identity changed: {root}")


@dataclass(frozen=True)
class ReviewedInputIdentities:
    sources: Mapping[str, tuple[int, int, str]]
    artifact: Mapping[str, tuple[int, int, str]]
    capture_path: Path | None
    captures: Mapping[str, tuple[int, int, str]]


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
        raise EdgeConneXPublicationError(f"{label} is missing or unsafe")
    entries = {path.name: path for path in root.iterdir()}
    if set(entries) != set(pins):
        raise EdgeConneXPublicationError(f"{label} inventory differs")
    for name, pin in pins.items():
        _pin(entries[name], pin, mode=file_mode)
    if tree_digest(root) != tree_sha256:
        raise EdgeConneXPublicationError(f"{label} tree differs")


def _resolve_raw_capture() -> Path | None:
    try:
        return resolve_external_capture(RAW_CAPTURE)
    except ExternalCaptureError:
        return None


def _validate_raw_capture(capture: Path) -> None:
    _validate_governed_tree(
        capture,
        RAW_CAPTURE_PINS,
        directory_mode=0o555,
        file_mode=0o444,
        tree_sha256=RAW_CAPTURE_TREE_SHA256,
        label="raw capture clone",
    )


def _assert_reviewed_input_identities(identities: ReviewedInputIdentities) -> None:
    _assert_tree_identities(REVIEWED_SOURCE_STAGE, identities.sources)
    _assert_tree_identities(REVIEWED_ARTIFACT_STAGE, identities.artifact)
    capture = _resolve_raw_capture()
    if identities.capture_path is None:
        if capture is not None:
            raise EdgeConneXPublicationError("raw capture clone identity changed")
        return
    if capture != identities.capture_path:
        raise EdgeConneXPublicationError("raw capture clone identity changed")
    _validate_raw_capture(capture)
    _assert_tree_identities(capture, identities.captures)


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
    capture = _resolve_raw_capture()
    if capture is not None:
        _validate_raw_capture(capture)

    manifest_path = REVIEWED_ARTIFACT_STAGE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("artifact_id") != REVIEWED_ARTIFACT_ID
        or manifest.get("recorded_at") != REVIEWED_RECORDED_AT
        or manifest.get("published") is not False
        or manifest.get("publisher_function_present") is not False
    ):
        raise EdgeConneXPublicationError("reviewed manifest contract differs")
    checksum = REVIEWED_ARTIFACT_STAGE / "manifest.sha256"
    if checksum.read_text(encoding="utf-8") != (
        f"{REVIEWED_ARTIFACT_PINS['manifest.json'][1]}  manifest.json\n"
    ):
        raise EdgeConneXPublicationError("reviewed manifest checksum differs")

    source_path = REVIEWED_SOURCE_STAGE / SOURCE_FILENAME
    source_raw = source_path.read_bytes()
    source = json.loads(source_raw)
    if _canonical(source) != source_raw:
        raise EdgeConneXPublicationError("reviewed source is not canonical")
    if (
        source.get("schema_version") != "1.1"
        or source.get("campus", {}).get("stable_key") != CAMPUS_KEY
        or source.get("project", {}).get("stable_key") != PROJECT_KEY
    ):
        raise EdgeConneXPublicationError("reviewed source identity differs")

    assessment = json.loads(
        (REVIEWED_ARTIFACT_STAGE / "candidate-assessment.json").read_text(
            encoding="utf-8"
        )
    )
    rows = assessment.get("candidates")
    if (
        not isinstance(rows, list)
        or len(rows) != 10
        or sum(row.get("candidate_id") == ACCEPTED_ASSESSMENT_ID for row in rows) != 1
    ):
        raise EdgeConneXPublicationError("reviewed assessment inventory differs")

    identities = ReviewedInputIdentities(
        _tree_identities(REVIEWED_SOURCE_STAGE),
        _tree_identities(REVIEWED_ARTIFACT_STAGE),
        capture,
        _tree_identities(capture) if capture is not None else {},
    )
    _assert_reviewed_input_identities(identities)
    return identities


def _walk_text(
    value: Any, path: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            yield (*path, "<key>"), key_text
            yield from _walk_text(item, (*path, key_text))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_text(item, (*path, str(index)))


def _assert_publication_clean(value: Any) -> None:
    internal_names = (
        RAW_CAPTURE.name.lower(),
        REVIEWED_SOURCE_STAGE.name.lower(),
        REVIEWED_ARTIFACT_STAGE.name.lower(),
    )
    for path, text in _walk_text(value):
        lowered = text.lower()
        if any(fragment in lowered for fragment in FORBIDDEN_PUBLICATION_FRAGMENTS):
            raise EdgeConneXPublicationError(
                f"restricted publication language at {path!r}"
            )
        if any(name in lowered for name in internal_names):
            raise EdgeConneXPublicationError(
                f"internal storage identity leaked at {path!r}"
            )


def expected_source_bytes() -> bytes:
    identities = _validate_reviewed_inputs()
    payload = (REVIEWED_SOURCE_STAGE / SOURCE_FILENAME).read_bytes()
    if (len(payload), _sha256_bytes(payload)) != REVIEWED_SOURCE_PINS[SOURCE_FILENAME]:
        raise EdgeConneXPublicationError("reviewed source payload differs")
    document = json.loads(payload)
    if _canonical(document) != payload:
        raise EdgeConneXPublicationError("reviewed source canonical bytes differ")
    _assert_publication_clean(document)
    _assert_reviewed_input_identities(identities)
    return payload


def expected_source_document() -> dict[str, Any]:
    return json.loads(expected_source_bytes())


def expected_source_documents() -> dict[str, dict[str, Any]]:
    return {SOURCE_FILENAME: expected_source_document()}


def _source_record(document: Mapping[str, Any], payload: bytes) -> dict[str, Any]:
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
        "disposition": "accepted_official_current_build_source",
        "accepted": True,
        "published": True,
        "seeded": False,
        "reviewed_source_bytes_preserved_exactly": True,
    }


def _accepted_assessment(recorded_at: str) -> dict[str, Any]:
    reviewed = json.loads(
        (REVIEWED_ARTIFACT_STAGE / "candidate-assessment.json").read_text(
            encoding="utf-8"
        )
    )
    rows = copy.deepcopy(reviewed["candidates"])
    for row in rows:
        assessment_id = row.pop("candidate_id")
        accepted = assessment_id == ACCEPTED_ASSESSMENT_ID
        row["assessment_id"] = assessment_id
        row["accepted"] = accepted
        row["published"] = accepted
        row["seeded"] = False
        row["open_seed_integration"] = False
        row["source_paths"] = [f"sources/{SOURCE_FILENAME}"] if accepted else []
        if accepted:
            row["decision"] = "accepted_official_current_build_source"
    result = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-current-build-acceptance-assessment-v1",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "assessment_count": 10,
        "accepted_source_record_count": 1,
        "published_source_record_count": 1,
        "review_only_count": 9,
        "global_completeness_claimed": False,
        "assessments": rows,
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
    reviewed.pop("capture_bundle_id", None)
    reviewed["capture_storage_location_redacted"] = True
    reviewed["capture_bytes_redistributed"] = False
    _assert_publication_clean(reviewed)
    return reviewed


def _aggregate_pin_hash(
    pins: Mapping[str, tuple[int, str]], *, include_names: bool
) -> str:
    rows = [
        (
            {"name": name, "bytes": pin[0], "sha256": pin[1]}
            if include_names
            else {"bytes": pin[0], "sha256": pin[1]}
        )
        for name, pin in sorted(pins.items())
    ]
    return _sha256_bytes(_canonical(rows))


def _reviewed_input_lineage() -> dict[str, Any]:
    return {
        "purpose": "reviewed_input_hash_lineage_only",
        "reviewed_recorded_at": REVIEWED_RECORDED_AT,
        "reviewed_source_tree_sha256": REVIEWED_SOURCE_TREE_SHA256,
        "reviewed_source_bytes": REVIEWED_SOURCE_PINS[SOURCE_FILENAME][0],
        "reviewed_source_sha256": REVIEWED_SOURCE_PINS[SOURCE_FILENAME][1],
        "reviewed_artifact_tree_sha256": REVIEWED_ARTIFACT_TREE_SHA256,
        "reviewed_manifest_sha256": REVIEWED_ARTIFACT_PINS["manifest.json"][1],
        "reviewed_artifact_member_count": len(REVIEWED_ARTIFACT_PINS),
        "reviewed_artifact_member_pin_set_sha256": _aggregate_pin_hash(
            REVIEWED_ARTIFACT_PINS, include_names=False
        ),
        "capture_file_count": len(RAW_CAPTURE_PINS),
        "capture_total_bytes": sum(pin[0] for pin in RAW_CAPTURE_PINS.values()),
        "capture_tree_sha256": RAW_CAPTURE_TREE_SHA256,
        "capture_member_pin_set_sha256": _aggregate_pin_hash(
            RAW_CAPTURE_PINS, include_names=False
        ),
        "capture_storage_location_redacted": True,
        "reviewed_storage_locations_redacted": True,
        "source_payload_promoted_byte_identically": True,
    }


def _artifact_documents(
    recorded_at: str,
    document: Mapping[str, Any],
    source_payload: bytes,
) -> dict[str, bytes]:
    source_record = _source_record(document, source_payload)
    assessment = _accepted_assessment(recorded_at)
    readme = f"""# EdgeConneX/Lambda Chicago official current-build source

This immutable accepted artifact publishes one city-level Chicago source record at {recorded_at}. The first-party release reports EdgeConneX developing a single-tenant data center with Lambda and supplies a dated `under_construction` observation from 2025-08-21. The source payload is byte-identical to the retained reviewed record.

The reported 23 MW remains untyped source metadata. It is not normalized as IT load, gross facility demand, grid connection, generation, installed capacity, current draw, annual energy, or measured performance. HPC, AI training, and AI inference are intended workloads as reported. The record creates no operating-model row, coordinate, geometry, parcel, building footprint, satellite observation, aerial observation, or computer-vision claim.

Construction Safety Week is city-level corroboration only and does not bridge the Lambda project to CHI03. Nine other site leads remain review-only because identity, phase, or current physical status is unresolved. No open seed, release, federation, identity graph, timeline, construction master, map, or coverage product is changed.

Exact response bytes are retained in restricted read-only storage and are not redistributed. Storage and staging locations are redacted.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "global_completeness_claimed": False,
        "source_records": [source_record],
        "totals": {
            "assessments": 10,
            "accepted_source_records": 1,
            "published_source_records": 1,
            "review_only_assessments": 9,
            "distinct_campuses": 1,
            "projects": 1,
            "distinct_entity_snapshots": 2,
            "evidence_records": 3,
            "lifecycle_observations": 1,
            "operating_model_observations": 0,
            "workload_observations": 3,
            "capacity_estimates": 0,
            "current_consumption_observations": 0,
            "annual_energy_observations": 0,
            "coordinate_observations": 0,
            "geometry_observations": 0,
            "satellite_observations": 0,
            "computer_vision_normalized_claims": 0,
        },
        "reviewed_input_lineage": _reviewed_input_lineage(),
        "integration": {
            "published": True,
            "accepted": True,
            "open_seed_source_created": False,
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
            "exactly_two_offline_imports": True,
            "unique_same_filesystem_sibling_stages": True,
            "exclusive_creation_lock_required": True,
            "future_recorded_at_required": True,
            "wait_live_before_freeze": True,
            "recursive_inode_recheck_before_freeze": True,
            "reviewed_input_inode_recheck_before_promotion": True,
            "byte_and_tree_recheck_before_and_after_freeze": True,
            "atomic_no_replace_promotion": True,
            "identity_checked_rollback": True,
            "recursive_stage_birthtimes_and_mtimes_not_after_recorded_at": True,
            "recursive_final_ctimes_not_before_recorded_at": True,
            "source_file_mode": "0444",
            "artifact_file_mode": "0444",
            "artifact_directory_mode": "0555",
            "existing_identical_replay": True,
            "storage_locations_redacted": True,
        },
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-disposition-v3",
        "recorded_at": recorded_at,
        "artifact_is_hash_and_factual_extract_only": True,
        "source_rights": ("EdgeConneX public pages treated as all-rights-reserved."),
        "request_credentials_supplied": False,
        "publisher_media_retained_in_artifact": False,
        "raw_response_bodies_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "capture_bytes_redistributed": False,
        "capture_storage_location_redacted": True,
        "capture_file_count": len(RAW_CAPTURE_PINS),
        "capture_total_bytes": sum(pin[0] for pin in RAW_CAPTURE_PINS.values()),
        "capture_tree_sha256": RAW_CAPTURE_TREE_SHA256,
        "publication_performed": True,
        "deletion_performed": False,
    }
    payloads = {
        "README.md": readme.encode("utf-8"),
        "acceptance-assessment.json": _canonical(assessment),
        "retrieval-inventory.json": _canonical(_retrieval_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }
    for name, payload in payloads.items():
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as error:  # pragma: no cover
            raise EdgeConneXPublicationError(
                f"accepted artifact member is not UTF-8: {name}"
            ) from error
        _assert_publication_clean(text)
    return payloads


def _offline_import(path: Path, recorded_at: str) -> dict[str, int]:
    import_calls = 0
    with tempfile.TemporaryDirectory(
        prefix="edgeconnex-lambda-accepted-import-", dir="/private/tmp"
    ) as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            adapter.import_file(connection, path, recorded_at=recorded_at)
            import_calls += 1
        errors = validate_database(connection)
        if errors:
            raise EdgeConneXPublicationError(
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
        "evidence": 3,
        "lifecycle_observations": 1,
        "operating_model_observations": 0,
        "workload_observations": 3,
        "capacity_estimates": 0,
    }
    if import_calls != 2:
        raise EdgeConneXPublicationError("offline import count differs")
    if counts != expected:
        raise EdgeConneXPublicationError(f"offline import rows differ: {counts!r}")
    return counts


def _write_new_file(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _write_source_stage(stage: Path, payload: bytes) -> None:
    _write_new_file(stage / SOURCE_FILENAME, payload)
    stage.chmod(0o700)
    _fsync_directory(stage)


def _write_artifact_stage(
    stage: Path,
    recorded_at: str,
    document: Mapping[str, Any],
    source_payload: bytes,
) -> None:
    payloads = _artifact_documents(recorded_at, document, source_payload)
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
        "assessment_records": 10,
        "accepted_source_records": 1,
        "published_source_records": 1,
        "review_only_assessments": 9,
        "successful_http_200_body_captures": 14,
        "capture_files": 28,
        "capture_bytes_redistributed": False,
        "capture_storage_location_redacted": True,
        "published": True,
        "accepted": True,
        "global_completeness_claimed": False,
        "open_seed_source_created": False,
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
    for path in members:
        metadata = path.stat(follow_symlinks=False)
        birthtime = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if max(birthtime, metadata.st_mtime) > target.timestamp() + 0.000_001:
            raise EdgeConneXPublicationError(
                f"stage member post-dates recorded_at: {path}"
            )


def _assert_recursive_ctimes_at_or_after(root: Path, target: datetime) -> None:
    members = (root, *root.rglob("*")) if root.is_dir() else (root,)
    for path in members:
        if path.stat(follow_symlinks=False).st_ctime + 0.000_001 < target.timestamp():
            raise EdgeConneXPublicationError(
                f"final member ctime predates recorded_at: {path}"
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
    source_payload: bytes,
    *,
    frozen: bool,
) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise EdgeConneXPublicationError("accepted source is missing or unsafe")
    expected_mode = 0o444 if frozen else 0o600
    if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) != expected_mode:
        raise EdgeConneXPublicationError("accepted source mode differs")
    payload = path.read_bytes()
    if payload != source_payload or payload != _canonical(document):
        raise EdgeConneXPublicationError("accepted source differs")
    if (len(payload), _sha256_bytes(payload)) != REVIEWED_SOURCE_PINS[SOURCE_FILENAME]:
        raise EdgeConneXPublicationError("accepted source pin differs")
    _assert_publication_clean(payload.decode("utf-8"))
    return _source_record(document, payload)


def _validate_artifact(
    artifact: Path,
    source: Path,
    *,
    frozen: bool,
    require_live: bool,
    require_final_chronology: bool,
    document: Mapping[str, Any],
    source_payload: bytes,
) -> dict[str, Any]:
    if artifact.is_symlink() or not artifact.is_dir():
        raise EdgeConneXPublicationError("accepted artifact is missing or unsafe")
    directory_mode = 0o555 if frozen else 0o700
    file_mode = 0o444 if frozen else 0o600
    if stat.S_IMODE(artifact.stat(follow_symlinks=False).st_mode) != directory_mode:
        raise EdgeConneXPublicationError("accepted artifact directory mode differs")
    entries = {path.name: path for path in artifact.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise EdgeConneXPublicationError("accepted artifact closed file set differs")
    for name, path in entries.items():
        if path.is_symlink() or not path.is_file():
            raise EdgeConneXPublicationError(f"unsafe artifact member: {name}")
        if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) != file_mode:
            raise EdgeConneXPublicationError(f"artifact member mode differs: {name}")

    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if (
        manifest.get("artifact_id") != ARTIFACT_ID
        or manifest.get("format")
        != "datacenter-atlas-official-source-artifact-manifest-v3"
        or manifest.get("published") is not True
        or manifest.get("accepted") is not True
        or manifest.get("assessment_records") != 10
        or manifest.get("accepted_source_records") != 1
        or manifest.get("review_only_assessments") != 9
        or manifest.get("capture_storage_location_redacted") is not True
        or manifest.get("open_seed_source_created") is not False
        or manifest.get("release_integration") != "none"
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
    ):
        raise EdgeConneXPublicationError("accepted manifest contract differs")
    rows = manifest.get("files")
    if not isinstance(rows, list) or [row.get("path") for row in rows] != list(
        CONTENT_FILES
    ):
        raise EdgeConneXPublicationError("accepted manifest inventory differs")
    for row in rows:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (
            row["bytes"],
            row["sha256"],
        ):
            raise EdgeConneXPublicationError(
                f"accepted manifest pin differs: {row['path']}"
            )
    if manifest["tree_sha256"] != _sha256_bytes(_canonical(rows)):
        raise EdgeConneXPublicationError("accepted logical tree differs")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise EdgeConneXPublicationError("accepted manifest checksum differs")

    expected_payloads = _artifact_documents(
        manifest["recorded_at"], document, source_payload
    )
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected_payloads[name]:
            raise EdgeConneXPublicationError(f"artifact content differs: {name}")
    source_record = _validate_source(source, document, source_payload, frozen=frozen)
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot.get("source_records") != [source_record]:
        raise EdgeConneXPublicationError("accepted source record differs")
    assessment = json.loads(
        entries["acceptance-assessment.json"].read_text(encoding="utf-8")
    )
    accepted_rows = [row for row in assessment["assessments"] if row["accepted"]]
    if (
        len(accepted_rows) != 1
        or accepted_rows[0]["assessment_id"] != ACCEPTED_ASSESSMENT_ID
        or len(assessment["assessments"]) != 10
    ):
        raise EdgeConneXPublicationError("accepted assessment set differs")
    for path in entries.values():
        _assert_publication_clean(path.read_text(encoding="utf-8"))

    target = _instant(manifest["recorded_at"])
    if require_live and datetime.now(UTC) < target:
        raise EdgeConneXPublicationError("accepted recorded_at is not live")
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
    source_payload: bytes
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
        raise EdgeConneXPublicationError(f"final-path collision: {present!r}")


def _discard_owned_tree(
    root: Path,
    *,
    expected: Mapping[str, tuple[int, int, str]] | None = None,
) -> None:
    identities = _tree_identities(root)
    if expected is not None and identities != dict(expected):
        raise EdgeConneXPublicationError(
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
            raise EdgeConneXPublicationError(
                f"refusing identity-mismatched stage cleanup: {directory}"
            )
        directory.chmod(0o700)
    for path in [
        path for path in root.rglob("*") if path.is_file() and not path.is_symlink()
    ]:
        relative = path.relative_to(root).as_posix()
        if not _has_identity(path, identities[relative][:2], directory=False):
            raise EdgeConneXPublicationError(
                f"refusing identity-mismatched stage cleanup: {path}"
            )
        path.unlink()
    for directory in sorted(
        directories, key=lambda item: len(item.parts), reverse=True
    ):
        relative = "." if directory == root else directory.relative_to(root).as_posix()
        if not _has_identity(directory, identities[relative][:2], directory=True):
            raise EdgeConneXPublicationError(
                f"refusing identity-mismatched stage cleanup: {directory}"
            )
        directory.rmdir()


def _prepare(recorded_at: str) -> PreparedPublication:
    _assert_final_absent()
    target = _instant(recorded_at)
    if datetime.now(UTC) >= target:
        raise EdgeConneXPublicationError("recorded_at must be future before staging")
    reviewed_identities = _validate_reviewed_inputs()
    source_payload = expected_source_bytes()
    document = json.loads(source_payload)
    source_stage = Path(
        tempfile.mkdtemp(
            prefix=".edgeconnex-lambda-current-build-source-stage-",
            dir=SOURCES_ROOT,
        )
    )
    source_root_identity: tuple[int, int] | None = None
    artifact_stage: Path | None = None
    artifact_root_identity: tuple[int, int] | None = None
    try:
        source_root_identity = _identity(source_stage, directory=True)
        artifact_stage = Path(
            tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.stage-", dir=ARTIFACT_ROOT)
        )
        artifact_root_identity = _identity(artifact_stage, directory=True)
        if source_root_identity[0] != _identity(SOURCES_ROOT, directory=True)[0]:
            raise EdgeConneXPublicationError("source stage is not on source filesystem")
        if artifact_root_identity[0] != _identity(ARTIFACT_ROOT, directory=True)[0]:
            raise EdgeConneXPublicationError(
                "artifact stage is not on artifact filesystem"
            )
        _write_source_stage(source_stage, source_payload)
        _write_artifact_stage(artifact_stage, recorded_at, document, source_payload)
        _assert_stage_precedes(source_stage, target)
        _assert_stage_precedes(artifact_stage, target)
        source_identities = _tree_identities(source_stage)
        artifact_identities = _tree_identities(artifact_stage)
        source_tree = _content_tree_sha256(source_stage)
        artifact_tree = _content_tree_sha256(artifact_stage)
        _offline_import(source_stage / SOURCE_FILENAME, recorded_at)
        _validate_artifact(
            artifact_stage,
            source_stage / SOURCE_FILENAME,
            frozen=False,
            require_live=False,
            require_final_chronology=False,
            document=document,
            source_payload=source_payload,
        )
        _assert_tree_identities(source_stage, source_identities)
        _assert_tree_identities(artifact_stage, artifact_identities)
        _assert_reviewed_input_identities(reviewed_identities)
        return PreparedPublication(
            source_stage,
            artifact_stage,
            recorded_at,
            document,
            source_payload,
            source_identities,
            artifact_identities,
            reviewed_identities,
            source_tree,
            artifact_tree,
        )
    except BaseException:
        if source_root_identity is None:
            try:
                source_root_identity = _identity(source_stage, directory=True)
            except (FileNotFoundError, EdgeConneXPublicationError, OSError):
                pass
        if source_root_identity is not None and _has_identity(
            source_stage, source_root_identity, directory=True
        ):
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
        raise EdgeConneXPublicationError("prepared source tree differs")
    if _content_tree_sha256(prepared.artifact_stage) != prepared.artifact_tree_sha256:
        raise EdgeConneXPublicationError("prepared artifact tree differs")
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
        source_payload=prepared.source_payload,
    )


def preflight(*, recorded_at: str | None = None) -> dict[str, Any]:
    """Render, import exactly twice, freeze, validate, and discard."""

    target = (
        _instant(recorded_at)
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=30)
    )
    if datetime.now(UTC) >= target:
        raise EdgeConneXPublicationError("preflight recorded_at must be future")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    prepared = _prepare(timestamp)
    source_stage = prepared.source_stage
    artifact_stage = prepared.artifact_stage
    try:
        _assert_prepared_exact(prepared, frozen=False)
        _freeze_stages(source_stage, artifact_stage)
        _assert_prepared_exact(prepared, frozen=True)
        source_path = source_stage / SOURCE_FILENAME
        result = {
            "status": "PREFLIGHT_VALIDATED_AND_DISCARDED",
            "recorded_at": timestamp,
            "artifact_id": ARTIFACT_ID,
            "artifact_manifest_sha256": _sha256(artifact_stage / "manifest.json"),
            "artifact_tree_sha256": tree_digest(artifact_stage),
            "artifact_pins": [
                {
                    "path": name,
                    "bytes": (artifact_stage / name).stat().st_size,
                    "sha256": _sha256(artifact_stage / name),
                }
                for name in sorted(CLOSED_FILES)
            ],
            "source_tree_sha256": tree_digest(source_stage),
            "source_pins": [
                {
                    "path": f"sources/{SOURCE_FILENAME}",
                    "bytes": source_path.stat().st_size,
                    "sha256": _sha256(source_path),
                }
            ],
            "modes": {
                "source_file": "0444",
                "artifact_directory": "0555",
                "artifact_files": "0444",
                "reviewed_source_directory": "0700",
                "reviewed_source_files": "0600",
                "reviewed_artifact_directory": "0700",
                "reviewed_artifact_files": "0600",
                "capture_clone_directory": "0555",
                "capture_clone_files": "0444",
            },
            "rows": {
                "entities": 2,
                "entity_snapshots": 2,
                "evidence": 3,
                "lifecycle": 1,
                "operating_models": 0,
                "workloads": 3,
                "capacities": 0,
                "coordinates": 0,
                "geometry": 0,
                "current_consumption": 0,
                "annual_energy": 0,
            },
            "offline_imports": 2,
            "published": False,
        }
    finally:
        if source_stage.exists():
            _discard_owned_tree(source_stage, expected=prepared.source_identities)
        if artifact_stage.exists():
            _discard_owned_tree(artifact_stage, expected=prepared.artifact_identities)
    _assert_final_absent()
    retained_inputs = _validate_reviewed_inputs()
    result["source_stage_discarded"] = not source_stage.exists()
    result["artifact_stage_discarded"] = not artifact_stage.exists()
    result["reviewed_source_stage_retained"] = REVIEWED_SOURCE_STAGE.exists()
    result["reviewed_artifact_stage_retained"] = REVIEWED_ARTIFACT_STAGE.exists()
    result["capture_clone_retained"] = retained_inputs.capture_path is not None
    result["capture_storage_location_redacted"] = True
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
        raise EdgeConneXPublicationError(str(error)) from error


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
            raise EdgeConneXPublicationError("promoted source identity differs")
        promoted.append((_final_source(), staged_source, source_identity, False))

        artifact_identity = _identity(prepared.artifact_stage, directory=True)
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        if not _has_identity(ARTIFACT, artifact_identity, directory=True):
            raise EdgeConneXPublicationError("promoted artifact identity differs")
        _assert_tree_identities(ARTIFACT, prepared.artifact_identities)
        promoted.append((ARTIFACT, prepared.artifact_stage, artifact_identity, True))
        _validate_artifact(
            ARTIFACT,
            _final_source(),
            frozen=True,
            require_live=True,
            require_final_chronology=True,
            document=prepared.document,
            source_payload=prepared.source_payload,
        )
        _assert_reviewed_input_identities(prepared.reviewed_input_identities)
    except BaseException as error:
        for final, staged, identity, directory in reversed(promoted):
            try:
                if not _has_identity(final, identity, directory=directory):
                    raise EdgeConneXPublicationError(
                        f"refusing identity-mismatched rollback: {final}"
                    )
                _promote_noreplace(final, staged)
                if not _has_identity(staged, identity, directory=directory):
                    raise EdgeConneXPublicationError(
                        f"rolled-back identity differs: {staged}"
                    )
            except Exception as rollback_error:
                error.add_note(
                    f"EdgeConneX/Lambda rollback failed for {final}: {rollback_error}"
                )
        raise


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise EdgeConneXPublicationError(
            "active EdgeConneX/Lambda publication lock exists"
        ) from error
    identity: tuple[int, int] | None = None
    try:
        metadata = os.fstat(descriptor)
        identity = (metadata.st_dev, metadata.st_ino)
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        if identity is None:
            try:
                metadata = os.fstat(descriptor)
                identity = (metadata.st_dev, metadata.st_ino)
            except OSError:
                pass
        os.close(descriptor)
        if identity is None:
            raise EdgeConneXPublicationError(
                "publication lock identity could not be established"
            )
        try:
            current = PUBLICATION_LOCK.stat(follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if (
                not stat.S_ISREG(current.st_mode)
                or (current.st_dev, current.st_ino) != identity
            ):
                raise EdgeConneXPublicationError(
                    "refusing substituted EdgeConneX/Lambda lock cleanup"
                )
            PUBLICATION_LOCK.unlink()


def _existing_identical(recorded_at: str | None) -> dict[str, Any]:
    manifest = json.loads((ARTIFACT / "manifest.json").read_text(encoding="utf-8"))
    existing_recorded_at = manifest.get("recorded_at")
    if not isinstance(existing_recorded_at, str):
        raise EdgeConneXPublicationError("existing recorded_at is missing")
    if recorded_at is not None and recorded_at != existing_recorded_at:
        raise EdgeConneXPublicationError("existing recorded_at differs")
    identities = _validate_reviewed_inputs()
    source_payload = expected_source_bytes()
    document = json.loads(source_payload)
    _offline_import(_final_source(), existing_recorded_at)
    _validate_artifact(
        ARTIFACT,
        _final_source(),
        frozen=True,
        require_live=True,
        require_final_chronology=True,
        document=document,
        source_payload=source_payload,
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
        "review_only_assessments": 9,
        "capture_clone_retained": identities.capture_path is not None,
        "capture_storage_location_redacted": True,
    }


def validate_published() -> dict[str, Any]:
    """Validate a complete accepted final and reject missing or partial state."""

    complete, present = _final_presence()
    if not complete:
        if present:
            raise EdgeConneXPublicationError(
                f"partial final-path collision: {present!r}"
            )
        raise EdgeConneXPublicationError("accepted final is absent")
    return _existing_identical(None)


def build(
    *,
    recorded_at: str | None = None,
    publication_authorized: bool = False,
) -> dict[str, Any]:
    """Publish only with explicit authorization; otherwise fail closed."""

    if not publication_authorized:
        raise EdgeConneXPublicationError(
            "EdgeConneX/Lambda publication requires publication_authorized=True"
        )
    complete, present = _final_presence()
    if complete:
        return _existing_identical(recorded_at)
    if present:
        raise EdgeConneXPublicationError(f"partial final-path collision: {present!r}")

    target = (
        _instant(recorded_at)
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise EdgeConneXPublicationError(
            "recorded_at must be future before publication"
        )
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
                    prepared.source_stage, expected=prepared.source_identities
                )
            if prepared.artifact_stage.exists():
                _discard_owned_tree(
                    prepared.artifact_stage, expected=prepared.artifact_identities
                )
            raise
        if prepared.source_stage.exists():
            if any(prepared.source_stage.iterdir()):
                raise EdgeConneXPublicationError(
                    "source stage not empty after publication"
                )
            root_identity = prepared.source_identities["."][:2]
            if not _has_identity(prepared.source_stage, root_identity, directory=True):
                raise EdgeConneXPublicationError("source stage identity differs")
            prepared.source_stage.rmdir()
        manifest = _validate_artifact(
            ARTIFACT,
            _final_source(),
            frozen=True,
            require_live=True,
            require_final_chronology=True,
            document=prepared.document,
            source_payload=prepared.source_payload,
        )
    return {
        "status": "published",
        "artifact": str(ARTIFACT),
        "recorded_at": manifest["recorded_at"],
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "published": True,
        "accepted_source_records": 1,
        "review_only_assessments": 9,
        "capture_clone_retained": (
            prepared.reviewed_input_identities.capture_path is not None
        ),
        "capture_storage_location_redacted": True,
    }


def main() -> int:
    print(json.dumps(preflight(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
