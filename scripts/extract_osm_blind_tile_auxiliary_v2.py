#!/usr/bin/env python3
"""Build or validate the geometry-complete full-Planet OSM auxiliary v2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(PROJECT_ROOT))

from datacenter_atlas import osm_blind_tile_auxiliary_v2 as auxiliary  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=auxiliary.PLANET_PATH)
    parser.add_argument(
        "--fetch-manifest", type=Path, default=auxiliary.PLANET_FETCH_MANIFEST
    )
    parser.add_argument(
        "--output-directory", type=Path, default=auxiliary.OUTPUT_DIRECTORY
    )
    parser.add_argument("--osmium", default="osmium")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument(
        "--skip-deep-source-hash",
        action="store_true",
        help="validate the frozen derivative without rereading the full Planet",
    )
    parser.add_argument(
        "--skip-post-source-hash",
        action="store_true",
        help="development-only: do not rehash the Planet after extraction",
    )
    arguments = parser.parse_args(argv)
    if arguments.dry_run and arguments.verify_only:
        parser.error("--dry-run and --verify-only are mutually exclusive")
    if arguments.verify_only and arguments.skip_post_source_hash:
        parser.error("--skip-post-source-hash applies only to extraction")
    try:
        osmium = auxiliary.resolve_osmium(arguments.osmium)
        if arguments.dry_run:
            document = auxiliary.build_plan(
                arguments.source,
                arguments.fetch_manifest,
                arguments.output_directory,
                osmium_executable=osmium,
            ).contract_document()
        elif arguments.verify_only:
            document = auxiliary.validate_bundle(
                arguments.output_directory,
                source_path=arguments.source,
                fetch_manifest_path=arguments.fetch_manifest,
                osmium_executable=osmium,
                deep_source_hash=not arguments.skip_deep_source_hash,
            )
        else:
            document = auxiliary.extract_auxiliary(
                arguments.source,
                arguments.fetch_manifest,
                arguments.output_directory,
                osmium_executable=osmium,
                invocation=[
                    sys.executable,
                    str(Path(__file__).resolve()),
                    *(argv or sys.argv[1:]),
                ],
                recheck_source_hash_after=not arguments.skip_post_source_hash,
            )
    except (auxiliary.OsmBlindTileAuxiliaryV2Error, OSError) as error:
        parser.exit(1, f"error: {error}\n")
    summary = {
        "candidate_independent": True,
        "dry_run": arguments.dry_run,
        "output_directory": str(arguments.output_directory.resolve()),
        "production_frame_built": False,
        "selected_objects": document.get("selection_statistics", {})
        .get("final", {})
        .get("selected_objects"),
        "state": document.get("state", "contract_only"),
        "unresolved_geometry_objects": document.get("selection_statistics", {})
        .get("final", {})
        .get("unresolved_geometry_objects"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
