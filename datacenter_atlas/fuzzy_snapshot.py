"""Atomic release assembly for the review-only fuzzy OSM discovery layer."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
from typing import Any, Callable, Mapping

from .database import initialize
from .fuzzy_shortlist import build_fuzzy_shortlist, shortlist_csv
from .global_snapshot import (
    DEFAULT_MAP_GENERATOR,
    DEFAULT_NATURAL_EARTH_INPUT,
    GlobalSnapshotError,
    _add_manifest_file,
    _assert_database_cutoffs,
    _generate_map,
    _instant,
    _timestamp,
    validate_release_files,
)
from .natural_earth import enrich_administrative_assignments
from .osm_fuzzy import (
    DEFAULT_MANIFEST_FILENAME,
    OpenStreetMapFuzzyDiscoveryAdapter,
    materialize_fuzzy_extract,
)
from .publication_release import write_release
from .service import summarize, validate_database
from .timestamps import canonical_read_cutoff


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXTRACTION_MANIFEST = (
    PROJECT_ROOT / "source_cache" / "osm-planet-260713" / "fuzzy-extract-manifest.json"
)
DEFAULT_MATERIALIZATION = (
    PROJECT_ROOT / "source_cache" / "osm-planet-260713" / "fuzzy-materialized-review"
)


class FuzzySnapshotError(GlobalSnapshotError):
    """Raised when the fuzzy review release cannot be assembled losslessly."""


def fuzzy_review_readme(
    *,
    as_of: str,
    snapshot_date: str,
    integrity: Mapping[str, Any],
    summary: Mapping[str, Any],
    triage: Mapping[str, Any] | None = None,
) -> str:
    classifications = integrity.get("classification_counts") or {}
    statuses = summary.get("entities_by_status") or {}
    triage_counts = (triage or {}).get("counts") or {}
    return (
        f"# Data Center Atlas OSM fuzzy review layer — {as_of}\n\n"
        f"This isolated review release contains {summary.get('entities_total', 0):,} supplemental "
        f"OpenStreetMap candidates from the {snapshot_date} Planet snapshot. It is a recall-"
        "expansion queue, not a census, a confirmed-facility list, or a claim of parity with "
        "SemiAnalysis. Every record requires analyst review and independent corroboration before "
        "promotion to a confirmed atlas.\n\n"
        f"The broad materialization found {integrity.get('broad_match_counts', {}).get('total', 0):,} "
        f"objects. It excluded {integrity.get('exact_layer_duplicate_count', 0):,} canonical "
        "92-pair matches already represented in the exact Planet layer, leaving "
        f"{integrity.get('supplemental_eligible_count', 0):,} review candidates: "
        f"{int(classifications.get('explicit_marker_variant', 0)):,} explicit marker variants, "
        f"{int(classifications.get('unknown_key_explicit_value', 0)):,} unknown-key exact values, "
        f"{int(classifications.get('textual_only', 0)):,} text-only matches, and "
        f"{int(classifications.get('ambiguous', 0)):,} ambiguous matches. Text-only and ambiguous "
        "matches are low-confidence leads and never prove data-centre identity.\n\n"
        f"The lifecycle view contains {int(statuses.get('under_construction', 0)):,} review-only "
        f"`under_construction` candidates and {int(statuses.get('proposed', 0)):,} review-only "
        "`proposed` candidates, based only on exact normalized values under explicit OSM lifecycle "
        "keys. These are tag observations, not physical confirmation. All remaining rows are "
        "`lead`. No capacity, workload, operating model, commissioning state, or energy use is "
        "inferred.\n\n"
        f"`fuzzy_review_shortlist.csv` retains {int(triage_counts.get('shortlisted_candidates', 0)):,} "
        f"higher-signal candidates and excludes {int(triage_counts.get('excluded_source_or_reference_only_candidates', 0)):,} "
        "source/reference-only text matches from that shortlist. The excluded rows remain in the "
        "full database for audit. `fuzzy_review_triage.json` records the exact policy, tier counts, "
        "and top excluded trigger patterns; shortlist membership is not confirmation.\n\n"
        "Natural Earth boundaries provide a separate country-assignment observation for every "
        "coordinate-bearing candidate; unmatched results remain explicit. `construction_pipeline.csv` "
        "and `construction_source_signals.csv` are review queues in this release because `lead` is "
        "an active discovery state. They must not be reported as counts of projects being built.\n\n"
        "The database and exports are derived from OpenStreetMap and retain © OpenStreetMap "
        "contributors attribution. Downstream use must comply with ODbL. `atlas.sqlite` preserves "
        "the auditable claims; `atlas.html` is the standalone map; `manifest.json` binds every "
        "distributed file to its byte count and SHA-256.\n"
    )


def _count(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FuzzySnapshotError(f"{label} must be a non-negative integer")
    return value


def build_fuzzy_review_snapshot(
    *,
    extraction_manifest: str | Path,
    materialization: str | Path,
    natural_earth_input: str | Path,
    output_directory: str | Path,
    as_of: str,
    recorded_at: str,
    retrieved_at: str,
    map_generator: str | Path = DEFAULT_MAP_GENERATOR,
    command_runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> dict[str, Any]:
    """Build one immutable review release without network access or promotion."""
    try:
        recorded_at = canonical_read_cutoff(recorded_at, "recorded_at")
    except ValueError as error:
        raise FuzzySnapshotError(str(error)) from error
    destination = Path(os.path.abspath(os.fspath(output_directory)))
    if destination.exists() or destination.is_symlink():
        raise FuzzySnapshotError(f"refusing existing output directory: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        as_of_date = date.fromisoformat(as_of)
    except ValueError as error:
        raise FuzzySnapshotError("as_of must be an ISO date") from error
    retrieved_at = _timestamp(retrieved_at, "retrieved_at")
    if _instant(retrieved_at) > _instant(recorded_at):
        raise FuzzySnapshotError("recorded_at precedes fuzzy source retrieval")

    materialization_directory = Path(materialization).resolve()
    source_manifest = materialize_fuzzy_extract(
        extraction_manifest,
        materialization_directory,
    )
    if source_manifest.get("state") != "completed" or source_manifest.get("review_only") is not True:
        raise FuzzySnapshotError("fuzzy materialization is not a completed review bundle")
    snapshot_date = source_manifest.get("snapshot_date")
    if not isinstance(snapshot_date, str):
        raise FuzzySnapshotError("fuzzy materialization has no snapshot date")
    try:
        parsed_snapshot_date = date.fromisoformat(snapshot_date)
    except ValueError as error:
        raise FuzzySnapshotError("fuzzy materialization snapshot date is invalid") from error
    if parsed_snapshot_date > as_of_date:
        raise FuzzySnapshotError("fuzzy snapshot date is later than as_of")
    integrity = source_manifest.get("counts")
    if not isinstance(integrity, Mapping):
        raise FuzzySnapshotError("fuzzy materialization counts are missing")
    broad_total = _count(
        (integrity.get("broad_match_counts") or {}).get("total"),
        "fuzzy broad-match total",
    )
    supplemental = _count(
        integrity.get("supplemental_eligible_count"),
        "fuzzy supplemental count",
    )
    exact_duplicates = _count(
        integrity.get("exact_layer_duplicate_count"),
        "fuzzy exact-duplicate count",
    )
    if supplemental + exact_duplicates != broad_total:
        raise FuzzySnapshotError("fuzzy classification counts do not reconcile")

    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent)
    )
    connection: sqlite3.Connection | None = None
    try:
        database_path = stage / "atlas.sqlite"
        connection, migrations = initialize(database_path)
        import_result = OpenStreetMapFuzzyDiscoveryAdapter().import_file(
            connection,
            materialization_directory,
            retrieved_at=retrieved_at,
        )
        actual = (
            import_result.examined_elements,
            import_result.imported_elements,
            import_result.skipped_elements,
        )
        expected = (broad_total, supplemental, exact_duplicates)
        if actual != expected:
            raise FuzzySnapshotError(
                f"fuzzy import counts do not reconcile: expected {expected}, got {actual}"
            )
        country_result = enrich_administrative_assignments(
            connection,
            Path(natural_earth_input).resolve(),
            as_of=as_of,
            recorded_at=recorded_at,
        )
        if country_result.assignments_created != country_result.examined_snapshots:
            raise FuzzySnapshotError(
                "Natural Earth did not create one assignment result per examined snapshot"
            )
        errors = validate_database(connection)
        if errors:
            raise FuzzySnapshotError("database validation failed: " + "; ".join(errors))
        _assert_database_cutoffs(
            connection,
            as_of=as_of_date,
            recorded_at=_instant(recorded_at),
        )
        summary = summarize(connection, as_of=as_of, recorded_at=recorded_at)
        if summary.get("entities_total") != supplemental:
            raise FuzzySnapshotError("fuzzy release entity total does not match source bundle")
        shortlist_rows, triage = build_fuzzy_shortlist(
            connection,
            as_of=as_of,
            recorded_at=recorded_at,
        )
        if triage["counts"]["imported_supplemental_candidates"] != supplemental:
            raise FuzzySnapshotError("fuzzy triage total does not match source bundle")
        triage["source_materialization_counts"] = dict(integrity)
        readme = fuzzy_review_readme(
            as_of=as_of,
            snapshot_date=snapshot_date,
            integrity=integrity,
            summary=summary,
            triage=triage,
        )
        write_release(
            connection,
            stage,
            as_of=as_of,
            recorded_at=recorded_at,
            readme=readme,
        )
        (stage / "fuzzy_review_shortlist.csv").write_text(
            shortlist_csv(shortlist_rows), encoding="utf-8"
        )
        (stage / "fuzzy_review_triage.json").write_text(
            json.dumps(triage, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        connection.execute("PRAGMA optimize")
        connection.commit()
        connection.close()
        connection = None

        _add_manifest_file(stage, "atlas.sqlite")
        _generate_map(stage, Path(map_generator).resolve(), command_runner)
        _add_manifest_file(stage, "atlas.html")
        _add_manifest_file(stage, "fuzzy_review_shortlist.csv")
        _add_manifest_file(stage, "fuzzy_review_triage.json")
        manifest_path = stage / "manifest.json"
        annotated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        annotated_manifest["fuzzy_review_shortlist_records"] = len(shortlist_rows)
        annotated_manifest["fuzzy_review_excluded_candidates"] = triage["counts"][
            "excluded_source_or_reference_only_candidates"
        ]
        annotated_manifest["review_only"] = True
        manifest_path.write_text(
            json.dumps(annotated_manifest, indent=2, sort_keys=True, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        release_manifest = validate_release_files(stage)
        stage.replace(destination)
    except Exception:
        if connection is not None:
            connection.close()
        if stage.exists():
            shutil.rmtree(stage)
        raise

    return {
        "output_directory": str(destination),
        "schema_migrations_installed": migrations,
        "source_manifest": str(materialization_directory / DEFAULT_MANIFEST_FILENAME),
        "sources": {
            "openstreetmap_fuzzy_review": asdict(import_result),
            "natural_earth": asdict(country_result),
        },
        "summary": summary,
        "triage": triage,
        "manifest": release_manifest,
        "review_only": True,
    }


__all__ = [
    "DEFAULT_EXTRACTION_MANIFEST",
    "DEFAULT_MATERIALIZATION",
    "FuzzySnapshotError",
    "build_fuzzy_review_snapshot",
    "fuzzy_review_readme",
]
