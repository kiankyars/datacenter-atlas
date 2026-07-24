#!/usr/bin/env python3
"""Prepare, validate, or discard the private v32 construction-map candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from datacenter_atlas.construction_map_v32 import (
    BUNDLE,
    DEFINITION,
    MAP_GENERATED_AT,
    ConstructionMapV32Error,
    discard_candidate_construction_map_v32,
    prepare_candidate_construction_map_v32,
    validate_candidate_construction_map_v32,
)
from datacenter_atlas.open_seed_v56 import tree_digest


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--validate-private", action="store_true")
    mode.add_argument("--discard-private", action="store_true")
    result.add_argument("--definition-stage", type=Path)
    result.add_argument("--bundle-stage", type=Path)
    result.add_argument("--generated-at", default=MAP_GENERATED_AT)
    return result


def _checkpoint(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "bytes": len(raw),
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _require_stages(arguments: argparse.Namespace) -> tuple[Path, Path]:
    if arguments.definition_stage is None or arguments.bundle_stage is None:
        raise ConstructionMapV32Error(
            "private validation or discard requires both stage paths"
        )
    return arguments.definition_stage.resolve(), arguments.bundle_stage.resolve()


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.prepare_only:
            definition, bundle = prepare_candidate_construction_map_v32(
                arguments.generated_at
            )
        else:
            definition, bundle = _require_stages(arguments)
            if arguments.discard_private:
                discard_candidate_construction_map_v32(definition, bundle)
                print(json.dumps({"discarded": True}, sort_keys=True))
                return 0
        validation_wall_clock = datetime.fromisoformat(
            arguments.generated_at
        ).astimezone(UTC)
        validate_candidate_construction_map_v32(
            definition,
            bundle,
            validation_wall_clock=validation_wall_clock,
        )
        result = {
            "bundle": str(bundle),
            "definition": _checkpoint(definition),
            "final_bundle_absent": not BUNDLE.exists(),
            "final_definition_absent": not DEFINITION.exists(),
            "manifest": _checkpoint(bundle / "manifest.json"),
            "projection": json.loads((bundle / "coverage.json").read_bytes())[
                "projection"
            ],
            "tree_sha256": tree_digest(bundle),
        }
        print(json.dumps(result, sort_keys=True))
    except (ConstructionMapV32Error, OSError, SystemExit) as error:
        print(f"construction-map-v32 error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
