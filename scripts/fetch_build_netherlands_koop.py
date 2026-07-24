#!/usr/bin/env python3
"""Capture, build, or offline-validate the Netherlands KOOP review lane."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.netherlands_koop import (
    MANIFEST_FILENAME,
    RELEASE_ID,
    NetherlandsKoopError,
    capture_live_sources,
    is_frozen_release,
    sha256_bytes,
    validate_release_bundle,
    write_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "source_assessments" / RELEASE_ID


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    mode = result.add_mutually_exclusive_group()
    mode.add_argument(
        "--capture-only",
        action="store_true",
        help="fetch a new paced live capture and emit a definition candidate",
    )
    mode.add_argument(
        "--validate-only",
        action="store_true",
        help="validate and reproduce an existing frozen bundle with zero network requests",
    )
    result.add_argument("--capture-directory", type=Path)
    result.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--timeout", type=float, default=120.0)
    result.add_argument("--max-attempts", type=int, default=4)
    result.add_argument("--pacing-seconds", type=float, default=0.35)
    result.add_argument(
        "--freeze",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="freeze a built release 0555/0444 (default: true)",
    )
    return result


def _capture(arguments: argparse.Namespace) -> Path:
    if arguments.capture_directory is None:
        raise NetherlandsKoopError("--capture-directory is required for capture-only")
    capture = capture_live_sources(
        arguments.capture_directory,
        timeout=arguments.timeout,
        max_attempts=arguments.max_attempts,
        pacing_seconds=arguments.pacing_seconds,
    )
    candidate = capture / "definition-candidate.json"
    checkpoint = {
        "bytes": candidate.stat().st_size,
        "sha256": sha256_bytes(candidate.read_bytes()),
    }
    print(
        json.dumps(
            {
                "capture": str(capture),
                "definition_candidate": str(candidate),
                "definition_candidate_checkpoint": checkpoint,
                "mode": "live_capture_only",
                "network_requests": 12,
                "release_id": RELEASE_ID,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return capture


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.capture_only:
        _capture(arguments)
        return 0
    if arguments.validate_only:
        bundle = validate_release_bundle(
            arguments.output, definition_path=arguments.definition
        )
        manifest_raw = (arguments.output / MANIFEST_FILENAME).read_bytes()
        print(
            json.dumps(
                {
                    "classifications": bundle["assessment"][
                        "classification_counts"
                    ],
                    "manifest_sha256": sha256_bytes(manifest_raw),
                    "mode": "offline_validate_and_reproduce",
                    "network_requests": 0,
                    "observations": len(bundle["observations"]),
                    "output": str(arguments.output),
                    "release_id": RELEASE_ID,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if arguments.capture_directory is not None:
        capture = arguments.capture_directory
        output = write_release_bundle(
            arguments.definition,
            capture,
            arguments.output,
            freeze=arguments.freeze,
        )
    else:
        with tempfile.TemporaryDirectory(prefix="netherlands-koop-capture-") as temporary:
            capture = capture_live_sources(
                Path(temporary) / "capture",
                timeout=arguments.timeout,
                max_attempts=arguments.max_attempts,
                pacing_seconds=arguments.pacing_seconds,
            )
            output = write_release_bundle(
                arguments.definition,
                capture,
                arguments.output,
                freeze=arguments.freeze,
            )
    bundle = validate_release_bundle(output, definition_path=arguments.definition)
    manifest_raw = (output / MANIFEST_FILENAME).read_bytes()
    print(
        json.dumps(
            {
                "classifications": bundle["assessment"]["classification_counts"],
                "frozen": is_frozen_release(output),
                "manifest_sha256": sha256_bytes(manifest_raw),
                "mode": "build_then_offline_validate",
                "network_requests": (
                    0 if arguments.capture_directory is not None else 12
                ),
                "observations": len(bundle["observations"]),
                "output": str(output),
                "release_id": RELEASE_ID,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
