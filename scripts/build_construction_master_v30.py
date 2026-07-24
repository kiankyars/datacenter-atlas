#!/usr/bin/env python3
"""Prepare, publish, or offline-validate the immutable v30 construction master."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from datacenter_atlas.construction_master_v30 import (  # noqa: E402
    BUNDLE_PATH,
    DEFINITION_PATH,
    ConstructionMasterV30Error,
    discard_construction_master_v30_stage,
    prepare_construction_master_v30,
    publish_construction_master_v30,
    validate_construction_master_v30,
)
from datacenter_atlas.open_seed_v56 import tree_digest  # noqa: E402


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--publish", action="store_true")
    mode.add_argument("--validate-only", action="store_true")
    result.add_argument(
        "--discard-prepared",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="discard a private --prepare-only transaction after reporting pins",
    )
    return result


def _checkpoint(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "bytes": len(raw),
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.prepare_only:
            transaction, definition, bundle = prepare_construction_master_v30()
            manifest = validate_construction_master_v30(
                bundle, definition_path=definition, reproduce=True
            )
            result = {
                "bundle": str(bundle),
                "definition": _checkpoint(definition),
                "final_bundle_absent": not BUNDLE_PATH.exists(),
                "final_definition_absent": not DEFINITION_PATH.exists(),
                "manifest": _checkpoint(bundle / "manifest.json"),
                "row_counts": manifest["row_counts"],
                "transaction": str(transaction),
                "tree_sha256": tree_digest(bundle),
            }
            print(json.dumps(result, sort_keys=True))
            if arguments.discard_prepared:
                discard_construction_master_v30_stage(transaction)
        elif arguments.publish:
            manifest = publish_construction_master_v30()
            print(
                json.dumps(
                    {
                        "bundle": str(BUNDLE_PATH),
                        "definition": str(DEFINITION_PATH),
                        "row_counts": manifest["row_counts"],
                        "tree_sha256": tree_digest(BUNDLE_PATH),
                    },
                    sort_keys=True,
                )
            )
        else:
            manifest = validate_construction_master_v30(
                BUNDLE_PATH, definition_path=DEFINITION_PATH, reproduce=True
            )
            print(
                json.dumps(
                    {
                        "bundle": str(BUNDLE_PATH),
                        "definition": str(DEFINITION_PATH),
                        "row_counts": manifest["row_counts"],
                        "tree_sha256": tree_digest(BUNDLE_PATH),
                    },
                    sort_keys=True,
                )
            )
    except (ConstructionMasterV30Error, OSError, SystemExit) as error:
        print(f"construction-master-v30 error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
