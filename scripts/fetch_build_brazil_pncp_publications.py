#!/usr/bin/env python3
"""Capture, build, or offline-validate the bounded Brazil PNCP release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.brazil_pncp_publications import (
    EXPECTED_NETWORK_REQUESTS,
    MANIFEST_FILENAME,
    RELEASE_ID,
    BrazilPNCPError,
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
    mode.add_argument("--capture-only", action="store_true")
    mode.add_argument("--validate-only", action="store_true")
    result.add_argument("--capture-directory", type=Path)
    result.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--timeout", type=float, default=120.0)
    result.add_argument("--max-attempts", type=int, default=4)
    result.add_argument("--pacing-seconds", type=float, default=1.0)
    result.add_argument(
        "--freeze", action=argparse.BooleanOptionalAction, default=True
    )
    return result


def _summary(bundle: dict[str, object], output: Path, mode: str) -> dict[str, object]:
    assessment = bundle["assessment"]
    assert isinstance(assessment, dict)
    return {
        "classification_counts": assessment["classification_counts"],
        "frozen": is_frozen_release(output),
        "manifest_sha256": sha256_bytes((output / MANIFEST_FILENAME).read_bytes()),
        "mode": mode,
        "network_requests": 0,
        "output": str(output),
        "publication_count": assessment["publication_count"],
        "release_id": RELEASE_ID,
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.capture_only:
        if arguments.capture_directory is None:
            raise BrazilPNCPError("--capture-directory is required for capture-only")
        capture_live_sources(
            arguments.capture_directory,
            timeout=arguments.timeout,
            max_attempts=arguments.max_attempts,
            pacing_seconds=arguments.pacing_seconds,
        )
        print(
            json.dumps(
                {
                    "capture": str(arguments.capture_directory),
                    "mode": "live_capture_only",
                    "network_requests": EXPECTED_NETWORK_REQUESTS,
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
        print(json.dumps(_summary(bundle, arguments.output, "offline_validate"), indent=2, sort_keys=True))
        return 0
    if arguments.capture_directory is None:
        raise BrazilPNCPError(
            "a quarantined --capture-directory is required; live capture and "
            "release build are intentionally separate"
        )
    write_release_bundle(
        arguments.definition,
        arguments.capture_directory,
        arguments.output,
        freeze=arguments.freeze,
    )
    bundle = validate_release_bundle(arguments.output, definition_path=arguments.definition)
    print(json.dumps(_summary(bundle, arguments.output, "offline_build_and_validate"), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
