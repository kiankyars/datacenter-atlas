"""Publish the corrected v2 MERLIN, CyrusOne, and Beale source tranche.

V1 is retained byte-for-byte as a rejected publication incident because one
Pima evidence guardrail mis-scoped Tulsa's 500 MW website value. V2 reuses the
four unaffected source files and publishes corrected Tulsa and Pima files.
Neither website capacity value is normalized.
"""

from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence

from . import merlin_cyrusone_beale_official_current_build_gap_20260722 as v1
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .external_captures import resolve_external_capture
from .service import validate_database


ROOT = v1.ROOT
SOURCES_ROOT = v1.SOURCES_ROOT
ARTIFACT_ROOT = v1.ARTIFACT_ROOT
ARTIFACT_ID = "merlin-cyrusone-beale-official-current-build-gap-2026-07-22-v2"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".merlin-cyrusone-beale-current-build-gap-v2.lock"

V1_ARTIFACT_ID = v1.ARTIFACT_ID
V1_ARTIFACT = v1.ARTIFACT
V1_RECORDED_AT = "2026-07-22T02:37:09Z"
V1_PHYSICAL_TREE_SHA256 = (
    "5ad26f77d9ef44683dec48b63b7e0bd2f32a46b6fe7ba0c0a4b94534226dba3e"
)
V1_LOGICAL_TREE_SHA256 = (
    "f2f2910ae25758a82e85224d5d1ab616471f22d733cc535ab35574213f48d9f5"
)
V1_ROOT_CTIME_NS = 1_784_687_829_007_048_496
REJECTED_SENTENCE = "Any 500 MW or other power figure is untyped context only."
REJECTION_REASON = (
    "The sentence above occurs in the Pima location evidence metadata, but the "
    "captured official locations page assigns 500 MW to Tulsa County and 600 MW "
    "to Pima County. Normalized lifecycle and capacity rows were unaffected."
)

V1_ARTIFACT_MEMBER_PINS: Mapping[str, tuple[int, str, int]] = {
    "README.md": (
        2_103,
        "4d7b439826977e3bfa27eb8b7eeab16ba4d1580e60929fd71c664b7f3b543bb9",
        1_784_687_829_005_061_523,
    ),
    "candidate-assessment.json": (
        7_095,
        "47423387f64056a91f3dad58a1c5e4f185aeb5afbbcc9c134080d606cd51421c",
        1_784_687_829_005_019_856,
    ),
    "manifest.json": (
        1_824,
        "a2daf458cacfebc5a8614c36e7e89984e7bd7cb086482e2c0a1d4cdb888b634e",
        1_784_687_829_005_102_148,
    ),
    "manifest.sha256": (
        80,
        "7d99f066d5abfbb7d8a9520a56bf391f8aeca5c858afa1550619455ba86a6527",
        1_784_687_829_004_968_814,
    ),
    "retrieval-inventory.json": (
        20_462,
        "ffc15fda72de99adf4698bce7f835015a666ff7f1358e00563b325b9dfc89881",
        1_784_687_829_005_140_940,
    ),
    "rights-and-disposition.json": (
        1_137,
        "bcf5492996637065102b3f2db132c45abd9ad84b4f350e40cc8a5133e875e279",
        1_784_687_829_005_181_024,
    ),
    "source-snapshot.json": (
        8_248,
        "47fb016799d871571fdd36265c8120c9610c337082acceb93847ba1182f174b1",
        1_784_687_829_005_220_566,
    ),
}

V1_SOURCE_PINS: Mapping[str, tuple[int, str, int]] = {
    "curated-official-2026-07-22-merlin-bilbao-arasur-building-2-current-build.json": (
        6_371,
        "2385887a06e05885dfbb64b7868b1571d14879815e58e92a0347b9f279c4d30d",
        1_784_687_829_006_126_656,
    ),
    "curated-official-2026-07-22-merlin-bilbao-arasur-building-3-current-build.json": (
        6_371,
        "40353acf426a4193037aeceb89c06ff2340f761ba6374226ab70c3e7530adb42",
        1_784_687_829_006_481_367,
    ),
    "curated-official-2026-07-22-cyrusone-fra5-hanau-halls-2-3-current-build.json": (
        4_214,
        "576edad0e0eac03fbab0b4232c6cb513048c85efa5c314649916596a6bcf8806",
        1_784_687_829_006_579_368,
    ),
    "curated-official-2026-07-22-cyrusone-wood-dale-phase-1-current-build.json": (
        6_934,
        "e4b3cf1d11434a434df7f412126c1f4d8f99182a8c5da0ecdedc21f47ff97b8e",
        1_784_687_829_006_668_369,
    ),
    "curated-official-2026-07-22-beale-tulsa-project-clydesdale-initial-phase-current-build.json": (
        6_681,
        "ccacca1bb4bb90b522719682335982be6981f5027ae94a8d0d1fbac49efe9cb0",
        1_784_687_829_006_762_370,
    ),
    "curated-official-2026-07-22-beale-pima-project-blue-bobcat-site-preparation.json": (
        11_276,
        "6da1eb317e956a19c37e2e23a6ae8c142223976a01c79752fa46336a40990b73",
        1_784_687_829_006_860_162,
    ),
}

REUSED_SOURCE_FILENAMES = v1.SOURCE_FILENAMES[:4]
V1_TULSA_FILENAME = v1.SOURCE_FILENAMES[4]
V1_PIMA_FILENAME = v1.SOURCE_FILENAMES[5]
V2_TULSA_FILENAME = V1_TULSA_FILENAME.removesuffix(".json") + "-v2.json"
V2_PIMA_FILENAME = V1_PIMA_FILENAME.removesuffix(".json") + "-v2.json"
NEW_SOURCE_FILENAMES = (V2_TULSA_FILENAME, V2_PIMA_FILENAME)
SOURCE_FILENAMES = (*REUSED_SOURCE_FILENAMES, *NEW_SOURCE_FILENAMES)
PREDECESSOR_BY_SUCCESSOR = {
    V2_TULSA_FILENAME: V1_TULSA_FILENAME,
    V2_PIMA_FILENAME: V1_PIMA_FILENAME,
}
CONTENT_FILES = v1.CONTENT_FILES
CLOSED_FILES = v1.CLOSED_FILES

_canonical = v1._canonical
_sha256 = v1._sha256
_sha256_bytes = v1._sha256_bytes
_instant = v1._instant
_fsync_regular = v1._fsync_regular
_fsync_directory = v1._fsync_directory
_promote_noreplace = v1._promote_noreplace
tree_digest = v1.tree_digest

TULSA_CONTEXT_KEY = "beale-locations-tulsa-500mw-context-captured-2026-07-22"
PIMA_CONTEXT_KEY = "beale-locations-pima-600mw-context-captured-2026-07-22"


def _context_evidence(*, pima: bool) -> dict[str, Any]:
    if pima:
        key = PIMA_CONTEXT_KEY
        title = "Beale locations page - Pima County context"
        excerpt = (
            "Beale's current locations page labels Pima County with expected "
            "capacity of 600 MW."
        )
        reported = "Pima County, AZ — Expected Capacity 600 MW."
        scope = (
            "The 600 MW website label is untyped, campus-level commercial context "
            "only; it is not normalized as critical IT, gross facility, grid, "
            "generation, current load, measured energy, PUE, or WUE."
        )
    else:
        key = TULSA_CONTEXT_KEY
        title = "Beale locations page - Tulsa County context"
        excerpt = (
            "Beale's current locations page labels Tulsa County with capacity of "
            "500 MW."
        )
        reported = "Tulsa County, OK — Capacity 500 MW."
        scope = (
            "The 500 MW website label is untyped, campus-level commercial context "
            "only; it is not normalized as critical IT, gross facility, grid, "
            "generation, current load, measured energy, PUE, or WUE."
        )
    spec = v1.EvidenceSpec(
        key,
        "beale_locations",
        title,
        "Beale Infrastructure",
        "beale_infrastructure_official_locations",
        "company_disclosure",
        excerpt,
        {
            "capacity_context_as_reported": reported,
            "capacity_context_not_normalized": scope,
            "correction_scope": (
                "This scoped extract prevents the v1 Tulsa/Pima website values "
                "from being transposed."
            ),
        },
    )
    evidence = v1._evidence(spec)
    evidence["metadata"]["capture_artifact_id"] = ARTIFACT_ID
    return evidence


def expected_source_documents() -> dict[str, dict[str, Any]]:
    predecessor = v1.expected_source_documents()
    documents = {
        name: copy.deepcopy(predecessor[name]) for name in REUSED_SOURCE_FILENAMES
    }
    tulsa = copy.deepcopy(predecessor[V1_TULSA_FILENAME])
    pima = copy.deepcopy(predecessor[V1_PIMA_FILENAME])
    for document in (tulsa, pima):
        for evidence in document["evidence"]:
            evidence["metadata"]["capture_artifact_id"] = ARTIFACT_ID
    pima_location = next(
        row
        for row in pima["evidence"]
        if row["key"] == "beale-pima-project-bobcat-location-captured-2026-07-22"
    )
    removed = pima_location["metadata"].pop("power_context_not_normalized")
    if removed != REJECTED_SENTENCE:
        raise RuntimeError("v1 rejected sentence changed")
    tulsa["evidence"].append(_context_evidence(pima=False))
    pima["evidence"].append(_context_evidence(pima=True))
    documents[V2_TULSA_FILENAME] = tulsa
    documents[V2_PIMA_FILENAME] = pima
    _assert_capacity_context(documents)
    return documents


def _assert_capacity_context(
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    try:
        tulsa = documents[V2_TULSA_FILENAME]
        pima = documents[V2_PIMA_FILENAME]
        tulsa_context = next(
            row for row in tulsa["evidence"] if row["key"] == TULSA_CONTEXT_KEY
        )["metadata"]["capacity_context_as_reported"]
        pima_context = next(
            row for row in pima["evidence"] if row["key"] == PIMA_CONTEXT_KEY
        )["metadata"]["capacity_context_as_reported"]
    except (KeyError, StopIteration, TypeError) as error:
        raise RuntimeError("Tulsa/Pima capacity context is incomplete") from error
    if tulsa_context != "Tulsa County, OK — Capacity 500 MW.":
        raise RuntimeError("Tulsa/Pima capacity context differs: Tulsa must be 500 MW")
    if pima_context != "Pima County, AZ — Expected Capacity 600 MW.":
        raise RuntimeError("Tulsa/Pima capacity context differs: Pima must be 600 MW")
    if tulsa["capacities"] or pima["capacities"]:
        raise RuntimeError("Tulsa/Pima website capacity context was normalized")
    pima_location = next(
        row
        for row in pima["evidence"]
        if row["key"] == "beale-pima-project-bobcat-location-captured-2026-07-22"
    )
    if "power_context_not_normalized" in pima_location["metadata"]:
        raise RuntimeError("rejected Pima metadata survived correction")


def _require_v1_lineage() -> None:
    if V1_ARTIFACT.is_symlink() or not V1_ARTIFACT.is_dir():
        raise RuntimeError("rejected v1 artifact is absent or unsafe")
    root = V1_ARTIFACT.stat(follow_symlinks=False)
    if (
        stat.S_IMODE(root.st_mode) != 0o555
        or root.st_ctime_ns != V1_ROOT_CTIME_NS
    ):
        raise RuntimeError("rejected v1 artifact root changed")
    entries = {entry.name: entry for entry in V1_ARTIFACT.iterdir()}
    if set(entries) != set(V1_ARTIFACT_MEMBER_PINS):
        raise RuntimeError("rejected v1 artifact member set changed")
    for name, (size, digest, ctime_ns) in V1_ARTIFACT_MEMBER_PINS.items():
        path = entries[name]
        metadata = path.stat(follow_symlinks=False)
        if (
            path.is_symlink()
            or not path.is_file()
            or len(path.read_bytes()) != size
            or _sha256(path) != digest
            or metadata.st_ctime_ns != ctime_ns
            or stat.S_IMODE(metadata.st_mode) != 0o444
        ):
            raise RuntimeError(f"rejected v1 artifact member changed: {name}")
    if tree_digest(V1_ARTIFACT) != V1_PHYSICAL_TREE_SHA256:
        raise RuntimeError("rejected v1 physical tree changed")
    manifest = json.loads((V1_ARTIFACT / "manifest.json").read_text())
    if (
        manifest.get("artifact_id") != V1_ARTIFACT_ID
        or manifest.get("recorded_at") != V1_RECORDED_AT
        or manifest.get("tree_sha256") != V1_LOGICAL_TREE_SHA256
    ):
        raise RuntimeError("rejected v1 logical lineage changed")
    for name, (size, digest, ctime_ns) in V1_SOURCE_PINS.items():
        path = SOURCES_ROOT / name
        metadata = path.stat(follow_symlinks=False)
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != size
            or _sha256(path) != digest
            or metadata.st_ctime_ns != ctime_ns
            or stat.S_IMODE(metadata.st_mode) != 0o444
        ):
            raise RuntimeError(f"v1 source changed: {name}")
    pima = json.loads((SOURCES_ROOT / V1_PIMA_FILENAME).read_text())
    rejected = next(
        row
        for row in pima["evidence"]
        if row["key"] == "beale-pima-project-bobcat-location-captured-2026-07-22"
    )["metadata"].get("power_context_not_normalized")
    if rejected != REJECTED_SENTENCE:
        raise RuntimeError("v1 rejected sentence changed")


def _source_records(
    documents: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
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
                "capacity_estimates": len(document["capacities"]),
                "coordinates_present": 0,
                "geometry_present": 0,
                "source_status": (
                    "reused_byte_exact_from_v1"
                    if name in REUSED_SOURCE_FILENAMES
                    else "corrected_v2_successor"
                ),
                "seed_eligible": True,
                "seeded": False,
            }
        )
    return rows


def _planned_keys(
    documents: Mapping[str, Mapping[str, Any]],
) -> tuple[set[str], set[str]]:
    stable = {
        document[entity]["stable_key"]
        for document in documents.values()
        for entity in ("campus", "project")
    }
    evidence = {
        row["key"]
        for document in documents.values()
        for row in document["evidence"]
    }
    return stable, evidence


def _collision_witness(
    documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    _require_v1_lineage()
    base = v1._collision_witness(v1.expected_source_documents())
    planned_stable, planned_evidence = _planned_keys(documents)
    source_inputs = json.loads(v1.V92_SOURCE_INPUTS.read_text())
    v92_evidence = {
        key
        for row in source_inputs.get("sources", [])
        if isinstance(row, dict)
        for key in [row.get("provenance", {}).get("curated_record_key")]
        if isinstance(key, str)
    }
    if planned_evidence & v92_evidence:
        raise RuntimeError("v2 evidence key collides with v92")
    ignored = set(V1_SOURCE_PINS) | set(SOURCE_FILENAMES)
    collisions: dict[str, Any] = {}
    for path in SOURCES_ROOT.glob("*.json"):
        if path.name in ignored:
            continue
        try:
            document = json.loads(path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        stable = {
            row.get("stable_key")
            for key in ("campus", "facility", "building", "project")
            if isinstance((row := document.get(key)), dict)
        }
        evidence = {
            row.get("key")
            for row in document.get("evidence", [])
            if isinstance(row, dict)
        }
        if planned_stable & stable or planned_evidence & evidence:
            collisions[str(path.relative_to(ROOT))] = {
                "stable_keys": sorted(planned_stable & stable),
                "evidence_keys": sorted(planned_evidence & evidence),
            }
    if collisions:
        raise RuntimeError(f"unexpected v2 source collision: {collisions!r}")
    return {
        "v92_selected_input_count": base["v92_selected_input_count"],
        "v92_entity_count": base["v92_entity_count"],
        "planned_distinct_stable_keys": len(planned_stable),
        "planned_distinct_evidence_keys": len(planned_evidence),
        "exact_v92_stable_key_collisions": [],
        "exact_v92_evidence_key_collisions": [],
        "expected_v1_predecessor_overlap": {
            "stable_keys": len(planned_stable),
            "predecessor_evidence_keys": 11,
            "new_scoped_evidence_keys": [TULSA_CONTEXT_KEY, PIMA_CONTEXT_KEY],
        },
        "unexpected_source_collisions": {},
    }


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    assessment = copy.deepcopy(v1._candidate_assessment(recorded_at))
    assessment["artifact_id"] = ARTIFACT_ID
    remap = {
        f"sources/{V1_TULSA_FILENAME}": f"sources/{V2_TULSA_FILENAME}",
        f"sources/{V1_PIMA_FILENAME}": f"sources/{V2_PIMA_FILENAME}",
    }
    for candidate in assessment["candidates"]:
        candidate["source_paths"] = [
            remap.get(path, path) for path in candidate["source_paths"]
        ]
    assessment["correction"] = {
        "rejected_artifact_id": V1_ARTIFACT_ID,
        "rejected_sentence": REJECTED_SENTENCE,
        "reason": REJECTION_REASON,
        "accepted_tulsa_context": "500 MW untyped metadata only",
        "accepted_pima_context": "600 MW untyped metadata only",
        "normalized_capacity_rows_added": 0,
    }
    return assessment


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    inventory = copy.deepcopy(v1._capture_inventory(recorded_at))
    inventory["artifact_id"] = ARTIFACT_ID
    inventory["capture_reuse"] = {
        "raw_tree_recaptured": False,
        "reused_from_rejected_v1_lineage": True,
        "raw_tree_still_exact_in_recoverable_trash": True,
    }
    return inventory


def _file_tree(rows: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_bytes(
        (json.dumps(rows, indent=2, sort_keys=True) + "\n").encode()
    )


def _incident_lineage() -> dict[str, Any]:
    return {
        "accepted_as_base": False,
        "artifact_id": V1_ARTIFACT_ID,
        "artifact_path": f"source_artifacts/{V1_ARTIFACT_ID}",
        "declared_recorded_at": V1_RECORDED_AT,
        "physical_tree_sha256": V1_PHYSICAL_TREE_SHA256,
        "logical_tree_sha256": V1_LOGICAL_TREE_SHA256,
        "root_ctime_ns": V1_ROOT_CTIME_NS,
        "rejected_sentence": REJECTED_SENTENCE,
        "rejection_reason": REJECTION_REASON,
        "artifact_members": {
            name: {"bytes": size, "sha256": digest, "ctime_ns": ctime_ns}
            for name, (size, digest, ctime_ns) in V1_ARTIFACT_MEMBER_PINS.items()
        },
        "source_files": {
            name: {"bytes": size, "sha256": digest, "ctime_ns": ctime_ns}
            for name, (size, digest, ctime_ns) in V1_SOURCE_PINS.items()
        },
        "unaffected_sources_reused": list(REUSED_SOURCE_FILENAMES),
        "sources_replaced_by_corrected_successors": {
            V1_TULSA_FILENAME: V2_TULSA_FILENAME,
            V1_PIMA_FILENAME: V2_PIMA_FILENAME,
        },
        "status": "rejected_publication_incident",
    }


def _artifact_documents(
    recorded_at: str, documents: Mapping[str, Mapping[str, Any]]
) -> dict[str, bytes]:
    collision = _collision_witness(documents)
    records = _source_records(documents)
    totals = {
        "candidate_assessments": 5,
        "source_records": 6,
        "reused_source_records": 4,
        "corrected_successor_source_records": 2,
        "distinct_campuses": 5,
        "projects": 6,
        "distinct_entities": 11,
        "source_document_entity_snapshots": 12,
        "unique_imported_entity_snapshots": 11,
        "source_document_evidence_references": 15,
        "unique_evidence_records": 13,
        "lifecycle_observations": 8,
        "capacity_estimates": 2,
        "operating_model_observations": 0,
        "workload_observations": 0,
        "coordinates_present": 0,
        "geometry_present": 0,
    }
    readme = f"""# Corrected MERLIN, CyrusOne, and Beale official current-build tranche v2

V1 is retained immutably but rejected for selection or integration. Its normalized rows were correct, but its Pima evidence metadata contained the sentence “{REJECTED_SENTENCE}” The exact captured Beale locations page assigns 500 MW to Tulsa County and 600 MW to Pima County. V2 reuses four unaffected source files byte-for-byte and publishes corrected, non-colliding Tulsa and Pima schema-1.1 successors.

The accepted scoped metadata is Tulsa County “Capacity 500 MW” and Pima County “Expected Capacity 600 MW.” Both labels remain untyped website context only. Neither creates a capacity, load, energy, generation, PUE, or WUE row. The only normalized capacities remain 54 MW planned critical IT on the FRA5 campus and 18 MW planned critical IT on Wood Dale Phase 1. Lifecycle remains exactly eight dated observations across eleven unique entities. No operating model, workload, standardized role, coordinate, geometry, satellite, aerial, map-click, or computer-vision claim is added.

V2's two new source files and all seven artifact members received frozen modes at or after {recorded_at}; the artifact root did as well. Final v2 paths were promoted without replacement only after that instant. The four reused source files retain their exact earlier v1 source ctimes and are pinned as immutable predecessor inputs, not republished v2 members. The rejected v1 artifact's root, every member, all six source files, physical and logical trees, and exact rejected sentence are pinned in source-snapshot.json. No open-seed, release, construction-master, map, federation, coverage, or review integration is performed.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "source_records": records,
        "totals": totals,
        "rejected_v1_incident_lineage": _incident_lineage(),
        "frozen_v92_non_mutation_witness": {
            "release_tree_sha256": v1.V92_TREE_SHA256,
            **collision,
        },
        "correction_contract": {
            "tulsa_context": "Tulsa County, OK — Capacity 500 MW.",
            "pima_context": "Pima County, AZ — Expected Capacity 600 MW.",
            "both_untyped_metadata_only": True,
            "normalized_capacity_rows_added_by_correction": 0,
            "rejected_v1_integrated": False,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v92_mutated": False,
            "release_integration": "none",
            "construction_master_integration": "none",
            "map_integration": "none",
            "federation_integration": "none",
            "coverage_integration": "none",
            "review_integration": "none",
        },
        "publication_contract": {
            "version": 2,
            "all_new_source_and_artifact_member_ctimes_at_or_after_recorded_at": True,
            "artifact_root_ctime_at_or_after_recorded_at": True,
            "final_paths_absent_before_recorded_at": True,
            "publication_waited_until_recorded_at": True,
            "no_replace_promotion": True,
            "identity_checked_rollback_on_late_collision": True,
            "new_source_file_mode": "0444",
            "artifact_directory_mode": "0555",
            "artifact_file_mode": "0444",
        },
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-disposition-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "source_rights": (
            "All captured official response bodies are treated as all-rights-reserved; "
            "only exact hashes and compact factual extracts are redistributed."
        ),
        "raw_capture_redistributed": False,
        "raw_capture_reused_from_v1": True,
        "raw_capture_tree_sha256": v1.CAPTURE_TREE_SHA256,
        "raw_capture_file_count": v1.CAPTURE_FILE_COUNT,
        "raw_capture_total_bytes": v1.CAPTURE_TOTAL_BYTES,
        "raw_capture_recoverable_trash_path": str(v1.CAPTURE_TRASH),
        "publisher_media_retained_in_artifact": False,
        "deletion_performed": False,
    }
    return {
        "README.md": readme.encode(),
        "candidate-assessment.json": _canonical(_candidate_assessment(recorded_at)),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _source_paths(new_root: Path = SOURCES_ROOT) -> dict[str, Path]:
    paths = {name: SOURCES_ROOT / name for name in REUSED_SOURCE_FILENAMES}
    paths.update({name: new_root / name for name in NEW_SOURCE_FILENAMES})
    return paths


def _validate_sources(
    paths: Mapping[str, Path], *, require_new_frozen: bool
) -> list[dict[str, Any]]:
    expected = expected_source_documents()
    if set(paths) != set(SOURCE_FILENAMES):
        raise RuntimeError("v2 source path inventory differs")
    for name in SOURCE_FILENAMES:
        path = paths[name]
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"v2 source is unsafe: {name}")
        if path.read_bytes() != _canonical(expected[name]):
            raise RuntimeError(f"v2 source differs: {name}")
        mode = stat.S_IMODE(path.stat().st_mode)
        wanted = 0o444 if name in REUSED_SOURCE_FILENAMES or require_new_frozen else 0o600
        if mode != wanted:
            raise RuntimeError(f"v2 source mode differs: {name}")
    _assert_capacity_context(expected)
    documents = list(expected.values())
    if any(
        document[entity][field] is not None
        for document in documents
        for entity in ("campus", "project")
        for field in ("coordinates", "geometry")
    ):
        raise RuntimeError("v2 source invented coordinates or geometry")
    if any(
        document[entity]["roles"]
        for document in documents
        for entity in ("campus", "project")
    ):
        raise RuntimeError("v2 source invented roles")
    if any(
        document[key]
        for document in documents
        for key in ("operating_models", "workloads")
    ):
        raise RuntimeError("v2 source invented classifications")
    capacities = [row for document in documents for row in document["capacities"]]
    if sorted((row["entity"], row["metric"], row["stage"], row["base"]) for row in capacities) != [
        ("campus", "critical_it_mw", "planned", 54.0),
        ("project", "critical_it_mw", "planned", 18.0),
    ]:
        raise RuntimeError("v2 normalized capacity contract differs")
    if sum(len(document["lifecycle"]) for document in documents) != 8:
        raise RuntimeError("v2 lifecycle contract differs")
    return _source_records(expected)


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="merlin-cyrusone-beale-v2-import-", dir="/private/tmp"
    ) as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            for name in SOURCE_FILENAMES:
                adapter.import_file(connection, paths[name], recorded_at=recorded_at)
        validate_database(connection)
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
            "entities": 11,
            "entity_snapshots": 11,
            "evidence": 13,
            "lifecycle_observations": 8,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 2,
        }
        if counts != expected:
            raise RuntimeError(f"v2 offline import counts differ: {counts!r}")
        return counts


def _assert_chronology(paths: Sequence[Path], recorded_at: str) -> None:
    threshold = _instant(recorded_at).timestamp()
    for path in paths:
        if path.stat(follow_symlinks=False).st_ctime + 0.000_001 < threshold:
            raise RuntimeError(f"v2 member ctime predates recorded_at: {path}")


def validate_artifact(
    path: Path = ARTIFACT,
    *,
    source_paths: Mapping[str, Path] | None = None,
    require_live: bool = True,
    require_frozen: bool = True,
    wall_clock: datetime | None = None,
) -> dict[str, Any]:
    _require_v1_lineage()
    paths = source_paths or _source_paths()
    records = _validate_sources(paths, require_new_frozen=require_frozen)
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError("v2 artifact must be an ordinary directory")
    wanted_root = 0o555 if require_frozen else 0o700
    if stat.S_IMODE(path.stat().st_mode) != wanted_root:
        raise RuntimeError("v2 artifact root mode differs")
    entries = {entry.name: entry for entry in path.iterdir()}
    wanted_member = 0o444 if require_frozen else 0o600
    if set(entries) != CLOSED_FILES or any(
        entry.is_symlink()
        or not entry.is_file()
        or stat.S_IMODE(entry.stat().st_mode) != wanted_member
        for entry in entries.values()
    ):
        raise RuntimeError("v2 artifact member contract differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if (
        manifest_raw != _canonical(manifest)
        or manifest.get("artifact_id") != ARTIFACT_ID
        or manifest.get("curated_source_records") != 6
        or manifest.get("new_source_records") != 2
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise RuntimeError("v2 manifest contract differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (
            row["bytes"],
            row["sha256"],
        ):
            raise RuntimeError(f"v2 manifest pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text() != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise RuntimeError("v2 manifest checksum differs")
    expected_payloads = _artifact_documents(
        manifest["recorded_at"], expected_source_documents()
    )
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected_payloads[name]:
            raise RuntimeError(f"v2 artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text())
    if snapshot["source_records"] != records:
        raise RuntimeError("v2 source pins differ")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise RuntimeError("wall clock must be timezone aware")
    if require_live and now.astimezone(UTC) < target:
        raise RuntimeError("v2 recorded_at is not live")
    replay = [_offline_import(paths, manifest["recorded_at"]) for _ in range(2)]
    if replay[0] != replay[1]:
        raise RuntimeError("v2 offline replay differs")
    v1._validate_capture_directory(
        resolve_external_capture(v1.CAPTURE_ORIGIN, v1.CAPTURE_TRASH)
    )
    if require_frozen:
        _assert_chronology(
            [
                path,
                *entries.values(),
                *(paths[name] for name in NEW_SOURCE_FILENAMES),
            ],
            manifest["recorded_at"],
        )
    return manifest


def _write_source_stage(
    stage: Path, documents: Mapping[str, Mapping[str, Any]]
) -> None:
    for name in NEW_SOURCE_FILENAMES:
        path = stage / name
        path.write_bytes(_canonical(documents[name]))
        path.chmod(0o600)
        _fsync_regular(path)
    _fsync_directory(stage)


def _write_artifact_stage(
    stage: Path, recorded_at: str, documents: Mapping[str, Mapping[str, Any]]
) -> None:
    payloads = _artifact_documents(recorded_at, documents)
    for name in CONTENT_FILES:
        path = stage / name
        path.write_bytes(payloads[name])
        path.chmod(0o600)
        _fsync_regular(path)
    rows = [
        {
            "bytes": (stage / name).stat().st_size,
            "path": name,
            "sha256": _sha256(stage / name),
        }
        for name in CONTENT_FILES
    ]
    manifest = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-artifact-manifest-v3",
        "recorded_at": recorded_at,
        "files": rows,
        "tree_sha256": _file_tree(rows),
        "closed_file_set": sorted(CLOSED_FILES),
        "candidate_assessments": 5,
        "curated_source_records": 6,
        "reused_source_records": 4,
        "new_source_records": 2,
        "seed_eligible_candidates": 5,
        "review_only_candidates": 0,
        "rejected_v1_artifact_id": V1_ARTIFACT_ID,
        "rejected_v1_integrated": False,
        "all_v2_member_and_root_ctimes_at_or_after_recorded_at": True,
        "raw_capture_redistributed": False,
        "regional_completeness_claimed": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
    }
    manifest_path = stage / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    manifest_path.chmod(0o600)
    _fsync_regular(manifest_path)
    sidecar = stage / "manifest.sha256"
    sidecar.write_text(f"{_sha256(manifest_path)}  manifest.json\n")
    sidecar.chmod(0o600)
    _fsync_regular(sidecar)
    stage.chmod(0o700)
    _fsync_directory(stage)


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise RuntimeError("active v2 publication lock exists") from error
    os.write(descriptor, f"pid={os.getpid()}\n".encode())
    os.fsync(descriptor)
    metadata = os.fstat(descriptor)
    identity = (metadata.st_dev, metadata.st_ino)
    try:
        yield
    finally:
        os.close(descriptor)
        if PUBLICATION_LOCK.exists():
            current = PUBLICATION_LOCK.stat(follow_symlinks=False)
            if (current.st_dev, current.st_ino) != identity:
                raise RuntimeError("refusing substituted v2 lock cleanup")
            PUBLICATION_LOCK.unlink()


@dataclass(frozen=True)
class _Prepared:
    source_stage: Path
    artifact_stage: Path
    recorded_at: str


def _prepare(recorded_at: str) -> _Prepared:
    _require_v1_lineage()
    if (
        ARTIFACT.exists()
        or ARTIFACT.is_symlink()
        or any(
            (SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink()
            for name in NEW_SOURCE_FILENAMES
        )
    ):
        raise RuntimeError("v2 final-path collision")
    v1._validate_capture_directory(
        resolve_external_capture(v1.CAPTURE_ORIGIN, v1.CAPTURE_TRASH)
    )
    documents = expected_source_documents()
    _collision_witness(documents)
    source_stage = Path(
        tempfile.mkdtemp(prefix=".merlin-cyrusone-beale-v2-sources.", dir=SOURCES_ROOT)
    )
    artifact_stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT)
    )
    try:
        _write_source_stage(source_stage, documents)
        _write_artifact_stage(artifact_stage, recorded_at, documents)
        validate_artifact(
            artifact_stage,
            source_paths=_source_paths(source_stage),
            require_live=False,
            require_frozen=False,
            wall_clock=_instant(recorded_at),
        )
        return _Prepared(source_stage, artifact_stage, recorded_at)
    except Exception:
        if source_stage.exists():
            shutil.rmtree(source_stage)
        if artifact_stage.exists():
            shutil.rmtree(artifact_stage)
        raise


def _freeze_after_barrier(prepared: _Prepared) -> None:
    target = _instant(prepared.recorded_at)
    while datetime.now(UTC) < target:
        time.sleep(min(0.25, (target - datetime.now(UTC)).total_seconds()))
    for name in NEW_SOURCE_FILENAMES:
        path = prepared.source_stage / name
        path.chmod(0o444)
        _fsync_regular(path)
    for path in prepared.artifact_stage.iterdir():
        path.chmod(0o444)
        _fsync_regular(path)
    prepared.artifact_stage.chmod(0o555)
    _fsync_directory(prepared.source_stage)
    _fsync_directory(prepared.artifact_stage)
    _assert_chronology(
        [
            prepared.artifact_stage,
            *prepared.artifact_stage.iterdir(),
            *(prepared.source_stage / name for name in NEW_SOURCE_FILENAMES),
        ],
        prepared.recorded_at,
    )


def _publish(prepared: _Prepared) -> None:
    _freeze_after_barrier(prepared)
    if (
        ARTIFACT.exists()
        or ARTIFACT.is_symlink()
        or any(
            (SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink()
            for name in NEW_SOURCE_FILENAMES
        )
    ):
        raise RuntimeError("late v2 final-path collision")
    promoted: list[tuple[Path, Path]] = []
    try:
        for name in NEW_SOURCE_FILENAMES:
            staged = prepared.source_stage / name
            final = SOURCES_ROOT / name
            _promote_noreplace(staged, final)
            promoted.append((final, staged))
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        promoted.append((ARTIFACT, prepared.artifact_stage))
    except BaseException as error:
        for final, staged in reversed(promoted):
            try:
                _promote_noreplace(final, staged)
            except Exception as rollback_error:
                error.add_note(f"v2 rollback failed for {final}: {rollback_error}")
        raise


def _result(manifest: Mapping[str, Any], status_value: str) -> dict[str, Any]:
    return {
        "artifact": str(ARTIFACT),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "recorded_at": manifest["recorded_at"],
        "rejected_v1_artifact": str(V1_ARTIFACT),
        "reused_sources": 4,
        "new_corrected_sources": 2,
        "unique_entities": 11,
        "lifecycle_observations": 8,
        "capacity_estimates": 2,
        "status": status_value,
    }


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    if ARTIFACT.exists() and all(
        (SOURCES_ROOT / name).exists() for name in NEW_SOURCE_FILENAMES
    ):
        return _result(validate_artifact(), "existing-identical")
    if (
        ARTIFACT.exists()
        or ARTIFACT.is_symlink()
        or any(
            (SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink()
            for name in NEW_SOURCE_FILENAMES
        )
    ):
        raise RuntimeError("partial v2 final-path collision")
    target = (
        _instant(recorded_at)
        if recorded_at
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise RuntimeError("v2 recorded_at must be future before staging")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    with _publication_lock():
        prepared = _prepare(timestamp)
        _publish(prepared)
        manifest = validate_artifact()
        if any(prepared.source_stage.iterdir()):
            raise RuntimeError("v2 source stage not empty")
        prepared.source_stage.rmdir()
    return _result(manifest, "published")


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
