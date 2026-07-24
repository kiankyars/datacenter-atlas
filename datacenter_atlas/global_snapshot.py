"""Offline assembly of the ODbL-compatible global open snapshot."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from typing import Any, Callable, Mapping

from .database import initialize
from .natural_earth import enrich_administrative_assignments
from .osm import OpenStreetMapAdapter
from .osm_planet import DEFAULT_JSON_FILENAME, materialize_planet_extract
from .pnnl import PNNL_IM3_VERSION, PNNLIM3GeoPackageAdapter
from .publication_release import write_release
from .release import ACTIVE_PIPELINE_STATUSES
from .service import summarize, validate_database
from .timestamps import canonical_read_cutoff
from .uva import UVA_EXPECTED_ROWS, UVA_RELEASE_DATE, UVADataverseAdapter
from .wikidata import WikidataAdapter, validate_wikidata_bundle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXTRACTION_MANIFEST = (
    PROJECT_ROOT / "source_cache" / "osm-planet-260713" / "extract-manifest.json"
)
DEFAULT_OSM_MATERIALIZATION = (
    PROJECT_ROOT / "source_cache" / "osm-planet-260713" / "materialized"
)
DEFAULT_PNNL_INPUT = (
    PROJECT_ROOT / "source_cache" / "pnnl-im3-v2026.02.09"
)
DEFAULT_WIKIDATA_INPUT = PROJECT_ROOT / "source_cache" / "wikidata-2026-07-18"
DEFAULT_UVA_INPUT = PROJECT_ROOT / "source_cache" / "uva-dc-v2.0-2026-05-18"
DEFAULT_NATURAL_EARTH_INPUT = (
    PROJECT_ROOT / "source_cache" / "natural-earth-5.1.1-ca96624"
)
DEFAULT_MAP_GENERATOR = PROJECT_ROOT / "web" / "generate_atlas.py"
PNNL_EXPECTED_SOURCE_ROWS = 1_479
PNNL_EXPECTED_CANDIDATES = 1_474
PNNL_EXPECTED_DUPLICATE_ROWS = 5
TEMPORAL_CLAIM_TABLES = (
    "entity_snapshots",
    "lifecycle_observations",
    "operating_model_observations",
    "workload_observations",
    "capacity_estimates",
    "administrative_assignments",
)


class GlobalSnapshotError(ValueError):
    """Raised when the global snapshot cannot be assembled losslessly."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _json_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise GlobalSnapshotError(f"{label} must be a regular file: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GlobalSnapshotError(f"{label} is not valid JSON") from error
    if not isinstance(document, dict):
        raise GlobalSnapshotError(f"{label} must be a JSON object")
    return document


def _timestamp(value: Any, label: str) -> str:
    try:
        return canonical_read_cutoff(value, label)
    except ValueError as error:
        raise GlobalSnapshotError(str(error)) from error


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def planet_import_provenance(
    materialization_directory: str | Path,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a compact, public lineage chain for OSM evidence records."""
    directory = Path(materialization_directory)
    manifest_path = directory / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    outputs = manifest.get("outputs")
    inputs = manifest.get("inputs")
    transform = manifest.get("transform")
    rights = manifest.get("rights")
    counts = manifest.get("counts")
    if not all(
        isinstance(value, Mapping)
        for value in (outputs, inputs, transform, rights, counts)
    ):
        raise GlobalSnapshotError("OSM materialization manifest lineage is incomplete")
    overpass = outputs.get("overpass_json")
    extraction = inputs.get("extraction_manifest")
    filtered_pbf = inputs.get("filtered_pbf")
    planet_source = inputs.get("planet_source")
    if not all(
        isinstance(value, Mapping)
        for value in (overpass, extraction, filtered_pbf, planet_source)
    ):
        raise GlobalSnapshotError("OSM materialization inputs are incomplete")
    input_sha256 = overpass.get("sha256")
    if not isinstance(input_sha256, str) or len(input_sha256) != 64:
        raise GlobalSnapshotError("OSM materialization has no valid JSON SHA256")
    return {
        "input_sha256": input_sha256,
        "materialization_manifest": {
            "bytes": len(manifest_bytes),
            "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "pipeline": manifest.get("pipeline"),
            "schema_version": manifest.get("schema_version"),
            "materialized_at": manifest.get("materialized_at"),
            "source_retrieved_at": manifest.get("source_retrieved_at"),
        },
        "materialized_overpass_json": dict(overpass),
        "extraction_manifest": {
            key: extraction.get(key)
            for key in ("bytes", "sha256", "pipeline", "schema_version")
        },
        "filtered_pbf": {
            key: filtered_pbf.get(key) for key in ("bytes", "md5", "sha256")
        },
        "planet_source": {
            key: planet_source.get(key)
            for key in ("url", "snapshot_date", "bytes", "md5", "sha256")
        },
        "selection": {
            "rule": transform.get("selection"),
            "tag_filter_sha256": transform.get("tag_filter_sha256"),
            "tag_pair_count": transform.get("tag_pair_count"),
            "references_required": transform.get("references_required"),
        },
        "integrity_counts": json.loads(
            json.dumps(counts, sort_keys=True, separators=(",", ":"))
        ),
        "rights": dict(rights),
    }


def global_release_readme(
    *,
    as_of: str,
    osm_snapshot_date: str,
    osm_integrity: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> str:
    status_counts = summary.get("entities_by_status") or {}
    construction_records = sum(
        int(count)
        for status, count in status_counts.items()
        if status in ACTIVE_PIPELINE_STATUSES
    )
    construction_signals = int(
        summary.get("construction_source_signals", construction_records)
    )
    exact_counts = osm_integrity.get("exact_match_counts") or {}
    exact_matches = int(exact_counts.get("total", 0))
    geometry_unavailable = int(osm_integrity.get("geometry_unavailable_count", 0))
    unresolved_relations = int(
        osm_integrity.get("relation_geometry_unresolved_count", 0)
    )
    return (
        f"# Data Center Atlas global open snapshot — {as_of}\n\n"
        f"This release contains {summary.get('entities_total', 0):,} source-scoped records "
        f"with {summary.get('entities_with_coordinates', 0):,} geocoded records and "
        f"{construction_records:,} entity rows in the active/pre-construction view, derived from "
        f"{construction_signals:,} distinct lifecycle evidence/source observations. The source-"
        "observation grouping is not cross-source deduplication and neither number is a count of "
        "unique physical sites. This is a global discovery snapshot, not yet a complete census "
        "and not a claim of parity with SemiAnalysis.\n\n"
        f"The primary layer is an exact 92-tag extraction from the dated OpenStreetMap planet "
        f"snapshot of {osm_snapshot_date}, which emitted all {exact_matches:,} exact matches "
        f"once. {geometry_unavailable:,} retained matches have no resolvable coordinate geometry "
        f"and {unresolved_relations:,} relation geometries have unresolved polygon assembly; these "
        "limitations remain in provenance rather than being silently dropped. PNNL/DOE IM3 is "
        "retained as a separate OSM-derived "
        "U.S. candidate layer, not independent corroboration. Wikidata candidates remain "
        "source-scoped and require item/reference review. UVA DC-SENSE contributes 382 CC0 "
        "modeled Virginia facilities. Natural Earth public-domain boundaries provide the "
        "evidence-backed country assignment layer. Epoch AI is intentionally excluded from this "
        "ODbL-compatible build; Scrutica is published separately because its compiled dataset is "
        "CC BY-SA and contains source-specific rights.\n\n"
        "Lifecycle is conservative: an ordinary mapped data-centre object is `unknown`; only "
        "explicit proposed/construction tags or source claims can populate the pipeline. Text-only "
        "and fuzzy OSM discoveries are review leads and are not included as confirmed facilities. "
        "Capacity rows preserve metric and stage. UVA power and annual energy are modeled, not "
        "metered; Wikidata power rows are explicit source statements with unknown lifecycle stage. "
        "No facility power is inferred from satellite imagery, floor area, or labels.\n\n"
        "The database and exports contain ODbL-derived data and retain © OpenStreetMap contributors "
        "attribution; downstream use must comply with ODbL. CC0 and public-domain inputs retain "
        "their own provenance. Inspect `evidence.csv`, `source_inputs.json`, per-claim evidence IDs, "
        "and `ATTRIBUTION.txt` before relying on a field.\n\n"
        "`resolution_candidates.*` contains advisory cross-source links only and never merges "
        "entities automatically. `construction_pipeline.csv` retains the entity-level view; "
        "`construction_source_signals.csv` groups the same rows by lifecycle evidence ID while "
        "preserving all affected entity IDs, kinds, and stable keys. `atlas.html` is the standalone "
        "map; `atlas.sqlite` is the full auditable database; CSV and GeoJSON files are current-view "
        "exports; `manifest.json` records every distributed file hash.\n"
    )


def _add_manifest_file(release_directory: Path, filename: str) -> None:
    manifest_path = release_directory / "manifest.json"
    manifest = _json_object(manifest_path, "release manifest")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise GlobalSnapshotError("release manifest files must be an object")
    path = release_directory / filename
    if path.is_symlink() or not path.is_file():
        raise GlobalSnapshotError(f"release file must be regular: {filename}")
    files[filename] = {
        "bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def validate_release_files(release_directory: str | Path) -> dict[str, Any]:
    directory = Path(release_directory)
    manifest = _json_object(directory / "manifest.json", "release manifest")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise GlobalSnapshotError("release manifest files must be an object")
    expected = set(files) | {"manifest.json"}
    entries = list(directory.iterdir())
    non_files = [path.name for path in entries if not path.is_file()]
    if non_files:
        raise GlobalSnapshotError(
            "release contains non-file entries: " + ", ".join(sorted(non_files))
        )
    actual = {path.name for path in entries}
    if actual != expected:
        raise GlobalSnapshotError(
            f"release file set differs from manifest: expected {sorted(expected)}, "
            f"found {sorted(actual)}"
        )
    for filename, record in files.items():
        if not isinstance(record, Mapping):
            raise GlobalSnapshotError(f"release manifest record is invalid: {filename}")
        path = directory / filename
        if path.stat().st_size != record.get("bytes") or _sha256_file(path) != record.get(
            "sha256"
        ):
            raise GlobalSnapshotError(f"release file hash mismatch: {filename}")
    return manifest


def _fetched_at(bundle: Path, label: str) -> str:
    return _timestamp(
        _json_object(bundle / "manifest.json", f"{label} manifest").get("fetched_at"),
        f"{label} fetched_at",
    )


def _generate_map(
    release_directory: Path,
    generator: Path,
    runner: Callable[..., subprocess.CompletedProcess[Any]],
) -> None:
    if generator.is_symlink() or not generator.is_file():
        raise GlobalSnapshotError(f"map generator must be a regular file: {generator}")
    runner(
        [
            sys.executable,
            str(generator),
            str(release_directory / "atlas.geojson"),
            str(release_directory / "atlas.html"),
        ],
        check=True,
    )
    output = release_directory / "atlas.html"
    if output.is_symlink() or not output.is_file() or output.stat().st_size == 0:
        raise GlobalSnapshotError("map generator did not create a non-empty atlas.html")


def _assert_import_counts(
    label: str,
    result: Any,
    *,
    examined: int,
    imported: int,
    skipped: int,
) -> None:
    actual = (
        result.examined_elements,
        result.imported_elements,
        result.skipped_elements,
    )
    expected = (examined, imported, skipped)
    if actual != expected:
        raise GlobalSnapshotError(
            f"{label} import counts do not match the verified source: "
            f"expected {expected}, got {actual}"
        )


def _assert_database_cutoffs(
    connection: sqlite3.Connection,
    *,
    as_of: date,
    recorded_at: datetime,
) -> None:
    future_observations: dict[str, int] = {}
    future_transactions: dict[str, int] = {}
    for table in TEMPORAL_CLAIM_TABLES:
        for row in connection.execute(
            f"SELECT as_of_date, COUNT(*) AS count FROM {table} GROUP BY as_of_date"
        ):
            try:
                observation_date = date.fromisoformat(row["as_of_date"])
            except (TypeError, ValueError) as error:
                raise GlobalSnapshotError(
                    f"{table} contains an invalid as_of_date: {row['as_of_date']}"
                ) from error
            if observation_date > as_of:
                future_observations[table] = (
                    future_observations.get(table, 0) + row["count"]
                )
        for row in connection.execute(
            f"SELECT recorded_at, COUNT(*) AS count FROM {table} GROUP BY recorded_at"
        ):
            transaction_time = _instant(
                _timestamp(row["recorded_at"], f"{table} recorded_at")
            )
            if transaction_time > recorded_at:
                future_transactions[table] = (
                    future_transactions.get(table, 0) + row["count"]
                )

    for table, field in (("evidence", "retrieved_at"), ("entities", "created_at")):
        for row in connection.execute(
            f"SELECT {field}, COUNT(*) AS count FROM {table} GROUP BY {field}"
        ):
            transaction_time = _instant(_timestamp(row[field], f"{table} {field}"))
            if transaction_time > recorded_at:
                future_transactions[table] = (
                    future_transactions.get(table, 0) + row["count"]
                )

    if future_observations:
        details = ", ".join(
            f"{table}={count}" for table, count in sorted(future_observations.items())
        )
        raise GlobalSnapshotError(
            "database contains imported observations later than as_of: " + details
        )
    if future_transactions:
        details = ", ".join(
            f"{table}={count}" for table, count in sorted(future_transactions.items())
        )
        raise GlobalSnapshotError(
            "database contains imported transaction or retrieval times later than "
            f"recorded_at: {details}"
        )


def build_global_snapshot(
    *,
    extraction_manifest: str | Path,
    osm_materialization: str | Path,
    pnnl_input: str | Path,
    pnnl_retrieved_at: str | None,
    wikidata_input: str | Path,
    uva_input: str | Path,
    natural_earth_input: str | Path,
    output_directory: str | Path,
    as_of: str,
    recorded_at: str,
    map_generator: str | Path = DEFAULT_MAP_GENERATOR,
    command_runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> dict[str, Any]:
    """Build one atomic release without network access or cross-source auto-merges."""
    try:
        recorded_at = canonical_read_cutoff(recorded_at, "recorded_at")
    except ValueError as error:
        raise GlobalSnapshotError(str(error)) from error
    destination = Path(os.path.abspath(os.fspath(output_directory)))
    if destination.exists() or destination.is_symlink():
        raise GlobalSnapshotError(f"refusing existing output directory: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        as_of_date = date.fromisoformat(as_of)
    except ValueError as error:
        raise GlobalSnapshotError("as_of must be an ISO date") from error
    recorded_instant = _instant(recorded_at)

    materialization_directory = Path(osm_materialization).resolve()
    materialization = materialize_planet_extract(
        extraction_manifest,
        materialization_directory,
    )
    if materialization.get("state") != "completed":
        raise GlobalSnapshotError("OSM materialization is not complete")
    osm_snapshot_date = materialization.get("snapshot_date")
    if not isinstance(osm_snapshot_date, str):
        raise GlobalSnapshotError("OSM materialization has no snapshot date")
    try:
        parsed_osm_snapshot_date = date.fromisoformat(osm_snapshot_date)
    except ValueError as error:
        raise GlobalSnapshotError("OSM materialization snapshot date is invalid") from error
    if parsed_osm_snapshot_date > as_of_date:
        raise GlobalSnapshotError("OSM snapshot date is later than as_of")
    osm_retrieved_at = _timestamp(
        materialization.get("source_retrieved_at"), "OSM source_retrieved_at"
    )
    osm_provenance = planet_import_provenance(
        materialization_directory, materialization
    )

    pnnl_path = Path(pnnl_input).resolve()
    if pnnl_retrieved_at is None:
        if not pnnl_path.is_dir():
            raise GlobalSnapshotError(
                "pnnl_retrieved_at is required when PNNL input is not a fetch bundle"
            )
        pnnl_retrieved_at = _fetched_at(pnnl_path, "PNNL")
    else:
        pnnl_retrieved_at = _timestamp(pnnl_retrieved_at, "PNNL retrieved_at")
    wikidata_directory = Path(wikidata_input).resolve()
    wikidata_view = validate_wikidata_bundle(wikidata_directory)
    wikidata_retrieved_at = _timestamp(
        wikidata_view.manifest.get("retrieved_completed_at"),
        "Wikidata retrieved_completed_at",
    )
    uva_directory = Path(uva_input).resolve()
    uva_retrieved_at = _fetched_at(uva_directory, "UVA")
    natural_earth_directory = Path(natural_earth_input).resolve()
    natural_earth_retrieved_at = _fetched_at(
        natural_earth_directory, "Natural Earth"
    )
    source_observation_dates = {
        "OpenStreetMap": parsed_osm_snapshot_date,
        "PNNL": date.fromisoformat(PNNL_IM3_VERSION),
        "Wikidata": _instant(wikidata_retrieved_at).date(),
        "UVA": date.fromisoformat(UVA_RELEASE_DATE),
    }
    future_observations = [
        label
        for label, observation_date in source_observation_dates.items()
        if observation_date > as_of_date
    ]
    if future_observations:
        raise GlobalSnapshotError(
            "as_of precedes imported source observations: "
            + ", ".join(future_observations)
        )
    source_retrievals = {
        "OpenStreetMap": osm_retrieved_at,
        "PNNL": pnnl_retrieved_at,
        "Wikidata": wikidata_retrieved_at,
        "UVA": uva_retrieved_at,
        "Natural Earth": natural_earth_retrieved_at,
    }
    later_sources = [
        label
        for label, timestamp in source_retrievals.items()
        if _instant(timestamp) > recorded_instant
    ]
    if later_sources:
        raise GlobalSnapshotError(
            "recorded_at precedes source retrievals: " + ", ".join(later_sources)
        )

    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent)
    )
    connection: sqlite3.Connection | None = None
    try:
        database_path = stage / "atlas.sqlite"
        connection, migrations = initialize(database_path)
        osm_result = OpenStreetMapAdapter().import_file(
            connection,
            materialization_directory / DEFAULT_JSON_FILENAME,
            retrieved_at=osm_retrieved_at,
            provenance=osm_provenance,
        )
        osm_counts = materialization.get("counts") or {}
        exact_counts = osm_counts.get("exact_match_counts") or {}
        exact_total = exact_counts.get("total")
        if isinstance(exact_total, bool) or not isinstance(exact_total, int):
            raise GlobalSnapshotError("OSM materialization exact-match count is invalid")
        _assert_import_counts(
            "OpenStreetMap",
            osm_result,
            examined=exact_total,
            imported=exact_total,
            skipped=0,
        )
        pnnl_result = PNNLIM3GeoPackageAdapter().import_file(
            connection,
            pnnl_path,
            retrieved_at=pnnl_retrieved_at,
        )
        _assert_import_counts(
            "PNNL/IM3",
            pnnl_result,
            examined=PNNL_EXPECTED_SOURCE_ROWS,
            imported=PNNL_EXPECTED_CANDIDATES,
            skipped=PNNL_EXPECTED_DUPLICATE_ROWS,
        )
        wikidata_result = WikidataAdapter().import_file(
            connection,
            wikidata_directory,
            retrieved_at=wikidata_retrieved_at,
        )
        candidate_checkpoint = wikidata_view.manifest.get("candidate_qids")
        wikidata_count = (
            candidate_checkpoint.get("count")
            if isinstance(candidate_checkpoint, Mapping)
            else None
        )
        if isinstance(wikidata_count, bool) or not isinstance(wikidata_count, int):
            raise GlobalSnapshotError("Wikidata candidate count is invalid")
        _assert_import_counts(
            "Wikidata",
            wikidata_result,
            examined=wikidata_count,
            imported=wikidata_count,
            skipped=0,
        )
        uva_result = UVADataverseAdapter().import_file(
            connection,
            uva_directory,
            retrieved_at=uva_retrieved_at,
        )
        _assert_import_counts(
            "UVA DC-SENSE",
            uva_result,
            examined=UVA_EXPECTED_ROWS,
            imported=UVA_EXPECTED_ROWS,
            skipped=0,
        )
        country_result = enrich_administrative_assignments(
            connection,
            natural_earth_directory,
            as_of=as_of,
            recorded_at=recorded_at,
        )
        if country_result.assignments_created != country_result.examined_snapshots:
            raise GlobalSnapshotError(
                "Natural Earth did not create one assignment result per examined snapshot"
            )
        errors = validate_database(connection)
        if errors:
            raise GlobalSnapshotError(
                "database validation failed: " + "; ".join(errors)
            )
        _assert_database_cutoffs(
            connection,
            as_of=as_of_date,
            recorded_at=recorded_instant,
        )
        summary = summarize(connection, as_of=as_of, recorded_at=recorded_at)
        readme = global_release_readme(
            as_of=as_of,
            osm_snapshot_date=osm_snapshot_date,
            osm_integrity=osm_counts,
            summary=summary,
        )
        write_release(
            connection,
            stage,
            as_of=as_of,
            recorded_at=recorded_at,
            readme=readme,
        )
        connection.execute("PRAGMA optimize")
        connection.commit()
        connection.close()
        connection = None

        _add_manifest_file(stage, "atlas.sqlite")
        _generate_map(stage, Path(map_generator).resolve(), command_runner)
        _add_manifest_file(stage, "atlas.html")
        manifest = validate_release_files(stage)
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
        "sources": {
            "openstreetmap_planet": asdict(osm_result),
            "pnnl_im3": asdict(pnnl_result),
            "wikidata": asdict(wikidata_result),
            "uva_dc_sense": asdict(uva_result),
            "natural_earth": asdict(country_result),
        },
        "summary": summary,
        "manifest": manifest,
    }


__all__ = [
    "DEFAULT_EXTRACTION_MANIFEST",
    "DEFAULT_MAP_GENERATOR",
    "DEFAULT_NATURAL_EARTH_INPUT",
    "DEFAULT_OSM_MATERIALIZATION",
    "DEFAULT_PNNL_INPUT",
    "DEFAULT_UVA_INPUT",
    "DEFAULT_WIKIDATA_INPUT",
    "GlobalSnapshotError",
    "build_global_snapshot",
    "global_release_readme",
    "planet_import_provenance",
    "validate_release_files",
]
