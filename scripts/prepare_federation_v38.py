#!/usr/bin/env python3
"""Run the v38 prepublication validation without publishing finals."""

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.federation_v38 import prepare_federation_v38

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated-at")
    arguments = parser.parse_args()
    result = prepare_federation_v38(arguments.generated_at)
    print(json.dumps(result, indent=2, sort_keys=True))
