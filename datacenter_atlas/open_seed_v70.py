"""Build open seed v70 as the coordinate-only successor to accepted v69."""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import csv
from datetime import datetime, timedelta, timezone
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

from .coordinate_seed_replacement import (
    CoordinateReplacement,
    parse_utc,
    replace_curated_inputs,
)
from . import open_seed_v69 as v69
from .open_seed_v61 import FRESHNESS_FIELDS, FRESHNESS_FILENAME, build_freshness_csv
from .publication_release import build_release_documents
from .service import summarize


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v69.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v69"
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v70.json"
RELEASE_ID = "2026-07-21-open-seed-v70"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v70.lock"

AS_OF = "2026-07-21"
BASE_RECORDED_AT = "2026-07-21T09:31:27Z"
BASE_DEFINITION_SHA256 = (
    "d72275d4d0c37f90bffa694ae15f2b58fc1c03d70f69501e2c16abde425748ff"
)
BASE_MANIFEST_SHA256 = (
    "1708696cb999baa00fba2f97b05277bb0156e6eebf878bd16cc8ad6cfe6153f0"
)
BASE_TREE_SHA256 = "765488c1c69b11bb5d38c5d5387aca2afa45e21e6c2ab995c1d92e8cecd56881"

COORDINATE_ARTIFACT = (
    ROOT / "source_artifacts/site-coordinate-assessment-2026-07-21-v3"
)
COORDINATE_MANIFEST_SHA256 = (
    "acb675580c993e3af150f8a3e25f53a8d66a6d7b595b644088a84f1294acd43d"
)
COORDINATE_MANIFEST_TREE_SHA256 = (
    "aeaebd102f00c4e6b25ff4b86e15d2c88ad3b1fbe8d23cc216c4f0c57995a6b2"
)
COORDINATE_PHYSICAL_TREE_SHA256 = (
    "0d9c582c2e0bcea2124458c0d387a0fe9117c7477b1b5ba1709f87adb8aa657b"
)
COORDINATE_RECORDED_AT = "2026-07-21T09:55:47.489508Z"

TEMPORAL_INCIDENT = (
    ROOT
    / "source_artifacts/site-coordinate-assessment-temporal-incident-2026-07-21-v1"
)
TEMPORAL_INCIDENT_MANIFEST_SHA256 = (
    "2812b326ca373c74d83d28278ea52780fd68da47ecb275b9027c6d91380ef930"
)
TEMPORAL_INCIDENT_MANIFEST_TREE_SHA256 = (
    "6525e60fc718471e1550562e493ecded668dfe115c982ed37e53bdb1fad9c260"
)
TEMPORAL_INCIDENT_PHYSICAL_TREE_SHA256 = (
    "92fa578ddeb341e6397d535b2625001715450e175d210c01d45835cbb2647efb"
)

PUBLICATION_INCIDENT = (
    ROOT
    / "source_artifacts/site-coordinate-assessment-publication-incident-2026-07-21-v1"
)
PUBLICATION_INCIDENT_MANIFEST_SHA256 = (
    "8128a6be3fb6fbe7d9d576e8445524590ff53542530fc499c5d40588cd0bed1d"
)
PUBLICATION_INCIDENT_MANIFEST_TREE_SHA256 = (
    "dc80687ee6ec61cbc71fb31169ed568ab23ab6140de7d86688079861ca1835b8"
)
PUBLICATION_INCIDENT_PHYSICAL_TREE_SHA256 = (
    "c8fe9f2266ccf67f1ead2ae5fa5f47b3a783a7da9d2bddc9a594d3f003db4c5c"
)

PREDECESSOR_PINS = {
    "sources/curated-official-2026-07-21-scala-sforpf01-fortaleza-current-build.json": (
        6_032,
        "aaf91ac612720e5aaaf66fcc13a5061701b4f95ee5cd4499485b347f9a3d314c",
    ),
    "sources/curated-official-2026-07-21-scala-ssclhb01-huechuraba-current-build.json": (
        5_666,
        "1894b5625adfa95f03a4a3ba981fa0a5e28010ef1cfa0fe1e7ba858e9a877699",
    ),
    "sources/curated-official-2026-07-21-scala-sscllp01-lampa-current-build.json": (
        5_948,
        "04c1747343928095b9c2901c6ed95717766e8c6abce3e480d1157959791ab8c1",
    ),
}

REPLACEMENTS = (
    CoordinateReplacement(
        predecessor_path=(
            "sources/curated-official-2026-07-21-scala-sforpf01-fortaleza-"
            "current-build.json"
        ),
        predecessor_sha256=PREDECESSOR_PINS[
            "sources/curated-official-2026-07-21-scala-sforpf01-fortaleza-current-build.json"
        ][1],
        successor_path=(
            "source_artifacts/site-coordinate-assessment-2026-07-21-v3/"
            "normalized-successors/curated-official-2026-07-21-scala-sforpf01-"
            "fortaleza-current-build-coordinate-v3.json"
        ),
        successor_bytes=13_434,
        successor_sha256=(
            "c685989acf5fb9d405c6803f79457de930fb90e6b57a5780cbf903a876a12e6f"
        ),
        campus_key="curated:scala-praia-do-futuro-campus",
        project_key="curated:scala-praia-do-futuro-campus:sforpf01",
        added_evidence_key="fortaleza-seuma-sforpf01-survey-plan-captured-2026-07-21",
    ),
    CoordinateReplacement(
        predecessor_path=(
            "sources/curated-official-2026-07-21-scala-ssclhb01-huechuraba-"
            "current-build.json"
        ),
        predecessor_sha256=PREDECESSOR_PINS[
            "sources/curated-official-2026-07-21-scala-ssclhb01-huechuraba-current-build.json"
        ][1],
        successor_path=(
            "source_artifacts/site-coordinate-assessment-2026-07-21-v3/"
            "normalized-successors/curated-official-2026-07-21-scala-ssclhb01-"
            "huechuraba-current-build-coordinate-v3.json"
        ),
        successor_bytes=13_559,
        successor_sha256=(
            "1bcb03a404f927e628cd1e99dab6a3505bea18312b694143911002da4970487f"
        ),
        campus_key="curated:scala-huechuraba-campus",
        project_key="curated:scala-huechuraba-campus:ssclhb01",
        added_evidence_key=(
            "chile-mma-simbio-scala-huechuraba-point-2162968448-captured-"
            "2026-07-21"
        ),
    ),
    CoordinateReplacement(
        predecessor_path=(
            "sources/curated-official-2026-07-21-scala-sscllp01-lampa-"
            "current-build.json"
        ),
        predecessor_sha256=PREDECESSOR_PINS[
            "sources/curated-official-2026-07-21-scala-sscllp01-lampa-current-build.json"
        ][1],
        successor_path=(
            "source_artifacts/site-coordinate-assessment-2026-07-21-v3/"
            "normalized-successors/curated-official-2026-07-21-scala-sscllp01-"
            "lampa-current-build-coordinate-v3.json"
        ),
        successor_bytes=13_780,
        successor_sha256=(
            "970e17532a3210b72e7c5cae376302feeefbfe13b9ae059b934b693f4a7a8391"
        ),
        campus_key="curated:scala-lampa-campus",
        project_key="curated:scala-lampa-campus:sscllp01",
        added_evidence_key=(
            "chile-mma-simbio-scala-lampa-point-2152920300-captured-2026-07-21"
        ),
    ),
)

COORDINATE_CONTRACT: dict[str, dict[str, Any]] = {
    "curated:scala-huechuraba-campus": {
        "latitude": -33.36636,
        "longitude": -70.67394,
        "geometry": {"coordinates": [-70.67394, -33.36636], "type": "Point"},
        "evidence_key": REPLACEMENTS[1].added_evidence_key,
    },
    "curated:scala-huechuraba-campus:ssclhb01": {
        "latitude": -33.36636,
        "longitude": -70.67394,
        "geometry": {"coordinates": [-70.67394, -33.36636], "type": "Point"},
        "evidence_key": REPLACEMENTS[1].added_evidence_key,
    },
    "curated:scala-lampa-campus": {
        "latitude": -33.29298,
        "longitude": -70.73915,
        "geometry": {"coordinates": [-70.73915, -33.29298], "type": "Point"},
        "evidence_key": REPLACEMENTS[2].added_evidence_key,
    },
    "curated:scala-lampa-campus:sscllp01": {
        "latitude": -33.29298,
        "longitude": -70.73915,
        "geometry": {"coordinates": [-70.73915, -33.29298], "type": "Point"},
        "evidence_key": REPLACEMENTS[2].added_evidence_key,
    },
    "curated:scala-praia-do-futuro-campus": {
        "latitude": -3.751509,
        "longitude": -38.458001,
        "geometry": {"coordinates": [-38.458001, -3.751509], "type": "Point"},
        "evidence_key": REPLACEMENTS[0].added_evidence_key,
    },
    "curated:scala-praia-do-futuro-campus:sforpf01": {
        "latitude": -3.751509,
        "longitude": -38.458001,
        "geometry": {
            "coordinates": [[
                [-38.458162, -3.753499],
                [-38.45902, -3.753223],
                [-38.45784, -3.749518],
                [-38.456983, -3.749794],
                [-38.458162, -3.753499],
            ]],
            "type": "Polygon",
        },
        "evidence_key": REPLACEMENTS[0].added_evidence_key,
    },
}

NEW_EVIDENCE_KEYS = frozenset(row.added_evidence_key for row in REPLACEMENTS)
NEW_SOURCE_FAMILIES = {
    "chile_mma_simbio_seia_project_points",
    "fortaleza_cppd_project_plans",
}
UNCHANGED_RELEASE_CSVS = (
    "capacity_estimates.csv",
    "resolution_candidates.csv",
    "lifecycle_freshness.csv",
)
COORDINATE_PROJECT_KEYS = frozenset(
    replacement.project_key for replacement in REPLACEMENTS
)
PUBLIC_COORDINATES = {
    stable_key: (contract["latitude"], contract["longitude"])
    for stable_key, contract in COORDINATE_CONTRACT.items()
}
# Public projection derives representative coordinates from project geometry.
# The surveyed Fortaleza polygon centroid is distinct from the stored campus point.
PUBLIC_COORDINATES[
    "curated:scala-praia-do-futuro-campus:sforpf01"
] = (-3.7515085, -38.4580015)

FRESHNESS_README = f"""
Open seed v70 is the exact accepted v69 successor with three curated inputs
replaced in place by their coordinate-only successors. Input cardinality remains
391. The replacement adds exactly three government-record evidence rows and six
located entity snapshots: the explicitly parented campus and project records for
Scala Lampa, Huechuraba, and Praia do Futuro. It changes no identity, lifecycle,
capacity, workload, operating-model, role, energy, type, or current-status claim.
The Chile points are publisher-declared representative environmental-review
points, not footprints or centroids. The Fortaleza campus point is derived from
the official surveyed project boundary; only the explicitly parented SFORPF01
project carries that boundary polygon.

Every lifecycle value remains a dated, last-observed historical fact.
`current_status_classification` remains `unknown` and
`current_construction_claim` remains `false` for every freshness row. No
satellite, aerial, computer-vision, inferred-site, capacity-arithmetic, or
commercial-census claim is added.

The selected coordinate artifact is
`source_artifacts/site-coordinate-assessment-2026-07-21-v3`, manifest
`{COORDINATE_MANIFEST_SHA256}`, manifest tree
`{COORDINATE_MANIFEST_TREE_SHA256}`, and physical tree
`{COORDINATE_PHYSICAL_TREE_SHA256}`. Rejected coordinate v1 and v2 are not
lineage. Their publication and temporal incidents remain preserved at manifest
`{PUBLICATION_INCIDENT_MANIFEST_SHA256}` and
`{TEMPORAL_INCIDENT_MANIFEST_SHA256}` respectively; passage of wall-clock time
does not retroactively validate either rejected artifact.
""".strip()


@contextmanager
def publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise SystemExit(f"active publication lock exists: {PUBLICATION_LOCK}") from error
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            PUBLICATION_LOCK.unlink()
        except FileNotFoundError:
            pass


def _canonical_json_document(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
    document = json.loads(raw)
    expected = (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode()
    if raw != expected:
        raise ValueError(f"noncanonical artifact JSON: {path}")
    return raw, document


def _validate_closed_artifact(
    artifact: Path,
    *,
    manifest_sha256: str,
    manifest_tree_sha256: str,
    physical_tree_sha256: str,
    expected_recorded_at: str | None,
) -> dict[str, Any]:
    if (
        not artifact.is_dir()
        or artifact.is_symlink()
        or stat.S_IMODE(artifact.stat().st_mode) != 0o555
        or v69.tree_digest(artifact) != physical_tree_sha256
    ):
        raise ValueError(f"source artifact is not exact and frozen: {artifact}")
    for path in artifact.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"source artifact contains a symlink: {artifact}")
        expected_mode = 0o555 if path.is_dir() else 0o444
        if stat.S_IMODE(path.stat().st_mode) != expected_mode:
            raise ValueError(f"source artifact mode differs: {path}")
    manifest_raw, manifest = _canonical_json_document(artifact / "manifest.json")
    if hashlib.sha256(manifest_raw).hexdigest() != manifest_sha256:
        raise ValueError(f"source artifact manifest pin differs: {artifact}")
    listed = manifest.get("files")
    if not isinstance(listed, list):
        raise ValueError(f"source artifact file inventory differs: {artifact}")
    expected_files = {row.get("path") for row in listed} | {
        "manifest.json",
        "manifest.sha256",
    }
    actual_files = {
        path.relative_to(artifact).as_posix()
        for path in artifact.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files or len(expected_files) != len(listed) + 2:
        raise ValueError(f"source artifact is not a closed file set: {artifact}")
    for row in listed:
        path = artifact / row["path"]
        payload = path.read_bytes()
        if (len(payload), hashlib.sha256(payload).hexdigest()) != (
            row.get("bytes"),
            row.get("sha256"),
        ):
            raise ValueError(f"source artifact file pin differs: {path}")
    tree_payload = (json.dumps(listed, indent=2, ensure_ascii=False) + "\n").encode()
    if (
        manifest.get("tree_sha256") != manifest_tree_sha256
        or hashlib.sha256(tree_payload).hexdigest() != manifest_tree_sha256
    ):
        raise ValueError(f"source artifact manifest tree differs: {artifact}")
    if (artifact / "manifest.sha256").read_text(encoding="utf-8") != (
        f"{manifest_sha256}  manifest.json\n"
    ):
        raise ValueError(f"source artifact checksum carrier differs: {artifact}")
    if expected_recorded_at is not None:
        if manifest.get("recorded_at") != expected_recorded_at:
            raise ValueError(f"source artifact recorded_at differs: {artifact}")
        recorded = datetime.fromisoformat(
            expected_recorded_at.replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        birth = datetime.fromtimestamp(artifact.stat().st_birthtime, timezone.utc)
        if birth > recorded or recorded > datetime.now(timezone.utc):
            raise ValueError(f"source artifact temporal gate differs: {artifact}")
    return manifest


def _validate_source_lineage() -> dict[str, Any]:
    coordinate = _validate_closed_artifact(
        COORDINATE_ARTIFACT,
        manifest_sha256=COORDINATE_MANIFEST_SHA256,
        manifest_tree_sha256=COORDINATE_MANIFEST_TREE_SHA256,
        physical_tree_sha256=COORDINATE_PHYSICAL_TREE_SHA256,
        expected_recorded_at=COORDINATE_RECORDED_AT,
    )
    temporal = _validate_closed_artifact(
        TEMPORAL_INCIDENT,
        manifest_sha256=TEMPORAL_INCIDENT_MANIFEST_SHA256,
        manifest_tree_sha256=TEMPORAL_INCIDENT_MANIFEST_TREE_SHA256,
        physical_tree_sha256=TEMPORAL_INCIDENT_PHYSICAL_TREE_SHA256,
        expected_recorded_at="2026-07-21T09:55:47.487842Z",
    )
    publication = _validate_closed_artifact(
        PUBLICATION_INCIDENT,
        manifest_sha256=PUBLICATION_INCIDENT_MANIFEST_SHA256,
        manifest_tree_sha256=PUBLICATION_INCIDENT_MANIFEST_TREE_SHA256,
        physical_tree_sha256=PUBLICATION_INCIDENT_PHYSICAL_TREE_SHA256,
        expected_recorded_at=None,
    )
    disposition = json.loads((COORDINATE_ARTIFACT / "disposition.json").read_text())
    if (
        coordinate.get("integration") != "none"
        or disposition.get("integration") != "none"
        or disposition.get("accepted_seed_definition") is not None
        or disposition.get("non_coordinate_claims_added") != []
    ):
        raise ValueError("coordinate v3 artifact-only boundary differs")
    accepted = disposition.get("accepted", {}).get("successors", {})
    if not isinstance(accepted, dict) or len(accepted) != 3:
        raise ValueError("coordinate v3 successor inventory differs")
    expected = {
        replacement.predecessor_path: replacement for replacement in REPLACEMENTS
    }
    for row in accepted.values():
        replacement = expected.get(row.get("predecessor"))
        if replacement is None:
            raise ValueError("coordinate v3 predecessor inventory differs")
        successor = COORDINATE_ARTIFACT / row["path"]
        if (
            successor.relative_to(ROOT).as_posix() != replacement.successor_path
            or (row.get("bytes"), row.get("sha256"))
            != (replacement.successor_bytes, replacement.successor_sha256)
            or row.get("campus_key") != replacement.campus_key
            or row.get("project_key") != replacement.project_key
        ):
            raise ValueError("coordinate v3 successor contract differs")
    rejected = {
        row.get("path"): row.get("reason")
        for row in disposition.get("lineage", {}).get("rejected_as_lineage", [])
    }
    if rejected.get(
        "source_artifacts/site-coordinate-assessment-2026-07-21-v2"
    ) != "rejected_future_retrieved_at_metadata_at_publication":
        raise ValueError("coordinate v2 rejection boundary differs")
    integrity = disposition.get("publication_integrity", {})
    if (
        integrity.get("v1_incident_manifest_sha256")
        != PUBLICATION_INCIDENT_MANIFEST_SHA256
        or integrity.get("temporal_incident_manifest_sha256")
        != TEMPORAL_INCIDENT_MANIFEST_SHA256
        or integrity.get("v2_accepted") is not False
    ):
        raise ValueError("coordinate incident lineage differs")
    if temporal.get("integration") != "none" or publication.get("integration") != "none":
        raise ValueError("coordinate incident integration boundary differs")
    return {
        "coordinate_manifest_sha256": COORDINATE_MANIFEST_SHA256,
        "coordinate_tree_sha256": COORDINATE_PHYSICAL_TREE_SHA256,
        "publication_incident_manifest_sha256": (
            PUBLICATION_INCIDENT_MANIFEST_SHA256
        ),
        "temporal_incident_manifest_sha256": TEMPORAL_INCIDENT_MANIFEST_SHA256,
    }


def _guard_state() -> dict[str, Any]:
    lineage = _validate_source_lineage()
    predecessors = {}
    for relative, expected in PREDECESSOR_PINS.items():
        path = ROOT / relative
        actual = (path.stat().st_size, v69.sha256(path))
        if actual != expected:
            raise ValueError(f"coordinate predecessor pin differs: {relative}")
        predecessors[relative] = actual
    return {
        "base_definition": v69.sha256(BASE_DEFINITION),
        "base_manifest": v69.sha256(BASE_RELEASE / "manifest.json"),
        "base_tree": v69.tree_digest(BASE_RELEASE),
        "lineage": lineage,
        "predecessors": predecessors,
    }


def selected_inputs(
    base: Mapping[str, Any],
    *,
    recorded_at: str,
    validation_wall_clock: datetime | None = None,
) -> tuple[list[dict[str, str]], list[Path]]:
    if base.get("release_id") != "2026-07-21-open-seed-v69":
        raise ValueError("v70 base must be exactly accepted v69")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 391:
        raise ValueError("accepted v69 curated inventory differs")
    _validate_source_lineage()
    selected, paths = replace_curated_inputs(
        ROOT,
        rows,
        REPLACEMENTS,
        recorded_at=recorded_at,
        validation_wall_clock=validation_wall_clock,
    )
    if len(selected) != 391:
        raise ValueError("v70 curated input cardinality differs")
    base_paths = [row["path"] for row in rows]
    selected_paths = [row["path"] for row in selected]
    for replacement in REPLACEMENTS:
        if selected_paths.index(replacement.successor_path) != base_paths.index(
            replacement.predecessor_path
        ):
            raise ValueError("v70 coordinate replacement moved its input position")
    return selected, paths


def _base_paths(base: Mapping[str, Any]) -> list[Path]:
    paths = []
    for row in base["curated_inputs"]:
        path = ROOT / row["path"]
        if v69.sha256(path) != row["sha256"]:
            raise ValueError(f"accepted v69 source hash differs: {row['path']}")
        paths.append(path)
    return paths


def _table_state(connection: sqlite3.Connection, table: str) -> tuple[tuple[Any, ...], ...]:
    return tuple(sorted((tuple(row) for row in connection.execute(f"SELECT * FROM {table}")), key=repr))


def _evidence_by_key(connection: sqlite3.Connection) -> dict[str, tuple[Any, ...]]:
    rows = {}
    for row in connection.execute("SELECT * FROM evidence"):
        packed = tuple(row)
        metadata = json.loads(row[12])
        key = metadata.get("curated_record_key")
        if key is not None:
            rows[key] = packed
    return rows


def _validate_database_contract(
    connection: sqlite3.Connection,
    base: Mapping[str, Any],
    *,
    recorded_at: str,
) -> None:
    expected_counts = {
        "entities": 806,
        "evidence": 631,
        "entity_snapshots": 826,
        "lifecycle_observations": 472,
        "capacity_estimates": 531,
        "operating_model_observations": 56,
        "workload_observations": 128,
    }
    actual_counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in expected_counts
    }
    if actual_counts != expected_counts:
        raise ValueError(f"v70 database counts differ: {actual_counts}")
    with tempfile.TemporaryDirectory(prefix="open-seed-v70-base-", dir="/private/tmp") as temporary:
        prior = v69._populate_database(
            base,
            _base_paths(base),
            Path(temporary) / "v69.sqlite",
            recorded_at=recorded_at,
        )
        try:
            for table in (
                "campuses",
                "facilities",
                "buildings",
                "projects",
                "administrative_assignments",
                "lifecycle_observations",
                "operating_model_observations",
                "workload_observations",
                "capacity_estimates",
            ):
                if _table_state(connection, table) != _table_state(prior, table):
                    raise ValueError(f"v70 changed non-coordinate table: {table}")

            before_evidence = _evidence_by_key(prior)
            after_evidence = _evidence_by_key(connection)
            if set(after_evidence) - set(before_evidence) != NEW_EVIDENCE_KEYS:
                raise ValueError("v70 evidence delta differs")
            if set(before_evidence) - set(after_evidence) or any(
                after_evidence[key] != row for key, row in before_evidence.items()
            ):
                raise ValueError("v70 changed prior evidence")

            coordinate_keys = tuple(sorted(COORDINATE_CONTRACT))
            placeholders = ",".join("?" for _ in coordinate_keys)
            before_entities = {
                row[2]: tuple(row)
                for row in prior.execute("SELECT * FROM entities")
            }
            after_entities = {
                row[2]: tuple(row)
                for row in connection.execute("SELECT * FROM entities")
            }
            if set(before_entities) != set(after_entities):
                raise ValueError("v70 entity identity inventory differs")
            if any(
                before_entities[key] != after_entities[key]
                for key in before_entities
                if key not in COORDINATE_CONTRACT
            ):
                raise ValueError("v70 changed a non-coordinate entity")
            new_evidence = _evidence_by_key(connection)
            for stable_key, contract in COORDINATE_CONTRACT.items():
                before = before_entities[stable_key]
                after = after_entities[stable_key]
                expected_evidence_id = new_evidence[contract["evidence_key"]][0]
                if (
                    before[:3] != after[:3]
                    or before[4] != after[4]
                    or after[3] != expected_evidence_id
                ):
                    raise ValueError(f"v70 entity provenance delta differs: {stable_key}")

            before_snapshots = {
                row[0]: tuple(row)
                for row in prior.execute("SELECT * FROM entity_snapshots")
            }
            after_snapshots = {
                row[0]: tuple(row)
                for row in connection.execute("SELECT * FROM entity_snapshots")
            }
            entity_ids = {
                row[2]: row[0]
                for row in connection.execute(
                    f"SELECT id, kind, stable_key FROM entities WHERE stable_key IN ({placeholders})",
                    coordinate_keys,
                )
            }
            changed_before_ids = {
                row[0]
                for row in prior.execute(
                    f"SELECT entity_snapshots.id FROM entity_snapshots JOIN entities "
                    f"ON entities.id = entity_snapshots.entity_id WHERE entities.stable_key IN ({placeholders})",
                    coordinate_keys,
                )
            }
            changed_after_ids = {
                row[0]
                for row in connection.execute(
                    f"SELECT entity_snapshots.id FROM entity_snapshots JOIN entities "
                    f"ON entities.id = entity_snapshots.entity_id WHERE entities.stable_key IN ({placeholders})",
                    coordinate_keys,
                )
            }
            if any(
                row != after_snapshots[snapshot_id]
                for snapshot_id, row in before_snapshots.items()
                if snapshot_id not in changed_before_ids
            ) or any(
                snapshot_id not in before_snapshots
                for snapshot_id in after_snapshots
                if snapshot_id not in changed_after_ids
            ):
                raise ValueError("v70 changed a non-coordinate snapshot")
            if len(changed_before_ids) != 6 or len(changed_after_ids) != 6:
                raise ValueError("v70 located snapshot cardinality differs")
            for stable_key, contract in COORDINATE_CONTRACT.items():
                rows = connection.execute(
                    """
                    SELECT latitude, longitude, geometry_json, evidence_id, method
                    FROM entity_snapshots WHERE entity_id = ?
                    """,
                    (entity_ids[stable_key],),
                ).fetchall()
                expected_evidence_id = new_evidence[contract["evidence_key"]][0]
                expected = (
                    contract["latitude"],
                    contract["longitude"],
                    json.dumps(contract["geometry"], sort_keys=True, separators=(",", ":")),
                    expected_evidence_id,
                    "authoritative_site_plan",
                )
                if len(rows) != 1 or tuple(rows[0]) != expected:
                    raise ValueError(f"v70 coordinate snapshot differs: {stable_key}")
        finally:
            prior.close()


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


def augment_release_documents(
    documents: Mapping[str, str], *, as_of: str
) -> dict[str, str]:
    output = dict(documents)
    if FRESHNESS_FILENAME in output:
        raise RuntimeError("freshness filename already exists")
    freshness = build_freshness_csv(output["entities.csv"], as_of=as_of)
    output[FRESHNESS_FILENAME] = freshness
    readme = output["README.md"].rstrip() + "\n\n" + FRESHNESS_README + "\n"
    output["README.md"] = readme
    manifest = json.loads(output["manifest.json"])
    manifest["files"]["README.md"] = {
        "bytes": len(readme.encode()),
        "sha256": hashlib.sha256(readme.encode()).hexdigest(),
    }
    manifest["files"][FRESHNESS_FILENAME] = {
        "bytes": len(freshness.encode()),
        "sha256": hashlib.sha256(freshness.encode()).hexdigest(),
    }
    manifest["current_status_inferred"] = False
    manifest["lifecycle_freshness_records"] = len(
        list(csv.DictReader(io.StringIO(freshness)))
    )
    manifest["lifecycle_status_semantics"] = "last_observed"
    output["manifest.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    return output


def _write_release(
    connection: sqlite3.Connection,
    output: Path,
    *,
    recorded_at: str,
    precreated: bool = False,
) -> None:
    if precreated:
        if not output.is_dir() or output.is_symlink() or any(output.iterdir()):
            raise ValueError("precreated v70 release stage must be empty")
    else:
        output.mkdir(parents=True, exist_ok=False)
    documents = build_release_documents(
        connection,
        as_of=AS_OF,
        recorded_at=recorded_at,
        publication_contract_version=4,
    )
    for filename, text in augment_release_documents(documents, as_of=AS_OF).items():
        (output / filename).write_text(text, encoding="utf-8")


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _normalized_csv_counter(path: Path, *, recorded_at: str) -> Counter[Any]:
    timestamps = {BASE_RECORDED_AT, recorded_at}
    return Counter(
        tuple((key, "<recorded-at>" if value in timestamps else value) for key, value in row.items())
        for row in _csv_rows(path)
    )


def _validate_release_delta(stage: Path, *, recorded_at: str) -> None:
    for filename in UNCHANGED_RELEASE_CSVS:
        if _normalized_csv_counter(
            stage / filename, recorded_at=recorded_at
        ) != _normalized_csv_counter(
            BASE_RELEASE / filename, recorded_at=recorded_at
        ):
            raise ValueError(f"v70 changed non-coordinate release rows: {filename}")

    before_pipeline = {
        row["stable_key"]: row
        for row in _csv_rows(BASE_RELEASE / "construction_pipeline.csv")
    }
    after_pipeline = {
        row["stable_key"]: row
        for row in _csv_rows(stage / "construction_pipeline.csv")
    }
    if set(before_pipeline) != set(after_pipeline) or len(after_pipeline) != 414:
        raise ValueError("v70 construction-pipeline inventory differs")
    pipeline_allowed = {
        "latitude",
        "longitude",
        "geometry_json",
        "snapshot_evidence_id",
        "source_url",
        "source_publisher",
        "source_license",
        "source_retrieved_at",
    }
    for stable_key, before in before_pipeline.items():
        after = after_pipeline[stable_key]
        changed = {key for key in before if before[key] != after[key]}
        if stable_key not in COORDINATE_PROJECT_KEYS:
            if changed:
                raise ValueError(
                    f"v70 changed non-coordinate pipeline row: {stable_key}"
                )
            continue
        if not changed or not changed <= pipeline_allowed:
            raise ValueError(f"v70 pipeline coordinate delta differs: {stable_key}")
        latitude, longitude = PUBLIC_COORDINATES[stable_key]
        if (
            after["latitude"] != str(latitude)
            or after["longitude"] != str(longitude)
            or after["status"] != before["status"]
            or after["status_as_of"] != before["status_as_of"]
            or after["capacity_estimates_json"] != before["capacity_estimates_json"]
            or after["workloads_json"] != before["workloads_json"]
        ):
            raise ValueError(f"v70 pipeline coordinate facts differ: {stable_key}")

    before_signals = {
        row["source_observation_evidence_id"]: row
        for row in _csv_rows(BASE_RELEASE / "construction_source_signals.csv")
    }
    after_signals = {
        row["source_observation_evidence_id"]: row
        for row in _csv_rows(stage / "construction_source_signals.csv")
    }
    if set(before_signals) != set(after_signals) or len(after_signals) != 316:
        raise ValueError("v70 construction-signal inventory differs")
    changed_signal_keys = set()
    for evidence_id, before in before_signals.items():
        after = after_signals[evidence_id]
        changed = {key for key in before if before[key] != after[key]}
        stable_key = after["representative_stable_key"]
        if not changed:
            continue
        changed_signal_keys.add(stable_key)
        if (
            stable_key not in COORDINATE_PROJECT_KEYS
            or changed
            != {"representative_latitude", "representative_longitude"}
        ):
            raise ValueError(f"v70 construction-signal delta differs: {stable_key}")
        latitude, longitude = PUBLIC_COORDINATES[stable_key]
        if (
            after["representative_latitude"] != str(latitude)
            or after["representative_longitude"] != str(longitude)
            or after["representative_status"] != before["representative_status"]
            or after["source_content_hash"] != before["source_content_hash"]
        ):
            raise ValueError(f"v70 construction-signal facts differ: {stable_key}")
    if changed_signal_keys != COORDINATE_PROJECT_KEYS:
        raise ValueError("v70 construction-signal coordinate set differs")

    before_evidence = {row["evidence_id"]: row for row in _csv_rows(BASE_RELEASE / "evidence.csv")}
    after_evidence = {row["evidence_id"]: row for row in _csv_rows(stage / "evidence.csv")}
    if len(after_evidence) != 510 or set(before_evidence) - set(after_evidence):
        raise ValueError("v70 public evidence inventory differs")
    if any(after_evidence[key] != row for key, row in before_evidence.items()):
        raise ValueError("v70 changed prior public evidence")
    added = [row for key, row in after_evidence.items() if key not in before_evidence]
    if (
        len(added) != 3
        or {row["source_family"] for row in added} != NEW_SOURCE_FAMILIES
        or {row["kind"] for row in added} != {"government_record"}
    ):
        raise ValueError("v70 public coordinate evidence delta differs")

    before_entities = {row["stable_key"]: row for row in _csv_rows(BASE_RELEASE / "entities.csv")}
    after_entities = {row["stable_key"]: row for row in _csv_rows(stage / "entities.csv")}
    if set(before_entities) != set(after_entities) or len(after_entities) != 806:
        raise ValueError("v70 public entity inventory differs")
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
                raise ValueError(f"v70 changed non-coordinate public entity: {stable_key}")
            continue
        if not changed or not changed <= allowed:
            raise ValueError(f"v70 public coordinate delta differs: {stable_key}")
        contract = COORDINATE_CONTRACT[stable_key]
        latitude, longitude = PUBLIC_COORDINATES[stable_key]
        if (
            after["latitude"] != str(latitude)
            or after["longitude"] != str(longitude)
            or json.loads(after["geometry_json"]) != contract["geometry"]
            or after["status"] != before["status"]
            or after["capacity_estimates_json"] != before["capacity_estimates_json"]
            or after["workloads_json"] != before["workloads_json"]
        ):
            raise ValueError(f"v70 public coordinate facts differ: {stable_key}")

    atlas = json.loads((stage / "atlas.geojson").read_text(encoding="utf-8"))
    features = {row["properties"]["stable_key"]: row for row in atlas["features"]}
    if len(features) != 806 or set(features) != set(after_entities):
        raise ValueError("v70 GeoJSON inventory differs")
    for stable_key, contract in COORDINATE_CONTRACT.items():
        feature = features[stable_key]
        if (
            feature["geometry"] != contract["geometry"]
            or feature["properties"]["latitude"] != contract["latitude"]
            or feature["properties"]["longitude"] != contract["longitude"]
        ):
            raise ValueError(f"v70 GeoJSON coordinate differs: {stable_key}")


def _validate_release_facts(stage: Path, *, recorded_at: str) -> None:
    summary = json.loads((stage / "summary.json").read_text(encoding="utf-8"))
    expected_summary = {
        "campuses_total": 425,
        "campuses_with_coordinates": 131,
        "capacity_estimates_current": 530,
        "construction_pipeline_records": 414,
        "construction_source_signals": 316,
        "entities_total": 806,
        "entities_with_coordinates": 189,
        "evidence_total": 631,
        "lifecycle_observations_current": 456,
        "projects_total": 381,
        "recorded_at": recorded_at,
    }
    if {key: summary.get(key) for key in expected_summary} != expected_summary:
        raise ValueError("v70 summary facts differ")
    base_summary = json.loads((BASE_RELEASE / "summary.json").read_text())
    for key in (
        "capacity_estimates_by_metric",
        "capacity_estimates_by_stage",
        "entities_by_status",
    ):
        if summary.get(key) != base_summary.get(key):
            raise ValueError(f"v70 changed summary {key}")

    manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    expected_manifest = {
        "entities": 806,
        "evidence_records": 510,
        "capacity_estimates": 530,
        "construction_pipeline_records": 414,
        "construction_source_signals": 316,
        "resolution_candidates": 6,
        "lifecycle_freshness_records": 456,
        "lifecycle_status_semantics": "last_observed",
        "current_status_inferred": False,
        "recorded_at": recorded_at,
    }
    if {key: manifest.get(key) for key in expected_manifest} != expected_manifest:
        raise ValueError("v70 manifest facts differ")
    base_manifest = json.loads((BASE_RELEASE / "manifest.json").read_text())
    if (
        set(manifest["source_families"]) - set(base_manifest["source_families"])
        != NEW_SOURCE_FAMILIES
        or set(base_manifest["source_families"]) - set(manifest["source_families"])
        or len(manifest["source_families"]) != 286
    ):
        raise ValueError("v70 source-family delta differs")
    if len(list(stage.iterdir())) != 14:
        raise ValueError("v70 release file inventory count differs")
    freshness = _csv_rows(stage / FRESHNESS_FILENAME)
    if (
        len(freshness) != 456
        or tuple(freshness[0]) != FRESHNESS_FIELDS
        or any(
            row["status_semantics"] != "last_observed"
            or row["current_status_classification"] != "unknown"
            or row["current_construction_claim"] != "false"
            for row in freshness
        )
    ):
        raise ValueError("v70 freshness/current-status guardrail differs")
    readme = (stage / "README.md").read_text(encoding="utf-8")
    for marker in (
        COORDINATE_MANIFEST_SHA256,
        COORDINATE_MANIFEST_TREE_SHA256,
        COORDINATE_PHYSICAL_TREE_SHA256,
        TEMPORAL_INCIDENT_MANIFEST_SHA256,
        PUBLICATION_INCIDENT_MANIFEST_SHA256,
        "current_status_classification` remains `unknown",
        "current_construction_claim` remains `false",
    ):
        if marker not in readme:
            raise ValueError("v70 README lineage/guardrail differs")


def _validate_definition(
    document: Mapping[str, Any],
    base: Mapping[str, Any],
    *,
    validation_wall_clock: datetime,
) -> str:
    if set(document) != set(base):
        raise ValueError("v70 definition schema differs from v69")
    if document.get("release_id") != RELEASE_ID:
        raise ValueError("v70 release_id differs")
    build = document.get("build")
    if not isinstance(build, dict) or set(build) != {"as_of", "recorded_at"}:
        raise ValueError("v70 build carrier differs")
    if build.get("as_of") != AS_OF:
        raise ValueError("v70 as_of differs")
    recorded = parse_utc(build.get("recorded_at"), label="v70 recorded_at")
    if validation_wall_clock.tzinfo is None:
        raise ValueError("validation wall clock must include a timezone")
    if recorded > validation_wall_clock.astimezone(timezone.utc):
        raise ValueError("v70 recorded_at is later than validation wall clock")
    for key in (
        "epoch_capture",
        "expected_epoch_result",
        "freshness_contract",
        "publication_contract_version",
        "schema_version",
        "scope",
    ):
        if document.get(key) != base.get(key):
            raise ValueError(f"v70 inherited definition field differs: {key}")
    return build["recorded_at"]


def _ordinary_file(path: Path, label: str) -> bytes:
    if not path.is_file() or path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"{label} must be an ordinary file")
    return path.read_bytes()


def _validate_publication_times(
    definition_path: Path, release_path: Path, *, recorded_at: str
) -> None:
    recorded = parse_utc(recorded_at, label="v70 recorded_at").timestamp()
    for path in (definition_path, release_path, *release_path.iterdir()):
        status = path.stat()
        if status.st_birthtime > recorded + 0.000_001:
            raise ValueError(f"v70 artifact was born after recorded_at: {path.name}")
        if status.st_mtime > recorded + 0.000_001:
            raise ValueError(f"v70 artifact mtime is after recorded_at: {path.name}")


def validate_open_seed_v70(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
) -> dict[str, Any]:
    if replay_count != 2:
        raise ValueError("v70 requires exactly two offline replays")
    wall_clock = validation_wall_clock or datetime.now(timezone.utc)
    guard = _guard_state()
    if (
        guard["base_definition"] != BASE_DEFINITION_SHA256
        or guard["base_manifest"] != BASE_MANIFEST_SHA256
        or guard["base_tree"] != BASE_TREE_SHA256
    ):
        raise ValueError("accepted v69 base pin differs")
    base_raw = _ordinary_file(BASE_DEFINITION, "v69 definition")
    base = json.loads(base_raw)
    definition_raw = _ordinary_file(definition_path, "v70 definition")
    document = json.loads(definition_raw)
    if definition_raw != v69.canonical_json(document):
        raise ValueError("v70 definition JSON is not canonical")
    recorded_at = _validate_definition(
        document, base, validation_wall_clock=wall_clock
    )
    selected, paths = selected_inputs(
        base, recorded_at=recorded_at, validation_wall_clock=wall_clock
    )
    if document.get("curated_inputs") != selected:
        raise ValueError("v70 selected input inventory differs")

    if not release_path.is_dir() or release_path.is_symlink():
        raise ValueError("v70 release must be an ordinary directory")
    if require_frozen and stat.S_IMODE(release_path.stat().st_mode) != 0o555:
        raise ValueError("v70 release directory mode must be 0555")
    release_files = {path.name: path for path in release_path.iterdir()}
    if any(path.is_symlink() or not path.is_file() for path in release_files.values()):
        raise ValueError("v70 release contains a symlink or non-file")
    if require_frozen and any(
        stat.S_IMODE(path.stat().st_mode) != 0o444 for path in release_files.values()
    ):
        raise ValueError("v70 release file mode must be 0444")
    manifest_raw = _ordinary_file(release_path / "manifest.json", "v70 manifest")
    manifest = json.loads(manifest_raw)
    if hashlib.sha256(manifest_raw).hexdigest() != document["expected_release"].get(
        "manifest_sha256"
    ):
        raise ValueError("v70 manifest hash differs")
    expected_release = {
        key: value for key, value in document["expected_release"].items()
        if key != "manifest_sha256"
    }
    if {key: value for key, value in manifest.items() if key != "files"} != expected_release:
        raise ValueError("v70 expected release facts differ")
    if set(release_files) != set(manifest["files"]) | {"manifest.json"}:
        raise ValueError("v70 release file inventory differs")
    for filename, pin in manifest["files"].items():
        payload = _ordinary_file(release_path / filename, filename)
        if (len(payload), hashlib.sha256(payload).hexdigest()) != (
            pin["bytes"], pin["sha256"]
        ):
            raise ValueError(f"v70 release file pin differs: {filename}")
    _validate_publication_times(
        definition_path, release_path, recorded_at=recorded_at
    )
    _validate_release_delta(release_path, recorded_at=recorded_at)
    _validate_release_facts(release_path, recorded_at=recorded_at)
    summary = json.loads((release_path / "summary.json").read_text())
    if {key: summary[key] for key in document["expected_summary"]} != document[
        "expected_summary"
    ]:
        raise ValueError("v70 expected summary differs")

    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v70-replay-{replay + 1}-", dir="/private/tmp"
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
            _validate_release_delta(replay_release, recorded_at=recorded_at)
            _validate_release_facts(replay_release, recorded_at=recorded_at)
            if {path.name for path in replay_release.iterdir()} != set(release_files):
                raise ValueError("v70 replay file inventory differs")
            for filename, frozen in release_files.items():
                if (replay_release / filename).read_bytes() != frozen.read_bytes():
                    raise ValueError(f"v70 offline replay differs: {filename}")
    if _guard_state() != guard:
        raise ValueError("v70 validation mutated accepted inputs")
    return manifest


def _planned_publication_time(lead_seconds: int = 20) -> str:
    target = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(
        seconds=lead_seconds
    )
    return target.isoformat().replace("+00:00", "Z")


def _max_stage_time(paths: tuple[Path, ...]) -> float:
    values = []
    for root in paths:
        for path in (root, *root.rglob("*")) if root.is_dir() else (root,):
            status = path.stat()
            values.extend((status.st_birthtime, status.st_mtime))
    return max(values)


def _wait_until(recorded_at: str) -> None:
    target = parse_utc(recorded_at, label="v70 recorded_at").timestamp()
    while time.time() < target:
        time.sleep(min(0.05, target - time.time()))


def build_open_seed_v70() -> dict[str, Any]:
    guard = _guard_state()
    with publication_lock():
        if DEFINITION.exists() or DEFINITION.is_symlink():
            raise SystemExit(f"definition already exists; refusing overwrite: {DEFINITION}")
        if RELEASE.exists() or RELEASE.is_symlink():
            raise SystemExit(f"release already exists; refusing overwrite: {RELEASE}")
        if (
            guard["base_definition"] != BASE_DEFINITION_SHA256
            or guard["base_manifest"] != BASE_MANIFEST_SHA256
            or guard["base_tree"] != BASE_TREE_SHA256
        ):
            raise SystemExit("accepted v69 base pin differs")

        release_stage = Path(
            tempfile.mkdtemp(prefix=f".{RELEASE.name}.", dir=RELEASE.parent)
        )
        definition_stage = DEFINITION.parent / f".{DEFINITION.name}.{os.getpid()}.tmp"
        try:
            descriptor = os.open(
                definition_stage, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
        except FileExistsError as error:
            v69.discard_release_stage(release_stage)
            raise SystemExit(f"definition stage collision: {definition_stage}") from error
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

        published_release = False
        try:
            recorded_at = _planned_publication_time()
            planned_wall = parse_utc(recorded_at, label="v70 recorded_at")
            base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
            input_rows, paths = selected_inputs(
                base,
                recorded_at=recorded_at,
                validation_wall_clock=planned_wall,
            )
            staging_root = ROOT / ".staging"
            staging_root.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix="open-seed-v70-db-", dir=staging_root
            ) as temporary:
                connection = _build_database(
                    base,
                    paths,
                    Path(temporary) / "atlas.sqlite",
                    recorded_at=recorded_at,
                )
                try:
                    _write_release(
                        connection,
                        release_stage,
                        recorded_at=recorded_at,
                        precreated=True,
                    )
                    summary = summarize(
                        connection, as_of=AS_OF, recorded_at=recorded_at
                    )
                finally:
                    connection.close()
            _validate_release_delta(release_stage, recorded_at=recorded_at)
            _validate_release_facts(release_stage, recorded_at=recorded_at)
            manifest_raw = (release_stage / "manifest.json").read_bytes()
            manifest = json.loads(manifest_raw)
            expected_release = {
                key: value for key, value in manifest.items() if key != "files"
            }
            expected_release["manifest_sha256"] = hashlib.sha256(
                manifest_raw
            ).hexdigest()
            definition = dict(base)
            definition["build"] = {"as_of": AS_OF, "recorded_at": recorded_at}
            definition["curated_inputs"] = input_rows
            definition["expected_release"] = expected_release
            definition["expected_summary"] = {
                key: summary[key] for key in base["expected_summary"]
            }
            definition["release_id"] = RELEASE_ID
            with definition_stage.open("r+b") as stream:
                stream.write(v69.canonical_json(definition))
                stream.truncate()
                stream.flush()
                os.fsync(stream.fileno())
            definition_stage.chmod(0o644)
            for output in release_stage.iterdir():
                output.chmod(0o444)
            release_stage.chmod(0o555)
            target = parse_utc(recorded_at, label="v70 recorded_at").timestamp()
            if _max_stage_time((definition_stage, release_stage)) > target + 0.000_001:
                raise SystemExit("v70 staging exceeded its planned publication timestamp")
            _wait_until(recorded_at)
            validate_open_seed_v70(definition_stage, release_stage)
            v69.promote_noreplace(release_stage, RELEASE)
            published_release = True
            v69.promote_noreplace(definition_stage, DEFINITION)
            validate_open_seed_v70(DEFINITION, RELEASE)
        finally:
            if not published_release:
                v69.discard_release_stage(release_stage)
            try:
                definition_stage.unlink()
            except FileNotFoundError:
                pass
    if _guard_state() != guard:
        raise SystemExit("v70 build mutated accepted inputs")
    manifest = json.loads((RELEASE / "manifest.json").read_text())
    return {
        "definition": str(DEFINITION),
        "definition_sha256": v69.sha256(DEFINITION),
        "manifest_sha256": v69.sha256(RELEASE / "manifest.json"),
        "recorded_at": manifest["recorded_at"],
        "release": str(RELEASE),
        "release_tree_sha256": v69.tree_digest(RELEASE),
        **{
            key: value for key, value in manifest.items()
            if key not in {"files", "source_families"}
        },
        "source_families": len(manifest["source_families"]),
    }


def main() -> int:
    print(json.dumps(build_open_seed_v70(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
