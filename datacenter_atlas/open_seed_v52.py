"""Build the collision-isolated official open seed v52 exactly once.

V52 derives only from the independently accepted frozen v51 definition and
release. It preserves all 301 inherited input-pin rows and their relative order
while inserting five accepted official-source records into deterministic path
order. The release is source scoped and makes no completeness, parity, or
unique-physical-site claim.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
from typing import Iterator, Sequence

from .curated import CuratedOfficialSourceAdapter
from .database import initialize
from .epoch import EpochAIAdapter
from .open_seed_release import validate_open_seed_release
from .open_seed_v51 import (
    canonical_json,
    discard_release_stage,
    promote_noreplace,
    sha256,
)
from .publication_release import write_release
from .service import summarize, validate_database


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v51.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v51"
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v52.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v52"
PUBLICATION_LOCK = ROOT / ".open-seed-v52.lock"

BASE_DEFINITION_SHA256 = (
    "eca98402dfcb5e7c2c9b9a16093dcf852d20afa932d047966e3409c07d1d3837"
)
BASE_MANIFEST_SHA256 = (
    "c0534405a668df93a783e7d7bdd4cb4f18898879892f559a0dfee914ea081235"
)
RECORDED_AT = "2026-07-20T18:11:00Z"
MAX_SELECTED_RETRIEVED_AT = "2026-07-20T17:35:25Z"

ADDITIONS = {
    "sources/curated-official-2026-07-20-greensquaredc-syd1-stage2.json": (
        "7e5628efb8beae2a3e43c015800dfe37d4ea74f2a58e4b227e0b23c2e83adfa4"
    ),
    "sources/curated-official-2026-07-20-iron-mountain-mum3-navi-mumbai.json": (
        "6913bff64fb893a8377ad384936a8873f1d886b1654590ac62d8b7f7130e3080"
    ),
    "sources/curated-official-2026-07-20-bell-ai-fabric-saskatchewan.json": (
        "212173178a5b04e1299ef62bd8de0aabac6cdcdb84132fb53d06ba6bb2994a39"
    ),
    "sources/curated-official-2026-07-20-trg-hou2-spring-texas.json": (
        "1689c544d726d8eb9c1e21602c8b3e8a20209c7e5650b84e589ad604a4bff60d"
    ),
    "sources/curated-official-2026-07-20-related-digital-cheyenne-phase1.json": (
        "5889a849ed963fd59b944d2c2da0bfa0d8920eaf76489a0c6f8f68f7c25119c2"
    ),
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

ADDED_EVIDENCE_KEYS = (
    "greensquaredc-syd1-construction-2026-01-14-captured-2026-07-20",
    "greensquaredc-syd1-locations-wayback-2025-11-26-captured-2026-07-20",
    "greensquaredc-syd1-locations-current-captured-2026-07-20",
    "iron-mountain-mum3-groundbreaking-linkedin-2026-01-20-captured-2026-07-20",
    "iron-mountain-india-current-mum3-captured-2026-07-20",
    "bell-sherwood-early-site-works-2026-05-04-captured-2026-07-20",
    "bell-sherwood-construction-partners-2026-05-14-captured-2026-07-20",
    "bell-sherwood-community-current-captured-2026-07-20",
    "trg-hou2-campus-brochure-2026-captured-2026-07-20",
    "related-digital-cheyenne-current-captured-2026-07-20",
    "clayco-related-cheyenne-current-captured-2026-07-20",
    "related-digital-cheyenne-news-index-2026-06-14-captured-2026-07-20",
)

UNPUBLISHED_EVIDENCE_KEYS = frozenset(
    {
        "greensquaredc-syd1-locations-current-captured-2026-07-20",
        "related-digital-cheyenne-news-index-2026-06-14-captured-2026-07-20",
    }
)

EXPECTED_SUMMARY = {
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
    "evidence_total": 435,
    "projects_total": 298,
}

BASE_DATABASE_SOURCE_FAMILIES = 211
INCOMING_DATABASE_SOURCE_FAMILIES = 10
EXPECTED_DATABASE_SOURCE_FAMILIES = 221
BASE_RELEASE_SOURCE_FAMILIES = 181
INCOMING_RELEASE_SOURCE_FAMILIES = 9
EXPECTED_RELEASE_SOURCE_FAMILIES = 190


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
    """Hold an exclusive v52 publication lock without replacing any file."""

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


def _validate_base_definition(base: dict[str, object]) -> None:
    """Prove that accepted v51, and no rejected seed, is the lineage root."""

    accepted_definition = ROOT / "sources/open-seed-2026-07-20-v51.json"
    accepted_release = ROOT / "releases/2026-07-20-open-seed-v51"
    if BASE_DEFINITION != accepted_definition or BASE_RELEASE != accepted_release:
        raise SystemExit("v52 base paths must select exactly accepted v51")
    if base.get("release_id") != "2026-07-20-open-seed-v51":
        raise SystemExit("accepted seed base must be exactly v51")
    build = base.get("build")
    if (
        not isinstance(build, dict)
        or build.get("recorded_at") != "2026-07-20T17:33:00Z"
    ):
        raise SystemExit("accepted v51 build metadata differs")
    expected = base.get("expected_release")
    if not isinstance(expected, dict):
        raise SystemExit("accepted v51 release contract is invalid")
    if expected.get("manifest_sha256") != BASE_MANIFEST_SHA256:
        raise SystemExit("accepted v51 manifest lineage differs")


def selected_inputs(
    base: dict[str, object],
) -> tuple[list[dict[str, str]], list[Path]]:
    """Return 301 v51 rows verbatim plus five additions in path order."""

    _validate_base_definition(base)
    raw_base_rows = base.get("curated_inputs")
    if not isinstance(raw_base_rows, list):
        raise SystemExit("accepted v51 curated input inventory is invalid")
    base_rows: list[dict[str, str]] = []
    base_pins: dict[str, str] = {}
    for row in raw_base_rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise SystemExit("accepted v51 curated input row is invalid")
        relative = row.get("path")
        digest = row.get("sha256")
        if not isinstance(relative, str) or not isinstance(digest, str):
            raise SystemExit("accepted v51 curated input pin is invalid")
        if relative in base_pins:
            raise SystemExit(f"duplicate accepted v51 input: {relative}")
        base_pins[relative] = digest
        base_rows.append({"path": relative, "sha256": digest})
    if len(base_rows) != 301:
        raise SystemExit(f"expected 301 unique v51 inputs, found {len(base_rows)}")
    if set(base_pins) & set(ADDITIONS):
        raise SystemExit("one or more v52 additions already occurs in v51")

    addition_rows = [
        {"path": relative, "sha256": digest} for relative, digest in ADDITIONS.items()
    ]
    rows = sorted([*base_rows, *addition_rows], key=lambda row: row["path"])
    pins = {row["path"]: row["sha256"] for row in rows}
    if len(rows) != 306 or len(pins) != 306:
        raise SystemExit(f"expected 306 unique v52 inputs, found {len(pins)}")
    inherited_rows = [row for row in rows if row["path"] in base_pins]
    if inherited_rows != base_rows:
        raise SystemExit("one or more inherited v51 input rows changed or reordered")
    if {path: pins[path] for path in ADDITIONS} != ADDITIONS:
        raise SystemExit("v52 addition inventory changed")

    epoch = base.get("epoch_capture")
    if not isinstance(epoch, dict) or not isinstance(epoch.get("retrieved_at"), str):
        raise SystemExit("accepted v51 Epoch capture metadata is invalid")
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


def _validate_added_evidence_boundary(connection: sqlite3.Connection) -> None:
    """Pin 12 ingested rows and the two deliberately unpublished records."""

    if (
        EXPECTED_DATABASE_SOURCE_FAMILIES
        != BASE_DATABASE_SOURCE_FAMILIES + INCOMING_DATABASE_SOURCE_FAMILIES
        or EXPECTED_RELEASE_SOURCE_FAMILIES
        != BASE_RELEASE_SOURCE_FAMILIES + INCOMING_RELEASE_SOURCE_FAMILIES
        or 191 in {EXPECTED_DATABASE_SOURCE_FAMILIES, EXPECTED_RELEASE_SOURCE_FAMILIES}
    ):
        raise SystemExit("source-family scope arithmetic is invalid or mixed")

    added = {
        row["curated_record_key"]: (row["id"], row["source_family"])
        for row in connection.execute(
            """
            SELECT id, source_family,
                   json_extract(metadata_json, '$.curated_record_key')
                       AS curated_record_key
            FROM evidence
            WHERE json_extract(metadata_json, '$.curated_record_key') IN (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ORDER BY curated_record_key
            """,
            ADDED_EVIDENCE_KEYS,
        )
    }
    if set(added) != set(ADDED_EVIDENCE_KEYS):
        raise SystemExit(
            "fresh database does not contain exactly 12 added evidence rows"
        )
    incoming_families = {source_family for _, source_family in added.values()}
    if len(incoming_families) != INCOMING_DATABASE_SOURCE_FAMILIES:
        raise SystemExit(
            "incoming database source-family count differs: "
            f"{len(incoming_families)} != {INCOMING_DATABASE_SOURCE_FAMILIES}"
        )
    evidence_total = connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
    if evidence_total != EXPECTED_SUMMARY["evidence_total"]:
        raise SystemExit(
            "fresh database evidence total differs: "
            f"{evidence_total} != {EXPECTED_SUMMARY['evidence_total']}"
        )
    database_source_families = connection.execute(
        "SELECT COUNT(DISTINCT source_family) FROM evidence"
    ).fetchone()[0]
    if database_source_families != EXPECTED_DATABASE_SOURCE_FAMILIES:
        raise SystemExit(
            "fresh database source-family count differs: "
            f"{database_source_families} != {EXPECTED_DATABASE_SOURCE_FAMILIES}"
        )
    related_news_rows = connection.execute(
        """
        SELECT json_extract(metadata_json, '$.curated_record_key')
        FROM evidence
        WHERE source_family = 'related_digital_news_index'
        """
    ).fetchall()
    if [row[0] for row in related_news_rows] != [
        "related-digital-cheyenne-news-index-2026-06-14-captured-2026-07-20"
    ]:
        raise SystemExit("Related news-index family boundary differs")

    reference_queries = (
        "SELECT COUNT(*) FROM entities WHERE created_from_evidence_id = ?",
        "SELECT COUNT(*) FROM entity_snapshots WHERE evidence_id = ?",
        "SELECT COUNT(*) FROM lifecycle_observations WHERE evidence_id = ?",
        "SELECT COUNT(*) FROM operating_model_observations WHERE evidence_id = ?",
        "SELECT COUNT(*) FROM workload_observations WHERE evidence_id = ?",
        "SELECT COUNT(*) FROM capacity_estimates WHERE evidence_id = ?",
        "SELECT COUNT(*) FROM administrative_assignments WHERE boundary_evidence_id = ?",
    )
    publication_reference_queries = reference_queries[1:]
    publishable_incoming_families: set[str] = set()
    for key, (evidence_id, source_family) in added.items():
        all_references = sum(
            connection.execute(query, (evidence_id,)).fetchone()[0]
            for query in reference_queries
        )
        publication_references = sum(
            connection.execute(query, (evidence_id,)).fetchone()[0]
            for query in publication_reference_queries
        )
        if key in UNPUBLISHED_EVIDENCE_KEYS:
            if all_references != 0:
                raise SystemExit(
                    f"source-only evidence unexpectedly has a normalized reference: {key}"
                )
        elif publication_references == 0:
            raise SystemExit(f"publishable added evidence is unreferenced: {key}")
        else:
            publishable_incoming_families.add(source_family)
    if len(publishable_incoming_families) != INCOMING_RELEASE_SOURCE_FAMILIES:
        raise SystemExit(
            "incoming release source-family count differs: "
            f"{len(publishable_incoming_families)} "
            f"!= {INCOMING_RELEASE_SOURCE_FAMILIES}"
        )
    if incoming_families - publishable_incoming_families != {
        "related_digital_news_index"
    }:
        raise SystemExit("incoming database-only source-family boundary differs")


def build_open_seed_v52() -> dict[str, object]:
    """Build and freeze v52 once, refusing every publication collision."""

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
            raise SystemExit("accepted v51 definition hash differs")
        if sha256(BASE_RELEASE / "manifest.json") != BASE_MANIFEST_SHA256:
            raise SystemExit("accepted v51 manifest hash differs")

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
                prefix="open-seed-v52-db-", dir=staging_root
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
                        raise SystemExit("fresh Epoch import result differs from v51")
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
            actual_summary = {key: summary[key] for key in EXPECTED_SUMMARY}
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
            if "related_digital_news_index" in manifest["source_families"]:
                raise SystemExit(
                    "unpublished Related news-index family leaked to release"
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
    """Build v52 and print the frozen release facts."""

    print(json.dumps(build_open_seed_v52(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
