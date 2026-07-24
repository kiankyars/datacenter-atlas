"""Build open seed v72 as the conservative coordinate successor to v71."""

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
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v71.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v71"
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v72.json"
RELEASE_ID = "2026-07-21-open-seed-v72"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v72.lock"
AS_OF = "2026-07-21"

BASE_RECORDED_AT = "2026-07-21T10:17:38Z"
BASE_DEFINITION_BYTES = 86_839
BASE_DEFINITION_SHA256 = (
    "f5115fa57f32c8d9451609a662f6b524a15283b8e4fa1d9b65af59430d9e3b38"
)
BASE_MANIFEST_SHA256 = (
    "0f8acbce360f763707cb4c51276a0873ee60ec96d9258b1915fa8c76fcf9fa22"
)
BASE_TREE_SHA256 = "7636964f1d640268ed8627d5f18d800a43a35a4d7dbc1f62b8386e60bd1fa720"

COORDINATE_ARTIFACT = (
    ROOT / "source_artifacts/site-coordinate-assessment-2026-07-21-v4"
)
COORDINATE_RECORDED_AT = "2026-07-21T13:00:18Z"
COORDINATE_MANIFEST_SHA256 = (
    "8bcd9842af00890e4820e2b011a9fa799a1c4d5c98b0a77c4dc874c79b4c04b8"
)
COORDINATE_MANIFEST_TREE_SHA256 = (
    "df7d66252ac82c80679638c059b0d4edbd6bd86be788e9b997298945a1c13ccf"
)
COORDINATE_PHYSICAL_TREE_SHA256 = (
    "ee9da27dadb203dc44d4c4e23b2012c9849aa2f528d5753d4f5d466d15e9ccda"
)


@dataclass(frozen=True)
class CoordinateReplacementV4:
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
    CoordinateReplacementV4(
        predecessor_path=(
            "sources/curated-official-2026-07-19-nextdc-s4-sydney-"
            "1h26-early-works.json"
        ),
        predecessor_bytes=13_507,
        predecessor_sha256=(
            "4f465a73da77cc106c37aff41050079c1f07e78d25e3bdd92319b78a30418082"
        ),
        successor_path=(
            "source_artifacts/site-coordinate-assessment-2026-07-21-v4/"
            "normalized-successors/curated-official-2026-07-19-nextdc-s4-"
            "sydney-1h26-early-works-coordinate-v4.json"
        ),
        successor_bytes=19_467,
        successor_sha256=(
            "aca10cb2fccefb0cbfe6afff0fd0393ff75fe78ad2d7f26716d3720935541984"
        ),
        campus_key="curated:nextdc-s4-sydney",
        project_key="curated:nextdc-s4-sydney:early-works",
        changed_entities=("campus", "project"),
        added_evidence_key=(
            "nsw-planning-nextdc-s4-pda-coordinate-captured-2026-07-21"
        ),
    ),
    CoordinateReplacementV4(
        predecessor_path=(
            "sources/curated-official-2026-07-19-nextdc-sc2-sunshine-"
            "coast-1h26-fitout.json"
        ),
        predecessor_bytes=14_284,
        predecessor_sha256=(
            "768526b34023aac438eca3513898102b90d29f0107e52da16e6e16c6fe7e01c2"
        ),
        successor_path=(
            "source_artifacts/site-coordinate-assessment-2026-07-21-v4/"
            "normalized-successors/curated-official-2026-07-19-nextdc-sc2-"
            "sunshine-coast-1h26-fitout-coordinate-v4.json"
        ),
        successor_bytes=20_349,
        successor_sha256=(
            "c1fcf2d397f241ff98969d6ccc3d21712e01077f6be6bfbc95e266633fd981b8"
        ),
        campus_key="curated:nextdc-sc2-maroochydore",
        project_key=(
            "curated:nextdc-sc2-maroochydore:incremental-in-progress-fit-out"
        ),
        changed_entities=("project",),
        added_evidence_key=(
            "queensland-nextdc-sc2-lot-10-sp305311-centroid-captured-2026-07-21"
        ),
    ),
)

NEW_EVIDENCE_KEYS = frozenset(row.added_evidence_key for row in REPLACEMENTS)
NEW_SOURCE_FAMILIES = {
    "nsw_planning_major_projects",
    "queensland_government_development_and_cadastre",
}
COORDINATE_CONTRACT: dict[str, dict[str, Any]] = {
    "curated:nextdc-s4-sydney": {
        "latitude": -33.8278399,
        "longitude": 150.825,
        "geometry": {"type": "Point", "coordinates": [150.825, -33.8278399]},
        "source_family": "nsw_planning_major_projects",
    },
    "curated:nextdc-s4-sydney:early-works": {
        "latitude": -33.8278399,
        "longitude": 150.825,
        "geometry": {"type": "Point", "coordinates": [150.825, -33.8278399]},
        "source_family": "nsw_planning_major_projects",
    },
    "curated:nextdc-sc2-maroochydore:incremental-in-progress-fit-out": {
        "latitude": -26.6600114,
        "longitude": 153.0924068,
        "geometry": {
            "type": "Point",
            "coordinates": [153.0924068, -26.6600114],
        },
        "source_family": "queensland_government_development_and_cadastre",
    },
}

FRESHNESS_README = f"""
Open seed v72 is the exact accepted v71 successor with two curated inputs
replaced in place by the two official-coordinate successors accepted in
`source_artifacts/site-coordinate-assessment-2026-07-21-v4`. Input cardinality
remains 393. S4 gains a source-reported NSW Planning point on its campus and
project. SC2's explicitly parented incremental-fit-out project gains the
area-weighted centroid of exact Queensland Lot 10 SP305311; its source-local
campus snapshot remains unchanged because an already selected, later campus
snapshot supplies the existing approximate campus point.

The coordinate artifact manifest is `{COORDINATE_MANIFEST_SHA256}`, manifest
tree `{COORDINATE_MANIFEST_TREE_SHA256}`, and physical tree
`{COORDINATE_PHYSICAL_TREE_SHA256}`. Its 18 excluded project rows remain
review-only. No OSM candidate, failed-response URL, geocoder query seed,
midpoint, or unsupported LD14 report inference is integrated.

No identity, lifecycle, capacity, energy, consumption, ownership, operator,
tenant, workload, type, or current-status claim changes. Every lifecycle value
remains a dated last-observed fact; `current_status_classification` remains
`unknown` and `current_construction_claim` remains `false`.
""".strip()


class OpenSeedV72Error(RuntimeError):
    """Raised when a v72 lineage or publication condition fails closed."""


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
        raise OpenSeedV72Error(f"expected ordinary JSON file: {path}")
    if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
        raise OpenSeedV72Error(f"file mode differs: {path}")
    raw = path.read_bytes()
    document = json.loads(raw)
    expected = _canonical_source_json(document) if source_order else _canonical_json(document)
    if raw != expected:
        raise OpenSeedV72Error(f"JSON is not canonical: {path}")
    return raw, document


def _validate_coordinate_artifact() -> dict[str, Any]:
    artifact = COORDINATE_ARTIFACT
    if (
        artifact.is_symlink()
        or not artifact.is_dir()
        or stat.S_IMODE(artifact.stat().st_mode) != 0o555
        or v69.tree_digest(artifact) != COORDINATE_PHYSICAL_TREE_SHA256
    ):
        raise OpenSeedV72Error("coordinate v4 artifact is not exact and frozen")
    if any(
        path.is_symlink()
        or stat.S_IMODE(path.stat().st_mode) != (0o555 if path.is_dir() else 0o444)
        for path in artifact.rglob("*")
    ):
        raise OpenSeedV72Error("coordinate v4 artifact member mode differs")
    manifest_raw, manifest = _read_json(
        artifact / "manifest.json", mode=0o444, source_order=True
    )
    if (
        _sha256(manifest_raw) != COORDINATE_MANIFEST_SHA256
        or manifest.get("recorded_at") != COORDINATE_RECORDED_AT
        or manifest.get("integration") != "none"
        or manifest.get("tree_sha256") != COORDINATE_MANIFEST_TREE_SHA256
    ):
        raise OpenSeedV72Error("coordinate v4 manifest contract differs")
    listed = manifest.get("files")
    if not isinstance(listed, list):
        raise OpenSeedV72Error("coordinate v4 file inventory differs")
    actual = {
        path.relative_to(artifact).as_posix()
        for path in artifact.rglob("*")
        if path.is_file()
    }
    if actual != {row["path"] for row in listed} | {"manifest.json", "manifest.sha256"}:
        raise OpenSeedV72Error("coordinate v4 is not a closed file set")
    for row in listed:
        raw = (artifact / row["path"]).read_bytes()
        if (len(raw), _sha256(raw)) != (row["bytes"], row["sha256"]):
            raise OpenSeedV72Error(f"coordinate v4 file pin differs: {row['path']}")
    if _sha256(_canonical_source_json(listed)) != COORDINATE_MANIFEST_TREE_SHA256:
        raise OpenSeedV72Error("coordinate v4 manifest tree differs")
    if (artifact / "manifest.sha256").read_text() != (
        f"{COORDINATE_MANIFEST_SHA256}  manifest.json\n"
    ):
        raise OpenSeedV72Error("coordinate v4 sidecar differs")
    recorded = v70.parse_utc(COORDINATE_RECORDED_AT, label="coordinate recorded_at")
    if artifact.stat().st_ctime + 1e-6 < recorded.timestamp() or recorded > datetime.now(UTC):
        raise OpenSeedV72Error("coordinate v4 publication time differs")
    disposition = json.loads((artifact / "disposition.json").read_text())
    if (
        disposition.get("integration") != "none"
        or disposition.get("accepted_seed_definition") is not None
        or disposition.get("non_coordinate_claims_added") != []
        or disposition.get("review_only", {}).get("project_rows") != 18
        or len(disposition.get("accepted", {}).get("successors", {})) != 2
    ):
        raise OpenSeedV72Error("coordinate v4 disposition differs")
    return manifest


def _validate_successor(
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    replacement: CoordinateReplacementV4,
) -> None:
    if (
        predecessor.get("schema_version") != "1.0"
        or successor.get("schema_version") != "1.1"
        or set(predecessor) != set(successor)
    ):
        raise OpenSeedV72Error("coordinate v4 schema upgrade differs")
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
        raise OpenSeedV72Error("coordinate v4 evidence append differs")
    restored = copy.deepcopy(successor)
    restored["schema_version"] = "1.0"
    restored["evidence"] = copy.deepcopy(before_evidence)
    expected_keys = {
        "campus": replacement.campus_key,
        "project": replacement.project_key,
    }
    for entity_name, stable_key in expected_keys.items():
        before = predecessor[entity_name]
        after = successor[entity_name]
        if before.get("stable_key") != stable_key or after.get("stable_key") != stable_key:
            raise OpenSeedV72Error("coordinate v4 entity identity differs")
        changed = {
            key for key in set(before) | set(after) if before.get(key) != after.get(key)
        }
        if entity_name in replacement.changed_entities:
            if changed != {"coordinates", "geometry", "evidence_key", "method"}:
                raise OpenSeedV72Error("coordinate v4 non-coordinate delta detected")
            if before.get("coordinates") is not None or before.get("geometry") is not None:
                raise OpenSeedV72Error("coordinate v4 predecessor was already located")
            if after.get("method") != "authoritative_site_plan":
                raise OpenSeedV72Error("coordinate v4 method differs")
            for key in changed:
                restored[entity_name][key] = copy.deepcopy(before[key])
        elif changed:
            raise OpenSeedV72Error("coordinate v4 changed an excluded entity")
    if restored != predecessor:
        raise OpenSeedV72Error("coordinate v4 successor gained another claim")
    for section in ("lifecycle", "operating_models", "workloads", "capacities"):
        if successor[section] != predecessor[section] or any(
            row.get("evidence_key") == replacement.added_evidence_key
            for row in successor[section]
        ):
            raise OpenSeedV72Error(f"coordinate v4 changed {section}")


def _base_paths(base: Mapping[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for row in base["curated_inputs"]:
        path = ROOT / row["path"]
        if path.is_symlink() or not path.is_file() or v69.sha256(path) != row["sha256"]:
            raise OpenSeedV72Error(f"accepted v71 input pin differs: {row['path']}")
        paths.append(path)
    return paths


def selected_inputs(
    base: Mapping[str, Any],
    *,
    recorded_at: str,
    validation_wall_clock: datetime | None = None,
) -> tuple[list[dict[str, str]], list[Path]]:
    if base.get("release_id") != "2026-07-21-open-seed-v71":
        raise OpenSeedV72Error("v72 base must be exactly accepted v71")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 393:
        raise OpenSeedV72Error("accepted v71 curated inventory differs")
    _validate_coordinate_artifact()
    target = v70.parse_utc(recorded_at, label="v72 recorded_at")
    wall = validation_wall_clock or datetime.now(UTC)
    if wall.tzinfo is None or target > wall.astimezone(UTC):
        raise OpenSeedV72Error("v72 recorded_at is later than validation wall clock")

    by_predecessor = {row.predecessor_path: row for row in REPLACEMENTS}
    if len(by_predecessor) != 2:
        raise OpenSeedV72Error("v72 replacement inventory differs")
    selected: list[dict[str, str]] = []
    paths: list[Path] = []
    selected_documents: list[tuple[str, Mapping[str, Any]]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise OpenSeedV72Error("accepted v71 curated row differs")
        replacement = by_predecessor.get(row["path"])
        if replacement is None:
            path = ROOT / row["path"]
            if path.is_symlink() or not path.is_file() or v69.sha256(path) != row["sha256"]:
                raise OpenSeedV72Error(f"accepted v71 input drifted: {row['path']}")
            document = json.loads(path.read_text())
            output_row = dict(row)
        else:
            if row["sha256"] != replacement.predecessor_sha256:
                raise OpenSeedV72Error("v72 predecessor definition pin differs")
            predecessor_path = ROOT / replacement.predecessor_path
            predecessor_raw, predecessor = _read_json(
                predecessor_path, mode=0o644, source_order=True
            )
            if (len(predecessor_raw), _sha256(predecessor_raw)) != (
                replacement.predecessor_bytes,
                replacement.predecessor_sha256,
            ):
                raise OpenSeedV72Error("v72 predecessor byte pin differs")
            path = ROOT / replacement.successor_path
            successor_raw, document = _read_json(path, mode=0o444, source_order=True)
            if (len(successor_raw), _sha256(successor_raw)) != (
                replacement.successor_bytes,
                replacement.successor_sha256,
            ):
                raise OpenSeedV72Error("v72 successor byte pin differs")
            _validate_successor(predecessor, document, replacement)
            output_row = {
                "path": replacement.successor_path,
                "sha256": replacement.successor_sha256,
            }
            seen.add(replacement.predecessor_path)
        selected.append(output_row)
        paths.append(path)
        selected_documents.append((output_row["path"], document))

    if seen != set(by_predecessor) or len(selected) != 393:
        raise OpenSeedV72Error("v72 replacement selection is incomplete")
    selected_names = [row["path"] for row in selected]
    if len(set(selected_names)) != 393 or any(
        replacement.predecessor_path in selected_names for replacement in REPLACEMENTS
    ):
        raise OpenSeedV72Error("v72 selected inventory collides")
    for relative, document in selected_documents:
        for index, evidence in enumerate(document.get("evidence", [])):
            retrieved = v70.parse_utc(
                evidence.get("retrieved_at"),
                label=f"{relative} evidence[{index}].retrieved_at",
            )
            if retrieved > target or retrieved > wall.astimezone(UTC):
                raise OpenSeedV72Error("v72 selected evidence is future-dated")
    return selected, paths


def _guard_state() -> dict[str, Any]:
    _validate_coordinate_artifact()
    predecessors = {}
    for replacement in REPLACEMENTS:
        path = ROOT / replacement.predecessor_path
        predecessors[replacement.predecessor_path] = (
            path.stat().st_size,
            v69.sha256(path),
        )
    return {
        "base_definition": (BASE_DEFINITION.stat().st_size, v69.sha256(BASE_DEFINITION)),
        "base_manifest": v69.sha256(BASE_RELEASE / "manifest.json"),
        "base_tree": v69.tree_digest(BASE_RELEASE),
        "coordinate_manifest": v69.sha256(COORDINATE_ARTIFACT / "manifest.json"),
        "coordinate_tree": v69.tree_digest(COORDINATE_ARTIFACT),
        "predecessors": predecessors,
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
        raise OpenSeedV72Error(f"unsupported logical table: {table}")
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
        "entities": 810,
        "evidence": 636,
        "entity_snapshots": 830,
        "lifecycle_observations": 474,
        "capacity_estimates": 533,
        "operating_model_observations": 56,
        "workload_observations": 128,
    }
    actual = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in expected
    }
    if actual != expected:
        raise OpenSeedV72Error(f"v72 database counts differ: {actual}")
    with tempfile.TemporaryDirectory(prefix="open-seed-v72-base-", dir="/private/tmp") as td:
        prior = v69._populate_database(
            base, _base_paths(base), Path(td) / "v71.sqlite", recorded_at=recorded_at
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
                raise OpenSeedV72Error("v72 entity identities changed")
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
                or len(added) != 2
                or {row[3] for row in added} != NEW_SOURCE_FAMILIES
            ):
                raise OpenSeedV72Error("v72 evidence delta differs")
            for table in (
                "lifecycle_observations",
                "capacity_estimates",
                "operating_model_observations",
                "workload_observations",
            ):
                if _logical_rows(prior, table) != _logical_rows(connection, table):
                    raise OpenSeedV72Error(f"v72 changed logical {table}")
            before_snapshots = _snapshot_rows(prior)
            after_snapshots = _snapshot_rows(connection)
            if set(before_snapshots) != set(after_snapshots):
                raise OpenSeedV72Error("v72 snapshot identities changed")
            for stable_key in before_snapshots:
                if stable_key in COORDINATE_CONTRACT:
                    continue
                if before_snapshots[stable_key] != after_snapshots[stable_key]:
                    raise OpenSeedV72Error(
                        f"v72 changed a non-coordinate snapshot: {stable_key}"
                    )
            for stable_key, contract in COORDINATE_CONTRACT.items():
                rows = after_snapshots[stable_key]
                if len(rows) != 1:
                    raise OpenSeedV72Error(f"v72 coordinate snapshot count differs: {stable_key}")
                row = rows[0]
                if (
                    row[1] != contract["latitude"]
                    or row[2] != contract["longitude"]
                    or json.loads(row[3]) != contract["geometry"]
                    or row[5] != contract["source_family"]
                    or row[10] != "authoritative_site_plan"
                ):
                    raise OpenSeedV72Error(f"v72 coordinate snapshot differs: {stable_key}")
        finally:
            prior.close()
    new_evidence_ids = {
        row[0]
        for row in connection.execute(
            "SELECT id FROM evidence WHERE source_family IN (?, ?)",
            tuple(sorted(NEW_SOURCE_FAMILIES)),
        )
    }
    if len(new_evidence_ids) != 2:
        raise OpenSeedV72Error("v72 new evidence identity count differs")
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
            raise OpenSeedV72Error(f"coordinate evidence created {table}")


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
            raise OpenSeedV72Error("precreated v72 release stage must be empty")
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
    ):
        if (stage / filename).read_bytes() != (BASE_RELEASE / filename).read_bytes():
            raise OpenSeedV72Error(f"v72 changed invariant release file: {filename}")

    before_evidence = {
        row["evidence_id"]: row for row in _csv_rows(BASE_RELEASE / "evidence.csv")
    }
    after_evidence = {
        row["evidence_id"]: row for row in _csv_rows(stage / "evidence.csv")
    }
    if set(before_evidence) - set(after_evidence) or any(
        after_evidence[key] != row for key, row in before_evidence.items()
    ):
        raise OpenSeedV72Error("v72 changed prior public evidence")
    added = [row for key, row in after_evidence.items() if key not in before_evidence]
    if (
        len(added) != 2
        or {row["source_family"] for row in added} != NEW_SOURCE_FAMILIES
        or {row["kind"] for row in added} != {"government_record"}
    ):
        raise OpenSeedV72Error("v72 public evidence delta differs")

    before_entities = {
        row["stable_key"]: row for row in _csv_rows(BASE_RELEASE / "entities.csv")
    }
    after_entities = {
        row["stable_key"]: row for row in _csv_rows(stage / "entities.csv")
    }
    if set(before_entities) != set(after_entities) or len(after_entities) != 810:
        raise OpenSeedV72Error("v72 public entity inventory differs")
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
    for stable_key, before in before_entities.items():
        after = after_entities[stable_key]
        changed = {key for key in before if before[key] != after[key]}
        if stable_key not in COORDINATE_CONTRACT:
            if changed:
                raise OpenSeedV72Error(f"v72 changed public entity: {stable_key}")
            continue
        if not changed or not changed <= allowed:
            raise OpenSeedV72Error(f"v72 coordinate entity delta differs: {stable_key}")
        contract = COORDINATE_CONTRACT[stable_key]
        if (
            after["latitude"] != str(contract["latitude"])
            or after["longitude"] != str(contract["longitude"])
            or json.loads(after["geometry_json"]) != contract["geometry"]
            or after["status"] != before["status"]
            or after["capacity_estimates_json"] != before["capacity_estimates_json"]
            or after["workloads_json"] != before["workloads_json"]
        ):
            raise OpenSeedV72Error(f"v72 coordinate entity facts differ: {stable_key}")

    before_pipeline = {
        row["stable_key"]: row
        for row in _csv_rows(BASE_RELEASE / "construction_pipeline.csv")
    }
    after_pipeline = {
        row["stable_key"]: row for row in _csv_rows(stage / "construction_pipeline.csv")
    }
    if set(before_pipeline) != set(after_pipeline) or len(after_pipeline) != 416:
        raise OpenSeedV72Error("v72 pipeline inventory differs")
    changed_pipeline = set()
    for stable_key, before in before_pipeline.items():
        after = after_pipeline[stable_key]
        changed = {key for key in before if before[key] != after[key]}
        if not changed:
            continue
        changed_pipeline.add(stable_key)
        if stable_key not in COORDINATE_CONTRACT or not changed <= allowed:
            raise OpenSeedV72Error(f"v72 pipeline delta differs: {stable_key}")
    expected_projects = {row.project_key for row in REPLACEMENTS}
    if changed_pipeline != expected_projects:
        raise OpenSeedV72Error("v72 pipeline coordinate set differs")

    before_signals = {
        row["source_observation_evidence_id"]: row
        for row in _csv_rows(BASE_RELEASE / "construction_source_signals.csv")
    }
    after_signals = {
        row["source_observation_evidence_id"]: row
        for row in _csv_rows(stage / "construction_source_signals.csv")
    }
    if set(before_signals) != set(after_signals) or len(after_signals) != 318:
        raise OpenSeedV72Error("v72 construction-signal inventory differs")
    changed_signals = set()
    for key, before in before_signals.items():
        after = after_signals[key]
        changed = {field for field in before if before[field] != after[field]}
        if not changed:
            continue
        stable_key = after["representative_stable_key"]
        changed_signals.add(stable_key)
        if (
            stable_key not in expected_projects
            or changed != {"representative_latitude", "representative_longitude"}
        ):
            raise OpenSeedV72Error(f"v72 construction-signal delta differs: {stable_key}")
    expected_signal_projects = {
        "curated:nextdc-sc2-maroochydore:incremental-in-progress-fit-out"
    }
    if changed_signals != expected_signal_projects:
        raise OpenSeedV72Error("v72 construction-signal coordinate set differs")

    before_resolution = _csv_rows(BASE_RELEASE / "resolution_candidates.csv")
    after_resolution = _csv_rows(stage / "resolution_candidates.csv")
    before_counter = Counter(tuple(sorted(row.items())) for row in before_resolution)
    after_counter = Counter(tuple(sorted(row.items())) for row in after_resolution)
    added_resolution = list((after_counter - before_counter).elements())
    if before_counter - after_counter or len(added_resolution) != 1:
        raise OpenSeedV72Error("v72 resolution-candidate delta differs")
    added_resolution_row = dict(added_resolution[0])
    if (
        added_resolution_row.get("relationship_suggestion") != "nearby_only"
        or {
            added_resolution_row.get("left_name"),
            added_resolution_row.get("right_name"),
        }
        != {
            "NEXTDC S4 Sydney Data Center Campus",
            "Microsoft Kemps Creek Data Centre",
        }
        or added_resolution_row.get("distance_m") != "4244.216"
    ):
        raise OpenSeedV72Error("v72 added resolution candidate differs")
    before_resolution_json = json.loads(
        (BASE_RELEASE / "resolution_candidates.json").read_text()
    )
    after_resolution_json = json.loads(
        (stage / "resolution_candidates.json").read_text()
    )
    before_candidates = Counter(
        json.dumps(row, sort_keys=True, ensure_ascii=False)
        for row in before_resolution_json
    )
    after_candidates = Counter(
        json.dumps(row, sort_keys=True, ensure_ascii=False)
        for row in after_resolution_json
    )
    if before_candidates - after_candidates or sum(
        (after_candidates - before_candidates).values()
    ) != 1:
        raise OpenSeedV72Error("v72 resolution JSON candidate delta differs")

    atlas = json.loads((stage / "atlas.geojson").read_text())
    features = {row["properties"]["stable_key"]: row for row in atlas["features"]}
    if len(features) != 810 or set(features) != set(after_entities):
        raise OpenSeedV72Error("v72 atlas inventory differs")
    for stable_key, contract in COORDINATE_CONTRACT.items():
        feature = features[stable_key]
        if (
            feature["geometry"] != contract["geometry"]
            or feature["properties"]["latitude"] != contract["latitude"]
            or feature["properties"]["longitude"] != contract["longitude"]
        ):
            raise OpenSeedV72Error(f"v72 atlas coordinate differs: {stable_key}")

    summary = json.loads((stage / "summary.json").read_text())
    expected_summary = {
        "campuses_total": 427,
        "campuses_with_coordinates": 132,
        "capacity_estimates_current": 532,
        "construction_pipeline_records": 416,
        "construction_source_signals": 318,
        "entities_total": 810,
        "entities_with_coordinates": 192,
        "evidence_total": 636,
        "lifecycle_observations_current": 458,
        "projects_total": 383,
        "recorded_at": recorded_at,
    }
    if {key: summary.get(key) for key in expected_summary} != expected_summary:
        raise OpenSeedV72Error("v72 public summary differs")
    manifest = json.loads((stage / "manifest.json").read_text())
    if (
        manifest.get("entities") != 810
        or manifest.get("evidence_records") != 514
        or manifest.get("capacity_estimates") != 532
        or manifest.get("construction_pipeline_records") != 416
        or manifest.get("construction_source_signals") != 318
        or manifest.get("lifecycle_freshness_records") != 458
        or manifest.get("current_status_inferred") is not False
        or manifest.get("publication_contract_version") != 4
    ):
        raise OpenSeedV72Error("v72 release manifest facts differ")
    readme = (stage / "README.md").read_text()
    for marker in (
        COORDINATE_MANIFEST_SHA256,
        COORDINATE_PHYSICAL_TREE_SHA256,
        "18 excluded project rows remain",
        "No OSM candidate",
        "current_status_classification` remains",
    ):
        if marker not in readme:
            raise OpenSeedV72Error("v72 README lineage differs")


def _validate_definition(
    document: Mapping[str, Any],
    base: Mapping[str, Any],
    *,
    validation_wall_clock: datetime,
) -> str:
    if set(document) != set(base) or document.get("release_id") != RELEASE_ID:
        raise OpenSeedV72Error("v72 definition identity or schema differs")
    build = document.get("build")
    if not isinstance(build, dict) or set(build) != {"as_of", "recorded_at"}:
        raise OpenSeedV72Error("v72 definition build carrier differs")
    if build["as_of"] != AS_OF:
        raise OpenSeedV72Error("v72 as_of differs")
    recorded = v70.parse_utc(build["recorded_at"], label="v72 recorded_at")
    if validation_wall_clock.tzinfo is None or recorded > validation_wall_clock.astimezone(UTC):
        raise OpenSeedV72Error("v72 recorded_at is later than validation wall clock")
    for key in (
        "epoch_capture",
        "expected_epoch_result",
        "freshness_contract",
        "publication_contract_version",
        "schema_version",
        "scope",
    ):
        if document.get(key) != base.get(key):
            raise OpenSeedV72Error(f"v72 inherited definition field differs: {key}")
    return build["recorded_at"]


def _validate_publication_times(
    definition: Path,
    release: Path,
    *,
    recorded_at: str,
    require_live: bool,
) -> None:
    target = v70.parse_utc(recorded_at, label="v72 recorded_at")
    paths = (definition, release, *release.iterdir())
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV72Error(f"v72 staged inode post-dates recorded_at: {path.name}")
    if require_live:
        if datetime.now(UTC) < target:
            raise OpenSeedV72Error("v72 recorded_at is not live")
        for path in (definition, release):
            if path.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
                raise OpenSeedV72Error(f"v72 final root ctime predates recorded_at: {path.name}")


def validate_open_seed_v72(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
    require_live: bool = True,
) -> dict[str, Any]:
    if replay_count != 2:
        raise OpenSeedV72Error("v72 requires exactly two offline replays")
    wall = validation_wall_clock or datetime.now(UTC)
    guard = _guard_state()
    if guard["base_definition"] != (BASE_DEFINITION_BYTES, BASE_DEFINITION_SHA256):
        raise OpenSeedV72Error("accepted v71 definition pin differs")
    if guard["base_manifest"] != BASE_MANIFEST_SHA256 or guard["base_tree"] != BASE_TREE_SHA256:
        raise OpenSeedV72Error("accepted v71 release pin differs")
    base = json.loads(BASE_DEFINITION.read_text())
    definition_raw, definition = _read_json(definition_path, mode=0o444)
    recorded_at = _validate_definition(definition, base, validation_wall_clock=wall)
    selected, paths = selected_inputs(
        base, recorded_at=recorded_at, validation_wall_clock=wall
    )
    if definition.get("curated_inputs") != selected:
        raise OpenSeedV72Error("v72 selected input inventory differs")
    if release_path.is_symlink() or not release_path.is_dir():
        raise OpenSeedV72Error("v72 release must be an ordinary directory")
    if require_frozen and stat.S_IMODE(release_path.stat().st_mode) != 0o555:
        raise OpenSeedV72Error("v72 release root is not frozen")
    release_files = {path.name: path for path in release_path.iterdir()}
    if any(path.is_symlink() or not path.is_file() for path in release_files.values()):
        raise OpenSeedV72Error("v72 release contains a non-file")
    if require_frozen and any(
        stat.S_IMODE(path.stat().st_mode) != 0o444 for path in release_files.values()
    ):
        raise OpenSeedV72Error("v72 release file is not frozen")
    manifest_raw, manifest = _read_json(release_path / "manifest.json", mode=0o444)
    if _sha256(manifest_raw) != definition["expected_release"].get("manifest_sha256"):
        raise OpenSeedV72Error("v72 manifest hash differs")
    expected_release = {
        key: value
        for key, value in definition["expected_release"].items()
        if key != "manifest_sha256"
    }
    if {key: value for key, value in manifest.items() if key != "files"} != expected_release:
        raise OpenSeedV72Error("v72 expected release facts differ")
    if set(release_files) != set(manifest["files"]) | {"manifest.json"}:
        raise OpenSeedV72Error("v72 release file inventory differs")
    for filename, pin in manifest["files"].items():
        raw = (release_path / filename).read_bytes()
        if (len(raw), _sha256(raw)) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV72Error(f"v72 release pin differs: {filename}")
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
        raise OpenSeedV72Error("v72 expected summary differs")

    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v72-replay-{replay + 1}-", dir="/private/tmp"
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
                raise OpenSeedV72Error("v72 replay file inventory differs")
            for filename, frozen in release_files.items():
                if (replay_release / filename).read_bytes() != frozen.read_bytes():
                    raise OpenSeedV72Error(f"v72 offline replay differs: {filename}")
    if _guard_state() != guard:
        raise OpenSeedV72Error("v72 validation mutated accepted inputs")
    return manifest


def _path_identity(path: Path, *, directory: bool) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    expected = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if not expected:
        raise OpenSeedV72Error(f"v72 stage type differs: {path}")
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
        raise OpenSeedV72Error("v72 release stage root identity changed")
    actual = _release_identities(root)
    if actual != dict(members):
        raise OpenSeedV72Error("v72 release stage member identity changed")


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
        raise OpenSeedV72Error("refusing substituted v72 definition cleanup")
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
        raise OpenSeedV72Error("active v72 publication lock exists") from error
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
                raise OpenSeedV72Error("refusing substituted v72 lock cleanup")
            PUBLICATION_LOCK.unlink()


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _require_absent(label: str) -> None:
    if DEFINITION.exists() or DEFINITION.is_symlink():
        raise OpenSeedV72Error(f"{label} v72 definition collision")
    if RELEASE.exists() or RELEASE.is_symlink():
        raise OpenSeedV72Error(f"{label} v72 release collision")


def _rollback_release(
    release_identity: tuple[int, int], release_stage: Path
) -> None:
    if _path_identity(RELEASE, directory=True) != release_identity:
        raise OpenSeedV72Error("refusing rollback of substituted v72 release")
    if release_stage.exists() or release_stage.is_symlink():
        raise OpenSeedV72Error("v72 release rollback stage is occupied")
    v69.promote_noreplace(RELEASE, release_stage)


def build_open_seed_v72(recorded_at: str | None = None) -> dict[str, Any]:
    """Build and atomically publish the strict v71 coordinate successor."""

    if (DEFINITION.exists() or DEFINITION.is_symlink()) and (
        RELEASE.exists() or RELEASE.is_symlink()
    ):
        manifest = validate_open_seed_v72()
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
        raise OpenSeedV72Error("partial v72 final-path collision")

    guard = _guard_state()
    if guard["base_definition"] != (BASE_DEFINITION_BYTES, BASE_DEFINITION_SHA256):
        raise OpenSeedV72Error("accepted v71 definition pin differs")
    if guard["base_manifest"] != BASE_MANIFEST_SHA256 or guard["base_tree"] != BASE_TREE_SHA256:
        raise OpenSeedV72Error("accepted v71 release pin differs")
    target = (
        v70.parse_utc(recorded_at, label="v72 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=30)
    )
    if datetime.now(UTC) >= target:
        raise OpenSeedV72Error("v72 recorded_at must be future before staging")
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
            with tempfile.TemporaryDirectory(prefix="open-seed-v72-db-", dir="/private/tmp") as td:
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
                raise OpenSeedV72Error("v72 release member identity capture differs")
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
                raise OpenSeedV72Error("v72 definition stage identity changed")
            _assert_release_identities(release_stage, release_identity, release_members)
            if definition_stage.read_bytes() != definition_raw or v69.tree_digest(release_stage) != release_tree:
                raise OpenSeedV72Error("v72 private stage changed while waiting")
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
                    error.add_note(f"v72 release rollback failed: {rollback_error}")
                raise
            manifest = validate_open_seed_v72(DEFINITION, RELEASE)
        finally:
            if not published_release and release_stage.exists():
                if release_members:
                    _discard_release_stage(
                        release_stage, release_identity, release_members
                    )
                else:
                    if _path_identity(release_stage, directory=True) != release_identity:
                        raise OpenSeedV72Error(
                            "refusing substituted empty v72 release cleanup"
                        )
                    if any(release_stage.iterdir()):
                        raise OpenSeedV72Error(
                            "refusing untracked partial v72 release cleanup"
                        )
                    release_stage.rmdir()
            if not published_definition and definition_stage.exists():
                _discard_file_stage(definition_stage, definition_identity)
    if _guard_state() != guard:
        raise OpenSeedV72Error("v72 build mutated accepted inputs")
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
    print(json.dumps(build_open_seed_v72(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
