#!/usr/bin/env python3
"""Build or validate an immutable exact-identity decision bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datacenter_atlas.exact_identity_decisions import (  # noqa: E402
    ExactIdentityDecisionError,
    validate_exact_identity_decision_bundle,
    write_exact_identity_decision_bundle,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--definition", required=True, type=Path)
    result.add_argument("--output-dir", required=True, type=Path)
    result.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate an existing output rather than publishing it",
    )
    result.add_argument(
        "--verify-inputs",
        action="store_true",
        help="Rebuild from the definition and require byte-identical output",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.validate_only:
            manifest = validate_exact_identity_decision_bundle(
                arguments.output_dir,
                definition_path=arguments.definition,
                verify_inputs=arguments.verify_inputs,
            )
        else:
            if arguments.verify_inputs:
                raise ExactIdentityDecisionError(
                    "--verify-inputs is only valid with --validate-only"
                )
            manifest = write_exact_identity_decision_bundle(
                arguments.definition, arguments.output_dir
            )
    except (OSError, ExactIdentityDecisionError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "output_directory": str(arguments.output_dir.resolve()),
                "bundle_id": manifest["bundle_id"],
                "counts": manifest["counts"],
                "manifest_sha256": (arguments.output_dir / "manifest.sha256")
                .read_text(encoding="ascii")
                .split()[0],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
