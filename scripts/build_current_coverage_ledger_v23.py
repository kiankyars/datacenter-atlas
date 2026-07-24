#!/usr/bin/env python3
"""Preflight or build current-coverage ledger v23 once all pins are sealed."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from datacenter_atlas.current_coverage_v23 import (  # noqa: E402
    CurrentCoverageV23Error,
    preflight_v23_publication,
    publish_current_coverage_v23,
    validate_current_coverage_ledger_v23,
    write_current_coverage_ledger_v23,
    write_v23_definition,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--definition",
        type=Path,
        default=PACKAGE_ROOT / "sources/current-coverage-2026-07-21-v23.json",
    )
    result.add_argument(
        "--output",
        type=Path,
        default=PACKAGE_ROOT / "current_coverage_ledgers/2026-07-21-v23",
    )
    result.add_argument("--generated-at")
    result.add_argument("--emit-definition", action="store_true")
    result.add_argument("--preflight", action="store_true")
    result.add_argument("--publish", action="store_true")
    result.add_argument("--validate-only", action="store_true")
    result.add_argument("--freeze", action=argparse.BooleanOptionalAction, default=True)
    return result


def main() -> int:
    arguments = parser().parse_args()
    selected = sum(
        (
            arguments.emit_definition,
            arguments.preflight,
            arguments.publish,
            arguments.validate_only,
        )
    )
    if selected > 1:
        print("current-coverage-v23 error: select only one mode", file=sys.stderr)
        return 2
    try:
        if arguments.preflight:
            payload = preflight_v23_publication(PACKAGE_ROOT)
        elif arguments.publish:
            if not arguments.generated_at:
                raise CurrentCoverageV23Error(
                    "--generated-at is required with --publish"
                )
            payload = publish_current_coverage_v23(
                PACKAGE_ROOT, generated_at=arguments.generated_at
            )
        elif arguments.emit_definition:
            if not arguments.generated_at:
                raise CurrentCoverageV23Error(
                    "--generated-at is required with --emit-definition"
                )
            digest = write_v23_definition(
                PACKAGE_ROOT,
                arguments.definition,
                generated_at=arguments.generated_at,
            )
            payload = {"definition": str(arguments.definition), "sha256": digest}
        elif arguments.validate_only:
            payload = validate_current_coverage_ledger_v23(
                arguments.output, definition_path=arguments.definition
            )
        else:
            payload = write_current_coverage_ledger_v23(
                arguments.definition, arguments.output, freeze=arguments.freeze
            )
    except CurrentCoverageV23Error as error:
        print(f"current-coverage-v23 error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
