#!/usr/bin/env python3
"""Capture, build, or offline-validate the New Zealand Fast-track lane."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.new_zealand_fast_track import (
    MANIFEST_FILENAME,
    RELEASE_ID,
    NewZealandFastTrackError,
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
        help=(
            "assemble verified browser extracts and fetch three MfE pages; "
            "emit a definition candidate"
        ),
    )
    mode.add_argument(
        "--validate-only",
        action="store_true",
        help="validate and reproduce an existing bundle with zero network requests",
    )
    result.add_argument("--browser-extract-directory", type=Path)
    result.add_argument("--capture-directory", type=Path)
    result.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--timeout", type=float, default=90.0)
    result.add_argument("--max-attempts", type=int, default=4)
    result.add_argument("--pacing-seconds", type=float, default=0.4)
    result.add_argument(
        "--freeze",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="freeze a built release 0555/0444 (default: true)",
    )
    return result


def _capture(arguments: argparse.Namespace, destination: Path) -> Path:
    if arguments.browser_extract_directory is None:
        raise NewZealandFastTrackError(
            "--browser-extract-directory is required for a live capture"
        )
    return capture_live_sources(
        destination,
        arguments.browser_extract_directory,
        timeout=arguments.timeout,
        max_attempts=arguments.max_attempts,
        pacing_seconds=arguments.pacing_seconds,
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.capture_only:
        if arguments.capture_directory is None:
            raise NewZealandFastTrackError(
                "--capture-directory is required for --capture-only"
            )
        capture = _capture(arguments, arguments.capture_directory)
        candidate = capture / "definition-candidate.json"
        print(
            json.dumps(
                {
                    "browser_rendered_requests": 2,
                    "capture": str(capture),
                    "definition_candidate": str(candidate),
                    "definition_candidate_checkpoint": {
                        "bytes": candidate.stat().st_size,
                        "sha256": sha256_bytes(candidate.read_bytes()),
                    },
                    "direct_http_requests": 3,
                    "mode": "live_capture_only",
                    "network_requests_observed": 5,
                    "release_id": RELEASE_ID,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if arguments.validate_only:
        bundle = validate_release_bundle(
            arguments.output, definition_path=arguments.definition
        )
        manifest_raw = (arguments.output / MANIFEST_FILENAME).read_bytes()
        print(
            json.dumps(
                {
                    "candidate_classifications": bundle["assessment"][
                        "candidate_classification_counts"
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
        if arguments.browser_extract_directory is not None:
            raise NewZealandFastTrackError(
                "do not pass --browser-extract-directory when building from an "
                "existing --capture-directory"
            )
        output = write_release_bundle(
            arguments.definition,
            arguments.capture_directory,
            arguments.output,
            freeze=arguments.freeze,
        )
        network_requests = 0
    else:
        if arguments.browser_extract_directory is None:
            raise NewZealandFastTrackError(
                "provide --capture-directory or --browser-extract-directory"
            )
        with tempfile.TemporaryDirectory(
            prefix="new-zealand-fast-track-capture-"
        ) as temporary:
            capture = _capture(arguments, Path(temporary) / "capture")
            output = write_release_bundle(
                arguments.definition,
                capture,
                arguments.output,
                freeze=arguments.freeze,
            )
        network_requests = 5
    bundle = validate_release_bundle(output, definition_path=arguments.definition)
    manifest_raw = (output / MANIFEST_FILENAME).read_bytes()
    print(
        json.dumps(
            {
                "candidate_classifications": bundle["assessment"][
                    "candidate_classification_counts"
                ],
                "frozen": is_frozen_release(output),
                "manifest_sha256": sha256_bytes(manifest_raw),
                "mode": "build_then_offline_validate",
                "network_requests": network_requests,
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
