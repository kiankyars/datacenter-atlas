"""Build open seed v74 as the strict coordinate-only successor to v73."""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import copy
import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping

from . import open_seed_v69 as v69
from . import open_seed_v70 as v70
from .open_seed_v61 import FRESHNESS_FILENAME, build_freshness_csv
from .publication_release import build_release_documents
from .service import summarize


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v73.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v73"
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v74.json"
RELEASE_ID = "2026-07-21-open-seed-v74"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v74.lock"
AS_OF = "2026-07-21"

BASE_RECORDED_AT = "2026-07-21T13:15:51Z"
BASE_DEFINITION_BYTES = 88_004
BASE_DEFINITION_SHA256 = (
    "cf8a4cfb8861ab732cdb9e72a01cbdd01d0e435102c47fd6d92bc30ebf11f97d"
)
BASE_MANIFEST_SHA256 = (
    "229c572759ab493448b788946a0c8a61ff6995d0ab505bea2af08860a19e204d"
)
BASE_TREE_SHA256 = "692583b86324b746fd6edf0ec2dc5101efa86ce0f08e04831e0d471e767a6394"

COORDINATE_ARTIFACT = (
    ROOT / "source_artifacts/site-coordinate-assessment-2026-07-21-v5"
)
COORDINATE_RECORDED_AT = "2026-07-21T15:42:33Z"
COORDINATE_MANIFEST_SHA256 = (
    "b05492a0454502e332c6517b60e48a99f3897f29dfae9ccd4d69569da3173b34"
)
COORDINATE_MANIFEST_TREE_SHA256 = (
    "dc74260a7b03bea2f9250b8962fc47f7cb1a1e45bdedb1ee046ee67e021b17e2"
)
COORDINATE_PHYSICAL_TREE_SHA256 = (
    "ecc63ed53d0151366caaf1d3d8b82a70ff4e1476baebc737356e3d8a8f77116f"
)


@dataclass(frozen=True)
class CoordinateReplacementV5:
    predecessor_path: str
    predecessor_bytes: int
    predecessor_sha256: str
    successor_path: str
    successor_bytes: int
    successor_sha256: str
    campus_key: str
    project_key: str
    changed_entities: tuple[str, ...]
    added_evidence_key: str


REPLACEMENTS = (
    CoordinateReplacementV5(
        predecessor_path="sources/curated-official-2026-07-21-akashi-astana-phase-1-current-build.json",
        predecessor_bytes=8_057,
        predecessor_sha256=(
            "7f93487075c06e359c8f41c264633393b64b731c4f5d89b4a804dc5476db2543"
        ),
        successor_path=(
            "source_artifacts/site-coordinate-assessment-2026-07-21-v5/"
            "normalized-successors/curated-official-2026-07-21-akashi-astana-"
            "phase-1-current-build-coordinate-v5.json"
        ),
        successor_bytes=13_490,
        successor_sha256=(
            "b1f3f37927895d6e7a02adc9afd8b93aac9e0a322d846158fe362c645a07e3a6"
        ),
        campus_key="curated:akashi-astana-data-center-campus",
        project_key="curated:akashi-astana-data-center-campus:phase-1-current-build",
        changed_entities=("campus", "project"),
        added_evidence_key="kazakhstan-akashi-same-parcel-substation-coordinate-captured-2026-07-21",
    ),
    CoordinateReplacementV5(
        predecessor_path="sources/curated-official-2026-07-21-icatec-ica-current-build.json",
        predecessor_bytes=7_745,
        predecessor_sha256=(
            "8a87e5271914fc351ff01576661e9e5f315ab783489c44cf75144c03451fa4e6"
        ),
        successor_path=(
            "source_artifacts/site-coordinate-assessment-2026-07-21-v5/"
            "normalized-successors/curated-official-2026-07-21-icatec-ica-"
            "current-build-coordinate-v5.json"
        ),
        successor_bytes=13_113,
        successor_sha256=(
            "88d05044c8a3ab7ad7c4f0a42227cb610b2b0fff43863672c5faf0a121d31e2a"
        ),
        campus_key="curated:icatec-ica-digital-transformation-data-center",
        project_key=(
            "curated:icatec-ica-digital-transformation-data-center:"
            "four-storey-technology-center-build"
        ),
        changed_entities=("campus", "project"),
        added_evidence_key="peru-icatec-gore-ica-sede-central-destination-coordinate-captured-2026-07-21",
    ),
    CoordinateReplacementV5(
        predecessor_path="sources/curated-official-2026-07-21-lvrtc-pozitrons-kurzeme-current-build.json",
        predecessor_bytes=8_203,
        predecessor_sha256=(
            "8653286bdfc853918125e1294483e9175a339cc44705422d68a9bd4709d27d9b"
        ),
        successor_path=(
            "source_artifacts/site-coordinate-assessment-2026-07-21-v5/"
            "normalized-successors/curated-official-2026-07-21-lvrtc-pozitrons-"
            "kurzeme-current-build-coordinate-v5.json"
        ),
        successor_bytes=14_366,
        successor_sha256=(
            "5fce778372ee4d01b8e7990a11624ed2d588007c9a071e7f73a9e2a8a117e426"
        ),
        campus_key="curated:lvrtc-pozitrons-kurzeme-data-center",
        project_key="curated:lvrtc-pozitrons-kurzeme-data-center:phase-1-current-build",
        changed_entities=("campus", "project"),
        added_evidence_key="latvia-lvrtc-pozitrons-vzd-parcel-reference-point-captured-2026-07-21",
    ),
)

NEW_EVIDENCE_KEYS = frozenset(row.added_evidence_key for row in REPLACEMENTS)
NEW_SOURCE_FAMILIES = {
    "kazakhstan_environmental_project_records",
    "peru_gob_pe_region_ica_records",
    "latvia_vzd_cadastre_and_lvrtc_site_records",
}
COORDINATE_CONTRACT: dict[str, dict[str, Any]] = {
    "curated:akashi-astana-data-center-campus": {
        "latitude": 51.2067694444,
        "longitude": 71.4577083333,
        "geometry": {"type": "Point", "coordinates": [71.4577083333, 51.2067694444]},
        "source_family": "kazakhstan_environmental_project_records",
    },
    "curated:akashi-astana-data-center-campus:phase-1-current-build": {
        "latitude": 51.2067694444,
        "longitude": 71.4577083333,
        "geometry": {"type": "Point", "coordinates": [71.4577083333, 51.2067694444]},
        "source_family": "kazakhstan_environmental_project_records",
    },
    "curated:icatec-ica-digital-transformation-data-center": {
        "latitude": -14.075622,
        "longitude": -75.734798,
        "geometry": {"type": "Point", "coordinates": [-75.734798, -14.075622]},
        "source_family": "peru_gob_pe_region_ica_records",
    },
    "curated:icatec-ica-digital-transformation-data-center:four-storey-technology-center-build": {
        "latitude": -14.075622,
        "longitude": -75.734798,
        "geometry": {"type": "Point", "coordinates": [-75.734798, -14.075622]},
        "source_family": "peru_gob_pe_region_ica_records",
    },
    "curated:lvrtc-pozitrons-kurzeme-data-center": {
        "latitude": 56.9356302057,
        "longitude": 22.0132502617,
        "geometry": {"type": "Point", "coordinates": [22.0132502617, 56.9356302057]},
        "source_family": "latvia_vzd_cadastre_and_lvrtc_site_records",
    },
    "curated:lvrtc-pozitrons-kurzeme-data-center:phase-1-current-build": {
        "latitude": 56.9356302057,
        "longitude": 22.0132502617,
        "geometry": {"type": "Point", "coordinates": [22.0132502617, 56.9356302057]},
        "source_family": "latvia_vzd_cadastre_and_lvrtc_site_records",
    },
}

BICHUTEN_PATH = "sources/curated-official-2026-07-21-bichuten-chovar-current-build.json"
BICHUTEN_PIN = (
    5_339,
    "6c7b84b59da58cd5bcce44bff041578b22a243279db9e836bb6ce54c610ce1eb",
)

FRESHNESS_README = f"""
Open seed v74 is the exact accepted v73 successor with only three curated
inputs replaced in place by the coordinate-only successors accepted in
`source_artifacts/site-coordinate-assessment-2026-07-21-v5`. Input cardinality
remains 397. Akashi gains an official same-parcel substation representative
point, ICATEC gains the official regional-government Sede Central destination
point, and LVRTC gains the official VZD cadastral reference point. Each point
locates both its campus and explicitly parented project.

The coordinate artifact manifest is `{COORDINATE_MANIFEST_SHA256}`, manifest
tree `{COORDINATE_MANIFEST_TREE_SHA256}`, and physical tree
`{COORDINATE_PHYSICAL_TREE_SHA256}`. Bichuten remains unchanged and unlocated:
Chovar-06 and Kirtipur Municipality do not establish a facility-specific point.
No locality centroid, OSM point, Google content, geocoder result, or
analyst-selected point is integrated.

No identity, lifecycle, capacity, energy, consumption, ownership, operator,
tenant, workload, type, or current-status claim changes. Every lifecycle value
remains a dated last-observed fact; `current_status_classification` remains
`unknown` and `current_construction_claim` remains `false`.
""".strip()


class OpenSeedV74Error(RuntimeError):
    """Raised when a v74 lineage or publication condition fails closed."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _canonical_source_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def _read_json(
    path: Path, *, mode: int | None = None, source_order: bool = False
) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise OpenSeedV74Error(f"expected ordinary JSON file: {path}")
    if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
        raise OpenSeedV74Error(f"file mode differs: {path}")
    raw = path.read_bytes()
    document = json.loads(raw)
    expected = _canonical_source_json(document) if source_order else _canonical_json(document)
    if raw != expected:
        raise OpenSeedV74Error(f"JSON is not canonical: {path}")
    return raw, document


def _validate_coordinate_artifact() -> dict[str, Any]:
    artifact = COORDINATE_ARTIFACT
    publication_contract = {
        "recorded_at": COORDINATE_RECORDED_AT,
        "all_private_stage_birth_and_mtime_not_later_than_recorded_at": True,
        "final_paths_absent_until_recorded_at_live": True,
        "frozen_before_promotion": True,
        "atomic_no_replace_promotion": True,
        "final_root_ctime_not_earlier_than_recorded_at": True,
        "identity_safe_cleanup": True,
    }
    if (
        artifact.is_symlink()
        or not artifact.is_dir()
        or stat.S_IMODE(artifact.stat().st_mode) != 0o555
        or v69.tree_digest(artifact) != COORDINATE_PHYSICAL_TREE_SHA256
    ):
        raise OpenSeedV74Error("coordinate v5 artifact is not exact and frozen")
    if any(
        path.is_symlink()
        or stat.S_IMODE(path.stat().st_mode) != (0o555 if path.is_dir() else 0o444)
        for path in artifact.rglob("*")
    ):
        raise OpenSeedV74Error("coordinate v5 artifact member mode differs")
    manifest_raw, manifest = _read_json(
        artifact / "manifest.json", mode=0o444, source_order=True
    )
    if (
        _sha256(manifest_raw) != COORDINATE_MANIFEST_SHA256
        or manifest.get("schema_version") != "1.2"
        or manifest.get("artifact_id")
        != "site-coordinate-assessment-2026-07-21-v5"
        or manifest.get("recorded_at") != COORDINATE_RECORDED_AT
        or manifest.get("integration") != "none"
        or manifest.get("publication_contract_version") != 5
        or manifest.get("publication") != publication_contract
        or manifest.get("tree_sha256") != COORDINATE_MANIFEST_TREE_SHA256
    ):
        raise OpenSeedV74Error("coordinate v5 manifest contract differs")
    listed = manifest.get("files")
    if not isinstance(listed, list):
        raise OpenSeedV74Error("coordinate v5 file inventory differs")
    actual = {
        path.relative_to(artifact).as_posix()
        for path in artifact.rglob("*")
        if path.is_file()
    }
    if actual != {row["path"] for row in listed} | {"manifest.json", "manifest.sha256"}:
        raise OpenSeedV74Error("coordinate v5 is not a closed file set")
    for row in listed:
        raw = (artifact / row["path"]).read_bytes()
        if (len(raw), _sha256(raw)) != (row["bytes"], row["sha256"]):
            raise OpenSeedV74Error(f"coordinate v5 file pin differs: {row['path']}")
    if _sha256(_canonical_source_json(listed)) != COORDINATE_MANIFEST_TREE_SHA256:
        raise OpenSeedV74Error("coordinate v5 manifest tree differs")
    if (artifact / "manifest.sha256").read_text() != (
        f"{COORDINATE_MANIFEST_SHA256}  manifest.json\n"
    ):
        raise OpenSeedV74Error("coordinate v5 sidecar differs")
    recorded = v70.parse_utc(COORDINATE_RECORDED_AT, label="coordinate recorded_at")
    if artifact.stat().st_ctime + 1e-6 < recorded.timestamp() or recorded > datetime.now(UTC):
        raise OpenSeedV74Error("coordinate v5 publication time differs")
    _, disposition = _read_json(
        artifact / "disposition.json", mode=0o444, source_order=True
    )
    successors = disposition.get("accepted", {}).get("successors", {})
    blocked = disposition.get("blocked", {})
    boundaries = disposition.get("source_boundaries", {})
    if (
        disposition.get("artifact_id")
        != "site-coordinate-assessment-2026-07-21-v5"
        or disposition.get("recorded_at") != COORDINATE_RECORDED_AT
        or disposition.get("integration") != "none"
        or disposition.get("accepted_seed_definition") is not None
        or disposition.get("non_coordinate_claims_added") != []
        or len(successors) != 3
        or blocked.get("project_rows") != 1
        or len(blocked.get("rows", [])) != 1
        or blocked["rows"][0].get("predecessor") != BICHUTEN_PATH
        or blocked["rows"][0].get("successor") is not None
        or boundaries.get("osm_inputs_consumed") != []
        or boundaries.get("osm_routed_through_curated_official_importer") is not False
        or boundaries.get("google_content_captured_or_redistributed") is not False
        or boundaries.get("raw_official_bodies_redistributed") is not False
        or boundaries.get("satellite_or_cv_claims_added") is not False
        or disposition.get("publication_contract") != publication_contract
    ):
        raise OpenSeedV74Error("coordinate v5 disposition differs")
    lineage = disposition.get("lineage", {})
    if (
        lineage.get("base_definition")
        != {
            "path": "sources/open-seed-2026-07-21-v73.json",
            "bytes": BASE_DEFINITION_BYTES,
            "sha256": BASE_DEFINITION_SHA256,
        }
        or lineage.get("base_manifest")
        != {
            "path": "releases/2026-07-21-open-seed-v73/manifest.json",
            "bytes": 12_814,
            "sha256": BASE_MANIFEST_SHA256,
        }
    ):
        raise OpenSeedV74Error("coordinate v5 base lineage differs")
    expected_successors = {
        replacement.campus_key: replacement for replacement in REPLACEMENTS
    }
    for row in successors.values():
        replacement = expected_successors.get(row.get("campus_key"))
        if replacement is None or (
            row.get("path")
            != replacement.successor_path.removeprefix(
                "source_artifacts/site-coordinate-assessment-2026-07-21-v5/"
            )
            or row.get("bytes") != replacement.successor_bytes
            or row.get("sha256") != replacement.successor_sha256
            or row.get("predecessor") != replacement.predecessor_path
            or row.get("predecessor_sha256") != replacement.predecessor_sha256
            or row.get("project_key") != replacement.project_key
            or tuple(row.get("changed_entities", [])) != replacement.changed_entities
            or row.get("added_evidence_key") != replacement.added_evidence_key
        ):
            raise OpenSeedV74Error("coordinate v5 accepted-successor pin differs")
    _, observations = _read_json(
        artifact / "coordinate-observations.json", mode=0o444, source_order=True
    )
    scope = observations.get("assessment_scope", {})
    if (
        observations.get("integration") != "none"
        or scope.get("project_rows") != 4
        or scope.get("accepted_successors") != 3
        or scope.get("accepted_project_locations") != 3
        or scope.get("accepted_campus_location_mutations") != 3
        or scope.get("blocked_project_rows") != 1
    ):
        raise OpenSeedV74Error("coordinate v5 observation scope differs")
    accepted_rows = {
        row.get("predecessor"): row
        for row in observations.get("rows", [])
        if row.get("successor") is not None
    }
    if set(accepted_rows) != {
        replacement.predecessor_path for replacement in REPLACEMENTS
    }:
        raise OpenSeedV74Error("coordinate v5 observation rows differ")
    for replacement in REPLACEMENTS:
        row = accepted_rows[replacement.predecessor_path]
        contract = COORDINATE_CONTRACT[replacement.campus_key]
        if (
            row.get("predecessor_bytes") != replacement.predecessor_bytes
            or row.get("predecessor_sha256") != replacement.predecessor_sha256
            or row.get("campus_key") != replacement.campus_key
            or row.get("project_key") != replacement.project_key
            or row.get("successor")
            != replacement.successor_path.removeprefix(
                "source_artifacts/site-coordinate-assessment-2026-07-21-v5/"
            )
            or tuple(row.get("changed_entities", []))
            != replacement.changed_entities
            or row.get("coordinate", {}).get("latitude")
            != contract["latitude"]
            or row.get("coordinate", {}).get("longitude")
            != contract["longitude"]
        ):
            raise OpenSeedV74Error("coordinate v5 observation pin differs")
    return manifest


def _validate_successor(
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    replacement: CoordinateReplacementV5,
) -> None:
    if (
        predecessor.get("schema_version") != "1.1"
        or successor.get("schema_version") != "1.1"
        or set(predecessor) != set(successor)
    ):
        raise OpenSeedV74Error("coordinate v5 schema contract differs")
    before_evidence = predecessor.get("evidence")
    after_evidence = successor.get("evidence")
    if (
        not isinstance(before_evidence, list)
        or not isinstance(after_evidence, list)
        or after_evidence[:-1] != before_evidence
        or len(after_evidence) != len(before_evidence) + 1
        or after_evidence[-1].get("key") != replacement.added_evidence_key
        or after_evidence[-1].get("kind") != "government_record"
    ):
        raise OpenSeedV74Error("coordinate v5 evidence append differs")
    restored = copy.deepcopy(successor)
    restored["evidence"] = copy.deepcopy(before_evidence)
    expected_keys = {
        "campus": replacement.campus_key,
        "project": replacement.project_key,
    }
    for entity_name, stable_key in expected_keys.items():
        before = predecessor[entity_name]
        after = successor[entity_name]
        if before.get("stable_key") != stable_key or after.get("stable_key") != stable_key:
            raise OpenSeedV74Error("coordinate v5 entity identity differs")
        changed = {
            key for key in set(before) | set(after) if before.get(key) != after.get(key)
        }
        if entity_name in replacement.changed_entities:
            if changed != {"coordinates", "geometry", "evidence_key", "method"}:
                raise OpenSeedV74Error("coordinate v5 non-coordinate delta detected")
            if before.get("coordinates") is not None or before.get("geometry") is not None:
                raise OpenSeedV74Error("coordinate v5 predecessor was already located")
            if after.get("method") != "authoritative_site_plan":
                raise OpenSeedV74Error("coordinate v5 method differs")
            for key in changed:
                restored[entity_name][key] = copy.deepcopy(before[key])
        elif changed:
            raise OpenSeedV74Error("coordinate v5 changed an excluded entity")
    if restored != predecessor:
        raise OpenSeedV74Error("coordinate v5 successor gained another claim")
    for section in ("lifecycle", "operating_models", "workloads", "capacities"):
        if successor[section] != predecessor[section] or any(
            row.get("evidence_key") == replacement.added_evidence_key
            for row in successor[section]
        ):
            raise OpenSeedV74Error(f"coordinate v5 changed {section}")
    evidence = after_evidence[-1]
    contract = COORDINATE_CONTRACT[replacement.campus_key]
    metadata = evidence.get("metadata", {})
    if (
        evidence.get("source_family") != contract["source_family"]
        or metadata.get("capture_artifact_id")
        != "site-coordinate-assessment-2026-07-21-v5"
        or metadata.get("stored_coordinate")
        != {
            "latitude": contract["latitude"],
            "longitude": contract["longitude"],
        }
        or metadata.get("coordinate_method") != "authoritative_site_plan"
        or "changes only campus and project coordinate snapshot fields"
        not in metadata.get("claim_guardrail", "")
        or "No OpenStreetMap-derived point" not in metadata.get("osm_guardrail", "")
    ):
        raise OpenSeedV74Error("coordinate v5 evidence boundary differs")


def _base_paths(base: Mapping[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for row in base["curated_inputs"]:
        path = ROOT / row["path"]
        if path.is_symlink() or not path.is_file() or v69.sha256(path) != row["sha256"]:
            raise OpenSeedV74Error(f"accepted v73 input pin differs: {row['path']}")
        paths.append(path)
    return paths


def selected_inputs(
    base: Mapping[str, Any],
    *,
    recorded_at: str,
    validation_wall_clock: datetime | None = None,
) -> tuple[list[dict[str, str]], list[Path]]:
    if base.get("release_id") != "2026-07-21-open-seed-v73":
        raise OpenSeedV74Error("v74 base must be exactly accepted v73")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 397:
        raise OpenSeedV74Error("accepted v73 curated inventory differs")
    _validate_coordinate_artifact()
    target = v70.parse_utc(recorded_at, label="v74 recorded_at")
    wall = validation_wall_clock or datetime.now(UTC)
    if wall.tzinfo is None or target > wall.astimezone(UTC):
        raise OpenSeedV74Error("v74 recorded_at is later than validation wall clock")

    by_predecessor = {row.predecessor_path: row for row in REPLACEMENTS}
    if len(by_predecessor) != 3:
        raise OpenSeedV74Error("v74 replacement inventory differs")
    selected: list[dict[str, str]] = []
    paths: list[Path] = []
    selected_documents: list[tuple[str, Mapping[str, Any]]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise OpenSeedV74Error("accepted v73 curated row differs")
        replacement = by_predecessor.get(row["path"])
        if replacement is None:
            path = ROOT / row["path"]
            if path.is_symlink() or not path.is_file() or v69.sha256(path) != row["sha256"]:
                raise OpenSeedV74Error(f"accepted v73 input drifted: {row['path']}")
            document = json.loads(path.read_text())
            output_row = dict(row)
        else:
            if row["sha256"] != replacement.predecessor_sha256:
                raise OpenSeedV74Error("v74 predecessor definition pin differs")
            predecessor_path = ROOT / replacement.predecessor_path
            predecessor_raw, predecessor = _read_json(
                predecessor_path, mode=0o644, source_order=True
            )
            if (len(predecessor_raw), _sha256(predecessor_raw)) != (
                replacement.predecessor_bytes,
                replacement.predecessor_sha256,
            ):
                raise OpenSeedV74Error("v74 predecessor byte pin differs")
            path = ROOT / replacement.successor_path
            successor_raw, document = _read_json(path, mode=0o444, source_order=True)
            if (len(successor_raw), _sha256(successor_raw)) != (
                replacement.successor_bytes,
                replacement.successor_sha256,
            ):
                raise OpenSeedV74Error("v74 successor byte pin differs")
            _validate_successor(predecessor, document, replacement)
            output_row = {
                "path": replacement.successor_path,
                "sha256": replacement.successor_sha256,
            }
            seen.add(replacement.predecessor_path)
        selected.append(output_row)
        paths.append(path)
        selected_documents.append((output_row["path"], document))

    if seen != set(by_predecessor) or len(selected) != 397:
        raise OpenSeedV74Error("v74 replacement selection is incomplete")
    selected_names = [row["path"] for row in selected]
    if len(set(selected_names)) != 397 or any(
        replacement.predecessor_path in selected_names for replacement in REPLACEMENTS
    ):
        raise OpenSeedV74Error("v74 selected inventory collides")
    bichuten = ROOT / BICHUTEN_PATH
    if (
        BICHUTEN_PATH not in selected_names
        or (bichuten.stat().st_size, v69.sha256(bichuten)) != BICHUTEN_PIN
        or selected[selected_names.index(BICHUTEN_PATH)]
        != {"path": BICHUTEN_PATH, "sha256": BICHUTEN_PIN[1]}
    ):
        raise OpenSeedV74Error("v74 changed blocked Bichuten input")
    for relative, document in selected_documents:
        for index, evidence in enumerate(document.get("evidence", [])):
            retrieved = v70.parse_utc(
                evidence.get("retrieved_at"),
                label=f"{relative} evidence[{index}].retrieved_at",
            )
            if retrieved > target or retrieved > wall.astimezone(UTC):
                raise OpenSeedV74Error("v74 selected evidence is future-dated")
    return selected, paths


def _guard_state() -> dict[str, Any]:
    _validate_coordinate_artifact()
    predecessors = {}
    successors = {}
    for replacement in REPLACEMENTS:
        path = ROOT / replacement.predecessor_path
        predecessors[replacement.predecessor_path] = (
            path.stat().st_size,
            v69.sha256(path),
        )
        successor = ROOT / replacement.successor_path
        successors[replacement.successor_path] = (
            successor.stat().st_size,
            v69.sha256(successor),
        )
    return {
        "base_definition": (BASE_DEFINITION.stat().st_size, v69.sha256(BASE_DEFINITION)),
        "base_manifest": v69.sha256(BASE_RELEASE / "manifest.json"),
        "base_tree": v69.tree_digest(BASE_RELEASE),
        "coordinate_manifest": v69.sha256(COORDINATE_ARTIFACT / "manifest.json"),
        "coordinate_tree": v69.tree_digest(COORDINATE_ARTIFACT),
        "predecessors": predecessors,
        "successors": successors,
        "bichuten": (
            (ROOT / BICHUTEN_PATH).stat().st_size,
            v69.sha256(ROOT / BICHUTEN_PATH),
        ),
    }


def _logical_rows(connection: sqlite3.Connection, table: str) -> Counter[tuple[Any, ...]]:
    if table == "lifecycle_observations":
        query = """
            SELECT entities.stable_key, status, evidence.title, evidence.source_url,
                   as_of_date, valid_to_date, method, confidence, notes
            FROM lifecycle_observations
            JOIN entities ON entities.id = entity_id
            JOIN evidence ON evidence.id = evidence_id
        """
    elif table == "capacity_estimates":
        query = """
            SELECT entities.stable_key, metric, stage, unit, low, base, high,
                   method, confidence, evidence.title, evidence.source_url,
                   as_of_date, target_date, valid_to_date, notes
            FROM capacity_estimates
            JOIN entities ON entities.id = entity_id
            JOIN evidence ON evidence.id = evidence_id
        """
    elif table in {"operating_model_observations", "workload_observations"}:
        value = (
            "operating_model"
            if table == "operating_model_observations"
            else "workload"
        )
        query = f"""
            SELECT entities.stable_key, {value}, evidence.title, evidence.source_url,
                   as_of_date, valid_to_date, method, confidence, notes
            FROM {table}
            JOIN entities ON entities.id = entity_id
            JOIN evidence ON evidence.id = evidence_id
        """
    else:  # pragma: no cover - internal misuse guard
        raise OpenSeedV74Error(f"unsupported logical table: {table}")
    return Counter(tuple(row) for row in connection.execute(query))


def _snapshot_rows(
    connection: sqlite3.Connection,
) -> dict[str, list[tuple[Any, ...]]]:
    rows: dict[str, list[tuple[Any, ...]]] = {}
    for row in connection.execute(
        """
        SELECT entities.stable_key, entity_snapshots.name, latitude, longitude,
               geometry_json, tags_json, evidence.source_family, evidence.title,
               evidence.source_url, as_of_date, valid_to_date,
               entity_snapshots.method, entity_snapshots.confidence
        FROM entity_snapshots
        JOIN entities ON entities.id = entity_id
        JOIN evidence ON evidence.id = evidence_id
        """
    ):
        rows.setdefault(row[0], []).append(tuple(row[1:]))
    for values in rows.values():
        values.sort(key=repr)
    return rows


def _validate_database_contract(
    connection: sqlite3.Connection,
    base: Mapping[str, Any],
    *,
    recorded_at: str,
) -> None:
    expected = {
        "entities": 818,
        "evidence": 646,
        "entity_snapshots": 838,
        "lifecycle_observations": 479,
        "capacity_estimates": 535,
        "operating_model_observations": 59,
        "workload_observations": 128,
    }
    actual = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in expected
    }
    if actual != expected:
        raise OpenSeedV74Error(f"v74 database counts differ: {actual}")
    with tempfile.TemporaryDirectory(prefix="open-seed-v74-base-", dir="/private/tmp") as td:
        prior = v69._populate_database(
            base, _base_paths(base), Path(td) / "v73.sqlite", recorded_at=recorded_at
        )
        try:
            before_entities = {
                tuple(row)
                for row in prior.execute("SELECT stable_key, kind FROM entities")
            }
            after_entities = {
                tuple(row)
                for row in connection.execute("SELECT stable_key, kind FROM entities")
            }
            if before_entities != after_entities:
                raise OpenSeedV74Error("v74 entity identities changed")
            before_evidence = {
                tuple(row)
                for row in prior.execute(
                    "SELECT title, source_url, publisher, source_family, content_hash FROM evidence"
                )
            }
            after_evidence = {
                tuple(row)
                for row in connection.execute(
                    "SELECT title, source_url, publisher, source_family, content_hash FROM evidence"
                )
            }
            added = after_evidence - before_evidence
            if (
                before_evidence - after_evidence
                or len(added) != 3
                or {row[3] for row in added} != NEW_SOURCE_FAMILIES
            ):
                raise OpenSeedV74Error("v74 evidence delta differs")
            before_evidence_keys = set(v70._evidence_by_key(prior))
            after_evidence_keys = set(v70._evidence_by_key(connection))
            if (
                after_evidence_keys - before_evidence_keys != NEW_EVIDENCE_KEYS
                or before_evidence_keys - after_evidence_keys
            ):
                raise OpenSeedV74Error("v74 evidence-key delta differs")
            for table in (
                "lifecycle_observations",
                "capacity_estimates",
                "operating_model_observations",
                "workload_observations",
            ):
                if _logical_rows(prior, table) != _logical_rows(connection, table):
                    raise OpenSeedV74Error(f"v74 changed logical {table}")
            before_snapshots = _snapshot_rows(prior)
            after_snapshots = _snapshot_rows(connection)
            if set(before_snapshots) != set(after_snapshots):
                raise OpenSeedV74Error("v74 snapshot identities changed")
            for stable_key in before_snapshots:
                if stable_key in COORDINATE_CONTRACT:
                    continue
                if before_snapshots[stable_key] != after_snapshots[stable_key]:
                    raise OpenSeedV74Error(
                        f"v74 changed a non-coordinate snapshot: {stable_key}"
                    )
            for stable_key, contract in COORDINATE_CONTRACT.items():
                if any(
                    row[1] is not None or row[2] is not None or row[3] not in {None, "null"}
                    for row in before_snapshots[stable_key]
                ):
                    raise OpenSeedV74Error(
                        f"v74 coordinate predecessor was already located: {stable_key}"
                    )
                rows = after_snapshots[stable_key]
                if len(rows) != 1:
                    raise OpenSeedV74Error(f"v74 coordinate snapshot count differs: {stable_key}")
                row = rows[0]
                if (
                    row[1] != contract["latitude"]
                    or row[2] != contract["longitude"]
                    or json.loads(row[3]) != contract["geometry"]
                    or row[5] != contract["source_family"]
                    or row[10] != "authoritative_site_plan"
                ):
                    raise OpenSeedV74Error(f"v74 coordinate snapshot differs: {stable_key}")
        finally:
            prior.close()
    new_evidence_ids = {
        row[0]
        for row in connection.execute(
            f"SELECT id FROM evidence WHERE source_family IN "
            f"({','.join('?' for _ in NEW_SOURCE_FAMILIES)})",
            tuple(sorted(NEW_SOURCE_FAMILIES)),
        )
    }
    if len(new_evidence_ids) != 3:
        raise OpenSeedV74Error("v74 new evidence identity count differs")
    placeholders = ",".join("?" for _ in new_evidence_ids)
    for table in (
        "lifecycle_observations",
        "capacity_estimates",
        "operating_model_observations",
        "workload_observations",
    ):
        if connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE evidence_id IN ({placeholders})",
            tuple(new_evidence_ids),
        ).fetchone()[0]:
            raise OpenSeedV74Error(f"coordinate evidence created {table}")


def _build_database(
    base: Mapping[str, Any],
    paths: list[Path],
    sqlite_path: Path,
    *,
    recorded_at: str,
) -> sqlite3.Connection:
    connection = v69._populate_database(base, paths, sqlite_path, recorded_at=recorded_at)
    try:
        _validate_database_contract(connection, base, recorded_at=recorded_at)
        return connection
    except Exception:
        connection.close()
        raise


def _augment_release(documents: Mapping[str, str]) -> dict[str, str]:
    output = dict(documents)
    freshness = build_freshness_csv(output["entities.csv"], as_of=AS_OF)
    output[FRESHNESS_FILENAME] = freshness
    output["README.md"] = output["README.md"].rstrip() + "\n\n" + FRESHNESS_README + "\n"
    manifest = json.loads(output["manifest.json"])
    manifest["files"]["README.md"] = {
        "bytes": len(output["README.md"].encode()),
        "sha256": _sha256(output["README.md"].encode()),
    }
    manifest["files"][FRESHNESS_FILENAME] = {
        "bytes": len(freshness.encode()),
        "sha256": _sha256(freshness.encode()),
    }
    manifest["current_status_inferred"] = False
    manifest["lifecycle_freshness_records"] = len(
        list(csv.DictReader(io.StringIO(freshness)))
    )
    manifest["lifecycle_status_semantics"] = "last_observed"
    output["manifest.json"] = _canonical_json(manifest).decode()
    return output


def _write_release(
    connection: sqlite3.Connection,
    output: Path,
    *,
    recorded_at: str,
    precreated: bool = False,
    member_identities: dict[str, tuple[int, int]] | None = None,
) -> None:
    if precreated:
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise OpenSeedV74Error("precreated v74 release stage must be empty")
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
        if member_identities is not None:
            member_identities[filename] = _path_identity(path, directory=False)


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _validate_release_delta(stage: Path, *, recorded_at: str) -> None:
    for filename in (
        "capacity_estimates.csv",
        "lifecycle_freshness.csv",
        "resolution_candidates.csv",
        "resolution_candidates.json",
    ):
        if (stage / filename).read_bytes() != (BASE_RELEASE / filename).read_bytes():
            raise OpenSeedV74Error(
                f"v74 changed invariant release file: {filename}"
            )

    before_evidence = {
        row["evidence_id"]: row for row in _csv_rows(BASE_RELEASE / "evidence.csv")
    }
    after_evidence = {
        row["evidence_id"]: row for row in _csv_rows(stage / "evidence.csv")
    }
    if set(before_evidence) - set(after_evidence) or any(
        after_evidence[key] != row for key, row in before_evidence.items()
    ):
        raise OpenSeedV74Error("v74 changed prior public evidence")
    added = [row for key, row in after_evidence.items() if key not in before_evidence]
    if (
        len(added) != 3
        or {row["source_family"] for row in added} != NEW_SOURCE_FAMILIES
        or {row["kind"] for row in added} != {"government_record"}
    ):
        raise OpenSeedV74Error("v74 public evidence delta differs")
    added_urls = {row["source_url"] for row in added}

    before_entities = {
        row["stable_key"]: row for row in _csv_rows(BASE_RELEASE / "entities.csv")
    }
    after_entities = {
        row["stable_key"]: row for row in _csv_rows(stage / "entities.csv")
    }
    if set(before_entities) != set(after_entities) or len(after_entities) != 818:
        raise OpenSeedV74Error("v74 public entity inventory differs")
    allowed = {
        "latitude",
        "longitude",
        "geometry_json",
        "snapshot_evidence_id",
        "source_url",
        "source_publisher",
        "source_license",
        "source_retrieved_at",
    }
    changed_entities: set[str] = set()
    for stable_key, before in before_entities.items():
        after = after_entities[stable_key]
        changed = {key for key in before if before[key] != after[key]}
        if stable_key not in COORDINATE_CONTRACT:
            if changed:
                raise OpenSeedV74Error(f"v74 changed public entity: {stable_key}")
            continue
        changed_entities.add(stable_key)
        if not changed or not changed <= allowed:
            raise OpenSeedV74Error(
                f"v74 coordinate entity delta differs: {stable_key}"
            )
        contract = COORDINATE_CONTRACT[stable_key]
        if (
            after["latitude"] != str(contract["latitude"])
            or after["longitude"] != str(contract["longitude"])
            or json.loads(after["geometry_json"]) != contract["geometry"]
            or after["source_url"] not in added_urls
            or after["status"] != before["status"]
            or after["capacity_estimates_json"]
            != before["capacity_estimates_json"]
            or after["workloads_json"] != before["workloads_json"]
        ):
            raise OpenSeedV74Error(
                f"v74 coordinate entity facts differ: {stable_key}"
            )
    if changed_entities != set(COORDINATE_CONTRACT):
        raise OpenSeedV74Error("v74 changed-coordinate entity set differs")

    before_pipeline = {
        row["stable_key"]: row
        for row in _csv_rows(BASE_RELEASE / "construction_pipeline.csv")
    }
    after_pipeline = {
        row["stable_key"]: row
        for row in _csv_rows(stage / "construction_pipeline.csv")
    }
    if set(before_pipeline) != set(after_pipeline) or len(after_pipeline) != 420:
        raise OpenSeedV74Error("v74 pipeline inventory differs")
    changed_pipeline: set[str] = set()
    for stable_key, before in before_pipeline.items():
        after = after_pipeline[stable_key]
        changed = {key for key in before if before[key] != after[key]}
        if not changed:
            continue
        changed_pipeline.add(stable_key)
        if stable_key not in COORDINATE_CONTRACT or not changed <= allowed:
            raise OpenSeedV74Error(f"v74 pipeline delta differs: {stable_key}")
        contract = COORDINATE_CONTRACT[stable_key]
        if (
            after["latitude"] != str(contract["latitude"])
            or after["longitude"] != str(contract["longitude"])
            or json.loads(after["geometry_json"]) != contract["geometry"]
            or after["status"] != before["status"]
            or after["capacity_estimates_json"]
            != before["capacity_estimates_json"]
            or after["workloads_json"] != before["workloads_json"]
        ):
            raise OpenSeedV74Error(f"v74 pipeline facts differ: {stable_key}")
    expected_projects = {row.project_key for row in REPLACEMENTS}
    if changed_pipeline != expected_projects:
        raise OpenSeedV74Error("v74 pipeline coordinate set differs")

    before_signals = {
        row["source_observation_evidence_id"]: row
        for row in _csv_rows(BASE_RELEASE / "construction_source_signals.csv")
    }
    after_signals = {
        row["source_observation_evidence_id"]: row
        for row in _csv_rows(stage / "construction_source_signals.csv")
    }
    if set(before_signals) != set(after_signals) or len(after_signals) != 322:
        raise OpenSeedV74Error("v74 construction-signal inventory differs")
    changed_signals: set[str] = set()
    for key, before in before_signals.items():
        after = after_signals[key]
        changed = {field for field in before if before[field] != after[field]}
        if not changed:
            continue
        stable_key = after["representative_stable_key"]
        changed_signals.add(stable_key)
        contract = COORDINATE_CONTRACT.get(stable_key)
        if (
            stable_key not in expected_projects
            or changed
            != {"representative_latitude", "representative_longitude"}
            or contract is None
            or after["representative_latitude"] != str(contract["latitude"])
            or after["representative_longitude"] != str(contract["longitude"])
        ):
            raise OpenSeedV74Error(
                f"v74 construction-signal delta differs: {stable_key}"
            )
    if changed_signals != expected_projects:
        raise OpenSeedV74Error("v74 construction-signal coordinate set differs")

    before_sources = json.loads(
        (BASE_RELEASE / "source_inputs.json").read_text()
    )["sources"]
    after_sources = json.loads((stage / "source_inputs.json").read_text())[
        "sources"
    ]
    before_source_rows = {
        json.dumps(row, sort_keys=True, ensure_ascii=False) for row in before_sources
    }
    after_source_rows = {
        json.dumps(row, sort_keys=True, ensure_ascii=False) for row in after_sources
    }
    added_sources = [
        json.loads(row) for row in after_source_rows - before_source_rows
    ]
    if (
        before_source_rows - after_source_rows
        or len(added_sources) != 3
        or {row["source_family"] for row in added_sources}
        != NEW_SOURCE_FAMILIES
    ):
        raise OpenSeedV74Error("v74 source-input evidence delta differs")

    before_atlas = json.loads((BASE_RELEASE / "atlas.geojson").read_text())
    after_atlas = json.loads((stage / "atlas.geojson").read_text())
    before_features = {
        row["properties"]["stable_key"]: row for row in before_atlas["features"]
    }
    after_features = {
        row["properties"]["stable_key"]: row for row in after_atlas["features"]
    }
    if (
        set(before_features) != set(after_features)
        or len(after_features) != 818
        or set(after_features) != set(after_entities)
    ):
        raise OpenSeedV74Error("v74 atlas inventory differs")
    allowed_properties = {
        "latitude",
        "longitude",
        "snapshot_evidence_id",
        "source_attribution",
        "source_family",
        "source_license",
        "source_published_at",
        "source_publisher",
        "source_retrieved_at",
        "source_url",
    }
    for stable_key, before in before_features.items():
        after = after_features[stable_key]
        if stable_key not in COORDINATE_CONTRACT:
            if after != before:
                raise OpenSeedV74Error(
                    f"v74 changed non-coordinate atlas feature: {stable_key}"
                )
            continue
        property_changes = {
            key
            for key in before["properties"]
            if before["properties"][key] != after["properties"][key]
        }
        if (
            not property_changes
            or not property_changes <= allowed_properties
            or before["geometry"] is not None
        ):
            raise OpenSeedV74Error(
                f"v74 atlas feature delta differs: {stable_key}"
            )
        restored = copy.deepcopy(after)
        restored["geometry"] = before["geometry"]
        for key in property_changes:
            restored["properties"][key] = copy.deepcopy(
                before["properties"][key]
            )
        if restored != before:
            raise OpenSeedV74Error(
                f"v74 atlas feature gained another delta: {stable_key}"
            )
        contract = COORDINATE_CONTRACT[stable_key]
        if (
            after["geometry"] != contract["geometry"]
            or after["properties"]["latitude"] != contract["latitude"]
            or after["properties"]["longitude"] != contract["longitude"]
            or after["properties"]["source_family"]
            != contract["source_family"]
        ):
            raise OpenSeedV74Error(f"v74 atlas coordinate differs: {stable_key}")

    before_summary = json.loads((BASE_RELEASE / "summary.json").read_text())
    summary = json.loads((stage / "summary.json").read_text())
    expected_summary = copy.deepcopy(before_summary)
    expected_summary.update(
        {
            "campuses_with_coordinates": 135,
            "entities_with_coordinates": 198,
            "evidence_by_kind": {
                **before_summary["evidence_by_kind"],
                "government_record": 89,
            },
            "evidence_total": 646,
            "recorded_at": recorded_at,
        }
    )
    if summary != expected_summary:
        raise OpenSeedV74Error("v74 public summary differs")

    base_manifest = json.loads((BASE_RELEASE / "manifest.json").read_text())
    manifest = json.loads((stage / "manifest.json").read_text())
    expected_source_families = sorted(
        set(base_manifest["source_families"]) | NEW_SOURCE_FAMILIES
    )
    if (
        manifest.get("recorded_at") != recorded_at
        or manifest.get("entities") != 818
        or manifest.get("entities_by_kind") != {"campus": 431, "project": 387}
        or manifest.get("evidence_records") != 523
        or manifest.get("capacity_estimates") != 534
        or manifest.get("construction_pipeline_records") != 420
        or manifest.get("construction_source_signals") != 322
        or manifest.get("resolution_candidates") != 7
        or manifest.get("lifecycle_freshness_records") != 462
        or manifest.get("source_families") != expected_source_families
        or len(manifest.get("source_families", [])) != 297
        or manifest.get("current_status_inferred") is not False
        or manifest.get("publication_contract_version") != 4
    ):
        raise OpenSeedV74Error("v74 release manifest facts differ")
    readme = (stage / "README.md").read_text()
    for marker in (
        COORDINATE_MANIFEST_SHA256,
        COORDINATE_MANIFEST_TREE_SHA256,
        COORDINATE_PHYSICAL_TREE_SHA256,
        "Bichuten remains unchanged and unlocated",
        "No locality centroid, OSM point, Google content",
        "current_status_classification` remains",
    ):
        if marker not in readme:
            raise OpenSeedV74Error("v74 README lineage differs")


def _validate_definition(
    document: Mapping[str, Any],
    base: Mapping[str, Any],
    *,
    validation_wall_clock: datetime,
) -> str:
    if set(document) != set(base) or document.get("release_id") != RELEASE_ID:
        raise OpenSeedV74Error("v74 definition identity or schema differs")
    build = document.get("build")
    if not isinstance(build, dict) or set(build) != {"as_of", "recorded_at"}:
        raise OpenSeedV74Error("v74 definition build carrier differs")
    if build["as_of"] != AS_OF:
        raise OpenSeedV74Error("v74 as_of differs")
    recorded = v70.parse_utc(build["recorded_at"], label="v74 recorded_at")
    if validation_wall_clock.tzinfo is None or recorded > validation_wall_clock.astimezone(UTC):
        raise OpenSeedV74Error("v74 recorded_at is later than validation wall clock")
    for key in (
        "epoch_capture",
        "expected_epoch_result",
        "freshness_contract",
        "publication_contract_version",
        "schema_version",
        "scope",
    ):
        if document.get(key) != base.get(key):
            raise OpenSeedV74Error(f"v74 inherited definition field differs: {key}")
    return build["recorded_at"]


def _validate_publication_times(
    definition: Path,
    release: Path,
    *,
    recorded_at: str,
    require_live: bool,
) -> None:
    target = v70.parse_utc(recorded_at, label="v74 recorded_at")
    paths = (definition, release, *release.iterdir())
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV74Error(f"v74 staged inode post-dates recorded_at: {path.name}")
    if require_live:
        if datetime.now(UTC) < target:
            raise OpenSeedV74Error("v74 recorded_at is not live")
        for path in (definition, release):
            if path.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
                raise OpenSeedV74Error(f"v74 final root ctime predates recorded_at: {path.name}")


def validate_open_seed_v74(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
    require_live: bool = True,
) -> dict[str, Any]:
    if replay_count != 2:
        raise OpenSeedV74Error("v74 requires exactly two offline replays")
    wall = validation_wall_clock or datetime.now(UTC)
    guard = _guard_state()
    if guard["base_definition"] != (BASE_DEFINITION_BYTES, BASE_DEFINITION_SHA256):
        raise OpenSeedV74Error("accepted v73 definition pin differs")
    if guard["base_manifest"] != BASE_MANIFEST_SHA256 or guard["base_tree"] != BASE_TREE_SHA256:
        raise OpenSeedV74Error("accepted v73 release pin differs")
    base = json.loads(BASE_DEFINITION.read_text())
    definition_raw, definition = _read_json(definition_path, mode=0o444)
    recorded_at = _validate_definition(definition, base, validation_wall_clock=wall)
    selected, paths = selected_inputs(
        base, recorded_at=recorded_at, validation_wall_clock=wall
    )
    if definition.get("curated_inputs") != selected:
        raise OpenSeedV74Error("v74 selected input inventory differs")
    if release_path.is_symlink() or not release_path.is_dir():
        raise OpenSeedV74Error("v74 release must be an ordinary directory")
    if require_frozen and stat.S_IMODE(release_path.stat().st_mode) != 0o555:
        raise OpenSeedV74Error("v74 release root is not frozen")
    release_files = {path.name: path for path in release_path.iterdir()}
    if any(path.is_symlink() or not path.is_file() for path in release_files.values()):
        raise OpenSeedV74Error("v74 release contains a non-file")
    if require_frozen and any(
        stat.S_IMODE(path.stat().st_mode) != 0o444 for path in release_files.values()
    ):
        raise OpenSeedV74Error("v74 release file is not frozen")
    manifest_raw, manifest = _read_json(release_path / "manifest.json", mode=0o444)
    if _sha256(manifest_raw) != definition["expected_release"].get("manifest_sha256"):
        raise OpenSeedV74Error("v74 manifest hash differs")
    expected_release = {
        key: value
        for key, value in definition["expected_release"].items()
        if key != "manifest_sha256"
    }
    if {key: value for key, value in manifest.items() if key != "files"} != expected_release:
        raise OpenSeedV74Error("v74 expected release facts differ")
    if set(release_files) != set(manifest["files"]) | {"manifest.json"}:
        raise OpenSeedV74Error("v74 release file inventory differs")
    for filename, pin in manifest["files"].items():
        raw = (release_path / filename).read_bytes()
        if (len(raw), _sha256(raw)) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV74Error(f"v74 release pin differs: {filename}")
    _validate_publication_times(
        definition_path,
        release_path,
        recorded_at=recorded_at,
        require_live=require_live,
    )
    _validate_release_delta(release_path, recorded_at=recorded_at)
    summary = json.loads((release_path / "summary.json").read_text())
    if {key: summary[key] for key in definition["expected_summary"]} != definition[
        "expected_summary"
    ]:
        raise OpenSeedV74Error("v74 expected summary differs")

    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v74-replay-{replay + 1}-", dir="/private/tmp"
        ) as td:
            root = Path(td)
            connection = _build_database(
                base, paths, root / "atlas.sqlite", recorded_at=recorded_at
            )
            try:
                replay_release = root / "release"
                _write_release(connection, replay_release, recorded_at=recorded_at)
            finally:
                connection.close()
            _validate_release_delta(replay_release, recorded_at=recorded_at)
            if {path.name for path in replay_release.iterdir()} != set(release_files):
                raise OpenSeedV74Error("v74 replay file inventory differs")
            for filename, frozen in release_files.items():
                if (replay_release / filename).read_bytes() != frozen.read_bytes():
                    raise OpenSeedV74Error(f"v74 offline replay differs: {filename}")
    if _guard_state() != guard:
        raise OpenSeedV74Error("v74 validation mutated accepted inputs")
    return manifest


def _path_identity(path: Path, *, directory: bool) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    expected = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if not expected:
        raise OpenSeedV74Error(f"v74 stage type differs: {path}")
    return metadata.st_dev, metadata.st_ino


def _release_identities(root: Path) -> dict[str, tuple[int, int]]:
    return {
        path.name: _path_identity(path, directory=False) for path in root.iterdir()
    }


def _assert_release_identities(
    root: Path,
    root_identity: tuple[int, int],
    members: Mapping[str, tuple[int, int]],
) -> None:
    if _path_identity(root, directory=True) != root_identity:
        raise OpenSeedV74Error("v74 release stage root identity changed")
    actual = _release_identities(root)
    if actual != dict(members):
        raise OpenSeedV74Error("v74 release stage member identity changed")


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
        raise OpenSeedV74Error("refusing substituted v74 definition cleanup")
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
        raise OpenSeedV74Error("active v74 publication lock exists") from error
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
            if not stat.S_ISREG(current.st_mode) or (
                current.st_dev,
                current.st_ino,
            ) != identity:
                raise OpenSeedV74Error("refusing substituted v74 lock cleanup")
            PUBLICATION_LOCK.unlink()


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _require_absent(label: str) -> None:
    if DEFINITION.exists() or DEFINITION.is_symlink():
        raise OpenSeedV74Error(f"{label} v74 definition collision")
    if RELEASE.exists() or RELEASE.is_symlink():
        raise OpenSeedV74Error(f"{label} v74 release collision")


def _rollback_release(
    release_identity: tuple[int, int], release_stage: Path
) -> None:
    if _path_identity(RELEASE, directory=True) != release_identity:
        raise OpenSeedV74Error("refusing rollback of substituted v74 release")
    if release_stage.exists() or release_stage.is_symlink():
        raise OpenSeedV74Error("v74 release rollback stage is occupied")
    v69.promote_noreplace(RELEASE, release_stage)


def build_open_seed_v74(recorded_at: str | None = None) -> dict[str, Any]:
    """Build and atomically publish the strict v73 coordinate successor."""

    if (DEFINITION.exists() or DEFINITION.is_symlink()) and (
        RELEASE.exists() or RELEASE.is_symlink()
    ):
        manifest = validate_open_seed_v74()
        return {
            "definition": str(DEFINITION),
            "definition_sha256": v69.sha256(DEFINITION),
            "manifest_sha256": v69.sha256(RELEASE / "manifest.json"),
            "recorded_at": manifest["recorded_at"],
            "release": str(RELEASE),
            "release_tree_sha256": v69.tree_digest(RELEASE),
            "status": "existing-identical",
        }
    if DEFINITION.exists() or DEFINITION.is_symlink() or RELEASE.exists() or RELEASE.is_symlink():
        raise OpenSeedV74Error("partial v74 final-path collision")

    guard = _guard_state()
    if guard["base_definition"] != (BASE_DEFINITION_BYTES, BASE_DEFINITION_SHA256):
        raise OpenSeedV74Error("accepted v73 definition pin differs")
    if guard["base_manifest"] != BASE_MANIFEST_SHA256 or guard["base_tree"] != BASE_TREE_SHA256:
        raise OpenSeedV74Error("accepted v73 release pin differs")
    target = (
        v70.parse_utc(recorded_at, label="v74 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise OpenSeedV74Error("v74 recorded_at must be future before staging")
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
            with tempfile.TemporaryDirectory(prefix="open-seed-v74-db-", dir="/private/tmp") as td:
                connection = _build_database(
                    base, paths, Path(td) / "atlas.sqlite", recorded_at=recorded_at
                )
                try:
                    _write_release(
                        connection,
                        release_stage,
                        recorded_at=recorded_at,
                        precreated=True,
                        member_identities=release_members,
                    )
                    summary = summarize(connection, as_of=AS_OF, recorded_at=recorded_at)
                finally:
                    connection.close()
            _validate_release_delta(release_stage, recorded_at=recorded_at)
            manifest_raw = (release_stage / "manifest.json").read_bytes()
            manifest = json.loads(manifest_raw)
            expected_release = {key: value for key, value in manifest.items() if key != "files"}
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
                stream.write(_canonical_json(definition))
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
            if release_members != _release_identities(release_stage):
                raise OpenSeedV74Error("v74 release member identity capture differs")
            _validate_publication_times(
                definition_stage,
                release_stage,
                recorded_at=recorded_at,
                require_live=False,
            )
            _require_absent("pre-wait")
            definition_raw = definition_stage.read_bytes()
            release_tree = v69.tree_digest(release_stage)
            _wait_until(target)
            _require_absent("late")
            if _path_identity(definition_stage, directory=False) != definition_identity:
                raise OpenSeedV74Error("v74 definition stage identity changed")
            _assert_release_identities(release_stage, release_identity, release_members)
            if definition_stage.read_bytes() != definition_raw or v69.tree_digest(release_stage) != release_tree:
                raise OpenSeedV74Error("v74 private stage changed while waiting")
            _validate_publication_times(
                definition_stage,
                release_stage,
                recorded_at=recorded_at,
                require_live=False,
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
                    error.add_note(f"v74 release rollback failed: {rollback_error}")
                raise
            manifest = validate_open_seed_v74(DEFINITION, RELEASE)
        finally:
            if not published_release and release_stage.exists():
                if release_members:
                    _discard_release_stage(
                        release_stage, release_identity, release_members
                    )
                else:
                    if _path_identity(release_stage, directory=True) != release_identity:
                        raise OpenSeedV74Error(
                            "refusing substituted empty v74 release cleanup"
                        )
                    if any(release_stage.iterdir()):
                        raise OpenSeedV74Error(
                            "refusing untracked partial v74 release cleanup"
                        )
                    release_stage.rmdir()
            if not published_definition and definition_stage.exists():
                _discard_file_stage(definition_stage, definition_identity)
    if _guard_state() != guard:
        raise OpenSeedV74Error("v74 build mutated accepted inputs")
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
    print(json.dumps(build_open_seed_v74(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
