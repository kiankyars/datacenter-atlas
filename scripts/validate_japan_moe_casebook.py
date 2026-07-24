#!/usr/bin/env python3
"""Validate a Japan MOE casebook release entirely offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.japan_moe_casebook import (
    RELEASE_ID,
    default_source_artifact_path,
    validate_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID
DEFAULT_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"
DEFAULT_SOURCE_ARTIFACT = default_source_artifact_path()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--release", type=Path, default=DEFAULT_RELEASE)
    result.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    result.add_argument("--source-artifact", type=Path, default=DEFAULT_SOURCE_ARTIFACT)
    result.add_argument(
        "--allow-writable-release",
        action="store_true",
        help="validate a draft copy without enforcing 0444/0555 frozen modes",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    bundle = validate_release_bundle(
        arguments.release,
        definition_path=arguments.definition,
        source_artifact_path=arguments.source_artifact,
        require_frozen=not arguments.allow_writable_release,
    )
    print(
        json.dumps(
            {
                "case_observations": len(bundle["observations"]),
                "detail_cases": bundle["reconciliation"]["detail_case_count"],
                "direct_request_attempts": bundle["retrieval"]["direct_request_attempts"],
                "matched_cases": bundle["reconciliation"]["matched_count"],
                "metric_observations": len(bundle["metrics"]),
                "overview_cases": bundle["reconciliation"]["overview_case_count"],
                "physical_site_count": bundle["reconciliation"]["physical_site_count"],
                "program_observations": len(bundle["programs"]),
                "release_id": RELEASE_ID,
                "release_manifest_sha256": (
                    arguments.release / "manifest.sha256"
                ).read_text(encoding="ascii").split()[0],
                "release_tree_sha256": bundle["manifest"]["tree_sha256"],
                "status": bundle["assessment"]["atlas_decision"]["status"],
                "validation_mode": (
                    "offline_writable_release_allowed"
                    if arguments.allow_writable_release
                    else "offline_frozen_release_required"
                ),
                "validation_network_requests": 0,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
