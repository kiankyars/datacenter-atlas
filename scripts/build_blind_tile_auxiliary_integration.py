#!/usr/bin/env python3
"""Build or resume a gated blind-tile auxiliary integration bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(PROJECT_ROOT))

from datacenter_atlas import blind_tile_auxiliary_integration as integration


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-database", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=10_000)
    parser.add_argument("--maximum-batches", type=int)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--allow-mutable-fixture", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        if arguments.verify_only:
            result = integration.validate_integration_bundle(
                arguments.output,
                definition_path=arguments.definition,
                require_frozen=not arguments.allow_mutable_fixture,
            )
        else:
            result = integration.build_integration_bundle(
                arguments.output,
                definition_path=arguments.definition,
                work_database_path=arguments.work_database,
                batch_size=arguments.batch_size,
                maximum_batches=arguments.maximum_batches,
                freeze=not arguments.allow_mutable_fixture,
            )
    except Exception as error:
        parser.exit(1, f"error: {error}\n")
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
