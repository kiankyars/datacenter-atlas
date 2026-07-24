#!/usr/bin/env python3
"""Rebuild and validate the frozen open-seed v59 twice offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.open_seed_release_v4 import validate_open_seed_release_v4


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--definition", required=True, type=Path)
    result.add_argument("--release", required=True, type=Path)
    result.add_argument("--allow-mutable", action="store_true")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    manifest = validate_open_seed_release_v4(
        arguments.definition,
        arguments.release,
        require_frozen=not arguments.allow_mutable,
    )
    print(
        json.dumps(
            {
                "entities": manifest["entities"],
                "evidence_records": manifest["evidence_records"],
                "lifecycle_freshness_records": manifest[
                    "lifecycle_freshness_records"
                ],
                "manifest_sha256": hashlib.sha256(
                    (arguments.release / "manifest.json").read_bytes()
                ).hexdigest(),
                "mode": "offline_double_rebuild_validate",
                "network_requests": 0,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
