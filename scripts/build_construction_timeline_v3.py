from __future__ import annotations

import argparse
import json
from pathlib import Path

from datacenter_atlas.construction_timeline_v3 import (
    write_construction_timeline_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the immutable open-seed-v67 construction timeline v3"
    )
    parser.add_argument("definition", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    manifest = write_construction_timeline_bundle(
        arguments.definition, arguments.output
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
