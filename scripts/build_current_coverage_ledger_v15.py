#!/usr/bin/env python3
"""Generate, build, or offline-validate current-coverage ledger v15."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from datacenter_atlas.current_coverage_v15 import (  # noqa: E402
    CurrentCoverageV15Error,
    validate_current_coverage_ledger_v15,
    write_current_coverage_ledger_v15,
    write_v15_definition,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--definition",
        type=Path,
        default=PACKAGE_ROOT / "sources/current-coverage-2026-07-20-v15.json",
    )
    result.add_argument(
        "--output",
        type=Path,
        default=PACKAGE_ROOT / "current_coverage_ledgers/2026-07-20-v15",
    )
    result.add_argument("--emit-definition", action="store_true")
    result.add_argument("--validate-only", action="store_true")
    result.add_argument(
        "--freeze", action=argparse.BooleanOptionalAction, default=True
    )
    return result


def main() -> int:
    arguments = parser().parse_args()
    if arguments.emit_definition and arguments.validate_only:
        print(
            "current-coverage-v15 error: --emit-definition and --validate-only "
            "are mutually exclusive",
            file=sys.stderr,
        )
        return 2
    try:
        if arguments.emit_definition:
            digest = write_v15_definition(PACKAGE_ROOT, arguments.definition)
            payload = {"definition": str(arguments.definition), "sha256": digest}
        elif arguments.validate_only:
            manifest = validate_current_coverage_ledger_v15(
                arguments.output,
                definition_path=arguments.definition,
            )
            payload = {
                "artifacts": len(manifest["input_checkpoints"]),
                "ledger_id": manifest["ledger_id"],
                "output": str(arguments.output),
                "validated": True,
            }
        else:
            manifest = write_current_coverage_ledger_v15(
                arguments.definition,
                arguments.output,
                freeze=arguments.freeze,
            )
            payload = {
                "artifacts": len(manifest["input_checkpoints"]),
                "ledger_id": manifest["ledger_id"],
                "output": str(arguments.output),
            }
    except CurrentCoverageV15Error as error:
        print(f"current-coverage-v15 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
