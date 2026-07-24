"""Accepted-format publisher for the reviewed Nordic current-build tranche.

The final records cover XTX Markets' second Kajaani data center, Skygard OSL1
phase 2, and an evidence/currentness successor for atNorth FIN04 phase 1.  The
module never fetches the network.  It requires byte-exact reviewed candidate
stages and the frozen raw-capture bundle, renders distinct accepted final
bytes, and refuses publication unless ``publication_authorized=True``.

``preflight`` is the safe default workflow: it renders the exact final source
and artifact bytes in unique sibling stages, imports every source twice,
freezes and validates the stages, reports their pins, and identity-safely
discards them.  It does not create any final path.
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
from .open_seed_v56 import tree_digest
from .open_seed_v69 import promote_noreplace
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "official-nordic-current-build-tranche-2026-07-22-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".official-nordic-current-build-tranche.lock"

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

REVIEWED_CANDIDATE_ID = "official-nordic-tranche-prepublication-2026-07-22-v1"
REVIEWED_SOURCE_STAGE = (
    SOURCES_ROOT / ".official-nordic-prepublication-sources.ifskx9ae"
)
REVIEWED_ARTIFACT_STAGE = (
    ARTIFACT_ROOT / ".official-nordic-tranche-prepublication-2026-07-22-v1.88kkj_4s"
)
RAW_CAPTURE = Path("/private/tmp/dc-nordic-prepublication-20260722.jN0cUf")

REVIEWED_SOURCE_TREE_SHA256 = (
    "eae64483e9434f159bb757807903fbdfa92069e3d3799f84d95fa3eff6267e87"
)
REVIEWED_ARTIFACT_TREE_SHA256 = (
    "cb4c0c3430128ec8d20444eca7556686cccb929a07ccf1057c5750efec9c817c"
)
RAW_CAPTURE_TREE_SHA256 = (
    "2021d6ee7a32bf90bc20e6a682b734498fae741df861b856fd755e693965747b"
)

REVIEWED_SOURCE_PINS: Mapping[str, tuple[int, str]] = {
    XTX_SOURCE_FILENAME: (
        7_795,
        "b7332e6c57f3713a7fc8c5b714cb4e5d0cfeb257237e7416d9049594ee5068b0",
    ),
    SKYGARD_SOURCE_FILENAME: (
        7_154,
        "5b264dbd7347f0876ad5885f56d09573e157796d510ecc374a68b9e0ae63774e",
    ),
    FIN04_SOURCE_FILENAME: (
        19_174,
        "5429866aa3ca71ef8b1ec1e4d250eb0fb00ad724c0d8782a2d71742f4f910d54",
    ),
}

REVIEWED_ARTIFACT_PINS: Mapping[str, tuple[int, str]] = {
    "README.md": (
        1_871,
        "5b2d1e992c088b645906ea94c245a24ed6e6740f8b2d70a61cea48f4341b65eb",
    ),
    "candidate-assessment.json": (
        3_130,
        "9dc03f7f8af09d0ef0fcc5f0524898dcaf22b4ac98b50bda16e7cfca6fd00e6d",
    ),
    "manifest.json": (
        1_592,
        "f5539f3dea41054c65dee18bde231a722859ab716289c8398300d03a318ae2c6",
    ),
    "manifest.sha256": (
        80,
        "1ab10629012d2d3af0d79a9eca813214660eaa61e73ceb300a33088e16d9136e",
    ),
    "retrieval-inventory.json": (
        8_347,
        "38168faf242e9b8cc60b9aeb743c1ca6e3ae01293001e87a109fbfa01f8063f8",
    ),
    "rights-and-disposition.json": (
        1_009,
        "43af1cb740c2f8a8b07b6bc310cb4a234ae0d432c526233ed18fced7563e62b4",
    ),
    "source-snapshot.json": (
        4_910,
        "36ae94f7d12a99f1f3043712e6b933eb392500a6868568e0868e30187dda346a",
    ),
}

RAW_CAPTURE_PINS: Mapping[str, tuple[int, str]] = {
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

XTX_CAMPUS_KEY = "curated:xtx-markets-kajaani-data-center-campus"
XTX_PROJECT_KEY = f"{XTX_CAMPUS_KEY}:second-data-center"
SKYGARD_CAMPUS_KEY = "curated:skygard-osl1-hovinbyen-campus"
SKYGARD_PROJECT_KEY = f"{SKYGARD_CAMPUS_KEY}:phase-2"
FIN04_CAMPUS_KEY = "curated:atnorth-fin04-kouvola-campus"
FIN04_PROJECT_KEY = f"{FIN04_CAMPUS_KEY}:phase-1"


class NordicPublicationError(RuntimeError):
    """Fail-closed publication error."""


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
        raise NordicPublicationError("recorded_at must be ISO 8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise NordicPublicationError("recorded_at must be timezone aware")
    return parsed.astimezone(UTC)


def _pin(path: Path, expected: tuple[int, str], *, mode: int) -> None:
    if path.is_symlink() or not path.is_file():
        raise NordicPublicationError(f"missing or unsafe pinned input: {path}")
    metadata = path.stat(follow_symlinks=False)
    actual = (metadata.st_size, _sha256(path))
    if actual != expected:
        raise NordicPublicationError(f"pinned input differs: {path}")
    if stat.S_IMODE(metadata.st_mode) != mode:
        raise NordicPublicationError(f"pinned input mode differs: {path}")


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
        raise NordicPublicationError(f"symlink is not allowed: {path}")
    metadata = path.stat(follow_symlinks=False)
    if directory is True and not stat.S_ISDIR(metadata.st_mode):
        raise NordicPublicationError(f"expected directory: {path}")
    if directory is False and not stat.S_ISREG(metadata.st_mode):
        raise NordicPublicationError(f"expected regular file: {path}")
    return metadata.st_dev, metadata.st_ino


def _has_identity(
    path: Path, expected: tuple[int, int], *, directory: bool | None = None
) -> bool:
    try:
        return _identity(path, directory=directory) == expected
    except (FileNotFoundError, NordicPublicationError):
        return False


def _tree_identities(root: Path) -> dict[str, tuple[int, int, str]]:
    if root.is_symlink() or not root.is_dir():
        raise NordicPublicationError(f"unsafe tree root: {root}")
    result: dict[str, tuple[int, int, str]] = {}
    for candidate in (root, *sorted(root.rglob("*"))):
        if candidate.is_symlink():
            raise NordicPublicationError(f"symlink in governed tree: {candidate}")
        metadata = candidate.stat(follow_symlinks=False)
        kind = (
            "directory"
            if stat.S_ISDIR(metadata.st_mode)
            else "file"
            if stat.S_ISREG(metadata.st_mode)
            else "other"
        )
        if kind == "other":
            raise NordicPublicationError(f"special file in governed tree: {candidate}")
        relative = "." if candidate == root else candidate.relative_to(root).as_posix()
        result[relative] = (metadata.st_dev, metadata.st_ino, kind)
    return result


def _assert_tree_identities(
    root: Path, expected: Mapping[str, tuple[int, int, str]]
) -> None:
    if _tree_identities(root) != dict(expected):
        raise NordicPublicationError(f"tree identity changed: {root}")


@dataclass(frozen=True)
class ReviewedInputIdentities:
    sources: Mapping[str, tuple[int, int, str]]
    artifact: Mapping[str, tuple[int, int, str]]
    captures: Mapping[str, tuple[int, int, str]]


def _validate_reviewed_inputs() -> ReviewedInputIdentities:
    if (
        REVIEWED_SOURCE_STAGE.is_symlink()
        or not REVIEWED_SOURCE_STAGE.is_dir()
        or stat.S_IMODE(REVIEWED_SOURCE_STAGE.stat().st_mode) != 0o700
    ):
        raise NordicPublicationError("reviewed source stage is missing or unsafe")
    source_entries = {path.name: path for path in REVIEWED_SOURCE_STAGE.iterdir()}
    if set(source_entries) != set(REVIEWED_SOURCE_PINS):
        raise NordicPublicationError("reviewed source stage inventory differs")
    for name, pin in REVIEWED_SOURCE_PINS.items():
        _pin(source_entries[name], pin, mode=0o600)
    if tree_digest(REVIEWED_SOURCE_STAGE) != REVIEWED_SOURCE_TREE_SHA256:
        raise NordicPublicationError("reviewed source stage tree differs")

    if (
        REVIEWED_ARTIFACT_STAGE.is_symlink()
        or not REVIEWED_ARTIFACT_STAGE.is_dir()
        or stat.S_IMODE(REVIEWED_ARTIFACT_STAGE.stat().st_mode) != 0o700
    ):
        raise NordicPublicationError("reviewed artifact stage is missing or unsafe")
    artifact_entries = {path.name: path for path in REVIEWED_ARTIFACT_STAGE.iterdir()}
    if set(artifact_entries) != set(REVIEWED_ARTIFACT_PINS):
        raise NordicPublicationError("reviewed artifact stage inventory differs")
    for name, pin in REVIEWED_ARTIFACT_PINS.items():
        _pin(artifact_entries[name], pin, mode=0o600)
    if tree_digest(REVIEWED_ARTIFACT_STAGE) != REVIEWED_ARTIFACT_TREE_SHA256:
        raise NordicPublicationError("reviewed artifact stage tree differs")
    reviewed_manifest = json.loads(
        artifact_entries["manifest.json"].read_text(encoding="utf-8")
    )
    if (
        reviewed_manifest.get("artifact_id") != REVIEWED_CANDIDATE_ID
        or reviewed_manifest.get("published") is not False
        or reviewed_manifest.get("recorded_at") != "2026-07-22T04:20:11Z"
    ):
        raise NordicPublicationError("reviewed candidate manifest differs")
    if artifact_entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{REVIEWED_ARTIFACT_PINS['manifest.json'][1]}  manifest.json\n"
    ):
        raise NordicPublicationError("reviewed candidate checksum differs")

    if (
        RAW_CAPTURE.is_symlink()
        or not RAW_CAPTURE.is_dir()
        or stat.S_IMODE(RAW_CAPTURE.stat().st_mode) != 0o700
    ):
        raise NordicPublicationError("raw capture bundle is missing or unsafe")
    raw_entries = {path.name: path for path in RAW_CAPTURE.iterdir()}
    if set(raw_entries) != set(RAW_CAPTURE_PINS):
        raise NordicPublicationError("raw capture inventory differs")
    for name, pin in RAW_CAPTURE_PINS.items():
        _pin(raw_entries[name], pin, mode=0o444)
    if tree_digest(RAW_CAPTURE) != RAW_CAPTURE_TREE_SHA256:
        raise NordicPublicationError("raw capture tree differs")

    identities = ReviewedInputIdentities(
        _tree_identities(REVIEWED_SOURCE_STAGE),
        _tree_identities(REVIEWED_ARTIFACT_STAGE),
        _tree_identities(RAW_CAPTURE),
    )
    _assert_tree_identities(REVIEWED_SOURCE_STAGE, identities.sources)
    _assert_tree_identities(REVIEWED_ARTIFACT_STAGE, identities.artifact)
    _assert_tree_identities(RAW_CAPTURE, identities.captures)
    return identities


def _assert_reviewed_input_identities(
    identities: ReviewedInputIdentities,
) -> None:
    _assert_tree_identities(REVIEWED_SOURCE_STAGE, identities.sources)
    _assert_tree_identities(REVIEWED_ARTIFACT_STAGE, identities.artifact)
    _assert_tree_identities(RAW_CAPTURE, identities.captures)


def _load_reviewed_documents() -> dict[str, dict[str, Any]]:
    identities = _validate_reviewed_inputs()
    documents: dict[str, dict[str, Any]] = {}
    for name in SOURCE_FILENAMES:
        document = json.loads(
            (REVIEWED_SOURCE_STAGE / name).read_text(encoding="utf-8")
        )
        if document.get("schema_version") != "1.1":
            raise NordicPublicationError(f"reviewed source schema differs: {name}")
        accepted = copy.deepcopy(document)
        for evidence in accepted["evidence"]:
            metadata = evidence.get("metadata")
            if (
                isinstance(metadata, dict)
                and metadata.get("capture_artifact_id") == REVIEWED_CANDIDATE_ID
            ):
                metadata["capture_artifact_id"] = ARTIFACT_ID
        documents[name] = accepted
    _assert_reviewed_input_identities(identities)
    _assert_no_candidate_language(documents)
    return documents


def expected_source_documents() -> dict[str, dict[str, Any]]:
    return _load_reviewed_documents()


def _source_records(
    documents: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    dispositions = {
        XTX_SOURCE_FILENAME: "accepted_official_second_facility_current_build",
        SKYGARD_SOURCE_FILENAME: "accepted_official_phase_2_current_build",
        FIN04_SOURCE_FILENAME: "accepted_official_existing_phase_currentness_successor",
    }
    rows = []
    for name in SOURCE_FILENAMES:
        document = documents[name]
        payload = _canonical(document)
        rows.append(
            {
                "path": f"sources/{name}",
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
                    document[entity]["geometry"] is not None
                    for entity in ("campus", "project")
                ),
                "disposition": dispositions[name],
                "accepted": True,
                "published": True,
                "seeded": False,
            }
        )
    return rows


def _accepted_assessment(recorded_at: str) -> dict[str, Any]:
    reviewed = json.loads(
        (REVIEWED_ARTIFACT_STAGE / "candidate-assessment.json").read_text(
            encoding="utf-8"
        )
    )
    rows = copy.deepcopy(reviewed["candidates"])
    accepted = {
        "xtx-kajaani-second-data-center": XTX_SOURCE_FILENAME,
        "skygard-osl1-phase-2": SKYGARD_SOURCE_FILENAME,
        "atnorth-fin04-currentness-successor": FIN04_SOURCE_FILENAME,
    }
    for row in rows:
        candidate_id = row["candidate_id"]
        if candidate_id in accepted:
            row["decision"] = (
                "accepted_official_existing_phase_successor"
                if candidate_id == "atnorth-fin04-currentness-successor"
                else "accepted_official_current_build"
            )
            row["source_paths"] = [f"sources/{accepted[candidate_id]}"]
            row["accepted"] = True
            row["published"] = True
        else:
            row["accepted"] = False
            row["published"] = False
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-current-build-assessment-v1",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "candidate_count": 4,
        "accepted_source_record_count": 3,
        "published_source_record_count": 3,
        "review_only_count": 1,
        "regional_completeness_claimed": False,
        "candidates": rows,
    }


def _retrieval_inventory(recorded_at: str) -> dict[str, Any]:
    reviewed = json.loads(
        (REVIEWED_ARTIFACT_STAGE / "retrieval-inventory.json").read_text(
            encoding="utf-8"
        )
    )
    reviewed["artifact_id"] = ARTIFACT_ID
    reviewed["recorded_at"] = recorded_at
    reviewed.pop("capture_directory", None)
    reviewed["raw_capture_storage_path_redacted"] = True
    reviewed["raw_capture_retained_private"] = True
    reviewed["raw_capture_redistributed"] = False
    return reviewed


def _reviewed_candidate_lineage() -> dict[str, Any]:
    return {
        "purpose": "reviewed_candidate_input_lineage_only",
        "artifact_id": REVIEWED_CANDIDATE_ID,
        "artifact_stage": str(REVIEWED_ARTIFACT_STAGE),
        "artifact_manifest_sha256": REVIEWED_ARTIFACT_PINS["manifest.json"][1],
        "artifact_tree_sha256": REVIEWED_ARTIFACT_TREE_SHA256,
        "source_stage": str(REVIEWED_SOURCE_STAGE),
        "source_tree_sha256": REVIEWED_SOURCE_TREE_SHA256,
        "source_files": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in REVIEWED_SOURCE_PINS.items()
        ],
        "raw_capture_directory": str(RAW_CAPTURE),
        "raw_capture_file_count": len(RAW_CAPTURE_PINS),
        "raw_capture_total_bytes": sum(pin[0] for pin in RAW_CAPTURE_PINS.values()),
        "raw_capture_tree_sha256": RAW_CAPTURE_TREE_SHA256,
        "semantic_review_decision": (
            "accepted_without_capacity_workload_coordinate_or_geometry_expansion"
        ),
        "direct_promotion_of_candidate_bytes": False,
    }


def _artifact_documents(
    recorded_at: str,
    documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    source_records = _source_records(documents)
    assessment = _accepted_assessment(recorded_at)
    readme = f"""# Nordic official current-build tranche

This immutable accepted source artifact publishes three official-source records at {recorded_at}: XTX Markets' second Kajaani data center, Skygard OSL1 phase 2, and an evidence/currentness successor for the existing atNorth FIN04 phase-1 record.

The records contain six entity snapshots, eight evidence rows, and three `under_construction` lifecycle observations. They contain zero operating-model, workload, capacity, coordinate, geometry, satellite, aerial, map-derived, or computer-vision rows. XTX's 22.5 MW applies only to its first Kajaani facility and is not copied to the second. Skygard's 20 MW and PUE describe OSL1 as a whole and are not allocated to phase 2. YIT's 430 MW remains untyped planned capacity for the entire FIN04 campus. Renewable-power, heat-reuse, AI, and HPC language creates no consumption, annual-energy, efficiency, workload, tenant, or active-compute claim.

XTX's third Kajaani facility remains review-only with no stable key or lifecycle row. FIN04 reuses the exact existing campus and phase-1 keys, preserves the predecessor evidence, and adds no phase. Skygard identity/locality comes from its official OSL1 page; the dated phase-2 physical-start observation comes from Sentia. No street address, Google Maps result, coordinate, parcel, or imagery inference is used.

Publication is limited to the three source files and this artifact. No open-seed successor, release, federation, identity, timeline, construction-master, map, coverage, or other downstream file is created or modified. The frozen official response bundle remains private and is not redistributed.
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
            "accepted_source_records": 3,
            "published_source_records": 3,
            "review_only_candidates": 1,
            "distinct_campuses": 3,
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
        "reviewed_candidate_lineage": _reviewed_candidate_lineage(),
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
            "unique_sibling_stages": True,
            "lock_required": True,
            "future_recorded_at_required": True,
            "wait_live_before_freeze": True,
            "recursive_inode_recheck_before_freeze": True,
            "byte_and_tree_recheck_before_and_after_freeze": True,
            "atomic_no_replace_promotion": True,
            "identity_checked_rollback": True,
            "all_recursive_stage_birthtimes_and_mtimes_at_or_before_recorded_at": True,
            "all_recursive_final_ctimes_at_or_after_recorded_at": True,
            "source_file_mode": "0444",
            "artifact_file_mode": "0444",
            "artifact_directory_mode": "0555",
            "existing_identical_replay": True,
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
    _assert_no_candidate_language(
        {
            name: json.loads(raw)
            for name, raw in payloads.items()
            if name.endswith(".json")
        },
        allow_lineage=True,
    )
    return payloads


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


def _assert_no_candidate_language(value: Any, *, allow_lineage: bool = False) -> None:
    for path, text in _walk_strings(value):
        lowered = text.lower()
        if "prospective-sources/" in lowered:
            raise NordicPublicationError(f"prospective source path leaked at {path!r}")
        if "prepublication" in lowered:
            if allow_lineage and "reviewed_candidate_lineage" in path:
                continue
            raise NordicPublicationError(f"candidate language leaked at {path!r}")


def _offline_import(
    source_paths: Mapping[str, Path], recorded_at: str
) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="nordic-accepted-import-", dir="/private/tmp"
    ) as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            for name in SOURCE_FILENAMES:
                adapter.import_file(
                    connection, source_paths[name], recorded_at=recorded_at
                )
        errors = validate_database(connection)
        if errors:
            raise NordicPublicationError(
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
            "entities": 6,
            "entity_snapshots": 6,
            "evidence": 8,
            "lifecycle_observations": 3,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
        }
        if counts != expected:
            raise NordicPublicationError(f"offline import counts differ: {counts!r}")
        return counts


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def _write_new_file(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _write_source_stage(
    stage: Path, documents: Mapping[str, Mapping[str, Any]]
) -> None:
    for name in SOURCE_FILENAMES:
        _write_new_file(stage / name, _canonical(documents[name]))
    stage.chmod(0o700)
    _fsync_directory(stage)


def _write_artifact_stage(
    stage: Path,
    recorded_at: str,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    payloads = _artifact_documents(recorded_at, documents)
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
        "accepted_source_records": 3,
        "published_source_records": 3,
        "review_only_candidates": 1,
        "successful_http_200_body_captures": 6,
        "raw_capture_redistributed": False,
        "published": True,
        "accepted": True,
        "regional_completeness_claimed": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
    }
    manifest_path = stage / "manifest.json"
    _write_new_file(manifest_path, _canonical(manifest))
    _write_new_file(
        stage / "manifest.sha256",
        f"{_sha256(manifest_path)}  manifest.json\n".encode("utf-8"),
    )
    stage.chmod(0o700)
    _fsync_directory(stage)


def _assert_stage_precedes(root: Path, target: datetime) -> None:
    for candidate in (root, *root.rglob("*")):
        metadata = candidate.stat(follow_symlinks=False)
        birthtime = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if max(birthtime, metadata.st_mtime) > target.timestamp() + 0.000_001:
            raise NordicPublicationError(
                f"private stage post-dates recorded_at: {candidate}"
            )


def _assert_recursive_ctimes_at_or_after(root: Path, target: datetime) -> None:
    for candidate in (root, *root.rglob("*")):
        if (
            candidate.stat(follow_symlinks=False).st_ctime + 0.000_001
            < target.timestamp()
        ):
            raise NordicPublicationError(
                f"final member ctime predates recorded_at: {candidate}"
            )


def _freeze_stages(source_stage: Path, artifact_stage: Path) -> None:
    for path in source_stage.iterdir():
        path.chmod(0o444)
        _fsync_regular(path)
    _fsync_directory(source_stage)
    for path in artifact_stage.iterdir():
        path.chmod(0o444)
        _fsync_regular(path)
    artifact_stage.chmod(0o555)
    _fsync_directory(artifact_stage)


def _validate_sources(
    paths: Mapping[str, Path],
    documents: Mapping[str, Mapping[str, Any]],
    *,
    frozen: bool,
    recorded_at: str,
) -> list[dict[str, Any]]:
    if set(paths) != set(SOURCE_FILENAMES):
        raise NordicPublicationError("accepted source inventory differs")
    expected_mode = 0o444 if frozen else 0o600
    for name in SOURCE_FILENAMES:
        path = paths[name]
        if path.is_symlink() or not path.is_file():
            raise NordicPublicationError(
                f"accepted source is missing or unsafe: {name}"
            )
        if stat.S_IMODE(path.stat().st_mode) != expected_mode:
            raise NordicPublicationError(f"accepted source mode differs: {name}")
        if path.read_bytes() != _canonical(documents[name]):
            raise NordicPublicationError(f"accepted source differs: {name}")
    _offline_import(paths, recorded_at)
    return _source_records(documents)


def _validate_artifact(
    artifact: Path,
    source_paths: Mapping[str, Path],
    *,
    frozen: bool,
    require_live: bool,
    require_final_chronology: bool,
    documents: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    documents = dict(documents or expected_source_documents())
    if artifact.is_symlink() or not artifact.is_dir():
        raise NordicPublicationError("accepted artifact is missing or unsafe")
    expected_directory_mode = 0o555 if frozen else 0o700
    expected_file_mode = 0o444 if frozen else 0o600
    if stat.S_IMODE(artifact.stat().st_mode) != expected_directory_mode:
        raise NordicPublicationError("accepted artifact directory mode differs")
    entries = {path.name: path for path in artifact.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise NordicPublicationError("accepted artifact closed file set differs")
    for name, path in entries.items():
        if path.is_symlink() or not path.is_file():
            raise NordicPublicationError(f"unsafe accepted artifact member: {name}")
        if stat.S_IMODE(path.stat().st_mode) != expected_file_mode:
            raise NordicPublicationError(
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
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
    ):
        raise NordicPublicationError("accepted manifest contract differs")
    rows = manifest.get("files")
    if not isinstance(rows, list) or [row.get("path") for row in rows] != list(
        CONTENT_FILES
    ):
        raise NordicPublicationError("accepted manifest inventory differs")
    for row in rows:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (
            row["bytes"],
            row["sha256"],
        ):
            raise NordicPublicationError(
                f"accepted manifest pin differs: {row['path']}"
            )
    if manifest["tree_sha256"] != _sha256_bytes(_canonical(rows)):
        raise NordicPublicationError("accepted logical tree differs")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise NordicPublicationError("accepted manifest checksum differs")
    expected_payloads = _artifact_documents(manifest["recorded_at"], documents)
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected_payloads[name]:
            raise NordicPublicationError(f"accepted artifact content differs: {name}")
    source_records = _validate_sources(
        source_paths,
        documents,
        frozen=frozen,
        recorded_at=manifest["recorded_at"],
    )
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records:
        raise NordicPublicationError("accepted source pins differ")
    _assert_no_candidate_language(snapshot, allow_lineage=True)
    assessment = json.loads(
        entries["candidate-assessment.json"].read_text(encoding="utf-8")
    )
    _assert_no_candidate_language(assessment)
    target = _instant(manifest["recorded_at"])
    if require_live and datetime.now(UTC) < target:
        raise NordicPublicationError("accepted recorded_at is not live")
    if require_final_chronology:
        _assert_stage_precedes(artifact, target)
        _assert_recursive_ctimes_at_or_after(artifact, target)
        for path in source_paths.values():
            _assert_stage_precedes(path, target)
            _assert_recursive_ctimes_at_or_after(path, target)
    return manifest


@dataclass(frozen=True)
class PreparedPublication:
    source_stage: Path
    artifact_stage: Path
    recorded_at: str
    documents: Mapping[str, Mapping[str, Any]]
    source_identities: Mapping[str, tuple[int, int, str]]
    artifact_identities: Mapping[str, tuple[int, int, str]]
    reviewed_input_identities: ReviewedInputIdentities
    source_tree_sha256: str
    artifact_tree_sha256: str


def _final_source_paths() -> dict[str, Path]:
    return {name: SOURCES_ROOT / name for name in SOURCE_FILENAMES}


def _final_presence() -> tuple[bool, list[str]]:
    paths = {"artifact": ARTIFACT, **_final_source_paths()}
    present = [
        name for name, path in paths.items() if path.exists() or path.is_symlink()
    ]
    return len(present) == len(paths), present


def _assert_final_absent() -> None:
    complete, present = _final_presence()
    if complete or present:
        raise NordicPublicationError(f"final-path collision: {present!r}")


def _prepare(recorded_at: str) -> PreparedPublication:
    _assert_final_absent()
    target = _instant(recorded_at)
    if datetime.now(UTC) >= target:
        raise NordicPublicationError("recorded_at must be future before staging")
    reviewed_identities = _validate_reviewed_inputs()
    documents = expected_source_documents()
    source_stage = Path(
        tempfile.mkdtemp(
            prefix=".official-nordic-current-build-source-stage-", dir=SOURCES_ROOT
        )
    )
    artifact_stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.stage-", dir=ARTIFACT_ROOT)
    )
    source_root_identity = _identity(source_stage, directory=True)
    artifact_root_identity = _identity(artifact_stage, directory=True)
    try:
        _write_source_stage(source_stage, documents)
        _write_artifact_stage(artifact_stage, recorded_at, documents)
        _assert_stage_precedes(source_stage, target)
        _assert_stage_precedes(artifact_stage, target)
        source_identities = _tree_identities(source_stage)
        artifact_identities = _tree_identities(artifact_stage)
        source_tree = _content_tree_sha256(source_stage)
        artifact_tree = _content_tree_sha256(artifact_stage)
        _validate_artifact(
            artifact_stage,
            _source_paths(source_stage),
            frozen=False,
            require_live=False,
            require_final_chronology=False,
            documents=documents,
        )
        _assert_tree_identities(source_stage, source_identities)
        _assert_tree_identities(artifact_stage, artifact_identities)
        _assert_reviewed_input_identities(reviewed_identities)
        return PreparedPublication(
            source_stage,
            artifact_stage,
            recorded_at,
            documents,
            source_identities,
            artifact_identities,
            reviewed_identities,
            source_tree,
            artifact_tree,
        )
    except BaseException:
        if _has_identity(source_stage, source_root_identity, directory=True):
            _discard_owned_tree(source_stage)
        if _has_identity(artifact_stage, artifact_root_identity, directory=True):
            _discard_owned_tree(artifact_stage)
        raise


def _assert_prepared_exact(prepared: PreparedPublication, *, frozen: bool) -> None:
    _assert_tree_identities(prepared.source_stage, prepared.source_identities)
    _assert_tree_identities(prepared.artifact_stage, prepared.artifact_identities)
    if _content_tree_sha256(prepared.source_stage) != prepared.source_tree_sha256:
        raise NordicPublicationError("prepared source tree differs")
    if _content_tree_sha256(prepared.artifact_stage) != prepared.artifact_tree_sha256:
        raise NordicPublicationError("prepared artifact tree differs")
    _assert_stage_precedes(prepared.source_stage, _instant(prepared.recorded_at))
    _assert_stage_precedes(prepared.artifact_stage, _instant(prepared.recorded_at))
    _validate_artifact(
        prepared.artifact_stage,
        _source_paths(prepared.source_stage),
        frozen=frozen,
        require_live=False,
        require_final_chronology=False,
        documents=prepared.documents,
    )


def _discard_owned_tree(root: Path) -> None:
    identities = _tree_identities(root)
    _assert_tree_identities(root, identities)
    directories = [
        path
        for path in (root, *root.rglob("*"))
        if path.is_dir() and not path.is_symlink()
    ]
    for directory in sorted(
        directories, key=lambda item: len(item.parts), reverse=True
    ):
        relative = "." if directory == root else directory.relative_to(root).as_posix()
        expected = identities[relative]
        if not _has_identity(directory, expected[:2], directory=True):
            raise NordicPublicationError(
                f"refusing identity-mismatched stage cleanup: {directory}"
            )
        directory.chmod(0o700)
    files = [
        path for path in root.rglob("*") if path.is_file() and not path.is_symlink()
    ]
    for path in files:
        relative = path.relative_to(root).as_posix()
        expected = identities[relative]
        if not _has_identity(path, expected[:2], directory=False):
            raise NordicPublicationError(
                f"refusing identity-mismatched stage cleanup: {path}"
            )
        path.unlink()
    for directory in sorted(
        directories, key=lambda item: len(item.parts), reverse=True
    ):
        relative = "." if directory == root else directory.relative_to(root).as_posix()
        expected = identities[relative]
        if not _has_identity(directory, expected[:2], directory=True):
            raise NordicPublicationError(
                f"refusing identity-mismatched stage cleanup: {directory}"
            )
        directory.rmdir()


def preflight(*, recorded_at: str | None = None) -> dict[str, Any]:
    """Render, import twice, freeze, validate, and discard exact final bytes."""

    target = (
        _instant(recorded_at)
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=30)
    )
    if datetime.now(UTC) >= target:
        raise NordicPublicationError("preflight recorded_at must be future")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    prepared = _prepare(timestamp)
    source_stage = prepared.source_stage
    artifact_stage = prepared.artifact_stage
    try:
        _assert_prepared_exact(prepared, frozen=False)
        _freeze_stages(source_stage, artifact_stage)
        _assert_prepared_exact(prepared, frozen=True)
        manifest_sha256 = _sha256(artifact_stage / "manifest.json")
        artifact_tree_sha256 = tree_digest(artifact_stage)
        source_tree_sha256 = tree_digest(source_stage)
        source_pins = [
            {
                "path": f"sources/{name}",
                "bytes": (source_stage / name).stat().st_size,
                "sha256": _sha256(source_stage / name),
            }
            for name in SOURCE_FILENAMES
        ]
        result = {
            "status": "PREFLIGHT_VALIDATED_AND_DISCARDED",
            "recorded_at": timestamp,
            "artifact_id": ARTIFACT_ID,
            "artifact_manifest_sha256": manifest_sha256,
            "artifact_tree_sha256": artifact_tree_sha256,
            "source_tree_sha256": source_tree_sha256,
            "source_pins": source_pins,
            "rows": {
                "entity_snapshots": 6,
                "evidence": 8,
                "lifecycle": 3,
                "operating_models": 0,
                "workloads": 0,
                "capacities": 0,
                "coordinates": 0,
                "geometry": 0,
            },
            "published": False,
        }
    finally:
        if source_stage.exists():
            _discard_owned_tree(source_stage)
        if artifact_stage.exists():
            _discard_owned_tree(artifact_stage)
    _assert_final_absent()
    _validate_reviewed_inputs()
    result["source_stage_discarded"] = not source_stage.exists()
    result["artifact_stage_discarded"] = not artifact_stage.exists()
    result["reviewed_source_stage_retained"] = REVIEWED_SOURCE_STAGE.exists()
    result["reviewed_artifact_stage_retained"] = REVIEWED_ARTIFACT_STAGE.exists()
    result["raw_capture_retained"] = RAW_CAPTURE.exists()
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
        raise NordicPublicationError(str(error)) from error


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
    for source in prepared.source_stage.iterdir():
        _assert_recursive_ctimes_at_or_after(source, target)
    _assert_recursive_ctimes_at_or_after(prepared.artifact_stage, target)
    _assert_final_absent()

    promoted: list[tuple[Path, Path, tuple[int, int], bool]] = []
    try:
        for name in SOURCE_FILENAMES:
            staged = prepared.source_stage / name
            final = SOURCES_ROOT / name
            identity = _identity(staged, directory=False)
            _promote_noreplace(staged, final)
            if not _has_identity(final, identity, directory=False):
                raise NordicPublicationError(
                    f"promoted source identity differs: {name}"
                )
            promoted.append((final, staged, identity, False))
        artifact_identity = _identity(prepared.artifact_stage, directory=True)
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        if not _has_identity(ARTIFACT, artifact_identity, directory=True):
            raise NordicPublicationError("promoted artifact identity differs")
        _assert_tree_identities(ARTIFACT, prepared.artifact_identities)
        promoted.append((ARTIFACT, prepared.artifact_stage, artifact_identity, True))
        _validate_artifact(
            ARTIFACT,
            _final_source_paths(),
            frozen=True,
            require_live=True,
            require_final_chronology=True,
            documents=prepared.documents,
        )
        _assert_reviewed_input_identities(prepared.reviewed_input_identities)
    except BaseException as error:
        for final, staged, identity, directory in reversed(promoted):
            try:
                if not _has_identity(final, identity, directory=directory):
                    raise NordicPublicationError(
                        f"refusing identity-mismatched rollback: {final}"
                    )
                _promote_noreplace(final, staged)
                if not _has_identity(staged, identity, directory=directory):
                    raise NordicPublicationError(
                        f"rolled-back identity differs: {staged}"
                    )
            except Exception as rollback_error:
                error.add_note(f"Nordic rollback failed for {final}: {rollback_error}")
        raise


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise NordicPublicationError("active Nordic publication lock exists") from error
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
                raise NordicPublicationError(
                    "refusing substituted Nordic publication-lock cleanup"
                )
            PUBLICATION_LOCK.unlink()


def _existing_identical(recorded_at: str | None) -> dict[str, Any]:
    manifest = json.loads((ARTIFACT / "manifest.json").read_text(encoding="utf-8"))
    existing_recorded_at = manifest.get("recorded_at")
    if not isinstance(existing_recorded_at, str):
        raise NordicPublicationError("existing recorded_at is missing")
    if recorded_at is not None and recorded_at != existing_recorded_at:
        raise NordicPublicationError("existing recorded_at differs")
    inputs = _validate_reviewed_inputs()
    documents = expected_source_documents()
    _validate_artifact(
        ARTIFACT,
        _final_source_paths(),
        frozen=True,
        require_live=True,
        require_final_chronology=True,
        documents=documents,
    )
    _assert_reviewed_input_identities(inputs)
    return {
        "status": "existing-identical",
        "artifact": str(ARTIFACT),
        "recorded_at": existing_recorded_at,
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "published": True,
        "accepted_source_records": 3,
        "raw_capture_retained": RAW_CAPTURE.exists(),
    }


def build(
    *,
    recorded_at: str | None = None,
    publication_authorized: bool = False,
) -> dict[str, Any]:
    """Publish only with explicit authorization; otherwise fail closed."""

    if not publication_authorized:
        raise NordicPublicationError(
            "Nordic publication requires publication_authorized=True"
        )
    complete, present = _final_presence()
    if complete:
        return _existing_identical(recorded_at)
    if present:
        raise NordicPublicationError(f"partial final-path collision: {present!r}")

    target = (
        _instant(recorded_at)
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise NordicPublicationError("recorded_at must be future before publication")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    SOURCES_ROOT.mkdir(parents=True, exist_ok=True)
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    with _publication_lock():
        prepared = _prepare(timestamp)
        try:
            _publish_prepared(prepared)
        except BaseException:
            if prepared.source_stage.exists():
                _discard_owned_tree(prepared.source_stage)
            if prepared.artifact_stage.exists():
                _discard_owned_tree(prepared.artifact_stage)
            raise
        if prepared.source_stage.exists():
            if any(prepared.source_stage.iterdir()):
                raise NordicPublicationError("source stage not empty after publication")
            identity = prepared.source_identities["."][:2]
            if not _has_identity(prepared.source_stage, identity, directory=True):
                raise NordicPublicationError("source stage identity differs")
            prepared.source_stage.rmdir()
        manifest = _validate_artifact(
            ARTIFACT,
            _final_source_paths(),
            frozen=True,
            require_live=True,
            require_final_chronology=True,
            documents=prepared.documents,
        )
    return {
        "status": "published",
        "artifact": str(ARTIFACT),
        "recorded_at": manifest["recorded_at"],
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "published": True,
        "accepted_source_records": 3,
        "raw_capture_retained": RAW_CAPTURE.exists(),
    }


def main() -> int:
    print(json.dumps(preflight(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
