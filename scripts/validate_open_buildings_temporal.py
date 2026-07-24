#!/usr/bin/env python3
"""Validate Open Buildings source and review bundles entirely offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.open_buildings_temporal import (
    validate_candidate_bundle,
    validate_source_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ATLAS = (
    PROJECT_ROOT / "releases" / "2026-07-18-global-open-v3" / "atlas.geojson"
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--source", required=True, type=Path)
    result.add_argument("--review", required=True, type=Path)
    result.add_argument("--atlas", type=Path, default=DEFAULT_ATLAS)
    result.add_argument(
        "--atlas-manifest",
        type=Path,
        help="release manifest (default: manifest.json beside --atlas)",
    )
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    source = validate_source_bundle(arguments.source)
    review = validate_candidate_bundle(
        arguments.review,
        source_directory=arguments.source,
        atlas_path=arguments.atlas,
        atlas_manifest_path=arguments.atlas_manifest,
    )
    print(
        json.dumps(
            {
                "network_requests": 0,
                "raster_dependencies_required": False,
                "source_manifest_sha256": _sha256(arguments.source / "manifest.json"),
                "review_manifest_sha256": _sha256(arguments.review / "manifest.json"),
                "source_years": len(source["source_files"]),
                "counts": review["counts"],
                "source_family_constraint": review["source_family_constraint"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
