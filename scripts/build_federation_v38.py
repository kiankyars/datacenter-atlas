#!/usr/bin/env python3
"""Publish v38 only through the authorization-gated builder entrypoint."""

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.federation_v38 import main

if __name__ == "__main__":
    if "--publish-authorized" not in sys.argv[1:] and not {
        "-h",
        "--help",
    }.intersection(sys.argv[1:]):
        raise SystemExit(
            "build_federation_v38.py requires --publish-authorized; "
            "use prepare_federation_v38.py for prepublication validation"
        )
    raise SystemExit(main())
