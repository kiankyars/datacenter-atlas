#!/usr/bin/env python3
"""Prepare or validate the private/prepublication v32 construction master."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from datacenter_atlas.construction_master_v32 import (
    BUNDLE_PATH,
    DEFINITION_PATH,
    ConstructionMasterV32Error,
    discard_construction_master_v32_stage,
    prepare_construction_master_v32,
    validate_construction_master_v32,
)
from datacenter_atlas.open_seed_v56 import tree_digest


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--validate-private", action="store_true")
    result.add_argument("--transaction", type=Path)
    result.add_argument(
        "--discard-prepared",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    return result


def _checkpoint(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "bytes": len(raw),
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _report(transaction: Path, definition: Path, bundle: Path) -> dict[str, object]:
    manifest = validate_construction_master_v32(
        bundle,
        definition_path=definition,
        reproduce=True,
        allow_prospective_identity=False,
    )
    return {
        "bundle": str(bundle),
        "definition": _checkpoint(definition),
        "final_bundle_absent": not BUNDLE_PATH.exists(),
        "final_definition_absent": not DEFINITION_PATH.exists(),
        "manifest": _checkpoint(bundle / "manifest.json"),
        "row_counts": manifest["row_counts"],
        "transaction": str(transaction),
        "tree_sha256": tree_digest(bundle),
    }


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.prepare_only:
            transaction, definition, bundle = prepare_construction_master_v32()
        else:
            if arguments.transaction is None:
                raise ConstructionMasterV32Error(
                    "--validate-private requires --transaction"
                )
            transaction = arguments.transaction.resolve()
            definition = transaction / DEFINITION_PATH.name
            bundle = transaction / "bundle"
        result = _report(transaction, definition, bundle)
        print(json.dumps(result, sort_keys=True))
        if arguments.discard_prepared:
            discard_construction_master_v32_stage(transaction)
    except (ConstructionMasterV32Error, OSError, SystemExit) as error:
        print(f"construction-master-v32 error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
