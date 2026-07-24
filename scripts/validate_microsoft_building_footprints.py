#!/usr/bin/env python3
"""Validate and reproduce the frozen Microsoft buildings lane offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.microsoft_building_footprints import validate_bundle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEFINITION = (
    PROJECT_ROOT
    / "sources"
    / "microsoft-global-ml-building-footprints-2026-07-18-v1.json"
)
DEFAULT_BUNDLE = (
    PROJECT_ROOT
    / "source_cache"
    / "microsoft-global-ml-buildings-2026-07-18-v1"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    result.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    manifest = validate_bundle(
        arguments.bundle,
        definition_path=arguments.definition,
        require_frozen=True,
    )
    print(
        json.dumps(
            {
                "bundle": str(arguments.bundle.resolve()),
                "manifest_sha256": _sha256(arguments.bundle / "manifest.json"),
                "network_requests": 0,
                "offline_byte_reproduction": True,
                "review_policy": manifest["review_policy"],
                "totals": manifest["totals"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
