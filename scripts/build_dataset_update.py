#!/usr/bin/env python3
"""Build or verify a dated Atlas data update from reviewed source projections."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datacenter_atlas.dataset_update import ROOT, _path, build_update, validate_update  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Override the definition's repository-relative output directory, or its date-based default.")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    input_path = args.input.resolve()
    definition = json.loads(input_path.read_text())
    default_output = definition.get("output") or f"verified_construction_core/{definition['updated_at']}"
    output = args.output or _path(ROOT, default_output)
    action = validate_update if args.validate_only else build_update
    manifest = action(input_path, output)
    print(json.dumps({"dataset": str(output), **manifest["counts"]}, sort_keys=True))


if __name__ == "__main__":
    main()
