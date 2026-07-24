#!/usr/bin/env python3
"""Capture, build, or offline-validate explicit-ID catalog reselection v2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.satellite_catalog_reselection_v2 import (
    build_catalog_reselection_v2,
    capture_grid_header_evidence_v2,
    validate_catalog_reselection_v2,
)


def _inputs(command: argparse.ArgumentParser) -> None:
    command.add_argument("--queue-dir", required=True, type=Path)
    command.add_argument("--source-catalog-batch-dir", required=True, type=Path)
    command.add_argument(
        "--queue-id",
        required=True,
        action="append",
        dest="queue_ids",
        help=(
            "Explicit edge-audit queue ID; repeat for each candidate. "
            "Input order and duplicate occurrences are canonicalized to queue order."
        ),
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)

    capture = commands.add_parser(
        "capture-headers",
        help="Explicitly open selected COG metadata; performs no pixel reads",
    )
    _inputs(capture)
    capture.add_argument("--output-file", required=True, type=Path)
    capture.add_argument("--captured-at", required=True)

    build = commands.add_parser(
        "build",
        help="Build atomically and freeze with no network access",
    )
    _inputs(build)
    build.add_argument("--grid-header-evidence", required=True, type=Path)
    build.add_argument("--output-dir", required=True, type=Path)
    build.add_argument("--generated-at", required=True)

    validate = commands.add_parser(
        "validate",
        help="Validate a frozen closed-world release with no network access",
    )
    _inputs(validate)
    validate.add_argument("--release-dir", required=True, type=Path)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.command == "capture-headers":
        document = capture_grid_header_evidence_v2(
            arguments.queue_dir,
            arguments.source_catalog_batch_dir,
            arguments.queue_ids,
            arguments.output_file,
            captured_at=arguments.captured_at,
        )
        payload = {
            "file": str(arguments.output_file.resolve()),
            "captured_at": document["captured_at"],
            "candidate_queue_ids": document["candidate_queue_ids"],
            "asset_open_operations": document["asset_open_operations"],
            "scope": document["scope"],
        }
    elif arguments.command == "build":
        document = build_catalog_reselection_v2(
            arguments.queue_dir,
            arguments.source_catalog_batch_dir,
            arguments.queue_ids,
            arguments.grid_header_evidence,
            arguments.output_dir,
            generated_at=arguments.generated_at,
        )
        payload = {
            "manifest": str((arguments.output_dir / "batch-manifest.json").resolve()),
            "state": document["state"],
            "summary": document["summary"],
            "scope": document["scope"],
        }
    else:
        document = validate_catalog_reselection_v2(
            arguments.queue_dir,
            arguments.source_catalog_batch_dir,
            arguments.queue_ids,
            arguments.release_dir,
        )
        payload = {
            "manifest": str((arguments.release_dir / "batch-manifest.json").resolve()),
            "state": document["state"],
            "summary": document["summary"],
            "scope": document["scope"],
        }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
