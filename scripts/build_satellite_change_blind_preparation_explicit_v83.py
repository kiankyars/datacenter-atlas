#!/usr/bin/env python3
"""Publish or validate the identity-blind v83 68-proposal image bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.satellite_change_blind_preparation_explicit_v83 import (
    OUTPUT_PATH,
    blind_image_paths,
    publish_blind_preparation,
    suggested_generated_at,
    validate_blind_preparation,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--generated-at", default=suggested_generated_at())
    result.add_argument("--validate-only", action="store_true")
    result.add_argument("--list-blind-paths", action="store_true")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.validate_only:
        result = validate_blind_preparation(OUTPUT_PATH)
    else:
        result = publish_blind_preparation(arguments.generated_at, OUTPUT_PATH)
    payload: dict[str, object] = {
        "generated_at": result["generated_at"],
        "manifest_sha256": hashlib.sha256(
            (OUTPUT_PATH / "manifest.json").read_bytes()
        ).hexdigest(),
        "output": str(OUTPUT_PATH),
        "preparation_id": result["preparation_id"],
        "summary": result["summary"],
        "tree_inventory": result["tree_inventory"],
        "validated": True,
    }
    if arguments.list_blind_paths:
        payload["blind_paths"] = {
            blind_id: [str(path) for path in paths]
            for blind_id, paths in blind_image_paths(OUTPUT_PATH).items()
        }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
