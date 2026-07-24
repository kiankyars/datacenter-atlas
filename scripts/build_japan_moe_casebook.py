#!/usr/bin/env python3
"""Build the Japan MOE casebook auxiliary release without network access."""

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
    SOURCE_ARTIFACT_MANIFEST_SHA256,
    SOURCE_ARTIFACT_TREE_SHA256,
    canonical_json,
    default_source_artifact_path,
    source_definition,
    validate_release_bundle,
    write_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ARTIFACT = default_source_artifact_path()
DEFAULT_OUTPUT = PROJECT_ROOT / "source_assessments" / RELEASE_ID
DEFAULT_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--source-artifact", type=Path, default=DEFAULT_SOURCE_ARTIFACT)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    return result


def _write_definition(path: Path) -> None:
    expected = canonical_json(source_definition())
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
            raise ValueError("existing source definition differs")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(expected)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    _write_definition(arguments.definition)
    write_release_bundle(arguments.source_artifact, arguments.output)
    bundle = validate_release_bundle(
        arguments.output,
        definition_path=arguments.definition,
        source_artifact_path=arguments.source_artifact,
    )
    print(
        json.dumps(
            {
                "build_mode": "offline_from_frozen_structured_source_artifact",
                "build_network_requests": 0,
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
                    arguments.output / "manifest.sha256"
                ).read_text(encoding="ascii").split()[0],
                "release_tree_sha256": bundle["manifest"]["tree_sha256"],
                "source_artifact_manifest_sha256": SOURCE_ARTIFACT_MANIFEST_SHA256,
                "source_artifact_tree_sha256": SOURCE_ARTIFACT_TREE_SHA256,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
