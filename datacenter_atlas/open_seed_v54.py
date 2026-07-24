"""Build the collision-isolated official open seed v54 exactly once.

V54 derives only from the independently accepted frozen v53 definition and
release. It preserves all 306 inherited input-pin rows and their relative order
while inserting eight accepted official-source records into deterministic path
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
from .open_seed_v53 import (
    canonical_json,
    discard_release_stage,
    promote_noreplace,
    sha256,
    tree_digest,
)
from .publication_release import write_release
from .service import summarize, validate_database


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v53.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v53"
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v54.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v54"
PUBLICATION_LOCK = ROOT / ".open-seed-v54.lock"

BASE_DEFINITION_SHA256 = (
    "de3f8ccb3db48808b13114b7e2508f7043a6af848465d56e3dabec4242373a30"
)
BASE_MANIFEST_SHA256 = (
    "cd11546443ef2302bac358dea5bf3f57fc0c4f0b84f181e007294da9831a0baa"
)
BASE_TREE_SHA256 = "e1efff272b1469b0431f881d5bafefcea7fe625e1679f31329714c6adb88f9d9"
RECORDED_AT = "2026-07-20T19:56:00Z"
MAX_SELECTED_RETRIEVED_AT = "2026-07-20T19:42:23Z"

ADDITIONS = {
    "sources/curated-official-2026-07-20-fleet-reno-storey-county-program.json": (
        "7ada494873559da3782bc31773af1f312b3362df3706a7f8cf90ac97011c7e70"
    ),
    "sources/curated-official-2026-07-20-databank-red-oak-dfw9.json": (
        "2e49ef1fb5659929878ef7418911d9af13e4f45487a013a3e9f7120ea081fab1"
    ),
    "sources/curated-official-2026-07-20-databank-red-oak-dfw10-v2.json": (
        "a5da37d9cab7b326e7f08db9ae0561cc20c63dc2e363f87834c146167e7ac14d"
    ),
    "sources/curated-official-2026-07-20-databank-red-oak-dfw11-v2.json": (
        "a01a6f59e2f52de29b867c35e16f124c15a09704c82c980a344efebb4f4512b0"
    ),
    "sources/curated-official-2026-07-20-ascenty-spo06-greater-sao-paulo.json": (
        "6217582ee8cdf3c0e3d1ad175ab33debd90a4fa3ce88288b0e2ce96c9535a491"
    ),
    "sources/curated-official-2026-07-20-ascenty-vinhedo-3.json": (
        "1dfc6f7de38b62692f88c0a8153f7ab3b50117b67fc292c7df97d0ca2f2df8a9"
    ),
    "sources/curated-official-2026-07-20-sb-energy-ports-technology-campus.json": (
        "7a8a6c639b0b26a7c14949ff8787473714eb774d57bf39612adc219584c24260"
    ),
    "sources/curated-official-2026-07-20-raxio-tz1-tanzania.json": (
        "14ef48f59ff1ea9365362a017e68446a362c9cdb748ddffce2ce4be6dc16abd1"
    ),
}

REJECTED_PROVISIONAL_INPUTS = frozenset(
    {
        "sources/curated-official-2026-07-20-databank-red-oak-dfw10.json",
        "sources/curated-official-2026-07-20-databank-red-oak-dfw11.json",
    }
)

EXPECTED_ADDITION_POSITIONS = {
    "sources/curated-official-2026-07-20-ascenty-spo06-greater-sao-paulo.json": 165,
    "sources/curated-official-2026-07-20-ascenty-vinhedo-3.json": 167,
    "sources/curated-official-2026-07-20-databank-red-oak-dfw10-v2.json": 186,
    "sources/curated-official-2026-07-20-databank-red-oak-dfw11-v2.json": 187,
    "sources/curated-official-2026-07-20-databank-red-oak-dfw9.json": 188,
    "sources/curated-official-2026-07-20-fleet-reno-storey-county-program.json": 237,
    "sources/curated-official-2026-07-20-raxio-tz1-tanzania.json": 290,
    "sources/curated-official-2026-07-20-sb-energy-ports-technology-campus.json": 292,
}

EXPECTED_IMPORT_RESULTS = {
    "sources/curated-official-2026-07-20-ascenty-spo06-greater-sao-paulo.json": (
        2,
        2,
    ),
    "sources/curated-official-2026-07-20-ascenty-vinhedo-3.json": (2, 0),
    "sources/curated-official-2026-07-20-databank-red-oak-dfw10-v2.json": (
        2,
        4,
    ),
    "sources/curated-official-2026-07-20-databank-red-oak-dfw11-v2.json": (
        1,
        1,
    ),
    "sources/curated-official-2026-07-20-databank-red-oak-dfw9.json": (1, 1),
    "sources/curated-official-2026-07-20-fleet-reno-storey-county-program.json": (
        1,
        2,
    ),
    "sources/curated-official-2026-07-20-raxio-tz1-tanzania.json": (2, 3),
    "sources/curated-official-2026-07-20-sb-energy-ports-technology-campus.json": (
        1,
        4,
    ),
}

ADDED_EVIDENCE_KEYS = (
    "ascenty-ai-contracts-vinhedo3-spo06-2026-05-28-captured-2026-07-20",
    "ascenty-spo06-construction-2026-05-08-captured-2026-07-20",
    "databank-dfw10-current-captured-2026-07-20",
    "databank-dfw11-current-captured-2026-07-20",
    "databank-dfw9-current-captured-2026-07-20",
    "databank-red-oak-campus-current-captured-2026-07-20",
    "databank-red-oak-construction-2025-11-10-captured-2026-07-20",
    "databank-red-oak-first-three-financing-2026-04-21-captured-2026-07-20",
    "doe-ports-groundbreaking-2026-03-24-captured-2026-07-20",
    "doe-ports-lease-record-2026-04-29-captured-2026-07-20",
    "doe-ports-partnership-announcement-2026-03-20-captured-2026-07-20",
    "fleet-reno-groundbreaking-linkedin-2026-05-21-captured-2026-07-20",
    "fleet-storey-county-financing-2026-02-24-captured-2026-07-20",
    "raxio-capital-expansion-2026-07-13-captured-2026-07-20",
    "raxio-tanzania-construction-progress-2024-12-23-captured-2026-07-20",
    "raxio-tz1-location-page-captured-2026-07-20",
    "sb-energy-ports-current-captured-2026-07-20",
)

UNPUBLISHED_EVIDENCE_KEYS = frozenset(
    {
        "databank-red-oak-first-three-financing-2026-04-21-captured-2026-07-20",
        "doe-ports-partnership-announcement-2026-03-20-captured-2026-07-20",
        "fleet-storey-county-financing-2026-02-24-captured-2026-07-20",
        "raxio-capital-expansion-2026-07-13-captured-2026-07-20",
        "sb-energy-ports-current-captured-2026-07-20",
    }
)

ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:ascenty-greater-sao-paulo-campus",
        "curated:ascenty-greater-sao-paulo-campus:spo06",
        "curated:ascenty-vinhedo-campus",
        "curated:ascenty-vinhedo-campus:vinhedo-3",
        "curated:databank-red-oak-campus",
        "curated:databank-red-oak-campus:dfw10",
        "curated:databank-red-oak-campus:dfw11",
        "curated:databank-red-oak-campus:dfw9",
        "curated:fleet-reno-storey-county-program",
        "curated:raxio-tanzania-tz1-campus",
        "curated:raxio-tanzania-tz1-campus:tz1-facility",
        "curated:sb-energy-ports-technology-campus",
    }
)

EXPECTED_RELEASE_FACTS = {
    "capacity_estimates": 482,
    "construction_pipeline_records": 344,
    "construction_source_signals": 250,
    "entities": 659,
    "entities_by_kind": {"campus": 355, "project": 304},
    "evidence_records": 381,
    "resolution_candidates": 4,
}

EXPECTED_SUMMARY = {
    "campuses_total": 355,
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
    "construction_pipeline_records": 344,
    "construction_source_signals": 250,
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
        "under_construction": 247,
    },
    "entities_total": 659,
    "entities_with_coordinates": 150,
    "evidence_total": 452,
    "lifecycle_observations_current": 379,
    "projects_total": 304,
    "recorded_at": RECORDED_AT,
}

BASE_DATABASE_SOURCE_FAMILIES = 221
INCOMING_DATABASE_SOURCE_FAMILIES = 14
EXPECTED_DATABASE_SOURCE_FAMILIES = 235
BASE_RELEASE_SOURCE_FAMILIES = 190
INCOMING_RELEASE_SOURCE_FAMILIES = 9
EXPECTED_RELEASE_SOURCE_FAMILIES = 199

CSV_ADDITIVE_COUNTS = {
    "entities.csv": (647, 12),
    "evidence.csv": (369, 12),
    "capacity_estimates.csv": (476, 6),
    "construction_pipeline.csv": (336, 8),
    "construction_source_signals.csv": (244, 6),
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
    """Hold an exclusive v54 publication lock without replacing any file."""

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
    """Prove that accepted v53, and no rejected seed, is the lineage root."""

    accepted_definition = ROOT / "sources/open-seed-2026-07-20-v53.json"
    accepted_release = ROOT / "releases/2026-07-20-open-seed-v53"
    if BASE_DEFINITION != accepted_definition or BASE_RELEASE != accepted_release:
        raise SystemExit("v54 base paths must select exactly accepted v53")
    if base.get("release_id") != "2026-07-20-open-seed-v53":
        raise SystemExit("accepted seed base must be exactly v53")
    build = base.get("build")
    if (
        not isinstance(build, dict)
        or build.get("recorded_at") != "2026-07-20T19:33:00Z"
    ):
        raise SystemExit("accepted v53 build metadata differs")
    expected = base.get("expected_release")
    if not isinstance(expected, dict):
        raise SystemExit("accepted v53 release contract is invalid")
    if expected.get("manifest_sha256") != BASE_MANIFEST_SHA256:
        raise SystemExit("accepted v53 manifest lineage differs")


def selected_inputs(
    base: Mapping[str, object],
) -> tuple[list[dict[str, str]], list[Path]]:
    """Return 306 v53 rows verbatim plus eight additions in path order."""

    _validate_base_definition(base)
    raw_base_rows = base.get("curated_inputs")
    if not isinstance(raw_base_rows, list):
        raise SystemExit("accepted v53 curated input inventory is invalid")
    base_rows: list[dict[str, str]] = []
    base_pins: dict[str, str] = {}
    for row in raw_base_rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise SystemExit("accepted v53 curated input row is invalid")
        relative = row.get("path")
        digest = row.get("sha256")
        if not isinstance(relative, str) or not isinstance(digest, str):
            raise SystemExit("accepted v53 curated input pin is invalid")
        if relative in base_pins:
            raise SystemExit(f"duplicate accepted v53 input: {relative}")
        base_pins[relative] = digest
        base_rows.append({"path": relative, "sha256": digest})
    if len(base_rows) != 306:
        raise SystemExit(f"expected 306 unique v53 inputs, found {len(base_rows)}")
    if set(base_pins) & set(ADDITIONS):
        raise SystemExit("one or more v54 additions already occurs in v53")

    addition_rows = [
        {"path": relative, "sha256": digest} for relative, digest in ADDITIONS.items()
    ]
    rows = sorted([*base_rows, *addition_rows], key=lambda row: row["path"])
    pins = {row["path"]: row["sha256"] for row in rows}
    if len(rows) != 314 or len(pins) != 314:
        raise SystemExit(f"expected 314 unique v54 inputs, found {len(pins)}")
    inherited_rows = [row for row in rows if row["path"] in base_pins]
    if inherited_rows != base_rows:
        raise SystemExit("one or more inherited v53 input rows changed or reordered")
    if {path: pins[path] for path in ADDITIONS} != ADDITIONS:
        raise SystemExit("v54 addition inventory changed")
    if set(pins) & REJECTED_PROVISIONAL_INPUTS:
        raise SystemExit("a rejected DataBank v1 input is selected")
    actual_positions = {
        row["path"]: index for index, row in enumerate(rows) if row["path"] in ADDITIONS
    }
    if actual_positions != EXPECTED_ADDITION_POSITIONS:
        raise SystemExit("v54 deterministic addition positions changed")

    epoch = base.get("epoch_capture")
    if not isinstance(epoch, dict) or not isinstance(epoch.get("retrieved_at"), str):
        raise SystemExit("accepted v53 Epoch capture metadata is invalid")
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
    """Pin 17 ingested rows, 12 published rows, and shared-record behavior."""

    if (
        EXPECTED_DATABASE_SOURCE_FAMILIES
        != BASE_DATABASE_SOURCE_FAMILIES + INCOMING_DATABASE_SOURCE_FAMILIES
        or EXPECTED_RELEASE_SOURCE_FAMILIES
        != BASE_RELEASE_SOURCE_FAMILIES + INCOMING_RELEASE_SOURCE_FAMILIES
    ):
        raise SystemExit("source-family scope arithmetic is invalid")
    placeholders = ", ".join("?" for _ in ADDED_EVIDENCE_KEYS)
    added = {
        row["curated_record_key"]: (row["id"], row["source_family"])
        for row in connection.execute(
            f"""
            SELECT id, source_family,
                   json_extract(metadata_json, '$.curated_record_key')
                       AS curated_record_key
            FROM evidence
            WHERE json_extract(metadata_json, '$.curated_record_key')
                  IN ({placeholders})
            ORDER BY curated_record_key
            """,
            ADDED_EVIDENCE_KEYS,
        )
    }
    if set(added) != set(ADDED_EVIDENCE_KEYS):
        raise SystemExit(
            "fresh database does not contain exactly 17 added evidence rows"
        )
    incoming_families = {source_family for _, source_family in added.values()}
    if len(incoming_families) != INCOMING_DATABASE_SOURCE_FAMILIES:
        raise SystemExit("incoming database source-family count differs")
    if connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] != 452:
        raise SystemExit("fresh database evidence total differs from 452")
    if (
        connection.execute(
            "SELECT COUNT(DISTINCT source_family) FROM evidence"
        ).fetchone()[0]
        != EXPECTED_DATABASE_SOURCE_FAMILIES
    ):
        raise SystemExit("fresh database source-family count differs from 235")

    reference_queries = (
        "SELECT COUNT(*) FROM entity_snapshots WHERE evidence_id = ?",
        "SELECT COUNT(*) FROM lifecycle_observations WHERE evidence_id = ?",
        "SELECT COUNT(*) FROM operating_model_observations WHERE evidence_id = ?",
        "SELECT COUNT(*) FROM workload_observations WHERE evidence_id = ?",
        "SELECT COUNT(*) FROM capacity_estimates WHERE evidence_id = ?",
        "SELECT COUNT(*) FROM administrative_assignments WHERE boundary_evidence_id = ?",
    )
    publishable_families: set[str] = set()
    for key, (evidence_id, source_family) in added.items():
        references = sum(
            connection.execute(query, (evidence_id,)).fetchone()[0]
            for query in reference_queries
        )
        if key in UNPUBLISHED_EVIDENCE_KEYS:
            if references != 0:
                raise SystemExit(
                    f"source-only evidence is unexpectedly referenced: {key}"
                )
        elif references == 0:
            raise SystemExit(f"publishable added evidence is unreferenced: {key}")
        else:
            publishable_families.add(source_family)
    if len(publishable_families) != INCOMING_RELEASE_SOURCE_FAMILIES:
        raise SystemExit("incoming release source-family count differs from nine")

    shared_expectations = {
        "databank-red-oak-construction-2025-11-10-captured-2026-07-20": (
            "lifecycle_observations",
            3,
        ),
        "databank-red-oak-campus-current-captured-2026-07-20": (
            "entity_snapshots",
            1,
        ),
        "ascenty-ai-contracts-vinhedo3-spo06-2026-05-28-captured-2026-07-20": (
            "entity_snapshots",
            2,
        ),
    }
    for key, (table, expected_count) in shared_expectations.items():
        evidence_id = added[key][0]
        count = connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE evidence_id = ?", (evidence_id,)
        ).fetchone()[0]
        if count != expected_count:
            raise SystemExit(f"shared evidence collision behavior differs: {key}")


def _csv_counter(path: Path) -> Counter[tuple[tuple[str, str], ...]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return Counter(tuple(row.items()) for row in csv.DictReader(stream))


def _validate_additive_release_delta(release_stage: Path) -> None:
    """Require all v53 rows to survive and exact new row counts with no removals."""

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


def build_open_seed_v54() -> dict[str, object]:
    """Build and freeze v54 once, refusing every publication collision."""

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
            raise SystemExit("accepted v53 definition hash differs")
        if sha256(BASE_RELEASE / "manifest.json") != BASE_MANIFEST_SHA256:
            raise SystemExit("accepted v53 manifest hash differs")
        if tree_digest(BASE_RELEASE) != BASE_TREE_SHA256:
            raise SystemExit("accepted v53 release tree differs")

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
                prefix="open-seed-v54-db-", dir=staging_root
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
                        raise SystemExit("fresh Epoch import result differs from v53")
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
    """Build v54 and print the frozen release facts."""

    print(json.dumps(build_open_seed_v54(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
