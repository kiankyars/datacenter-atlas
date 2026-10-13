#!/usr/bin/env python3
"""Build or verify a frozen, lossless source-inventory consolidation."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datacenter_atlas.consolidation import ROOT, build_consolidation, validate_consolidation  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    input_path = args.input.resolve()
    updated = json.loads(input_path.read_text())["updated_at"]
    output = args.output or ROOT / "verified_construction_core" / (updated + "-consolidated")
    action = validate_consolidation if args.validate_only else build_consolidation
    manifest = action(input_path, output)
    print(json.dumps({"dataset": str(output), **manifest["counts"]}, sort_keys=True))


if __name__ == "__main__":
    main()
