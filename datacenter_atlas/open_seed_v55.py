"""Build the collision-isolated official open seed v55 exactly once.

V55 derives only from the independently accepted frozen v54 definition and
release. It preserves all 314 inherited input-pin rows and their relative order
while inserting two accepted official-source records into deterministic path
order. The release is source scoped and makes no completeness, parity, or
unique-physical-site claim.
"""

from __future__ import annotations

from collections import Counter
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
from .open_seed_v54 import (
    canonical_json,
    discard_release_stage,
    promote_noreplace,
    sha256,
    tree_digest,
)
from .publication_release import write_release
from .service import summarize, validate_database


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v54.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v54"
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v55.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v55"
PUBLICATION_LOCK = ROOT / ".open-seed-v55.lock"

BASE_DEFINITION_SHA256 = (
    "1510c2abcf24c90be1de69c11878ad7075a495ddeff53859a7525a4e6c6778a5"
)
BASE_MANIFEST_SHA256 = (
    "ae3d6229d7a78e41d7df1e9d6424a45da3ee9ce41d109d8dee426f557e03db11"
)
BASE_TREE_SHA256 = "6a48e0caf8b2a0d6542005b25cf196d1e96a29b1cb44a37af8a9dde0c18c75d5"
RECORDED_AT = "2026-07-20T20:05:00Z"
MAX_SELECTED_RETRIEVED_AT = "2026-07-20T20:01:06Z"

ADDITIONS = {
    "sources/curated-official-2026-07-20-digital-edge-bgrimm-chonburi-eec.json": (
        "c31ecbe7fb4b8e47de2683c0b321d5dd3e59dda1fbf596218ceab0ef7e191f94"
    ),
    "sources/curated-official-2026-07-20-google-kronstorf-austria.json": (
        "763f11edfea3ce7ff7ec76093716d732a92a906562a3b7f3d17c3b08fa3a4e21"
    ),
}

REJECTED_PROVISIONAL_INPUTS = frozenset(
    {
        "sources/curated-official-2026-07-20-databank-red-oak-dfw10.json",
        "sources/curated-official-2026-07-20-databank-red-oak-dfw11.json",
    }
)

EXPECTED_ADDITION_POSITIONS = {
    "sources/curated-official-2026-07-20-digital-edge-bgrimm-chonburi-eec.json": 190,
    "sources/curated-official-2026-07-20-google-kronstorf-austria.json": 251,
}

EXPECTED_IMPORT_RESULTS = {
    "sources/curated-official-2026-07-20-digital-edge-bgrimm-chonburi-eec.json": (
        2,
        1,
    ),
    "sources/curated-official-2026-07-20-google-kronstorf-austria.json": (2, 1),
}

ADDED_EVIDENCE = {
    "digital-edge-bgrimm-chonburi-eec-groundbreaking-2025-09-04-captured-2026-07-20": (
        "449843d800a5ba175833634054b308369afdae02ea19ead284893f2152e6e7a9",
        "digital_edge_newsroom",
        (2, 1, 1, 0, 0, 0),
    ),
    "google-kronstorf-groundbreaking-2026-04-23-captured-2026-07-20": (
        "fa9fb59cdd774842321c98f471f4b6eb70df6ab47dd4d1adb23c63bf062bed08",
        "google_cloud_press_corner",
        (2, 1, 0, 0, 0, 0),
    ),
}

ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:digital-edge-bgrimm-chonburi-eec-data-center-campus",
        "curated:digital-edge-bgrimm-chonburi-eec-data-center-campus:current-development",
        "curated:google-kronstorf-austria-data-center-campus",
        "curated:google-kronstorf-austria-data-center-campus:current-development",
    }
)

EXPECTED_RELEASE_FACTS = {
    "capacity_estimates": 482,
    "construction_pipeline_records": 346,
    "construction_source_signals": 252,
    "entities": 663,
    "entities_by_kind": {"campus": 357, "project": 306},
    "evidence_records": 383,
    "resolution_candidates": 4,
}

EXPECTED_SUMMARY = {
    "campuses_total": 357,
    "campuses_with_coordinates": 110,
    "capacity_estimates_by_stage": {
        "contracted": 16,
        "design": 6,
        "forecast": 135,
        "operational": 170,
        "planned": 119,
        "unknown": 36,
    },
    "capacity_estimates_current": 482,
    "construction_pipeline_records": 346,
    "construction_source_signals": 252,
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
        "under_construction": 249,
    },
    "entities_total": 663,
    "entities_with_coordinates": 150,
    "evidence_total": 454,
    "lifecycle_observations_current": 381,
    "projects_total": 306,
    "recorded_at": RECORDED_AT,
}

BASE_DATABASE_SOURCE_FAMILIES = 235
INCOMING_DATABASE_SOURCE_FAMILIES = 2
EXPECTED_DATABASE_SOURCE_FAMILIES = 237
BASE_RELEASE_SOURCE_FAMILIES = 199
INCOMING_RELEASE_SOURCE_FAMILIES = 2
EXPECTED_RELEASE_SOURCE_FAMILIES = 201

CSV_ADDITIVE_COUNTS = {
    "entities.csv": (659, 4),
    "evidence.csv": (381, 2),
    "capacity_estimates.csv": (482, 0),
    "construction_pipeline.csv": (344, 2),
    "construction_source_signals.csv": (250, 2),
    "resolution_candidates.csv": (4, 0),
}


def validate_temporal_contract(
    retrieved_at: Sequence[str],
    *,
    build_started_at: datetime | None = None,
) -> None:
    """Require a fixed recorded time after inputs and not after the build."""

    if not retrieved_at:
        raise SystemExit("selected retrieval inventory is empty")
    if max(retrieved_at) != MAX_SELECTED_RETRIEVED_AT:
        raise SystemExit(
            "selected retrieval maximum differs: "
            f"{max(retrieved_at)} != {MAX_SELECTED_RETRIEVED_AT}"
        )
    cutoff = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
    parsed_retrievals = [
        datetime.fromisoformat(value.replace("Z", "+00:00")) for value in retrieved_at
    ]
    if not all(value < cutoff for value in parsed_retrievals):
        raise SystemExit("recorded_at must be strictly after every selected retrieval")
    observed_clock = build_started_at or datetime.now(timezone.utc)
    if observed_clock.tzinfo is None:
        raise SystemExit("build-start clock must be timezone-aware")
    if observed_clock.astimezone(timezone.utc) < cutoff:
        raise SystemExit("recorded_at must be at or before the build-start clock")


@contextmanager
def publication_lock() -> Iterator[None]:
    """Hold an exclusive v55 publication lock without replacing any file."""

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
    """Prove that accepted v54 is the sole seed-lineage root."""

    accepted_definition = ROOT / "sources/open-seed-2026-07-20-v54.json"
    accepted_release = ROOT / "releases/2026-07-20-open-seed-v54"
    if BASE_DEFINITION != accepted_definition or BASE_RELEASE != accepted_release:
        raise SystemExit("v55 base paths must select exactly accepted v54")
    if base.get("release_id") != "2026-07-20-open-seed-v54":
        raise SystemExit("accepted seed base must be exactly v54")
    build = base.get("build")
    if (
        not isinstance(build, dict)
        or build.get("recorded_at") != "2026-07-20T19:56:00Z"
    ):
        raise SystemExit("accepted v54 build metadata differs")
    expected = base.get("expected_release")
    if not isinstance(expected, dict):
        raise SystemExit("accepted v54 release contract is invalid")
    if expected.get("manifest_sha256") != BASE_MANIFEST_SHA256:
        raise SystemExit("accepted v54 manifest lineage differs")


def selected_inputs(
    base: Mapping[str, object],
) -> tuple[list[dict[str, str]], list[Path]]:
    """Return 314 v54 rows verbatim plus two additions in path order."""

    _validate_base_definition(base)
    raw_base_rows = base.get("curated_inputs")
    if not isinstance(raw_base_rows, list):
        raise SystemExit("accepted v54 curated input inventory is invalid")
    base_rows: list[dict[str, str]] = []
    base_pins: dict[str, str] = {}
    for row in raw_base_rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise SystemExit("accepted v54 curated input row is invalid")
        relative = row.get("path")
        digest = row.get("sha256")
        if not isinstance(relative, str) or not isinstance(digest, str):
            raise SystemExit("accepted v54 curated input pin is invalid")
        if relative in base_pins:
            raise SystemExit(f"duplicate accepted v54 input: {relative}")
        base_pins[relative] = digest
        base_rows.append({"path": relative, "sha256": digest})
    if len(base_rows) != 314:
        raise SystemExit(f"expected 314 unique v54 inputs, found {len(base_rows)}")
    if set(base_pins) & set(ADDITIONS):
        raise SystemExit("one or more v55 additions already occurs in v54")

    addition_rows = [
        {"path": relative, "sha256": digest} for relative, digest in ADDITIONS.items()
    ]
    rows = sorted([*base_rows, *addition_rows], key=lambda row: row["path"])
    pins = {row["path"]: row["sha256"] for row in rows}
    if len(rows) != 316 or len(pins) != 316:
        raise SystemExit(f"expected 316 unique v55 inputs, found {len(pins)}")
    inherited_rows = [row for row in rows if row["path"] in base_pins]
    if inherited_rows != base_rows:
        raise SystemExit("one or more inherited v54 input rows changed or reordered")
    if {path: pins[path] for path in ADDITIONS} != ADDITIONS:
        raise SystemExit("v55 addition inventory changed")
    if set(pins) & REJECTED_PROVISIONAL_INPUTS:
        raise SystemExit("a rejected DataBank v1 input is selected")
    actual_positions = {
        row["path"]: index for index, row in enumerate(rows) if row["path"] in ADDITIONS
    }
    if actual_positions != EXPECTED_ADDITION_POSITIONS:
        raise SystemExit("v55 deterministic addition positions changed")

    epoch = base.get("epoch_capture")
    if not isinstance(epoch, dict) or not isinstance(epoch.get("retrieved_at"), str):
        raise SystemExit("accepted v54 Epoch capture metadata is invalid")
    retrieved_at = [epoch["retrieved_at"]]
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
        retrieved_at.extend(timestamps)
        curated_paths.append(path)
    validate_temporal_contract(retrieved_at)
    return rows, curated_paths


def _validate_import_result(relative: str, result: object) -> None:
    expected = EXPECTED_IMPORT_RESULTS.get(relative)
    if expected is None:
        return
    actual = (
        getattr(result, "entities_created"),
        getattr(result, "evidence_created"),
    )
    if actual != expected:
        raise SystemExit(
            f"accepted tranche import result differs for {relative}: "
            f"{actual} != {expected}"
        )
    if (
        getattr(result, "examined_elements") != 1
        or getattr(result, "imported_elements") != 1
        or getattr(result, "skipped_elements") != 0
        or getattr(result, "warnings")
    ):
        raise SystemExit(f"accepted tranche import boundary differs for {relative}")


def _validate_added_evidence_boundary(connection: sqlite3.Connection) -> None:
    """Pin both ingested and published evidence records and their references."""

    if (
        EXPECTED_DATABASE_SOURCE_FAMILIES
        != BASE_DATABASE_SOURCE_FAMILIES + INCOMING_DATABASE_SOURCE_FAMILIES
        or EXPECTED_RELEASE_SOURCE_FAMILIES
        != BASE_RELEASE_SOURCE_FAMILIES + INCOMING_RELEASE_SOURCE_FAMILIES
    ):
        raise SystemExit("source-family scope arithmetic is invalid")
    placeholders = ", ".join("?" for _ in ADDED_EVIDENCE)
    added = {
        row["curated_record_key"]: (
            row["id"],
            row["content_hash"],
            row["source_family"],
        )
        for row in connection.execute(
            f"""
            SELECT id, content_hash, source_family,
                   json_extract(metadata_json, '$.curated_record_key')
                       AS curated_record_key
            FROM evidence
            WHERE json_extract(metadata_json, '$.curated_record_key')
                  IN ({placeholders})
            ORDER BY curated_record_key
            """,
            tuple(ADDED_EVIDENCE),
        )
    }
    if set(added) != set(ADDED_EVIDENCE):
        raise SystemExit("fresh database does not contain exactly two added evidence rows")
    if connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] != 454:
        raise SystemExit("fresh database evidence total differs from 454")
    if (
        connection.execute(
            "SELECT COUNT(DISTINCT source_family) FROM evidence"
        ).fetchone()[0]
        != EXPECTED_DATABASE_SOURCE_FAMILIES
    ):
        raise SystemExit("fresh database source-family count differs from 237")

    reference_queries = (
        "SELECT COUNT(*) FROM entity_snapshots WHERE evidence_id = ?",
        "SELECT COUNT(*) FROM lifecycle_observations WHERE evidence_id = ?",
        "SELECT COUNT(*) FROM operating_model_observations WHERE evidence_id = ?",
        "SELECT COUNT(*) FROM workload_observations WHERE evidence_id = ?",
        "SELECT COUNT(*) FROM capacity_estimates WHERE evidence_id = ?",
        "SELECT COUNT(*) FROM administrative_assignments WHERE boundary_evidence_id = ?",
    )
    for key, (evidence_id, content_hash, source_family) in added.items():
        expected_hash, expected_family, expected_references = ADDED_EVIDENCE[key]
        if (content_hash, source_family) != (expected_hash, expected_family):
            raise SystemExit(f"added evidence identity differs: {key}")
        references = tuple(
            connection.execute(query, (evidence_id,)).fetchone()[0]
            for query in reference_queries
        )
        if references != expected_references:
            raise SystemExit(f"added evidence reference boundary differs: {key}")


def _csv_counter(path: Path) -> Counter[tuple[tuple[str, str], ...]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return Counter(tuple(row.items()) for row in csv.DictReader(stream))


def _validate_additive_release_delta(release_stage: Path) -> None:
    """Require all v54 rows to survive and only the exact v55 additions."""

    for filename, (expected_common, expected_added) in CSV_ADDITIVE_COUNTS.items():
        before = _csv_counter(BASE_RELEASE / filename)
        after = _csv_counter(release_stage / filename)
        common = before & after
        added = after - common
        removed = before - common
        if (
            sum(common.values()) != expected_common
            or sum(added.values()) != expected_added
            or sum(removed.values()) != 0
        ):
            raise SystemExit(f"fresh release additive delta differs: {filename}")
    entity_rows = _csv_counter(release_stage / "entities.csv") - _csv_counter(
        BASE_RELEASE / "entities.csv"
    )
    stable_keys = {dict(packed)["stable_key"] for packed in entity_rows.elements()}
    if stable_keys != ADDED_ENTITY_KEYS:
        raise SystemExit("fresh release added entity identity set differs")


def build_open_seed_v55() -> dict[str, object]:
    """Build and freeze v55 once, refusing every publication collision."""

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
            raise SystemExit("accepted v54 definition hash differs")
        if sha256(BASE_RELEASE / "manifest.json") != BASE_MANIFEST_SHA256:
            raise SystemExit("accepted v54 manifest hash differs")
        if tree_digest(BASE_RELEASE) != BASE_TREE_SHA256:
            raise SystemExit("accepted v54 release tree differs")

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
                prefix="open-seed-v55-db-", dir=staging_root
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
                        raise SystemExit("fresh Epoch import result differs from v54")
                    for path in curated_paths:
                        document = json.loads(path.read_text(encoding="utf-8"))
                        timestamp = {
                            row["retrieved_at"] for row in document["evidence"]
                        }.pop()
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection, path, retrieved_at=timestamp
                        )
                        relative = path.relative_to(ROOT).as_posix()
                        _validate_import_result(relative, result)
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
                    _validate_added_evidence_boundary(connection)
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
                    if "source_families" in summary:
                        raise SystemExit(
                            "summary unexpectedly mixes in a source-family count"
                        )
                finally:
                    connection.close()

            _validate_additive_release_delta(release_stage)
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
            published_summary = json.loads(
                (release_stage / "summary.json").read_text(encoding="utf-8")
            )
            actual_summary = {
                key: published_summary.get(key) for key in EXPECTED_SUMMARY
            }
            if actual_summary != EXPECTED_SUMMARY:
                raise SystemExit(
                    "fresh summary projection differs; refusing to publish:\n"
                    + json.dumps(
                        {"actual": actual_summary, "expected": EXPECTED_SUMMARY},
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
        "source_families": EXPECTED_RELEASE_SOURCE_FAMILIES,
    }


def main() -> int:
    """Build v55 and print the frozen release facts."""

    print(json.dumps(build_open_seed_v55(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
