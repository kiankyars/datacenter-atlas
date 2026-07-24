"""Build and freeze official open seed v66 as the exact v65 successor.

V66 remains on the 2026-07-20 local research day. It replaces four selected
curated files with authoritative coordinate-bearing successors. No identity,
lifecycle, capacity, workload, operating-model, role, or canonical-address
claim changes.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import copy
import csv
from dataclasses import asdict
from datetime import date
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
from typing import Any, Iterator, Mapping

from .curated import CuratedOfficialSourceAdapter
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .epoch import EpochAIAdapter
from .open_seed_release_v10 import (
    OUT_OF_SCOPE_EXCLUSIONS,
    PENDING_NEXT_DAY_EXCLUSIONS,
    STALE_EXCLUSIONS,
    freshness_contract,
)
from .open_seed_v56 import (
    canonical_json,
    discard_release_stage,
    promote_noreplace,
    sha256,
    tree_digest,
)
from .open_seed_v61 import FRESHNESS_FIELDS, FRESHNESS_FILENAME, build_freshness_csv
from .publication_release import build_release_documents
from .service import summarize, validate_database


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v65.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v65"
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v66.json"
RELEASE_ID = "2026-07-20-open-seed-v66"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v66.lock"

AS_OF = "2026-07-20"
RECORDED_AT = "2026-07-21T07:00:00Z"
V11_RECORDED_AT = RECORDED_AT

BASE_DEFINITION_SHA256 = (
    "7431234bac3158ceada1f9545c841a5c59557ed97ec602695e0a3849da9c3d7d"
)
BASE_MANIFEST_SHA256 = (
    "38fcfc7fbd051decdb73c071762c2bb38e430ea43a4f9054489f51b6cb55c92b"
)
BASE_TREE_SHA256 = "8448b30e9909e5f752c50c3b6c568445d1c963a11d97a62f1e4bf4bc3bca6e11"

FRESHNESS_README = (
    "`lifecycle_freshness.csv` treats every published lifecycle value as a "
    "last-observed status, reports its age on the release date, and makes no "
    "current-construction inference. Its 0–90, 91–365, and over-365-day bands "
    "are review queues, not evidence that a status persisted. "
    "`current_status_classification` therefore remains `unknown` and "
    "`current_construction_claim` remains `false` for every row. V66 changes "
    "only authoritative coordinate evidence and the corresponding campus and "
    "project snapshot location fields for four selected sources; lifecycle, "
    "capacity, workload, operating-model, role, and canonical-address claims "
    "remain unchanged."
)

REPLACEMENT_PINS: dict[str, tuple[str, str, str]] = {
    "sources/curated-official-2026-07-20-coresite-de3-denver.json": (
        "8bfb0b31e468647753a142e9fc0ba3306e06e8272b02e6fbe848809a3bd69868",
        "sources/curated-official-2026-07-20-coresite-de3-denver-v2.json",
        "9d0727dcbb8ed42b55887012d0d267188e4561d67f4694dd49ce2e834ed64ab2",
    ),
    "sources/curated-official-2026-07-20-powerhouse-irving-building-1-topout.json": (
        "03e3c1de817fba2a0b14d42ec5d063caf07ac23df4083b22bd0a99f6803d0990",
        "sources/curated-official-2026-07-20-powerhouse-irving-building-1-topout-v2.json",
        "48ea1c56e18fbf0d7f69be51e4892f60e5871ca5540f19e3eb21040205217ce3",
    ),
    "sources/curated-official-2026-07-20-edged-ord01-2-chicago-topout.json": (
        "576e5d80846805d130dbebc50b0af8a23cbdac619ccf664dbf2421cdaeaa5a7c",
        "sources/curated-official-2026-07-20-edged-ord01-2-chicago-topout-v3.json",
        "a61e7d4f4c4374a99b62b52980903c94e7b8c2659a8470045530fbc2cb55fe4e",
    ),
    "sources/curated-official-2026-07-20-core-scientific-dalton-4.json": (
        "ed121928047032b1740d7f6e30faa0fad7304cb6b5144c1b708812300ebe9a09",
        "sources/curated-official-2026-07-20-core-scientific-dalton-4-v2.json",
        "55fcb118be1a5380f2ec49ccb56b557fc35deedd3cdfcadef727df3b3bf98733",
    ),
}

REJECTED_EDGED_V2 = (
    "sources/curated-official-2026-07-20-edged-ord01-2-chicago-topout-v2.json",
    "03fa4a5915a43d70456b63ab54c2b7c8eb9bdf918ffc10c938276a4da90db368",
)

SOURCE_CHANGE_CONTRACT: dict[str, dict[str, Any]] = {
    "sources/curated-official-2026-07-20-coresite-de3-denver.json": {
        "schema_changed": True,
        "appended": 1,
        "campus": {"coordinates", "geometry", "evidence_key", "method"},
        "project": {"coordinates", "geometry", "evidence_key", "method"},
    },
    "sources/curated-official-2026-07-20-powerhouse-irving-building-1-topout.json": {
        "schema_changed": False,
        "appended": 2,
        "campus": {"coordinates", "geometry", "evidence_key", "method"},
        "project": {
            "coordinates",
            "geometry",
            "evidence_key",
            "as_of_date",
            "method",
        },
    },
    "sources/curated-official-2026-07-20-edged-ord01-2-chicago-topout.json": {
        "schema_changed": True,
        "appended": 1,
        "campus": {"coordinates", "geometry", "evidence_key", "method"},
        "project": {"coordinates", "geometry", "evidence_key", "method"},
    },
    "sources/curated-official-2026-07-20-core-scientific-dalton-4.json": {
        "schema_changed": False,
        "appended": 2,
        "campus": {
            "coordinates",
            "geometry",
            "evidence_key",
            "as_of_date",
            "method",
        },
        "project": {
            "coordinates",
            "geometry",
            "evidence_key",
            "as_of_date",
            "method",
        },
    },
}

COORDINATE_CONTRACT = {
    "curated:coresite-de3-race-street-campus": (
        39.7861942431606,
        -104.96277124667975,
        "Polygon",
        "authoritative_site_plan",
        "2026-07-20",
    ),
    "curated:coresite-de3-race-street-campus:de3": (
        39.7861942431606,
        -104.96277124667975,
        "Polygon",
        "authoritative_site_plan",
        "2026-07-20",
    ),
    "curated:powerhouse-irving-data-center-campus": (
        32.888545840931,
        -96.9410613460374,
        "Point",
        "authoritative_address_geocode",
        "2026-07-20",
    ),
    "curated:powerhouse-irving-data-center-campus:building-1-current-build": (
        32.888545840931,
        -96.9410613460374,
        "Point",
        "authoritative_address_geocode",
        "2026-07-20",
    ),
    "curated:edged-chicago-aurora-campus": (
        41.806967678,
        -88.240996871,
        "Point",
        "authoritative_address_geocode",
        "2026-07-20",
    ),
    "curated:edged-chicago-aurora-campus:ord01-2": (
        41.806967678,
        -88.240996871,
        "Point",
        "authoritative_address_geocode",
        "2026-07-20",
    ),
    "curated:core-scientific-dalton-4-data-center-campus": (
        34.6948095438794,
        -84.941093728219,
        "Point",
        "authoritative_address_geocode",
        "2026-07-20",
    ),
    "curated:core-scientific-dalton-4-data-center-campus:greenfield-build": (
        34.6948095438794,
        -84.941093728219,
        "Point",
        "authoritative_address_geocode",
        "2026-07-20",
    ),
}

MUTATED_ENTITY_KEYS = frozenset(COORDINATE_CONTRACT)
MUTATED_PROJECT_KEYS = frozenset(
    {
        "curated:coresite-de3-race-street-campus:de3",
        "curated:powerhouse-irving-data-center-campus:building-1-current-build",
        "curated:edged-chicago-aurora-campus:ord01-2",
        "curated:core-scientific-dalton-4-data-center-campus:greenfield-build",
    }
)

ENTITY_SNAPSHOT_CHANGE_FIELDS = frozenset(
    {
        "latitude",
        "longitude",
        "geometry_json",
        "snapshot_as_of",
        "snapshot_evidence_id",
        "source_url",
        "source_publisher",
        "source_license",
        "source_retrieved_at",
    }
)

# Common, added, added hash, removed, removed hash against frozen v65.
CSV_DELTA_CONTRACT = {
    "entities.csv": (
        747,
        8,
        "b6f193f7d830d34d60aa7ed95a5282b8aaa576056308755114a376e536d48d10",
        8,
        "aa174a95b3166bbb60d551b69f02df2cae7ba75829b803824a5721f5a3553025",
    ),
    "evidence.csv": (
        467,
        4,
        "dde95dcb1e29c80264730e2ea15c956b0c0d7a48469c154810c52ffa3cf067d8",
        1,
        "79a60009706e9d57fa1de0953c9d22074823d72ebb9b87b8e6a6365429ef80b5",
    ),
    "capacity_estimates.csv": (
        512,
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_pipeline.csv": (
        383,
        4,
        "4aee653bdd302324941aceb79352734acf25342ee91d8ba6e753b8e0fb89b220",
        4,
        "9beb5bbb775fd246d899327d25be330867563f9b5a8956f8df92ed6fd3c1ac47",
    ),
    "construction_source_signals.csv": (
        288,
        4,
        "e4a83c5ebb318557b94e86323355f325a199ecb2b4d3cbc3af13213c0a828d77",
        4,
        "5492c28261dd094b7e35c3a4a16be6ba8d576c7cde29718298b717e08bf37b49",
    ),
    "resolution_candidates.csv": (
        5,
        1,
        "3ea0af041169e0b45ead1fb2b62122bdb19492d91ea841ee96fa9ee4d5e95f08",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
}

PUBLIC_EVIDENCE_ADDED = {
    "58cd4851-129d-59c4-9cb0-4f24070a71a9": (
        "denver_open_data_property_parcels",
        "Denver tax parcel 0214400131000 at 4900 North Race Street",
        "41387d3d2d09af9e88e494d24f29ccc6897f25b0b077edf5f9011a470de0c7e2",
    ),
    "7926ee19-0abd-5eaa-96d8-4db720fc1ab0": (
        "whitfield_county_addressing_points",
        "Whitfield County 911 point for 1199 Enterprise Drive",
        "add0b6ce576afa5b0de6e6a23ee7990d64ae19b805414106b938baefdfd3f5a9",
    ),
    "98fcd750-ba33-537e-8669-fe8d1db1a6c6": (
        "aurora_open_data_address_points",
        "City of Aurora address point 85050 at 2835 Bilter Road",
        "8db6b8217609665b4b58ab8ade5e5bb0a252321f056a1e80d6203533d837a84a",
    ),
    "ae36c78d-e5c6-5578-a3f4-6913e37f24bc": (
        "irving_planning_and_zoning_open_data",
        "City of Irving permit 2025-02-1125 at 111 Customer Way",
        "c01d04e1303c2c66df6449656f0cc102d487bcb9c5564b58d8a3ddce405ebb0d",
    ),
}

PUBLIC_EVIDENCE_REMOVED = {
    "276847d4-183f-5995-ab80-90d4636b467b": (
        "coresite_official_website",
        "CoreSite DE3 - Denver Data Center",
        "99720e18665fabb5cb2d09308b60326c9bcb226dd1ff2648fa95ba3b21fdb894",
    )
}

RESOLUTION_CANDIDATE_ADDED = {
    "relationship_suggestion": "nearby_only",
    "distance_m": "2236.579",
    "left_name": "CoreWeave Dalton 1 & 2",
    "left_source_family": "epoch_ai_data_centers",
    "left_evidence_id": "ca532cc3-ab94-5feb-ad8a-8b975f4f6f4b",
    "right_name": "Core Scientific Dalton 4 Data Center Campus",
    "right_source_family": "whitfield_county_addressing_points",
    "right_evidence_id": "7926ee19-0abd-5eaa-96d8-4db720fc1ab0",
    "suggested_parent_entity_id": "",
    "suggested_child_entity_id": "",
}

NEW_SOURCE_FAMILIES = {
    "aurora_open_data_address_points",
    "denver_open_data_property_parcels",
    "irving_planning_and_zoning_open_data",
    "whitfield_county_addressing_points",
}


@contextmanager
def publication_lock() -> Iterator[None]:
    """Hold an exclusive v66 publication lock without replacing any file."""

    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise SystemExit(
            f"active publication lock exists: {PUBLICATION_LOCK}"
        ) from error
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


def _load_source(relative: str, digest: str) -> dict[str, Any]:
    path = ROOT / relative
    if not path.is_file() or path.is_symlink():
        raise SystemExit(f"source must be an ordinary file: {relative}")
    if stat.S_IMODE(path.stat().st_mode) != 0o644:
        raise SystemExit(f"source mode must be 0644: {relative}")
    if sha256(path) != digest:
        raise SystemExit(f"source hash differs: {relative}")
    document = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    if path.read_text(encoding="utf-8") != canonical:
        raise SystemExit(f"source JSON is not canonical: {relative}")
    return document


def _validate_source_successors() -> None:
    appended_total = 0
    for predecessor_path, (old_hash, successor_path, new_hash) in (
        REPLACEMENT_PINS.items()
    ):
        predecessor = _load_source(predecessor_path, old_hash)
        successor = _load_source(successor_path, new_hash)
        contract = SOURCE_CHANGE_CONTRACT[predecessor_path]
        if successor.get("schema_version") != "1.1":
            raise SystemExit(f"successor schema differs: {successor_path}")
        if (
            predecessor.get("schema_version") != successor.get("schema_version")
        ) != contract["schema_changed"]:
            raise SystemExit(f"successor schema-change boundary differs: {successor_path}")
        inherited = len(predecessor["evidence"])
        if successor["evidence"][:inherited] != predecessor["evidence"]:
            raise SystemExit(f"inherited evidence differs: {successor_path}")
        appended = successor["evidence"][inherited:]
        if len(appended) != contract["appended"]:
            raise SystemExit(f"appended evidence count differs: {successor_path}")
        appended_total += len(appended)
        for entity_name in ("campus", "project"):
            before = predecessor[entity_name]
            after = successor[entity_name]
            changed = {key for key in before if before[key] != after[key]}
            if changed != contract[entity_name]:
                raise SystemExit(
                    f"coordinate-only field boundary differs: {successor_path}:{entity_name}"
                )
            if before["stable_key"] != after["stable_key"]:
                raise SystemExit(f"stable key differs: {successor_path}:{entity_name}")
            if date.fromisoformat(after["as_of_date"]) > date.fromisoformat(AS_OF):
                raise SystemExit(f"successor crosses research day: {successor_path}")
        restored = copy.deepcopy(successor)
        restored["schema_version"] = predecessor["schema_version"]
        restored["evidence"] = copy.deepcopy(predecessor["evidence"])
        restored["campus"] = copy.deepcopy(predecessor["campus"])
        restored["project"] = copy.deepcopy(predecessor["project"])
        if restored != predecessor:
            raise SystemExit(f"successor contains a non-coordinate change: {successor_path}")
        if max(row["retrieved_at"] for row in successor["evidence"]) > RECORDED_AT:
            raise SystemExit(f"successor evidence is newer than publication: {successor_path}")
    if appended_total != 6:
        raise SystemExit(f"expected six appended coordinate evidence rows, found {appended_total}")
    _load_source(*REJECTED_EDGED_V2)


def selected_inputs(base: Mapping[str, Any]) -> tuple[list[dict[str, str]], list[Path]]:
    """Return the exact four-replacement, 364-input v65 successor."""

    if base.get("release_id") != "2026-07-20-open-seed-v65":
        raise SystemExit("v66 base must be exactly frozen v65")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 364:
        raise SystemExit("frozen v65 curated inventory differs")
    pins: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise SystemExit("frozen v65 curated row is invalid")
        source_path, digest = row["path"], row["sha256"]
        if (
            not isinstance(source_path, str)
            or not isinstance(digest, str)
            or source_path in pins
        ):
            raise SystemExit("frozen v65 curated inventory is invalid")
        pins[source_path] = digest

    _validate_source_successors()
    for predecessor, (old_hash, successor, new_hash) in REPLACEMENT_PINS.items():
        if pins.get(predecessor) != old_hash or successor in pins:
            raise SystemExit(f"replacement boundary differs: {predecessor}")
        del pins[predecessor]
        pins[successor] = new_hash

    rejected_path, _ = REJECTED_EDGED_V2
    if rejected_path in pins:
        raise SystemExit("rejected Edged Google-derived v2 was selected")
    excluded = STALE_EXCLUSIONS | PENDING_NEXT_DAY_EXCLUSIONS | OUT_OF_SCOPE_EXCLUSIONS
    if excluded & set(pins):
        raise SystemExit("an excluded source was selected")
    if len(pins) != 364:
        raise SystemExit(f"expected 364 unique v66 inputs, found {len(pins)}")

    rows_out = [
        {"path": source_path, "sha256": pins[source_path]}
        for source_path in sorted(pins)
    ]
    paths: list[Path] = []
    for row in rows_out:
        path = ROOT / row["path"]
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"input must be an ordinary file: {row['path']}")
        if stat.S_IMODE(path.stat().st_mode) != 0o644:
            raise SystemExit(f"input mode must be 0644: {row['path']}")
        if sha256(path) != row["sha256"]:
            raise SystemExit(f"input hash differs: {row['path']}")
        paths.append(path)
    return rows_out, paths


def _import_curated(connection: sqlite3.Connection, source_path: Path) -> object:
    document = json.loads(source_path.read_text(encoding="utf-8"))
    timestamps = {item["retrieved_at"] for item in document["evidence"]}
    if document["schema_version"] == "1.0":
        if len(timestamps) != 1:
            raise SystemExit(
                f"schema 1.0 source has multiple timestamps: {source_path.name}"
            )
        return CuratedOfficialSourceAdapter().import_file(
            connection, source_path, retrieved_at=next(iter(timestamps))
        )
    if document["schema_version"] == "1.1":
        return CuratedOfficialSourceAdapterV11().import_file(
            connection, source_path, recorded_at=V11_RECORDED_AT
        )
    raise SystemExit(f"unsupported curated schema: {source_path.name}")


def _validate_database_contract(connection: sqlite3.Connection) -> None:
    tables = (
        "entities",
        "evidence",
        "lifecycle_observations",
        "capacity_estimates",
        "entity_snapshots",
        "operating_model_observations",
        "workload_observations",
    )
    counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in tables
    }
    expected = {
        "entities": 755,
        "evidence": 583,
        "lifecycle_observations": 444,
        "capacity_estimates": 513,
        "entity_snapshots": 775,
        "operating_model_observations": 56,
        "workload_observations": 125,
    }
    if counts != expected:
        raise SystemExit(f"fresh v66 database projection differs: {counts}")

    keys = tuple(sorted(MUTATED_ENTITY_KEYS))
    placeholders = ",".join("?" for _ in keys)
    rows = connection.execute(
        f"""
        SELECT entities.stable_key, entity_snapshots.latitude,
               entity_snapshots.longitude, entity_snapshots.geometry_json,
               entity_snapshots.method, entity_snapshots.as_of_date
        FROM entity_snapshots
        JOIN entities ON entities.id = entity_snapshots.entity_id
        WHERE entities.stable_key IN ({placeholders})
          AND entity_snapshots.valid_to_date IS NULL
          AND entity_snapshots.superseded_at IS NULL
        """,
        keys,
    ).fetchall()
    if len(rows) != len(keys):
        raise SystemExit("v66 current coordinate snapshot set differs")
    actual: dict[str, tuple[float, float, str, str, str]] = {}
    for stable_key, latitude, longitude, geometry_json, method, as_of_date in rows:
        geometry_type = json.loads(geometry_json)["type"]
        actual[stable_key] = (
            latitude,
            longitude,
            geometry_type,
            method,
            as_of_date,
        )
    if actual != COORDINATE_CONTRACT:
        raise SystemExit(f"fresh v66 coordinate contract differs: {actual}")


def _build_database(base: Mapping[str, Any], paths: list[Path], sqlite_path: Path):
    connection, _ = initialize(sqlite_path)
    epoch = base["epoch_capture"]
    result = EpochAIAdapter().import_file(
        connection,
        ROOT / epoch["archive"],
        map_html=ROOT / epoch["map"],
        retrieved_at=epoch["retrieved_at"],
        as_of_date=AS_OF,
    )
    if json.loads(json.dumps(asdict(result))) != base["expected_epoch_result"]:
        connection.close()
        raise SystemExit("fresh Epoch import result differs from v65")
    try:
        for source_path in paths:
            imported = _import_curated(connection, source_path)
            if getattr(imported, "warnings"):
                raise SystemExit(f"curated import warnings for {source_path.name}")
        errors = validate_database(connection)
        if errors:
            raise SystemExit("fresh database validation failed: " + "; ".join(errors))
        _validate_database_contract(connection)
        return connection
    except Exception:
        connection.close()
        raise


def augment_release_documents(
    documents: Mapping[str, str], *, as_of: str
) -> dict[str, str]:
    """Add the unchanged last-observed carrier and bind it into the manifest."""

    output = dict(documents)
    if FRESHNESS_FILENAME in output:
        raise RuntimeError("freshness filename already exists")
    freshness = build_freshness_csv(output["entities.csv"], as_of=as_of)
    output[FRESHNESS_FILENAME] = freshness
    readme = output["README.md"].rstrip() + "\n\n" + FRESHNESS_README + "\n"
    output["README.md"] = readme
    manifest = json.loads(output["manifest.json"])
    manifest["files"]["README.md"] = {
        "bytes": len(readme.encode("utf-8")),
        "sha256": hashlib.sha256(readme.encode("utf-8")).hexdigest(),
    }
    manifest["files"][FRESHNESS_FILENAME] = {
        "bytes": len(freshness.encode("utf-8")),
        "sha256": hashlib.sha256(freshness.encode("utf-8")).hexdigest(),
    }
    freshness_rows = list(csv.DictReader(io.StringIO(freshness)))
    manifest["current_status_inferred"] = False
    manifest["lifecycle_freshness_records"] = len(freshness_rows)
    manifest["lifecycle_status_semantics"] = "last_observed"
    output["manifest.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    return output


def _write_augmented_release(connection: sqlite3.Connection, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    documents = build_release_documents(
        connection,
        as_of=AS_OF,
        recorded_at=RECORDED_AT,
        publication_contract_version=4,
    )
    for filename, text in augment_release_documents(documents, as_of=AS_OF).items():
        (output / filename).write_text(text, encoding="utf-8")


def _csv_counter(path: Path) -> Counter[tuple[tuple[str, str], ...]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return Counter(tuple(row.items()) for row in csv.DictReader(stream))


def _counter_hash(counter: Counter[tuple[tuple[str, str], ...]]) -> str:
    rows = [dict(packed) for packed in counter.elements()]
    rows.sort(
        key=lambda row: json.dumps(
            row, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    )
    raw = (
        json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _rows_by_key(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return {row["stable_key"]: row for row in csv.DictReader(stream)}


def _changed_fields(before: Mapping[str, str], after: Mapping[str, str]) -> set[str]:
    return {key for key in before if before[key] != after[key]}


def _validate_release_delta(stage: Path) -> None:
    for filename, expected in CSV_DELTA_CONTRACT.items():
        before = _csv_counter(BASE_RELEASE / filename)
        after = _csv_counter(stage / filename)
        common = before & after
        added = after - common
        removed = before - common
        actual = (
            sum(common.values()),
            sum(added.values()),
            _counter_hash(added),
            sum(removed.values()),
            _counter_hash(removed),
        )
        if actual != expected:
            raise SystemExit(f"fresh v66 CSV delta differs: {filename}: {actual}")

    evidence_before = _csv_counter(BASE_RELEASE / "evidence.csv")
    evidence_after = _csv_counter(stage / "evidence.csv")
    added_evidence = {
        row["evidence_id"]: (
            row["source_family"],
            row["title"],
            row["content_hash"],
        )
        for row in map(dict, (evidence_after - evidence_before).elements())
    }
    removed_evidence = {
        row["evidence_id"]: (
            row["source_family"],
            row["title"],
            row["content_hash"],
        )
        for row in map(dict, (evidence_before - evidence_after).elements())
    }
    if added_evidence != PUBLIC_EVIDENCE_ADDED:
        raise SystemExit(f"v66 public evidence additions differ: {added_evidence}")
    if removed_evidence != PUBLIC_EVIDENCE_REMOVED:
        raise SystemExit(f"v66 public evidence removal differs: {removed_evidence}")

    resolution_before = _csv_counter(BASE_RELEASE / "resolution_candidates.csv")
    resolution_after = _csv_counter(stage / "resolution_candidates.csv")
    added_candidates = [
        dict(row) for row in (resolution_after - resolution_before).elements()
    ]
    if len(added_candidates) != 1 or (
        {
            key: added_candidates[0][key] for key in RESOLUTION_CANDIDATE_ADDED
        }
        != RESOLUTION_CANDIDATE_ADDED
    ):
        raise SystemExit(f"v66 Dalton nearby-only advisory differs: {added_candidates}")
    if resolution_before - resolution_after:
        raise SystemExit("v66 removed a resolution candidate")

    before_entities = _rows_by_key(BASE_RELEASE / "entities.csv")
    after_entities = _rows_by_key(stage / "entities.csv")
    if set(before_entities) != set(after_entities):
        raise SystemExit("v66 changed the stable entity identity set")
    changed = {
        key
        for key in before_entities
        if before_entities[key] != after_entities[key]
    }
    if changed != MUTATED_ENTITY_KEYS:
        raise SystemExit("v66 entity-row mutation set is not exactly eight snapshots")
    for key in changed:
        fields = _changed_fields(before_entities[key], after_entities[key])
        if not fields or not fields <= ENTITY_SNAPSHOT_CHANGE_FIELDS:
            raise SystemExit(f"v66 changed a non-snapshot entity field: {key}:{fields}")

    before_pipeline = _rows_by_key(BASE_RELEASE / "construction_pipeline.csv")
    after_pipeline = _rows_by_key(stage / "construction_pipeline.csv")
    if set(before_pipeline) != set(after_pipeline):
        raise SystemExit("v66 changed the construction-pipeline identity set")
    changed_pipeline = {
        key
        for key in before_pipeline
        if before_pipeline[key] != after_pipeline[key]
    }
    if changed_pipeline != MUTATED_PROJECT_KEYS:
        raise SystemExit("v66 construction-pipeline mutation set differs")
    for key in changed_pipeline:
        fields = _changed_fields(before_pipeline[key], after_pipeline[key])
        if not fields or not fields <= ENTITY_SNAPSHOT_CHANGE_FIELDS:
            raise SystemExit(f"v66 changed a non-snapshot pipeline field: {key}:{fields}")

    if (stage / "capacity_estimates.csv").read_bytes() != (
        BASE_RELEASE / "capacity_estimates.csv"
    ).read_bytes():
        raise SystemExit("v66 changed capacity estimates")
    if (stage / FRESHNESS_FILENAME).read_bytes() != (
        BASE_RELEASE / FRESHNESS_FILENAME
    ).read_bytes():
        raise SystemExit("v66 changed lifecycle freshness observations")


def _validate_freshness(stage: Path) -> None:
    with (stage / FRESHNESS_FILENAME).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 429 or tuple(rows[0]) != FRESHNESS_FIELDS:
        raise SystemExit(f"fresh v66 freshness shape differs: {len(rows)}")
    if any(
        row["status_semantics"] != "last_observed"
        or row["current_status_classification"] != "unknown"
        or row["current_construction_claim"] != "false"
        for row in rows
    ):
        raise SystemExit("v66 freshness rows infer current status")
    classes = Counter(row["freshness_class"] for row in rows)
    if classes != {
        "recent_0_90_days": 219,
        "aging_91_365_days": 183,
        "stale_over_365_days": 27,
    }:
        raise SystemExit(f"v66 freshness distribution differs: {classes}")
    as_of_date = date.fromisoformat(AS_OF)
    for row in rows:
        age = (as_of_date - date.fromisoformat(row["last_observed_status_as_of"])).days
        if row["observation_age_days"] != str(age):
            raise SystemExit("v66 freshness age differs")


def _validate_release_facts(stage: Path) -> None:
    summary = json.loads((stage / "summary.json").read_text(encoding="utf-8"))
    expected = {
        "campuses_total": 401,
        "campuses_with_coordinates": 127,
        "capacity_estimates_current": 512,
        "construction_pipeline_records": 387,
        "construction_source_signals": 292,
        "entities_total": 755,
        "entities_with_coordinates": 181,
        "evidence_total": 583,
        "lifecycle_observations_current": 429,
        "projects_total": 354,
        "recorded_at": RECORDED_AT,
    }
    actual = {key: summary.get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"fresh v66 summary facts differ: {actual}")
    base_summary = json.loads((BASE_RELEASE / "summary.json").read_text(encoding="utf-8"))
    if summary["entities_by_status"] != base_summary["entities_by_status"]:
        raise SystemExit("v66 changed lifecycle status observations")
    if summary["capacity_estimates_by_metric"] != base_summary[
        "capacity_estimates_by_metric"
    ] or summary["capacity_estimates_by_stage"] != base_summary[
        "capacity_estimates_by_stage"
    ]:
        raise SystemExit("v66 changed capacity classification")

    manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    expected_manifest = {
        "entities": 755,
        "evidence_records": 471,
        "capacity_estimates": 512,
        "construction_pipeline_records": 387,
        "construction_source_signals": 292,
        "resolution_candidates": 6,
        "lifecycle_freshness_records": 429,
        "lifecycle_status_semantics": "last_observed",
        "current_status_inferred": False,
    }
    actual_manifest = {key: manifest.get(key) for key in expected_manifest}
    if actual_manifest != expected_manifest:
        raise SystemExit(f"fresh v66 manifest facts differ: {actual_manifest}")
    base_manifest = json.loads(
        (BASE_RELEASE / "manifest.json").read_text(encoding="utf-8")
    )
    if set(manifest["source_families"]) - set(base_manifest["source_families"]) != (
        NEW_SOURCE_FAMILIES
    ):
        raise SystemExit("fresh v66 source-family delta differs")
    if set(base_manifest["source_families"]) - set(manifest["source_families"]):
        raise SystemExit("fresh v66 removed a source family")
    if len(manifest["source_families"]) != 260:
        raise SystemExit("fresh v66 source-family count differs")
    if len(list(stage.iterdir())) != 14:
        raise SystemExit("fresh v66 release must contain exactly 14 files")
    _validate_freshness(stage)


def _ordinary_file(path: Path, label: str) -> bytes:
    if not path.is_file() or path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"{label} must be an ordinary file")
    return path.read_bytes()


def _validate_definition(document: Mapping[str, Any], base: Mapping[str, Any]) -> None:
    if set(document) != set(base):
        raise ValueError("v66 definition schema differs from v65")
    if document.get("release_id") != RELEASE_ID:
        raise ValueError("release_id must identify frozen v66")
    if document.get("build") != {"as_of": AS_OF, "recorded_at": RECORDED_AT}:
        raise ValueError("v66 build timestamp contract differs")
    if document.get("publication_contract_version") != 4:
        raise ValueError("v66 publication contract differs")
    if document.get("freshness_contract") != freshness_contract():
        raise ValueError("v66 freshness contract differs")
    for key in ("epoch_capture", "expected_epoch_result", "schema_version", "scope"):
        if document.get(key) != base.get(key):
            raise ValueError(f"v66 inherited definition field differs: {key}")


def _guard_state() -> dict[str, Any]:
    source_hashes: dict[str, str] = {}
    for predecessor, (old_hash, successor, new_hash) in REPLACEMENT_PINS.items():
        source_hashes[predecessor] = sha256(ROOT / predecessor)
        source_hashes[successor] = sha256(ROOT / successor)
        if source_hashes[predecessor] != old_hash or source_hashes[successor] != new_hash:
            raise SystemExit("coordinate source pin differs")
    return {
        "base_definition": sha256(BASE_DEFINITION),
        "base_manifest": sha256(BASE_RELEASE / "manifest.json"),
        "base_tree": tree_digest(BASE_RELEASE),
        "sources": source_hashes,
    }


def validate_open_seed_v66(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
) -> dict[str, Any]:
    """Validate exact adjacency, frozen bytes, and deterministic offline replay."""

    if replay_count != 2:
        raise ValueError("v66 requires exactly two offline replays")
    guard = _guard_state()
    if guard != {
        "base_definition": BASE_DEFINITION_SHA256,
        "base_manifest": BASE_MANIFEST_SHA256,
        "base_tree": BASE_TREE_SHA256,
        "sources": guard["sources"],
    }:
        raise ValueError("accepted v65 base pin differs")
    base = json.loads(_ordinary_file(BASE_DEFINITION, "v65 definition"))
    raw = _ordinary_file(definition_path, "v66 definition")
    document = json.loads(raw)
    if raw != canonical_json(document):
        raise ValueError("v66 definition JSON is not canonical")
    _validate_definition(document, base)
    selected_rows, paths = selected_inputs(base)
    if document.get("curated_inputs") != selected_rows:
        raise ValueError("v66 selected input inventory differs")

    if not release_path.is_dir() or release_path.is_symlink():
        raise ValueError("v66 release must be an ordinary directory")
    if require_frozen and stat.S_IMODE(release_path.stat().st_mode) != 0o555:
        raise ValueError("v66 release directory mode must be 0555")
    release_files = {path.name: path for path in release_path.iterdir()}
    if any(path.is_symlink() or not path.is_file() for path in release_files.values()):
        raise ValueError("v66 release contains a symlink or non-file entry")
    if require_frozen and any(
        stat.S_IMODE(path.stat().st_mode) != 0o444 for path in release_files.values()
    ):
        raise ValueError("v66 release file mode must be 0444")

    manifest_raw = _ordinary_file(release_path / "manifest.json", "v66 manifest")
    manifest = json.loads(manifest_raw)
    if sha256(release_path / "manifest.json") != document["expected_release"].get(
        "manifest_sha256"
    ):
        raise ValueError("v66 release manifest hash differs")
    expected_release = {
        key: value for key, value in document["expected_release"].items()
        if key != "manifest_sha256"
    }
    actual_release = {key: value for key, value in manifest.items() if key != "files"}
    if actual_release != expected_release:
        raise ValueError("v66 expected release facts differ")
    expected_names = set(manifest["files"]) | {"manifest.json"}
    if set(release_files) != expected_names:
        raise ValueError("v66 release file inventory differs")
    for filename, pin in manifest["files"].items():
        payload = _ordinary_file(release_path / filename, filename)
        if len(payload) != pin["bytes"] or hashlib.sha256(payload).hexdigest() != pin[
            "sha256"
        ]:
            raise ValueError(f"v66 release file pin differs: {filename}")
    _validate_release_delta(release_path)
    _validate_release_facts(release_path)

    summary = json.loads((release_path / "summary.json").read_text(encoding="utf-8"))
    if {
        key: summary[key] for key in document["expected_summary"]
    } != document["expected_summary"]:
        raise ValueError("v66 expected summary differs")

    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v66-replay-{replay + 1}-", dir="/private/tmp"
        ) as temporary:
            temporary_path = Path(temporary)
            connection = _build_database(
                base, paths, temporary_path / "atlas.sqlite"
            )
            try:
                replay_release = temporary_path / "release"
                _write_augmented_release(connection, replay_release)
            finally:
                connection.close()
            _validate_release_delta(replay_release)
            _validate_release_facts(replay_release)
            if {path.name for path in replay_release.iterdir()} != set(release_files):
                raise ValueError("v66 replay file inventory differs")
            for filename, frozen in release_files.items():
                if (replay_release / filename).read_bytes() != frozen.read_bytes():
                    raise ValueError(f"v66 offline replay differs: {filename}")
    if _guard_state() != guard:
        raise ValueError("v66 validation mutated a frozen predecessor or source")
    return manifest


def build_open_seed_v66() -> dict[str, object]:
    """Build and freeze v66 exactly once, refusing every publication collision."""

    guard = _guard_state()
    with publication_lock():
        if DEFINITION.exists() or DEFINITION.is_symlink():
            raise SystemExit(
                f"definition already exists; refusing overwrite: {DEFINITION}"
            )
        if RELEASE.exists() or RELEASE.is_symlink():
            raise SystemExit(f"release already exists; refusing overwrite: {RELEASE}")
        if guard["base_definition"] != BASE_DEFINITION_SHA256:
            raise SystemExit("accepted v65 definition hash differs")
        if guard["base_manifest"] != BASE_MANIFEST_SHA256:
            raise SystemExit("accepted v65 manifest hash differs")
        if guard["base_tree"] != BASE_TREE_SHA256:
            raise SystemExit("accepted v65 release tree differs")

        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        input_rows, paths = selected_inputs(base)
        staging_root = ROOT / ".staging"
        staging_root.mkdir(exist_ok=True)
        release_stage = Path(
            tempfile.mkdtemp(prefix=f".{RELEASE.name}.", dir=RELEASE.parent)
        )
        release_stage.rmdir()
        definition_stage = DEFINITION.parent / f".{DEFINITION.name}.{os.getpid()}.tmp"
        published_release = False
        try:
            with tempfile.TemporaryDirectory(
                prefix="open-seed-v66-db-", dir=staging_root
            ) as temporary:
                connection = _build_database(
                    base, paths, Path(temporary) / "atlas.sqlite"
                )
                try:
                    _write_augmented_release(connection, release_stage)
                    summary = summarize(
                        connection, as_of=AS_OF, recorded_at=RECORDED_AT
                    )
                finally:
                    connection.close()

            _validate_release_delta(release_stage)
            _validate_release_facts(release_stage)
            manifest_raw = (release_stage / "manifest.json").read_bytes()
            manifest = json.loads(manifest_raw)
            expected_release = {
                key: value for key, value in manifest.items() if key != "files"
            }
            expected_release["manifest_sha256"] = hashlib.sha256(
                manifest_raw
            ).hexdigest()
            expected_summary = {key: summary[key] for key in base["expected_summary"]}
            definition = dict(base)
            definition["build"] = {"as_of": AS_OF, "recorded_at": RECORDED_AT}
            definition["curated_inputs"] = input_rows
            definition["expected_release"] = expected_release
            definition["expected_summary"] = expected_summary
            definition["freshness_contract"] = freshness_contract()
            definition["publication_contract_version"] = 4
            definition["release_id"] = RELEASE.name
            with definition_stage.open("xb") as stream:
                stream.write(canonical_json(definition))
                stream.flush()
                os.fsync(stream.fileno())
            definition_stage.chmod(0o644)

            for output in release_stage.iterdir():
                output.chmod(0o444)
            release_stage.chmod(0o555)
            validate_open_seed_v66(definition_stage, release_stage)
            promote_noreplace(release_stage, RELEASE)
            published_release = True
            promote_noreplace(definition_stage, DEFINITION)
            validate_open_seed_v66(DEFINITION, RELEASE)
        finally:
            if not published_release:
                discard_release_stage(release_stage)
            try:
                definition_stage.unlink()
            except FileNotFoundError:
                pass
    if _guard_state() != guard:
        raise SystemExit("v66 build mutated a frozen predecessor or source")

    manifest = json.loads((RELEASE / "manifest.json").read_text(encoding="utf-8"))
    return {
        "definition": str(DEFINITION),
        "definition_sha256": sha256(DEFINITION),
        "manifest_sha256": sha256(RELEASE / "manifest.json"),
        "recorded_at": RECORDED_AT,
        "release": str(RELEASE),
        "release_tree_sha256": tree_digest(RELEASE),
        **{
            key: value
            for key, value in manifest.items()
            if key not in {"files", "source_families"}
        },
        "source_families": len(manifest["source_families"]),
    }


def main() -> int:
    print(json.dumps(build_open_seed_v66(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
