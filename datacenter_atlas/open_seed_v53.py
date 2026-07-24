"""Build the collision-isolated official open seed v53 exactly once.

V53 derives only from the independently accepted frozen v52 definition and
release. It replaces four curated source records with accepted coordinate-
provenance successors, preserves every other input row, and changes only seven
current entity coordinates. The release remains source scoped and makes no
completeness, parity, or unique-physical-site claim.
"""

from __future__ import annotations

from contextlib import contextmanager
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
from typing import Iterator, Mapping, Sequence

from .curated import CuratedOfficialSourceAdapter
from .database import initialize
from .epoch import EpochAIAdapter
from .open_seed_release import validate_open_seed_release
from .open_seed_v52 import (
    canonical_json,
    discard_release_stage,
    promote_noreplace,
    sha256,
)
from .publication_release import write_release
from .service import summarize, validate_database


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v52.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v52"
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v53.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v53"
PUBLICATION_LOCK = ROOT / ".open-seed-v53.lock"

BASE_DEFINITION_SHA256 = (
    "95dcf883c9a9b8d37ad50e30f01668303d0ea55bc7199d7dcf827d2daea7a75f"
)
BASE_MANIFEST_SHA256 = (
    "c4e7edee4fbd37959f5c9eb080c416aa9ec3e2489e231795bd85f52a60be27cb"
)
BASE_TREE_SHA256 = "ae5df8cf0d9d6367db58ced1e1d66a66fe7b1b4e3caef05706248d8a286efed5"
RECORDED_AT = "2026-07-20T19:33:00Z"
MAX_SELECTED_RETRIEVED_AT = "2026-07-20T17:35:25Z"
MAX_COORDINATE_PROVENANCE_AT = "2026-07-20T18:20:10Z"

REPLACEMENTS = {
    "sources/curated-official-2026-07-19-data4-ath1-first-data-center.json": (
        "sources/curated-official-2026-07-19-data4-ath1-first-data-center-v2.json",
        "f5945a8c0b0c290bea1251d3514986c9d6fefc96ccc6f784ed23c703646f046a",
    ),
    "sources/curated-official-2026-07-19-digital-realty-fra20-frankfurt.json": (
        "sources/curated-official-2026-07-19-digital-realty-fra20-frankfurt-v2.json",
        "d50982f91d6bb3e9f69a555ceb61d7885ac4c463fd806c9daf5dbedc2edb8197",
    ),
    "sources/curated-official-2026-07-19-digital-realty-rom1-rome.json": (
        "sources/curated-official-2026-07-19-digital-realty-rom1-rome-v2.json",
        "f11d6fad3f51d5e5df8c2f667a9c4d600de7df94df5f5442a4201d44655c5120",
    ),
    "sources/curated-official-2026-07-20-vantage-zrh12-winterthur-topout.json": (
        "sources/curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v5.json",
        "45b8ba2a95b743fbff19df93ce4cb9b846d92aa347360bfd0606dd32d1fc90d8",
    ),
}

REJECTED_PROVISIONAL_INPUTS = frozenset(
    {
        "sources/curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v2.json",
        "sources/curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v3.json",
        "sources/curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v4.json",
        "sources/curated-official-2026-07-20-edged-atl01-3-atlanta-topout-v2.json",
        "sources/curated-official-2026-07-20-edged-ord01-2-chicago-topout-v2.json",
    }
)

EXPECTED_COORDINATES = {
    "curated:data4-ath1-paiania-campus": (37.9429028, 23.8735719),
    "curated:data4-ath1-paiania-campus:first-data-center": (
        37.9429028,
        23.8735719,
    ),
    "curated:digital-realty-fra20-frankfurt": (50.125936, 8.752816),
    "curated:digital-realty-fra20-frankfurt:current-facility-build": (
        50.125936,
        8.752816,
    ),
    "curated:digital-realty-rom1-rome": (41.776044, 12.48923),
    "curated:digital-realty-rom1-rome:current-facility-build": (
        41.776044,
        12.48923,
    ),
    "curated:vantage-zrh1-winterthur-campus": (47.5020821, 8.7713397),
}

EXPECTED_RELEASE_FACTS = {
    "capacity_estimates": 476,
    "construction_pipeline_records": 336,
    "construction_source_signals": 244,
    "entities": 647,
    "entities_by_kind": {"campus": 349, "project": 298},
    "evidence_records": 369,
    "resolution_candidates": 4,
}

EXPECTED_SUMMARY = {
    "campuses_total": 349,
    "campuses_with_coordinates": 110,
    "capacity_estimates_current": 476,
    "construction_pipeline_records": 336,
    "construction_source_signals": 244,
    "entities_by_status": {
        "announced": 6,
        "civil_works": 2,
        "commissioning": 1,
        "expansion": 27,
        "foundations": 2,
        "mep_electrical": 19,
        "operational": 35,
        "permitted": 3,
        "proposed": 2,
        "shell": 23,
        "site_preparation": 12,
        "under_construction": 239,
    },
    "entities_total": 647,
    "entities_with_coordinates": 150,
    "evidence_total": 435,
    "lifecycle_observations_current": 371,
    "projects_total": 298,
    "recorded_at": RECORDED_AT,
}

EXPECTED_DATABASE_SOURCE_FAMILIES = 221
EXPECTED_RELEASE_SOURCE_FAMILIES = 190


def tree_digest(root: Path) -> str:
    """Hash release paths, modes, sizes, and bytes without following symlinks."""

    digest = hashlib.sha256()
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise SystemExit(f"release tree contains symlink: {relative}")
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode("utf-8"))
        elif path.is_file():
            raw = path.read_bytes()
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{hashlib.sha256(raw).hexdigest()}\n"
                ).encode("utf-8")
            )
        else:
            raise SystemExit(f"release tree contains unsupported entry: {relative}")
    return digest.hexdigest()


def validate_temporal_contract(
    retrieved_at: Sequence[str],
    coordinate_provenance_at: Sequence[str],
    *,
    build_started_at: datetime | None = None,
) -> None:
    """Require fixed timestamps after every source and before the build."""

    if not retrieved_at:
        raise SystemExit("selected retrieval inventory is empty")
    if max(retrieved_at) != MAX_SELECTED_RETRIEVED_AT:
        raise SystemExit(
            "selected retrieval maximum differs: "
            f"{max(retrieved_at)} != {MAX_SELECTED_RETRIEVED_AT}"
        )
    if not coordinate_provenance_at:
        raise SystemExit("coordinate-provenance timestamp inventory is empty")
    if max(coordinate_provenance_at) != MAX_COORDINATE_PROVENANCE_AT:
        raise SystemExit(
            "coordinate-provenance maximum differs: "
            f"{max(coordinate_provenance_at)} != {MAX_COORDINATE_PROVENANCE_AT}"
        )
    cutoff = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
    parsed_inputs = [
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        for value in [*retrieved_at, *coordinate_provenance_at]
    ]
    if not all(value < cutoff for value in parsed_inputs):
        raise SystemExit(
            "recorded_at must be strictly after every selected source time"
        )
    observed_clock = build_started_at or datetime.now(timezone.utc)
    if observed_clock.tzinfo is None:
        raise SystemExit("build-start clock must be timezone-aware")
    if observed_clock.astimezone(timezone.utc) < cutoff:
        raise SystemExit("recorded_at must be at or before the build-start clock")


@contextmanager
def publication_lock() -> Iterator[None]:
    """Hold an exclusive v53 publication lock without replacing any file."""

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


def _validate_base_definition(base: Mapping[str, object]) -> None:
    """Prove that accepted v52, and no rejected seed, is the lineage root."""

    accepted_definition = ROOT / "sources/open-seed-2026-07-20-v52.json"
    accepted_release = ROOT / "releases/2026-07-20-open-seed-v52"
    if BASE_DEFINITION != accepted_definition or BASE_RELEASE != accepted_release:
        raise SystemExit("v53 base paths must select exactly accepted v52")
    if base.get("release_id") != "2026-07-20-open-seed-v52":
        raise SystemExit("accepted seed base must be exactly v52")
    build = base.get("build")
    if (
        not isinstance(build, dict)
        or build.get("recorded_at") != "2026-07-20T18:11:00Z"
    ):
        raise SystemExit("accepted v52 build metadata differs")
    expected = base.get("expected_release")
    if not isinstance(expected, dict):
        raise SystemExit("accepted v52 release contract is invalid")
    if expected.get("manifest_sha256") != BASE_MANIFEST_SHA256:
        raise SystemExit("accepted v52 manifest lineage differs")


def _coordinate_capture_times(document: Mapping[str, object]) -> list[str]:
    """Return explicit later coordinate-capture timestamps from evidence metadata."""

    timestamps: list[str] = []
    evidence = document.get("evidence")
    if not isinstance(evidence, list):
        raise SystemExit("curated input evidence inventory is invalid")
    for record in evidence:
        if not isinstance(record, dict):
            raise SystemExit("curated input evidence record is invalid")
        metadata = record.get("metadata")
        if not isinstance(metadata, dict):
            continue
        value = metadata.get("coordinate_capture_retrieved_at")
        if value is not None:
            if not isinstance(value, str):
                raise SystemExit("coordinate capture timestamp is invalid")
            timestamps.append(value)
    return timestamps


def selected_inputs(
    base: Mapping[str, object],
) -> tuple[list[dict[str, str]], list[Path]]:
    """Replace exactly four v52 rows while preserving the other 302 rows."""

    _validate_base_definition(base)
    raw_base_rows = base.get("curated_inputs")
    if not isinstance(raw_base_rows, list):
        raise SystemExit("accepted v52 curated input inventory is invalid")
    base_rows: list[dict[str, str]] = []
    base_pins: dict[str, str] = {}
    for row in raw_base_rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise SystemExit("accepted v52 curated input row is invalid")
        relative = row.get("path")
        digest = row.get("sha256")
        if not isinstance(relative, str) or not isinstance(digest, str):
            raise SystemExit("accepted v52 curated input pin is invalid")
        if relative in base_pins:
            raise SystemExit(f"duplicate accepted v52 input: {relative}")
        base_pins[relative] = digest
        base_rows.append({"path": relative, "sha256": digest})
    if len(base_rows) != 306:
        raise SystemExit(f"expected 306 unique v52 inputs, found {len(base_rows)}")
    if set(REPLACEMENTS) - set(base_pins):
        raise SystemExit("one or more v53 replacement origins is absent from v52")

    rows = []
    for row in base_rows:
        replacement = REPLACEMENTS.get(row["path"])
        if replacement is None:
            rows.append(dict(row))
        else:
            rows.append({"path": replacement[0], "sha256": replacement[1]})
    pins = {row["path"]: row["sha256"] for row in rows}
    replacement_paths = {new_path for new_path, _ in REPLACEMENTS.values()}
    if len(rows) != 306 or len(pins) != 306:
        raise SystemExit(f"expected 306 unique v53 inputs, found {len(pins)}")
    if rows != sorted(rows, key=lambda row: row["path"]):
        raise SystemExit("v53 input inventory is not in deterministic path order")
    inherited = [row for row in rows if row["path"] not in replacement_paths]
    expected_inherited = [row for row in base_rows if row["path"] not in REPLACEMENTS]
    if inherited != expected_inherited or len(inherited) != 302:
        raise SystemExit("one or more inherited v52 input rows changed or reordered")
    if set(pins) & set(REPLACEMENTS):
        raise SystemExit("one or more superseded v52 inputs remains selected")
    if set(pins) & REJECTED_PROVISIONAL_INPUTS:
        raise SystemExit("a rejected provisional coordinate input is selected")
    if {path: pins[path] for path in replacement_paths} != {
        path: digest for path, digest in REPLACEMENTS.values()
    }:
        raise SystemExit("v53 replacement inventory changed")

    epoch = base.get("epoch_capture")
    if not isinstance(epoch, dict) or not isinstance(epoch.get("retrieved_at"), str):
        raise SystemExit("accepted v52 Epoch capture metadata is invalid")
    retrieved_at = [epoch["retrieved_at"]]
    coordinate_provenance_at: list[str] = []
    curated_paths: list[Path] = []
    for row in rows:
        relative = row["path"]
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"input must be an ordinary file: {relative}")
        if stat.S_IMODE(path.stat().st_mode) != 0o644:
            raise SystemExit(f"input mode must be 0644: {relative}")
        if sha256(path) != row["sha256"]:
            raise SystemExit(f"input hash differs: {relative}")
        document = json.loads(path.read_text(encoding="utf-8"))
        timestamps = {item["retrieved_at"] for item in document.get("evidence", [])}
        if len(timestamps) != 1:
            raise SystemExit(f"input must use one evidence retrieved_at: {relative}")
        capture_times = _coordinate_capture_times(document)
        has_coordinate_capture = bool(capture_times)
        if has_coordinate_capture and relative not in replacement_paths:
            raise SystemExit(f"unapproved provisional coordinate source: {relative}")
        if relative in replacement_paths and relative.endswith("-v5.json"):
            if capture_times:
                raise SystemExit(
                    "accepted Vantage v5 must use its retained evidence body"
                )
        elif relative in replacement_paths and not capture_times:
            raise SystemExit(
                f"accepted coordinate successor lacks capture time: {relative}"
            )
        retrieved_at.extend(timestamps)
        coordinate_provenance_at.extend(capture_times)
        curated_paths.append(path)
    validate_temporal_contract(retrieved_at, coordinate_provenance_at)
    return rows, curated_paths


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _rows_by_key(path: Path, key: str) -> dict[str, dict[str, str]]:
    records = _csv_rows(path)
    result = {row[key]: row for row in records}
    if len(result) != len(records):
        raise SystemExit(f"duplicate {key} in {path.name}")
    return result


def _validate_coordinate_rows(
    base_path: Path,
    current_path: Path,
    *,
    key: str,
    latitude_field: str,
    longitude_field: str,
    expected_keys: set[str],
) -> None:
    """Require exact row restoration after blanking only coordinate columns."""

    before = _rows_by_key(base_path, key)
    after = _rows_by_key(current_path, key)
    if set(before) != set(after):
        raise SystemExit(f"{current_path.name} identity set changed")
    changed = {row_key for row_key in before if before[row_key] != after[row_key]}
    if changed != expected_keys:
        raise SystemExit(
            f"{current_path.name} changed row set differs: {sorted(changed)}"
        )
    for row_key in expected_keys:
        restored = dict(after[row_key])
        restored[latitude_field] = before[row_key][latitude_field]
        restored[longitude_field] = before[row_key][longitude_field]
        if "geometry_json" in restored:
            restored["geometry_json"] = before[row_key]["geometry_json"]
        if restored != before[row_key]:
            raise SystemExit(
                f"{current_path.name} changed non-coordinate semantics: {row_key}"
            )


def _validate_geojson_delta(release_stage: Path) -> None:
    """Require exactly seven null-to-point geometry changes and no property drift."""

    before_document = json.loads((BASE_RELEASE / "atlas.geojson").read_text())
    after_document = json.loads((release_stage / "atlas.geojson").read_text())
    if set(before_document) != set(after_document):
        raise SystemExit("atlas GeoJSON top-level schema changed")
    before_features = {
        feature["properties"]["stable_key"]: feature
        for feature in before_document["features"]
    }
    after_features = {
        feature["properties"]["stable_key"]: feature
        for feature in after_document["features"]
    }
    if set(before_features) != set(after_features):
        raise SystemExit("atlas GeoJSON identity set changed")
    changed = {
        stable_key
        for stable_key in before_features
        if before_features[stable_key] != after_features[stable_key]
    }
    if changed != set(EXPECTED_COORDINATES):
        raise SystemExit(
            f"atlas GeoJSON changed feature set differs: {sorted(changed)}"
        )
    for stable_key, (latitude, longitude) in EXPECTED_COORDINATES.items():
        before = before_features[stable_key]
        after = after_features[stable_key]
        if before["geometry"] is not None:
            raise SystemExit(f"v52 geometry was unexpectedly populated: {stable_key}")
        if after["geometry"] != {
            "coordinates": [longitude, latitude],
            "type": "Point",
        }:
            raise SystemExit(f"v53 point geometry differs: {stable_key}")
        restored_properties = dict(after["properties"])
        restored_properties["latitude"] = before["properties"]["latitude"]
        restored_properties["longitude"] = before["properties"]["longitude"]
        if before["properties"] != restored_properties:
            raise SystemExit(f"atlas GeoJSON properties changed: {stable_key}")


def _validate_coordinate_only_delta(
    connection: sqlite3.Connection,
    release_stage: Path,
) -> None:
    """Prove counts, evidence, identities, statuses, and metrics match v52."""

    evidence_count = connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
    if evidence_count != 435:
        raise SystemExit(f"fresh database evidence count differs: {evidence_count}")
    family_count = connection.execute(
        "SELECT COUNT(DISTINCT source_family) FROM evidence"
    ).fetchone()[0]
    if family_count != EXPECTED_DATABASE_SOURCE_FAMILIES:
        raise SystemExit(f"fresh database source-family count differs: {family_count}")

    for filename in (
        "capacity_estimates.csv",
        "evidence.csv",
        "resolution_candidates.csv",
        "resolution_candidates.json",
    ):
        if (BASE_RELEASE / filename).read_bytes() != (
            release_stage / filename
        ).read_bytes():
            raise SystemExit(f"coordinate successor changed frozen {filename}")

    _validate_coordinate_rows(
        BASE_RELEASE / "entities.csv",
        release_stage / "entities.csv",
        key="stable_key",
        latitude_field="latitude",
        longitude_field="longitude",
        expected_keys=set(EXPECTED_COORDINATES),
    )
    pipeline_keys = {
        "curated:data4-ath1-paiania-campus:first-data-center",
        "curated:digital-realty-fra20-frankfurt:current-facility-build",
        "curated:digital-realty-rom1-rome:current-facility-build",
    }
    _validate_coordinate_rows(
        BASE_RELEASE / "construction_pipeline.csv",
        release_stage / "construction_pipeline.csv",
        key="stable_key",
        latitude_field="latitude",
        longitude_field="longitude",
        expected_keys=pipeline_keys,
    )
    _validate_coordinate_rows(
        BASE_RELEASE / "construction_source_signals.csv",
        release_stage / "construction_source_signals.csv",
        key="source_observation_evidence_id",
        latitude_field="representative_latitude",
        longitude_field="representative_longitude",
        expected_keys={
            "574037df-3663-58ff-ad75-72635006e6e6",
            "24a2ee72-4b00-5bf8-860a-089f2f970edd",
            "f663d571-a87f-5869-8477-d3f3de680d49",
        },
    )
    entity_rows = _rows_by_key(release_stage / "entities.csv", "stable_key")
    for stable_key, (latitude, longitude) in EXPECTED_COORDINATES.items():
        row = entity_rows[stable_key]
        if (float(row["latitude"]), float(row["longitude"])) != (
            latitude,
            longitude,
        ):
            raise SystemExit(f"accepted coordinate differs: {stable_key}")
    _validate_geojson_delta(release_stage)

    base_summary = json.loads((BASE_RELEASE / "summary.json").read_text())
    published_summary = json.loads((release_stage / "summary.json").read_text())
    allowed_summary_changes = {
        "campuses_with_coordinates",
        "entities_with_coordinates",
        "recorded_at",
    }
    restored_summary = dict(published_summary)
    for key in allowed_summary_changes:
        restored_summary[key] = base_summary[key]
    if restored_summary != base_summary:
        raise SystemExit("fresh summary changed beyond coordinates and recorded_at")
    actual_summary = {key: published_summary.get(key) for key in EXPECTED_SUMMARY}
    if actual_summary != EXPECTED_SUMMARY:
        raise SystemExit(
            "fresh coordinate summary differs:\n"
            + json.dumps(
                {"actual": actual_summary, "expected": EXPECTED_SUMMARY},
                indent=2,
                sort_keys=True,
            )
        )


def build_open_seed_v53() -> dict[str, object]:
    """Build and freeze v53 once, refusing every publication collision."""

    with publication_lock():
        if DEFINITION.exists() or DEFINITION.is_symlink():
            raise SystemExit(
                f"definition already exists; refusing to overwrite: {DEFINITION}"
            )
        if RELEASE.exists() or RELEASE.is_symlink():
            raise SystemExit(
                f"release already exists; refusing to overwrite: {RELEASE}"
            )
        if sha256(BASE_DEFINITION) != BASE_DEFINITION_SHA256:
            raise SystemExit("accepted v52 definition hash differs")
        if sha256(BASE_RELEASE / "manifest.json") != BASE_MANIFEST_SHA256:
            raise SystemExit("accepted v52 manifest hash differs")
        if tree_digest(BASE_RELEASE) != BASE_TREE_SHA256:
            raise SystemExit("accepted v52 release tree differs")

        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        input_rows, curated_paths = selected_inputs(base)

        staging_root = ROOT / ".staging"
        staging_root.mkdir(exist_ok=True)
        release_stage = Path(
            tempfile.mkdtemp(prefix=f".{RELEASE.name}.", dir=RELEASE.parent)
        )
        definition_stage = DEFINITION.parent / (f".{DEFINITION.name}.{os.getpid()}.tmp")
        published_release = False
        try:
            with tempfile.TemporaryDirectory(
                prefix="open-seed-v53-db-", dir=staging_root
            ) as temporary:
                temporary_root = Path(temporary)
                connection, _ = initialize(temporary_root / "atlas.sqlite")
                try:
                    epoch = base["epoch_capture"]
                    epoch_result = EpochAIAdapter().import_file(
                        connection,
                        ROOT / epoch["archive"],
                        map_html=ROOT / epoch["map"],
                        retrieved_at=epoch["retrieved_at"],
                        as_of_date="2026-07-20",
                    )
                    normalized_epoch = json.loads(json.dumps(asdict(epoch_result)))
                    if normalized_epoch != base["expected_epoch_result"]:
                        raise SystemExit("fresh Epoch import result differs from v52")
                    for path in curated_paths:
                        document = json.loads(path.read_text(encoding="utf-8"))
                        timestamp = {
                            row["retrieved_at"] for row in document["evidence"]
                        }.pop()
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection, path, retrieved_at=timestamp
                        )
                        if result.warnings:
                            raise SystemExit(
                                f"curated import warnings for {path.name}: "
                                f"{result.warnings}"
                            )
                    errors = validate_database(connection)
                    if errors:
                        raise SystemExit(
                            "fresh database validation failed: " + "; ".join(errors)
                        )
                    write_release(
                        connection,
                        release_stage,
                        as_of="2026-07-20",
                        recorded_at=RECORDED_AT,
                        publication_contract_version=4,
                    )
                    summary = summarize(
                        connection,
                        as_of="2026-07-20",
                        recorded_at=RECORDED_AT,
                    )
                    _validate_coordinate_only_delta(connection, release_stage)
                    if "source_families" in summary:
                        raise SystemExit(
                            "summary unexpectedly mixes in a source-family count"
                        )
                finally:
                    connection.close()

            manifest_path = release_stage / "manifest.json"
            manifest_raw = manifest_path.read_bytes()
            manifest = json.loads(manifest_raw)
            actual = {key: manifest[key] for key in EXPECTED_RELEASE_FACTS}
            if actual != EXPECTED_RELEASE_FACTS:
                raise SystemExit(
                    "fresh release projection differs; refusing to publish:\n"
                    + json.dumps(
                        {"actual": actual, "expected": EXPECTED_RELEASE_FACTS},
                        indent=2,
                        sort_keys=True,
                    )
                )
            if len(manifest["source_families"]) != EXPECTED_RELEASE_SOURCE_FAMILIES:
                raise SystemExit(
                    "fresh release source-family count differs from "
                    f"{EXPECTED_RELEASE_SOURCE_FAMILIES}"
                )
            if len(list(release_stage.iterdir())) != 13:
                raise SystemExit("fresh release must contain exactly 13 files")

            expected_release = {
                key: value for key, value in manifest.items() if key != "files"
            }
            expected_release["manifest_sha256"] = hashlib.sha256(
                manifest_raw
            ).hexdigest()
            definition = dict(base)
            definition["build"] = {
                "as_of": "2026-07-20",
                "recorded_at": RECORDED_AT,
            }
            definition["curated_inputs"] = input_rows
            definition["expected_release"] = expected_release
            definition["expected_summary"] = EXPECTED_SUMMARY
            definition["release_id"] = RELEASE.name
            with definition_stage.open("xb") as stream:
                stream.write(canonical_json(definition))
                stream.flush()
                os.fsync(stream.fileno())
            definition_stage.chmod(0o644)

            for path in release_stage.iterdir():
                path.chmod(0o444)
            release_stage.chmod(0o555)
            validate_open_seed_release(definition_stage, release_stage)
            promote_noreplace(release_stage, RELEASE)
            published_release = True
            promote_noreplace(definition_stage, DEFINITION)
            validate_open_seed_release(DEFINITION, RELEASE)
        finally:
            if not published_release:
                discard_release_stage(release_stage)
            try:
                definition_stage.unlink()
            except FileNotFoundError:
                pass

    return {
        "definition": str(DEFINITION),
        "definition_sha256": sha256(DEFINITION),
        "manifest_sha256": sha256(RELEASE / "manifest.json"),
        "recorded_at": RECORDED_AT,
        "release": str(RELEASE),
        **EXPECTED_RELEASE_FACTS,
        "database_source_families": EXPECTED_DATABASE_SOURCE_FAMILIES,
        "entities_with_coordinates": EXPECTED_SUMMARY["entities_with_coordinates"],
        "source_families": EXPECTED_RELEASE_SOURCE_FAMILIES,
    }


def main() -> int:
    """Build v53 and print the frozen release facts."""

    print(json.dumps(build_open_seed_v53(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
