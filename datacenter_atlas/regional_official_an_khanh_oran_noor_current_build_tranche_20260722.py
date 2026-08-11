"""Accepted-format publisher for the reviewed An Khanh, Oran, and Noor tranche.

The module never fetches the network. It requires the byte-exact reviewed
prepublication stages and the frozen private capture bundle, renders distinct
accepted final bytes, and refuses publication unless
``publication_authorized=True``.

``preflight`` is the safe default: it renders exact final source and artifact
bytes in unique sibling stages, imports each source twice, freezes and validates
the stages, reports their pins, and identity-safely discards them. It creates no
final path. The accepted records retain zero coordinate, geometry, facility
type, operating-model, workload, capacity, energy-consumption, or efficiency
rows. An Khanh's 60 MW remains untyped design metadata only. Bolivia remains a
rejected, review-only, unhashable candidate.
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

from .external_captures import resolve_external_capture
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .open_seed_v69 import promote_noreplace
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "regional-official-an-khanh-oran-noor-current-build-tranche-2026-07-22-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".regional-an-khanh-oran-noor-publication.lock"

AN_KHANH_SOURCE_FILENAME = (
    "curated-official-2026-07-22-viettel-an-khanh-current-build.json"
)
ORAN_SOURCE_FILENAME = (
    "curated-official-2026-07-22-oran-ai-data-center-current-build.json"
)
NOOR_SOURCE_FILENAME = (
    "curated-official-2026-07-22-noor-capital-gardens-current-build.json"
)
SOURCE_FILENAMES = (
    AN_KHANH_SOURCE_FILENAME,
    ORAN_SOURCE_FILENAME,
    NOOR_SOURCE_FILENAME,
)

REVIEWED_CANDIDATE_ID = (
    "regional-official-an-khanh-oran-noor-prepublication-2026-07-22-v1"
)
REVIEWED_RECORDED_AT = "2026-07-22T04:37:36Z"
REVIEWED_SOURCE_STAGE = (
    SOURCES_ROOT / ".regional-official-prepublication-sources.ofv2p9wh"
)
REVIEWED_ARTIFACT_STAGE = (
    ARTIFACT_ROOT / ".regional-official-an-khanh-oran-noor-prepublication-"
    "2026-07-22-v1.trindi5a"
)
RAW_CAPTURE = Path("/Users/kian/.Trash/dc-regional-gap.Q63EWa")


def _raw_capture() -> Path:
    return resolve_external_capture(RAW_CAPTURE)

REVIEWED_SOURCE_TREE_SHA256 = (
    "42563fccdc56ed9cce102b9236eb937a5a7585e68035434004d943e06f71959b"
)
REVIEWED_ARTIFACT_TREE_SHA256 = (
    "74c2e5d63594a541c52c773002245c5f515f708fd941ac0c34c0982a95af2807"
)
RAW_CAPTURE_TREE_SHA256 = (
    "ddbc99ff381e3cfec2e7a660933df7c64516f634d68e5c6879b7fec7d72ebcc6"
)

REVIEWED_SOURCE_PINS: Mapping[str, tuple[int, str]] = {
    AN_KHANH_SOURCE_FILENAME: (
        5_531,
        "3467017963d11e8ce74901600c41b7585b70a4fc14550b7904cd58825515e22f",
    ),
    ORAN_SOURCE_FILENAME: (
        7_387,
        "bf0a29c1b083a7aa21628824edc297f33a22fb1e1d3a6cb5f22547b34b61e666",
    ),
    NOOR_SOURCE_FILENAME: (
        4_944,
        "5d9e8441fa105ddc13b5e3cfb73afff62150b64dd4a3c0c6b6d1462c06ecadf7",
    ),
}

REVIEWED_ARTIFACT_PINS: Mapping[str, tuple[int, str]] = {
    "README.md": (
        2_011,
        "fa68ae004a7b23ad740c71745ba42489f58bc151043a7580bf4dbae16d2be0df",
    ),
    "candidate-assessment.json": (
        4_299,
        "6ea347287c90539453671008fc6701274b5e77053efc4579e93d1725474e077a",
    ),
    "manifest.json": (
        1_605,
        "b5306171c7b83ebfe9c3a433360f5495b4eff55091311d7f747b9fe5b8adfcae",
    ),
    "manifest.sha256": (
        80,
        "0ae0ea8eb47a53509b69d4ebb8ebf7928b64752a2752f7b3e6415e30ad83b680",
    ),
    "retrieval-inventory.json": (
        6_599,
        "cbca67b84a6d440f39c2e67dec368157bcecf3ef5a0f7c85ba95147bec5b5b2d",
    ),
    "rights-and-disposition.json": (
        1_092,
        "cb4162ad3d938224341d3ce21f2afc459692d8594c24db1c1e0fcdcdfb99d8c7",
    ),
    "source-snapshot.json": (
        6_435,
        "d2507083c612932d517374b2affc531c736909821b047a16b1e24e6cdd870603",
    ),
}

RAW_CAPTURE_PINS: Mapping[str, tuple[int, str]] = {
    "ankhanh.body": (
        343_794,
        "e17e5999c45a2341f0aa7986b94a57ab0d05a82615b64e55e353273ccbda63a0",
    ),
    "ankhanh.headers": (
        2_379,
        "e0787eb6bde85e4cde8448fae8661dbd599143bc0fb77c84155d7bee4c75efb5",
    ),
    "bolivia.headers": (
        0,
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    ),
    "noor.body": (
        35_951,
        "809b7b91729c0535105611ce9206678188ffe9bd3281210b04bdc02d7b9be920",
    ),
    "noor.headers": (
        444,
        "30c44e549751c08d551f2a90df5186eb46d8c62298238d25bc8a4556cb79fca5",
    ),
    "oran_mpt.body": (
        177_426,
        "fc754b5bd44cd345b52f09bdbfb0a8716b947e0c5247a0dec46b1453add64c21",
    ),
    "oran_mpt.headers": (
        1_346,
        "340b92ccca146ba3e837d0d55025f9a24af207be45c6ff5761dd3b5255c87e16",
    ),
    "oran_radio.body": (
        76_195,
        "6c543908dfe5ab8517178cee4a8745581bbff916aaa5733f4c58c072d4bda204",
    ),
    "oran_radio.headers": (
        507,
        "655a13b638019a7fd92bc09ee2da370a4bfee07710dd94ff5f2d22ce79a59999",
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

AN_KHANH_CAMPUS_KEY = "curated:viettel-an-khanh-data-center-campus"
AN_KHANH_PROJECT_KEY = f"{AN_KHANH_CAMPUS_KEY}:current-build"
ORAN_CAMPUS_KEY = "curated:oran-ai-data-center-campus"
ORAN_PROJECT_KEY = f"{ORAN_CAMPUS_KEY}:current-build"
NOOR_CAMPUS_KEY = "curated:noor-capital-gardens-data-center"
NOOR_PROJECT_KEY = f"{NOOR_CAMPUS_KEY}:current-build"


class RegionalPublicationError(RuntimeError):
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
        raise RegionalPublicationError("recorded_at must be ISO 8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RegionalPublicationError("recorded_at must be timezone aware")
    return parsed.astimezone(UTC)


def _pin(path: Path, expected: tuple[int, str], *, mode: int) -> None:
    if path.is_symlink() or not path.is_file():
        raise RegionalPublicationError(f"missing or unsafe pinned input: {path}")
    metadata = path.stat(follow_symlinks=False)
    if (metadata.st_size, _sha256(path)) != expected:
        raise RegionalPublicationError(f"pinned input differs: {path}")
    if stat.S_IMODE(metadata.st_mode) != mode:
        raise RegionalPublicationError(f"pinned input mode differs: {path}")


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
        raise RegionalPublicationError(f"symlink is not allowed: {path}")
    metadata = path.stat(follow_symlinks=False)
    if directory is True and not stat.S_ISDIR(metadata.st_mode):
        raise RegionalPublicationError(f"expected directory: {path}")
    if directory is False and not stat.S_ISREG(metadata.st_mode):
        raise RegionalPublicationError(f"expected regular file: {path}")
    return metadata.st_dev, metadata.st_ino


def _has_identity(
    path: Path, expected: tuple[int, int], *, directory: bool | None = None
) -> bool:
    try:
        return _identity(path, directory=directory) == expected
    except (FileNotFoundError, RegionalPublicationError):
        return False


def _tree_identities(root: Path) -> dict[str, tuple[int, int, str]]:
    if root.is_symlink() or not root.is_dir():
        raise RegionalPublicationError(f"unsafe tree root: {root}")
    result: dict[str, tuple[int, int, str]] = {}
    for candidate in (root, *sorted(root.rglob("*"))):
        if candidate.is_symlink():
            raise RegionalPublicationError(f"symlink in governed tree: {candidate}")
        metadata = candidate.stat(follow_symlinks=False)
        kind = (
            "directory"
            if stat.S_ISDIR(metadata.st_mode)
            else "file"
            if stat.S_ISREG(metadata.st_mode)
            else "other"
        )
        if kind == "other":
            raise RegionalPublicationError(
                f"special file in governed tree: {candidate}"
            )
        relative = "." if candidate == root else candidate.relative_to(root).as_posix()
        result[relative] = (metadata.st_dev, metadata.st_ino, kind)
    return result


def _assert_tree_identities(
    root: Path, expected: Mapping[str, tuple[int, int, str]]
) -> None:
    if _tree_identities(root) != dict(expected):
        raise RegionalPublicationError(f"tree identity changed: {root}")


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
        raise RegionalPublicationError("reviewed source stage is missing or unsafe")
    source_entries = {path.name: path for path in REVIEWED_SOURCE_STAGE.iterdir()}
    if set(source_entries) != set(REVIEWED_SOURCE_PINS):
        raise RegionalPublicationError("reviewed source stage inventory differs")
    for name, pin in REVIEWED_SOURCE_PINS.items():
        _pin(source_entries[name], pin, mode=0o600)
    if tree_digest(REVIEWED_SOURCE_STAGE) != REVIEWED_SOURCE_TREE_SHA256:
        raise RegionalPublicationError("reviewed source stage tree differs")

    if (
        REVIEWED_ARTIFACT_STAGE.is_symlink()
        or not REVIEWED_ARTIFACT_STAGE.is_dir()
        or stat.S_IMODE(REVIEWED_ARTIFACT_STAGE.stat().st_mode) != 0o700
    ):
        raise RegionalPublicationError("reviewed artifact stage is missing or unsafe")
    artifact_entries = {path.name: path for path in REVIEWED_ARTIFACT_STAGE.iterdir()}
    if set(artifact_entries) != set(REVIEWED_ARTIFACT_PINS):
        raise RegionalPublicationError("reviewed artifact stage inventory differs")
    for name, pin in REVIEWED_ARTIFACT_PINS.items():
        _pin(artifact_entries[name], pin, mode=0o600)
    if tree_digest(REVIEWED_ARTIFACT_STAGE) != REVIEWED_ARTIFACT_TREE_SHA256:
        raise RegionalPublicationError("reviewed artifact stage tree differs")
    reviewed_manifest = json.loads(
        artifact_entries["manifest.json"].read_text(encoding="utf-8")
    )
    if (
        reviewed_manifest.get("artifact_id") != REVIEWED_CANDIDATE_ID
        or reviewed_manifest.get("published") is not False
        or reviewed_manifest.get("recorded_at") != REVIEWED_RECORDED_AT
    ):
        raise RegionalPublicationError("reviewed candidate manifest differs")
    if artifact_entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{REVIEWED_ARTIFACT_PINS['manifest.json'][1]}  manifest.json\n"
    ):
        raise RegionalPublicationError("reviewed candidate checksum differs")

    if (
        _raw_capture().is_symlink()
        or not _raw_capture().is_dir()
        or stat.S_IMODE(_raw_capture().stat().st_mode) != 0o555
    ):
        raise RegionalPublicationError("raw capture bundle is missing or unsafe")
    raw_entries = {path.name: path for path in _raw_capture().iterdir()}
    if set(raw_entries) != set(RAW_CAPTURE_PINS):
        raise RegionalPublicationError("raw capture inventory differs")
    for name, pin in RAW_CAPTURE_PINS.items():
        _pin(raw_entries[name], pin, mode=0o444)
    if tree_digest(_raw_capture()) != RAW_CAPTURE_TREE_SHA256:
        raise RegionalPublicationError("raw capture tree differs")

    identities = ReviewedInputIdentities(
        _tree_identities(REVIEWED_SOURCE_STAGE),
        _tree_identities(REVIEWED_ARTIFACT_STAGE),
        _tree_identities(_raw_capture()),
    )
    _assert_tree_identities(REVIEWED_SOURCE_STAGE, identities.sources)
    _assert_tree_identities(REVIEWED_ARTIFACT_STAGE, identities.artifact)
    _assert_tree_identities(_raw_capture(), identities.captures)
    return identities


def _assert_reviewed_input_identities(
    identities: ReviewedInputIdentities,
) -> None:
    _assert_tree_identities(REVIEWED_SOURCE_STAGE, identities.sources)
    _assert_tree_identities(REVIEWED_ARTIFACT_STAGE, identities.artifact)
    _assert_tree_identities(_raw_capture(), identities.captures)


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
            raise RegionalPublicationError(
                f"prospective source path leaked at {path!r}"
            )
        if "prepublication" in lowered:
            if allow_lineage and "reviewed_candidate_lineage" in path:
                continue
            raise RegionalPublicationError(f"candidate language leaked at {path!r}")


def _assert_claim_boundaries(documents: Mapping[str, Mapping[str, Any]]) -> None:
    if tuple(documents) != SOURCE_FILENAMES:
        raise RegionalPublicationError("accepted source inventory differs")
    if sum(len(document["evidence"]) for document in documents.values()) != 4:
        raise RegionalPublicationError("accepted evidence count differs")
    if sum(len(document["lifecycle"]) for document in documents.values()) != 3:
        raise RegionalPublicationError("accepted lifecycle count differs")
    for document in documents.values():
        if (
            document["schema_version"] != "1.1"
            or document["operating_models"]
            or document["workloads"]
            or document["capacities"]
        ):
            raise RegionalPublicationError(
                "accepted type/workload/capacity/energy boundary differs"
            )
        for entity in ("campus", "project"):
            if (
                document[entity]["coordinates"] is not None
                or document[entity]["geometry"] is not None
            ):
                raise RegionalPublicationError("accepted spatial boundary differs")

    design = documents[AN_KHANH_SOURCE_FILENAME]["evidence"][0]["metadata"][
        "design_power_not_normalized"
    ]
    if (
        design.get("value") != 60
        or design.get("unit") != "MW"
        or design.get("typing") != "untyped_design_metadata_only"
        or design.get("capacity_row_created") is not False
    ):
        raise RegionalPublicationError("An Khanh 60 MW boundary differs")

    oran = documents[ORAN_SOURCE_FILENAME]
    if (
        oran["campus"]["roles"]
        or oran["project"]["roles"]
        or oran["lifecycle"]
        != [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": (
                    "algerian-radio-oran-ai-data-center-cornerstone-"
                    "2025-03-16-captured-2026-07-22"
                ),
                "as_of_date": "2025-03-16",
                "method": "authoritative_construction_start",
                "confidence": 0.99,
            }
        ]
    ):
        raise RegionalPublicationError("Oran cornerstone boundary differs")

    noor = documents[NOOR_SOURCE_FILENAME]
    status = noor["evidence"][0]["metadata"]["retrieval_date_status_classification"]
    if (
        status.get("publisher_value") != "Ongoing"
        or status.get("scope") != "contractor_current_page_classification_only"
        or noor["lifecycle"][0]["as_of_date"] != "2026-07-22"
        or noor["lifecycle"][0]["method"] != "authoritative_physical_status_update"
    ):
        raise RegionalPublicationError("Noor retrieval-date status boundary differs")


def _load_reviewed_documents() -> dict[str, dict[str, Any]]:
    identities = _validate_reviewed_inputs()
    documents: dict[str, dict[str, Any]] = {}
    for name in SOURCE_FILENAMES:
        document = json.loads(
            (REVIEWED_SOURCE_STAGE / name).read_text(encoding="utf-8")
        )
        if document.get("schema_version") != "1.1":
            raise RegionalPublicationError(f"reviewed source schema differs: {name}")
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
    _assert_claim_boundaries(documents)
    _assert_no_candidate_language(documents)
    return documents


def expected_source_documents() -> dict[str, dict[str, Any]]:
    return _load_reviewed_documents()


def _source_records(
    documents: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    dispositions = {
        AN_KHANH_SOURCE_FILENAME: "accepted_official_groundbreaking_current_build",
        ORAN_SOURCE_FILENAME: "accepted_official_cornerstone_current_build",
        NOOR_SOURCE_FILENAME: (
            "accepted_retrieval_date_contractor_status_current_build"
        ),
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
        "viettel-an-khanh-data-center-current-build": (
            AN_KHANH_SOURCE_FILENAME,
            "accepted_official_groundbreaking_current_build",
        ),
        "oran-data-center-ai-computing-center-current-build": (
            ORAN_SOURCE_FILENAME,
            "accepted_official_cornerstone_current_build",
        ),
        "noor-capital-gardens-data-center-current-build": (
            NOOR_SOURCE_FILENAME,
            "accepted_retrieval_date_contractor_status_current_build",
        ),
    }
    for row in rows:
        candidate_id = row["candidate_id"]
        if candidate_id in accepted:
            filename, decision = accepted[candidate_id]
            row["decision"] = decision
            row["source_paths"] = [f"sources/{filename}"]
            row["accepted"] = True
            row["published"] = True
            row["rejected"] = False
        else:
            if candidate_id != "bolivia-fiscalia-data-center":
                raise RegionalPublicationError(
                    f"unexpected reviewed candidate: {candidate_id}"
                )
            row["decision"] = "rejected_review_only_unhashable_official_timeout"
            row["source_paths"] = []
            row["accepted"] = False
            row["published"] = False
            row["rejected"] = True
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-current-build-assessment-v1",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "candidate_count": 4,
        "accepted_source_record_count": 3,
        "published_source_record_count": 3,
        "rejected_review_only_count": 1,
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
        "artifact_storage_path_redacted": True,
        "artifact_manifest_sha256": REVIEWED_ARTIFACT_PINS["manifest.json"][1],
        "artifact_tree_sha256": REVIEWED_ARTIFACT_TREE_SHA256,
        "source_storage_path_redacted": True,
        "source_tree_sha256": REVIEWED_SOURCE_TREE_SHA256,
        "source_files": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in REVIEWED_SOURCE_PINS.items()
        ],
        "raw_capture_storage_path_redacted": True,
        "raw_capture_file_count": len(RAW_CAPTURE_PINS),
        "raw_capture_total_bytes": sum(pin[0] for pin in RAW_CAPTURE_PINS.values()),
        "raw_capture_tree_sha256": RAW_CAPTURE_TREE_SHA256,
        "semantic_review_decision": (
            "three_records_accepted_without_coordinate_type_workload_capacity_or_"
            "energy_expansion_and_bolivia_rejected_unhashable"
        ),
        "direct_promotion_of_candidate_bytes": False,
    }


def _artifact_documents(
    recorded_at: str,
    documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    source_records = _source_records(documents)
    assessment = _accepted_assessment(recorded_at)
    readme = f"""# Regional official current-build tranche

This immutable accepted source artifact publishes three official-source records at {recorded_at}: Viettel An Khanh Data Center in Vietnam, the Oran data center and AI computing center in Algeria, and Noor Data Center in Egypt.

The records contain six entity snapshots, four evidence rows, and three generic `under_construction` lifecycle observations. They contain zero facility-type, operating-model, workload, capacity, energy-consumption, efficiency, coordinate, geometry, satellite, aerial, map-derived, or computer-vision rows. An Khanh's 60 MW remains source-described, untyped design metadata only and is not asserted as IT power, grid power, current power, operational power, or energy consumption. Oran's cornerstone establishes no more specific physical stage. Noor's status remains only Square Engineering's `Ongoing` classification as retrieved on 2026-07-22; its area, scope, and planned completion remain metadata.

The Bolivia Fiscalía candidate is rejected and remains review-only and unhashable. Both controlled attempts timed out before any HTTP response header or body, so it has no stable key, evidence record, lifecycle observation, or source record.

Publication is limited to the three accepted source files and this artifact. No open-seed successor, release, federation, identity, timeline, construction-master, map, coverage, or other downstream file is created or modified. The frozen nine-file official-response bundle remains private in place and is not redistributed.
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
            "rejected_review_only_candidates": 1,
            "distinct_campuses": 3,
            "projects": 3,
            "distinct_entity_snapshots": 6,
            "new_entities_against_v95": 6,
            "reused_existing_entities": 0,
            "evidence_records": 4,
            "lifecycle_observations": 3,
            "facility_type_observations": 0,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
            "energy_consumption_observations": 0,
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


def _offline_import(
    source_paths: Mapping[str, Path], recorded_at: str
) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="regional-accepted-import-", dir="/private/tmp"
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
            raise RegionalPublicationError(
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
            "evidence": 4,
            "lifecycle_observations": 3,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
        }
        if counts != expected:
            raise RegionalPublicationError(f"offline import counts differ: {counts!r}")
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
        "rejected_review_only_candidates": 1,
        "successful_http_200_body_captures": 4,
        "official_server_timeout_targets": 1,
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
    if root.is_symlink():
        raise RegionalPublicationError(f"symlink is not allowed: {root}")
    for candidate in (root, *root.rglob("*")):
        if candidate.is_symlink():
            raise RegionalPublicationError(f"symlink in governed tree: {candidate}")
        metadata = candidate.stat(follow_symlinks=False)
        birthtime = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if max(birthtime, metadata.st_mtime) > target.timestamp() + 0.000_001:
            raise RegionalPublicationError(
                f"private stage post-dates recorded_at: {candidate}"
            )


def _assert_recursive_ctimes_at_or_after(root: Path, target: datetime) -> None:
    if root.is_symlink():
        raise RegionalPublicationError(f"symlink is not allowed: {root}")
    for candidate in (root, *root.rglob("*")):
        if candidate.is_symlink():
            raise RegionalPublicationError(f"symlink in governed tree: {candidate}")
        if (
            candidate.stat(follow_symlinks=False).st_ctime + 0.000_001
            < target.timestamp()
        ):
            raise RegionalPublicationError(
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
        raise RegionalPublicationError("accepted source inventory differs")
    expected_mode = 0o444 if frozen else 0o600
    for name in SOURCE_FILENAMES:
        path = paths[name]
        if path.is_symlink() or not path.is_file():
            raise RegionalPublicationError(
                f"accepted source is missing or unsafe: {name}"
            )
        if stat.S_IMODE(path.stat().st_mode) != expected_mode:
            raise RegionalPublicationError(f"accepted source mode differs: {name}")
        if path.read_bytes() != _canonical(documents[name]):
            raise RegionalPublicationError(f"accepted source differs: {name}")
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
    _assert_claim_boundaries(documents)
    if artifact.is_symlink() or not artifact.is_dir():
        raise RegionalPublicationError("accepted artifact is missing or unsafe")
    expected_directory_mode = 0o555 if frozen else 0o700
    expected_file_mode = 0o444 if frozen else 0o600
    if stat.S_IMODE(artifact.stat().st_mode) != expected_directory_mode:
        raise RegionalPublicationError("accepted artifact directory mode differs")
    entries = {path.name: path for path in artifact.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise RegionalPublicationError("accepted artifact closed file set differs")
    for name, path in entries.items():
        if path.is_symlink() or not path.is_file():
            raise RegionalPublicationError(f"unsafe accepted artifact member: {name}")
        if stat.S_IMODE(path.stat().st_mode) != expected_file_mode:
            raise RegionalPublicationError(
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
        raise RegionalPublicationError("accepted manifest contract differs")
    rows = manifest.get("files")
    if not isinstance(rows, list) or [row.get("path") for row in rows] != list(
        CONTENT_FILES
    ):
        raise RegionalPublicationError("accepted manifest inventory differs")
    for row in rows:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (
            row["bytes"],
            row["sha256"],
        ):
            raise RegionalPublicationError(
                f"accepted manifest pin differs: {row['path']}"
            )
    if manifest["tree_sha256"] != _sha256_bytes(_canonical(rows)):
        raise RegionalPublicationError("accepted logical tree differs")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise RegionalPublicationError("accepted manifest checksum differs")
    expected_payloads = _artifact_documents(manifest["recorded_at"], documents)
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected_payloads[name]:
            raise RegionalPublicationError(f"accepted artifact content differs: {name}")
    source_records = _validate_sources(
        source_paths,
        documents,
        frozen=frozen,
        recorded_at=manifest["recorded_at"],
    )
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records:
        raise RegionalPublicationError("accepted source pins differ")
    _assert_no_candidate_language(snapshot, allow_lineage=True)
    assessment = json.loads(
        entries["candidate-assessment.json"].read_text(encoding="utf-8")
    )
    _assert_no_candidate_language(assessment)
    bolivia = next(
        row
        for row in assessment["candidates"]
        if row["candidate_id"] == "bolivia-fiscalia-data-center"
    )
    if (
        bolivia["accepted"] is not False
        or bolivia["published"] is not False
        or bolivia["rejected"] is not True
        or bolivia["source_paths"]
        or bolivia["stable_key_created"] is not False
        or bolivia["lifecycle_claim_created"] is not False
        or bolivia["evidence_record_created"] is not False
    ):
        raise RegionalPublicationError("Bolivia rejected boundary differs")
    target = _instant(manifest["recorded_at"])
    if require_live and datetime.now(UTC) < target:
        raise RegionalPublicationError("accepted recorded_at is not live")
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
        raise RegionalPublicationError(f"final-path collision: {present!r}")


def _prepare(recorded_at: str) -> PreparedPublication:
    _assert_final_absent()
    target = _instant(recorded_at)
    if datetime.now(UTC) >= target:
        raise RegionalPublicationError("recorded_at must be future before staging")
    reviewed_identities = _validate_reviewed_inputs()
    documents = expected_source_documents()
    source_stage = Path(
        tempfile.mkdtemp(
            prefix=".regional-an-khanh-oran-noor-source-stage-", dir=SOURCES_ROOT
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
        raise RegionalPublicationError("prepared source tree differs")
    if _content_tree_sha256(prepared.artifact_stage) != prepared.artifact_tree_sha256:
        raise RegionalPublicationError("prepared artifact tree differs")
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
            raise RegionalPublicationError(
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
            raise RegionalPublicationError(
                f"refusing identity-mismatched stage cleanup: {path}"
            )
        path.unlink()
    for directory in sorted(
        directories, key=lambda item: len(item.parts), reverse=True
    ):
        relative = "." if directory == root else directory.relative_to(root).as_posix()
        expected = identities[relative]
        if not _has_identity(directory, expected[:2], directory=True):
            raise RegionalPublicationError(
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
        raise RegionalPublicationError("preflight recorded_at must be future")
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
                "evidence": 4,
                "lifecycle": 3,
                "facility_types": 0,
                "operating_models": 0,
                "workloads": 0,
                "capacities": 0,
                "energy_consumption": 0,
                "coordinates": 0,
                "geometry": 0,
            },
            "published": False,
        }
    finally:
        if source_stage.exists() or source_stage.is_symlink():
            if not _has_identity(
                source_stage, prepared.source_identities["."][:2], directory=True
            ):
                raise RegionalPublicationError(
                    "refusing identity-mismatched source-stage cleanup"
                )
            _discard_owned_tree(source_stage)
        if artifact_stage.exists() or artifact_stage.is_symlink():
            if not _has_identity(
                artifact_stage,
                prepared.artifact_identities["."][:2],
                directory=True,
            ):
                raise RegionalPublicationError(
                    "refusing identity-mismatched artifact-stage cleanup"
                )
            _discard_owned_tree(artifact_stage)
    _assert_final_absent()
    _validate_reviewed_inputs()
    result["source_stage_discarded"] = not source_stage.exists()
    result["artifact_stage_discarded"] = not artifact_stage.exists()
    result["reviewed_source_stage_retained"] = REVIEWED_SOURCE_STAGE.exists()
    result["reviewed_artifact_stage_retained"] = REVIEWED_ARTIFACT_STAGE.exists()
    result["raw_capture_retained"] = _raw_capture().exists()
    result["final_artifact_exists"] = ARTIFACT.exists()
    result["final_source_exists"] = any(
        path.exists() for path in _final_source_paths().values()
    )
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
        raise RegionalPublicationError(str(error)) from error


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
                raise RegionalPublicationError(
                    f"promoted source identity differs: {name}"
                )
            promoted.append((final, staged, identity, False))
        artifact_identity = _identity(prepared.artifact_stage, directory=True)
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        if not _has_identity(ARTIFACT, artifact_identity, directory=True):
            raise RegionalPublicationError("promoted artifact identity differs")
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
                    raise RegionalPublicationError(
                        f"refusing identity-mismatched rollback: {final}"
                    )
                _promote_noreplace(final, staged)
                if not _has_identity(staged, identity, directory=directory):
                    raise RegionalPublicationError(
                        f"rolled-back identity differs: {staged}"
                    )
            except Exception as rollback_error:
                error.add_note(
                    f"regional rollback failed for {final}: {rollback_error}"
                )
        raise


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise RegionalPublicationError(
            "active regional publication lock exists"
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
                raise RegionalPublicationError(
                    "refusing substituted regional publication-lock cleanup"
                )
            PUBLICATION_LOCK.unlink()


def _existing_identical(recorded_at: str | None) -> dict[str, Any]:
    manifest = json.loads((ARTIFACT / "manifest.json").read_text(encoding="utf-8"))
    existing_recorded_at = manifest.get("recorded_at")
    if not isinstance(existing_recorded_at, str):
        raise RegionalPublicationError("existing recorded_at is missing")
    if recorded_at is not None and recorded_at != existing_recorded_at:
        raise RegionalPublicationError("existing recorded_at differs")
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
        "rejected_review_only_candidates": 1,
        "raw_capture_retained": _raw_capture().exists(),
    }


def build(
    *,
    recorded_at: str | None = None,
    publication_authorized: bool = False,
) -> dict[str, Any]:
    """Publish only with explicit authorization; otherwise fail closed."""

    if not publication_authorized:
        raise RegionalPublicationError(
            "regional publication requires publication_authorized=True"
        )
    complete, present = _final_presence()
    if complete:
        return _existing_identical(recorded_at)
    if present:
        raise RegionalPublicationError(f"partial final-path collision: {present!r}")

    target = (
        _instant(recorded_at)
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise RegionalPublicationError("recorded_at must be future before publication")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    SOURCES_ROOT.mkdir(parents=True, exist_ok=True)
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    with _publication_lock():
        prepared = _prepare(timestamp)
        try:
            _publish_prepared(prepared)
        except BaseException:
            if _has_identity(
                prepared.source_stage,
                prepared.source_identities["."][:2],
                directory=True,
            ):
                _discard_owned_tree(prepared.source_stage)
            if _has_identity(
                prepared.artifact_stage,
                prepared.artifact_identities["."][:2],
                directory=True,
            ):
                _discard_owned_tree(prepared.artifact_stage)
            raise
        if prepared.source_stage.exists():
            if any(prepared.source_stage.iterdir()):
                raise RegionalPublicationError(
                    "source stage not empty after publication"
                )
            identity = prepared.source_identities["."][:2]
            if not _has_identity(prepared.source_stage, identity, directory=True):
                raise RegionalPublicationError("source stage identity differs")
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
        "rejected_review_only_candidates": 1,
        "raw_capture_retained": _raw_capture().exists(),
    }


def main() -> int:
    print(json.dumps(preflight(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
