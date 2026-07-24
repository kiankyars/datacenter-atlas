#!/usr/bin/env python3
"""Publish or validate exact-identity v9."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datacenter_atlas.exact_identity_decisions_v9 import (  # noqa: E402
    BUNDLE,
    DEFINITION,
    ExactIdentityDecisionError,
    validate_exact_identity_decision_bundle,
    write_exact_identity_decision_bundle,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--validate-only", action="store_true")
    result.add_argument("--definition", type=Path, default=DEFINITION)
    result.add_argument("--output-dir", type=Path, default=BUNDLE)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.validate_only:
            manifest = validate_exact_identity_decision_bundle(
                arguments.output_dir,
                definition_path=arguments.definition,
            )
        else:
            if arguments.definition != DEFINITION or arguments.output_dir != BUNDLE:
                raise ExactIdentityDecisionError(
                    "identity v9 publication paths are fixed and no-replace"
                )
            manifest = write_exact_identity_decision_bundle()
    except (OSError, ExactIdentityDecisionError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "bundle_id": manifest["bundle_id"],
                "counts": manifest["counts"],
                "definition": str(arguments.definition.resolve()),
                "output_directory": str(arguments.output_dir.resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
