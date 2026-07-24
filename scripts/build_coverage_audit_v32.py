#!/usr/bin/env python3
"""Build or validate a private coverage-audit v32 candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.coverage_audit_v32 import (
    prepare_private_candidate,
    validate_private_candidate,
)
from datacenter_atlas.open_seed_v56 import tree_digest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate-root",
        required=True,
        type=Path,
        help="private candidate directory; must be absent when building",
    )
    parser.add_argument("--validate-only", action="store_true")
    arguments = parser.parse_args()
    if arguments.validate_only:
        manifest = validate_private_candidate(arguments.candidate_root)
        definition = next(arguments.candidate_root.glob("coverage-audit-*.json"))
        bundle = arguments.candidate_root / "bundle"
    else:
        definition, bundle, manifest = prepare_private_candidate(
            arguments.candidate_root
        )
    print(
        json.dumps(
            {
                "audit_id": manifest["audit_id"],
                "bundle_tree_sha256": tree_digest(bundle),
                "candidate_root": str(arguments.candidate_root.resolve()),
                "definition_sha256": _sha256(definition),
                "generated_at": manifest["generated_at"],
                "manifest_sha256": _sha256(bundle / "manifest.json"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
