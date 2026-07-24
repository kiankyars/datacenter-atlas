"""Atomic release assembly for the isolated Scrutica discovery layer."""

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
from .global_snapshot import (
    DEFAULT_MAP_GENERATOR,
    GlobalSnapshotError,
    _add_manifest_file,
    _assert_database_cutoffs,
    _generate_map,
    _instant,
    _timestamp,
    validate_release_files,
)
from .publication_release import write_release
from .scrutica import (
    SCRUTICA_DIRECTORY_SPEC,
    SCRUTICA_MANIFEST,
    SCRUTICA_SOURCE_FAMILY,
    DirectorySpec,
    ScruticaAdapter,
)
from .service import summarize, validate_database
from .timestamps import canonical_read_cutoff


SCRUTICA_PINNED_IN_SCOPE_RECORDS = 4_120
SCRUTICA_PINNED_EXCLUDED_BY_FACILITY_TYPE = {
    "logic_fab": 14,
    "memory_fab": 3,
    "other": 91,
    "packaging": 6,
}
SCRUTICA_PINNED_EXCLUDED_RECORDS = sum(
    SCRUTICA_PINNED_EXCLUDED_BY_FACILITY_TYPE.values()
)


class ScruticaSnapshotError(GlobalSnapshotError):
    """Raised when an isolated Scrutica release cannot be assembled losslessly."""


def _nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ScruticaSnapshotError(f"{label} must be a non-negative integer")
    return value


def scrutica_release_readme(
    *,
    as_of: str,
    summary: Mapping[str, Any],
    examined_records: int,
    imported_records: int,
    excluded_by_facility_type: Mapping[str, int],
) -> str:
    excluded_records = sum(excluded_by_facility_type.values())
    exclusions = ", ".join(
        f"`{facility_type}`={count:,}"
        for facility_type, count in sorted(excluded_by_facility_type.items())
    )
    statuses = summary.get("entities_by_status") or {}
    status_text = ", ".join(
        f"`{status}`={int(count):,}" for status, count in sorted(statuses.items())
    ) or "none"
    return (
        f"# Data Center Atlas Scrutica discovery release — {as_of}\n\n"
        f"This isolated CC BY-SA 4.0 review release examined {examined_records:,} "
        f"individually browsable Scrutica records and retained {imported_records:,} rows whose "
        "exact `facility_type` is one of `ai_training`, `colocation`, `edge`, `hpc_center`, or "
        f"`hyperscale_dc`. It excluded {excluded_records:,} mixed-inventory rows ({exclusions}) "
        "without deleting them from the hash-verified source bundle. The 316 licensed-source "
        "records present only in Scrutica aggregate counts are not represented as facility rows.\n\n"
        "Every entity remains source-scoped and review-only. It is not merged with the open "
        "ODbL release, is not independent corroboration of Scrutica's named upstream source, and "
        "is not a count of unique physical sites. Lifecycle values are mapped only from Scrutica's "
        f"exact status field; the current release view is {status_text}. No status is inferred from "
        "a name, map geometry, or satellite imagery.\n\n"
        "Reported gross-facility MW, critical-IT MW, and PUE remain separate metrics. Rows are "
        "marked modeled unless Scrutica explicitly says `is_estimated=false`; capacity stage stays "
        "unknown, and no annual energy consumption is derived. Operating model is inferred only "
        "from exact `colocation`, workload only from exact `ai_training`, and `hyperscale_dc` never "
        "implies a hyperscaler.\n\n"
        "`source_fetch_manifest.json` preserves the exact completed-fetch checkpoint. "
        "`source_inputs.json`, `evidence.csv`, and per-claim evidence IDs retain raw artifact hashes, "
        "upstream dependency roots, source URLs, rights, authority tier, vintage, and the complete "
        "scope decision. `atlas.sqlite` is the isolated auditable database; `atlas.html` is the "
        "standalone review map; `manifest.json` binds every distributed file by bytes and SHA-256.\n"
    )


def _scope_summary(connection: sqlite3.Connection) -> dict[str, Any]:
    row = connection.execute(
        "SELECT metadata_json FROM evidence WHERE source_family = ? "
        "ORDER BY id LIMIT 1",
        (SCRUTICA_SOURCE_FAMILY,),
    ).fetchone()
    if row is None:
        raise ScruticaSnapshotError("Scrutica import produced no evidence")
    try:
        metadata = json.loads(row["metadata_json"] or "{}")
    except json.JSONDecodeError as error:
        raise ScruticaSnapshotError("Scrutica evidence metadata is invalid") from error
    scope = metadata.get("datacenter_atlas_scope")
    if not isinstance(scope, dict):
        raise ScruticaSnapshotError("Scrutica evidence has no scope summary")
    return scope


def build_scrutica_snapshot(
    *,
    source_bundle: str | Path,
    output_directory: str | Path,
    as_of: str,
    recorded_at: str,
    retrieved_at: str,
    map_generator: str | Path = DEFAULT_MAP_GENERATOR,
    command_runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
    directory_spec: DirectorySpec = SCRUTICA_DIRECTORY_SPEC,
    expected_imported_records: int = SCRUTICA_PINNED_IN_SCOPE_RECORDS,
    expected_excluded_by_facility_type: Mapping[str, int] = (
        SCRUTICA_PINNED_EXCLUDED_BY_FACILITY_TYPE
    ),
) -> dict[str, Any]:
    """Build one immutable, Scrutica-only review release without network access."""
    try:
        recorded_at = canonical_read_cutoff(recorded_at, "recorded_at")
    except ValueError as error:
        raise ScruticaSnapshotError(str(error)) from error
    destination = Path(os.path.abspath(os.fspath(output_directory)))
    if destination.exists() or destination.is_symlink():
        raise ScruticaSnapshotError(f"refusing existing output directory: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        as_of_date = date.fromisoformat(as_of)
    except ValueError as error:
        raise ScruticaSnapshotError("as_of must be an ISO date") from error
    retrieved_at = _timestamp(retrieved_at, "retrieved_at")
    if _instant(retrieved_at) > _instant(recorded_at):
        raise ScruticaSnapshotError("recorded_at precedes Scrutica retrieval")

    bundle_input = Path(source_bundle)
    if bundle_input.is_symlink() or not bundle_input.is_dir():
        raise ScruticaSnapshotError("Scrutica source bundle must be a regular directory")
    bundle = bundle_input.resolve()
    source_manifest_path = bundle / SCRUTICA_MANIFEST
    if source_manifest_path.is_symlink() or not source_manifest_path.is_file():
        raise ScruticaSnapshotError("Scrutica source manifest must be a regular file")
    source_manifest_raw = source_manifest_path.read_bytes()
    try:
        source_manifest = json.loads(source_manifest_raw)
    except json.JSONDecodeError as error:
        raise ScruticaSnapshotError("Scrutica source manifest is invalid JSON") from error
    if not isinstance(source_manifest, dict) or source_manifest.get("state") != "completed":
        raise ScruticaSnapshotError("Scrutica source bundle is not complete")

    expected_examined = directory_spec.browsable
    if not isinstance(expected_excluded_by_facility_type, Mapping):
        raise ScruticaSnapshotError("expected Scrutica exclusions must be a mapping")
    expected_imported_records = _nonnegative_integer(
        expected_imported_records, "expected Scrutica imported records"
    )
    expected_exclusions: dict[str, int] = {}
    for facility_type, count in sorted(expected_excluded_by_facility_type.items()):
        if not isinstance(facility_type, str) or not facility_type:
            raise ScruticaSnapshotError(
                "expected Scrutica exclusion facility types must be non-empty text"
            )
        expected_exclusions[facility_type] = _nonnegative_integer(
            count, f"expected Scrutica {facility_type} exclusions"
        )
    expected_skipped = sum(expected_exclusions.values())
    if expected_imported_records + expected_skipped != expected_examined:
        raise ScruticaSnapshotError(
            "expected Scrutica imported and excluded counts do not match browsable records"
        )

    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent)
    )
    connection: sqlite3.Connection | None = None
    try:
        database_path = stage / "atlas.sqlite"
        connection, migrations = initialize(database_path)
        import_result = ScruticaAdapter(spec=directory_spec).import_file(
            connection,
            bundle,
            retrieved_at=retrieved_at,
            allow_partial=False,
        )
        actual = (
            import_result.examined_elements,
            import_result.imported_elements,
            import_result.skipped_elements,
        )
        expected = (expected_examined, expected_imported_records, expected_skipped)
        if actual != expected:
            raise ScruticaSnapshotError(
                f"Scrutica import counts do not reconcile: expected {expected}, got {actual}"
            )
        scope = _scope_summary(connection)
        if (
            scope.get("completed_records_examined") != expected_examined
            or scope.get("records_imported") != expected_imported_records
            or scope.get("records_excluded") != expected_skipped
            or scope.get("excluded_by_facility_type") != expected_exclusions
        ):
            raise ScruticaSnapshotError("Scrutica scope counts do not match the pinned inventory")
        source_families = {
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT source_family FROM evidence ORDER BY source_family"
            )
        }
        if source_families != {SCRUTICA_SOURCE_FAMILY}:
            raise ScruticaSnapshotError("Scrutica release database is not source-isolated")
        errors = validate_database(connection)
        if errors:
            raise ScruticaSnapshotError("database validation failed: " + "; ".join(errors))
        _assert_database_cutoffs(
            connection,
            as_of=as_of_date,
            recorded_at=_instant(recorded_at),
        )
        summary = summarize(connection, as_of=as_of, recorded_at=recorded_at)
        if summary.get("entities_total") != expected_imported_records:
            raise ScruticaSnapshotError(
                "Scrutica current-view entity count does not match the pinned import"
            )
        readme = scrutica_release_readme(
            as_of=as_of,
            summary=summary,
            examined_records=expected_examined,
            imported_records=expected_imported_records,
            excluded_by_facility_type=expected_exclusions,
        )
        write_release(
            connection,
            stage,
            as_of=as_of,
            recorded_at=recorded_at,
            readme=readme,
        )
        (stage / "source_fetch_manifest.json").write_bytes(source_manifest_raw)
        connection.execute("PRAGMA optimize")
        connection.commit()
        connection.close()
        connection = None

        _add_manifest_file(stage, "atlas.sqlite")
        _generate_map(stage, Path(map_generator).resolve(), command_runner)
        _add_manifest_file(stage, "atlas.html")
        _add_manifest_file(stage, "source_fetch_manifest.json")
        release_manifest_path = stage / "manifest.json"
        annotated_manifest = json.loads(release_manifest_path.read_text(encoding="utf-8"))
        annotated_manifest["review_only"] = True
        release_manifest_path.write_text(
            json.dumps(annotated_manifest, indent=2, sort_keys=True, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        if source_manifest_path.read_bytes() != source_manifest_raw:
            raise ScruticaSnapshotError("Scrutica source manifest changed during the build")
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
        "source_manifest": str(source_manifest_path),
        "sources": {"scrutica": asdict(import_result)},
        "summary": summary,
        "scope": scope,
        "manifest": release_manifest,
        "review_only": True,
    }


__all__ = [
    "SCRUTICA_PINNED_EXCLUDED_BY_FACILITY_TYPE",
    "SCRUTICA_PINNED_EXCLUDED_RECORDS",
    "SCRUTICA_PINNED_IN_SCOPE_RECORDS",
    "ScruticaSnapshotError",
    "build_scrutica_snapshot",
    "scrutica_release_readme",
]
