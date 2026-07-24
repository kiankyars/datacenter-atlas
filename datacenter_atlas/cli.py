"""Command-line interface for the local atlas registry."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Sequence

from .curated import CuratedOfficialSourceAdapter
from .database import initialize, schema_version
from .epoch import EpochAIAdapter
from .ohsome import OhsomeGeoJSONAdapter
from .osm import OpenStreetMapAdapter
from .publication_release import write_release
from .resolution import (
    candidate_links_to_csv,
    candidate_links_to_json,
    generate_candidate_links,
)
from .service import (
    default_as_of,
    default_recorded_at,
    export_geojson,
    summarize,
    validate_database,
)
from .timestamps import canonical_read_cutoff


def _retrieval_timestamp(value: str) -> str:
    try:
        return canonical_read_cutoff(value, "retrieval timestamp")
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected an ISO date in YYYY-MM-DD form") from exc


def _json_dump(value: object, stream: object | None = None) -> None:
    print(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False),
        file=stream or sys.stdout,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="datacenter-atlas")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-db", help="create or migrate a local SQLite database")
    init_parser.add_argument("--db", required=True, type=Path)

    import_parser = subparsers.add_parser(
        "import-osm", help="import a bounded offline Overpass JSON file"
    )
    import_parser.add_argument("--db", required=True, type=Path)
    import_parser.add_argument("--input", required=True, type=Path)
    import_parser.add_argument(
        "--retrieved-at",
        required=True,
        type=_retrieval_timestamp,
        help="timezone-aware ISO-8601 retrieval timestamp",
    )

    epoch_parser = subparsers.add_parser(
        "import-epoch", help="import a saved Epoch AI data ZIP and optional saved map page"
    )
    epoch_parser.add_argument("--db", required=True, type=Path)
    epoch_parser.add_argument("--input", required=True, type=Path)
    epoch_parser.add_argument("--map-html", type=Path)
    epoch_parser.add_argument(
        "--retrieved-at",
        required=True,
        type=_retrieval_timestamp,
        help="timezone-aware ISO-8601 retrieval timestamp",
    )
    epoch_parser.add_argument("--as-of", required=True, type=_date)

    ohsome_parser = subparsers.add_parser(
        "import-ohsome", help="import a verified saved ohsome shard bundle"
    )
    ohsome_parser.add_argument("--db", required=True, type=Path)
    ohsome_parser.add_argument("--input", required=True, type=Path)
    ohsome_parser.add_argument(
        "--retrieved-at",
        required=True,
        type=_retrieval_timestamp,
        help="timezone-aware ISO-8601 retrieval timestamp",
    )
    ohsome_parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="explicitly import only completed shards from an incomplete manifest",
    )

    curated_parser = subparsers.add_parser(
        "import-curated", help="import one strict offline official-source record"
    )
    curated_parser.add_argument("--db", required=True, type=Path)
    curated_parser.add_argument("--input", required=True, type=Path)
    curated_parser.add_argument(
        "--retrieved-at",
        required=True,
        type=_retrieval_timestamp,
        help="must exactly match every evidence retrieved_at in the record",
    )

    export_parser = subparsers.add_parser("export-geojson", help="export a reproducible atlas view")
    export_parser.add_argument("--db", required=True, type=Path)
    export_parser.add_argument("--output", required=True, help="output path, or - for stdout")
    export_parser.add_argument("--as-of", type=_date)
    export_parser.add_argument("--recorded-at", type=_retrieval_timestamp)

    release_parser = subparsers.add_parser(
        "export-release", help="write an auditable CSV, GeoJSON, evidence, and manifest bundle"
    )
    release_parser.add_argument("--db", required=True, type=Path)
    release_parser.add_argument("--output-dir", required=True, type=Path)
    release_parser.add_argument("--as-of", type=_date)
    release_parser.add_argument("--recorded-at", type=_retrieval_timestamp)
    release_parser.add_argument(
        "--publication-contract-version", choices=(1, 2, 3, 4), default=2, type=int
    )

    summary_parser = subparsers.add_parser("summary", help="print coverage and classification counts")
    summary_parser.add_argument("--db", required=True, type=Path)
    summary_parser.add_argument("--as-of", type=_date)
    summary_parser.add_argument("--recorded-at", type=_retrieval_timestamp)

    validate_parser = subparsers.add_parser("validate", help="check integrity and atlas invariants")
    validate_parser.add_argument("--db", required=True, type=Path)

    resolution_parser = subparsers.add_parser(
        "resolution-report", help="write read-only cross-source match candidates"
    )
    resolution_parser.add_argument("--db", required=True, type=Path)
    resolution_parser.add_argument("--output", required=True, type=Path)
    resolution_parser.add_argument("--format", choices=("json", "csv"), default="json")
    resolution_parser.add_argument("--as-of", type=_date)
    resolution_parser.add_argument("--recorded-at", type=_retrieval_timestamp)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    connection, installed = initialize(args.db)
    try:
        if args.command == "init-db":
            _json_dump(
                {
                    "database": str(args.db.resolve()),
                    "installed_migrations": installed,
                    "schema_version": schema_version(connection),
                }
            )
            return 0
        if args.command == "import-osm":
            result = OpenStreetMapAdapter().import_file(
                connection, args.input, retrieved_at=args.retrieved_at
            )
            _json_dump(asdict(result))
            return 0
        if args.command == "import-epoch":
            result = EpochAIAdapter().import_file(
                connection,
                args.input,
                retrieved_at=args.retrieved_at,
                as_of_date=args.as_of,
                map_html=args.map_html,
            )
            _json_dump(asdict(result))
            return 0
        if args.command == "import-ohsome":
            result = OhsomeGeoJSONAdapter().import_path(
                connection,
                args.input,
                retrieved_at=args.retrieved_at,
                allow_partial=args.allow_partial,
            )
            _json_dump(asdict(result))
            return 0
        if args.command == "import-curated":
            result = CuratedOfficialSourceAdapter().import_file(
                connection, args.input, retrieved_at=args.retrieved_at
            )
            _json_dump(asdict(result))
            return 0
        if args.command == "export-geojson":
            document = export_geojson(
                connection, as_of=args.as_of, recorded_at=args.recorded_at
            )
            encoded = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            if args.output == "-":
                sys.stdout.write(encoded)
            else:
                output = Path(args.output)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(encoded, encoding="utf-8")
                _json_dump({"features": len(document["features"]), "output": str(output.resolve())})
            return 0
        if args.command == "summary":
            _json_dump(summarize(connection, as_of=args.as_of, recorded_at=args.recorded_at))
            return 0
        if args.command == "export-release":
            _json_dump(
                write_release(
                    connection,
                    args.output_dir,
                    as_of=args.as_of or default_as_of(),
                    recorded_at=args.recorded_at or default_recorded_at(),
                    publication_contract_version=args.publication_contract_version,
                )
            )
            return 0
        if args.command == "validate":
            errors = validate_database(connection)
            _json_dump({"errors": errors, "valid": not errors})
            return 0 if not errors else 1
        if args.command == "resolution-report":
            as_of = args.as_of or default_as_of()
            recorded_at = canonical_read_cutoff(
                args.recorded_at or default_recorded_at()
            )
            candidates = generate_candidate_links(
                connection, as_of=as_of, recorded_at=recorded_at
            )
            encoded = (
                candidate_links_to_json(candidates)
                if args.format == "json"
                else candidate_links_to_csv(candidates)
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
            _json_dump(
                {
                    "as_of": as_of,
                    "candidates": len(candidates),
                    "format": args.format,
                    "output": str(args.output.resolve()),
                    "recorded_at": recorded_at,
                }
            )
            return 0
    finally:
        connection.close()
    raise AssertionError(f"unhandled command: {args.command}")
